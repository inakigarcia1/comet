from typing import TypedDict

from pydantic import BaseModel

from comet.core.scrape import ScrapeContext


class ScrapeRequest(BaseModel):
    media_type: str  # "movie" or "series"
    media_id: str  # Full ID (e.g., "tt1234567:1:1" or "kitsu:123")
    media_only_id: str  # Base ID (e.g., "tt1234567")
    title: str
    year: int | None = None
    year_end: int | None = None
    season: int | None = None
    episode: int | None = None
    context: ScrapeContext = ScrapeContext.LIVE
    search_titles: tuple[str, ...] = ()
    absolute_episode: int | None = None

    @property
    def query_titles(self) -> tuple[str, ...]:
        return self.search_titles or (self.title,)

    def title_queries(self, *, include_episode_variants: bool = False):
        queries = []
        for title in self.query_titles:
            queries.append(title)
            if (
                include_episode_variants
                and self.media_type == "series"
                and self.season is not None
            ):
                queries.append(f"{title} S{self.season:02d}")
                if self.episode is not None:
                    queries.append(f"{title} S{self.season:02d}E{self.episode:02d}")
            if (
                self.absolute_episode is not None
                and self.episode is not None
                and self.absolute_episode != self.episode
            ):
                queries.append(f"{title} {self.absolute_episode}")
                padded = f"{self.absolute_episode:03d}"
                if padded != str(self.absolute_episode):
                    queries.append(f"{title} {padded}")
        return tuple(dict.fromkeys(queries))


class ScrapeResult(TypedDict):
    title: str
    infoHash: str
    fileIndex: int | None
    seeders: int | None
    size: int | None
    tracker: str
    sources: list[str]
