"""Optional basic web search, with extracted content saved as artifacts."""

import os
from typing import Literal

from ..core.cache import Cache, DEFAULT_WORKSPACE
from ..core.http import ProviderError, request_json, utcnow
from ..models import WebSearchResult


def search_web(
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    time_range: Literal["day", "week", "month", "year"] | None = None,
    *,
    workspace_dir=DEFAULT_WORKSPACE,
) -> WebSearchResult:
    if not query.strip():
        raise ValueError("query must not be empty")
    if type(max_results) is not int or not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10")
    if time_range not in {None, "day", "week", "month", "year"}:
        raise ValueError("invalid time_range")
    if include_domains is not None and any(
        not isinstance(d, str) or not d.strip() or "://" in d or "/" in d
        for d in include_domains
    ):
        raise ValueError("include_domains must contain hostnames, not URLs")
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise ProviderError(
            "Web research is unavailable: set TAVILY_API_KEY to enable search_web"
        )
    params = {
        "query": query.strip(),
        "max_results": max_results,
        "search_depth": "basic",
        "auto_parameters": False,
        "include_answer": False,
        "include_raw_content": "markdown",
        "include_usage": True,
    }
    if include_domains:
        params["include_domains"] = include_domains
    if time_range:
        params["time_range"] = time_range[0]  # Tavily's API uses d/w/m/y.
    cache = Cache(workspace_dir)
    cached = cache.get("cache/web", params)
    if cached is None:
        cached = {
            "data": request_json(
                "tavily",
                "POST",
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + api_key},
                json=params,
            ),
            "retrieved_at": utcnow(),
        }
        if not isinstance(cached["data"].get("results"), list):
            raise ProviderError("Tavily returned an invalid search result")
        cache.put("cache/web", params, cached)
    results = []
    for item in cached["data"]["results"][:max_results]:
        raw = item.get("raw_content") or ""
        url = item.get("url", "")
        artifact = (
            cache.artifact(
                "web",
                [url, cached["retrieved_at"]],
                f"# {item.get('title', '')}\n\nSource: {url}\nRetrieved: {cached['retrieved_at']}\n\n{raw}",
            )
            if raw.strip()
            else None
        )
        snippet = item.get("content") or ""
        results.append(
            {
                "title": item.get("title", ""),
                "url": url,
                "snippet": snippet[:1500],
                "snippet_truncated": len(snippet) > 1500,
                "score": item.get("score"),
                "artifact_path": artifact,
                "content_available": artifact is not None,
            }
        )
    return {
        "query": query.strip(),
        "provider": "tavily",
        "retrieved_at": cached["retrieved_at"],
        "results": results,
        "usage": cached["data"].get("usage"),
    }
