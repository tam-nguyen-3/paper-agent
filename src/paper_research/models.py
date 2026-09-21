"""JSON-compatible result types shared by providers and tools."""

from typing import TypedDict


class Paper(TypedDict):
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    updated: str
    categories: list[str]
    primary_category: str | None
    abstract_url: str
    pdf_url: str | None
    doi: str | None
    journal_reference: str | None
    comment: str | None


class SearchResult(TypedDict):
    total_results: int
    start: int
    items_per_page: int
    papers: list[Paper]


class Page(TypedDict):
    page: int
    text: str


class Document(TypedDict):
    paper: Paper
    version: str
    pdf_url: str
    total_pages: int
    pages: list[Page]
    next_page: int | None
    truncated: bool
    warnings: list[str]
    artifact_path: str


class WebResult(TypedDict):
    title: str
    url: str
    snippet: str
    snippet_truncated: bool
    score: float | None
    artifact_path: str | None
    content_available: bool


class WebSearchResult(TypedDict):
    query: str
    provider: str
    retrieved_at: str
    results: list[WebResult]
    usage: dict | None


class GraphNode(TypedDict):
    paper_id: str
    title: str | None
    year: int | None
    authors: list[str]
    url: str | None
    arxiv_id: str | None
    doi: str | None


class Edge(TypedDict):
    source: str
    target: str


class CitationGraph(TypedDict):
    status: str
    requested_id: str
    requested_arxiv_id: str | None
    provider: str
    retrieved_at: str
    direction: str
    seed: GraphNode | None
    nodes: list[GraphNode]
    edges: list[Edge]
    citation_count: int | None
    reference_count: int | None
    next_offset: int | None
    unresolved_neighbors: int
    warnings: list[str]
