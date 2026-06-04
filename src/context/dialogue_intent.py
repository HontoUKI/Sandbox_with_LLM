from __future__ import annotations

from dataclasses import dataclass


BOUNDARY_MARKERS = (
    "не дави",
    "отстань",
    "стоп",
    "не хочу",
    "хватит",
    "пауза",
    "stop",
    "don't push",
)

SELF_DEPRECATION_MARKERS = (
    "я плох",
    "я туп",
    "я ничтож",
    "я ничего не",
    "у меня не получается",
    "я не умею",
    "я хуже",
    "бесполез",
    "тривиал",
    "туплю",
    "bad at everything",
    "worthless",
    "useless",
)

POSITIVE_MARKERS = (
    "получилось",
    "смог",
    "смогла",
    "сделал",
    "сделала",
    "выучил",
    "выучила",
    "сдал",
    "сдала",
    "помог",
    "помогла",
    "finished",
    "fixed",
    "handled",
    "solved",
)


@dataclass(frozen=True)
class DialogueIntent:
    kind: str
    should_store_fact: bool
    should_store_content: bool
    response_tone: str


def classify_user_message(
    text: str,
    objectivity_score: int,
    objectivity_threshold: int,
) -> DialogueIntent:
    lowered = text.lower().strip()

    if not lowered:
        return DialogueIntent("empty", False, True, "soft_pause")

    if any(marker in lowered for marker in BOUNDARY_MARKERS):
        return DialogueIntent("boundary", False, True, "respect_boundary")

    if any(marker in lowered for marker in SELF_DEPRECATION_MARKERS):
        return DialogueIntent("self_deprecation", False, True, "grounded_support")

    if objectivity_score >= objectivity_threshold:
        return DialogueIntent("objective_fact", True, True, "fact_reflection")

    if any(marker in lowered for marker in POSITIVE_MARKERS):
        return DialogueIntent("positive_signal", False, True, "positive_to_fact")

    return DialogueIntent("conversation", False, True, "open_conversation")


def build_response_for_intent(
    intent: DialogueIntent,
    objectivity_score: int,
) -> str:
    if intent.response_tone == "respect_boundary":
        return "Ок, я слышу. Не буду давить. ... я рядом, если захочешь продолжить."

    if intent.response_tone == "soft_pause":
        return "... не спешим. Можешь просто посидеть со мной в этом пару секунд."

    if intent.response_tone == "grounded_support":
        return (
            "Блин, звучит тяжело. Я не буду спорить с твоим чувством, "
            "но давай держаться за то, что реально произошло."
        )

    if intent.response_tone == "positive_to_fact":
        return "Вот это уже что-то живое. Что именно ты сделал(а), когда начало получаться?"

    if intent.response_tone == "fact_reflection":
        return "Я это слышу. И, черт, это не выглядит как пустяк."

    return "... я слушаю. Продолжай, если можешь."
