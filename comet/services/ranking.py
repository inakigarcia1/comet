from RTN import Torrent, check_fetch_and_rank_many, sort_torrents
from RTN.exceptions import GarbageTorrent


def release_is_pack(parsed) -> bool:
    """A multi-episode release. Its torrent size is the whole pack, not one file."""
    episodes = getattr(parsed, "episodes", None) or ()
    return len(episodes) >= 2


def exceeds_file_size_cap(torrent: dict, max_size: int) -> bool:
    """True when this one file is over the plan cap.

    Pack size is not the file size. A 252 GB season stays eligible; the
    matched episode is checked once debrid replaces ``size`` with that file.
    """
    if not max_size:
        return False
    size = torrent.get("size")
    if size is None or size <= max_size:
        return False
    if release_is_pack(torrent.get("parsed")):
        return False
    return True


def allow_unknown_resolution(rtn_settings):
    """Anime releases often omit 720p/1080p from the filename."""
    resolutions = rtn_settings.resolutions
    if getattr(resolutions, "unknown", True) is not False:
        return rtn_settings
    return rtn_settings.model_copy(
        update={"resolutions": resolutions.model_copy(update={"unknown": True})}
    )


def rank_worker(
    torrents,
    rtn_settings,
    rtn_ranking,
    max_results_per_resolution,
    max_size,
    remove_trash,
):
    ranked_torrents = set()
    eligible_torrents = []
    for info_hash, torrent in torrents.items():
        if exceeds_file_size_cap(torrent, max_size):
            continue

        eligible_torrents.append((info_hash, torrent))

    rank_results = check_fetch_and_rank_many(
        (torrent["parsed"] for _, torrent in eligible_torrents),
        rtn_settings,
        rtn_ranking,
    )

    for (info_hash, torrent), (is_fetchable, _, rank) in zip(
        eligible_torrents, rank_results, strict=True
    ):
        parsed = torrent["parsed"]
        raw_title = torrent["title"]

        if remove_trash and (
            not is_fetchable or rank < rtn_settings.options["remove_ranks_under"]
        ):
            continue

        try:
            ranked_torrents.add(
                Torrent(
                    infohash=info_hash,
                    raw_title=raw_title,
                    data=parsed,
                    fetch=is_fetchable,
                    rank=rank,
                    lev_ratio=0.0,
                )
            )
        except GarbageTorrent:
            pass

    return sort_torrents(ranked_torrents, max_results_per_resolution)
