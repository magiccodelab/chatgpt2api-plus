from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from services.config import DATA_DIR

USER_TOKENS_FILE = DATA_DIR / "user_tokens.json"
QUOTA_TIMEZONE = ZoneInfo("Asia/Shanghai")

DEFAULT_DAILY_LIMIT = 20


class UserTokenError(Exception):
    pass


def _now_local() -> datetime:
    return datetime.now(QUOTA_TIMEZONE)


def _today_str() -> str:
    return _now_local().date().isoformat()


def _next_reset_iso() -> str:
    tomorrow = _now_local().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow.isoformat()


def _new_id() -> str:
    return f"ut_{secrets.token_hex(6)}"


def _new_token() -> str:
    return secrets.token_hex(16)


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _mask_value(token: str) -> str:
    token = _clean_str(token)
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}{'*' * 6}{token[-4:]}"


class UserTokenService:
    def __init__(self, store_file: Path):
        self.store_file = store_file
        self._lock = RLock()
        self._entries = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.store_file.exists():
            return []
        try:
            data = json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            token = _clean_str(raw.get("token"))
            if not token:
                continue
            cleaned.append({
                "id": _clean_str(raw.get("id")) or _new_id(),
                "token": token,
                "name": _clean_str(raw.get("name")),
                "notes": _clean_str(raw.get("notes")),
                "daily_limit": max(0, int(raw.get("daily_limit") or DEFAULT_DAILY_LIMIT)),
                "used_today": max(0, int(raw.get("used_today") or 0)),
                "last_reset_date": _clean_str(raw.get("last_reset_date")) or _today_str(),
                "created_at": _clean_str(raw.get("created_at")) or _now_local().isoformat(),
                "updated_at": _clean_str(raw.get("updated_at")) or _now_local().isoformat(),
            })
        return cleaned

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._entries, ensure_ascii=False, indent=2) + "\n"
        self.store_file.write_text(payload, encoding="utf-8")

    def _find_by_token(self, token: str) -> dict[str, Any] | None:
        token = _clean_str(token)
        if not token:
            return None
        for entry in self._entries:
            if entry.get("token") == token:
                return entry
        return None

    def _find_by_id(self, entry_id: str) -> dict[str, Any] | None:
        entry_id = _clean_str(entry_id)
        if not entry_id:
            return None
        for entry in self._entries:
            if entry.get("id") == entry_id:
                return entry
        return None

    def _apply_daily_reset(self, entry: dict[str, Any]) -> bool:
        today = _today_str()
        if entry.get("last_reset_date") == today:
            return False
        entry["used_today"] = 0
        entry["last_reset_date"] = today
        entry["updated_at"] = _now_local().isoformat()
        return True

    def _status_for(self, entry: dict[str, Any]) -> dict[str, Any]:
        limit = int(entry.get("daily_limit") or 0)
        used = int(entry.get("used_today") or 0)
        remaining = max(0, limit - used)
        return {
            "name": entry.get("name") or "",
            "daily_limit": limit,
            "used_today": used,
            "remaining": remaining,
            "last_reset_date": entry.get("last_reset_date"),
            "reset_at": _next_reset_iso(),
        }

    def _public_entry(self, entry: dict[str, Any], include_plain_token: bool = False) -> dict[str, Any]:
        status = self._status_for(entry)
        item = {
            "id": entry.get("id"),
            "name": entry.get("name") or "",
            "notes": entry.get("notes") or "",
            "token_masked": _mask_value(entry.get("token") or ""),
            "daily_limit": status["daily_limit"],
            "used_today": status["used_today"],
            "remaining": status["remaining"],
            "last_reset_date": status["last_reset_date"],
            "reset_at": status["reset_at"],
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
        }
        if include_plain_token:
            item["token_plain"] = entry.get("token") or ""
        return item

    def list_tokens(self) -> list[dict[str, Any]]:
        with self._lock:
            changed = False
            for entry in self._entries:
                if self._apply_daily_reset(entry):
                    changed = True
            if changed:
                self._save()
            return [self._public_entry(entry) for entry in self._entries]

    def add_token(self, name: str, daily_limit: int, notes: str = "") -> dict[str, Any]:
        name = _clean_str(name)
        notes = _clean_str(notes)
        try:
            limit = max(0, int(daily_limit))
        except (TypeError, ValueError) as exc:
            raise UserTokenError("daily_limit must be a non-negative integer") from exc
        with self._lock:
            now_iso = _now_local().isoformat()
            entry = {
                "id": _new_id(),
                "token": _new_token(),
                "name": name or "未命名",
                "notes": notes,
                "daily_limit": limit,
                "used_today": 0,
                "last_reset_date": _today_str(),
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            self._entries.append(entry)
            self._save()
            return self._public_entry(entry, include_plain_token=True)

    def update_token(self, entry_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            entry = self._find_by_id(entry_id)
            if entry is None:
                return None
            if "name" in updates and updates["name"] is not None:
                entry["name"] = _clean_str(updates["name"]) or entry.get("name") or "未命名"
            if "notes" in updates and updates["notes"] is not None:
                entry["notes"] = _clean_str(updates["notes"])
            if "daily_limit" in updates and updates["daily_limit"] is not None:
                try:
                    entry["daily_limit"] = max(0, int(updates["daily_limit"]))
                except (TypeError, ValueError) as exc:
                    raise UserTokenError("daily_limit must be a non-negative integer") from exc
            if bool(updates.get("reset_usage")):
                entry["used_today"] = 0
                entry["last_reset_date"] = _today_str()
            entry["updated_at"] = _now_local().isoformat()
            self._save()
            return self._public_entry(entry)

    def delete_token(self, entry_id: str) -> bool:
        with self._lock:
            entry = self._find_by_id(entry_id)
            if entry is None:
                return False
            self._entries = [item for item in self._entries if item.get("id") != entry_id]
            self._save()
            return True

    def authenticate(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._find_by_token(token)
            if entry is None:
                return None
            if self._apply_daily_reset(entry):
                self._save()
            return dict(entry)

    def get_status(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._find_by_token(token)
            if entry is None:
                return None
            if self._apply_daily_reset(entry):
                self._save()
            return self._status_for(entry)

    def consume(self, token: str) -> tuple[bool, dict[str, Any] | None]:
        with self._lock:
            entry = self._find_by_token(token)
            if entry is None:
                return False, None
            self._apply_daily_reset(entry)
            limit = int(entry.get("daily_limit") or 0)
            used = int(entry.get("used_today") or 0)
            if used >= limit:
                self._save()
                return False, self._status_for(entry)
            entry["used_today"] = used + 1
            entry["updated_at"] = _now_local().isoformat()
            self._save()
            return True, self._status_for(entry)

    def refund(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._find_by_token(token)
            if entry is None:
                return None
            used = int(entry.get("used_today") or 0)
            entry["used_today"] = max(0, used - 1)
            entry["updated_at"] = _now_local().isoformat()
            self._save()
            return self._status_for(entry)


user_token_service = UserTokenService(USER_TOKENS_FILE)
