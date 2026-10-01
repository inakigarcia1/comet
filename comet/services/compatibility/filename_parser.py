"""Release-name parser.

Explicit tokens win. Inferences are labeled and never overwrite an explicit
value. A missing token stays unknown; it is not filled in from the resolution
or from the codec family alone.
"""

from __future__ import annotations

import re

from comet.services.compatibility.models import (
    Evidence,
    StreamCharacteristics,
    explicit,
    inferred,
    inferred_high,
)

_PIXEL_SIZE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(\d{3,5})\s*[xX×]\s*(\d{3,5})(?![A-Za-z0-9])"
)
_RES_FPS = re.compile(
    r"(?i)(?<![A-Za-z0-9])(4320|2160|1440|1080|720|576|480|360)"
    r"p(23\.976|29\.97|59\.94|24|25|30|48|50|60)(?![A-Za-z0-9])"
)
_RES = re.compile(
    r"(?i)(?<![A-Za-z0-9])(4320|2160|1440|1080|720|576|480|360)(p|i)(?![A-Za-z0-9])"
)
_FOUR_K = re.compile(r"(?i)(?<![A-Za-z0-9])4k(?![A-Za-z0-9])")
_UHD = re.compile(r"(?i)(?<![A-Za-z0-9])uhd(?![A-Za-z0-9])")
_FPS = re.compile(
    r"(?i)(?<![A-Za-z0-9])(23\.976|29\.97|59\.94|24|25|30|48|50|60)\s*fps(?![A-Za-z0-9])"
)

_CODECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("av1", re.compile(r"(?i)(?<![A-Za-z0-9])av0?1(?![A-Za-z0-9])")),
    ("vp9", re.compile(r"(?i)(?<![A-Za-z0-9])vp9(?![A-Za-z0-9])")),
    ("vp8", re.compile(r"(?i)(?<![A-Za-z0-9])vp8(?![A-Za-z0-9])")),
    ("hevc", re.compile(r"(?i)(?<![A-Za-z0-9])(?:h[\.\s]?265|hevc|x265)(?![A-Za-z0-9])")),
    ("avc", re.compile(r"(?i)(?<![A-Za-z0-9])(?:h[\.\s]?264|x264|avc)(?![A-Za-z0-9])")),
    ("mpeg2", re.compile(r"(?i)(?<![A-Za-z0-9])mpeg-?2(?![A-Za-z0-9])")),
    ("xvid", re.compile(r"(?i)(?<![A-Za-z0-9])xvid(?![A-Za-z0-9])")),
)

# Glued or hyphenated only. "8.Bit.Christmas" and "10.Things" stay titles.
_BIT_DEPTH = re.compile(r"(?i)(?<![A-Za-z0-9])(8|10)-?bit(?![A-Za-z0-9])")
_HI10 = re.compile(r"(?i)(?<![A-Za-z0-9])hi10p?(?![A-Za-z0-9])")
# "Main.10bit" is Main plus a 10-bit token, not the Main10 profile.
_MAIN10 = re.compile(r"(?i)(?<![A-Za-z0-9])main(?:10|[\s_-]+10)(?![A-Za-z0-9])")
_MAIN = re.compile(r"(?i)(?<![A-Za-z0-9])main(?![A-Za-z0-9])")
_HIGH10 = re.compile(r"(?i)(?<![A-Za-z0-9])high(?:10|[\s_-]+10)(?![A-Za-z0-9])")
_PROFILE = re.compile(r"(?i)(?<![A-Za-z0-9])profile[\.\s_-]*([0-3])(?![A-Za-z0-9])")
_LEVEL = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:level[\.\s_-]*|l)"
    r"(6\.2|6\.1|6\.0|5\.2|5\.1|5\.0|4\.1|4\.0|3\.1)(?![A-Za-z0-9])"
)

