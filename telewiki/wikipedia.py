"""MediaWiki / Wikimedia API client.

Network code lives in WikipediaClient; all response parsing is done by pure
module-level functions so it can be unit-tested without network access.
"""

import html as html_lib
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from telewiki.config import Settings

TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SearchResult:
    title: str
    snippet: str = ""  # plain text, search terms highlighted upstream


@dataclass
class ArticleSummary:
    title: str
    extract: str
    url: str
    image: str | None = None
    description: str | None = None
    is_disambiguation: bool = False


@dataclass
class HistoryEvent:
    year: int | None
    text: str
    url: str | None = None


# -- pure parsing helpers ---------------------------------------------------


def strip_tags(text: str) -> str:
    """Remove HTML tags and unescape entities from MediaWiki snippets."""
    return html_lib.unescape(TAG_RE.sub("", text or "")).strip()


def truncate(text: str, limit: int) -> str:
    """Shorten to a word boundary, appending an ellipsis if cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,;:") + "…"


def parse_search_response(data: dict, limit: int = 5) -> list:
    items = (data.get("query") or {}).get("search") or []
    results = []
    for item in items[:limit]:
        title = item.get("title")
        if not title:
            continue
        results.append(SearchResult(title=title, snippet=strip_tags(item.get("snippet"))))
    return results


def parse_summary_response(data: dict) -> ArticleSummary | None:
    if not data or data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return None
    title = data.get("title") or data.get("displaytitle")
    if not title:
        return None
    content_urls = data.get("content_urls") or {}
    desktop = content_urls.get("desktop") or {}
    thumbnail = data.get("thumbnail") or {}
    return ArticleSummary(
        title=strip_tags(title),
        extract=(data.get("extract") or "").strip(),
        url=desktop.get("page", ""),
        image=thumbnail.get("source"),
        description=data.get("description"),
        is_disambiguation=data.get("type") == "disambiguation",
    )


def parse_onthisday_response(data: dict) -> list:
    events = []
    for item in data.get("events") or []:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        try:
            year = int(item.get("year")) if item.get("year") is not None else None
        except (TypeError, ValueError):
            year = None
        url = None
        pages = item.get("pages") or []
        if pages:
            content_urls = pages[0].get("content_urls") or {}
            url = (content_urls.get("desktop") or {}).get("page")
        events.append(HistoryEvent(year=year, text=text, url=url))
    return events


def format_summary_html(summary: ArticleSummary, limit: int = 900) -> str:
    """Render an article summary as Telegram HTML."""
    lines = [f"<b>{html_lib.escape(summary.title)}</b>"]
    if summary.description:
        lines.append(f"<i>{html_lib.escape(summary.description)}</i>")
    if summary.extract:
        lines.append(html_lib.escape(truncate(summary.extract, limit)))
    if summary.url:
        lines.append(f'<a href="{summary.url}">Read more on Wikipedia</a>')
    return "\n\n".join(lines)


# -- async client -------------------------------------------------------------


class WikipediaClient:
    def __init__(self, lang: str = "en", user_agent: str | None = None):
        self._lang = lang
        self._http = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": user_agent or Settings.user_agent},
            follow_redirects=True,
        )

    @property
    def _api(self) -> str:
        return f"https://{self._lang}.wikipedia.org/w/api.php"

    @property
    def _rest(self) -> str:
        return f"https://{self._lang}.wikipedia.org/api/rest_v1"

    @property
    def _feed(self) -> str:
        return f"https://api.wikimedia.org/feed/v1/wikipedia/{self._lang}"

    async def search(self, query: str, limit: int = 5) -> list:
        resp = await self._http.get(
            self._api,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
                "formatversion": 2,
            },
        )
        resp.raise_for_status()
        return parse_search_response(resp.json(), limit=limit)

    async def summary(self, title: str) -> ArticleSummary | None:
        resp = await self._http.get(f"{self._rest}/page/summary/{quote(title)}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return parse_summary_response(resp.json())

    async def on_this_day(self, month: int, day: int) -> list:
        resp = await self._http.get(f"{self._feed}/onthisday/all/{month:02d}/{day:02d}")
        resp.raise_for_status()
        return parse_onthisday_response(resp.json())

    async def featured(self, year: int, month: int, day: int) -> ArticleSummary | None:
        resp = await self._http.get(f"{self._feed}/featured/{year:04d}/{month:02d}/{day:02d}")
        resp.raise_for_status()
        return parse_summary_response((resp.json() or {}).get("tfa") or {})

    async def aclose(self) -> None:
        await self._http.aclose()
