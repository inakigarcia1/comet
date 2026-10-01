"""Whether a playback payload carries anything the scorer can use."""

from __future__ import annotations

from typing import Any, Mapping


def capabilities_active(capabilities: Mapping[str, Any] | None) -> bool:
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
    if isinstance(decoder, Mapping) and decoder:
        return True
    video = capabilities.get("video")
    if isinstance(video, Mapping) and video:
        return True
    return False