_HDR10_PLUS = re.compile(r"(?i)(?<![A-Za-z0-9])hdr10\+")
_HDR10 = re.compile(r"(?i)(?<![A-Za-z0-9])hdr10(?!\+)(?![A-Za-z0-9])")
_HLG = re.compile(r"(?i)(?<![A-Za-z0-9])hlg(?![A-Za-z0-9])")
_SDR = re.compile(r"(?i)(?<![A-Za-z0-9])sdr(?![A-Za-z0-9])")
_DV = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:dolby[\.\s_-]*vision|dovi|do[\.\s_-]*vi|dv)(?![A-Za-z0-9])"
)
_HDR = re.compile(r"(?i)(?<![A-Za-z0-9])hdr(?!10)(?![A-Za-z0-9])")
_ATMOS = re.compile(r"(?i)(?<![A-Za-z0-9])atmos(?![A-Za-z0-9])")

# The closing lookahead allows a channel count (DDP5.1, AAC2.0, TrueHD7.1).
_AUDIO = re.compile(
    r"(?i)(?<![A-Za-z0-9])("
    r"dts[\.\s_-]*hd[\.\s_-]*ma"
    r"|dts[\.\s:_-]*x"
    r"|dts[\.\s_-]*hd"
    r"|dts"
    r"|true[\.\s_-]*hd"
    r"|ddp|eac-?3|dd\+"
    r"|ac-?3"
    r"|aac|flac|opus|vorbis|mp3"
    r")(?![A-Za-z])"
)
_CHANNELS = re.compile(r"(?i)^[\.\s_-]*(7\.1|5\.1|2\.0|1\.0|7\.0)")

_LABEL_SIZE: dict[str, tuple[int, int]] = {
    "4320p": (7680, 4320),
    "2160p": (3840, 2160),
    "1440p": (2560, 1440),
    "1080p": (1920, 1080),
    "1080i": (1920, 1080),
    "720p": (1280, 720),
    "576p": (1024, 576),
    "480p": (854, 480),
    "360p": (640, 360),
}

_HEIGHT_LABEL: dict[int, str] = {
    4320: "4320p",
    2160: "2160p",
    1440: "1440p",
    1080: "1080p",
    720: "720p",
    576: "576p",
    480: "480p",
    360: "360p",
}

_AUDIO_KIND = (
    ("dtshd", re.compile(r"(?i)^dts[\.\s_-]*hd[\.\s_-]*ma$|^dts[\.\s_-]*hd$")),
    ("dtsx", re.compile(r"(?i)^dts[\.\s:_-]*x$")),
    ("dts", re.compile(r"(?i)^dts$")),
    ("truehd", re.compile(r"(?i)^true[\.\s_-]*hd$")),
    ("eac3", re.compile(r"(?i)^(?:ddp|eac-?3|dd\+)$")),
    ("ac3", re.compile(r"(?i)^ac-?3$")),
    ("aac", re.compile(r"(?i)^aac$")),
    ("flac", re.compile(r"(?i)^flac$")),
    ("opus", re.compile(r"(?i)^opus$")),
    ("vorbis", re.compile(r"(?i)^vorbis$")),
    ("mp3", re.compile(r"(?i)^mp3$")),
)
_AUDIO_RANK = {
    "truehd": 0,
    "dtshd": 1,
    "dtsx": 2,
    "dts": 3,
    "eac3": 4,
    "ac3": 5,
    "flac": 6,
    "aac": 7,
    "opus": 8,
    "vorbis": 9,
    "mp3": 10,
}


def parse_filename(filename: str) -> StreamCharacteristics:
    stream = StreamCharacteristics()
    if not isinstance(filename, str) or not filename.strip():
        return stream

    text = filename.replace("\\", "/").rsplit("/", 1)[-1]
    _read_resolution(text, stream)
    _read_codec(text, stream)
    _read_bit_depth_and_profile(text, stream)
    _read_level(text, stream)
    _read_hdr(text, stream)
    _read_audio(text, stream)
    _apply_implications(stream)
    return stream


def _read_resolution(text: str, stream: StreamCharacteristics) -> None:
    pixel = _PIXEL_SIZE.search(text)
    if pixel:
        width, height = int(pixel.group(1)), int(pixel.group(2))
        if width >= height:
            stream.width, stream.height = width, height
        else:
            stream.width, stream.height = height, width
        label = _HEIGHT_LABEL.get(stream.height or 0)
        if label:
            stream.resolution = explicit(label)

    fps_match = _RES_FPS.search(text)
    if fps_match:
        label = f"{fps_match.group(1)}p"
        stream.resolution = explicit(label)
        stream.fps = explicit(_fps_number(fps_match.group(2)))
        _apply_label_size(stream, label)
    elif stream.resolution.source == "unknown":
        res_match = _RES.search(text)
        if res_match:
            label = f"{res_match.group(1)}{res_match.group(2).lower()}"
            stream.resolution = explicit(label)
            if label.endswith("i"):
                stream.interlaced = True
            _apply_label_size(stream, label)
        elif _FOUR_K.search(text) or _UHD.search(text):
            stream.resolution = explicit("2160p")
            _apply_label_size(stream, "2160p")

    if stream.fps.source == "unknown":
        fps = _FPS.search(text)
        if fps:
            stream.fps = explicit(_fps_number(fps.group(1)))


