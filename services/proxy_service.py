"""Global outbound proxy helpers for upstream ChatGPT and CPA requests.

Precedence for any outbound request is: per-account proxy > global proxy >
direct. Per-account overrides are passed via `build_session_kwargs(override_proxy=...)`.
An invalid override is logged and silently falls back to the global proxy so that a
single bad field cannot wedge the whole account.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse, urlunparse

from curl_cffi.requests import Session

from services.config import config
from utils.log import logger


class ProxySettingsStore:
    def build_session_kwargs(
            self,
            *,
            override_proxy: str | None = None,
            **session_kwargs,
    ) -> dict[str, object]:
        candidate = _clean(override_proxy)
        if candidate:
            if _is_valid_proxy_url(candidate):
                session_kwargs["proxy"] = candidate
                return session_kwargs
            logger.warning({
                "event": "proxy_override_invalid",
                "proxy": mask_proxy_url(candidate),
                "fallback": "global",
            })
        global_proxy = config.get_proxy_settings()
        if global_proxy:
            session_kwargs["proxy"] = global_proxy
        return session_kwargs


def _clean(value: object) -> str:
    return str(value or "").strip()


def _is_valid_proxy_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https", "socks5", "socks5h"} and bool(parsed.netloc)


def mask_proxy_url(url: str) -> str:
    """Return the proxy URL with any user:password credentials replaced by ***."""
    candidate = _clean(url)
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return candidate
    if not parsed.hostname:
        return candidate
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username or parsed.password:
        netloc = f"***@{netloc}"
    return urlunparse(parsed._replace(netloc=netloc))


def test_proxy(url: str, *, timeout: float = 15.0) -> dict:
    candidate = _clean(url)
    if not candidate:
        return {"ok": False, "status": 0, "latency_ms": 0, "error": "proxy url is required"}
    if not _is_valid_proxy_url(candidate):
        return {"ok": False, "status": 0, "latency_ms": 0, "error": "invalid proxy url"}
    session = Session(impersonate="edge101", verify=True, proxy=candidate)
    started = time.perf_counter()
    try:
        response = session.get(
            "https://chatgpt.com/api/auth/csrf",
            headers={"user-agent": "Mozilla/5.0 (chatgpt2api proxy test)"},
            timeout=timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": response.status_code < 500,
            "status": int(response.status_code),
            "latency_ms": latency_ms,
            "error": None if response.status_code < 500 else f"HTTP {response.status_code}",
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": 0,
            "latency_ms": latency_ms,
            "error": str(exc) or exc.__class__.__name__,
        }
    finally:
        session.close()

proxy_settings = ProxySettingsStore()

