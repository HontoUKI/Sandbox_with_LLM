# Request Path

This document describes how a user answer moves through the current prototype.

## CLI Flow

1. `main.py` asks the user a concrete question.
2. The user enters an answer.
3. `ContextManager.objectivity_score()` estimates whether the answer is concrete enough.
4. If the answer is too short or below `OBJECTIVITY_THRESHOLD`, the bot asks again.
5. Accepted answers are saved through `ContextManager.ingest_user_content()`.
6. The bot prints a short reflection and the objectivity score.
7. At the end, the bot prints a portrait built from accepted facts.

## Objectivity Score

The score is an integer from `0` to `100`.

Higher means the answer looks more like an observable fact:

- concrete action
- concrete situation
- concrete result
- less vague self-judgment

When Ollama is available, `src/llm.py` asks the model for a JSON score.

When Ollama is unavailable, `ContextManager` uses a small heuristic based on length, digits, and action markers.

## Extraction

`FactExtractor` creates a small normalized layer from user text:

- `objective_facts` - observable facts extracted from the content
- `search_query` - compact text used for vector search
- `objectivity_score` - score used when LLM scoring is available through the extractor

If Ollama is unavailable or returns invalid JSON, the extractor falls back to local rules.

## Content And Memory Write

Accepted answers are written as three JSONL layers.

Content record:

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

Memory record:

```json
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

## Retrieval

`ContextManager.vector_search(query)` does this:

1. extracts a compact search query
2. embeds the search query
3. loads content and memory records by ID
4. loads vector records
5. calculates cosine similarity
6. returns the highest scoring `MemoryMatch` items

`ContextManager.relevant_memories(query)` is still available as a compatibility method. It filters vector search to objective fact memory.

## Wrapper Retrieval

`ContextualLLM` uses vector search before prompt construction:

1. takes the user prompt or last chat message
2. sends it through the mini extractor
3. searches vectors across `content` and `memory`
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
