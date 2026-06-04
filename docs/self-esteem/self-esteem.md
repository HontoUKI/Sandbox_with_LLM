# self-esteem

Mirrored from the `self-esteem` branch README. Preview includes sanitized `tools.scenario_runner` output captured during branch audit.

## Dialogue Bot: Daria

![Prototype](https://img.shields.io/badge/status-prototype-orange)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20required-blue)
[![CI](https://github.com/HontoUKI/Sandbox_with_LLM/actions/workflows/ci.yml/badge.svg?branch=self-esteem)](https://github.com/HontoUKI/Sandbox_with_LLM/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-green)

## For Developers And Reviewers

Start with `docs/START_HERE.md` on the `self-esteem` branch. It gives the fastest overview of the runtime, flow, storage, tests, and review checklist.

Deeper technical notes on the prototype branch:

- `docs/REQUEST_PATH.md` - how user answers flow through the system and how the summary reveals strengths.
- `docs/CONTEXT_SPECS.md` - memory, vector, and metadata formats.

## What Is This Project?

This is a prototype CLI dialogue bot named **Daria**. She conducts natural, empathetic conversations with users, helping them open up about their experiences. Then, in a final summary, she reveals the real strengths they may have underestimated.

### The Problem

People often downplay their own achievements, skills, and judgment because emotions feel more vivid than facts. They focus on what went wrong and minimize what they actually accomplished.

### The Solution

Daria:

1. **Listens without judgment** during the dialogue (no assessment shown)
2. **Extracts concrete facts** and implicit capabilities from what users share
3. **Reveals strengths honestly** in the final summary - not flattery, but real observations
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

Daria runs as open-ended just-chatting. Ordinary turns store user and assistant messages for recent-history and vector support, but do not extract facts immediately. Type `/summary` when you want the summary; that command generates the summary and runs fact extraction for memory. Type `/exit` to quit.

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

`tools.scenario_runner` uses the real Ollama configured in `.env`. It is meant for module-level smoke checks after local changes, while unit tests keep using fake or mocked LLMs.

The runner includes a supportive conversation scenario where the user talks about fatigue and self-doubt, Daria keeps the last 5 stored messages as immediate history, and vector search adds relevant older context without duplicating the recent history window.

```powershell
python -m tools.scenario_runner
```

Replay from a scenario JSON writes a transcript JSON and Markdown review summary:

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/supportive_conversation.json --out-dir cache/scenario_runner
```

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

## Preview: scenario_runner

Captured during the `self-esteem` branch audit before creating this hub branch. Local machine paths and generated conversational text are intentionally redacted.

```text
scenario_runner: data_dir=<temp>
PASS ollama_health (1.57s): chat_ok chars=32, embed_dims=768
PASS generated_question (2.77s): first=<generated text>; follow_up=<generated text>
PASS objective_fact_flow (3.30s): score=85, content=2, memories=0
PASS boundary_flow (3.11s): score=0, content=2, memories=0
PASS summary_flow (9.92s): summary_chars=988
PASS intent_responses_are_clean (0.00s): checked=4
PASS supportive_conversation_flow (24.41s): turns=3, recent=5, support_chars=1022, summary_chars=1169
PASS supportive_conversation_json (48.41s): artifact=<scenario transcript json>
scenario_runner: all 8 scenarios passed
```

## License

MIT. See `LICENSE`.
