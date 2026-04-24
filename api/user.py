from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.support import (
    extract_bearer_token,
    require_auth_key,
    resolve_image_base_url,
)
from services.chatgpt_service import ChatGPTService, ImageGenerationError
from services.user_token_service import UserTokenError, user_token_service


class UserImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "auto"


class UserTokenCreateRequest(BaseModel):
    name: str = ""
    daily_limit: int = 20
    notes: str = ""


class UserTokenUpdateRequest(BaseModel):
    name: str | None = None
    daily_limit: int | None = None
    notes: str | None = None
    reset_usage: bool | None = None


def _require_user_token(authorization: str | None) -> dict:
    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "authorization is invalid", "code": "unauthorized"},
        )
    entry = user_token_service.authenticate(token)
    if entry is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid user token", "code": "unauthorized"},
        )
    return entry


def _raise_quota_exhausted(status: dict | None) -> None:
    raise HTTPException(
        status_code=429,
        detail={
            "error": "daily quota exhausted",
            "code": "quota_exhausted",
            "status": status,
        },
    )


def _raise_image_error(exc: Exception) -> None:
    message = str(exc)
    if "no available image quota" in message.lower():
        raise HTTPException(
            status_code=429,
            detail={"error": "no available image quota", "code": "pool_exhausted"},
        ) from exc
    raise HTTPException(status_code=502, detail={"error": message, "code": "upstream_error"}) from exc


def create_router(chatgpt_service: ChatGPTService) -> APIRouter:
    router = APIRouter()

    # ── 用户侧（Bearer user_token）────────────────────────────────────────

    @router.post("/api/user/auth/login")
    async def user_login(authorization: str | None = Header(default=None)):
        entry = _require_user_token(authorization)
        return {"ok": True, "status": user_token_service.get_status(entry["token"])}

    @router.get("/api/user/me")
    async def user_me(authorization: str | None = Header(default=None)):
        entry = _require_user_token(authorization)
        return {"status": user_token_service.get_status(entry["token"])}

    @router.post("/api/user/images/generations")
    async def user_generate_images(
        body: UserImageGenerationRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        entry = _require_user_token(authorization)
        token = entry["token"]
        base_url = resolve_image_base_url(request)

        ok, status = user_token_service.consume(token)
        if not ok:
            _raise_quota_exhausted(status)

        try:
            result = await run_in_threadpool(
                chatgpt_service.generate_with_pool,
                body.prompt,
                body.model or "auto",
                1,
                "b64_json",
                base_url,
            )
        except ImageGenerationError as exc:
            user_token_service.refund(token)
            _raise_image_error(exc)
        except Exception as exc:
            user_token_service.refund(token)
            raise HTTPException(status_code=502, detail={"error": str(exc), "code": "upstream_error"}) from exc

        if isinstance(result, dict):
            result = dict(result)
            result["usage"] = user_token_service.get_status(token)
        return result

    @router.post("/api/user/images/edits")
    async def user_edit_images(
        request: Request,
        authorization: str | None = Header(default=None),
        image: list[UploadFile] | None = File(default=None),
        image_list: list[UploadFile] | None = File(default=None, alias="image[]"),
        prompt: str = Form(...),
        model: str = Form(default="auto"),
    ):
        entry = _require_user_token(authorization)
        token = entry["token"]
        base_url = resolve_image_base_url(request)

        uploads = [*(image or []), *(image_list or [])]
        if not uploads:
            raise HTTPException(status_code=400, detail={"error": "image file is required"})
        images: list[tuple[bytes, str, str]] = []
        for upload in uploads:
            image_data = await upload.read()
            if not image_data:
                raise HTTPException(status_code=400, detail={"error": "image file is empty"})
            images.append((image_data, upload.filename or "image.png", upload.content_type or "image/png"))

        ok, status = user_token_service.consume(token)
        if not ok:
            _raise_quota_exhausted(status)

        try:
            result = await run_in_threadpool(
                chatgpt_service.edit_with_pool,
                prompt,
                images,
                model or "auto",
                1,
                "b64_json",
                base_url,
            )
        except ImageGenerationError as exc:
            user_token_service.refund(token)
            _raise_image_error(exc)
        except Exception as exc:
            user_token_service.refund(token)
            raise HTTPException(status_code=502, detail={"error": str(exc), "code": "upstream_error"}) from exc

        if isinstance(result, dict):
            result = dict(result)
            result["usage"] = user_token_service.get_status(token)
        return result

    # ── 管理员侧（Bearer admin auth-key）──────────────────────────────────

    @router.get("/api/admin/user-tokens")
    async def list_user_tokens(authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        return {"items": user_token_service.list_tokens()}

    @router.post("/api/admin/user-tokens")
    async def create_user_token(
        body: UserTokenCreateRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        try:
            item = user_token_service.add_token(body.name, body.daily_limit, body.notes)
        except UserTokenError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"item": item, "items": user_token_service.list_tokens()}

    @router.post("/api/admin/user-tokens/{entry_id}")
    async def update_user_token(
        entry_id: str,
        body: UserTokenUpdateRequest,
        authorization: str | None = Header(default=None),
    ):
        require_auth_key(authorization)
        try:
            item = user_token_service.update_token(entry_id, body.model_dump(exclude_none=True))
        except UserTokenError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        if item is None:
            raise HTTPException(status_code=404, detail={"error": "user token not found"})
        return {"item": item, "items": user_token_service.list_tokens()}

    @router.delete("/api/admin/user-tokens/{entry_id}")
    async def delete_user_token(entry_id: str, authorization: str | None = Header(default=None)):
        require_auth_key(authorization)
        if not user_token_service.delete_token(entry_id):
            raise HTTPException(status_code=404, detail={"error": "user token not found"})
        return {"items": user_token_service.list_tokens()}

    return router
