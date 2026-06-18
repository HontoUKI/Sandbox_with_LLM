from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from main import (
    DialogueTurn,
    create_handoff_copy,
    build_summary,
    analyze_web_pages,
    generate_question,
    handle_user_message,
    parse_search_queries,
    save_packing,
    save_summary,
    WebPageText,
    WebSearchResult,
)
from src.context.build_prompt_little_director import build_prompt_little_director
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
        if "Придумай поисковые запросы" in prompt:
            return (
                '{"queries":["python excel parser openpyxl pandas",'
                '"excel to json python column mapping",'
                '"python excel parsing validation errors"]}'
            )
        if "Analyze web research" in prompt:
            return "External page analysis: openpyxl and pandas are visible options."
        if "Extract structured handoff fields" in prompt:
            return (
                '{"project_name":"Python Excel parser",'
                '"goal":"Read Excel columns and convert selected data to JSON.",'
                '"target_user":"A user who needs Excel data prepared for later processing.",'
                '"constraints":"Column detection, Excel file format, validation, and JSON schema need decisions.",'
                '"decisions":"Use Python and produce JSON from selected Excel columns.",'
                '"open_question_1":"How are required columns identified?",'
                '"open_question_2":"What JSON schema should be produced?",'
                '"open_question_3":"Which Excel formats must be supported?",'
                '"risk_1":"Unclear column selection",'
                '"risk_1_reason":"The parser cannot work reliably until required columns are defined.",'
                '"risk_1_check":"Choose name-based, index-based, or configured mapping.",'
                '"risk_2":"Weak error handling",'
                '"risk_2_reason":"Malformed files and missing columns can break processing.",'
                '"risk_2_check":"Define validation and error reporting rules.",'
                '"next_step_1":"Define the JSON schema.",'
                '"next_step_1_result":"A target output contract.",'
                '"next_step_2":"Define column mapping rules.",'
                '"next_step_2_result":"A reliable extraction rule.",'
                '"next_step_3":"Build a small parser for one .xlsx example.",'
                '"next_step_3_result":"A testable prototype."}'
            )
        return self.response

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


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

    def test_add_research_analysis_writes_analysis_not_content(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage)
            analysis = context.add_research_analysis(
                "External analysis: similar tools exist; verify demand.",
                query="idea planner agent risks",
                sources=[
                    {
                        "title": "Example source",
                        "url": "https://example.com",
                    }
                ],
            )

            self.assertEqual(storage.load_content(), [])
            summaries = storage.load_summaries()
            self.assertEqual(summaries[0]["id"], analysis["id"])
            self.assertEqual(summaries[0]["meta"]["kind"], "web_research_analysis")
            self.assertEqual(summaries[0]["meta"]["query"], "idea planner agent risks")

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
        self.assertEqual(
            set(extracted.idea_scores()),
            {
                "cohesion_score",
                "complexity_score",
                "technicality_score",
                "feasibility_score",
            },
        )

    def test_low_objectivity_rejection_markers_score_low(self) -> None:
        context = ContextManager()

        self.assertLess(context.objectivity_score("Не знаю... Не было таких"), 50)

    def test_russian_created_bot_answer_scores_as_fact(self) -> None:
        context = ContextManager()

        self.assertGreaterEqual(context.objectivity_score("Написал бота в телеграмме"), 50)

    def test_handle_user_message_stores_dialogue_content_only(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage, llm=DummyLLM())
            turn = handle_user_message(
                "Вспомни один эпизод.",
                "Не дави на меня",
                context,
                objectivity_threshold=50,
            )

            self.assertEqual(turn.intent, "idea_turn")
            contents = storage.load_content()
            self.assertEqual(len(contents), 2)
            self.assertEqual(storage.load_memories(), [])
            self.assertEqual({content["meta"]["role"] for content in contents}, {"user", "assistant"})

    def test_handle_user_message_stores_assistant_response_for_fact(self) -> None:
        with TemporaryDirectory() as directory:
            storage = JsonlStorage(directory)
            context = ContextManager(storage=storage, llm=DummyLLM())
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

            self.assertEqual(turn.intent, "idea_turn")
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

    def test_handoff_copy_is_created_from_template(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "HANDOFF_TEMPLATE.md"
            output_dir = root / ".local"
            template.write_text(
                "# {project_name}\n\n{project_summary}\n\n{cohesion_score}\n{conversation_notes}\n",
                encoding="utf-8",
            )
            turn = DialogueTurn(
                question="What does it do?",
                user_answer="A tiny planning agent for ideas",
                bot_answer="So it helps you explain the idea first?",
                objectivity_score=80,
                idea_scores={
                    "cohesion_score": 80,
                    "complexity_score": 45,
                    "technicality_score": 55,
                    "feasibility_score": 70,
                },
                intent="objective_fact",
            )

            output_path = create_handoff_copy(
                "Tiny Planner\nA small agent for thinking through ideas.",
                [turn],
                template_path=template,
                output_dir=output_dir,
            )
            content = output_path.read_text(encoding="utf-8")

            self.assertTrue(output_path.exists())
            self.assertIn("Tiny Planner", content)
            self.assertIn("A tiny planning agent for ideas", content)
            self.assertIn("80", content)

    def test_summary_and_packing_are_separate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            storage = JsonlStorage(root / "data")
            context = ContextManager(storage=storage, llm=DummyLLM())
            template = root / "HANDOFF_TEMPLATE.md"
            output_dir = root / ".local"
            template.write_text(
                "# {project_name}\n\n{project_summary}\n\nGoal: {goal}\n",
                encoding="utf-8",
            )
            turns = [
                DialogueTurn(
                    question="What does it do?",
                    user_answer="A tiny planning agent for ideas",
                    bot_answer="So it helps you explain the idea first?",
                    objectivity_score=80,
                    idea_scores={
                        "cohesion_score": 80,
                        "complexity_score": 45,
                        "technicality_score": 55,
                        "feasibility_score": 70,
                    },
                    intent="idea_turn",
                )
            ]

            summary = save_summary(context, context.llm, turns)

            self.assertTrue(summary)
            self.assertFalse(output_dir.exists())

            handoff_path = save_packing(
                context,
                context.llm,
                turns,
                template_path=template,
                output_dir=output_dir,
            )

            self.assertTrue(handoff_path.exists())
            handoff = handoff_path.read_text(encoding="utf-8")
            self.assertIn("Python Excel parser", handoff)
            self.assertIn("Read Excel columns", handoff)

    def test_summary_prompt_includes_web_research_analysis(self) -> None:
        llm = DummyLLM()
        turns = [
            DialogueTurn(
                question="What does it do?",
                user_answer="A tiny planning agent for ideas",
                bot_answer="So it helps you explain the idea first?",
                objectivity_score=80,
                idea_scores={
                    "cohesion_score": 80,
                    "complexity_score": 45,
                    "technicality_score": 55,
                    "feasibility_score": 70,
                },
                intent="idea_turn",
            )
        ]

        build_summary(
            llm,
            turns,
            web_research_analysis="External analysis says competitors already exist.",
        )

        self.assertIn("External analysis says competitors already exist.", llm.last_prompt)

    def test_parse_search_queries_from_json(self) -> None:
        queries = parse_search_queries(
            '{"queries":["python excel parser","excel to json python","python excel parser"]}'
        )

        self.assertEqual(queries, ["python excel parser", "excel to json python"])

    def test_web_page_analysis_uses_fetched_page_text(self) -> None:
        llm = DummyLLM()
        analysis = analyze_web_pages(
            llm,
            ["python excel parser"],
            [
                WebSearchResult(
                    title="openpyxl docs",
                    url="https://example.com/openpyxl",
                    snippet="Read and write Excel files.",
                )
            ],
            [
                WebPageText(
                    title="openpyxl",
                    url="https://example.com/openpyxl",
                    text="openpyxl can read xlsx files and access worksheets, rows, and cells.",
                )
            ],
        )

        self.assertIn("openpyxl", llm.last_prompt)
        self.assertIn("xlsx files", llm.last_prompt)
        self.assertIn("External page analysis", analysis)

    def test_little_director_selects_modes_by_objectivity(self) -> None:
        self.assertEqual(build_prompt_little_director(20).mode, "idea_grounding")
        self.assertEqual(build_prompt_little_director(70).mode, "idea_clarification")
        self.assertEqual(build_prompt_little_director(90).mode, "idea_stress_test")

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

        self.assertIn("Director mode: idea_stress_test", llm.last_prompt)
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
