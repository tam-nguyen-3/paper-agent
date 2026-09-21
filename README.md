# Local research tools

A local Deep Agents prototype with arXiv search, PDF reading, citation exploration,
and optional Tavily web search. No database service or web server is required.

## Setup

```bash
uv sync
```

Use `.env.example` as a template for your local `.env`. Add `TAVILY_API_KEY` only
if you want web search. `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended
because unauthenticated users share provider capacity. Configure your model's
credentials separately. The example loads `.env`; library functions do not.

## Use it directly

```python
from paper_research import search
from paper_research.providers.semantic_scholar import get_citation_graph
from paper_research.providers.tavily import search_web
from paper_research.services.paper_reader import read_arxiv_paper

result = search(
    'cat:cs.AI AND all:"self improving agents"',
    max_results=5,
    sort_by="submittedDate",
)

for paper in result["papers"]:
    print(paper["title"], paper["abstract_url"])

paper = read_arxiv_paper("1706.03762v7", start_page=1, max_pages=3)
graph = get_citation_graph("1706.03762", direction="citations", limit=20)
# Requires TAVILY_API_KEY:
# web = search_web("Attention Is All You Need official code", include_domains=["github.com"])
```

Or from the command line:

```bash
uv run paper-research 'cat:cs.AI AND all:"self improving agents"' \
  --max-results 5 --sort-by submittedDate
```

## Give it to a LangChain or Deep Agents agent

```python
from paper_research import create_research_agent

agent = create_research_agent(model=model, workspace_dir="research_data")
result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Read 1706.03762v7 and explain its method with page citations.",
            }
        ]
    }
)
print(result["messages"][-1].content)
```

Here `model` is your configured chat model or a supported `provider:model` string.
Without a Tavily key, the factory emits a warning and omits `search_web`.

```bash
uv run python examples/research.py --model PROVIDER:MODEL \
  'Find recent agent papers and their official code; cite your sources.'
