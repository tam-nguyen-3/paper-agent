"""Research tools for academic papers and supporting web sources."""

from .providers.arxiv import ArxivAPIError, search

__all__ = [
    "ArxivAPIError",
    "search",
    "search_arxiv",
    "read_arxiv_paper",
    "search_web",
    "get_citation_graph",
    "create_research_agent",
]


def __getattr__(name):
    if name == "create_research_agent":
        from .agent import create_research_agent

        return create_research_agent
    if name in {"search_arxiv", "read_arxiv_paper"}:
        from .tools import arxiv

        return getattr(arxiv, name)
    if name == "search_web":
        from .tools.web import search_web

        return search_web
    if name == "get_citation_graph":
        from .tools.citations import get_citation_graph

        return get_citation_graph
    raise AttributeError(name)
