from __future__ import annotations

from src.context.manager import ContextManager, MemoryMatch
from src.llm import OllamaLLM


class ContentWrapper:
    """Simple content container kept for compatibility with the first draft."""

    def __init__(self, content: str) -> None:
        self.content = content


class ContextualLLM:
    """LLM facade that injects stored user facts into prompts."""

    def __init__(
        self,
        llm: OllamaLLM,
        context_manager: ContextManager | None = None,
        memory_limit: int = 5,
    ) -> None:
        self.llm = llm
        self.context_manager = context_manager or ContextManager(llm=llm)
        self.memory_limit = memory_limit

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        contextual_prompt = self.build_prompt_for_log(prompt)
        return self.llm.generate(
            contextual_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        query = self._last_user_message(messages)
        memory_message = {
            "role": "system",
            "content": self._build_memory_context(query),
        }
        return self.llm.chat(
            [memory_message, *messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def remember_fact(
        self,
        text: str,
        prompt: str | None = None,
        objectivity_score: int | None = None,
    ) -> dict:
        return self.context_manager.add_fact(
            text=text,
            prompt=prompt,
            objectivity_score=objectivity_score,
        )

    def build_prompt_for_log(self, prompt: str) -> str:
        context = self._build_memory_context(prompt)
        return f"{context}\n\nUser request:\n{prompt}"

    def _build_memory_context(self, query: str) -> str:
        matches = self.context_manager.vector_search(
            query,
            limit=self.memory_limit,
        )

        if not matches:
            return (
                "User memory is empty. Do not invent facts about the user."
            )

        lines = [
            "User memory. Use only as factual context. Do not flatter, "
            "invent, or add unsupported traits:",
        ]
        lines.extend(self._format_memory(match) for match in matches)

        return "\n".join(lines)

    @staticmethod
    def _format_memory(memory: MemoryMatch) -> str:
        objectivity = memory.meta.get("objectivity_score", "unknown")
        return (
            f"- [{memory.record_type}] {memory.text} | "
            f"objectivity={objectivity} | relevance={memory.score:.2f}"
        )

    @staticmethod
    def _last_user_message(messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")

        return messages[-1].get("content", "") if messages else ""
