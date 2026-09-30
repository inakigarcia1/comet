"""How many torrents the shared cache keeps for one title.

The number in the client b64 config (`maxResultsPerResolution`) trims the
response for that client. It does not decide what gets stored. Storage uses
the fixed cap below, after a search that did not apply client filters.
"""

from collections import defaultdict

# ponytail: top seeders per resolution. Switch to an unfiltered RTN rank if
# seeders stop being a decent stand-in for which releases are worth keeping.
CACHE_RESULTS_PER_RESOLUTION = 8


def resolution_of(parsed) -> str:
    value = getattr(parsed, "resolution", None)
    text = str(value or "unknown").strip()
    return text or "unknown"


def cap_per_resolution(
    torrents: list[dict],
    limit: int = CACHE_RESULTS_PER_RESOLUTION,
) -> list[dict]:
    """Keep at most `limit` torrents for each resolution. Fewer if that's all there is."""
    if limit <= 0:
        return list(torrents)

    grouped: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for index, torrent in enumerate(torrents):
        grouped[resolution_of(torrent.get("parsed"))].append((index, torrent))

    kept: list[dict] = []
    for bucket in grouped.values():
        bucket.sort(
            key=lambda item: (
                -(item[1].get("seeders") or 0),
                -(item[1].get("size") or 0),
                item[0],
            )
        )
        kept.extend(torrent for _, torrent in bucket[:limit])
    return kept


def count_resolutions(torrents) -> dict[str, int]:
    counts: dict[str, int] = {}
    for torrent in torrents:
        parsed = torrent.get("parsed") if isinstance(torrent, dict) else None
        key = resolution_of(parsed)
        counts[key] = counts.get(key, 0) + 1
    return counts


def format_counts(counts: dict | None) -> str:
    if not counts:
        return "-"
    return ",".join(f"{key}:{counts[key]}" for key in sorted(counts))
