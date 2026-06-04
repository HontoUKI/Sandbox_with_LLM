# Objective Self-Esteem Bot

![Prototype](https://img.shields.io/badge/status-prototype-orange)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20optional-blue)
![CI](https://img.shields.io/badge/CI-planned-lightgrey)
![License](https://img.shields.io/badge/license-MIT%20planned-lightgrey)

> License note: I plan to use MIT for this project. `LICENSE` and git initialization are planned for a later step.

## For Developers And Reviewers

Start with [docs/START_HERE.md](docs/START_HERE.md).

The deeper technical notes are split into:

- [docs/REQUEST_PATH.md](docs/REQUEST_PATH.md) - how a user answer moves through the system.
- [docs/CONTEXT_SPECS.md](docs/CONTEXT_SPECS.md) - memory, vectors, and objective fact metadata.

## What Is This Project?

This is a CLI prototype for a self-dialogue bot that helps the user look at themselves through observable facts.

The core idea is simple: instead of asking the model to flatter the user or produce generic encouragement, the bot asks for concrete episodes, checks whether they are objective enough, stores them as memory, and later uses those facts as context.

The context layer keeps accepted user content, extracts objective facts from it, creates vectors for both layers, and uses vector search before building the final LLM prompt.

It is meant to work like a mirror for decisions, skills, effort, and patterns the user may routinely ignore.

## Why I Am Making This

People often underestimate their own achievements, skills, and judgment because they remember feelings more easily than facts.

This bot is an attempt to build a colder, more grounded view from the side: not "you are great", but "this happened, you did this, and it counts as evidence".

## Requirements

- Python 3.11+
- Optional: Ollama for LLM generation, objectivity scoring, and embeddings

You can use local Ollama models or Ollama cloud models, for example `gemma3:12b-cloud`, if they are available in your Ollama setup.

The project still runs without Ollama. In that mode it uses heuristic objectivity scoring and local hash vectors.

## Setup

```powershell
python -m venv .local
.\.local\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`requirements.txt` is currently empty because the prototype uses only the Python standard library.

## Configuration

Edit `.env` after copying [.env.example](.env.example):

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
OLLAMA_TIMEOUT=2.0
CONTEXT_LENGTH=8192
OBJECTIVITY_THRESHOLD=45
USER_NAME=User
```

## Run

```powershell
python main.py
```

Accepted user content and extracted facts are stored locally in:

- `user_data/content.jsonl`
- `user_data/memories.jsonl`
- `user_data/vectors.jsonl`

These files are ignored by git because they contain user-specific memory.

## Tests

```powershell
python -m unittest discover -s tests
```

Tests also write the final built prompt to:

```text
cache/final_prompt.log
```

Open that file after tests to check that the LLM prompt is not polluted by broken encoding, irrelevant memory, or unsupported claims.

## File Structure

```text
main.py                 CLI entry point
src/llm.py              Ollama HTTP wrapper
src/context/storage.py  JSONL storage
src/context/extractor.py objective fact and search query extraction
src/context/manager.py  memory write/retrieval logic
src/context/wrapper.py  LLM wrapper with memory injection
tests/                  unittest suite
docs/                   project notes and implementation specs
```

## What Can You Do With This Code?

Try it yourself. Use it as a small experiment in self-dialogue, fact retrieval, and LLM-assisted reflection.

It is not therapy, a diagnosis tool, or a replacement for professional help. It is a prototype for making self-reflection less vague and more evidence-based.