def _apply_label_size(stream: StreamCharacteristics, label: str) -> None:
    size = _LABEL_SIZE.get(label)
    if size and stream.width is None:
        stream.width, stream.height = size


def _fps_number(raw: str) -> float:
    if raw.startswith("23.976"):
        return 23.976
    if raw.startswith("59.94"):
        return 59.94
    if raw.startswith("29.97"):
        return 29.97
    return float(int(raw))


def _read_codec(text: str, stream: StreamCharacteristics) -> None:
    found: list[tuple[int, str]] = []
    for codec, pattern in _CODECS:
        match = pattern.search(text)
        if match:
            found.append((match.start(), codec))
    if not found:
        return
    found.sort()
    codecs = []
    for _, codec in found:
        if codec not in codecs:
            codecs.append(codec)
    stream.codec = explicit(codecs[0])
    if len(codecs) > 1:
        stream.conflicts.append("multiple-codecs")


def _read_bit_depth_and_profile(text: str, stream: StreamCharacteristics) -> None:
    bit = _BIT_DEPTH.search(text)
    if bit:
        stream.bit_depth = explicit(int(bit.group(1)))

    if _HI10.search(text) or _HIGH10.search(text):
        stream.profile = explicit("High10")
    elif _MAIN10.search(text):
        stream.profile = explicit("Main10")
    else:
        profile = _PROFILE.search(text)
        if profile:
            stream.profile = explicit(f"Profile{profile.group(1)}")
        elif _MAIN.search(text):
            stream.profile = explicit("Main")


def _read_level(text: str, stream: StreamCharacteristics) -> None:
    match = _LEVEL.search(text)
    if match:
        stream.level = explicit(match.group(1))


def _read_hdr(text: str, stream: StreamCharacteristics) -> None:
    if _DV.search(text):
        stream.dolby_vision = explicit(True)
    if _HDR10_PLUS.search(text):
        stream.hdr = explicit("hdr10+")
    elif _HDR10.search(text):
        stream.hdr = explicit("hdr10")
    elif _HLG.search(text):
        stream.hdr = explicit("hlg")
    elif _SDR.search(text):
        stream.hdr = explicit("sdr")
    elif _HDR.search(text):
        stream.hdr = explicit("hdr")

    if (
        stream.hdr.source == "explicit"
        and stream.hdr.value == "sdr"
        and (_HDR10_PLUS.search(text) or _HDR10.search(text) or _HDR.search(text) or _HLG.search(text))
    ):
        stream.conflicts.append("sdr-vs-hdr")


def _audio_kind(token: str) -> str | None:
    for kind, pattern in _AUDIO_KIND:
        if pattern.match(token):
            return kind
    return None


def _read_audio(text: str, stream: StreamCharacteristics) -> None:
    matches = list(_AUDIO.finditer(text))
    ranked: list[tuple[int, str, re.Match[str]]] = []
    for match in matches:
        kind = _audio_kind(match.group(1))
        if kind:
            ranked.append((_AUDIO_RANK[kind], kind, match))
    if ranked:
        ranked.sort(key=lambda item: item[0])
        _, kind, match = ranked[0]
        stream.audio_codec = explicit(kind)
        channels = _channels_after(text, match.end())
        if channels is None:
            for _, _, other in ranked:
                channels = _channels_after(text, other.end())
                if channels:
                    break
        if channels:
            stream.audio_channels = explicit(channels)

    if _ATMOS.search(text):
        stream.atmos = explicit(True)


def _channels_after(text: str, index: int) -> str | None:
    match = _CHANNELS.match(text[index : index + 8])
    if not match:
        return None
    return match.group(1)


