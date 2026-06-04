from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import sqrt
from uuid import uuid4

from src.context.extractor import FactExtractor
from src.context.extractor import LOW_OBJECTIVITY_MARKERS
from src.context.storage import JsonlStorage
from src.llm import OllamaError, OllamaLLM


DIRTY_ENCODING_MARKERS = tuple(
    value.decode("utf-8")
    for value in (
        b"\xd0\xa1\xd0\x83",
        b"\xd0\xa1\xe2\x80\x9a",
        b"\xd0\xa0\xd1\x99",
        b"\xd0\xa0\xd1\x9f",
        b"\xd0\xa0\xd1\x9c",
        b"\xd0\xa0\xc2\xb0",
        b"\xd0\xa0\xc2\xb5",
        b"\xd0\xa0\xd1\x91",
    )
)


@dataclass
class MemoryMatch:
    text: str
    score: float
    meta: dict
    record_type: str = "memory"
    record_id: str | None = None


class BuildingPromptManager:
    """Small prompt registry kept for compatibility with the first draft."""

    def __init__(self) -> None:
        self.prompts: dict[str, list[str]] = {}

    def add_prompt(self, building_id: str, prompt: str) -> None:
        self.prompts.setdefault(building_id, []).append(prompt)

    def get_prompts(self, building_id: str) -> list[str]:
        return self.prompts.get(building_id, [])


