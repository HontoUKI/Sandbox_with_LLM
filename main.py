from dataclasses import dataclass
import os
from pathlib import Path
from random import choice
import sys

from src.context.manager import ContextManager
from src.llm import OllamaError, OllamaLLM


if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class Fact:
    prompt: str
    answer: str
    objectivity_score: int


QUESTIONS = [
    "Назови ситуацию, где ты сделал(а) что-то трудное, хотя никто не заставлял.",
    "Что ты умеешь замечать быстрее или тоньше, чем большинство людей рядом?",
    "Какую проблему ты когда-то решил(а) неидеально, но самостоятельно?",
    "За что к тебе реально обращались другие люди? Не за 'поддержкой вообще', а конкретно.",
    "Какое качество ты считаешь обычным, но оно стабильно помогает тебе вывозить?",
    "Где ты однажды выдержал(а) больше, чем сам(а) от себя ожидал(а)?",
]

COLD_REFLECTIONS = [
    "Это не 'повезло'. В ответе есть действие, выбор и повторяемый навык.",
    "Скромность тут не добавляет точности. Факт уже прозвучал.",
    "Если это было бы совсем обычно, ты бы не смог(ла) описать такой конкретный эпизод.",
    "Не нужно превращать это в героизм. Достаточно признать: это твоя рабочая способность.",
]

WARM_REFLECTIONS = [
    "Похоже, ты привык(ла) обесценивать то, что у тебя получается без театра.",
    "Здесь видна не случайная удача, а способ обращаться с реальностью.",
    "Это звучит как часть личности, которую ты используешь, но редко называешь ценностью.",
    "В этом есть нетривиальность: ты не просто пережил(а) ситуацию, ты что-то из нее сделал(а).",
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
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            timeout=env_float("OLLAMA_TIMEOUT", 2.0),
        )
        llm.generate("Ответь одним словом: ok", max_tokens=4, temperature=0.0)
        return llm
    except OllamaError:
        return None


def ask_fact(prompt: str, context: ContextManager, objectivity_threshold: int) -> Fact:
    print(f"\n{prompt}")
    answer = input("> ").strip()
    objectivity_score = context.objectivity_score(answer)

    while len(answer) < 8 or objectivity_score < objectivity_threshold:
        print("Слишком общо. Дай один конкретный факт: действие, ситуация, результат.")
        answer = input("> ").strip()
        objectivity_score = context.objectivity_score(answer)

    context.ingest_user_content(
        text=answer,
        prompt=prompt,
        objectivity_score=objectivity_score,
    )

    return Fact(
        prompt=prompt,
        answer=answer,
        objectivity_score=objectivity_score,
    )


def reflect_on_fact(fact: Fact, index: int) -> str:
    reflection_pool = COLD_REFLECTIONS if index % 3 == 1 else WARM_REFLECTIONS
    return f"{choice(reflection_pool)} Объективность факта: {fact.objectivity_score}/100."


def build_portrait(facts: list[Fact]) -> str:
    fragments = []

    for fact in facts:
        fragments.append(f"- {fact.answer} [{fact.objectivity_score}/100]")

    return (
        "\nПортрет по фактам, без украшений:\n"
        "Ты не пустое место и не набор случайных провалов. В твоих ответах повторяется "
        "способность действовать, замечать, выдерживать и быть полезным(ой) не только в "
        "простых условиях. Это не обязано выглядеть эффектно, чтобы быть реальным.\n\n"
        "Факты, на которые теперь нельзя честно не смотреть:\n"
        + "\n".join(fragments)
    )


def run_bot() -> None:
    load_env()
    print("Бот объективной самооценки")
    print("Отвечай конкретными фактами. Не 'я добрый', а 'я сделал вот это'.")
    print("Можно писать коротко. Главное - без самоуменьшения.")

    llm = make_llm()
    context = ContextManager(llm=llm)
    objectivity_threshold = env_int("OBJECTIVITY_THRESHOLD", 45)
    facts = []

    for index, question in enumerate(QUESTIONS, start=1):
        fact = ask_fact(question, context, objectivity_threshold)
        facts.append(fact)
        print(reflect_on_fact(fact, index))

    print(build_portrait(facts))
    print("\nКонтрольный вопрос: какой из этих фактов ты чаще всего выкидываешь из оценки себя?")


if __name__ == "__main__":
    run_bot()
