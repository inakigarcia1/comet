"""Score how likely a parsed stream is to play on one device.

The number is a playback probability, not a quality rank. Two scores in the
same band of 5 are tied; the caller then prefers the taller picture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from comet.services.compatibility.device_capabilities import parse_device
from comet.services.compatibility.filename_parser import parse_filename
from comet.services.compatibility.models import (
    CodecSupport,
    DevicePlaybackCapabilities,
    StreamCharacteristics,
)
from comet.services.compatibility.playback_active import capabilities_active

SIMILAR_SCORE_BAND = 5
_INCOMPATIBLE_SCORE = 5
_MODERN = {"avc", "hevc", "vp9", "av1"}


@dataclass
class CompatibilityResult:
    score: int
    incompatible: bool
    height: int
    summary: str
    raised: list[str] = field(default_factory=list)
    lowered: list[str] = field(default_factory=list)
    stream: StreamCharacteristics | None = None


def score_band(score: int) -> int:
    """Band used as the primary sort key. Nearby scores share a band."""
    return (score + SIMILAR_SCORE_BAND // 2) // SIMILAR_SCORE_BAND


def playback_sort_key(score: int, height: int) -> tuple[int, int]:
    return (score_band(score), height)


def evaluate_title(
    filename: str,
    capabilities: Mapping[str, Any] | None,
) -> CompatibilityResult | None:
    if not capabilities_active(capabilities):
        return None
    device = parse_device(capabilities)
    stream = parse_filename(filename or "")
    return evaluate(stream, device)


def evaluate(
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
) -> CompatibilityResult:
    raised: list[str] = []
    lowered: list[str] = []
    blocking: list[str] = []

    codec = stream.codec.value if stream.codec.known else None
    codec_name = codec if isinstance(codec, str) else None
    support = device.codec(codec_name)
    height = stream.height or 0

    _check_screen(stream, device, blocking)
    _check_codec_presence(codec_name, support, device, blocking)
    _check_profile_and_depth(stream, codec_name, support, device, blocking)
    _check_size_and_fps(stream, codec_name, support, device, blocking)
    _check_level(stream, support, blocking)
    _check_observed_failures(stream, device, blocking, lowered)

    if blocking:
        summary = _summary(stream, _INCOMPATIBLE_SCORE, True, raised, blocking)
        return CompatibilityResult(
            score=_INCOMPATIBLE_SCORE,
            incompatible=True,
            height=height,
            summary=summary,
            raised=raised,
            lowered=blocking,
            stream=stream,
        )

    score = 18
    score = _score_codec(score, codec_name, support, raised, lowered)
    score = _score_profile(score, stream, codec_name, support, raised, lowered)
    score = _score_bit_depth(score, stream, codec_name, support, raised, lowered)
    score = _score_resolution(score, stream, support, raised, lowered)
    score = _score_fps(score, stream, support, raised, lowered)
    score = _score_hdr(score, stream, device, support, raised, lowered)
    score = _score_dolby_vision(score, stream, device, raised, lowered)
    score = _score_audio(score, stream, device, raised, lowered)
    score = _score_evidence(score, stream, raised, lowered)
    if stream.conflicts:
        score -= 12
        lowered.append("conflicting labels")

    score = max(9, min(100, score))
    return CompatibilityResult(
        score=score,
        incompatible=False,
        height=height,
        summary=_summary(stream, score, False, raised, lowered),
        raised=raised,
        lowered=lowered,
        stream=stream,
    )


def _check_screen(
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
    blocking: list[str],
) -> None:
    if not stream.width or not stream.height:
        return
    if device.screen_width <= 0 or device.screen_height <= 0:
        return
    if not _fits(stream.width, stream.height, device.screen_width, device.screen_height):
        blocking.append("resolution exceeds screen")


def _check_codec_presence(
    codec_name: str | None,
    support: CodecSupport | None,
    device: DevicePlaybackCapabilities,
    blocking: list[str],
) -> None:
    if codec_name not in _MODERN or not device.codec_probe:
        return
    if support is None:
        blocking.append(f"{codec_name} not supported")


def _check_profile_and_depth(
    stream: StreamCharacteristics,
    codec_name: str | None,
    support: CodecSupport | None,
    device: DevicePlaybackCapabilities,
    blocking: list[str],
) -> None:
    if not _strong_ten_bit(stream) and not _strong_main10(stream) and not _strong_high10(stream):
        return

    if codec_name == "hevc" and support is not None and support.profiles_probed:
        if _strong_main10(stream) or (_strong_ten_bit(stream) and codec_name == "hevc"):
            if "Main10" not in support.profiles and 10 not in support.bit_depths:
                blocking.append("device does not support Main10")
                return
    if codec_name == "avc" and support is not None and support.profiles_probed:
        if _strong_high10(stream) or (
            stream.bit_depth.known and stream.bit_depth.value == 10 and stream.bit_depth.is_source("explicit", "inferred_high")
        ):
            if "High10" not in support.profiles and 10 not in support.bit_depths:
                blocking.append("device does not support AVC High10")
                return
    if codec_name == "vp9" and support is not None and support.profiles_probed:
        wants_ten = stream.profile.value == "Profile2" or _strong_ten_bit(stream)
        if wants_ten and "Profile2" not in support.profiles and 10 not in support.bit_depths:
            blocking.append("device does not support VP9 10-bit")
            return
    if codec_name == "av1" and support is not None and support.profiles_probed:
        if _strong_ten_bit(stream) and "Main10" not in support.profiles and 10 not in support.bit_depths:
            blocking.append("device does not support AV1 10-bit")
            return

    if codec_name is None and _strong_ten_bit(stream) and _profiles_were_probed(device):
        if not _any_codec_supports_ten_bit(device):
            blocking.append("device does not support 10-bit")


def _check_size_and_fps(
    stream: StreamCharacteristics,
    codec_name: str | None,
    support: CodecSupport | None,
    device: DevicePlaybackCapabilities,
    blocking: list[str],
) -> None:
    if not stream.width or not stream.height:
        return
    if support is not None and not _size_supported(stream, support):
        blocking.append("resolution exceeds decoder")
        return
    if codec_name is None and device.codec_probe and not _any_codec_supports_size(stream, device):
        blocking.append("resolution exceeds decoder")
        return
    fps = _stream_fps(stream)
    if fps is None:
        return
    target = support
    if target is not None and target.rates and not _rate_covers(stream, target, fps):
        blocking.append("fps exceeds decoder")
    elif target is None and device.codec_probe and not _any_rate_covers(stream, device, fps):
        if _any_rates(device):
            blocking.append("fps exceeds decoder")


def _check_level(
    stream: StreamCharacteristics,
    support: CodecSupport | None,
    blocking: list[str],
) -> None:
    if support is None or support.max_level is None or not stream.level.known:
        return
    try:
        needed = float(stream.level.value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if needed > support.max_level + 0.05:
        blocking.append(f"level {stream.level.value} exceeds decoder")


def _check_observed_failures(
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
    blocking: list[str],
    lowered: list[str],
) -> None:
    for failure in device.observed_failures:
        if not _failure_matches(stream, failure):
            continue
        specific = bool(failure.profile or failure.dolby_vision)
        if specific:
            blocking.append("this device already failed this profile")
            return
        lowered.append("similar stream already failed on this device")


def _score_codec(
    score: int,
    codec_name: str | None,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    if codec_name and support is not None:
        score += 26
        raised.append("codec supported")
        return score
    if codec_name and support is None:
        score += 8
        lowered.append("codec support unknown")
        return score
    score += 4
    lowered.append("codec unknown")
    return score


def _score_profile(
    score: int,
    stream: StreamCharacteristics,
    codec_name: str | None,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    profile = stream.profile.value if stream.profile.known else None
    probed = support is not None and support.profiles_probed
    if profile and probed and isinstance(profile, str) and profile in (support.profiles if support else set()):
        if stream.profile.source == "explicit":
            score += 16
            raised.append("profile supported")
        else:
            score += 13
            raised.append("profile likely supported")
        return score
    if profile and probed:
        score += 4
        lowered.append("profile support uncertain")
        return score
    if not profile and codec_name == "hevc" and (stream.height or 0) >= 2160 and probed and support:
        if "Main10" not in support.profiles and "Main" in support.profiles:
            score += 1
            lowered.append("device has HEVC Main but no Main10")
            return score
        if "Main10" in support.profiles:
            score += 10
            lowered.append("profile unknown")
            return score
    if not profile:
        score += 8
        lowered.append("profile unknown")
        return score
    score += 6
    lowered.append("profile not confirmed by device")
    return score


def _score_bit_depth(
    score: int,
    stream: StreamCharacteristics,
    codec_name: str | None,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    if not stream.bit_depth.known:
        risky = (
            codec_name == "hevc"
            and (stream.height or 0) >= 2160
            and support is not None
            and support.profiles_probed
            and 10 not in support.bit_depths
        )
        score += 1 if risky else 6
        lowered.append("bit depth unknown")
        return score
    depth = stream.bit_depth.value
    if support is not None and support.profiles_probed and isinstance(depth, int) and depth in support.bit_depths:
        score += 12 if stream.bit_depth.source == "explicit" else 10
        raised.append("bit depth supported" if stream.bit_depth.source == "explicit" else "bit depth likely supported")
        return score
    if stream.bit_depth.is_source("inferred_high") and _strong_main10(stream):
        lowered.append("Main10 probable from DV/HDR")
        score += 3
        return score
    score += 4
    lowered.append("bit depth not confirmed")
    return score


def _score_resolution(
    score: int,
    stream: StreamCharacteristics,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    if not stream.height:
        score += 3
        lowered.append("resolution unknown")
        return score
    if support is None or _size_supported(stream, support):
        score += 14
        raised.append("resolution supported")
        return score
    score += 4
    lowered.append("resolution uncertain")
    return score


def _score_fps(
    score: int,
    stream: StreamCharacteristics,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    fps = _stream_fps(stream)
    if fps is None:
        score += 2
        return score
    if support is None or not support.rates or _rate_covers(stream, support, fps):
        score += 6
        raised.append("fps supported")
        return score
    score -= 8
    lowered.append("fps uncertain")
    return score


def _score_hdr(
    score: int,
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
    support: CodecSupport | None,
    raised: list[str],
    lowered: list[str],
) -> int:
    hdr = stream.hdr.value if stream.hdr.known else None
    if hdr in (None, "sdr"):
        score += 4
        if hdr == "sdr":
            raised.append("sdr")
        return score
    decoder_hdr = support.hdr if support is not None else set()
    if hdr in device.display_hdr or hdr in decoder_hdr or (hdr == "hdr" and ("hdr10" in device.display_hdr or "hdr10" in decoder_hdr)):
        score += 5
        raised.append("hdr supported")
        return score
    if device.hdr_probed:
        score += 1
        lowered.append("hdr not declared by device")
        return score
    score += 3
    return score


def _score_dolby_vision(
    score: int,
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
    raised: list[str],
    lowered: list[str],
) -> int:
    if stream.dolby_vision.value is not True:
        return score
    if device.dolby_vision is True:
        score += 4
        raised.append("dolby vision supported")
        return score
    if device.dolby_vision is False:
        score -= 28
        lowered.append("dolby vision not supported")
        return score
    score -= 8
    lowered.append("dolby vision unknown on device")
    return score


def _score_audio(
    score: int,
    stream: StreamCharacteristics,
    device: DevicePlaybackCapabilities,
    raised: list[str],
    lowered: list[str],
) -> int:
    codec = stream.audio_codec.value if stream.audio_codec.known else None
    if not isinstance(codec, str):
        return score + 1
    if not device.audio_probed:
        return score + 1
    supported = device.audio.get(codec)
    if codec == "dtshd":
        supported = device.audio.get("dtshd", device.audio.get("dts"))
    if codec == "dtsx":
        supported = device.audio.get("dtsx", device.audio.get("dts"))
    if codec == "eac3" and stream.atmos.value is True:
        if device.audio.get("atmos") is False and supported is not False:
            score -= 2
            lowered.append("atmos not declared")
    if supported is True:
        score += 4
        raised.append("audio supported")
        return score
    if supported is False:
        score -= 6
        lowered.append("audio may not be supported")
        return score
    return score + 1


def _score_evidence(
    score: int,
    stream: StreamCharacteristics,
    raised: list[str],
    lowered: list[str],
) -> int:
    fields = (stream.codec, stream.resolution, stream.bit_depth, stream.profile)
    explicit_count = sum(1 for item in fields if item.source == "explicit")
    unknown_count = sum(1 for item in fields if item.source == "unknown")
    score += min(6, explicit_count * 2)
    if explicit_count >= 3:
        raised.append("filename is explicit")
    penalty = min(8, unknown_count * 2)
    score -= penalty
    if unknown_count >= 2:
        lowered.append("important fields unknown")
    return score


def _strong_ten_bit(stream: StreamCharacteristics) -> bool:
    if stream.bit_depth.known and stream.bit_depth.value == 10 and stream.bit_depth.is_source("explicit", "inferred_high"):
        return True
    if stream.dolby_vision.source == "explicit" and stream.dolby_vision.value is True:
        return True
    if stream.hdr.source == "explicit" and stream.hdr.value in ("hdr10", "hdr10+", "hlg"):
        return True
    return False


def _strong_main10(stream: StreamCharacteristics) -> bool:
    if stream.profile.known and stream.profile.value == "Main10" and stream.profile.is_source("explicit", "inferred_high"):
        return True
    codec = stream.codec.value if stream.codec.known else None
    return codec == "hevc" and _strong_ten_bit(stream)


def _strong_high10(stream: StreamCharacteristics) -> bool:
    return bool(
        stream.profile.known
        and stream.profile.value == "High10"
        and stream.profile.source == "explicit"
    )


def _profiles_were_probed(device: DevicePlaybackCapabilities) -> bool:
    return any(item.profiles_probed for item in device.codecs.values())


def _any_codec_supports_ten_bit(device: DevicePlaybackCapabilities) -> bool:
    for support in device.codecs.values():
        if not support.present or not support.profiles_probed:
            continue
        if 10 in support.bit_depths or "Main10" in support.profiles or "High10" in support.profiles or "Profile2" in support.profiles:
            return True
    return False


def _size_supported(stream: StreamCharacteristics, support: CodecSupport) -> bool:
    if not stream.width or not stream.height:
        return True
    if support.max_width and support.max_height:
        if not _fits(stream.width, stream.height, support.max_width, support.max_height):
            return False
    if support.rates:
        return any(
            _fits(stream.width, stream.height, rate[0], rate[1]) for rate in support.rates
        )
    return True


def _any_codec_supports_size(stream: StreamCharacteristics, device: DevicePlaybackCapabilities) -> bool:
    present = [item for item in device.codecs.values() if item.present]
    if not present:
        return True
    limited = [item for item in present if item.max_height or item.rates]
    if not limited:
        return True
    return any(_size_supported(stream, item) for item in limited)


def _any_rates(device: DevicePlaybackCapabilities) -> bool:
    return any(item.rates for item in device.codecs.values())


def _any_rate_covers(stream: StreamCharacteristics, device: DevicePlaybackCapabilities, fps: float) -> bool:
    present = [item for item in device.codecs.values() if item.present and item.rates]
    if not present:
        return True
    return any(_rate_covers(stream, item, fps) for item in present)


def _rate_covers(stream: StreamCharacteristics, support: CodecSupport, fps: float) -> bool:
    if not stream.width or not stream.height or not support.rates:
        return True
    needed = _fps_bucket(fps)
    return any(
        _fits(stream.width, stream.height, rate[0], rate[1]) and rate[2] + 0.1 >= needed
        for rate in support.rates
    )


def _fits(video_w: int, video_h: int, limit_w: int, limit_h: int) -> bool:
    return max(video_w, video_h) <= max(limit_w, limit_h) and min(video_w, video_h) <= min(limit_w, limit_h)


def _stream_fps(stream: StreamCharacteristics) -> float | None:
    if not stream.fps.known:
        return None
    try:
        return float(stream.fps.value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _fps_bucket(fps: float) -> float:
    if abs(fps - 23.976) < 0.02:
        return 24
    if abs(fps - 29.97) < 0.05:
        return 30
    if abs(fps - 59.94) < 0.05:
        return 60
    return fps


def _failure_matches(stream: StreamCharacteristics, failure) -> bool:
    if failure.count < 1:
        return False
    codec = stream.codec.value if stream.codec.known else None
    if failure.codec and codec and failure.codec != codec:
        return False
    if failure.min_height and stream.height and stream.height < failure.min_height:
        return False
    eight_bit_main = (
        stream.bit_depth.source == "explicit"
        and stream.bit_depth.value == 8
        and stream.profile.value == "Main"
        and stream.dolby_vision.value is not True
        and stream.hdr.value not in ("hdr", "hdr10", "hdr10+", "hlg")
    )
    if failure.profile == "Main10":
        if eight_bit_main:
            return False
        if not _strong_main10(stream) and not _strong_ten_bit(stream):
            return False
    if failure.dolby_vision and stream.dolby_vision.value is not True:
        return False
    if failure.profile is None and not failure.dolby_vision and failure.codec:
        return codec == failure.codec
    return True


def _summary(
    stream: StreamCharacteristics,
    score: int,
    incompatible: bool,
    raised: list[str],
    lowered: list[str],
) -> str:
    resolution = stream.resolution.value or "?"
    codec = stream.codec.value or "codec?"
    if isinstance(codec, str):
        codec = {"hevc": "HEVC", "avc": "AVC", "av1": "AV1", "vp9": "VP9", "vp8": "VP8", "mpeg2": "MPEG2", "xvid": "XVID"}.get(codec, codec.upper())
    parts = [f"score={score}", f"{resolution} {codec}"]
    if incompatible:
        parts.append("incompatible")
    parts.extend(raised[:3])
    parts.extend(lowered[:3])
    return " | ".join(str(part) for part in parts)
