# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `src/paper_research/`. Keep external API adapters in
`providers/`, cross-provider or document workflows in `services/`, LangChain tool
wrappers in `tools/`, and shared HTTP/cache utilities in `core/`. `agent.py`
assembles the Deep Agents runtime, while `cli.py` implements the metadata-search
command. Tests live in `tests/`; recorded JSON and fixture notes belong in
`tests/fixtures/`. `examples/research.py` is the runnable agent example.

Keep providers usable without LangChain. Tool modules should validate the
model-facing schema, delegate to a provider or service, and convert expected
failures into `ToolException`. Store generated research data only under
`research_data/`, which is ignored by Git.

## Build, Test, and Development Commands

- `uv sync` installs locked runtime and development dependencies.
- `uv run ruff check .` checks Python style and common errors.
- `uv run ruff format .` formats Python files.
- `uv run python -m unittest discover -s tests -v` runs the offline suite.
- `uv build` creates the source distribution and wheel in `dist/`.
- `uv run paper-research 'cat:cs.AI AND all:agents'` exercises the search CLI.
- `uv run python examples/research.py --model PROVIDER:MODEL 'question'` runs the
  complete agent workflow.

## Coding Style & Naming Conventions

Use Python 3.11+, four-space indentation, type hints on public functions, and
short module docstrings. Follow `snake_case` for functions and modules,
`PascalCase` for classes and `TypedDict` models, and uppercase names for constants.
Prefer small provider functions and explicit JSON-compatible return structures.
Preserve one-based PDF page numbering and the citation-edge convention
`citing paper -> cited paper`.

## Testing Guidelines

Tests use the standard-library `unittest` framework. Name files `test_*.py` and
methods `test_<behavior>`. Normal tests must be deterministic, offline, and
credential-free; mock provider responses and use temporary workspaces. Add an
opt-in test to `tests/test_live.py` for real provider checks. Live tests use
`RUN_LIVE_ARXIV`, `RUN_LIVE_CITATIONS`, or `RUN_LIVE_TAVILY`; Tavily consumes a
search credit.

## Commit & Pull Request Guidelines

The repository has no commit history yet. Use concise, imperative subjects such
as `Add citation pagination validation`. Keep commits focused. Pull requests
should explain the behavior change, provider or cache implications, tests run,
and any new environment variables. Link relevant issues; include screenshots
only for notebook or future UI changes.

## Configuration & Security

Copy `.env.example` to `.env`; never commit credentials. Tavily requires
`TAVILY_API_KEY`, while `SEMANTIC_SCHOLAR_API_KEY` is optional. Do not place API
keys in cache keys, artifacts, fixtures, logs, or test output.
