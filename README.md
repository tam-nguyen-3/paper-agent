# Paper Research Agent

Paper Research Agent is a local command-line project for finding and studying
academic papers. Give it a research question and a language model can choose from
four focused tools:

- search arXiv for papers and abstracts;
- download an arXiv PDF and read it page by page;
- follow a paper's references or find later papers that cite it; and
- optionally search the web for code, project pages, and other supporting sources.

The language model acts as the researcher: it decides which tool to use next,
compares the evidence it finds, and writes an answer with source locations. The
tools do the factual retrieval. This separation is the basic idea behind
"agentic" programming: instead of following one fixed sequence, the program lets
the model select the next action based on what it has learned so far.

Everything runs from the command line and stores downloaded or extracted material
under `research_data/`. No database or web server is required.

## Quick start

### 1. Install the prerequisites

You need Python 3.11 or newer, [`uv`](https://docs.astral.sh/uv/), and credentials
for a chat-model provider. The project includes the OpenAI integration; using a
different provider may require installing its LangChain integration package.

### 2. Install the project

From the repository root, run:

```bash
uv sync
```

### 3. Configure credentials

Create a local environment file:

```bash
cp .env.example .env
```

Add the API key required by your chosen chat-model provider using that provider's
documented environment-variable name. For example, an OpenAI model uses:

```dotenv
OPENAI_API_KEY=your-key-here
```

The agent cannot run without access to a model. The other keys are optional:

- `SEMANTIC_SCHOLAR_API_KEY` gives citation lookups dedicated provider capacity.
- `TAVILY_API_KEY` enables web searches for code and project pages.

Do not commit `.env`. The runnable example loads this file automatically; code
that imports the library directly must load its own environment.

### 4. Ask a research question

Replace `PROVIDER:MODEL` with the model identifier configured for your provider,
such as `openai:<model-name>`:

```bash
uv run python examples/research.py --model PROVIDER:MODEL \
  'Read arXiv:1706.03762v7 and explain its main method with page citations.'
```

Another useful prompt is:

```bash
uv run python examples/research.py --model PROVIDER:MODEL \
  'Find recent papers about self-improving agents and compare their approaches.'
```

The first run may take longer because PDFs and API results have not yet been
cached. Research artifacts are written to `research_data/` and reused where
possible on later runs.

## How a research workflow works

An agent is a language model in a loop with a small set of tools. For this project,
one loop looks like this:

```text
Your question
    |
    v
Model chooses a research action
    |
    +--> search arXiv ---------> paper titles and abstracts
    +--> read an arXiv PDF ----> text tied to physical PDF pages
    +--> inspect citations ----> references or later citing papers
    +--> search the web -------> code and project pages (optional)
    |
    v
Model reviews the new evidence
    |
    +--> needs more evidence? Choose another action
    |
    v
Answer with sources, limitations, and any coverage gaps
```

The model does not receive every paper at once. Search results are useful for
choosing candidates, but an abstract is not enough evidence for a detailed claim.
The agent can open promising PDFs, read relevant page ranges, and inspect the full
extracted text saved in the workspace. It can also branch outward through a
citation graph when the question calls for earlier foundations or later work.

The built-in instructions tell the model to distinguish what a source says from
its own interpretation, cite exact paper versions and physical PDF pages, and say
when extraction or provider coverage is incomplete. As with any model-generated
research, you should still verify important claims against the cited source.

### Common workflows

#### Explain one paper

1. Resolve the requested arXiv ID to a specific version.
2. Download the PDF and extract page-addressable text.
3. Read relevant sections and, when needed, search the complete text artifact.
4. Explain the method and limitations with version and page citations.

Example prompt:

```text
Read 1706.03762v7 and explain the architecture, training objective, and stated
limitations for a software engineer. Cite the PDF pages supporting each section.
```

#### Trace the ideas around a paper

1. Read the starting paper to understand the idea of interest.
2. Retrieve its references to find earlier work, or its citations to find later
   work.
3. Select relevant neighboring papers instead of treating citation count as a
   measure of quality.
4. Read the selected arXiv papers before comparing their claims.

Citation data can be incomplete, and some related papers do not have an arXiv
version that this project can download. The agent should report those gaps.

#### Survey a topic

1. Translate the question into one or more arXiv searches.
2. Use titles and abstracts to shortlist papers.
3. Read the strongest candidates and compare evidence from their full text.
4. Optionally follow citations to widen the survey.
5. Synthesize areas of agreement, differences, and unanswered questions.

This is an iterative survey rather than a systematic literature review: API
limits, search terms, and citation-provider coverage affect what it finds.

#### Find papers and their official code

1. Search arXiv and inspect the relevant papers.
2. If `TAVILY_API_KEY` is configured, search the web for official repositories or
   project pages.
3. Inspect the returned page content before claiming that a repository is
   official or implements the paper.
4. Cite both the paper and the inspected web URL.

Without a Tavily key, paper and citation research still works; the agent warns
that web research is unavailable.

## Search arXiv without an agent

If you only need metadata, you can use the simpler search command. It calls arXiv
directly and does not require a language model:

```bash
uv run paper-research 'cat:cs.AI AND all:"self improving agents"' \
  --max-results 5 --sort-by submittedDate
```

The result is JSON containing metadata and abstracts. This command does not read
PDFs, explore citations, or synthesize an answer.

## Use the Python API directly

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

## Create an agent in Python

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

Top-level imports `search_arxiv`, `read_arxiv_paper`, `search_web`, and
`get_citation_graph` are LangChain tool objects: call `.invoke({...})` or pass them
to an agent. For plain Python functions use the provider imports above.
Importing the direct search client does not import LangChain.

All tools must share the agent backend's workspace for artifact paths to work.
The factory handles that binding. For a custom agent, use
`paper_research.tools.build_tools(workspace_dir, web_enabled=True)` and configure a
`FilesystemBackend` with the same root and `virtual_mode=True`.

## Architecture

The package has four layers. `agent.py` assembles the Deep Agents runtime and a
shared filesystem; `tools/` exposes model-facing LangChain tools and translates
expected failures into `ToolException`; `services/` coordinates workflows that
span multiple operations; and `providers/` talks to external APIs. Shared cache,
HTTP retry, rate-limit, and artifact behavior lives in `core/`.

```text
User
  |
  v
Deep Agents runtime (agent.py) ------- shared FilesystemBackend
  |                                         |
  v                                         v
LangChain tools (tools/)               research_data/ artifacts
  |
  +-- search_arxiv -----------> arXiv provider ------------------+
  +-- read_arxiv_paper -------> paper reader service             |
  |                                +-- arXiv lookup               |
  |                                +-- PDF download/extraction    |
  +-- get_citation_graph -----> Semantic Scholar provider        |
  +-- search_web -------------> Tavily provider (optional)       |
                                                               v
                                             shared HTTP/cache (core/)
```

The tools complement rather than call one another: search finds candidate papers,
the reader turns a selected arXiv PDF into page-addressable evidence, the citation
graph expands from a known work, and web search finds non-arXiv material such as
code or project pages. The agent decides when to combine them. All artifact-producing
paths use the same workspace so the agent can inspect full text with its filesystem
tools after a provider returns a compact result.

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
`reports/`. Paper text uses its exact, versioned arXiv identifier, for example
`/papers/text/1706.03762v7.md`; legacy identifiers retain their category prefix,
as in `/papers/text/hep-th/9901001v2.md`. These paths are relative to the virtual
root. For direct Python use, locate one with
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

## arXiv query syntax

The search tool accepts the official arXiv query syntax. Useful fields include `all`,
`ti` (title), `au` (author), `abs` (abstract), and `cat` (category). Clauses can
be combined with `AND`, `OR`, and `ANDNOT`.

The metadata client caps one request at 100 results. For pagination, pass `start`
to the direct `search` function. Request pacing is enforced by the shared client.

## Run the tests

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
