from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DirectorInstruction:
    mode: str
    question_goal: str
    constraints: tuple[str, ...]

    def as_prompt_block(self) -> str:
        constraints = "\n".join(f"- {constraint}" for constraint in self.constraints)
        return (
            f"Director mode: {self.mode}\n"
            f"Next question goal: {self.question_goal}\n"
            f"Constraints:\n{constraints}"
        )


def build_prompt_little_director(
    objectivity_score: int,
    previous_answer: str = "",
) -> DirectorInstruction:
    """
    Decide how the next question should be shaped.

    Low objectivity means the user needs a narrower fact-finding question.
    High objectivity means we can ask about self-judging thoughts, but only while
    keeping the already named fact anchored in the dialogue.
    """
    if objectivity_score >= 80:
        return DirectorInstruction(
            mode="fact_to_self_judgment",
            question_goal=(
                "Ask how the user usually explains or discounts this concrete fact."
            ),
            constraints=(
                "Keep the question tied to the previous concrete event.",
                "Do not praise.",
                "Ask for one self-judging thought or interpretation.",
            ),
        )

    if objectivity_score >= 65:
        return DirectorInstruction(
            mode="fact_deepening",
            question_goal=(
                "Ask for one missing detail: situation, action, result, or other people involved."
            ),
            constraints=(
                "Ask one short question.",
                "Do not ask for a character trait.",
                "Prefer observable details over feelings.",
            ),
        )

    return DirectorInstruction(
        mode="fact_extraction",
        question_goal=(
            "Narrow the user into one concrete episode with action and result."
        ),
        constraints=(
            "Reject vague global self-descriptions.",
            "Ask what happened, what the user did, and what changed.",
            "Do not reassure before the fact is named.",
        ),
    )


def build_director_prompt_block(
    objectivity_score: int | None,
    previous_answer: str = "",
) -> str:
    if objectivity_score is None:
        instruction = build_prompt_little_director(0, previous_answer)
    else:
        instruction = build_prompt_little_director(objectivity_score, previous_answer)

    return instruction.as_prompt_block()


def reflect_on_answer(answer: str, objectivity_score: int) -> DirectorInstruction:
    return build_prompt_little_director(
        objectivity_score=objectivity_score,
        previous_answer=answer,
    )


def reflect_on_previous_answer(
    previous_answer: str,
    objectivity_score: int,
) -> DirectorInstruction:
    return reflect_on_answer(previous_answer, objectivity_score)
