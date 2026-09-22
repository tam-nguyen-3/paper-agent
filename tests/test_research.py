import io
import json
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch

import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from paper_research.core.cache import Cache
from paper_research.core.http import ProviderError, request, retry_delay
from paper_research.providers.arxiv import _parse_feed, lookup, normalize_arxiv_id
from paper_research.providers.semantic_scholar import (
    get_citation_graph,
    normalize_citation_id,
)
from paper_research.providers.tavily import search_web
from paper_research.services.paper_reader import read_arxiv_paper
from test_client import FEED

FIXTURES = Path(__file__).parent / "fixtures"


def pdf_bytes(texts=("Evidence page one.", "Evidence page two.")):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class PaperTests(unittest.TestCase):
    def test_identifiers(self):
        for value, expected in [
            ("https://arxiv.org/pdf/hep-th/9901001v2.pdf", "hep-th/9901001v2"),
            ("arXiv:2501.12345v1", "2501.12345v1"),
        ]:
            self.assertEqual(normalize_arxiv_id(value), expected)
        self.assertEqual(
            normalize_citation_id("https://doi.org/10.1234/example"),
            ("DOI:10.1234/example", None),
        )
        self.assertEqual(
            normalize_citation_id("2501.12345v3"), ("ARXIV:2501.12345", "2501.12345v3")
        )
        self.assertEqual(normalize_citation_id("S2:" + "a" * 40), ("a" * 40, None))
        for value in ("https://example.org/abs/2501.12345", "../../secret", "nonsense"):
            with self.assertRaises(ValueError):
                normalize_arxiv_id(value)

    def test_lookup_uses_id_list(self):
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.providers.arxiv.request",
                return_value=httpx.Response(200, content=FEED),
            ) as req,
        ):
            self.assertEqual(
                lookup("1234.56789v2", workspace_dir=root)["arxiv_id"], "1234.56789v2"
            )
            query = httpx.URL(req.call_args.args[2]).params
            self.assertEqual(query["id_list"], "1234.56789v2")

    def test_real_pdf_extraction_pages_and_pinned_cache(self):
        paper = _parse_feed(FEED)["papers"][0]
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.services.paper_reader.lookup", return_value=paper
            ) as metadata,
            patch(
                "paper_research.services.paper_reader.request",
                return_value=httpx.Response(200, content=pdf_bytes()),
            ) as download,
        ):
            first = read_arxiv_paper("1234.56789", max_pages=1, workspace_dir=root)
            second = read_arxiv_paper("1234.56789", start_page=2, workspace_dir=root)
            self.assertEqual(first["next_page"], 2)
            self.assertIn("Evidence page one", first["pages"][0]["text"])
            self.assertEqual(second["pages"][0]["page"], 2)
            self.assertIn("Evidence page two", second["pages"][0]["text"])
            self.assertIsNone(second["next_page"])
            self.assertEqual(first["version"], "v2")
            self.assertIn("1234.56789v2", download.call_args.args[2])
            metadata.assert_called_once()
            download.assert_called_once()
            self.assertIn(
                "## PDF page 2",
                (Path(root) / first["artifact_path"].lstrip("/")).read_text(),
            )
            with self.assertRaises(ValueError):
                read_arxiv_paper("1234.56789", start_page=3, workspace_dir=root)

    def test_pdf_failures_and_blank_pages(self):
        paper = _parse_feed(FEED)["papers"][0]
        for payload in (b"corrupt", pdf_bytes(())):
            with (
                TemporaryDirectory() as root,
                patch(
                    "paper_research.services.paper_reader.lookup", return_value=paper
                ),
                patch(
                    "paper_research.services.paper_reader.request",
                    return_value=httpx.Response(200, content=payload),
                ),
            ):
                with self.assertRaises(ProviderError):
                    read_arxiv_paper("1234.56789", workspace_dir=root)
        with (
            TemporaryDirectory() as root,
            patch("paper_research.services.paper_reader.lookup", return_value=paper),
            patch(
                "paper_research.services.paper_reader.request",
                return_value=httpx.Response(200, content=pdf_bytes(("",))),
            ),
        ):
            result = read_arxiv_paper("1234.56789", workspace_dir=root)
            self.assertTrue(any("OCR" in warning for warning in result["warnings"]))

    def test_inline_truncation_preserves_full_artifact(self):
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.services.paper_reader.lookup",
                return_value=_parse_feed(FEED)["papers"][0],
            ),
        ):
            Cache(root).put("papers/pages", "1234.56789v2", ["x" * 21000])
            result = read_arxiv_paper("1234.56789", workspace_dir=root)
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["pages"][0]["text"]), 20000)
            self.assertIn(
                "x" * 21000,
                (Path(root) / result["artifact_path"].lstrip("/")).read_text(),
            )


