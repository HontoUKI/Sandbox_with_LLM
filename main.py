from dataclasses import dataclass
import os
from pathlib import Path
import sys

from src.context.build_prompt_little_director import build_director_prompt_block
from src.context.dialogue_intent import (
    build_response_for_intent,
    classify_user_message,
)
from src.context.manager import ContextManager
from src.context.wrapper import ContextualLLM
from src.llm import OllamaError, OllamaLLM


if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SUMMARY_COMMAND = "/summary"
EXIT_COMMANDS = {"/exit", "/quit"}


@dataclass
class DialogueTurn:
    question: str
    user_answer: str
    bot_answer: str
    objectivity_score: int
    intent: str = "conversation"


class BotStartupError(RuntimeError):
    """Raised when required runtime services are unavailable."""


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


def make_llm() -> OllamaLLM:
    llm = OllamaLLM(
        model=os.getenv("OLLAMA_MODEL", "llama3"),
        embedding_model=os.getenv(
            "EMBED_MODEL",
            os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        ),
        host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        chat_url=os.getenv("OLLAMA_CHAT"),
        embed_url=os.getenv("OLLAMA_EMBED"),
        timeout=env_float("OLLAMA_TIMEOUT", 120.0),
    )

    try:
        llm.generate("Reply with one word: ok", max_tokens=4, temperature=0.0)
    except OllamaError as exc:
        raise BotStartupError(
            "Ollama is unavailable or the model is not responding. "
            f"Details: {exc}"
        ) from exc

    return llm


def is_summary_command(text: str) -> bool:
    return text.strip().lower() == SUMMARY_COMMAND


def is_exit_command(text: str) -> bool:
    return text.strip().lower() in EXIT_COMMANDS


def generate_question(
    llm: OllamaLLM,
    turns: list[DialogueTurn],
    context: ContextManager | None = None,
) -> str:
    previous_turn = turns[-1] if turns else None

    if not turns:
        prompt = (
            "Ты Дарья. Начинаешь живой разговор. Спроси один короткий теплый вопрос, "
            "как подруга, которой правда интересно. Без анкеты и без делового тона. "
            "Можно звучать чуть неидеально, по-человечески. На русском."
        )
    else:
        director_block = build_director_prompt_block(
            previous_turn.objectivity_score if previous_turn else None,
            previous_turn.user_answer if previous_turn else "",
        )
        support_context = ""
        history_context = "История разговора уже дана в блоке опоры выше."

        if context is not None:
            support_context = ContextualLLM(
                llm=llm,
                context_manager=context,
                memory_limit=5,
                history_limit=5,
            ).build_context_for_turn(previous_turn.user_answer)
        else:
            history = "\n".join(
                (
                    f"Q: {turn.question}\n"
                    f"You: {turn.user_answer}\n"
                    f"I said: {turn.bot_answer}"
                )
                for turn in turns[-5:]
            )
            history_context = f"История разговора:\n{history}"

        prompt = (
            "Ты Дарья. Ведешь живой разговор, не интервью. "
            "Слушаешь, иногда можешь помолчать в тексте, не обязана каждый раз вытаскивать факт. "
            "Можно мягко ругнуться вроде 'блин' или 'черт', если это звучит естественно, "
            "но не оскорбляй пользователя и не дави.\n\n"
            "Следующий ход должен быть одним коротким вопросом или очень коротким ожиданием, "
            "например: '... я рядом. продолжай.'\n"
            "Не используй списки. Не объясняй, что ты делаешь.\n\n"
            f"{director_block}\n\n"
            f"Опора из памяти и последних сообщений:\n{support_context or 'Пока нет сохраненной опоры.'}\n\n"
            f"{history_context}\n\n"
            "Мой следующий ход:"
        )

    try:
        question = llm.generate(prompt, max_tokens=120, temperature=0.55).strip()
    except OllamaError as exc:
        raise BotStartupError(f"Could not generate the next question through LLM. Details: {exc}") from exc

    question = question.strip().strip('"')

    if not question or len(question) > 260:
        raise BotStartupError("LLM returned an invalid question. Try again.")

    return question


def handle_user_message(
    question: str,
    answer: str,
    context: ContextManager,
    objectivity_threshold: int,
) -> DialogueTurn:
    objectivity_score = context.objectivity_score(answer)
    intent = classify_user_message(answer, objectivity_score, objectivity_threshold)
    fallback = build_response_for_intent(intent, objectivity_score)
    bot_answer = generate_bot_answer(
        question=question,
        answer=answer,
        context=context,
        intent_kind=intent.kind,
        objectivity_score=objectivity_score,
        fallback=fallback,
    )

    user_content = context.add_dialogue_content(
        text=answer,
        prompt=question,
        bot_response=bot_answer,
        intent=intent.kind,
        objectivity_score=objectivity_score,
        role="user",
        use_extractor=False,
    )
    context.add_dialogue_content(
        text=bot_answer,
        prompt=question,
        intent=f"{intent.kind}_response",
        objectivity_score=objectivity_score,
        source="assistant_response",
        role="assistant",
        linked_content_id=user_content["id"],
        use_extractor=False,
    )

    return DialogueTurn(
        question=question,
        user_answer=answer,
        bot_answer=bot_answer,
        objectivity_score=objectivity_score,
        intent=intent.kind,
    )


