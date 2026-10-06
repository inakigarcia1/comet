from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from fastapi.responses import FileResponse, JSONResponse, Response

from comet.core.logger import logger
from comet.utils.cache import NO_CACHE_HEADERS
from comet.utils.network import get_client_ip_any
from comet.utils.status_keys import normalize_status_key

STATUS_VIDEO_DIR = Path("comet/assets/status_videos")
GENERAL_ERROR_VIDEO = Path("comet/assets/Error_General_Apachiy.mp4")
DEFAULT_STATUS_KEY = "UNKNOWN"
_DETAIL_LIMIT = 4000
_SECRET_KEYS = {"apikey", "api_key", "authorization", "token", "debridapikey"}


def _iter_normalized_keys(status_keys: Iterable[str | None]) -> list[str]:
    normalized_keys = []
    seen = set()
    for status_key in status_keys:
        normalized = normalize_status_key(status_key)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_keys.append(normalized)
    return normalized_keys


def _status_video_directory_revision() -> int | None:
    try:
        return STATUS_VIDEO_DIR.stat().st_mtime_ns
    except FileNotFoundError:
        return None


@lru_cache(maxsize=4)
def _build_status_video_index(
    directory_revision: int | None,
) -> dict[str, str]:
    del directory_revision
    status_files = sorted(STATUS_VIDEO_DIR.glob("*.mp4"))
    status_video_index = {}

    for status_file in status_files:
        normalized_key = normalize_status_key(status_file.stem)
        if normalized_key and normalized_key not in status_video_index:
            status_video_index[normalized_key] = str(status_file)

    return status_video_index


def resolve_status_video_path(
    status_keys: Iterable[str | None],
    default_key: str = DEFAULT_STATUS_KEY,
) -> str | None:
    status_video_index = _build_status_video_index(_status_video_directory_revision())

    for key in _iter_normalized_keys(status_keys):
        video_path = status_video_index.get(key)
        if video_path:
            return video_path

    default_normalized = normalize_status_key(default_key) or DEFAULT_STATUS_KEY
    default_video = status_video_index.get(default_normalized)
    if default_video:
        return default_video

    unknown_video = status_video_index.get(DEFAULT_STATUS_KEY)
    if unknown_video:
        return unknown_video

    return None


def request_context(request) -> dict:
    ip, from_proxy = get_client_ip_any(request)
    return {
        "ip": ip,
        "ip_from_proxy": from_proxy,
        "user_agent": request.headers.get("user-agent", ""),
    }


def _clip(value) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= _DETAIL_LIMIT:
        return text
    return text[:_DETAIL_LIMIT] + "...(truncated)"


def _log_replaced_status_video(
    code: str,
    status_keys: list[str],
    default_key: str,
    detail: dict,
) -> None:
    lines = [
        "Comet reemplazó un video de estado por Error_General_Apachiy.mp4.",
        f"  code={code}",
        f"  keys={status_keys or [default_key]}",
        f"  default={default_key}",
    ]
    for key, value in detail.items():
        if value is None or value == "":
            continue
        if key.lower() in _SECRET_KEYS:
            value = "***"
        lines.append(f"  {key}={_clip(value)}")
    logger.error("\n".join(lines))


def build_status_video_response(
    status_keys: Iterable[str | None],
    default_key: str = DEFAULT_STATUS_KEY,
    *,
    detail: dict | None = None,
) -> Response:
    normalized_keys = _iter_normalized_keys(status_keys)
    normalized_default = normalize_status_key(default_key) or DEFAULT_STATUS_KEY
    code = normalized_keys[0] if normalized_keys else normalized_default
    _log_replaced_status_video(code, normalized_keys, normalized_default, detail or {})

    if not GENERAL_ERROR_VIDEO.is_file():
        logger.error(f"Missing general error video at {GENERAL_ERROR_VIDEO}")
        return JSONResponse(
            status_code=500,
            content={"detail": "General error video is missing on server.", "code": code},
            headers=NO_CACHE_HEADERS,
        )

    return FileResponse(
        GENERAL_ERROR_VIDEO,
        headers=NO_CACHE_HEADERS,
    )
