from typing import Literal

from langchain_core.tools import tool

from ..providers import semantic_scholar
from . import invoke_provider


def make_citation_tool(workspace_dir="research_data"):
    @tool
    def get_citation_graph(
        paper_id: str,
        direction: Literal["references", "citations"] = "references",
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Get one page of a paper's references or citing papers from Semantic Scholar.
        Accept arXiv IDs/URLs, DOI IDs/URLs, or S2:<40-character-paper-id>.
        Edges always run citing-to-cited. Follow next_offset to paginate; coverage
        can be incomplete. Citation counts do not establish quality or agreement.
        """
        return invoke_provider(
            semantic_scholar.get_citation_graph,
            paper_id,
            direction,
            limit,
            offset,
            workspace_dir=workspace_dir,
        )

    get_citation_graph.handle_tool_error = True
    return get_citation_graph


get_citation_graph = make_citation_tool()
