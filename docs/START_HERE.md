# Start Here

This document is the quick entry point for developers, reviewers, and future Codex sessions.

## Project Goal

The project is a prototype dialogue bot named **Daria**. She has empathetic conversations with users, listens to their stories, and then reveals the real strengths they may have underestimated.

Key principles:

- The dialogue is **natural and friend-like**, not an interview
- Assessment happens in the **final summary**, not during conversation
- Daria is **extremely honest** and does not flatter or minimize real limitations
- The bot extracts concrete facts but focuses on revealing **implicit capabilities** users may have downplayed
- Observations about strengths are grounded in what the user actually demonstrated

## Current Runtime

The current app is a CLI:

```powershell
python main.py
```

Ollama is required for dialogue generation and summaries. The bot is LLM-first and has no fallback mode.

The CLI is open-ended just-chatting. Regular turns store user/assistant messages
for recent-history and vector support. Fact extraction runs when the user types
`/summary`, not on every turn.

## Important Files

```text
main.py                 CLI dialogue, Daria persona, summary generation
src/llm.py              Ollama wrapper
src/context/storage.py  JSONL files for memory and vectors
src/context/extractor.py fact extraction + implicit strength detection
src/context/dialogue_intent.py response tone and intent classification
src/context/build_prompt_little_director.py question direction by objectivity level
src/context/manager.py  objectivity scoring, memory writes, retrieval
src/context/wrapper.py  prompt construction with memory context
tests/                  unittest suite
```

## Local Data

Runtime memory is written to:

```text
user_data/content.jsonl      (all dialogue messages)
user_data/memories.jsonl     (extracted objective facts)
user_data/summaries.jsonl    (final 5-turn summaries)
user_data/vectors.jsonl      (embeddings for search)
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
python -m py_compile main.py src/llm.py src/context/*.py tests/test_context_memory.py
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run a real Ollama scenario replay with transcript artifacts:

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/supportive_conversation.json --out-dir cache/scenario_runner
```

Scenario replays follow the Maria runner shape: JSON scenario in, turn-by-turn
transcript JSON and Markdown review summary out. The supportive scenario checks
soft support, grounded strength reflection, recent-history windowing, and vector
retrieval dedupe.

## Dialogue Flow

1. Bot greets the user as Daria and sets warm expectations
2. For each turn:
   - Daria asks a natural question (driven by `build_prompt_little_director`)
   - User answers
   - Objectivity score is computed internally but **not shown to user**
   - Bot responds as just-chatting, with a more alive voice, pauses, and occasional mild profanity when appropriate
   - User and assistant messages are stored; facts are not extracted yet
3. When the user types `/summary`, bot builds a summary that:
   - Reviews what happened
   - **Highlights real strengths user demonstrated or underestimated**
   - Notes where user is being too harsh on themselves
   - Suggests development directions (not criticisms)
   - Runs extractor over the dialogue and stores objective memories

## Review Checklist

- Does Daria sound like a friend, not a bot?
- Are objective scores computed internally but not reported during dialogue?
- Is the summary the primary place where strengths are highlighted?
- Does the summary look for implicit capabilities, not just stated facts?
- Are all dialogue turns stored (boundary, deprecation, conversation)?
- Are only objective facts (not all dialogue) stored as memories?
- Does `meta.objectivity_score` exist for stored content?
- Does vector storage align with memory IDs?
- Does question generation adapt to objectivity level?
- Are broken encoding artifacts avoided?
