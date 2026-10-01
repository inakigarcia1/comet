"""Parse the capability JSON a client sends with the stream request."""

from __future__ import annotations

from typing import Any, Mapping

from comet.services.compatibility.models import (
    CodecSupport,
    DevicePlaybackCapabilities,
    ObservedFailure,
)

_CODEC_NAMES = {
    "video/avc": "avc",
    "video/h264": "avc",
    "avc": "avc",
    "h264": "avc",
    "h.264": "avc",
    "video/hevc": "hevc",
    "video/h265": "hevc",
    "hevc": "hevc",
    "h265": "hevc",
    "h.265": "hevc",
    "video/x-vnd.on2.vp9": "vp9",
    "vp9": "vp9",
    "video/av01": "av1",
    "video/av1": "av1",
    "av1": "av1",
    "av01": "av1",
    "video/x-vnd.on2.vp8": "vp8",
    "vp8": "vp8",
    "video/mpeg2": "mpeg2",
    "mpeg2": "mpeg2",
    "video/dolby-vision": "dolby-vision",
    "dolbyvision": "dolby-vision",
    "dolby-vision": "dolby-vision",
}

_CELLS: dict[str, tuple[int, int, int]] = {
    "720p30": (1280, 720, 30),
    "720p60": (1280, 720, 60),
    "1080p30": (1920, 1080, 30),
    "1080p60": (1920, 1080, 60),
    "1440p30": (2560, 1440, 30),
    "1440p60": (2560, 1440, 60),
    "2160p24": (3840, 2160, 24),
    "2160p30": (3840, 2160, 30),
    "2160p60": (3840, 2160, 60),
    "4320p30": (7680, 4320, 30),
    "4320p60": (7680, 4320, 60),
}

_PROFILE_NAMES = {
    "main": "Main",
    "main8": "Main",
    "main10": "Main10",
    "main10hdr10": "Main10",
    "main10hdr10plus": "Main10",
    "high": "High",
    "high10": "High10",
    "hi10": "High10",
    "hi10p": "High10",
    "baseline": "Baseline",
    "constrainedbaseline": "Baseline",
    "constrainedhigh": "High",
    "profile0": "Profile0",
    "0": "Profile0",
    "profile2": "Profile2",
    "2": "Profile2",
}

_PROFILE_BITS = {
    "Main": 8,
    "Baseline": 8,
    "High": 8,
    "Main10": 10,
    "High10": 10,
    "Profile0": 8,
    "Profile2": 10,
}

_PROBED_MODERN = {"avc", "hevc", "vp9", "av1"}


