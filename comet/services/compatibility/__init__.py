"""Playback compatibility: filename parsing, device matrix, and score."""

from comet.services.compatibility.device_capabilities import (
    describe_device,
    parse_device,
)
from comet.services.compatibility.evaluator import (
    SIMILAR_SCORE_BAND,
    CompatibilityResult,
    evaluate,
    evaluate_title,
    playback_sort_key,
    score_band,
)
from comet.services.compatibility.filename_parser import parse_filename

__all__ = [
    "SIMILAR_SCORE_BAND",
    "CompatibilityResult",
    "describe_device",
    "evaluate",
    "evaluate_title",
    "parse_device",
    "parse_filename",
    "playback_sort_key",
    "score_band",
]
