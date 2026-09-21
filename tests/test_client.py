from unittest import TestCase
from unittest.mock import patch
from tempfile import TemporaryDirectory
import httpx

from paper_research.providers.arxiv import _parse_feed, search


FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>42</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/1234.56789v2</id>
    <updated>2026-01-02T00:00:00Z</updated>
    <published>2026-01-01T00:00:00Z</published>
    <title>  A Paper\n  About Agents </title>
    <summary>An abstract.\n With whitespace.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <category term="cs.AI"/>
    <arxiv:primary_category term="cs.AI"/>
    <arxiv:doi>10.1000/example</arxiv:doi>
    <link href="http://arxiv.org/abs/1234.56789v2" rel="alternate"/>
    <link title="pdf" href="http://arxiv.org/pdf/1234.56789v2" type="application/pdf"/>
  </entry>
</feed>"""


class ArxivClientTests(TestCase):
    def test_parse_feed(self):
        result = _parse_feed(FEED)

        self.assertEqual(result["total_results"], 42)
        self.assertEqual(result["papers"][0]["arxiv_id"], "1234.56789v2")
        self.assertEqual(result["papers"][0]["title"], "A Paper About Agents")
        self.assertEqual(
            result["papers"][0]["authors"], ["Ada Lovelace", "Alan Turing"]
        )
        self.assertEqual(result["papers"][0]["primary_category"], "cs.AI")
        self.assertEqual(result["papers"][0]["doi"], "10.1000/example")

    @patch(
        "paper_research.providers.arxiv.request",
        return_value=httpx.Response(200, content=FEED),
    )
    def test_search_builds_encoded_request(self, mocked_request):
        with TemporaryDirectory() as directory:
            for _ in range(2):
                search(
                    'cat:cs.AI AND ti:"tool use"',
                    max_results=7,
                    sort_by="submittedDate",
                    workspace_dir=directory,
                )
        params = mocked_request.call_args.kwargs["params"]
        self.assertEqual(params["search_query"], 'cat:cs.AI AND ti:"tool use"')
        self.assertEqual(params["max_results"], 7)
        self.assertEqual(params["sortBy"], "submittedDate")
        mocked_request.assert_called_once()

    def test_atom_errors_and_nonfeeds_are_not_papers(self):
        from paper_research import ArxivAPIError

        error = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#bad_query</id><summary>Bad query</summary></entry></feed>'
        for payload in (error, b"<html/>", b"broken"):
            with self.subTest(payload=payload), self.assertRaises(ArxivAPIError):
                _parse_feed(payload)

    def test_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            search("")
        with self.assertRaises(ValueError):
            search("all:agents", max_results=101)
