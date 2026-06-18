# little-agent-planner

Mirrored from the `little-agent-planner` branch README and latest scenario output.

## Little-agent-planner: Lisa

Lisa is a prototype CLI little-agent planner. She talks through early project
ideas with the user, asks simple skeptical questions, and turns the conversation
into an objective implementation review.

## What This Branch Tests

- LLM-first dialogue with no local canned response fallbacks.
- Four idea scores: cohesion, complexity, technicality, feasibility.
- `/summary` as objective idea review.
- Multi-step web research before summary:
  1. LLM proposes search queries.
  2. DuckDuckGo Lite returns result links.
  3. The runtime fetches several pages.
  4. LLM analyzes external context.
  5. Lisa writes the summary.
- `/packing` creates a handoff Markdown file from the latest summary.

## Commands

```powershell
python main.py
```

Runtime commands:

- `/summary` - evaluate the current idea; may take longer because Lisa can research online.
- `/packing` - write a handoff file to `.local/`.
- `/exit` - quit.

## Example Scenario

Scenario file on the branch:

```text
tools/scenario_runner/scenarios/excel_parser_idea.json
```

User idea:

```text
Я хочу сделать парсер для excell на пайтон
Хочу, чтобы он читал таблицу, находил нужные колонки и собирал из них нормальный JSON для дальнейшей обработки.
/summary
/packing
```

Observed output shape:

- Lisa asks why the parser is needed and how "needed columns" are defined.
- Summary identifies the main risk: column selection rules are not defined.
- Web research stores a compact `web_research_analysis` record with source titles/URLs.
- Packing creates a handoff titled `Excel to JSON Parser`.

Generated handoff example committed on the branch:

```text
example/excel-to-json-parser_handoff.md
```

Key handoff fields from the scenario:

```text
Project: Excel to JSON Parser
Goal: Read an Excel table, select specific columns, and convert them into JSON.
Main unknown: how the required columns are selected.
Next steps: choose an Excel library, get a sample file, define column rules.
```

## Real Ollama Scenario Command

```powershell
python -m tools.scenario_runner --scenario tools/scenario_runner/scenarios/excel_parser_idea.json --out-dir cache/scenario_runner
```

Latest local validation before adding this hub entry:

```text
python -m unittest discover -s tests
Ran 27 tests
OK

PASS tools/scenario_runner/scenarios/excel_parser_idea.json
```

## Notes

This branch is an experiment in turning rough ideas into implementation briefs.
It is not a general assistant branch and not a therapy/support bot.
