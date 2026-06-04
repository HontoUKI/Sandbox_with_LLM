from __future__ import annotations

from src.context.manager import ContextManager, DialogueMessage, MemoryMatch
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
        history_limit: int = 5,
    ) -> None:
        self.llm = llm
        self.context_manager = context_manager or ContextManager(llm=llm)
        self.memory_limit = memory_limit
        self.history_limit = history_limit

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
            "content": self.build_context_for_turn(query),
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
        context = self.build_context_for_turn(prompt)
        return f"{context}\n\nUser request:\n{prompt}"

    def build_context_for_turn(self, query: str) -> str:
        recent_messages = self.context_manager.recent_dialogue_messages(
            limit=self.history_limit,
        )
        recent_ids = {message.record_id for message in recent_messages}
        context_parts = []

        if recent_messages:
            context_parts.append(self._build_recent_history_context(recent_messages))

        memory_context = self._build_memory_context(
            query,
            exclude_ids=recent_ids,
            exclude_texts={message.text for message in recent_messages},
        )

        if memory_context:
            context_parts.append(memory_context)

        if not context_parts:
            return "User memory is empty. Do not invent facts about the user."

        return "\n\n".join(context_parts)

    def _build_memory_context(
        self,
        query: str,
        exclude_ids: set[str] | None = None,
        exclude_texts: set[str] | None = None,
    ) -> str:
        matches = self.context_manager.vector_search(
            query,
            limit=self.memory_limit * 2,
            exclude_ids=exclude_ids,
        )
        normalized_excluded = {
            self._normalize_text(text)
            for text in (exclude_texts or set())
        }
        matches = [
            match
            for match in matches
            if self._normalize_text(match.text) not in normalized_excluded
        ][: self.memory_limit]
        return self._format_memory_context(matches)

    def _format_memory_context(self, matches: list[MemoryMatch]) -> str:
        if not matches:
            return ""

        lines = [
            "Relevant stored context. Use only as support; do not repeat it as if new:",
        ]
        lines.extend(self._format_memory(match) for match in matches)

        return "\n".join(lines)

    @staticmethod
    def _build_recent_history_context(messages: list[DialogueMessage]) -> str:
        lines = [
            "Recent dialogue history. Use this as the immediate conversation state:",
        ]
        lines.extend(
            f"- [{message.role}] {message.text}"
            for message in messages
        )
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

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.lower().split())
