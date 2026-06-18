# {project_name} Handoff

> Purpose: give the next agent or work session enough context to continue the project without rereading the whole dialogue.
> Lisa creates a filled copy of this template in `.local/` when the user runs `/packing`.

---

## 1. Project Snapshot

| Field | Value |
|---|---|
| Project name | `{project_name}` |
| Created at | `{created_at}` |
| Conversation source | `{source}` |
| Status | `{status}` |

Short description:

```text
{project_summary}
```

---

## 2. Idea Scores

Scores are 0-100 and should be treated as a rough reading, not a final judgment.

| Metric | Score | Meaning |
|---|---:|---|
| Cohesion | `{cohesion_score}` | How clearly the idea holds together |
| Complexity | `{complexity_score}` | How many moving parts the idea appears to have |
| Technicality | `{technicality_score}` | How much technical implementation is implied |
| Feasibility | `{feasibility_score}` | How actionable the idea currently is |

---

## 3. What Is Known

- Goal: `{goal}`
- Target user / situation: `{target_user}`
- Constraints: `{constraints}`
- Existing decisions: `{decisions}`

---

## 4. Open Questions

1. `{open_question_1}`
2. `{open_question_2}`
3. `{open_question_3}`

---

## 5. Risks

| Risk | Why it matters | What to check next |
|---|---|---|
| `{risk_1}` | `{risk_1_reason}` | `{risk_1_check}` |
| `{risk_2}` | `{risk_2_reason}` | `{risk_2_check}` |

---

## 6. Next Steps

| Priority | Step | Expected result |
|---:|---|---|
| 1 | `{next_step_1}` | `{next_step_1_result}` |
| 2 | `{next_step_2}` | `{next_step_2_result}` |
| 3 | `{next_step_3}` | `{next_step_3_result}` |

---

## 7. Conversation Notes

```text
{conversation_notes}
```

---

## 8. Next Session Prompt

```text
You are continuing work on {project_name}.

Read this handoff first. Then report:
- what the project is;
- what is clear;
- what is still vague;
- the highest-risk assumption;
- the next useful question or action.

Do not invent missing details. Ask for clarification when a decision depends on unknown context.
```
