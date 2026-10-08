from collections import defaultdict
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Query, Request

from comet.core.config_validation import config_check
from comet.core.logger import logger
from comet.core.models import settings
from comet.debrid.manager import get_debrid_extension
from comet.observability import metrics
from comet.services.cache_admission import CACHE_RESULTS_PER_RESOLUTION, format_counts
from comet.services.media_search import MediaSearchStatus, search_media
from comet.services.compatibility import describe_device, evaluate_title
from comet.services.trace import current_trace, set_trace
from comet.services.trackers import trackers
from comet.utils.cache import CachePolicies, cached_json_response
from comet.utils.formatting import (
    format_chilllink,
    format_title,
    get_formatted_components,
    get_formatted_components_plain,
)
from comet.utils.network import get_client_ip
from comet.utils.parsing import is_non_video_file

streams = APIRouter()
STREMIO_API_PREFIX = settings.STREMIO_API_PREFIX

RESOLUTION_TO_DIMENSIONS = {
    "4K": (2160, 3840),
    "2160P": (2160, 3840),
    "1440P": (1440, 2560),
    "1080P": (1080, 1920),
    "720P": (720, 1280),
    "576P": (576, 720),
    "480P": (480, 640),
    "360P": (360, 480),
    "240P": (240, 320),
}


def _is_480p(parsed) -> bool:
    return str(getattr(parsed, "resolution", "") or "").strip().lower() in {
        "480p",
        "r480p",
    }


def _client_disabled_480p(config) -> bool:
    resolutions = config.get("resolutions") if isinstance(config, dict) else None
    return isinstance(resolutions, dict) and resolutions.get("r480p") is False


def _has_playable_stream(streams) -> bool:
    for stream in streams:
        hints = stream.get("behaviorHints") or {}
        if hints.get("bingeGroup") or stream.get("infoHash"):
            return True
    return False


def _sd480_fallback_hashes(torrents: dict, already, limit: int) -> list[str]:
    skipped = set(already)
    candidates = []
    for info_hash, torrent in torrents.items():
        if info_hash in skipped or not isinstance(torrent, dict):
            continue
        parsed = torrent.get("parsed")
        if parsed is None or not _is_480p(parsed):
            continue
        candidates.append(info_hash)
    candidates.sort(
        key=lambda info_hash: (
            -(torrents[info_hash].get("seeders") or 0),
            -(torrents[info_hash].get("size") or 0),
            info_hash,
        )
    )
    if limit > 0:
        return candidates[:limit]
    return candidates


def _disabled_resolutions(config) -> str:
    resolutions = config.get("resolutions") or {}
    if not isinstance(resolutions, dict):
        return "-"
    disabled = [str(key) for key, enabled in resolutions.items() if enabled is False]
    return ",".join(disabled) or "-"


def _playback_summary(config) -> str:
    playback = config.get("playbackCapabilities") or {}
    if not isinstance(playback, dict) or not playback:
        return "-"
    return describe_device(playback)


def _attach_playback_score(behavior_hints: dict, torrent_title: str, config) -> None:
    result = evaluate_title(torrent_title, config.get("playbackCapabilities"))
    if result is None:
        return
    behavior_hints["playbackScore"] = result.score
    if result.height:
        behavior_hints["playbackHeight"] = result.height
    behavior_hints["playbackSummary"] = result.summary
    logged = int(config.get("_playbackRankLogs") or 0) if isinstance(config, dict) else 0
    if isinstance(config, dict) and logged < 40:
        config["_playbackRankLogs"] = logged + 1
        logger.log(
            "SCRAPER",
            f"TRACE {current_trace()} rank {result.summary} file={torrent_title[:180]}",
        )


def _log_search_trace(config, result, duration_minutes) -> None:
    title = (result.metadata or {}).get("title") or "-"
    logger.log(
        "SCRAPER",
        f"TRACE {current_trace()} media={result.media_only_id or '-'} title={title} "
        f"status={result.status.value} cache={result.cache_state} "
        f"decision={result.cache_decision or '-'} scraped={str(result.scraped).lower()} "
        f"filtersOnSearch=none filtersOnCacheWrite=none "
        f"cacheCap={CACHE_RESULTS_PER_RESOLUTION} "
        f"clientMax={config.get('maxResultsPerResolution')} "
        f"stored={format_counts(result.stored_resolutions)} "
        f"wrote={format_counts(result.wrote_resolutions)} "
        f"afterClientFilters={format_counts(result.visible_resolutions)} "
        f"excludedResolutions={_disabled_resolutions(config)} "
        f"bitrateMax={config.get('maxBitrateMbps') or 0} "
        f"durationMin={duration_minutes or 0} playback={_playback_summary(config)}",
    )