```

Top-level imports `search_arxiv`, `read_arxiv_paper`, `search_web`, and
`get_citation_graph` are LangChain tool objects: call `.invoke({...})` or pass them
to an agent. For plain Python functions use the provider imports above.
Importing the direct search client does not import LangChain.

All tools must share the agent backend's workspace for artifact paths to work.
The factory handles that binding. For a custom agent, use
`paper_research.tools.build_tools(workspace_dir, web_enabled=True)` and configure a
`FilesystemBackend` with the same root and `virtual_mode=True`.

## Tool behavior

| Tool | Input | Output |
| --- | --- | --- |
| `search_arxiv` | arXiv query, result limit, sorting | Metadata and abstracts |
| `read_arxiv_paper` | ID/URL, one-based start page, 1–10 pages | Version, page text, next page, complete text artifact |
| `get_citation_graph` | arXiv/DOI ID or URL, `S2:<id>`, direction, limit/offset | Seed, nodes, citing-to-cited edges, counts and next offset |
| `search_web` | Query, 1–10 results, optional domains and day/week/month/year | Snippets, URLs, scores, optional extracted-content artifacts |

Paper reading resolves an exact version through arXiv's `id_list`. Unversioned
IDs are pinned locally: clear `research_data/cache/paper-pins/` to resolve them
again, or pass an explicit new version. Versioned PDFs and extracted text remain
cached until manually removed. Inline paper text is capped at 20,000 characters;
read the full artifact when `truncated` is true. `next_page` advances past the
requested page range, so use the artifact to recover truncated text within it.

PDF page numbers are physical one-based indices, which may differ from printed
page labels. Extraction preserves available text and line breaks, but may lose
equations, table structure, figures, or reading order. Blank/image-only pages
produce warnings; OCR and visual interpretation are not included.

Citation edges always point from citing to cited paper. `references` returns
outgoing edges and `citations` incoming edges. Follow the provider's `next_offset`
for more results. Missing seeds return `not_indexed`, a confirmed zero-neighbor
seed returns `empty`, and an empty pagination slice returns `empty_page`.
Unresolved neighbors are counted, and incomplete neighborhoods carry warnings.
Graph data applies to a work, not an exact arXiv version. There is no fuzzy title
matching, quality ranking, automatic multi-hop expansion, or completeness claim.

Web search uses Tavily basic search with automatic upgrades and generated answers
disabled. Snippets are capped at 1,500 characters each. `content_available` means
Tavily supplied extracted text, not that extraction was complete or the agent
has inspected it. Missing extraction leaves `artifact_path` null. Returned usage
is the original provider request's usage; cache hits do not consume another search.

Tavily is optional: neither PDF reading nor citation lookup needs it. It is useful
for project pages, code, and external discussion. No paid plan is required to try
its free allowance; check [current pricing](https://docs.tavily.com/documentation/api-credits)
for credits and limits. No search-engine scraping fallback is implemented.

## Storage and request handling

`research_data/` contains `cache/`, `papers/`, `web/`, and any agent-written
`reports/`. Returned artifact paths such as `/papers/text/<hash>.md` are relative
to this virtual root. For direct Python use, locate one with
`Path(workspace_dir) / artifact_path.lstrip("/")`.

Metadata, citation pages, and web results use a 24-hour cache. Writes are atomic.
Provider credentials are never included in cache keys or response artifacts.
The current design targets one local process; it does not coordinate multiple
processes or provide sandbox isolation.

Shared in-process limiters serialize arXiv requests at least three seconds apart
and Semantic Scholar requests at least one second apart. Transient failures have
at most two retries. `Retry-After` values up to 30 seconds are honored in retries;
longer waits are surfaced to the caller. HTTP responses are capped at 50 MB.
Expected provider failures raise `ProviderError` (arXiv uses `ArxivAPIError`), and
LangChain adapters turn those into actionable tool error messages.

## Structure and example research workflows

`providers/` contains external API adapters, `services/` contains workflows such
as PDF retrieval and extraction, `tools/` contains thin LangChain adapters, and
`core/` handles shared HTTP/cache behavior. `models.py` describes JSON-compatible
results, while `agent.py` binds the tools and filesystem to one root. The arXiv
provider and `paper-research` CLI are the metadata-search entry points.

| Request | Workflow |
| --- | --- |
| Explain a paper's method and limitations | Read pages, inspect complete text, cite version/page |
| Identify the work a method builds upon | Read seed, retrieve references, read selected arXiv neighbors |
| Find follow-up work | Retrieve citing papers, paginate, inspect relevant papers |
| Find recent papers and official code | Search arXiv, read papers, search web, inspect extracted project pages |

Related papers without arXiv IDs cannot be downloaded with the arXiv reader.
Provider gaps or missing extracted content should be reported, not filled with
unsupported claims. The example includes instructions for evidence-backed
answers and treating downloaded text as source material rather than instructions.

The tool accepts the official arXiv query syntax. Useful fields include `all`,
`ti` (title), `au` (author), `abs` (abstract), and `cat` (category). Clauses can
be combined with `AND`, `OR`, and `ANDNOT`.

The metadata client caps one request at 100 results. For pagination, pass `start`
to the direct `search` function. Request pacing is enforced by the shared client.

## Test

```bash
uv run python -m unittest discover -s tests
```

The default suite is offline and credential-free, including a scripted agent
that reads a paper artifact through the real filesystem backend. Fixtures are
synthetic provider responses and generated PDFs.

Live smoke tests are opt-in (environment variables must already be exported):

```bash
RUN_LIVE_ARXIV=1 uv run python -m unittest discover -s tests -p test_live.py
RUN_LIVE_CITATIONS=1 uv run python -m unittest discover -s tests -p test_live.py
RUN_LIVE_TAVILY=1 uv run python -m unittest discover -s tests -p test_live.py
```

The Tavily smoke test requires `TAVILY_API_KEY` and consumes a basic search credit.