class CitationTests(unittest.TestCase):
    def test_directions_deduplication_missing_neighbors_and_pagination(self):
        seed = json.loads((FIXTURES / "seed.json").read_text())
        for direction, field, source, target in [
            ("references", "citedPaper", "seed", "neighbor"),
            ("citations", "citingPaper", "neighbor", "seed"),
        ]:
            neighbor = {
                field: {"paperId": "neighbor", "title": "Neighbor", "externalIds": None}
            }
            page = {"data": [neighbor, neighbor, {field: None}], "next": 3}
            with (
                TemporaryDirectory() as root,
                patch(
                    "paper_research.providers.semantic_scholar.request_json",
                    side_effect=[seed, page],
                ) as req,
            ):
                result = get_citation_graph(
                    "2501.12345v2", direction, workspace_dir=root
                )
                cached = get_citation_graph(
                    "2501.12345v2", direction, workspace_dir=root
                )
                self.assertEqual(
                    result["edges"], [{"source": source, "target": target}]
                )
                self.assertEqual(len(result["nodes"]), 2)
                self.assertEqual(result["unresolved_neighbors"], 1)
                self.assertEqual(result["next_offset"], 3)
                self.assertEqual(result["retrieved_at"], cached["retrieved_at"])
                self.assertEqual(req.call_count, 2)
                self.assertIn("ARXIV%3A2501.12345", req.call_args.args[2])

    def test_not_indexed_empty_and_failure_differ(self):
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.providers.semantic_scholar.request_json",
                side_effect=ProviderError("missing", 404),
            ),
        ):
            self.assertEqual(
                get_citation_graph("2501.12345", workspace_dir=root)["status"],
                "not_indexed",
            )
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.providers.semantic_scholar.request_json",
                side_effect=ProviderError("throttled", 429),
            ),
        ):
            with self.assertRaises(ProviderError):
                get_citation_graph("2501.12345", workspace_dir=root)
        with (
            TemporaryDirectory() as root,
            patch(
                "paper_research.providers.semantic_scholar.request_json",
                side_effect=[{"paperId": "seed", "referenceCount": 0}, {"data": []}],
            ),
        ):
            self.assertEqual(
                get_citation_graph("2501.12345", workspace_dir=root)["status"], "empty"
            )


