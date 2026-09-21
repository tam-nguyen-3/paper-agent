"""One-hop citation neighborhoods from Semantic Scholar."""

import os
import re
from typing import Literal
from urllib.parse import quote, unquote, urlparse

from ..core.cache import Cache, DEFAULT_WORKSPACE
from ..core.http import ProviderError, request_json, utcnow
from ..models import CitationGraph
from .arxiv import normalize_arxiv_id

BASE = "https://api.semanticscholar.org/graph/v1/paper/"
FIELDS = "paperId,title,year,authors,url,externalIds"


def normalize_citation_id(value):
    """Normalize DOI, arXiv, and explicit Semantic Scholar identifiers."""
    value = value.strip()
    if value.lower().startswith(("s2:", "semanticscholar:")):
        identifier = value.split(":", 1)[1]
        if not re.fullmatch(r"[0-9a-fA-F]{40}", identifier):
            raise ValueError("Expected a 40-character Semantic Scholar paper ID")
        return identifier, None
    doi = value
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    elif urlparse(doi).hostname in {"doi.org", "dx.doi.org"}:
        doi = unquote(urlparse(doi).path.lstrip("/"))
    if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return "DOI:" + doi, None
    identifier = normalize_arxiv_id(value)
    return "ARXIV:" + re.sub(r"v\d+$", "", identifier), identifier


def _node(paper):
    external = paper.get("externalIds") or {}
    return {
        "paper_id": paper["paperId"],
        "title": paper.get("title"),
        "year": paper.get("year"),
        "authors": [a.get("name", "") for a in paper.get("authors", [])],
        "url": paper.get("url"),
        "arxiv_id": external.get("ArXiv"),
        "doi": external.get("DOI"),
    }


def get_citation_graph(
    paper_id: str,
    direction: Literal["references", "citations"] = "references",
    limit: int = 20,
    offset: int = 0,
    *,
    workspace_dir=DEFAULT_WORKSPACE,
) -> CitationGraph:
    if direction not in {"references", "citations"}:
        raise ValueError("direction must be references or citations")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    identifier, requested_arxiv = normalize_citation_id(paper_id)
    cache = Cache(workspace_dir)
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    headers = {"x-api-key": api_key} if api_key else {}

    def fetch(suffix, params):
        url = BASE + quote(identifier, safe="") + suffix
        key = [url, params]
        cached = cache.get("cache/citations", key)
        if cached is not None:
            return cached
        result = {
            "data": request_json(
                "semantic_scholar", "GET", url, params=params, headers=headers
            ),
            "retrieved_at": utcnow(),
        }
        cache.put("cache/citations", key, result)
        return result

    result = {
        "status": "ok",
        "requested_id": paper_id,
        "requested_arxiv_id": requested_arxiv,
        "provider": "semantic_scholar",
        "retrieved_at": utcnow(),
        "direction": direction,
        "seed": None,
        "nodes": [],
        "edges": [],
        "citation_count": None,
        "reference_count": None,
        "next_offset": None,
        "unresolved_neighbors": 0,
        "warnings": [
            "Coverage and counts reflect Semantic Scholar, not research quality."
        ],
    }
    if requested_arxiv:
        result["warnings"].append(
            "Citation data describes the work, not an individual arXiv version."
        )
    try:
        seed_record = fetch("", {"fields": FIELDS + ",citationCount,referenceCount"})
    except ProviderError as exc:
        if exc.status_code != 404:
            raise
        result["status"] = "not_indexed"
        result["warnings"].append("Seed paper was not found in Semantic Scholar.")
        return result
    paper = seed_record["data"]
    if not paper.get("paperId"):
        raise ProviderError("Semantic Scholar returned a seed without a paper ID")
    seed = _node(paper)
    result.update(
        seed=seed,
        citation_count=paper.get("citationCount"),
        reference_count=paper.get("referenceCount"),
    )
    page_record = fetch(
        "/" + direction, {"fields": FIELDS, "limit": limit, "offset": offset}
    )
    page = page_record["data"]
    if not isinstance(page.get("data"), list):
        raise ProviderError("Semantic Scholar returned an invalid neighbor page")
    result["retrieved_at"] = min(
        seed_record["retrieved_at"], page_record["retrieved_at"]
    )
    result["next_offset"] = page.get("next")
    nodes, edges = {seed["paper_id"]: seed}, set()
    for entry in page["data"]:
        neighbor = entry.get(
            "citedPaper" if direction == "references" else "citingPaper"
        )
        if not neighbor or not neighbor.get("paperId"):
            result["unresolved_neighbors"] += 1
            continue
        node = _node(neighbor)
        nodes[node["paper_id"]] = node
        pair = (seed["paper_id"], node["paper_id"])
        edges.add(pair if direction == "references" else pair[::-1])
    result["nodes"] = list(nodes.values())
    result["edges"] = [{"source": a, "target": b} for a, b in sorted(edges)]
    if result["unresolved_neighbors"]:
        result["warnings"].append("Some neighbor records lack resolvable paper IDs.")
    count = result["reference_count" if direction == "references" else "citation_count"]
    if not page["data"]:
        result["status"] = "empty" if offset == 0 and count == 0 else "empty_page"
    if (
        result["next_offset"] is not None
        or offset
        or result["unresolved_neighbors"]
        or (count or 0) > len(edges)
    ):
        result["warnings"].append(
            "This response is a partial neighborhood; follow next_offset when available."
        )
    return result
