"""A minimal client for the arXiv Atom API."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import unquote, urlencode, urlparse
from xml.etree import ElementTree

from ..core.cache import DEFAULT_WORKSPACE, Cache
from ..core.http import ProviderError, request
from ..models import Paper, SearchResult

API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = (
    "simple-arxiv-search/0.1 (mailto:125776168+tam-nguyen-3@users.noreply.github.com)"
)
SortBy = Literal["relevance", "lastUpdatedDate", "submittedDate"]
SortOrder = Literal["ascending", "descending"]

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


def normalize_arxiv_id(value):
    """Normalize modern/legacy arXiv IDs and arXiv abstract or PDF URLs."""
    value = value.strip()
    if value.lower().startswith("arxiv:"):
        value = value[6:]
    if "://" in value:
        url = urlparse(value)
        if url.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            raise ValueError("Expected an arXiv URL")
        match = re.fullmatch(r"/(?:abs|pdf)/(.+)", url.path)
        if not match:
            raise ValueError("Expected an arXiv abstract or PDF URL")
        value = unquote(match[1]).removesuffix(".pdf")
    if not re.fullmatch(
        r"(?:\d{4}\.\d{4,5}|[a-zA-Z][a-zA-Z.\-]*/\d{7})(?:v[1-9]\d*)?", value
    ):
        raise ValueError("Invalid arXiv identifier")
    return value


class ArxivAPIError(ProviderError):
    """Raised when the arXiv API cannot return a usable response."""


def _text(element: ElementTree.Element, path: str) -> str:
    child = element.find(path)
    return "" if child is None or child.text is None else " ".join(child.text.split())


def _optional_text(element: ElementTree.Element, path: str) -> str | None:
    value = _text(element, path)
    return value or None


def _parse_feed(payload: bytes) -> SearchResult:
    try:
        feed = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ArxivAPIError("arXiv returned malformed XML") from exc
    if feed.tag != f"{ATOM}feed":
        raise ArxivAPIError(
            "arXiv returned an unexpected document instead of an Atom feed"
        )

    papers: list[Paper] = []
    for entry in feed.findall(f"{ATOM}entry"):
        abstract_url = _text(entry, f"{ATOM}id")
        if (
            "/api/errors" in abstract_url
            or _text(entry, f"{ATOM}title").lower() == "error"
        ):
            raise ArxivAPIError(_text(entry, f"{ATOM}summary") or "arXiv query error")
        pdf_url = next(
            (
                link.get("href")
                for link in entry.findall(f"{ATOM}link")
                if link.get("title") == "pdf" or link.get("type") == "application/pdf"
            ),
            None,
        )
        arxiv_id = abstract_url.rsplit("/abs/", 1)[-1]

        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": _text(entry, f"{ATOM}title"),
                "authors": [
                    _text(author, f"{ATOM}name")
                    for author in entry.findall(f"{ATOM}author")
                ],
                "abstract": _text(entry, f"{ATOM}summary"),
                "published": _text(entry, f"{ATOM}published"),
                "updated": _text(entry, f"{ATOM}updated"),
                "categories": [
                    category.get("term", "")
                    for category in entry.findall(f"{ATOM}category")
                ],
                "primary_category": (
                    primary.get("term")
                    if (primary := entry.find(f"{ARXIV}primary_category")) is not None
                    else None
                ),
                "abstract_url": abstract_url,
                "pdf_url": pdf_url,
                "doi": _optional_text(entry, f"{ARXIV}doi"),
                "journal_reference": _optional_text(entry, f"{ARXIV}journal_ref"),
                "comment": _optional_text(entry, f"{ARXIV}comment"),
            }
        )

    def feed_int(name: str, fallback: int) -> int:
        value = _text(feed, f"{OPENSEARCH}{name}")
        try:
            return int(value) if value else fallback
        except ValueError as exc:
            raise ArxivAPIError("arXiv returned invalid pagination metadata") from exc

    return {
        "total_results": feed_int("totalResults", len(papers)),
        "start": feed_int("startIndex", 0),
        "items_per_page": feed_int("itemsPerPage", len(papers)),
        "papers": papers,
    }


def search(
    query: str,
    *,
    max_results: int = 5,
    start: int = 0,
    sort_by: SortBy = "relevance",
    sort_order: SortOrder = "descending",
    timeout: float = 20.0,
    workspace_dir=DEFAULT_WORKSPACE,
) -> SearchResult:
    """Search arXiv and return normalized paper metadata.

    ``query`` uses arXiv search syntax, for example ``all:transformers``,
    ``ti:"attention is all you need"``, or ``cat:cs.AI AND all:agents``.
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    if type(max_results) is not int or not 1 <= max_results <= 100:
        raise ValueError("max_results must be between 1 and 100")
    if type(start) is not int or start < 0:
        raise ValueError("start must be zero or greater")
    if sort_by not in {"relevance", "lastUpdatedDate", "submittedDate"}:
        raise ValueError("invalid sort_by value")
    if sort_order not in {"ascending", "descending"}:
        raise ValueError("invalid sort_order value")

    params = {
        "search_query": query.strip(),
        "start": start,
        "max_results": max_results,
    }
    if sort_by != "relevance":
        params.update(sortBy=sort_by, sortOrder=sort_order)
    return _query(params, timeout, workspace_dir)


def _query(params, timeout, workspace_dir):
    cache = Cache(workspace_dir)
    cached = cache.get("cache/arxiv", params)
    if cached is not None:
        return cached
    query_url = f"{API_URL}?{urlencode(params)}"
    print(f"Querying arXiv API: {query_url}")
    try:
        response = request(
            "arxiv",
            "GET",
            query_url,
            timeout=timeout,
            headers={"Accept": "application/atom+xml", "User-Agent": USER_AGENT},
        )
        result = _parse_feed(response.content)
    except ProviderError as exc:
        raise ArxivAPIError(str(exc), exc.status_code) from exc
    cache.put("cache/arxiv", params, result)
    return result


def lookup(identifier: str, *, workspace_dir=DEFAULT_WORKSPACE) -> Paper:
    """Resolve one exact identifier through arXiv's id_list endpoint."""
    result = _query(
        {"id_list": normalize_arxiv_id(identifier), "max_results": 1}, 20, workspace_dir
    )
    if not result["papers"]:
        raise ArxivAPIError("arXiv paper not found", 404)
    return result["papers"][0]
