# Request Path

This document describes how a user answer moves through the current prototype.

## CLI Flow

1. `main.py` greets the user as Daria and explains the dialogue approach.
2. For each turn:
   - Daria asks a natural question guided by `build_prompt_little_director()`
   - The user enters an answer
   - `ContextManager.objectivity_score()` estimates how concrete the answer is
   - `dialogue_intent.classify_user_message()` decides the intent: boundary, self-deprecation, positive signal, or general conversation
   - The bot generates a **warm, friend-like response** based on intent (responses do NOT show objectivity scores)
   - All content (user message and bot response) is saved to `content.jsonl` with metadata
   - If the answer contains objective facts, they are extracted and saved to `memories.jsonl`
3. After `QUESTION_COUNT` turns, a final summary is built that:
   - Describes what happened in the conversation
   - **Highlights real strengths the user demonstrated** (even if they downplayed them)
   - Notes where the user is being too harsh on themselves
   - Suggests development directions
4. Summary and all turn data are saved to `summaries.jsonl`

The CLI is LLM-first. Scripted fallback questions are intentionally disabled.

## Little Director

`src/context/build_prompt_little_director.py` turns objectivity score into a next-question strategy.

Three modes:

- **concrete_grounding** (score < 60): Ask for one concrete moment or example to make vague claims real. Patient, not pressuring.
- **fact_exploration** (score 60-80): Explore one missing detail: timing, other people, what changed, why it mattered. Sound curious.
- **context_deepening** (score >= 80): Explore thinking or context around the concrete fact. What was important? What was learned?

This keeps the conversation natural while progressively building a fuller picture.

## Objectivity Score

The score is an integer from `0` to `100`.

Higher means the answer looks more like an observable fact:

- concrete action
- concrete situation
- concrete result
- less vague self-judgment or abstract traits

When Ollama is available, `src/llm.py` asks the model for a JSON score.

When Ollama is unavailable, `ContextManager` uses a small heuristic based on text length, digit presence, and action markers.

**Important**: The score is **computed internally** but **not shown to the user during dialogue**. It shapes question strategy only.

## Extraction

`FactExtractor` creates a normalized layer from user text:

- `objective_facts` - observable facts extracted from the content
- `search_query` - compact text for vector search
- `objectivity_score` - score for the answer

The extractor is enhanced to identify **implicit capabilities**:
- If user says "I failed at X", extractor may note they actually demonstrated Y
- Looks for resilience, problem-solving, communication, learning markers
- Does not invent; only notes what is actually demonstrated

If Ollama is unavailable or returns invalid JSON, the extractor falls back to local rules.

## Response Tones

Instead of showing meta-analysis, the bot responds based on intent:

- **boundary** ("stop", "don't push"): Respect fully, ask soft follow-up
- **self_deprecation** ("I'm bad", "I'm useless"): Acknowledge pain, ask for one concrete episode to understand
- **positive_signal** ("I did this"): Show genuine interest, help clarify what actually happened
- **conversation** (general dialogue): Listen, ask what's important about this
- **objective_fact** (concrete answer): Acknowledge, move to next question naturally

All responses sound like a friend listening, not an evaluator.

## Content And Memory Write

Accepted answers and summaries are written as JSONL records with metadata.

Example user content record:

```json
{
  "id": "uuid",
  "text": "I fixed a broken script alone and shipped it",
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "kind": "user_content",
    "source": "user_input",
    "prompt": "What did you solve by yourself?",
    "objectivity_score": 87,
    "search_query": "i fixed a broken script alone and shipped it",
    "extracted_fact_count": 1
  }
}
```

Example extracted memory record:

```json
{
  "id": "uuid",
  "text": "Fixed a broken script and shipped it independently",
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "kind": "objective_fact",
    "objectivity_score": 87,
    "is_objective": true,
    "prompt": "What did you solve by yourself?",
    "source_content_id": "user content uuid"
  }
}
```

Example summary record with strength analysis:

```json
{
  "id": "uuid",
  "text": "In this conversation... [what I noticed about you]... [where you underestimated yourself]...",
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "kind": "dialogue_summary",
    "turn_count": 5,
    "summary_type": "strength_focused"
  }
}
```
{
  "id": "uuid",
  "text": "I fixed a broken script alone and shipped it",
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "kind": "objective_fact",
    "objectivity_score": 87,
    "is_objective": true,
    "prompt": "What did you solve by yourself?",
    "source_content_id": "content uuid"
  }
}
```

Vector record:

```json
{
  "id": "same uuid",
  "text": "I fixed a broken script alone and shipped it",
  "embedding": [0.0, 1.0, 0.0],
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "source": "local_hash",
    "record_type": "memory",
    "memory_kind": "objective_fact"
  }
}
```

Summary record:

```json
{
  "id": "uuid",
  "text": "User said... You answered... Meta objectivity...",
  "created_at": "2026-06-04T00:00:00+00:00",
  "meta": {
    "kind": "dialogue_summary",
    "source": "five_turn_dialogue",
    "turn_count": 5
  },
  "turns": [
    {
      "question": "What did you solve?",
      "user_answer": "I fixed a broken script.",
      "bot_answer": "This is concrete.",
      "objectivity_score": 87
    }
  ]
}
```

## Retrieval

`ContextManager.vector_search(query)` does this:

1. extracts a compact search query
2. embeds the search query
3. loads content, memory, and summary records by ID
4. loads vector records
5. calculates cosine similarity
6. returns the highest scoring `MemoryMatch` items

`ContextManager.relevant_memories(query)` is still available as a compatibility method. It filters vector search to objective fact memory.

## Wrapper Retrieval

`ContextualLLM` uses vector search before prompt construction:

1. takes the user prompt or last chat message
2. sends it through the mini extractor
3. searches vectors across `content`, `memory`, and `summary`
4. injects the best matches into the LLM context

## Prompt Construction

`ContextualLLM.build_prompt_for_log(prompt)` builds the final prompt without calling the LLM.

That final prompt includes:

- factual memory context
- objectivity scores
- relevance scores
- the user request

Tests write this prompt to:

```text
cache/final_prompt.log
```

This is the main inspection point for checking that context injection stays clean.
