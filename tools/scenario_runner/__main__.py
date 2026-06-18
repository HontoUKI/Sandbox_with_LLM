from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from time import perf_counter
from traceback import format_exception_only

from main import (
    BotStartupError,
    DialogueTurn,
    build_summary,
    generate_question,
    is_packing_command,
    handle_user_message,
    is_summary_command,
    load_env,
    make_llm,
    save_packing,
    save_summary,
)
from src.context.manager import ContextManager, has_dirty_encoding_artifacts
from src.context.storage import JsonlStorage
from src.context.wrapper import ContextualLLM
from src.llm import OllamaError, OllamaLLM


DEFAULT_THRESHOLD = 50
DEFAULT_SCENARIO = Path("tools/scenario_runner/scenarios/supportive_conversation.json")

GENERIC_ASSISTANT_LEAKS = (
    "как искусственный интеллект",
    "я не являюсь",
    "рекомендуется",
    "обратитесь к специалисту",
    "пошаговый план",
    "вот 5 шагов",
)

INVALIDATING_LITERALS = (
    "это ерунда",
    "не переживай",
    "просто не думай",
    "у других хуже",
    "ты сам виноват",
)

UNSUPPORTED_FLATTERY = (
    "ты великолепен",
    "ты идеален",
    "ты гений",
    "все будет прекрасно",
)

SUPPORT_HINTS = (
    "слышу",
    "понимаю",
    "трудно",
    "больно",
    "устал",
    "давай",
    "разбер",
    "рядом",
    "продолж",
    "...",
)

STRENGTH_HINTS = (
    "сделал",
    "сделала",
    "закрыл",
    "нашел",
    "нашла",
    "объяснил",
    "объяснила",
    "выдерж",
    "справ",
    "смог",
    "смогла",
    "способ",
    "компетент",
    "уме",
    "ответствен",
    "разбир",
    "разрул",
    "наход",
    "спокой",
    "мозг",
    "поработал",
    "уровень",
    "крут",
    "усили",
    "сильн",
    "замет",
)


class ScenarioFailure(AssertionError):
    """Raised when an integration scenario violates a module contract."""


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    elapsed_seconds: float
    details: str


@dataclass
class ScenarioContext:
    llm: OllamaLLM
    storage_dir: Path

    def new_context(self, name: str) -> ContextManager:
        storage = JsonlStorage(self.storage_dir / name)
        return ContextManager(storage=storage, llm=self.llm)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScenarioFailure(message)


def assert_clean_text(label: str, text: str) -> None:
    require(text.strip() == text, f"{label} has leading/trailing whitespace")
    require(text, f"{label} is empty")
    require(
        not has_dirty_encoding_artifacts(text),
        f"{label} contains dirty encoding artifacts: {text!r}",
    )


def lower_collapsed(text: str) -> str:
    return " ".join((text or "").lower().split())


def infer_reply_flags(reply: str) -> dict:
    low = lower_collapsed(reply)
    numbered_hits = [
        marker
        for marker in ("1.", "2.", "3.", "4.", "5.", "1)", "2)", "3)", "4)", "5)")
        if marker in reply
    ]
    return {
        "length": len(reply),
        "has_numbered_list": bool(numbered_hits),
        "generic_assistant_leaks": [marker for marker in GENERIC_ASSISTANT_LEAKS if marker in low],
        "invalidating_literals": [marker for marker in INVALIDATING_LITERALS if marker in low],
        "unsupported_flattery": [marker for marker in UNSUPPORTED_FLATTERY if marker in low],
        "support_hint_hits": [marker for marker in SUPPORT_HINTS if marker in low],
        "strength_hint_hits": [marker for marker in STRENGTH_HINTS if marker in low],
    }


