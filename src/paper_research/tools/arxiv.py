from typing import Literal

from langchain_core.tools import tool

from ..providers import arxiv
from ..services import paper_reader
from . import invoke_provider


def make_paper_tools(workspace_dir="research_data"):
    @tool
    def search_arxiv(
        query: str,
        max_results: int = 5,
        sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "relevance",
    ) -> dict:
        """Search arXiv metadata and abstracts. Use all:, ti:, au:, abs:, cat:
        fields with AND/OR/ANDNOT, e.g. cat:cs.AI AND ti:reasoning.
        Use submittedDate for recent papers. Read full papers before detailed claims.
        """
        return invoke_provider(
            arxiv.search,
            query,
            max_results=max_results,
            sort_by=sort_by,
            workspace_dir=workspace_dir,
        )

    @tool
    def read_arxiv_paper(
        arxiv_id: str, start_page: int = 1, max_pages: int = 5
    ) -> dict:
        """Read an arXiv paper's PDF text with physical page numbers (one-based).
        Accept an arXiv ID or abstract/PDF URL; request up to 10 pages at once.
        Follow next_page or read_file/grep the returned artifact_path for more text.
        Cite the resolved version and page. Text extraction may miss figures and math.
        """
        return invoke_provider(
            paper_reader.read_arxiv_paper,
            arxiv_id,
            start_page,
            max_pages,
            workspace_dir=workspace_dir,
        )

    for item in (search_arxiv, read_arxiv_paper):
        item.handle_tool_error = True
    return search_arxiv, read_arxiv_paper


search_arxiv, read_arxiv_paper = make_paper_tools()