def _codec(stream: StreamCharacteristics) -> str | None:
    if stream.codec.source == "unknown":
        return None
    value = stream.codec.value
    return value if isinstance(value, str) else None


def _imply_bits(stream: StreamCharacteristics, value: int, source: str, code: str) -> None:
    if stream.bit_depth.source == "explicit":
        if stream.bit_depth.value != value:
            _add_conflict(stream, code)
        return
    if stream.bit_depth.source == "unknown":
        stream.bit_depth = Evidence(value, source)


def _imply_profile(stream: StreamCharacteristics, value: str, source: str, code: str) -> None:
    codec = _codec(stream)
    if value == "Main10" and codec not in (None, "hevc"):
        _add_conflict(stream, "profile-codec-mismatch")
        return
    if (
        value == "Main10"
        and stream.bit_depth.source == "explicit"
        and stream.bit_depth.value == 8
    ):
        _add_conflict(stream, code)
        return
    if stream.profile.source == "explicit":
        if stream.profile.value != value:
            _add_conflict(stream, code)
        return
    if stream.profile.source == "unknown":
        stream.profile = Evidence(value, source)


def _add_conflict(stream: StreamCharacteristics, code: str) -> None:
    if code not in stream.conflicts:
        stream.conflicts.append(code)


def _apply_implications(stream: StreamCharacteristics) -> None:
    codec = _codec(stream)
    dv = stream.dolby_vision.source == "explicit" and stream.dolby_vision.value is True
    hdr = stream.hdr.value if stream.hdr.source == "explicit" else None

    if dv:
        _imply_bits(stream, 10, "inferred_high", "dv-vs-bit")
        if codec == "hevc":
            _imply_profile(stream, "Main10", "inferred_high", "dv-vs-profile")
        elif codec is not None:
            _add_conflict(stream, "dv-with-non-hevc")

    if hdr in ("hdr10", "hdr10+"):
        _imply_bits(stream, 10, "inferred_high", "hdr10-vs-bit")
        if codec == "hevc":
            _imply_profile(stream, "Main10", "inferred_high", "hdr10-vs-profile")

    if hdr == "hlg" and codec == "hevc":
        _imply_bits(stream, 10, "inferred_high", "hlg-vs-bit")
        _imply_profile(stream, "Main10", "inferred_high", "hlg-vs-profile")

    if hdr == "hdr":
        if codec == "hevc":
            _imply_bits(stream, 10, "inferred_high", "hdr-vs-bit")
            _imply_profile(stream, "Main10", "inferred_high", "hdr-vs-profile")
        elif codec == "vp9":
            _imply_bits(stream, 10, "inferred", "hdr-vp9-bit")

    if (
        stream.bit_depth.source == "explicit"
        and stream.bit_depth.value == 10
        and codec == "hevc"
    ):
        _imply_profile(stream, "Main10", "inferred_high", "10bit-vs-profile")

    hdr_demands_ten = dv or hdr in ("hdr", "hdr10", "hdr10+", "hlg")
    if (
        stream.bit_depth.source == "explicit"
        and stream.bit_depth.value == 8
        and codec == "hevc"
        and not hdr_demands_ten
        and stream.profile.source == "unknown"
    ):
        stream.profile = inferred_high("Main")

    if stream.profile.source == "explicit" and stream.profile.value == "High10":
        _imply_bits(stream, 10, "inferred", "hi10-bit")

    if (
        codec == "vp9"
        and stream.profile.source == "explicit"
        and stream.profile.value == "Profile2"
    ):
        _imply_bits(stream, 10, "inferred_high", "vp9-profile2-bit")

    if stream.profile.source == "explicit" and stream.profile.value == "Main10":
        if stream.bit_depth.source == "explicit" and stream.bit_depth.value != 10:
            _add_conflict(stream, "main10-vs-bit")
        elif stream.bit_depth.source != "explicit":
            stream.bit_depth = inferred(10)

    if (
        stream.profile.source == "explicit"
        and stream.profile.value == "Main"
        and stream.bit_depth.source == "explicit"
        and stream.bit_depth.value == 10
    ):
        _add_conflict(stream, "main-vs-10bit")


__all__ = ["parse_filename", "explicit", "inferred", "inferred_high"]