def generate_bot_answer(
    question: str,
    answer: str,
    context: ContextManager,
    intent_kind: str,
    objectivity_score: int,
    fallback: str,
) -> str:
    if context.llm is None:
        return fallback

    support_context = ContextualLLM(
        llm=context.llm,
        context_manager=context,
        memory_limit=5,
        history_limit=5,
    ).build_context_for_turn(answer)
    prompt = (
        "Ты Дарья. Отвечаешь человеку в живом диалоге.\n"
        "Тон: близко, мягко, честно, иногда чуть грубо по-живому. "
        "Можно редко использовать мягкий мат: 'блин', 'черт', 'пиздец' - только если это уместно "
        "как сочувствие ситуации, не как оскорбление человека.\n"
        "Можно выдержать молчаливую паузу текстом: '...'. Можно сказать 'я рядом, продолжай'.\n"
        "Не превращай ответ в терапевтический шаблон, чеклист или лекцию. Не используй списки.\n"
        "Если человек себя занижает, помоги увидеть конкретное действие или качество, которое он уже показал.\n"
        "Ответь 1-3 короткими предложениями на русском.\n\n"
        f"Опора из памяти:\n{support_context}\n\n"
        f"Предыдущий ход Дарьи: {question}\n"
        f"Ответ пользователя: {answer}\n"
        f"Intent: {intent_kind}\n"
        f"Objectivity score: {objectivity_score}\n\n"
        "Ответ Дарьи:"
    )

    try:
        response = context.llm.generate(prompt, max_tokens=180, temperature=0.55).strip()
    except OllamaError:
        return fallback

    response = response.strip().strip('"')

    if not response or len(response) > 900 or has_multiline_list(response):
        return fallback

    return response


def has_multiline_list(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbered = 0

    for line in lines:
        if len(line) >= 2 and line[0].isdigit() and line[1] in {".", ")"}:
            numbered += 1

    return numbered >= 2


def ask_turn(
    question: str,
    context: ContextManager,
    objectivity_threshold: int,
) -> DialogueTurn:
    print(f"\n{question}")
    answer = input("> ").strip()
    turn = handle_user_message(question, answer, context, objectivity_threshold)
    print(turn.bot_answer)
    return turn


def build_summary(llm: OllamaLLM, turns: list[DialogueTurn]) -> str:
    raw_turns = "\n\n".join(
        "\n".join(
            [
                f"Q: {turn.question}",
                f"You: {turn.user_answer}",
                f"I: {turn.bot_answer}",
            ]
        )
        for turn in turns
    )

    prompt = (
        "Ты Дарья. Человек попросил /summary. Суммируешь живой разговор.\n\n"
        "Сначала коротко назови, что происходило эмоционально. "
        "Потом честно покажи, где человек лучше, чем сам сейчас считает. "
        "Опирайся только на сказанное в разговоре: действия, выдержку, выборы, способ думать, просьбы о помощи.\n"
        "Можно звучать живо и чуть шероховато, но без пустой мотивации и без лести. "
        "Не делай длинный список. Лучше 3-5 плотных абзацев.\n\n"
        f"Разговор:\n{raw_turns}"
    )

    try:
        return llm.generate(prompt, max_tokens=900, temperature=0.35).strip()
    except OllamaError as exc:
        raise BotStartupError(f"Could not build summary through LLM. Details: {exc}") from exc


def save_summary(context: ContextManager, llm: OllamaLLM, turns: list[DialogueTurn]) -> str:
    summary = build_summary(llm, turns)
    turn_records = [
        {
            "question": turn.question,
            "user_answer": turn.user_answer,
            "bot_answer": turn.bot_answer,
            "intent": turn.intent,
            "objectivity_score": turn.objectivity_score,
        }
        for turn in turns
    ]
    summary_record = context.add_summary(text=summary, turns=turn_records)
    context.extract_dialogue_summary_facts(
        turns=turn_records,
        source_summary_id=summary_record["id"],
    )
    return summary


def run_bot() -> None:
    load_env()
    print("Привет, я Дарья.")
    print("Давай без анкеты. Просто говори, что есть. Я рядом.")
    print(f"Когда захочешь итог - напиши {SUMMARY_COMMAND}. Выйти: /exit.")
    print()

    try:
        llm = make_llm()
    except BotStartupError as exc:
        print(f"\nОшибка запуска: {exc}")
        return

    context = ContextManager(llm=llm)
    objectivity_threshold = env_int("OBJECTIVITY_THRESHOLD", 50)
    turns: list[DialogueTurn] = []
    question = generate_question(llm, turns, context=context)

    while True:
        print(f"\n{question}")
        answer = input("> ").strip()

        if is_exit_command(answer):
            break

        if is_summary_command(answer):
            if not turns:
                print("Пока нечего суммировать. Скажи мне хоть пару фраз сначала.")
            else:
                summary = save_summary(context, llm, turns)
                print("\nSummary по диалогу:")
                print(summary)
                print("\nСохранила summary и извлекла факты из разговора.")
            question = "... я здесь. продолжим?"
            continue

        turn = handle_user_message(
            question=question,
            answer=answer,
            context=context,
            objectivity_threshold=objectivity_threshold,
        )
        turns.append(turn)
        print(turn.bot_answer)
        question = generate_question(llm, turns, context=context)


if __name__ == "__main__":
    run_bot()
