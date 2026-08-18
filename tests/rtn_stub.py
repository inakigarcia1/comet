"""Local-only RTN stub used to run the test suite without the
real Rust-built RTN package. The real one is installed at CI / runtime.

This stub must live in `tests/` so it never shadows the real package in
production. Tests import `tests.rtn_stub` before importing any comet
module that pulls in RTN.
"""
import sys
import types


_RESOLUTIONS = [
    "r2160p",
    "r1440p",
    "r1080p",
    "r720p",
    "r576p",
    "r480p",
    "r360p",
    "r240p",
    "unknown",
]


class _Resolution:
    def __init__(self, value):
        self.value = value


class _ResolutionEnum:
    _members = {r: _Resolution(r) for r in _RESOLUTIONS}

    def __init__(self):
        for name, value in self._members.items():
            setattr(self, name, value)

    def __iter__(self):
        return iter(self._members.values())


class _Extras:
    Resolution = _ResolutionEnum()


def _normalize_title(title):
    return title.replace(".", " ").replace("_", " ").strip()


def _title_match(expected, parsed, aliases=None):
    if not expected or not parsed:
        return False
    exp = expected.lower().replace(".", " ").replace("_", " ").strip()
    par = parsed.lower().replace(".", " ").replace("_", " ").strip()
    return exp in par or par in exp


class Torrent:
    def __init__(self, infohash, raw_title, data, fetch, rank, lev_ratio):
        self.infohash = infohash
        self.raw_title = raw_title
        self.data = data
        self.fetch = fetch
        self.rank = rank
        self.lev_ratio = lev_ratio


class ParsedData:
    def __init__(self, **kwargs):
        # Allow any attribute; the slots list is just for documentation.
        self.__dict__.update(kwargs)

    def model_copy(self):
        clone = ParsedData()
        clone.__dict__.update(self.__dict__)
        return clone

    def model_dump(self):
        return dict(self.__dict__)


def _classify(title):
    upper = title.upper()
    if "REMUX" in upper:
        return "REMUX"
    if "ULTRA HD BLURAY" in upper or "UHD.BLURAY" in upper.replace(" ", "."):
        return "BLURAY"
    if "BLURAY" in upper or "BLU-RAY" in upper:
        return "BLURAY"
    if "WEB-DL" in upper or "WEBDL" in upper:
        return "WEBDL"
    if "WEBMUX" in upper:
        return "WEBMUX"
    if "WEBRIP" in upper:
        return "WEBRIP"
    if "WEB" in upper:
        return "WEB"
    if "HDTV" in upper:
        return "HDTV"
    if "BDRIP" in upper:
        return "BDRIP"
    if "BRRIP" in upper:
        return "BRRIP"
    if "DVDRIP" in upper:
        return "DVDRIP"
    if "HDRIP" in upper:
        return "HDRIP"
    if "TVRIP" in upper:
        return "TVRIP"
    if "TELECINE" in upper:
        return "TELECINE"
    if "TELESYNC" in upper:
        return "TELESYNC"
    if "SCREENER" in upper:
        return "SCREENER"
    if "CAM" in upper:
        return "CAM"
    if "DVD" in upper:
        return "DVD"
    return "UNKNOWN"


def parse(title):
    if not isinstance(title, str) or not title:
        return ParsedData(
            raw_title=title,
            parsed_title=None,
            year=None,
            resolution="unknown",
            quality=None,
            rip="UNKNOWN",
            codec=None,
            audio=None,
            channels=None,
            hdr=None,
            languages=[],
            extras=[],
            adult=False,
            trash=False,
            seasons=[],
            episodes=[],
            dubbed=False,
            edition=None,
            network=None,
            group=None,
            container=None,
            bitrate=None,
            site=None,
            proper=False,
            repack=False,
            upscaled=False,
            remux=False,
            documentary=False,
            three_d=False,
            converted=False,
            raw=None,
            title=None,
            complete=False,
        )
    upper = title.upper()
    parts = title.replace(".", " ").replace("_", " ").split()
    parsed_title = None
    for token in parts:
        if token and not token.isupper() and not token[0].isdigit():
            parsed_title = token
            break
    if parsed_title is None and parts:
        parsed_title = parts[0]

    year = None
    for token in parts:
        if token.isdigit() and len(token) == 4 and 1900 <= int(token) <= 2100:
            year = int(token)
            break

    resolution = "unknown"
    if "2160P" in upper:
        resolution = "2160p"
    elif "1440P" in upper:
        resolution = "1440p"
    elif "1080P" in upper:
        resolution = "1080p"
    elif "720P" in upper:
        resolution = "720p"
    elif "480P" in upper:
        resolution = "480p"

    rip = _classify(title)
    codec = "H.264" if "H.264" in upper or "X264" in upper else None
    audio = "DDP5.1" if "DDP" in upper or "TRUEHD" in upper else None
    channels = None
    hdr = "HDR" if "HDR" in upper else None
    adult = False
    trash = "sample" in title.lower()
    seasons = []
    episodes = []
    for i, token in enumerate(parts):
        if token.upper() == "S" and i + 1 < len(parts) and parts[i + 1].isdigit():
            seasons.append(int(parts[i + 1]))
        if token.upper() == "E" and i + 1 < len(parts) and parts[i + 1].isdigit():
            episodes.append(int(parts[i + 1]))
    return ParsedData(
        raw_title=title,
        parsed_title=parsed_title,
        year=year,
        resolution=resolution,
        quality=None,
        rip=rip,
        codec=codec,
        audio=audio,
        channels=channels,
        hdr=hdr,
        languages=[],
        extras=[],
        adult=adult,
        trash=trash,
        seasons=seasons,
        episodes=episodes,
        dubbed=False,
        edition=None,
        network=None,
        group=None,
        container=None,
        bitrate=None,
        site=None,
        proper=False,
        repack=False,
        upscaled=False,
        remux=False,
        documentary=False,
        three_d=False,
        converted=False,
        raw=None,
        title=title,
        complete=False,
    )


