"""Shared evidence model for a stream and for what a device actually reported."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    """A technical fact plus where it came from.

    `unknown` is a real state. It must not be treated as supported.
    `explicit` beats `inferred_high`, which beats `inferred`.
    """

    value: object = None
    source: str = "unknown"

    @property
    def known(self) -> bool:
        return self.source != "unknown" and self.value is not None

    def is_source(self, *sources: str) -> bool:
        return self.source in sources


def unknown() -> Evidence:
    return Evidence()


def explicit(value: object) -> Evidence:
    return Evidence(value, "explicit")


def inferred(value: object) -> Evidence:
    return Evidence(value, "inferred")


def inferred_high(value: object) -> Evidence:
    return Evidence(value, "inferred_high")


@dataclass
class StreamCharacteristics:
    resolution: Evidence = field(default_factory=unknown)
    width: int | None = None
    height: int | None = None
    interlaced: bool = False
    fps: Evidence = field(default_factory=unknown)
    codec: Evidence = field(default_factory=unknown)
    profile: Evidence = field(default_factory=unknown)
    level: Evidence = field(default_factory=unknown)
    bit_depth: Evidence = field(default_factory=unknown)
    hdr: Evidence = field(default_factory=unknown)
    dolby_vision: Evidence = field(default_factory=unknown)
    audio_codec: Evidence = field(default_factory=unknown)
    audio_channels: Evidence = field(default_factory=unknown)
    atmos: Evidence = field(default_factory=unknown)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class CodecSupport:
    profiles: set[str] = field(default_factory=set)
    profiles_probed: bool = False
    bit_depths: set[int] = field(default_factory=set)
    max_level: float | None = None
    max_width: int = 0
    max_height: int = 0
    rates: list[tuple[int, int, int]] = field(default_factory=list)
    hdr: set[str] = field(default_factory=set)
    present: bool = False


@dataclass
class ObservedFailure:
    codec: str | None = None
    profile: str | None = None
    min_height: int | None = None
    dolby_vision: bool = False
    count: int = 1


@dataclass
class DevicePlaybackCapabilities:
    platform: str | None = None
    player_backend: str | None = None
    screen_width: int = 0
    screen_height: int = 0
    codecs: dict[str, CodecSupport] = field(default_factory=dict)
    codec_probe: bool = False
    hdr_probed: bool = False
    display_hdr: set[str] = field(default_factory=set)
    dolby_vision: bool | None = None
    audio: dict[str, bool] = field(default_factory=dict)
    audio_probed: bool = False
    observed_failures: list[ObservedFailure] = field(default_factory=list)

    def codec(self, name: str | None) -> CodecSupport | None:
        if not name:
            return None
        support = self.codecs.get(name)
        if support is None or not support.present:
            return None
        return support
