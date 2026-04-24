from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.support import extract_bearer_token
from services.chatgpt_service import ChatGPTService, ImageGenerationError
from services.config import config
from utils.helper import sse_json_stream_with_heartbeat


class SimpleGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=4)
    stream: bool = False


def _require_api_key(authorization: str | None) -> None:
    auth_key = str(config.auth_key or "").strip()
    if not auth_key or extract_bearer_token(authorization) != auth_key:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "error": {"code": "unauthorized", "message": "invalid api key"}},
        )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _resolve_base_url(request: Request) -> str:
    return config.base_url or f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"


def _map_image_error(exc: Exception) -> tuple[int, str, str]:
    message = str(exc)
    if "no available image quota" in message.lower():
        return 429, "rate_limit", "no available image quota"
    return 502, "upstream_error", message


def _simple_event_stream(
    chunks: Iterator[dict],
    model: str,
    n: int,
) -> Iterator[dict]:
    yield {"type": "start", "model": model, "n": n}
    total_images = 0
    last_created: int | None = None
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        obj = str(chunk.get("object") or "")
        if obj == "image.generation.progress":
            yield {
                "type": "progress",
                "index": chunk.get("index"),
                "total": chunk.get("total"),
            }
            continue
        if obj == "image.generation.result":
            last_created = chunk.get("created") or last_created
            data = chunk.get("data") if isinstance(chunk.get("data"), list) else []
            for item in data:
                if not isinstance(item, dict):
                    continue
                b64 = str(item.get("b64_json") or "").strip()
                if not b64:
                    continue
                total_images += 1
                yield {
                    "type": "image",
                    "index": chunk.get("index"),
                    "b64_json": b64,
                }
    yield {"type": "done", "count": total_images, "created": last_created}


def create_router(chatgpt_service: ChatGPTService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/generate")
    async def generate(
            body: SimpleGenerateRequest,
            request: Request,
            authorization: str | None = Header(default=None),
    ):
        _require_api_key(authorization)
        base_url = _resolve_base_url(request)

        if body.stream:
            chunks = chatgpt_service.stream_image_generation(
                body.prompt, body.model, body.n, "b64_json", base_url,
            )
            return StreamingResponse(
                sse_json_stream_with_heartbeat(
                    _simple_event_stream(chunks, body.model, body.n)
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        try:
            result = await run_in_threadpool(
                chatgpt_service.generate_with_pool,
                body.prompt, body.model, body.n, "b64_json", base_url,
            )
        except ImageGenerationError as exc:
            status_code, code, message = _map_image_error(exc)
            return _error_response(status_code, code, message)
        except Exception as exc:
            return _error_response(502, "upstream_error", str(exc))

        data = result.get("data") if isinstance(result.get("data"), list) else []
        images = [
            {"b64_json": str(item.get("b64_json") or "")}
            for item in data
            if isinstance(item, dict) and item.get("b64_json")
        ]
        if not images:
            return _error_response(502, "empty_result", "no image returned")
        return {
            "success": True,
            "created": result.get("created"),
            "model": body.model,
            "count": len(images),
            "images": images,
        }

    return router