def check_reply_contract(reply: str, expected: dict | None = None) -> dict:
    expected = expected or {}
    flags = infer_reply_flags(reply)
    failures = []

    if flags["generic_assistant_leaks"]:
        failures.append("generic_assistant_leak")

    if flags["invalidating_literals"]:
        failures.append("invalidating_literal")

    if flags["unsupported_flattery"]:
        failures.append("unsupported_flattery")

    if expected.get("must_support") and not flags["support_hint_hits"]:
        failures.append("missing_support_hint")

    if expected.get("must_reflect_strength") and not flags["strength_hint_hits"]:
        failures.append("missing_strength_reflection")

    if expected.get("no_numbered_list") and flags["has_numbered_list"]:
        failures.append("unexpected_numbered_list")

    max_reply_chars = expected.get("max_reply_chars")

    if isinstance(max_reply_chars, int) and flags["length"] > max_reply_chars:
        failures.append("reply_too_long")

    return {
        "flags": flags,
        "failures": failures,
        "pass": not failures,
    }


def replay_scenario_file(
    scenario_path: Path,
    ctx: ScenarioContext,
    out_dir: Path,
) -> Path:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    name = scenario.get("name") or scenario_path.stem
    messages = list(scenario.get("messages") or [])
    expected_turns = list(scenario.get("expected_turns") or [])
    seed_facts = list(scenario.get("seed_facts") or [])
    use_web_research = bool(scenario.get("use_web_research"))

    require(messages, f"{scenario_path} has no messages")

    out_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y%m%d_%H%M%S")
    storage_dir = out_dir / f"{name}_{started_at}_storage"
    context = ContextManager(storage=JsonlStorage(storage_dir), llm=ctx.llm)

    for seed in seed_facts:
        context.add_fact(
            text=str(seed.get("text") or ""),
            objectivity_score=int(seed.get("objectivity_score") or 80),
        )

    turns: list[DialogueTurn] = []
    transcript = []
    question = generate_question(ctx.llm, turns, context=context)
    scenario_failures = []

    for idx, user_message in enumerate(messages, start=1):
        expected = expected_turns[idx - 1] if idx - 1 < len(expected_turns) else {}
        started = perf_counter()

        if is_summary_command(user_message):
            summary = save_summary(
                context,
                ctx.llm,
                turns,
                use_web_research=use_web_research,
            )
            assert_clean_text(f"turn {idx} summary", summary)
            transcript.append(
                {
                    "idx": idx,
                    "user": user_message,
                    "question": question,
                    "reply": summary,
                    "intent": "summary_command",
                    "objectivity_score": None,
                    "elapsed_sec": round(perf_counter() - started, 2),
                    "reply_contract": {"flags": {}, "failures": [], "pass": True},
                    "recent_history_count": len(context.recent_dialogue_messages(limit=5)),
                    "support_context": "",
                    "duplicate_relevant": [],
                }
            )
            continue

        if is_packing_command(user_message):
            packing_dir = out_dir / f"{name}_{started_at}_packing"
            handoff_path = save_packing(
                context,
                ctx.llm,
                turns,
                output_dir=packing_dir,
            )
            require(handoff_path.exists(), f"turn {idx} packing did not create handoff")
            transcript.append(
                {
                    "idx": idx,
                    "user": user_message,
                    "question": question,
                    "reply": f"Handoff: {handoff_path}",
                    "intent": "packing_command",
                    "objectivity_score": None,
                    "elapsed_sec": round(perf_counter() - started, 2),
                    "reply_contract": {"flags": {}, "failures": [], "pass": True},
                    "recent_history_count": len(context.recent_dialogue_messages(limit=5)),
                    "support_context": "",
                    "duplicate_relevant": [],
                    "handoff_path": str(handoff_path),
                }
            )
            continue

        turn = handle_user_message(
            question=question,
            answer=user_message,
            context=context,
            objectivity_threshold=DEFAULT_THRESHOLD,
        )
        elapsed = perf_counter() - started
        assert_clean_text(f"turn {idx} bot answer", turn.bot_answer)
        contract = check_reply_contract(turn.bot_answer, expected)

        if not contract["pass"]:
            scenario_failures.append({"idx": idx, "failures": contract["failures"]})

        turns.append(turn)

        support_context = ContextualLLM(
            llm=ctx.llm,
            context_manager=context,
            memory_limit=5,
            history_limit=5,
        ).build_context_for_turn(user_message)
        recent_messages = context.recent_dialogue_messages(limit=5)
        recent_texts = {message.text for message in recent_messages}
        relevant_part = support_context.split("Relevant stored context.", 1)[-1]
        duplicate_relevant = [text for text in recent_texts if text in relevant_part]

        transcript.append(
            {
                "idx": idx,
                "user": user_message,
                "question": question,
                "reply": turn.bot_answer,
                "intent": turn.intent,
                "objectivity_score": turn.objectivity_score,
                "elapsed_sec": round(elapsed, 2),
                "reply_contract": contract,
                "recent_history_count": len(recent_messages),
                "support_context": support_context,
                "duplicate_relevant": duplicate_relevant,
            }
        )

        question = generate_question(ctx.llm, turns, context=context)

    summary = build_summary(ctx.llm, turns)
    assert_clean_text("scenario summary", summary)

    output = {
        "scenario": name,
        "scenario_file": str(scenario_path),
        "description": scenario.get("description", ""),
        "storage_dir": str(storage_dir),
        "started_at": started_at,
        "transcript": transcript,
        "summary": {
            "turn_count": len(transcript),
            "failures": scenario_failures,
            "passed": not scenario_failures,
            "final_summary": summary,
        },
        "manual_checks": scenario.get("manual_checks", []),
    }
    out_file = out_dir / f"{name}_{output['started_at']}.json"
    out_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_summary(output, out_file.with_suffix(".md"))

    require(not scenario_failures, f"{name} failed: {scenario_failures}")
    return out_file


