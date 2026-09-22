"""Download an exact arXiv version and extract page-addressable text."""

import io
import re

from pypdf import PdfReader

from ..core.cache import DEFAULT_WORKSPACE, Cache
from ..core.http import ProviderError, request
from ..models import Document
from ..providers.arxiv import lookup, normalize_arxiv_id


def read_arxiv_paper(
    arxiv_id: str,
    start_page: int = 1,
    max_pages: int = 5,
    *,
    workspace_dir=DEFAULT_WORKSPACE,
) -> Document:
    if type(start_page) is not int or start_page < 1:
        raise ValueError("start_page must be a positive integer")
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError("max_pages must be between 1 and 10")
    requested = normalize_arxiv_id(arxiv_id)
    cache = Cache(workspace_dir)
    # Pin an unversioned ID for this local cache, even when metadata TTL expires.
    pinned = cache.get("cache/paper-pins", requested, ttl=None)
    paper = pinned or lookup(requested, workspace_dir=workspace_dir)
    resolved = normalize_arxiv_id(paper["arxiv_id"])
    version = re.search(r"v\d+$", resolved)
    if not version:
        raise ProviderError("arXiv metadata did not resolve an exact version")
    if re.search(r"v\d+$", requested) and requested != resolved:
        raise ProviderError("arXiv returned a different version than requested")
    pdf_url = "https://arxiv.org/pdf/" + resolved
    pdf_path = cache.path("papers/pdf", resolved, ".pdf")
    pages = cache.get("papers/pages", resolved, ttl=None)
    if pages is None:
        payload = (
            pdf_path.read_bytes()
            if pdf_path.exists()
            else request("arxiv", "GET", pdf_url, timeout=60).content
        )
        try:
            reader = PdfReader(io.BytesIO(payload))
            if reader.is_encrypted:
                raise ValueError("encrypted document")
            pages = [page.extract_text() or "" for page in reader.pages]
            if not pages:
                raise ValueError("document has no pages")
        except Exception as exc:
            raise ProviderError(f"Could not extract arXiv PDF: {exc}") from exc
        cache.write(pdf_path, payload)
        cache.put("papers/pages", resolved, pages)
    cache.put("cache/paper-pins", requested, paper)
    if start_page > len(pages):
        raise ValueError(f"start_page exceeds the document's {len(pages)} pages")
    artifact = cache.named_artifact(
        "papers/text",
        resolved,
        f"# {paper['title']}\n\nSource: {pdf_url}\nVersion: {version[0]}\n\n"
        + "\n\n".join(f"## PDF page {i}\n\n{text}" for i, text in enumerate(pages, 1)),
    )
    end = min(len(pages), start_page + max_pages - 1)
    selected, remaining, truncated = [], 20000, False
    for number in range(start_page, end + 1):
        text = pages[number - 1]
        selected.append({"page": number, "text": text[:remaining]})
        truncated |= len(text) > remaining
        remaining = max(0, remaining - len(text))
    warnings = [
        "Text extraction may lose equations, tables, figures, and reading order."
    ]
    empty = [i for i, text in enumerate(pages, 1) if not text.strip()]
    if empty:
        warnings.append(f"No text on PDF pages {empty}; these may require OCR.")
    if truncated:
        warnings.append(
            "Inline text truncated; use read_file on artifact_path for complete text."
        )
    return {
        "paper": paper,
        "version": version[0],
        "pdf_url": pdf_url,
        "total_pages": len(pages),
        "pages": selected,
        "next_page": end + 1 if end < len(pages) else None,
        "truncated": truncated,
        "warnings": warnings,
        "artifact_path": artifact,
    }
