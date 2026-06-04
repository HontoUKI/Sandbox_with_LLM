"""
Small Ollama client used by the self-esteem bot.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when Ollama returns an error or an unexpected payload."""


class OllamaLLM:
    """Minimal wrapper around Ollama's local HTTP API."""

    def __init__(
        self,
        model: str = "llama3",
        host: str = "http://localhost:11434",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Generate plain text from a single prompt."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        data = self._post("/api/generate", payload)
        return self._require_text(data, "response")

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Generate a response from chat messages."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        data = self._post("/api/chat", payload)
        message = data.get("message")

        if not isinstance(message, dict):
            raise OllamaError(f"Ollama returned no chat message: {data}")

        return self._require_text(message, "content")

    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for text using Ollama."""
        payload = {
            "model": self.model,
            "prompt": text,
        }
        data = self._post("/api/embeddings", payload)
        embedding = data.get("embedding")

        if not isinstance(embedding, list):
            raise OllamaError(f"Ollama response has no embedding: {data}")

        return [float(value) for value in embedding]

    def objectivity_score(self, text: str) -> int:
        """
        Estimate whether the text names observable facts.

        Returns an integer from 0 to 100:
        0 means fully vague or self-judging, 100 means concrete and observable.
        """
        prompt = (
            "Rate whether the user answer contains an observable fact for a "
            "self-esteem bot.\n"
            "Look for a concrete action, situation, or result. Return only JSON "
            "like {\"score\": 0}, where score is from 0 to 100.\n\n"
            f"User answer: {text}"
        )
        raw = self.generate(prompt, max_tokens=80, temperature=0.0)
        return self._parse_score(raw)

    def objectivity_check(self, text: str, threshold: int = 50) -> bool:
        """Return True if the text is concrete enough to keep in the dialogue."""
        return self.objectivity_score(text) >= threshold

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.host}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama returned HTTP {exc.code}: {error_body}") from exc
        except URLError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        try:
            data = json.loads(response_body)
        except ValueError as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {response_body}") from exc

        if not isinstance(data, dict):
            raise OllamaError(f"Ollama returned unexpected payload: {data}")

        return data

    @staticmethod
    def _require_text(data: dict[str, Any], key: str) -> str:
        value = data.get(key)

        if not isinstance(value, str):
            raise OllamaError(f"Ollama response has no text field '{key}': {data}")

        return value.strip()

    @staticmethod
    def _parse_score(raw: str) -> int:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Objectivity response is not JSON: {raw}") from exc

        score = data.get("score")

        if not isinstance(score, int):
            raise OllamaError(f"Objectivity score is missing or not an int: {raw}")

        return max(0, min(100, score))