def settings(*args, **kwargs):
    return None


def check_fetch_and_rank_many(*args, **kwargs):
    return []


def sort_torrents(*args, **kwargs):
    return []


class _Base:
    def __init__(self, *args, **kwargs):
        pass

    def model_copy(self, *, update=None):
        clone = _Base()
        clone.__dict__.update(self.__dict__)
        if update:
            clone.__dict__.update(update)
        return clone

    def model_dump(self, *args, **kwargs):
        return dict(self.__dict__)


def _make_pydantic_base():
    from pydantic import BaseModel

    class _PyBase(BaseModel):
        model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        def model_copy(self, *, update=None):
            data = self.model_dump()
            if update:
                data.update(update)
            return self.__class__(**data)

        def model_dump(self, *args, **kwargs):
            data = super().model_dump(*args, **kwargs)
            # Strip Pydantic infrastructure so dumps look like real RTN dumps.
            _skip_prefixes = ("model_", "parse_", "from_orm", "construct", "schema", "validate", "update_forward_refs", "copy", "dict", "json")
            data = {
                key: value
                for key, value in data.items()
                if not any(key.startswith(p) for p in _skip_prefixes)
            }
            # Walk class-level defaults from annotations so dumps include
            # them even when Pydantic's metaclass hides them.
            for klass in reversed(type(self).__mro__):
                annotations = getattr(klass, "__annotations__", None)
                if not annotations:
                    continue
                for name in annotations:
                    if name not in data and name in vars(klass):
                        data[name] = vars(klass)[name]
            # Drain class-level defaults that aren't annotated but are
            # declared via `field: Type = default` patterns.
            for klass in reversed(type(self).__mro__):
                for name, value in vars(klass).items():
                    if name.startswith("_"):
                        continue
                    if callable(value):
                        continue
                    if any(name.startswith(p) for p in _skip_prefixes):
                        continue
                    if name not in data:
                        data[name] = value
            return data

    return _PyBase


class DefaultRanking(_make_pydantic_base()):
    pass


class SettingsModel(_make_pydantic_base()):
    pass


def _rtn_models_module():
    from typing import Any
    from pydantic import Field

    mod = types.ModuleType("RTN.models")
    PyBase = _make_pydantic_base()

    class _BaseDict(PyBase):
        pass

    # Subclasses with the real RTN fields so dumps surface them.
    class _DictLike(PyBase):
        def __getitem__(self, key):
            return self.model_dump()[key]

        def __contains__(self, key):
            return key in self.model_dump()

    class OptionsConfig(_DictLike):
        remove_ranks_under: Any = -10000000000
        allow_english_in_languages: bool = False
        remove_unknown_languages: bool = False

    class LanguagesConfig(_DictLike):
        exclude: list = []
        required: list = []
        allowed: list = []
        preferred: list = []

    class ResolutionConfig(_DictLike):
        r2160p: bool = True
        r1440p: bool = True
        r1080p: bool = True
        r720p: bool = True
        r576p: bool = True
        r480p: bool = True
        r360p: bool = True
        r240p: bool = True
        unknown: bool = True

    mod.AudioRankModel = _BaseDict
    mod.CustomRank = _BaseDict
    mod.CustomRanksConfig = _BaseDict
    mod.ExtrasRankModel = _BaseDict
    mod.HdrRankModel = _BaseDict
    mod.LanguagesConfig = LanguagesConfig
    mod.OptionsConfig = OptionsConfig
    mod.QualityRankModel = _BaseDict
    mod.ResolutionConfig = ResolutionConfig
    mod.RipsRankModel = _BaseDict
    mod.TrashRankModel = _BaseDict
    return mod


def _install_rtn_stub():
    """Inject the stub `RTN` package into `sys.modules` if not already present."""
    if "RTN" in sys.modules:
        return
    rtn = types.ModuleType("RTN")
    rtn.ParsedData = ParsedData
    rtn.Torrent = Torrent
    rtn.parse = parse
    rtn.normalize_title = _normalize_title
    rtn.title_match = _title_match
    rtn.settings = settings
    rtn.DefaultRanking = DefaultRanking
    rtn.SettingsModel = SettingsModel
    rtn.check_fetch_and_rank_many = check_fetch_and_rank_many
    rtn.sort_torrents = sort_torrents
    rtn.extras = _Extras()
    rtn.models = _rtn_models_module()

    # Submodule `RTN.exceptions`
    exceptions = types.ModuleType("RTN.exceptions")

    class GarbageTorrent(Exception):
        pass

    exceptions.GarbageTorrent = GarbageTorrent
    rtn.exceptions = exceptions

    sys.modules["RTN"] = rtn
    sys.modules["RTN.models"] = rtn.models
    sys.modules["RTN.exceptions"] = exceptions


_install_rtn_stub()

