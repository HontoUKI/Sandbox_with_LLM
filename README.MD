# Dialogue Bot: Daria

![Prototype](https://img.shields.io/badge/status-prototype-orange)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20required-blue)
[![CI](https://github.com/HontoUKI/Sandbox_with_LLM/actions/workflows/ci.yml/badge.svg?branch=self-esteem)](https://github.com/HontoUKI/Sandbox_with_LLM/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-green)

## For Developers And Reviewers

Start with [docs/START_HERE.md](docs/START_HERE.md). It gives the fastest overview of the runtime, flow, storage, tests, and review checklist.

Deeper technical notes:

- [docs/REQUEST_PATH.md](docs/REQUEST_PATH.md) - how user answers flow through the system and how the summary reveals strengths.
- [docs/CONTEXT_SPECS.md](docs/CONTEXT_SPECS.md) - memory, vector, and metadata formats.

## What Is This Project?

This is a prototype CLI dialogue bot named **Daria**. She conducts natural, empathetic conversations with users, helping them open up about their experiences. Then, in a final summary, she reveals the real strengths they may have underestimated.

### The Problem

People often downplay their own achievements, skills, and judgment because emotions feel more vivid than facts. They focus on what went wrong and minimize what they actually accomplished.

### The Solution

Daria:
1. **Listens without judgment** during the dialogue (no assessment shown)
2. **Extracts concrete facts** and implicit capabilities from what users share
3. **Reveals strengths honestly** in the final summary—not flattery, but real observations
4. **Notes self-minimization** when she sees the user being too harsh

The dialogue feels like talking to a friend. The summary is where the honest reflection happens.

## Key Features

- **Natural dialogue**: Daria sounds like a friend, not a bot or interviewer
- **Implicit strength detection**: The system recognizes capabilities users may have downplayed
- **No mid-dialogue scoring**: Objectivity is computed internally but only used to guide questions, never shown to the user
- **Strength-focused summary**: The final summary explicitly highlights what the user demonstrated or overlooked
- **Honest without flattery**: Daria does not flatter or minimize real limitations
- **Memory-backed**: All dialogue is stored as structured JSONL for future context

## Requirements

- Python 3.11+
- Ollama with a language model (required for dialogue generation and summaries)

Example models: `llama3`, `mistral`, `neural-chat`, etc.

The bot is LLM-first. There is no fallback mode if Ollama is unavailable.

## Setup

```powershell
python -m venv .local
.\.local\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3
OLLAMA_EMBED_MODEL=nomic-embed-text
QUESTION_COUNT=5
OBJECTIVITY_THRESHOLD=50
```

## Running The Bot

`requirements.txt` is currently empty because the prototype uses only the Python standard library.

## Configuration

Edit `.env` after copying [.env.example](.env.example):

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

Daria now runs as open-ended just-chatting. Ordinary turns store user and
assistant messages for recent-history and vector support, but do not extract
facts immediately. Type `/summary` when you want the summary; that command
generates the summary and runs fact extraction for memory. Type `/exit` to quit.

Accepted user content and extracted facts are stored locally in:

- `user_data/content.jsonl`
- `user_data/memories.jsonl`
- `user_data/summaries.jsonl`
- `user_data/vectors.jsonl`

These files are ignored by git because they contain user-specific memory.

## Tests

```powershell
python -m unittest discover -s tests
```

## Integration Scenarios

`tools.scenario_runner` uses the real Ollama configured in `.env`. It is meant
for module-level smoke checks after local changes, while unit tests keep using
fake or mocked LLMs.

The runner includes a supportive conversation scenario where the user talks
about fatigue and self-doubt, Daria keeps the last 5 stored messages as
immediate history, and vector search adds relevant older context without
duplicating the recent history window.

```powershell
python -m tools.scenario_runner
```

Maria-style replay from a scenario JSON writes a transcript JSON and Markdown
review summary:

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/supportive_conversation.json --out-dir cache/scenario_runner
```

To keep scenario JSONL output for inspection:

```powershell
python -m tools.scenario_runner --data-dir cache/scenario_runner
```

Tests also write the final built prompt to:

```text
cache/final_prompt.log
```

Open that file after tests to check that the LLM prompt is not polluted by broken encoding, irrelevant memory, or unsupported claims.

## CI

GitHub Actions runs on push and pull request for:

- Ubuntu and Windows
- Python 3.11 and 3.12
- `py_compile`
- `unittest`

## File Structure

```text
main.py                 CLI entry point
src/llm.py              Ollama HTTP wrapper
src/context/storage.py  JSONL storage
src/context/extractor.py objective fact and search query extraction
src/context/build_prompt_little_director.py next-question direction from objectivity meta
src/context/manager.py  memory write/retrieval logic
src/context/wrapper.py  LLM wrapper with memory injection
tools/scenario_runner/  real Ollama integration scenarios
tests/                  unittest suite
docs/                   project notes and implementation specs
```

## What Can You Do With This Code?

Try it yourself. Use it as a small experiment in self-dialogue, fact retrieval, and LLM-assisted reflection.

It is not therapy, a diagnosis tool, or a replacement for professional help. It is a prototype for making self-reflection less vague and more evidence-based.

## License

MIT. See [LICENSE](LICENSE).
