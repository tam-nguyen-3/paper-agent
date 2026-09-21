"""Opt in explicitly; Tavily's smoke test consumes one search credit."""

import os
import unittest
from tempfile import TemporaryDirectory

from paper_research.providers.arxiv import search
from paper_research.providers.semantic_scholar import get_citation_graph
from paper_research.providers.tavily import search_web
from paper_research.services.paper_reader import read_arxiv_paper


class LiveTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv("RUN_LIVE_ARXIV") == "1", "opt-in live arXiv test")
    def test_arxiv_search(self):
        with TemporaryDirectory() as root:
            result = search(
                'ti:"attention is all you need"', max_results=1, workspace_dir=root
            )
            self.assertTrue(result["papers"])

    @unittest.skipUnless(os.getenv("RUN_LIVE_ARXIV") == "1", "opt-in live arXiv test")
    def test_arxiv_reader(self):
        with TemporaryDirectory() as root:
            paper = read_arxiv_paper("1706.03762v7", max_pages=1, workspace_dir=root)
            self.assertIn("Attention", paper["pages"][0]["text"])

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_CITATIONS") == "1", "opt-in live citation test"
    )
    def test_citations(self):
        with TemporaryDirectory() as root:
            result = get_citation_graph("1706.03762", limit=2, workspace_dir=root)
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["edges"])

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_TAVILY") == "1" and os.getenv("TAVILY_API_KEY"),
        "opt-in live Tavily test with API key",
    )
    def test_tavily(self):
        with TemporaryDirectory() as root:
            result = search_web(
                "Attention Is All You Need official paper",
                max_results=1,
                workspace_dir=root,
            )
            self.assertTrue(result["results"])
