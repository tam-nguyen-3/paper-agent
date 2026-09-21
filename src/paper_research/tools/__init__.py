"""Thin LangChain adapters bound to a shared artifact workspace."""

from langchain_core.tools import ToolException

from ..core.http import ProviderError


def invoke_provider(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ProviderError, ValueError, OSError) as exc:
        raise ToolException(str(exc)) from exc


def build_tools(workspace_dir="research_data", *, web_enabled=False):
    from .arxiv import make_paper_tools
    from .citations import make_citation_tool
    from .web import make_web_tool

    result = [*make_paper_tools(workspace_dir), make_citation_tool(workspace_dir)]
    if web_enabled:
        result.append(make_web_tool(workspace_dir))
    return result
