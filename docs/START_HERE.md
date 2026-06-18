# Start Here

This document is the quick entry point for developers, reviewers, and future
Codex sessions.

## Project Goal

The project is a prototype CLI little-agent planner named **Lisa**. Lisa helps a
user clarify rough project ideas by asking simple, naive, technically useful
questions. The goal is not emotional support; the goal is objective idea
evaluation and implementation planning.

Key principles:

- Lisa sounds like a curious teenager: direct, simple, and skeptical when needed.
- Ordinary dialogue is LLM-first. There are no local canned response fallbacks.
- Assessment happens in `/summary`, not as visible turn-by-turn scoring.
- `/summary` evaluates the idea, risks, missing assumptions, and implementation steps.
- `/packing` turns the latest summary and conversation into a handoff Markdown file.

## Current Runtime

Run the CLI:

```powershell
python main.py
```

Ollama is required for dialogue, summary, packing field extraction, and
embeddings. `/summary` can also use multi-step DuckDuckGo research and may take
longer.

## Important Files

```text
main.py                                      CLI commands, Lisa persona, summary, packing
src/llm.py                                   Ollama wrapper
src/context/storage.py                       JSONL files for content, memories, summaries, vectors
src/context/extractor.py                     idea extraction + four score axes
src/context/build_prompt_little_director.py  question direction by cohesion
src/context/manager.py                       memory writes, summaries, web research analysis
src/context/wrapper.py                       prompt construction with memory context
docs/HANDOFF_TEMPLATE.md                     template filled by /packing
tools/scenario_runner/                       real Ollama scenario runner
tests/                                       unittest suite
```

`src/context/dialogue_intent.py` was removed. Do not reintroduce local response
tone fallbacks unless the product direction explicitly changes.

## Local Data

Runtime memory is written to:

```text
user_data/content.jsonl      dialogue messages
user_data/memories.jsonl     extracted idea statements after summary
user_data/summaries.jsonl    dialogue summaries and web research analyses
user_data/vectors.jsonl      embeddings for search
```

Packing output is written to:

```text
.local/*_handoff.md
```

## Development Commands

Compile check:

```powershell
python -m py_compile main.py src\llm.py src\context\build_prompt_little_director.py src\context\extractor.py src\context\manager.py src\context\storage.py src\context\wrapper.py tools\scenario_runner\__main__.py tests\test_context_memory.py
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run the real Ollama Excel parser scenario:

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/excel_parser_idea.json --out-dir cache/scenario_runner
```

## Dialogue Flow

1. Lisa asks a short first question.
2. For each user answer:
   - the extractor computes idea scores;
   - the answer and Lisa's response are stored as dialogue content;
   - no objective memories are written yet;
   - the next question is guided by cohesion.
3. `/summary`:
   - warns the user that web research can take time;
   - asks the LLM to propose several search queries;
   - searches DuckDuckGo and records result titles/URLs;
   - fetches text from a few pages for analysis;
   - stores only LLM analysis plus source titles/URLs, not raw page content;
   - writes the idea summary and extracts memory facts from the dialogue.
4. `/packing`:
   - uses the latest summary if the dialogue has not changed;
   - asks the LLM for structured handoff fields;
   - fills `docs/HANDOFF_TEMPLATE.md`;
   - writes the result to `.local/` or the scenario artifact directory.

## Review Checklist

- Does Lisa ask one useful question rather than lecture?
- Does `/summary` criticize weak assumptions when needed?
- Does `/summary` avoid unsupported encouragement?
- Does web research use query planning, link collection, page analysis, then summary?
- Does web research store analysis only, not raw page content?
- Does `/packing` produce a concrete project name, goal, risks, and next steps?
- Are idea scores present in stored meta?
- Are broken encoding artifacts avoided in generated files?
- Do unit tests and at least one real Ollama scenario pass?