class ContextManager:
    """Stores user facts and retrieves relevant memory for future prompts."""

    def __init__(
        self,
        storage: JsonlStorage | None = None,
        llm: OllamaLLM | None = None,
        extractor: FactExtractor | None = None,
    ) -> None:
        self.storage = storage or JsonlStorage()
        self.llm = llm
        self.extractor = extractor or FactExtractor(llm=llm)

    def ingest_user_content(
        self,
        text: str,
        prompt: str | None = None,
        objectivity_score: int | None = None,
        source: str = "user_input",
    ) -> dict:
        extracted = self.extractor.extract(text)
        score = objectivity_score

        if score is None:
            score = extracted.objectivity_score

        content_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        content = {
            "id": content_id,
            "text": text,
            "created_at": created_at,
            "meta": {
                "kind": "user_content",
                "source": source,
                "prompt": prompt,
                "objectivity_score": score,
                "search_query": extracted.search_query,
                "extracted_fact_count": len(extracted.objective_facts),
            },
        }
        embedding, embedding_source = self._embed_with_source(extracted.search_query)
        vector = {
            "id": content_id,
            "text": extracted.search_query,
            "embedding": embedding,
            "created_at": created_at,
            "meta": {
                "source": embedding_source,
                "record_type": "content",
                "content_kind": content["meta"]["kind"],
            },
        }

        self.storage.add_content(content)
        self.storage.add_vector(vector)

        facts = []

        for fact_text in extracted.objective_facts:
            facts.append(
                self.add_fact(
                    text=fact_text,
                    prompt=prompt,
                    objectivity_score=score,
                    source_content_id=content_id,
                )
            )

        content["extracted_facts"] = facts
        return content

    def add_fact(
        self,
        text: str,
        prompt: str | None = None,
        objectivity_score: int | None = None,
        source_content_id: str | None = None,
    ) -> dict:
        score = objectivity_score

        if score is None:
            score = self.objectivity_score(text)

        memory_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "kind": "objective_fact",
            "objectivity_score": score,
            "is_objective": score >= 50,
            "prompt": prompt,
            "source_content_id": source_content_id,
        }
        memory = {
            "id": memory_id,
            "text": text,
            "created_at": created_at,
            "meta": meta,
        }
        embedding, embedding_source = self._embed_with_source(text)
        vector = {
            "id": memory_id,
            "text": text,
            "embedding": embedding,
            "created_at": created_at,
            "meta": {
                "source": embedding_source,
                "record_type": "memory",
                "memory_kind": meta["kind"],
            },
        }

        self.storage.add_memory(memory)
        self.storage.add_vector(vector)

        return memory

    def add_summary(
        self,
        text: str,
        turns: list[dict],
        source: str = "five_turn_dialogue",
    ) -> dict:
        summary_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        summary = {
            "id": summary_id,
            "text": text,
            "created_at": created_at,
            "meta": {
                "kind": "dialogue_summary",
                "source": source,
                "turn_count": len(turns),
            },
            "turns": turns,
        }
        embedding, embedding_source = self._embed_with_source(text)
        vector = {
            "id": summary_id,
            "text": text,
            "embedding": embedding,
            "created_at": created_at,
            "meta": {
                "source": embedding_source,
                "record_type": "summary",
                "summary_kind": summary["meta"]["kind"],
            },
        }

        self.storage.add_summary(summary)
        self.storage.add_vector(vector)

        return summary

    def objectivity_score(self, text: str) -> int:
        if self.llm is None:
            return self._heuristic_objectivity_score(text)

        try:
            return self.llm.objectivity_score(text)
        except OllamaError:
            return self._heuristic_objectivity_score(text)

    def embed(self, text: str) -> list[float]:
        embedding, _ = self._embed_with_source(text)
        return embedding

    def relevant_memories(self, query: str, limit: int = 5) -> list[MemoryMatch]:
        return self.vector_search(query, limit=limit, record_types={"memory"})

    def vector_search(
        self,
        query: str,
        limit: int = 5,
        record_types: set[str] | None = None,
    ) -> list[MemoryMatch]:
        extracted_query = self.extractor.build_search_query(query)
        query_vector = self.embed(extracted_query)
        records = self._searchable_records()
        matches = []

        for vector_record in self.storage.load_vectors():
            record_type = vector_record.get("meta", {}).get("record_type", "memory")

            if record_types is not None and record_type not in record_types:
                continue

            record = records.get(vector_record.get("id"))

            if record is None:
                continue

            embedding = vector_record.get("embedding")

            if not isinstance(embedding, list):
                continue

            score = self._cosine_similarity(query_vector, embedding)
            matches.append(
                MemoryMatch(
                    text=record.get("text", ""),
                    score=score,
                    meta=record.get("meta", {}),
                    record_type=record_type,
                    record_id=record.get("id"),
                )
            )

        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:limit]

    def _searchable_records(self) -> dict[str, dict]:
        records = {}

        for content in self.storage.load_content():
            records[content["id"]] = content

        for memory in self.storage.load_memories():
            records[memory["id"]] = memory

        for summary in self.storage.load_summaries():
            records[summary["id"]] = summary

        return records

    def _embed_with_source(self, text: str) -> tuple[list[float], str]:
        if self.llm is not None:
            try:
                return self.llm.embed(text), "ollama"
            except OllamaError:
                pass

        return self._local_embedding(text), "local_hash"

    @staticmethod
    def _heuristic_objectivity_score(text: str) -> int:
        lowered = text.lower()
        if any(marker in lowered for marker in LOW_OBJECTIVITY_MARKERS):
            return 15

        words = text.split()
        score = min(40 + len(words) * 4, 80)

        if any(char.isdigit() for char in text):
            score += 10

        action_markers = (
            "\u0441\u0434\u0435\u043b\u0430\u043b",
            "\u0441\u0434\u0435\u043b\u0430\u043b\u0430",
            "\u0440\u0435\u0448\u0438\u043b",
            "\u0440\u0435\u0448\u0438\u043b\u0430",
            "\u0437\u0430\u043c\u0435\u0442\u0438\u043b",
            "\u0437\u0430\u043c\u0435\u0442\u0438\u043b\u0430",
            "\u0432\u044b\u0434\u0435\u0440\u0436\u0430\u043b",
            "\u0432\u044b\u0434\u0435\u0440\u0436\u0430\u043b\u0430",
            "\u043f\u043e\u043c\u043e\u0433",
            "\u043f\u043e\u043c\u043e\u0433\u043b\u0430",
            "finished",
            "fixed",
            "handled",
            "noticed",
        )

        if any(marker in lowered for marker in action_markers):
            score += 10
        elif len(words) < 5:
            score -= 20

        return max(0, min(100, score))

    @staticmethod
    def _local_embedding(text: str, dimensions: int = 64) -> list[float]:
        vector = [0.0] * dimensions

        for word in text.lower().split():
            digest = sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % dimensions
            vector[index] += 1.0

        return vector

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        length = min(len(left), len(right))

        if length == 0:
            return 0.0

        left = left[:length]
        right = right[:length]
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))

        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        return dot / (left_norm * right_norm)


def has_dirty_encoding_artifacts(text: str) -> bool:
    return any(marker in text for marker in DIRTY_ENCODING_MARKERS)
