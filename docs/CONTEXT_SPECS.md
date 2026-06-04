# Context Specs

This document defines the current memory and context format.

## Storage Directory

Default storage directory:

```text
user_data/
```

Files:

```text
user_data/memories.jsonl
user_data/vectors.jsonl
user_data/content.jsonl
```

All files are created automatically by `JsonlStorage`.

## Content Record

Each line in `content.jsonl` is one JSON object.

Required fields:

```json
{
  "id": "string uuid",
  "text": "raw or lightly normalized user content",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "user_content",
    "source": "user_input",
    "prompt": "source question or null",
    "objectivity_score": 87,
    "search_query": "compact vector search text",
    "extracted_fact_count": 1
  }
}
```

This layer keeps the original accepted user content before fact extraction.

## Memory Record

Each line in `memories.jsonl` is one JSON object.

Required fields:

```json
{
  "id": "string uuid",
  "text": "string",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "objective_fact",
    "objectivity_score": 87,
    "is_objective": true,
    "prompt": "source question or null",
    "source_content_id": "content uuid or null"
  }
}
```

### Meta Fields

`kind`

Current value is `objective_fact`.

`objectivity_score`

Integer from `0` to `100`.

`is_objective`

Boolean shortcut. Current rule:

```text
objectivity_score >= 50
```

`prompt`

The question that produced the fact. This is useful for later review and debugging.

`source_content_id`

The `content.jsonl` record that produced this objective fact, when available.

## Vector Record

Each line in `vectors.jsonl` is one JSON object.

Required fields:

```json
{
  "id": "same uuid as memory record",
  "text": "same or equivalent source text",
  "embedding": [0.0, 1.0, 0.0],
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "source": "ollama",
    "record_type": "memory",
    "memory_kind": "objective_fact"
  }
}
```

### Vector Source

`source` can be:

- `ollama` - embedding came from Ollama `/api/embeddings`
- `local_hash` - fallback vector generated locally

The fallback exists so tests and CLI mode work without an LLM server.

`record_type` can be:

- `content` - vector points to a `content.jsonl` record
- `memory` - vector points to a `memories.jsonl` record

## Retrieval Contract

Retrieval is based on `ContextManager.vector_search()` and cosine similarity between:

- extracted query embedding
- stored vector embeddings

Returned items use `MemoryMatch`:

```python
MemoryMatch(
    text="I fixed a broken script alone and shipped it",
    score=0.37,
    meta={"objectivity_score": 87},
    record_type="memory",
    record_id="uuid"
)
```

`ContextManager.relevant_memories()` is a compatibility filter over `vector_search()` that returns only `memory` records.

## Prompt Context Contract

The prompt context should include only factual memory:

```text
User memory. Use only as factual context. Do not flatter, invent, or add unsupported traits:
- [memory] I fixed a broken script alone and shipped it | objectivity=87 | relevance=0.37
- [content] I fixed a broken script alone and shipped it | objectivity=87 | relevance=0.37

User request:
Help me remember objective evidence that I can solve technical problems.
```

The prompt must not include:

- broken encoding artifacts
- unrelated memories above more relevant ones
- invented user traits
- generic praise presented as fact

## Test Coverage

Current tests verify:

- JSONL files are created automatically
- memory and vector records share the same ID
- content and vector records share the same ID
- content ingestion extracts objective facts
- `objectivity_score` is stored in memory meta
- local hash vectors are used without Ollama
- retrieval returns relevant memory
- vector search can return both content and memory layers
- final prompt log is generated in `cache/final_prompt.log`
- final prompt has no dirty encoding artifacts
