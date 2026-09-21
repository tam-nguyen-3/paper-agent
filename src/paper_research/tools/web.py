from typing import Literal

from langchain_core.tools import tool

from ..providers import tavily
from . import invoke_provider


def make_web_tool(workspace_dir="research_data"):
    @tool
    def search_web(
        query: str,
        max_results: int = 5,
        include_domains: list[str] | None = None,
        time_range: Literal["day", "week", "month", "year"] | None = None,
    ) -> dict:
        """Search the web for project pages, code, benchmarks, or research discussion.
        Requires TAVILY_API_KEY. Returns snippets and optional extracted-content
        artifact paths. Read artifacts for evidence; snippets aren't full pages.
        """
        return invoke_provider(
            tavily.search_web,
            query,
            max_results,
            include_domains,
            time_range,
            workspace_dir=workspace_dir,
        )

    search_web.handle_tool_error = True
    return search_web


search_web = make_web_tool()