def _first_meta_value(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def _build_kodi_meta(parsed, formatted_components: dict):
    resolution_value = getattr(parsed, "resolution", "")
    resolution = str(resolution_value).upper() if resolution_value else ""
    height, width = RESOLUTION_TO_DIMENSIONS.get(resolution, (0, 0))
    languages = getattr(parsed, "languages", None) or []

    return {
        "width": width,
        "height": height,
        "resolution": resolution,
        "codec": _first_meta_value(getattr(parsed, "codec", "")),
        "hdr": _first_meta_value(getattr(parsed, "hdr", "")),
        "audio": _first_meta_value(getattr(parsed, "audio", "")),
        "channels": _first_meta_value(getattr(parsed, "channels", "")),
        "language": languages[0] if languages else "",
        "languages": languages,
        "title": formatted_components.get("title", ""),
        "videoInfo": formatted_components.get("video", ""),
        "audioInfo": formatted_components.get("audio", ""),
        "qualityInfo": formatted_components.get("quality", ""),
        "groupInfo": formatted_components.get("group", ""),
        "seedersInfo": formatted_components.get("seeders", ""),
        "sizeInfo": formatted_components.get("size", ""),
        "trackerInfo": formatted_components.get("tracker", ""),
        "languagesInfo": formatted_components.get("languages", ""),
    }


def _stream_notice_name(kodi: bool, emoji_name: str, plain_name: str):
    return plain_name if kodi else emoji_name


def _build_stream_name(
    kodi: bool,
    service: str,
    resolution,
    icon: str = "",
    formatted_components: dict | None = None,
    seeders: int | None = None,
    status: str = "",
):
    if not kodi:
        return f"[{service}{icon}] Comet {resolution}"

    prefix = f"[{f'{service} {status}'.strip()}] {resolution}"

    if formatted_components is None:
        return prefix

    details = [
        formatted_components.get("size", "").removeprefix("Size: "),
        f"S:{seeders}" if seeders is not None else "",
        formatted_components.get("video", ""),
        formatted_components.get("audio", ""),
        formatted_components.get("quality", ""),
        formatted_components.get("group", ""),
    ]
    details = [d for d in details if d]
    return f"{prefix} | {' | '.join(details)}" if details else prefix


def _build_stream_response(
    request: Request,
    content: dict,
    is_empty: bool = False,
    vary_headers: list | None = None,
    cache_policy=None,
):
    if cache_policy is None:
        cache_policy = (
            CachePolicies.empty_results() if is_empty else CachePolicies.streams()
        )

    return cached_json_response(
        request,
        content,
        cache_policy=cache_policy,
        vary=list(dict.fromkeys(["Accept", *(vary_headers or ())])),
    )


def _encode_playback_scope(value: int | None) -> str:
    return str(value) if value is not None else "n"


def _select_info_hashes_by_resolution(
    ranked_info_hashes,
    torrents: dict,
    service_cache_status: dict,
    max_results: int,
    cached_only: bool,
    prioritize_cached: bool,
):
    manual_hashes = [
        info_hash
        for info_hash in ranked_info_hashes
        if torrents.get(info_hash, {}).get("is_manual")
    ]
    if max_results <= 0:
        return None

    per_resolution_count = defaultdict(int)
    selected_info_hashes = []
    selected = set()

    def try_select(info_hash: str, *, force: bool = False):
        if info_hash in selected:
            return
        if not force:
            resolution = str(torrents[info_hash]["parsed"].resolution)
            if per_resolution_count[resolution] >= max_results:
                return
            selected_info_hashes.append(info_hash)
            selected.add(info_hash)
            per_resolution_count[resolution] += 1
            return
        selected_info_hashes.append(info_hash)
        selected.add(info_hash)

    for info_hash in manual_hashes:
        try_select(info_hash, force=True)

    is_cached_by_hash = {}
    if prioritize_cached or cached_only:
        is_cached_by_hash = {
            info_hash: any(service_cache_status.get(info_hash, {}).values())
            for info_hash in ranked_info_hashes
        }

    if prioritize_cached:
        for info_hash in ranked_info_hashes:
            if info_hash in selected:
                continue
            if not is_cached_by_hash[info_hash]:
                continue
            try_select(info_hash)

        if cached_only:
            return selected_info_hashes

        for info_hash in ranked_info_hashes:
            if info_hash in selected:
                continue
            if is_cached_by_hash[info_hash]:
                continue
            try_select(info_hash)

        return selected_info_hashes

    for info_hash in ranked_info_hashes:
        if info_hash in selected:
            continue
        if cached_only and not is_cached_by_hash[info_hash]:
            continue
        try_select(info_hash)

    return selected_info_hashes


@streams.get(
    "/stream/{media_type}/{media_id}.json",
    tags=["Stremio"],
    summary="Stream Provider",
    description="Returns a list of streams for the specified media.",
)
@streams.get(
    "/{b64config}/stream/{media_type}/{media_id}.json",
    tags=["Stremio"],
    summary="Stream Provider",
    description="Returns a list of streams for the specified media with existing configuration.",
)
async def stream(
    request: Request,
    media_type: str,
    media_id: str,
    background_tasks: BackgroundTasks,
    b64config: str | None = None,
    chilllink: bool = False,
    kodi: bool = False,
    duration_minutes: float | None = Query(
        default=None,
        ge=1,
        description=(
            "Optional runtime duration in minutes. When provided, the bitrate "
            "filter (min/max Mbps) is applied. 0 or negative disables the filter."
        ),
    ),
):
    set_trace(request.headers.get("x-trace-id"))
    if media_type not in ["movie", "series"]:
        logger.log("SCRAPER", f"TRACE {current_trace()} status=rejected media_type={media_type}")
        return _build_stream_response(request, {"streams": []}, is_empty=True)

    if "tmdb:" in media_id:
        return _build_stream_response(request, {"streams": []}, is_empty=True)

    config = config_check(b64config, strict_b64config=True)
    if not config:
        logger.log("SCRAPER", f"TRACE {current_trace()} status=invalid_config media={media_id}")
        error_response = {
            "streams": [
                {
                    "name": _stream_notice_name(kodi, "[❌] Comet", "[ERROR] Comet"),
                    "description": (
                        f"OBSOLETE CONFIGURATION, PLEASE RE-CONFIGURE ON {request.url.scheme}://{request.url.netloc}"
                        if kodi
                        else f"⚠️ OBSOLETE CONFIGURATION, PLEASE RE-CONFIGURE ON {request.url.scheme}://{request.url.netloc} ⚠️"
                    ),
                    "url": "https://comet.feels.legal",
                }
            ]
        }
        return _build_stream_response(request, error_response, is_empty=True)

    debrid_entries = config["_debridEntries"]
    enable_torrent = config["_enableTorrent"]
    deduplicate_streams = config["deduplicateStreams"]
    use_account_scrape = bool(debrid_entries and config["scrapeDebridAccountTorrents"])
    bitrate_filter_active = duration_minutes is not None and (
        config.get("minBitrateMbps") or config.get("maxBitrateMbps")
    )
    response_cache_policy = (
        CachePolicies.no_cache()
        if use_account_scrape or bitrate_filter_active
        else None
    )
    stream_cache_state = "unknown"
    stream_client = "kodi" if kodi else ("chilllink" if chilllink else "stremio")

    def _stream_response(content: dict, is_empty: bool = False):
        result_count = len(content.get("streams", ()))
        metrics.observe_stream(
            media_type,
            stream_client,
            stream_cache_state,
            "empty" if is_empty else "success",
            result_count,
        )
        return _build_stream_response(
            request,
            content,
            is_empty=is_empty,
            cache_policy=response_cache_policy,
        )

    search_result = await search_media(
        media_type,
        media_id,
        config,
        get_client_ip(request),
        background_tasks.add_task,
        duration_minutes=duration_minutes,
    )
    _log_search_trace(config, search_result, duration_minutes)
    stream_cache_state = search_result.cache_state

    if search_result.status is MediaSearchStatus.INVALID:
        return _stream_response({"streams": []}, is_empty=True)

    if search_result.status is MediaSearchStatus.DISABLED:
        placeholder_stream = {
            "name": settings.TORRENT_DISABLED_STREAM_NAME,
            "description": settings.TORRENT_DISABLED_STREAM_DESCRIPTION,
        }
        if settings.TORRENT_DISABLED_STREAM_URL:
            placeholder_stream["url"] = settings.TORRENT_DISABLED_STREAM_URL

        return _stream_response({"streams": [placeholder_stream]})

    if search_result.status is MediaSearchStatus.UNRELEASED:
        return _stream_response(
            {
                "streams": [
                    {
                        "name": _stream_notice_name(
                            kodi, "[🚫] Comet", "[BLOCKED] Comet"
                        ),
                        "description": "Content not digitally released yet.",
                        "url": "https://comet.feels.legal",
                    }
                ]
            },
            is_empty=True,
        )

    if search_result.status is MediaSearchStatus.METADATA_UNAVAILABLE:
        return _stream_response(
            {
                "streams": [
                    {
                        "name": _stream_notice_name(kodi, "[⚠️] Comet", "[WARN] Comet"),
                        "description": "Unable to get metadata.",
                        "url": "https://comet.feels.legal",
                    }
                ]
            },
            is_empty=True,
        )

    if search_result.status is MediaSearchStatus.BUSY:
        return _stream_response(
            {
                "streams": [
                    {
                        "name": _stream_notice_name(kodi, "[🔄] Comet", "[INFO] Comet"),
                        "description": (
                            "Scraping in progress, please try again in a few seconds..."
                        ),
                        "url": "https://comet.feels.legal",
                    }
                ]
            },
            is_empty=True,
        )

    metadata = search_result.metadata
    title = metadata["title"]
    media_only_id = search_result.media_only_id
    search_season = search_result.search_season
    search_episode = search_result.search_episode
    service_cache_status = search_result.service_cache_status
    debrid_errors = search_result.debrid_errors
    sort_mixed = search_result.sort_mixed
    torrents = search_result.torrents
    cached_results = [
        {
            "name": (f"[ERROR] {service}" if kodi else f"[❌] {service}"),
            "description": error.display_message,
            "url": "https://comet.feels.legal",
        }
        for service, error in search_result.debrid_errors.items()
    ]
    non_cached_results = []
    debrid_stream_specs = [
        (entry_index, entry["service"], get_debrid_extension(entry["service"]))
        for entry_index, entry in enumerate(debrid_entries)
    ]

    if (
        config["debridStreamProxyPassword"] != ""
        and settings.PROXY_DEBRID_STREAM
        and settings.PROXY_DEBRID_STREAM_PASSWORD != config["debridStreamProxyPassword"]
    ):
        cached_results.append(
            {
                "name": _stream_notice_name(kodi, "[⚠️] Comet", "[WARN] Comet"),
                "description": "Debrid Stream Proxy Password incorrect.\nStreams will not be proxied.",
                "url": "https://comet.feels.legal",
            }
        )

    result_season = _encode_playback_scope(search_season)
    result_episode = _encode_playback_scope(search_episode)
    quoted_media_only_id = quote(media_only_id, safe="")

    base_playback_host = (
        settings.PUBLIC_BASE_URL
        if settings.PUBLIC_BASE_URL
        else f"{request.url.scheme}://{request.url.netloc}"
    )
    api_prefix = STREMIO_API_PREFIX
    config_segment = f"/{b64config}" if b64config else ""
    playback_base_url = f"{base_playback_host}{api_prefix}{config_segment}"
    quoted_title = quote(title)
    format_components = (
        get_formatted_components_plain if kodi else get_formatted_components
    )
    format_title_fn = format_title
    torrent_extension = get_debrid_extension("torrent")
    torrent_service = "" if kodi else torrent_extension

    if search_result.show_account_sync_trigger:
        for entry_index, _, debrid_extension in debrid_stream_specs:
            cached_results.append(
                {
                    "name": (
                        f"[{debrid_extension}] Comet Sync"
                        if kodi
                        else f"[{debrid_extension}🔄] Comet Sync"
                    ),
                    "description": (
                        "Sync debrid account library now.\n"
                        "Select this stream, then retry this title in a few seconds."
                    ),
                    "url": f"{playback_base_url}/debrid-sync/{entry_index}",
                }
            )

    selected_info_hashes = _select_info_hashes_by_resolution(
        ranked_info_hashes=search_result.ranked_info_hashes,
        torrents=torrents,
        service_cache_status=service_cache_status,
        max_results=config["maxResultsPerResolution"],
        cached_only=bool(
            config["cachedOnly"] and debrid_entries and not enable_torrent
        ),
        prioritize_cached=bool(debrid_entries and not sort_mixed),
    )
    ranked_info_hashes = (
        selected_info_hashes
        if selected_info_hashes is not None
        else search_result.ranked_info_hashes
    )

    added_hashes = set()

    def _append_ranked_hash(info_hash):
        torrent = torrents[info_hash]
        if is_non_video_file(torrent.get("title") or ""):
            return
        rtn_data = torrent["parsed"]
        torrent_title = torrent["title"]
        torrent_size = torrent["size"]
        formatted_components = format_components(
            rtn_data,
            torrent_title,
            torrent["seeders"],
            torrent_size,
            torrent["tracker"],
            config["resultFormat"],
        )
        formatted_title = format_title_fn(formatted_components)
        kodi_meta = _build_kodi_meta(rtn_data, formatted_components) if kodi else None
        info_hash_cache_status = service_cache_status.get(info_hash)
        quoted_torrent_title = quote(torrent_title)

        for entry_index, service, debrid_extension in debrid_stream_specs:
            if service in debrid_errors:
                continue

            is_cached = (
                info_hash_cache_status.get(service, False)
                if info_hash_cache_status
                else False
            )
            is_manual = bool(torrent.get("is_manual"))

            if config["cachedOnly"] and not is_cached and not is_manual:
                continue

            if deduplicate_streams and info_hash in added_hashes and is_cached:
                continue

            behavior_hints = {
                "bingeGroup": f"comet|{service}|{info_hash}",
                "filename": rtn_data.raw_title,
            }
            _attach_playback_score(behavior_hints, torrent_title, config)
            if torrent_size is not None:
                behavior_hints["videoSize"] = torrent_size
            if kodi_meta is not None:
                behavior_hints["cometKodiMetaV1"] = kodi_meta

            stream_name = _build_stream_name(
                kodi,
                debrid_extension,
                rtn_data.resolution,
                icon="⚡" if is_cached else "⬇️",
                formatted_components=formatted_components,
                seeders=torrent["seeders"],
                status="C" if is_cached else "U",
            )

            the_stream = {
                "name": stream_name,
                "description": formatted_title,
                "behaviorHints": behavior_hints,
            }

            if chilllink:
                the_stream["_chilllink"] = format_chilllink(
                    formatted_components, is_cached
                )

            file_index = torrent.get("fileIndex")
            file_index_str = (
                str(file_index)
                if file_index is not None and (is_cached or is_manual)
                else "n"
            )
            the_stream["url"] = (
                f"{playback_base_url}/playback/{info_hash}/{entry_index}/{file_index_str}/{result_season}/{result_episode}"
                f"?torrent_name={quoted_torrent_title}&name={quoted_title}"
                f"&media_id={quoted_media_only_id}&media_type={media_type}"
            )

            if is_cached:
                added_hashes.add(info_hash)

            if sort_mixed or is_cached:
                cached_results.append(the_stream)
            else:
                non_cached_results.append(the_stream)

        if enable_torrent:
            if deduplicate_streams and info_hash in added_hashes:
                return

            behavior_hints = {
                "bingeGroup": f"comet|torrent|{info_hash}",
                "filename": rtn_data.raw_title,
            }
            _attach_playback_score(behavior_hints, torrent_title, config)
            if torrent_size is not None:
                behavior_hints["videoSize"] = torrent_size
            if kodi_meta is not None:
                behavior_hints["cometKodiMetaV1"] = kodi_meta

            stream_name = _build_stream_name(
                kodi,
                torrent_service,
                rtn_data.resolution,
                icon="🧲",
                formatted_components=formatted_components,
                seeders=torrent["seeders"],
                status="P2P",
            )

            the_stream = {
                "name": stream_name,
                "description": formatted_title,
                "behaviorHints": behavior_hints,
                "infoHash": info_hash,
            }

            if chilllink:
                the_stream["_chilllink"] = format_chilllink(formatted_components, False)

            if torrent.get("fileIndex") is not None:
                the_stream["fileIdx"] = torrent["fileIndex"]

            sources = torrent.get("sources") or trackers
            if sources:
                the_stream["sources"] = sources

            cached_results.append(the_stream)

    emitted = list(ranked_info_hashes)
    for info_hash in emitted:
        _append_ranked_hash(info_hash)

    if (
        _client_disabled_480p(config)
        and not _has_playable_stream(cached_results + non_cached_results)
    ):
        fallback = _sd480_fallback_hashes(
            torrents,
            emitted,
            config["maxResultsPerResolution"],
        )
        if fallback:
            logger.log(
                "SCRAPER",
                f"TRACE {current_trace()} 480p fallback count={len(fallback)}",
            )
            emitted.extend(fallback)
            for info_hash in fallback:
                _append_ranked_hash(info_hash)

    if sort_mixed:
        final_streams = cached_results
    else:
        final_streams = cached_results + non_cached_results

    returned_counts = {}
    for info_hash in emitted:
        parsed = torrents[info_hash]["parsed"]
        key = str(getattr(parsed, "resolution", None) or "unknown") or "unknown"
        returned_counts[key] = returned_counts.get(key, 0) + 1
    logger.log(
        "SCRAPER",
        f"TRACE {current_trace()} returned={format_counts(returned_counts)} "
        f"streams={len(final_streams)}",
    )

    has_results = len(final_streams) > 0

    return _stream_response(
        {"streams": final_streams},
        is_empty=not has_results,
    )
