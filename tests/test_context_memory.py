from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.context.extractor import FactExtractor
from src.context.manager import ContextManager, has_dirty_encoding_artifacts
from src.context.storage import JsonlStorage
from src.context.wrapper import ContextualLLM


class DummyLLM:
    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        return prompt


class ContextMemoryTests(unittest.TestCase):
    def test_storage_creates_jsonl_files(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)

            self.assertTrue(storage.content_path.exists())
            self.assertTrue(storage.memories_path.exists())
            self.assertTrue(storage.vectors_path.exists())
            self.assertEqual(storage.load_content(), [])
            self.assertEqual(storage.load_memories(), [])
            self.assertEqual(storage.load_vectors(), [])

    def test_add_fact_writes_memory_vector_and_meta(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            memory = context.add_fact(
                "I fixed a broken script alone and shipped it",
                prompt="What did you solve by yourself?",
                objectivity_score=87,
            )

            memories = storage.load_memories()
            vectors = storage.load_vectors()

            self.assertEqual(len(memories), 1)
            self.assertEqual(len(vectors), 1)
            self.assertEqual(memories[0]["id"], memory["id"])
            self.assertEqual(vectors[0]["id"], memory["id"])
            self.assertEqual(memories[0]["meta"]["objectivity_score"], 87)
            self.assertTrue(memories[0]["meta"]["is_objective"])
            self.assertEqual(vectors[0]["meta"]["record_type"], "memory")
            self.assertEqual(vectors[0]["meta"]["source"], "local_hash")
            self.assertIsInstance(vectors[0]["embedding"], list)

    def test_ingest_user_content_writes_content_and_extracted_fact(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            content = context.ingest_user_content(
                "I fixed a broken script alone and shipped it",
                prompt="What did you solve by yourself?",
                objectivity_score=87,
            )

            contents = storage.load_content()
            memories = storage.load_memories()
            vectors = storage.load_vectors()

            self.assertEqual(len(contents), 1)
            self.assertEqual(len(memories), 1)
            self.assertEqual(len(vectors), 2)
            self.assertEqual(contents[0]["id"], content["id"])
            self.assertEqual(contents[0]["meta"]["kind"], "user_content")
            self.assertEqual(contents[0]["meta"]["extracted_fact_count"], 1)
            self.assertEqual(memories[0]["meta"]["source_content_id"], content["id"])
            self.assertEqual(
                {vector["meta"]["record_type"] for vector in vectors},
                {"content", "memory"},
            )

    def test_relevant_memories_returns_best_matches(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.add_fact(
                "I fixed a broken script alone and shipped it",
                objectivity_score=87,
            )
            context.add_fact(
                "I noticed tension before the meeting started",
                objectivity_score=82,
            )

            matches = context.relevant_memories("broken script", limit=1)

            self.assertEqual(len(matches), 1)
            self.assertIn("broken script", matches[0].text)

    def test_vector_search_can_return_content_and_memory_layers(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.ingest_user_content(
                "I fixed a broken script alone and shipped it",
                objectivity_score=87,
            )

            matches = context.vector_search("broken script", limit=3)

            self.assertGreaterEqual(len(matches), 2)
            self.assertIn("content", {match.record_type for match in matches})
            self.assertIn("memory", {match.record_type for match in matches})

    def test_extractor_builds_search_query_and_fact(self) -> None:
        extracted = FactExtractor().extract(
            "I fixed a broken script alone and shipped it. I felt lucky."
        )

        self.assertEqual(
            extracted.objective_facts,
            ["I fixed a broken script alone and shipped it"],
        )
        self.assertIn("fixed", extracted.search_query)
        self.assertGreaterEqual(extracted.objectivity_score, 50)

    def test_final_prompt_log_is_clean(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.ingest_user_content(
                "I fixed a broken script alone and shipped it",
                prompt="What did you solve by yourself?",
                objectivity_score=87,
            )
            wrapper = ContextualLLM(
                llm=DummyLLM(),
                context_manager=context,
                memory_limit=3,
            )
            prompt = wrapper.build_prompt_for_log(
                "Help me remember objective evidence that I can solve technical problems."
            )

        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        log_path = cache_dir / "final_prompt.log"
        log_path.write_text(prompt, encoding="utf-8")

        self.assertIn("User memory.", prompt)
        self.assertIn("[memory] I fixed a broken script alone and shipped it", prompt)
        self.assertIn("[content] I fixed a broken script alone and shipped it", prompt)
        self.assertIn("objectivity=87", prompt)
        self.assertFalse(has_dirty_encoding_artifacts(prompt))


if __name__ == "__main__":
    unittest.main()
