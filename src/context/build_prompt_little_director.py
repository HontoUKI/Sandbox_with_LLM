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
    Decide how next question should be shaped.
    Goal: natural dialogue that draws out full picture, finds hidden strengths.

    Low objectivity = user is vague or self-critical, need concrete context.
    High objectivity = can explore the thinking, emotions, broader context.
    """
    if objectivity_score >= 80:
        return DirectorInstruction(
            mode="context_deepening",
            question_goal=(
                "Explore the thinking or context around this concrete fact. "
                "What was important to you, what did you learn, who was involved?"
            ),
            constraints=(
                "Keep tied to the fact they mentioned.",
                "Show genuine interest, not interrogation.",
                "Invite reflection naturally, not as evaluation.",
            ),
        )

    if objectivity_score >= 60:
        return DirectorInstruction(
            mode="fact_exploration",
            question_goal=(
                "Get one more detail that makes the picture complete: "
                "timing, other people, what changed, why it mattered."
            ),
            constraints=(
                "Ask one natural question.",
                "Prefer observables: who, what, when, where.",
                "Sound curious, not like you're checking facts.",
            ),
        )

    return DirectorInstruction(
        mode="concrete_grounding",
        question_goal=(
            "Find one concrete moment or example to make the vague more real. "
            "Not to judge - just to understand what actually happened."
        ),
        constraints=(
            "Gently ask for one specific time, person, or action.",
            "Do not ask for self-description.",
            "Be patient with vagueness, do not pressure.",
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
