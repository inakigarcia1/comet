"""Yes/no playback gate used by the per-request user filters.

The decision itself lives in the compatibility scorer. A stream is removed
only when that score marks it incompatible. Cache writes never call this.
"""

from __future__ import annotations

from typing import Any, Mapping

from comet.services.compatibility.evaluator import evaluate_title
from comet.services.compatibility.playback_active import capabilities_active


def playback_capabilities_active(capabilities: Mapping[str, Any] | None) -> bool:
    return capabilities_active(capabilities)


def torrent_title_allowed(torrent_title: str, capabilities: Mapping[str, Any] | None) -> bool:
    if not playback_capabilities_active(capabilities):
        return True
    if not isinstance(torrent_title, str) or not torrent_title:
        return True
    result = evaluate_title(torrent_title, capabilities)
    if result is None:
        return True
    return not result.incompatible