def parse_device(capabilities: Mapping[str, Any] | None) -> DevicePlaybackCapabilities:
    device = DevicePlaybackCapabilities()
    if not isinstance(capabilities, Mapping):
        return device

    platform = capabilities.get("platform")
    if isinstance(platform, str) and platform.strip():
        device.platform = platform.strip()
    backend = capabilities.get("playerBackend")
    if isinstance(backend, str) and backend.strip():
        device.player_backend = backend.strip()

    screen = capabilities.get("screen")
    if isinstance(screen, Mapping):
        device.screen_width = _positive_int(screen.get("width"))
        device.screen_height = _positive_int(screen.get("height"))

    video = capabilities.get("video")
    if isinstance(video, Mapping):
        device.codec_probe = True
        for raw_name, raw_support in video.items():
            name = _codec_name(raw_name)
            if name is None or not isinstance(raw_support, Mapping):
                continue
            support = device.codecs.setdefault(name, CodecSupport())
            support.present = True
            support.profiles_probed = True
            _read_codec_block(support, raw_support)

    matrix = capabilities.get("decoderCapabilities")
    if isinstance(matrix, Mapping) and matrix:
        device.codec_probe = True
        for raw_name, cells in matrix.items():
            name = _codec_name(raw_name)
            if name is None or not isinstance(cells, Mapping):
                continue
            support = device.codecs.setdefault(name, CodecSupport())
            support.present = True
            for cell_name, enabled in cells.items():
                if not enabled:
                    continue
                cell = _CELLS.get(str(cell_name).lower())
                if cell and cell not in support.rates:
                    support.rates.append(cell)
            if support.rates:
                support.max_width = max(support.max_width, max(item[0] for item in support.rates))
                support.max_height = max(support.max_height, max(item[1] for item in support.rates))

    codecs = capabilities.get("codecs")
    if isinstance(codecs, list) and codecs:
        device.codec_probe = True
        for raw_name in codecs:
            name = _codec_name(raw_name)
            if name is None:
                continue
            support = device.codecs.setdefault(name, CodecSupport())
            support.present = True

    hdr = capabilities.get("hdr")
    if isinstance(hdr, Mapping):
        probed = hdr.get("probed")
        device.hdr_probed = probed is not False
        for key, tag in (
            ("hdr10", "hdr10"),
            ("hdr10Plus", "hdr10+"),
            ("hlg", "hlg"),
        ):
            if hdr.get(key) is True:
                device.display_hdr.add(tag)
        if "dolbyVision" in hdr:
            device.dolby_vision = bool(hdr.get("dolbyVision"))
    if "dolby-vision" in device.codecs and device.codecs["dolby-vision"].present:
        device.dolby_vision = True
        device.hdr_probed = True

    audio = capabilities.get("audio")
    if isinstance(audio, Mapping):
        device.audio_probed = True
        for key, value in audio.items():
            if isinstance(key, str):
                device.audio[key.strip().lower()] = bool(value)

    failures = capabilities.get("observedFailures")
    if isinstance(failures, list):
        for item in failures:
            parsed = _read_failure(item)
            if parsed is not None:
                device.observed_failures.append(parsed)

    return device


def describe_device(capabilities: Mapping[str, Any] | None) -> str:
    if not isinstance(capabilities, Mapping) or not capabilities:
        return "-"
    device = parse_device(capabilities)
    parts: list[str] = []
    if device.platform:
        parts.append(f"platform={device.platform}")
    if device.player_backend:
        parts.append(f"player={device.player_backend}")
    if device.screen_width and device.screen_height:
        parts.append(f"screen={device.screen_width}x{device.screen_height}")
    codec_bits = []
    for name in ("avc", "hevc", "vp9", "av1", "vp8", "mpeg2"):
        support = device.codecs.get(name)
        if support is None or not support.present:
            continue
        profiles = ",".join(sorted(support.profiles)) or "-"
        depths = ",".join(str(item) for item in sorted(support.bit_depths)) or "-"
        level = f"L{support.max_level:g}" if support.max_level is not None else "-"
        size = f"{support.max_width}x{support.max_height}" if support.max_height else "-"
        rates = ",".join(_rate_label(rate) for rate in support.rates[:6]) or "-"
        codec_bits.append(f"{name}[{profiles}/{depths}bit/{level}/{size}/{rates}]")
    parts.append("codecs=" + ("|".join(codec_bits) if codec_bits else "-"))
    if device.hdr_probed:
        hdr = ",".join(sorted(device.display_hdr)) or "none"
        dv = "yes" if device.dolby_vision else "no"
        parts.append(f"hdr={hdr} dv={dv}")
    else:
        parts.append("hdr=unknown dv=unknown")
    if device.audio_probed:
        enabled = [name for name, ok in sorted(device.audio.items()) if ok]
        parts.append("audio=" + (",".join(enabled) if enabled else "none"))
    else:
        parts.append("audio=unknown")
    if device.observed_failures:
        parts.append(f"observedFailures={len(device.observed_failures)}")
    return " ".join(parts)


