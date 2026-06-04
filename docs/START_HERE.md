# Start Here

This document is the quick entry point for developers, reviewers, and future Codex sessions.

## Project Goal

The project is a prototype self-dialogue bot. It tries to improve self-assessment by asking the user for concrete, observable facts about themselves.

The bot should avoid generic praise. It should work with evidence:

- what happened
- what the user did
- what result or pattern can be observed
- how objective that fact is

## Current Runtime

The current app is a CLI:

```powershell
python main.py
```

Ollama is optional. If it is not running, the project falls back to heuristic scoring and local hash vectors.

## Important Files

```text
main.py                 CLI dialogue and env loading
src/llm.py              Ollama wrapper
src/context/storage.py  JSONL files for memory and vectors
src/context/extractor.py mini extractor for facts and search queries
src/context/build_prompt_little_director.py next-question direction from objectivity meta
src/context/manager.py  objectivity scoring, memory writes, retrieval
src/context/wrapper.py  prompt construction with memory context
tests/                  unittest suite
```

## Local Data

Runtime memory is written to:

```text
user_data/content.jsonl
user_data/memories.jsonl
user_data/summaries.jsonl
user_data/vectors.jsonl
```

These files are intentionally ignored by git.

Test prompt logs are written to:

```text
cache/final_prompt.log
```

This file is also ignored by git.

## Development Commands

Compile check:

```powershell
python -m py_compile main.py src/llm.py src/context/storage.py src/context/manager.py src/context/wrapper.py tests/test_context_memory.py
```

Tests:

```powershell
python -m unittest discover -s tests
```

## Review Checklist

- Does the bot ask for facts, not vague traits?
- Is user memory written only to `user_data/`?
- Does raw user content go to `content.jsonl` before extracted facts are saved?
- Does the 5-turn summary go to `summaries.jsonl`?
- Does `meta.objectivity_score` exist for stored facts?
- Does vector storage stay aligned with memory IDs?
- Does wrapper context come from vector search, not a hard-coded memory dump?
- Does question generation use the little director objectivity mode?
- Does `cache/final_prompt.log` contain only relevant memory?
- Does the prompt avoid broken encoding artifacts?
