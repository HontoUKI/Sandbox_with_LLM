from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContentStorage:
    """Simple in-memory storage for conversation history."""

    def __init__(self) -> None:
        self.history: list[dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def get_messages(self) -> list[dict[str, str]]:
        return self.history


class JsonlStorage:
    """Append-only JSONL storage for user memory and vectors."""

    def __init__(self, base_dir: str | Path = "user_data") -> None:
        self.base_dir = Path(base_dir)
        self.content_path = self.base_dir / "content.jsonl"
        self.memories_path = self.base_dir / "memories.jsonl"
        self.vectors_path = self.base_dir / "vectors.jsonl"
        self._ensure_files()

    def add_content(self, record: dict[str, Any]) -> None:
        self._append_jsonl(self.content_path, record)

    def add_memory(self, record: dict[str, Any]) -> None:
        self._append_jsonl(self.memories_path, record)

    def add_vector(self, record: dict[str, Any]) -> None:
        self._append_jsonl(self.vectors_path, record)

    def load_content(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.content_path)

    def load_memories(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.memories_path)

    def load_vectors(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.vectors_path)

    def _ensure_files(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.content_path.touch(exist_ok=True)
        self.memories_path.touch(exist_ok=True)
        self.vectors_path.touch(exist_ok=True)

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.write("\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        records = []

        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                records.append(json.loads(line))

        return records
