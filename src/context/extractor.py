from __future__ import annotations

from dataclasses import dataclass
import json
import re

from src.llm import OllamaError, OllamaLLM


ACTION_MARKERS = (
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
    "built",
    "created",
    "finished",
    "fixed",
    "handled",
    "noticed",
    "solved",
)

LOW_OBJECTIVITY_MARKERS = (
    "\u043d\u0435 \u0437\u043d\u0430\u044e",
    "\u043d\u0435 \u0431\u044b\u043b\u043e",
    "\u043d\u0435\u0442 \u0442\u0430\u043a\u0438\u0445",
    "\u043d\u0430\u0432\u0435\u0440\u043d\u043e",
    "\u0432\u0440\u043e\u0434\u0435",
    "\u043a\u0430\u0436\u0435\u0442\u0441\u044f",
    "i don't know",
    "not sure",
    "maybe",
)


@dataclass
class ExtractedContext:
    objective_facts: list[str]
    search_query: str
    objectivity_score: int


class FactExtractor:
    """Extract objective facts and search text from user content."""

    def __init__(self, llm: OllamaLLM | None = None) -> None:
        self.llm = llm

    def extract(self, text: str) -> ExtractedContext:
        if self.llm is not None:
            try:
                return self._extract_with_llm(text)
            except (OllamaError, json.JSONDecodeError, TypeError):
                pass

        return self._extract_locally(text)

    def build_search_query(self, text: str) -> str:
        return self.extract(text).search_query

    def _extract_with_llm(self, text: str) -> ExtractedContext:
        prompt = (
            "Extract objective memory facts from the user text.\n"
            "Return only JSON with this shape:\n"
            "{\"objective_facts\": [\"fact\"], \"search_query\": \"short query\", "
            "\"objectivity_score\": 0}\n"
            "Rules: facts must be observable actions, situations, or results. "
            "Do not infer traits. Do not flatter.\n\n"
            f"User text: {text}"
        )
        raw = self.llm.generate(prompt, max_tokens=300, temperature=0.0)
        data = json.loads(raw)
        facts = data.get("objective_facts", [])
        search_query = data.get("search_query", text)
        objectivity_score = data.get("objectivity_score", 0)

        if not isinstance(facts, list):
            facts = []

        facts = [str(fact).strip() for fact in facts if str(fact).strip()]

        if not isinstance(search_query, str) or not search_query.strip():
            search_query = text

        if not isinstance(objectivity_score, int):
            objectivity_score = 0

        return ExtractedContext(
            objective_facts=facts or [text.strip()],
            search_query=search_query.strip(),
            objectivity_score=max(0, min(100, objectivity_score)),
        )

    def _extract_locally(self, text: str) -> ExtractedContext:
        cleaned = " ".join(text.split())
        sentences = [
            sentence.strip()
            for sentence in re.split(r"[.!?\n]+", cleaned)
            if sentence.strip()
        ]
        objective_facts = [
            sentence for sentence in sentences if self._looks_like_fact(sentence)
        ]

        if not objective_facts and cleaned:
            objective_facts = [cleaned]

        return ExtractedContext(
            objective_facts=objective_facts,
            search_query=self._search_query_from_text(cleaned),
            objectivity_score=self._heuristic_objectivity_score(cleaned),
        )

    @staticmethod
    def _looks_like_fact(text: str) -> bool:
        lowered = text.lower()
        return len(text.split()) >= 4 and any(marker in lowered for marker in ACTION_MARKERS)

    @staticmethod
    def _search_query_from_text(text: str, max_words: int = 16) -> str:
        words = re.findall(r"[\w-]+", text.lower(), flags=re.UNICODE)
        return " ".join(words[:max_words]) if words else text

    @staticmethod
    def _heuristic_objectivity_score(text: str) -> int:
        lowered = text.lower()
        if any(marker in lowered for marker in LOW_OBJECTIVITY_MARKERS):
            return 15

        words = text.split()
        score = min(40 + len(words) * 4, 80)

        if any(char.isdigit() for char in text):
            score += 10

        if any(marker in lowered for marker in ACTION_MARKERS):
            score += 10
        elif len(words) < 5:
            score -= 20

        return max(0, min(100, score))