class WebTests(unittest.TestCase):
    def test_filters_artifacts_and_cache(self):
        payload = json.loads((FIXTURES / "web.json").read_text())
        payload["results"][0]["content"] = "s" * 2000
        with (
            TemporaryDirectory() as root,
            patch.dict(os.environ, {"TAVILY_API_KEY": "test"}),
            patch(
                "paper_research.providers.tavily.request_json", return_value=payload
            ) as req,
        ):
            result = search_web(
                "code",
                include_domains=["example.org"],
                time_range="month",
                workspace_dir=root,
            )
            search_web(
                "code",
                include_domains=["example.org"],
                time_range="month",
                workspace_dir=root,
            )
            req.assert_called_once()
            params = req.call_args.kwargs["json"]
            self.assertEqual(params["time_range"], "m")
            self.assertEqual(params["search_depth"], "basic")
            self.assertFalse(params["auto_parameters"])
            self.assertEqual(len(result["results"][0]["snippet"]), 1500)
            self.assertTrue(result["results"][0]["content_available"])
            self.assertFalse(result["results"][1]["content_available"])
            self.assertIsNone(result["results"][1]["artifact_path"])
            self.assertEqual(result["results"][0]["url"], "https://example.org/project")
            self.assertEqual(result["usage"], {"credits": 1})

    def test_missing_key_and_invalid_arguments(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            with self.assertRaisesRegex(ProviderError, "TAVILY_API_KEY"):
                search_web("code")
        for kwargs in (
            {"max_results": 11},
            {"include_domains": ["https://example.org"]},
            {"time_range": "decade"},
        ):
            with self.assertRaises(ValueError):
                search_web("code", **kwargs)


class InfrastructureTests(unittest.TestCase):
    def test_cache_expiry_and_atomic_concurrent_writes(self):
        with TemporaryDirectory() as root:
            cache = Cache(root)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(
                    pool.map(
                        lambda i: cache.put("test", {"key": 1}, {"value": "x" * i}),
                        range(100),
                    )
                )
            self.assertIsInstance(cache.get("test", {"key": 1})["value"], str)
            self.assertIsNone(cache.get("test", {"key": 1}, ttl=0))
            self.assertIsNotNone(cache.get("test", {"key": 1}, ttl=None))
            self.assertEqual(list(Path(root).rglob(".tmp-*")), [])

    def test_http_retries_timeouts_and_long_retry_after(self):
        real_client = httpx.Client
        for mode, expected_calls in [("retry", 3), ("timeout", 3), ("long", 1)]:
            calls = []

            def handler(req):
                calls.append(req)
                self.assertEqual(req.headers["user-agent"], "paper-research-agent/0.1")
                if mode == "timeout":
                    raise httpx.ReadTimeout("timeout", request=req)
                if mode == "retry" and len(calls) == 3:
                    return httpx.Response(200, content=b"ok")
                return httpx.Response(
                    429, headers={"Retry-After": "60" if mode == "long" else "0"}
                )

            with (
                patch(
                    "paper_research.core.http.httpx.Client",
                    side_effect=lambda **kw: real_client(
                        transport=httpx.MockTransport(handler), **kw
                    ),
                ),
                patch("paper_research.core.http.time.sleep") as sleep,
            ):
                if mode == "retry":
                    self.assertEqual(
                        request("arxiv", "GET", "https://example.org").content,
                        b"ok",
                    )
                else:
                    with self.assertRaises(ProviderError):
                        request("arxiv", "GET", "https://example.org")
                self.assertEqual(len(calls), expected_calls)
                expected_sleeps = {
                    "retry": [call(4), call(0), call(4), call(0), call(4)],
                    "timeout": [call(4), call(1), call(4), call(2), call(4)],
                    "long": [call(4)],
                }
                self.assertEqual(sleep.call_args_list, expected_sleeps[mode])

    def test_provider_request_delays(self):
        real_client = httpx.Client

        with patch(
            "paper_research.core.http.httpx.Client",
            side_effect=lambda **kw: real_client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=b"ok")
                ),
                **kw,
            ),
        ):
            for provider, expected_delay in (
                ("arxiv", 4),
                ("semantic_scholar", 1),
                ("tavily", None),
            ):
                with self.subTest(provider=provider), patch(
                    "paper_research.core.http.time.sleep"
                ) as sleep:
                    request(provider, "GET", "https://example.org")
                    if expected_delay is None:
                        sleep.assert_not_called()
                    else:
                        sleep.assert_called_once_with(expected_delay)

    def test_retry_delay_http_date(self):
        with patch("paper_research.core.http.time.time", return_value=0):
            self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:00:10 GMT", 0), 10)

    def test_http_error_includes_endpoint_and_bounded_body_excerpt(self):
        real_client = httpx.Client

        def handler(request):
            return httpx.Response(406, content=b"  Not acceptable\n" + b"x" * 400)

        with (
            patch(
                "paper_research.core.http.httpx.Client",
                side_effect=lambda **kw: real_client(
                    transport=httpx.MockTransport(handler), **kw
                ),
            ),
            patch("paper_research.core.http.time.sleep"),
            self.assertRaises(ProviderError) as caught,
        ):
            request(
                "arxiv",
                "GET",
                "https://export.arxiv.org/api/query?secret=hidden",
            )

        message = str(caught.exception)
        self.assertIn(
            "arxiv: HTTP 406 from https://export.arxiv.org/api/query", message
        )
        self.assertIn("; response: Not acceptable ", message)
        self.assertNotIn("secret", message)
        self.assertTrue(message.endswith("..."))
        self.assertLessEqual(len(message.rsplit("; response: ", 1)[1]), 300)

    def test_plain_import_is_lazy_and_tool_exports_work(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from paper_research import search; assert 'langchain_core' not in sys.modules",
            ],
            check=True,
        )
        from paper_research import search_arxiv
        from paper_research.tools.arxiv import search_arxiv as canonical

        self.assertIs(search_arxiv, canonical)