def _read_codec_block(support: CodecSupport, block: Mapping[str, Any]) -> None:
    profiles = block.get("profiles") or []
    if isinstance(profiles, list):
        for raw in profiles:
            name = _profile_name(raw)
            if name:
                support.profiles.add(name)
                bits = _PROFILE_BITS.get(name)
                if bits:
                    support.bit_depths.add(bits)
    depths = block.get("bitDepths") or block.get("bit_depths") or []
    if isinstance(depths, list):
        for raw in depths:
            value = _positive_int(raw)
            if value in (8, 10, 12):
                support.bit_depths.add(value)
    level = block.get("maxLevel") or block.get("max_level")
    parsed_level = _level_number(level)
    if parsed_level is not None:
        support.max_level = parsed_level
    support.max_width = max(support.max_width, _positive_int(block.get("maxWidth") or block.get("max_width")))
    support.max_height = max(support.max_height, _positive_int(block.get("maxHeight") or block.get("max_height")))
    hdr = block.get("hdr") or []
    if isinstance(hdr, list):
        for item in hdr:
            if isinstance(item, str) and item.strip():
                support.hdr.add(item.strip().lower().replace("hdr10plus", "hdr10+"))


def _read_failure(item: Any) -> ObservedFailure | None:
    if not isinstance(item, Mapping):
        return None
    count = _positive_int(item.get("count") or 1)
    if count <= 0:
        return None
    codec = _codec_name(item.get("codec")) if item.get("codec") else _codec_from_codecs_string(item.get("codecs"), item.get("mime"))
    profile = _profile_name(item.get("profile")) if item.get("profile") else _profile_from_codecs_string(item.get("codecs"))
    height = _positive_int(item.get("minHeight") or item.get("height"))
    dolby = bool(item.get("dolbyVision")) or _codecs_are_dolby(item.get("codecs"))
    if codec is None and profile is None and not dolby:
        return None
    return ObservedFailure(
        codec=codec,
        profile=profile,
        min_height=height or None,
        dolby_vision=dolby,
        count=count,
    )


def _codec_from_codecs_string(codecs: Any, mime: Any) -> str | None:
    from_mime = _codec_name(mime) if isinstance(mime, str) else None
    if from_mime and from_mime != "dolby-vision":
        return from_mime
    if not isinstance(codecs, str):
        return from_mime
    lowered = codecs.lower()
    if lowered.startswith(("dvh1", "dvhe", "dav1")):
        return "hevc"
    if lowered.startswith(("hvc1", "hev1")):
        return "hevc"
    if lowered.startswith("avc1"):
        return "avc"
    if lowered.startswith("av01"):
        return "av1"
    if "vp09" in lowered or lowered.startswith("vp9"):
        return "vp9"
    return from_mime


def _profile_from_codecs_string(codecs: Any) -> str | None:
    if not isinstance(codecs, str):
        return None
    lowered = codecs.lower()
    if lowered.startswith(("dvh1", "dvhe")):
        return "Main10"
    # hvc1.2 / hev1.2 is Main 10. hvc1.1 is Main.
    if lowered.startswith(("hvc1.2", "hev1.2")):
        return "Main10"
    if lowered.startswith(("hvc1.1", "hev1.1")):
        return "Main"
    return None


def _codecs_are_dolby(codecs: Any) -> bool:
    return isinstance(codecs, str) and codecs.lower().startswith(("dvh1", "dvhe"))


def _codec_name(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    return _CODEC_NAMES.get(raw.strip().lower())


def _profile_name(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if not key:
        return None
    return _PROFILE_NAMES.get(key, str(raw).strip())


def _level_number(raw: Any) -> float | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower().removeprefix("l").removeprefix("level").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _positive_int(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _rate_label(rate: tuple[int, int, int]) -> str:
    height, fps = rate[1], rate[2]
    return f"{height}p{fps}"


def modern_codec_was_probed(device: DevicePlaybackCapabilities) -> bool:
    return any(name in device.codecs for name in _PROBED_MODERN)