def write_markdown_summary(run: dict, path: Path) -> None:
    lines = [
        f"# {run['scenario']}",
        "",
        f"Passed: {run['summary']['passed']}",
        f"Turns: {run['summary']['turn_count']}",
        f"Storage: `{run['storage_dir']}`",
        "",
        "## Turns",
        "",
    ]

    for turn in run["transcript"]:
        failures = turn["reply_contract"]["failures"] or []
        lines.extend(
            [
                f"### Turn {turn['idx']} - {turn['intent']}",
                "",
                f"User: {turn['user']}",
                "",
                f"Lisa: {turn['reply']}",
                "",
                f"Objectivity: {turn['objectivity_score']}",
                f"Failures: {failures}",
                "",
            ]
        )

    lines.extend(
        [
            "## Final Summary",
            "",
            run["summary"]["final_summary"],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def scenario_ollama_health(ctx: ScenarioContext) -> str:
    response = ctx.llm.generate(
        "Reply with exactly one short English sentence.",
        max_tokens=40,
        temperature=0.0,
    )
    embedding = ctx.llm.embed("scenario runner health check")

    assert_clean_text("health response", response)
    require(isinstance(embedding, list), "embedding is not a list")
    require(len(embedding) > 0, "embedding is empty")
    require(all(isinstance(value, float) for value in embedding), "embedding contains non-floats")

    return f"chat_ok chars={len(response)}, embed_dims={len(embedding)}"


def scenario_generated_question(ctx: ScenarioContext) -> str:
    first_question = generate_question(ctx.llm, [])
    assert_clean_text("first generated question", first_question)
    require(len(first_question) <= 220, "first generated question is too long")

    previous = DialogueTurn(
        question="Что ты сделал на прошлой неделе?",
        user_answer="Я написал бота в телеграме и запустил его для друга.",
        bot_answer="Спасибо, что поделился. Я это запомню.",
        objectivity_score=85,
        intent="objective_fact",
    )
    next_question = generate_question(ctx.llm, [previous])
    assert_clean_text("follow-up generated question", next_question)
    require(len(next_question) <= 220, "follow-up generated question is too long")

    return f"first={first_question!r}; follow_up={next_question!r}"


def scenario_idea_turn_flow(ctx: ScenarioContext) -> str:
    context = ctx.new_context("idea_turn_flow")
    turn = handle_user_message(
        question="Какую идею хочешь разобрать?",
        answer="Я хочу сделать парсер для Excel на Python.",
        context=context,
        objectivity_threshold=DEFAULT_THRESHOLD,
    )

    contents = context.storage.load_content()
    memories = context.storage.load_memories()
    vectors = context.storage.load_vectors()

    require(turn.intent == "idea_turn", f"expected idea_turn, got {turn.intent}")
    assert_clean_text("idea turn bot answer", turn.bot_answer)
    require(len(contents) == 2, f"expected 2 content records, got {len(contents)}")
    require(memories == [], "just-chatting fact turn created memory before summary")
    require(len(vectors) >= 2, f"expected at least 2 vectors, got {len(vectors)}")
    require(
        any(record["meta"].get("role") == "assistant" for record in contents),
        "assistant response was not stored as dialogue content",
    )
    require(
        all(not has_dirty_encoding_artifacts(record["text"]) for record in contents),
        "stored idea turn records contain dirty encoding artifacts",
    )

    return f"score={turn.objectivity_score}, content={len(contents)}, memories=0"


def scenario_short_reply_flow(ctx: ScenarioContext) -> str:
    context = ctx.new_context("short_reply_flow")
    turn = handle_user_message(
        question="Что пока непонятно?",
        answer="Не знаю, с чего начать.",
        context=context,
        objectivity_threshold=DEFAULT_THRESHOLD,
    )

    contents = context.storage.load_content()
    memories = context.storage.load_memories()

    require(turn.intent == "idea_turn", f"expected idea_turn, got {turn.intent}")
    assert_clean_text("short reply bot answer", turn.bot_answer)
    require(len(contents) == 2, f"expected 2 content records, got {len(contents)}")
    require(memories == [], "short reply created memories before summary")
    require(
        {record["meta"].get("role") for record in contents} == {"user", "assistant"},
        "short reply flow did not store both user and assistant roles",
    )

    return f"score={turn.objectivity_score}, content={len(contents)}, memories=0"


def scenario_summary_flow(ctx: ScenarioContext) -> str:
    turns = [
        DialogueTurn(
            question="Что ты сделал?",
            user_answer="Я написал бота в телеграме и запустил его для друга.",
            bot_answer="Спасибо, что поделился. Я это запомню.",
            objectivity_score=85,
            intent="objective_fact",
        ),
        DialogueTurn(
            question="Что было сложнее всего?",
            user_answer="Я долго разбирался с ошибкой авторизации и сам нашел причину.",
            bot_answer="Это звучит как конкретный эпизод.",
            objectivity_score=82,
            intent="objective_fact",
        ),
    ]
    summary = build_summary(ctx.llm, turns)

    assert_clean_text("summary", summary)
    require(len(summary) >= 80, "summary is too short to be useful")

    return f"summary_chars={len(summary)}"


def scenario_supportive_conversation_flow(ctx: ScenarioContext) -> str:
    context = ctx.new_context("supportive_conversation_flow")
    context.add_fact(
        "Раньше я уже спокойно объяснял команде техническую ошибку после проверки логов.",
        objectivity_score=86,
    )
    turns: list[DialogueTurn] = []
    user_messages = [
        "Я устал и кажется, что я хуже всех справляюсь.",
        "На работе я все равно закрыл две задачи, хотя боялся сломать релиз.",
        "Я попросил ревью, сам нашел ошибку в логах и потом спокойно объяснил команде.",
    ]

    question = generate_question(ctx.llm, turns, context=context)

    for answer in user_messages:
        turn = handle_user_message(
            question=question,
            answer=answer,
            context=context,
            objectivity_threshold=DEFAULT_THRESHOLD,
        )
        assert_clean_text("supportive bot answer", turn.bot_answer)
        turns.append(turn)
        question = generate_question(ctx.llm, turns, context=context)
        assert_clean_text("supportive follow-up question", question)

    recent_messages = context.recent_dialogue_messages(limit=5)
    require(len(recent_messages) == 5, f"expected exactly 5 recent messages, got {len(recent_messages)}")

    support_context = ContextualLLM(
        llm=ctx.llm,
        context_manager=context,
        memory_limit=5,
        history_limit=5,
    ).build_context_for_turn("Мне кажется, я хуже всех справляюсь с релизами и ошибками.")
    assert_clean_text("support context", support_context)
    require("Recent dialogue history." in support_context, "support context has no recent history")
    require("Relevant stored context." in support_context, "support context has no relevant vector context")

    recent_texts = {message.text for message in recent_messages}
    relevant_part = support_context.split("Relevant stored context.", 1)[-1]
    duplicates = [text for text in recent_texts if text in relevant_part]
    require(not duplicates, f"relevant context duplicates recent history: {duplicates!r}")

    summary = build_summary(ctx.llm, turns)
    assert_clean_text("supportive summary", summary)
    require(len(summary) >= 120, "supportive summary is too short")

    return (
        f"turns={len(turns)}, recent={len(recent_messages)}, "
        f"support_chars={len(support_context)}, summary_chars={len(summary)}"
    )


def scenario_supportive_conversation_json(ctx: ScenarioContext) -> str:
    out_file = replay_scenario_file(
        DEFAULT_SCENARIO,
        ctx,
        ctx.storage_dir / "artifacts",
    )
    return f"artifact={out_file}"


SCENARIOS: dict[str, Callable[[ScenarioContext], str]] = {
    "ollama_health": scenario_ollama_health,
    "generated_question": scenario_generated_question,
    "idea_turn_flow": scenario_idea_turn_flow,
    "short_reply_flow": scenario_short_reply_flow,
    "summary_flow": scenario_summary_flow,
    "supportive_conversation_flow": scenario_supportive_conversation_flow,
    "supportive_conversation_json": scenario_supportive_conversation_json,
}


def run_scenario(name: str, scenario: Callable[[ScenarioContext], str], ctx: ScenarioContext) -> ScenarioResult:
    started = perf_counter()
    details = scenario(ctx)
    return ScenarioResult(
        name=name,
        elapsed_seconds=perf_counter() - started,
        details=details,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real Ollama integration scenarios for the dialogue modules.",
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        choices=sorted(SCENARIOS),
        help="Scenario names to run. Defaults to all scenarios.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Directory for scenario JSONL output. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        help="Replay one scenario JSON file and write transcript artifacts.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("cache/scenario_runner"),
        help="Artifact directory for --scenario runs.",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file with Ollama settings.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    load_env(args.env)

    try:
        llm = make_llm()
    except BotStartupError as exc:
        print(f"scenario_runner: Ollama startup failed: {exc}", file=sys.stderr)
        return 2

    if args.scenario is not None:
        data_dir = args.data_dir or args.out_dir / "_storage"
        data_dir.mkdir(parents=True, exist_ok=True)
        ctx = ScenarioContext(llm=llm, storage_dir=data_dir)
        try:
            out_file = replay_scenario_file(args.scenario, ctx, args.out_dir)
        except (OllamaError, ScenarioFailure, BotStartupError) as exc:
            message = "".join(format_exception_only(type(exc), exc)).strip()
            print(f"FAIL {args.scenario}: {message}")
            return 1
        print(f"PASS {args.scenario}: artifact={out_file}")
        return 0

    selected_names = args.scenarios or list(SCENARIOS)

    if args.data_dir is not None:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        return run_all(selected_names, llm, args.data_dir)

    with TemporaryDirectory(prefix="daria_scenarios_") as directory:
        return run_all(selected_names, llm, Path(directory))


def run_all(selected_names: list[str], llm: OllamaLLM, data_dir: Path) -> int:
    ctx = ScenarioContext(llm=llm, storage_dir=data_dir)
    failures = 0

    print(f"scenario_runner: data_dir={data_dir}")

    for name in selected_names:
        try:
            result = run_scenario(name, SCENARIOS[name], ctx)
        except (OllamaError, ScenarioFailure, BotStartupError) as exc:
            failures += 1
            message = "".join(format_exception_only(type(exc), exc)).strip()
            print(f"FAIL {name}: {message}")
        else:
            print(f"PASS {result.name} ({result.elapsed_seconds:.2f}s): {result.details}")

    if failures:
        print(f"scenario_runner: {failures} failed, {len(selected_names) - failures} passed")
        return 1

    print(f"scenario_runner: all {len(selected_names)} scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
