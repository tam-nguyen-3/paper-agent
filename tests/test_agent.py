import json
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from paper_research.agent import create_research_agent
from paper_research.providers.arxiv import _parse_feed
from paper_research.tools import build_tools
from test_client import FEED
from test_research import pdf_bytes


class ScriptedReader(BaseChatModel):
    """Drive actual graph/tool execution without a model service."""

    @property
    def _llm_type(self):
        return "scripted-reader"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        results = [message for message in messages if isinstance(message, ToolMessage)]
        if not results:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_arxiv_paper",
                        "args": {"arxiv_id": "1234.56789", "max_pages": 1},
                        "id": "paper-call",
                        "type": "tool_call",
                    }
                ],
            )
        elif results[-1].name == "read_arxiv_paper":
            data = json.loads(results[-1].content)
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": data["artifact_path"]},
                        "id": "file-call",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            assert "Evidence page two" in results[-1].content, results[-1].content
            message = AIMessage(content="Evidence verified in version v2, PDF page 2.")
        return ChatResult(generations=[ChatGeneration(message=message)])


class AgentTests(unittest.TestCase):
    def test_agent_reads_tool_artifact_through_backend(self):
        with (
            TemporaryDirectory() as root,
            patch.dict(os.environ, {"TAVILY_API_KEY": ""}),
            patch(
                "paper_research.services.paper_reader.lookup",
                return_value=_parse_feed(FEED)["papers"][0],
            ),
            patch(
                "paper_research.services.paper_reader.request",
                return_value=httpx.Response(200, content=pdf_bytes()),
            ),
        ):
            with self.assertWarnsRegex(UserWarning, "Web research is unavailable"):
                agent = create_research_agent(ScriptedReader(), root)
            result = agent.invoke(
                {
                    "messages": [
                        {"role": "user", "content": "Read and verify this paper"}
                    ]
                }
            )
            self.assertIn("PDF page 2", result["messages"][-1].content)

    def test_optional_web_and_error_conversion(self):
        self.assertEqual(len(build_tools(web_enabled=False)), 3)
        tools = {t.name: t for t in build_tools(web_enabled=True)}
        self.assertEqual(len(tools), 4)
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            self.assertIn(
                "TAVILY_API_KEY", tools["search_web"].invoke({"query": "code"})
            )
        self.assertIn(
            "Invalid arXiv", tools["read_arxiv_paper"].invoke({"arxiv_id": "invalid"})
        )
        self.assertNotIn("workspace_dir", tools["read_arxiv_paper"].args)

    def test_factory_registers_web_when_configured(self):
        with (
            TemporaryDirectory() as root,
            patch.dict(os.environ, {"TAVILY_API_KEY": "test"}),
            patch("paper_research.agent.create_deep_agent") as create,
        ):
            create_research_agent(ScriptedReader(), root)
            self.assertIn(
                "search_web", [t.name for t in create.call_args.kwargs["tools"]]
            )
