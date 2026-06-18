# Context Specs

This document defines the current memory and context format for Lisa.

## Storage Directory

Default storage directory:

```text
user_data/
```

Files:

```text
user_data/content.jsonl
user_data/memories.jsonl
user_data/summaries.jsonl
user_data/vectors.jsonl
```

All files are created automatically by `JsonlStorage`.

## Idea Scores

Idea turns use four 0-100 scores:

```json
{
  "cohesion_score": 80,
  "complexity_score": 70,
  "technicality_score": 33,
  "feasibility_score": 70
}
```

`objectivity_score` remains as a compatibility alias for `cohesion_score`.

## Content Records

Each line in `content.jsonl` is one JSON object. Dialogue content is stored for
recent-history and vector retrieval.

```json
{
  "id": "string uuid",
  "text": "assistant or user message",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "dialogue_message",
    "source": "dialogue or assistant_response",
    "role": "user or assistant",
    "intent": "idea_turn or idea_turn_response",
    "prompt": "source question or null",
    "bot_response": "assistant answer when stored on a user message or null",
    "linked_content_id": "related content uuid or null",
    "objectivity_score": 80,
    "idea_scores": {
      "cohesion_score": 80,
      "complexity_score": 70,
      "technicality_score": 33,
      "feasibility_score": 70
    },
    "search_query": "compact vector search text",
    "extracted_fact_count": 0
  }
}
```

Ordinary turns do not create memories. They only create content and vector
records.

## Memory Records

Memory records are created after `/summary`, when the dialogue is extracted into
idea statements.

```json
{
  "id": "string uuid",
  "text": "short idea statement, goal, assumption, decision, or constraint",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "objective_fact",
    "objectivity_score": 80,
    "idea_scores": {
      "cohesion_score": 80,
      "complexity_score": 70,
      "technicality_score": 33,
      "feasibility_score": 70
    },
    "is_objective": true,
    "prompt": "source question or null",
    "source_content_id": "summary uuid or null"
  }
}
```

The `objective_fact` name is retained for compatibility. New code should treat
these records as idea statements rather than self-esteem evidence.

## Summary Records

`summaries.jsonl` stores both dialogue summaries and web research analyses.

Dialogue summary:

```json
{
  "id": "string uuid",
  "text": "objective idea review",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "dialogue_summary",
    "source": "five_turn_dialogue",
    "turn_count": 2
  },
  "turns": [
    {
      "question": "string",
      "user_answer": "string",
      "bot_answer": "string",
      "intent": "idea_turn",
      "objectivity_score": 80,
      "idea_scores": {
        "cohesion_score": 80,
        "complexity_score": 70,
        "technicality_score": 33,
        "feasibility_score": 70
      }
    }
  ]
}
```

Web research analysis:

```json
{
  "id": "string uuid",
  "text": "LLM analysis of search results",
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "kind": "web_research_analysis",
    "source": "duckduckgo",
    "query": "query 1 | query 2 | query 3",
    "sources": [
      {
        "title": "source title",
        "url": "https://example.com"
      }
    ]
  }
}
```

The `/summary` research pipeline is:

1. LLM proposes several search queries.
2. DuckDuckGo returns result titles, URLs, and snippets.
3. The runtime fetches text from a few result pages.
4. LLM analyzes the page text and search results.
5. Only the compact analysis plus source titles/URLs are stored.

Raw web page content and raw snippets are not stored as content records.

## Vector Records

Each line in `vectors.jsonl` is one JSON object:

```json
{
  "id": "same uuid as source record",
  "text": "embedding source text",
  "embedding": [0.0, 1.0, 0.0],
  "created_at": "ISO-8601 UTC timestamp",
  "meta": {
    "source": "ollama or local_hash",
    "record_type": "content, memory, or summary",
    "content_kind": "dialogue_message",
    "memory_kind": "objective_fact",
    "summary_kind": "dialogue_summary"
  }
}
```

## Prompt Context Contract

Prompt context is built from:

1. Recent dialogue history, capped at 5 stored messages.
2. Relevant stored context from vector search.

Memory lines include idea scores when available:

```text
Relevant stored context. Use only as support; do not repeat it as if new:
- [summary] Parser should define column mapping first | cohesion=80, complexity=70, technicality=33, feasibility=70 | relevance=0.37
```

## Commands

`/summary`

- May use multi-step DuckDuckGo research.
- Plans several search queries before searching.
- Fetches and analyzes a few pages before final summary generation.
- Stores web research analysis in `summaries.jsonl`.
- Stores the final dialogue summary in `summaries.jsonl`.
- Extracts idea statements into `memories.jsonl`.

`/packing`

- Uses the latest summary if no new dialogue turns were added.
- Asks the LLM to extract structured handoff fields.
- Writes a Markdown file from `docs/HANDOFF_TEMPLATE.md`.
- In normal CLI mode, writes to `.local/`.
- In scenario replay, writes under the scenario artifact directory.

## Test Coverage

Current tests verify:

- JSONL files are created automatically
- content, memory, summary, and vector records are written
- idea scores are present on extracted context
- web research analysis is stored as summary analysis, not content
- `/summary` and `/packing` are separate operations
- handoff copies are created from the template
- local hash vectors work without Ollama
- vector search can return content, memory, and summary layers
- prompt logs avoid dirty encoding artifacts
