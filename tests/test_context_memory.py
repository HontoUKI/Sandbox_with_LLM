from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from main import DialogueTurn, generate_question, handle_user_message
from src.context.build_prompt_little_director import build_prompt_little_director
from src.context.dialogue_intent import classify_user_message
from src.context.extractor import FactExtractor
from src.context.manager import ContextManager, has_dirty_encoding_artifacts
from src.context.storage import JsonlStorage
from src.context.wrapper import ContextualLLM
from src.llm import OllamaLLM


class DummyLLM:
    def __init__(self) -> None:
        self.last_prompt = ""
        self.response = "Какой конкретный эпизод лучше всего показывает это?"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        self.last_prompt = prompt
        return self.response


class ContextMemoryTests(unittest.TestCase):
    def test_ollama_client_uses_configured_endpoints(self) -> None:
        calls = []
        llm = OllamaLLM(
            model="chat-model",
            embedding_model="embed-model",
            chat_url="http://ollama.local/api/chat",
            embed_url="http://ollama.local/api/embeddings",
        )

        def fake_post_url(url, payload):
            calls.append((url, payload))

            if url.endswith("/api/embeddings"):
                return {"embedding": [1, 2, 3]}

            return {"message": {"content": "ok"}}

        llm._post_url = fake_post_url

        self.assertEqual(llm.generate("hello"), "ok")
        self.assertEqual(llm.embed("hello"), [1.0, 2.0, 3.0])
        self.assertEqual(calls[0][0], "http://ollama.local/api/chat")
        self.assertEqual(calls[1][0], "http://ollama.local/api/embeddings")
        self.assertEqual(calls[1][1]["model"], "embed-model")

    def test_ollama_client_normalizes_base_endpoints(self) -> None:
        llm = OllamaLLM(
            model="chat-model",
            embedding_model="embed-model",
            chat_url="http://127.0.0.1:11434",
            embed_url="http://127.0.0.1:11434/api",
        )

        self.assertEqual(llm.chat_url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(llm.embed_url, "http://127.0.0.1:11434/api/embeddings")

    def test_storage_creates_jsonl_files(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)

            self.assertTrue(storage.content_path.exists())
            self.assertTrue(storage.memories_path.exists())
            self.assertTrue(storage.summaries_path.exists())
            self.assertTrue(storage.vectors_path.exists())
            self.assertEqual(storage.load_content(), [])
            self.assertEqual(storage.load_memories(), [])
            self.assertEqual(storage.load_summaries(), [])
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

    def test_add_dialogue_content_does_not_create_memory(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.add_dialogue_content(
                "Не дави на меня",
                prompt="Вспомни один эпизод.",
                bot_response="Ок, не давлю.",
                intent="boundary",
                objectivity_score=15,
            )

            self.assertEqual(len(storage.load_content()), 1)
            self.assertEqual(storage.load_memories(), [])
            self.assertEqual(storage.load_content()[0]["meta"]["role"], "user")
            self.assertEqual(storage.load_vectors()[0]["meta"]["record_type"], "content")

    def test_add_assistant_dialogue_content_links_to_user_content(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            user_content = context.add_dialogue_content(
                "I feel trivial",
                prompt="What feels hard right now?",
                intent="self_deprecation",
                objectivity_score=20,
                role="user",
            )
            assistant_content = context.add_dialogue_content(
                "Let's separate the feeling from one observable episode.",
                prompt="What feels hard right now?",
                intent="self_deprecation_response",
                objectivity_score=20,
                source="assistant_response",
                role="assistant",
                linked_content_id=user_content["id"],
            )

            contents = storage.load_content()
            vectors = storage.load_vectors()

            self.assertEqual(len(contents), 2)
            self.assertEqual(len(vectors), 2)
            self.assertEqual(assistant_content["meta"]["role"], "assistant")
            self.assertEqual(assistant_content["meta"]["source"], "assistant_response")
            self.assertEqual(assistant_content["meta"]["linked_content_id"], user_content["id"])

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

    def test_add_summary_writes_summary_and_vector(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            summary = context.add_summary(
                "User said they fixed a script. Meta objectivity: 87/100.",
                turns=[
                    {
                        "question": "What did you solve?",
                        "user_answer": "I fixed a broken script.",
                        "bot_answer": "This is concrete.",
                        "objectivity_score": 87,
                    }
                ],
            )

            summaries = storage.load_summaries()
            vectors = storage.load_vectors()

            self.assertEqual(len(summaries), 1)
            self.assertEqual(len(vectors), 1)
            self.assertEqual(summaries[0]["id"], summary["id"])
            self.assertEqual(vectors[0]["id"], summary["id"])
            self.assertEqual(vectors[0]["meta"]["record_type"], "summary")

    def test_vector_search_can_return_summary_layer(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.add_summary(
                "User said they fixed a script. Meta objectivity: 87/100.",
                turns=[],
            )

            matches = context.vector_search("fixed script", limit=1)

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].record_type, "summary")

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

    def test_low_objectivity_rejection_markers_score_low(self) -> None:
        context = ContextManager()

        self.assertLess(context.objectivity_score("Не знаю... Не было таких"), 50)

    def test_russian_created_bot_answer_scores_as_fact(self) -> None:
        context = ContextManager()

        self.assertGreaterEqual(context.objectivity_score("Написал бота в телеграмме"), 50)

    def test_intent_classifier_respects_boundaries(self) -> None:
        intent = classify_user_message("Не дави на меня", 15, 50)

        self.assertEqual(intent.kind, "boundary")
        self.assertFalse(intent.should_store_fact)
        self.assertTrue(intent.should_store_content)

    def test_intent_classifier_detects_self_deprecation(self) -> None:
        intent = classify_user_message("Я жестко туплю и не считаюсь с чужим мнением", 20, 50)

        self.assertEqual(intent.kind, "self_deprecation")
        self.assertFalse(intent.should_store_fact)

    def test_handle_user_message_stores_boundary_as_content_only(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            turn = handle_user_message(
                "Вспомни один эпизод.",
                "Не дави на меня",
                context,
                objectivity_threshold=50,
            )

            self.assertEqual(turn.intent, "boundary")
            self.assertIn("дав", turn.bot_answer)
            contents = storage.load_content()
            self.assertEqual(len(contents), 2)
            self.assertEqual(storage.load_memories(), [])
            self.assertEqual({content["meta"]["role"] for content in contents}, {"user", "assistant"})

    def test_handle_user_message_stores_assistant_response_for_fact(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            turn = handle_user_message(
                "What did you build?",
                "I wrote a telegram bot and tested it",
                context,
                objectivity_threshold=50,
            )

            contents = storage.load_content()
            memories = storage.load_memories()
            assistant_messages = [
                content
                for content in contents
                if content["meta"].get("role") == "assistant"
            ]

            self.assertEqual(turn.intent, "objective_fact")
            self.assertEqual(len(contents), 2)
            self.assertEqual(memories, [])
            self.assertEqual(len(assistant_messages), 1)
            self.assertEqual(assistant_messages[0]["text"], turn.bot_answer)
            self.assertEqual(assistant_messages[0]["meta"]["source"], "assistant_response")

    def test_summary_extraction_creates_memories_after_just_chatting(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            turns = [
                {
                    "question": "What did you build?",
                    "user_answer": "I wrote a telegram bot and tested it",
                    "bot_answer": "That counts.",
                    "intent": "objective_fact",
                    "objectivity_score": 80,
                }
            ]

            summary = context.add_summary("Short summary", turns=turns)
            facts = context.extract_dialogue_summary_facts(
                turns=turns,
                source_summary_id=summary["id"],
            )

            self.assertGreaterEqual(len(facts), 1)
            self.assertGreaterEqual(len(storage.load_memories()), 1)

    def test_little_director_selects_modes_by_objectivity(self) -> None:
        self.assertEqual(build_prompt_little_director(20).mode, "concrete_grounding")
        self.assertEqual(build_prompt_little_director(70).mode, "fact_exploration")
        self.assertEqual(build_prompt_little_director(90).mode, "context_deepening")

    def test_generate_question_includes_director_block(self) -> None:
        llm = DummyLLM()
        question = generate_question(
            llm,
            [
                DialogueTurn(
                    question="Что произошло?",
                    user_answer="Я сдал проект во время болезни.",
                    bot_answer="Факт принят.",
                    objectivity_score=85,
                    intent="objective_fact",
                )
            ],
        )

        self.assertIn("Director mode: context_deepening", llm.last_prompt)
        self.assertIn("Мой следующий ход:", llm.last_prompt)
        self.assertTrue(question)

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

        self.assertIn("Recent dialogue history.", prompt)
        self.assertIn("[user] I fixed a broken script alone and shipped it", prompt)
        self.assertEqual(prompt.count("I fixed a broken script alone and shipped it"), 1)
        self.assertFalse(has_dirty_encoding_artifacts(prompt))

    def test_prompt_context_excludes_recent_history_from_vector_matches(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            context.add_dialogue_content(
                "I am worried that I only get by because people help me.",
                intent="conversation",
                objectivity_score=35,
                role="user",
            )
            context.add_dialogue_content(
                "Let's look for what you actually did inside that situation.",
                intent="conversation_response",
                objectivity_score=35,
                source="assistant_response",
                role="assistant",
            )
            context.add_fact(
                "I resolved a deployment issue after reading logs and testing fixes.",
                objectivity_score=88,
            )
            wrapper = ContextualLLM(
                llm=DummyLLM(),
                context_manager=context,
                memory_limit=5,
                history_limit=5,
            )

            prompt = wrapper.build_prompt_for_log(
                "I am worried that I only get by because people help me."
            )

        self.assertIn("Recent dialogue history.", prompt)
        self.assertIn("Relevant stored context.", prompt)
        self.assertEqual(
            prompt.count("I am worried that I only get by because people help me."),
            2,
        )
        self.assertIn("I resolved a deployment issue", prompt)


if __name__ == "__main__":
    unittest.main()
