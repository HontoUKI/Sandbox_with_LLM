# Little-agent-planner: Lisa

![Prototype](https://img.shields.io/badge/status-prototype-orange)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20required-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## What Is This Project?

Lisa is a prototype CLI little-agent planner. She talks through early ideas with
the user, asks naive but pointed questions, and helps turn vague intention into
an implementation-shaped brief.

Her base character is a curious teenager: direct, simple, sometimes skeptical,
and focused on making the user explain the idea clearly.

## Current Behavior

- Ordinary turns are LLM-first. There are no local response fallbacks.
- Lisa stores user and assistant dialogue in JSONL for recent-history and vector context.
- The extractor scores each idea turn on four 0-100 axes:
  - `cohesion_score`
  - `complexity_score`
  - `technicality_score`
  - `feasibility_score`
- `/summary` produces an objective idea review: weak assumptions, risks,
  implementation steps, and difficulty estimates.
- `/summary` may run multi-step web research to improve evaluation. Lisa first
  asks the LLM to propose search queries, then searches DuckDuckGo, fetches a
  few pages, analyzes them, and only then writes the summary. This can take
  longer.
- Web research is stored only as compact analysis plus source titles/URLs in
  `summaries.jsonl`; raw site content is not stored.
- `/packing` creates a project handoff Markdown file from the latest summary and
  dialogue, using [docs/HANDOFF_TEMPLATE.md](docs/HANDOFF_TEMPLATE.md).

## Requirements

- Python 3.11+
- Ollama with a chat model and embedding model
- Network access for `/summary` web research

The bot is LLM-first. If Ollama is unavailable, dialogue and summaries fail
instead of using canned local replies.

## Setup

```powershell
python -m venv .local
.\.local\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Example `.env`:

```env
OLLAMA_CHAT=http://127.0.0.1:11434/api/chat
OLLAMA_EMBED=http://127.0.0.1:11434/api/embeddings
OLLAMA_MODEL=gemma3:4b
EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT=120.0
CONTEXT_LENGTH=4096
OBJECTIVITY_THRESHOLD=50
QUESTION_COUNT=5
USER_NAME=User
```

## Run

```powershell
python main.py
```

Commands:

- `/summary` - objective idea evaluation, with optional web research.
- `/packing` - writes a handoff Markdown file to `.local/`.
- `/exit` or `/quit` - quit.

Runtime data is stored locally:

- `user_data/content.jsonl`
- `user_data/memories.jsonl`
- `user_data/summaries.jsonl`
- `user_data/vectors.jsonl`

These files are ignored by git.

## Tests

```powershell
python -m unittest discover -s tests
```

## Integration Scenarios

`tools.scenario_runner` uses the real Ollama configured in `.env`.

Run all scenarios:

```powershell
python -m tools.scenario_runner
```

Replay the Excel parser idea scenario and write transcript artifacts:

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/excel_parser_idea.json --out-dir cache/scenario_runner
```

The scenario includes `/summary` and `/packing`; the packing handoff is written
under the scenario artifact directory.

An example handoff generated from that scenario is committed at:

```text
example/excel-to-json-parser_handoff.md
```

## File Structure

```text
main.py                                      CLI entry point, commands, summary, packing
src/llm.py                                   Ollama HTTP wrapper
src/context/storage.py                       JSONL storage
src/context/extractor.py                     idea extraction and four score axes
src/context/build_prompt_little_director.py  next-question direction by cohesion
src/context/manager.py                       memory writes, summaries, research analysis
src/context/wrapper.py                       prompt construction with memory context
tools/scenario_runner/                       real Ollama integration scenarios
tests/                                       unittest suite
docs/                                        project notes and templates
example/                                     generated handoff example
```

## Notes

This is a prototype for idea clarification and implementation planning. It is
not a therapy tool, diagnosis tool, or replacement for professional advice.

## License

MIT. See [LICENSE](LICENSE).
