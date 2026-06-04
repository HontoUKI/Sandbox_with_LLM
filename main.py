from dataclasses import dataclass
import os
from pathlib import Path
from random import choice
import sys

from src.context.build_prompt_little_director import build_director_prompt_block
from src.context.manager import ContextManager
from src.llm import OllamaError, OllamaLLM


if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class DialogueTurn:
    question: str
    user_answer: str
    bot_answer: str
    objectivity_score: int


FALLBACK_QUESTIONS = [
    "Вспомни один эпизод, где ты сделал(а) что-то трудное без внешнего давления. Что именно ты сделал(а)?",
    "Где твоя наблюдательность дала практический результат? Назови ситуацию, не качество.",
    "Какую проблему ты решил(а) сам(а), пусть даже неидеально? Что было на выходе?",
    "С чем к тебе реально приходили другие люди? Назови запрос и что ты сделал(а).",
    "Когда ты продолжил(а) работу, хотя было физически или эмоционально тяжело? Что было сделано?",
]

COLD_REFLECTIONS = [
    "Это уже ближе к факту: есть действие, ситуация и след.",
    "Без украшений: это можно сохранить как наблюдаемое свидетельство.",
    "Здесь меньше самооценки и больше материала, с которым можно работать.",
    "Не героизируем. Просто фиксируем: это произошло, и ты там действовал(а).",
]

WARM_REFLECTIONS = [
    "Это похоже на часть опыта, которую ты обычно не засчитываешь себе.",
    "В этом есть опора: не настроение, а конкретный эпизод.",
    "Такой ответ уже можно использовать как доказательство, а не как комплимент.",
    "Здесь видно действие, а не только отношение к себе.",
]


def load_env(path: str = ".env") -> None:
    env_path = Path(path)

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def make_llm() -> OllamaLLM | None:
    try:
        llm = OllamaLLM(
            model=os.getenv("OLLAMA_MODEL", "llama3"),
            embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            timeout=env_float("OLLAMA_TIMEOUT", 2.0),
        )
        llm.generate("Reply with one word: ok", max_tokens=4, temperature=0.0)
        return llm
    except OllamaError:
        return None


def generate_question(llm: OllamaLLM | None, turns: list[DialogueTurn]) -> str:
    fallback = FALLBACK_QUESTIONS[min(len(turns), len(FALLBACK_QUESTIONS) - 1)]

    if llm is None:
        return fallback

    previous_turn = turns[-1] if turns else None
    director_block = build_director_prompt_block(
        previous_turn.objectivity_score if previous_turn else None,
        previous_turn.user_answer if previous_turn else "",
    )
    history = "\n".join(
        f"Q: {turn.question}\nUser: {turn.user_answer}\nScore: {turn.objectivity_score}/100"
        for turn in turns
    )
    prompt = (
        "Ты задаешь вопросы для бота объективной самооценки.\n"
        "Задай ОДИН короткий вопрос на русском языке.\n"
        "Цель: вытащить конкретный наблюдаемый факт о пользователе: действие, ситуация, результат.\n"
        "Не проси качество характера. Не утешай. Не используй списки.\n\n"
        f"{director_block}\n\n"
        f"История:\n{history or 'Пока пусто.'}\n\n"
        "Следующий вопрос:"
    )

    try:
        question = llm.generate(prompt, max_tokens=120, temperature=0.4).strip()
    except OllamaError:
        return fallback

    question = question.strip().strip('"')

    if not question or "\n" in question or len(question) > 220:
        return fallback

    return question


def build_reflection(turn_index: int, objectivity_score: int) -> str:
    reflection_pool = COLD_REFLECTIONS if turn_index % 2 == 0 else WARM_REFLECTIONS
    return f"{choice(reflection_pool)} Meta объективности: {objectivity_score}/100."


def ask_turn(
    question: str,
    context: ContextManager,
    objectivity_threshold: int,
    turn_index: int,
) -> DialogueTurn:
    print(f"\n{question}")
    answer = input("> ").strip()
    objectivity_score = context.objectivity_score(answer)

    while len(answer) < 8 or objectivity_score < objectivity_threshold:
        print(
            "Это пока не факт. Нужен один эпизод: что случилось, что ты сделал(а), "
            "какой был результат."
        )
        answer = input("> ").strip()
        objectivity_score = context.objectivity_score(answer)

    bot_answer = build_reflection(turn_index, objectivity_score)
    context.ingest_user_content(
        text=answer,
        prompt=question,
        objectivity_score=objectivity_score,
    )

    print(bot_answer)
    return DialogueTurn(
        question=question,
        user_answer=answer,
        bot_answer=bot_answer,
        objectivity_score=objectivity_score,
    )


def build_summary(llm: OllamaLLM | None, turns: list[DialogueTurn]) -> str:
    raw_turns = "\n\n".join(
        "\n".join(
            [
                f"Вопрос: {turn.question}",
                f"User сказал: {turn.user_answer}",
                f"Ты ответил: {turn.bot_answer}",
                f"Meta объективности: {turn.objectivity_score}/100",
            ]
        )
        for turn in turns
    )

    fallback = (
        "Summary after 5 turns\n\n"
        f"{raw_turns}\n\n"
        "Короткий анализ: в ответах нужно отделять реальные эпизоды от самоописаний. "
        "Сохранять стоит только то, где есть действие, ситуация и результат."
    )

    if llm is None:
        return fallback

    prompt = (
        "Сделай короткое summary пяти ходов диалога для разработчика и следующего LLM-запроса.\n"
        "Формат каждого пункта сохраняй близко к:\n"
        "User сказал:\nТы ответил:\nMeta объективности:\n"
        "После пунктов добавь 3 строки анализа: сильные факты, слабые места, следующий фокус.\n"
        "Не добавляй выдуманных фактов и не льсти.\n\n"
        f"{raw_turns}"
    )

    try:
        return llm.generate(prompt, max_tokens=700, temperature=0.2).strip()
    except OllamaError:
        return fallback


def save_summary(context: ContextManager, llm: OllamaLLM | None, turns: list[DialogueTurn]) -> str:
    summary = build_summary(llm, turns)
    context.add_summary(
        text=summary,
        turns=[
            {
                "question": turn.question,
                "user_answer": turn.user_answer,
                "bot_answer": turn.bot_answer,
                "objectivity_score": turn.objectivity_score,
            }
            for turn in turns
        ],
    )
    return summary


def run_bot() -> None:
    load_env()
    print("Бот объективной самооценки")
    print("Отвечай конкретными фактами. Не 'я добрый', а 'я сделал вот это'.")
    print("Можно писать коротко. Главное - без самоуменьшения.")

    llm = make_llm()
    context = ContextManager(llm=llm)
    objectivity_threshold = env_int("OBJECTIVITY_THRESHOLD", 50)
    question_count = env_int("QUESTION_COUNT", 5)
    turns = []

    for turn_index in range(1, question_count + 1):
        question = generate_question(llm, turns)
        turn = ask_turn(question, context, objectivity_threshold, turn_index)
        turns.append(turn)

    summary = save_summary(context, llm, turns)
    print("\nSummary по 5 ответам:")
    print(summary)
    print("\nСохранено в user_data: content.jsonl, memories.jsonl, vectors.jsonl, summaries.jsonl.")


if __name__ == "__main__":
    run_bot()
