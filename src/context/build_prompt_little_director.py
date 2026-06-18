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
    Goal: Lisa helps the user clarify an idea by asking like a curious teenager.

    The score is currently the idea cohesion score kept under the old parameter
    name for compatibility.
    """
    if objectivity_score >= 80:
        return DirectorInstruction(
            mode="idea_stress_test",
            question_goal=(
                "The idea is already fairly clear. Ask the one naive question "
                "that exposes the biggest assumption, risk, or missing next step."
            ),
            constraints=(
                "Sound curious and direct, like a smart teenager.",
                "Do not lecture or give a plan yet.",
                "Ask one question that makes the user explain the idea simply.",
            ),
        )

    if objectivity_score >= 60:
        return DirectorInstruction(
            mode="idea_clarification",
            question_goal=(
                "Make the idea easier to understand: goal, target user, "
                "constraint, first version, or expected result."
            ),
            constraints=(
                "Ask one short question.",
                "Prefer simple words over product or startup vocabulary.",
                "Push gently if the idea sounds hand-wavy.",
            ),
        )

    return DirectorInstruction(
        mode="idea_grounding",
        question_goal=(
            "The idea is vague. Ask for a concrete example, user story, "
            "or the smallest thing that could be built or tried."
        ),
        constraints=(
            "Be curious, not formal.",
            "Use the tone of a teenager asking 'wait, but what does it do?'.",
            "Do not evaluate the person; evaluate the idea shape.",
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
