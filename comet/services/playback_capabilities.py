"""Filename-based playback compatibility using client-reported partial capabilities."""

from __future__ import annotations

import re
from typing import Any, Mapping

_PIXEL_SIZE = re.compile(r"\b(\d{3,5})\s*[xX×]\s*(\d{3,5})\b")
_FPS = re.compile(
    r"\b(?:@|fps[\s\.\-_]*)(?P<fps>23\.976|24|25|30|48|50|60)(?:\s*fps)?\b"
    r"|\b(?P<fps2>23\.976|24|25|30|48|50|60)\s*fps\b",
    re.IGNORECASE,
)

_STANDARD_CELLS: dict[str, tuple[int, int, int]] = {
    "720p30": (1280, 720, 30),
    "720p60": (1280, 720, 60),
    "1080p30": (1920, 1080, 30),
    "1080p60": (1920, 1080, 60),
    "1440p30": (2560, 1440, 30),
    "1440p60": (2560, 1440, 60),
    "2160p24": (3840, 2160, 24),
    "2160p30": (3840, 2160, 30),
    "2160p60": (3840, 2160, 60),
}

_LABEL_DIMENSIONS: dict[str, tuple[int, int]] = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1080i": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
    "4k": (3840, 2160),
    "4320p": (7680, 4320),
    "8k": (7680, 4320),
    "uhd": (3840, 2160),
}


def _parse_fps(text: str) -> int | None:
    match = _FPS.search(text)
    if not match:
        return None
    raw = match.group("fps") or match.group("fps2")
    if raw.startswith("23.976"):
        return 24
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_dimensions(text: str) -> tuple[int, int, bool]:
    pixel = _PIXEL_SIZE.search(text)
    if pixel:
        w, h = int(pixel.group(1)), int(pixel.group(2))
        if w > 0 and h > 0:
            return w, h, True
    upper = text.upper()
    for label, (w, h) in _LABEL_DIMENSIONS.items():
        if label.upper() in upper:
            return w, h, True
    return 0, 0, False


def _parse_mime(text: str) -> str | None:
    upper = text.upper()
    if "AV1" in upper or "AV01" in upper:
        return "video/av01"
    if "VP9" in upper:
        return "video/x-vnd.on2.vp9"
    if any(token in upper for token in ("HEVC", "H265", "H.265", "X265")):
        return "video/hevc"
    if any(token in upper for token in ("H264", "H.264", "X264", "AVC")):
        return "video/avc"
    return None


def _fits_screen(video_w: int, video_h: int, screen_w: int, screen_h: int) -> bool:
    screen_long = max(screen_w, screen_h)
    screen_short = min(screen_w, screen_h)
    video_long = max(video_w, video_h)
    video_short = min(video_w, video_h)
    return video_long <= screen_long and video_short <= screen_short


def _matrix_supports(
    matrix: Mapping[str, Any],
    mime: str,
    video_w: int,
    video_h: int,
    fps: int | None,
) -> bool:
    cells = matrix.get(mime)
    if not isinstance(cells, Mapping) or not cells:
        return False
    for cell_key, supported in cells.items():
        if not supported:
            continue
        standard = _STANDARD_CELLS.get(str(cell_key))
        if not standard:
            continue
        cw, ch, cfps = standard
        if cw < video_w or ch < video_h:
            continue
        if fps is not None and fps != cfps:
            continue
        return True
    return False


def _codec_list_supports(codecs: list[str], mime: str) -> bool:
    mime_lower = mime.lower()
    return any(isinstance(codec, str) and codec.lower() == mime_lower for codec in codecs)


def playback_capabilities_active(capabilities: Mapping[str, Any] | None) -> bool:
    if not isinstance(capabilities, Mapping):
        return False
    screen = capabilities.get("screen")
    if isinstance(screen, Mapping):
        try:
            if int(screen.get("width") or 0) > 0 and int(screen.get("height") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    codecs = capabilities.get("codecs")
    if isinstance(codecs, list) and codecs:
        return True
    decoder = capabilities.get("decoderCapabilities")
    return isinstance(decoder, Mapping) and bool(decoder)


def torrent_title_allowed(torrent_title: str, capabilities: Mapping[str, Any] | None) -> bool:
    if not playback_capabilities_active(capabilities):
        return True
    if not isinstance(torrent_title, str) or not torrent_title:
        return True

    video_w, video_h, has_dimensions = _parse_dimensions(torrent_title)
    fps = _parse_fps(torrent_title)
    mime = _parse_mime(torrent_title)

    screen = capabilities.get("screen") if isinstance(capabilities, Mapping) else None
    if isinstance(screen, Mapping) and has_dimensions:
        try:
            sw = int(screen.get("width") or 0)
            sh = int(screen.get("height") or 0)
        except (TypeError, ValueError):
            sw, sh = 0, 0
        if sw > 0 and sh > 0 and not _fits_screen(video_w, video_h, sw, sh):
            return False

    if mime is None:
        return True

    decoder = capabilities.get("decoderCapabilities") if isinstance(capabilities, Mapping) else None
    if isinstance(decoder, Mapping) and decoder:
        if not has_dimensions:
            return True
        return _matrix_supports(decoder, mime, video_w, video_h, fps)

    codecs = capabilities.get("codecs") if isinstance(capabilities, Mapping) else None
    if isinstance(codecs, list) and codecs:
        return _codec_list_supports(codecs, mime)

    return True
