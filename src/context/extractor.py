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
    "\u043d\u0430\u043f\u0438\u0441\u0430\u043b",
    "\u043d\u0430\u043f\u0438\u0441\u0430\u043b\u0430",
    "\u0441\u043e\u0431\u0440\u0430\u043b",
    "\u0441\u043e\u0431\u0440\u0430\u043b\u0430",
    "\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u043b",
    "\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u043b\u0430",
    "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0430\u043b",
    "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u0430",
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
    cohesion_score: int
    complexity_score: int
    technicality_score: int
    feasibility_score: int

    @property
    def objectivity_score(self) -> int:
        """Compatibility alias while the rest of the app moves to idea scores."""
        return self.cohesion_score

    def idea_scores(self) -> dict[str, int]:
        return {
            "cohesion_score": self.cohesion_score,
            "complexity_score": self.complexity_score,
            "technicality_score": self.technicality_score,
            "feasibility_score": self.feasibility_score,
        }


class FactExtractor:
    """Extract idea fragments, search text, and planning scores from user content."""

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
            "You are Lisa's extraction layer. Lisa is a curious teenager who helps "
            "a person understand an idea by asking simple, sharp questions.\n"
            "Extract from user text: concrete idea statements and planning signals.\n"
            "Return only JSON:\n"
            "{"
            "\"objective_facts\": [\"idea statement\"], "
            "\"search_query\": \"query\", "
            "\"cohesion_score\": 0, "
            "\"complexity_score\": 0, "
            "\"technicality_score\": 0, "
            "\"feasibility_score\": 0"
            "}\n\n"
            "Guidelines:\n"
            "- objective_facts are still named that way for compatibility, but store "
            "short concrete idea statements, assumptions, goals, constraints, or decisions.\n"
            "- cohesion_score: 0=fragmented/confusing, 100=clear goal and logic.\n"
            "- complexity_score: 0=trivial/simple, 100=many moving parts or dependencies.\n"
            "- technicality_score: 0=non-technical, 100=deep technical implementation.\n"
            "- feasibility_score: 0=unrealistic/underspecified, 100=actionable with clear next steps.\n"
            "- Do not flatter. Do not invent details. Prefer uncertainty over fake precision.\n\n"
            f"User text: {text}"
        )
        raw = self.llm.generate(prompt, max_tokens=400, temperature=0.0)
        data = json.loads(raw)
        facts = data.get("objective_facts", [])
        search_query = data.get("search_query", text)
        cohesion_score = self._score_from_data(data, "cohesion_score")
        complexity_score = self._score_from_data(data, "complexity_score")
        technicality_score = self._score_from_data(data, "technicality_score")
        feasibility_score = self._score_from_data(data, "feasibility_score")

        if not isinstance(facts, list):
            facts = []

        facts = [str(fact).strip() for fact in facts if str(fact).strip()]

        if not isinstance(search_query, str) or not search_query.strip():
            search_query = text

        return ExtractedContext(
            objective_facts=facts or [text.strip()],
            search_query=search_query.strip(),
            cohesion_score=cohesion_score,
            complexity_score=complexity_score,
            technicality_score=technicality_score,
            feasibility_score=feasibility_score,
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
            cohesion_score=self._heuristic_cohesion_score(cleaned),
            complexity_score=self._heuristic_complexity_score(cleaned),
            technicality_score=self._heuristic_technicality_score(cleaned),
            feasibility_score=self._heuristic_feasibility_score(cleaned),
        )

    @staticmethod
    def _score_from_data(data: dict, key: str) -> int:
        value = data.get(key, 0)

        if not isinstance(value, int):
            return 0

        return max(0, min(100, value))

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
        return FactExtractor._heuristic_cohesion_score(text)

    @staticmethod
    def _heuristic_cohesion_score(text: str) -> int:
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

    @staticmethod
    def _heuristic_complexity_score(text: str) -> int:
        words = text.split()
        score = min(20 + len(words) * 3, 70)
        lowered = text.lower()
        complexity_markers = (
            "architecture",
            "pipeline",
            "integration",
            "dependency",
            "workflow",
            "agent",
            "memory",
            "vector",
            "\u0430\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440",
            "\u0438\u043d\u0442\u0435\u0433\u0440\u0430\u0446",
            "\u0437\u0430\u0432\u0438\u0441\u0438\u043c",
            "\u0430\u0433\u0435\u043d\u0442",
            "\u043f\u0430\u043c\u044f\u0442",
        )

        if any(marker in lowered for marker in complexity_markers):
            score += 20

        return max(0, min(100, score))

    @staticmethod
    def _heuristic_technicality_score(text: str) -> int:
        lowered = text.lower()
        technical_markers = (
            "api",
            "cli",
            "json",
            "llm",
            "python",
            "prompt",
            "vector",
            "embedding",
            "database",
            "test",
            "github",
            "\u043a\u043e\u0434",
            "\u043c\u043e\u0434\u0435\u043b",
            "\u043f\u0440\u043e\u043c\u043f\u0442",
            "\u0442\u0435\u0441\u0442",
            "\u0431\u0430\u0437\u0430",
            "\u0434\u0430\u043d\u043d",
        )
        hits = sum(1 for marker in technical_markers if marker in lowered)
        score = min(15 + hits * 18, 90)

        if any(char in text for char in "{}[]()_/\\"):
            score += 10

        return max(0, min(100, score))

    @staticmethod
    def _heuristic_feasibility_score(text: str) -> int:
        lowered = text.lower()
        words = text.split()
        score = min(30 + len(words) * 3, 70)

        if any(marker in lowered for marker in ACTION_MARKERS):
            score += 15

        if any(char.isdigit() for char in text):
            score += 10

        if any(marker in lowered for marker in LOW_OBJECTIVITY_MARKERS):
            score -= 25

        return max(0, min(100, score))
