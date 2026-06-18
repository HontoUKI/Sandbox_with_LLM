# Excel to JSON Parser Handoff

> Purpose: give the next agent or work session enough context to continue the project without rereading the whole dialogue.
> Lisa creates a filled copy of this template in `.local/` when the user runs `/packing`.

---

## 1. Project Snapshot

| Field | Value |
|---|---|
| Project name | `Excel to JSON Parser` |
| Created at | `2026-06-18T04:47:27.984546+00:00` |
| Conversation source | `Lisa /packing` |
| Status | `draft` |

Short description:

```text
1. **Суть:** Парсер Excel, извлекающий данные из указанных колонок и преобразующий их в JSON.

2. **Понятно:**
    *   Цель - получение JSON для дальнейшей обработки.
    *   Необходимость чтения таблицы и выбора конкретных колонок.

3. **Слабое/Неясное:**
    *   **Структура Excel:** Неизвестно, как устроена таблица (количество листов, формат данных в колонках, наличие формул, и т.д.). Это критично для выбора библиотеки.
    *   **Выбор колонок:** Как будут определяться "нужные" колонки? По имени? По индексу? По содержимому?
    *   **Сложность данных:** Какие типы данных в колонках (текст, числа, даты)? Нужно ли преобразовывать типы?
    *   **Обработка ошибок:** Что делать, если колонка не найдена или данные в ней некорректны?
    *   **Объем данных:** Насколько велики Excel файлы? Это влияет на выбор библиотеки (производительность).
    *   **Формулы:** Нужно ли вычислять формулы или только извлекать их?

4. **Шаги реализации:**
    *   **Выбор библиотеки:** (Средняя) Изучить `openpyxl`, `formulas`, `eparse` (с осторожностью).  Оценить их возможности и производительность.
    *   **Чтение Excel файла:** (Низкая) Использование выбранной библиотеки для открытия файла.
    *   **Определение колонок:** (Средняя) Реализация логики выбора колонок на основе заданных критериев (имя, индекс, содержимое).
    *   **Извлечение данных:** (Средняя) Чтение данных из выбранных колонок.
    *   **Преобразование в JSON:** (Низкая) Использование библиотеки `json` для создания JSON структуры.
    *   **Обработка ошибок:** (Средняя) Реализация обработки ошибок (отсутствие колонки, некорректные данные).

5. **Что уточнить:**
    *   Пример Excel файла (или его структуры).
    *   Критерии выбора колонок.
    *   Типы данных в колонках и необходимость их преобразования.
    *   Нужно ли обрабатывать формулы.
    *   Пример ожидаемого JSON вывода.
```

---

## 2. Idea Scores

Scores are 0-100 and should be treated as a rough reading, not a final judgment.

| Metric | Score | Meaning |
|---|---:|---|
| Cohesion | `76` | How clearly the idea holds together |
| Complexity | `57` | How many moving parts the idea appears to have |
| Technicality | `24` | How much technical implementation is implied |
| Feasibility | `62` | How actionable the idea currently is |

---

## 3. What Is Known

- Goal: `Read an Excel table, select specific columns, and convert them into a JSON structure for further processing.`
- Target user / situation: `Needs clarification - the user's specific use case for the JSON output is unknown.`
- Constraints: `The parser needs to read the Excel table and select specific columns.`
- Existing decisions: `The project will be implemented in Python.`

---

## 4. Open Questions

1. `What is the structure of the Excel file (number of sheets, data format in columns, presence of formulas, etc.)?`
2. `How will the 'necessary' columns be determined (by name, index, or content)?`
3. `What is the expected JSON output format?`

---

## 5. Risks

| Risk | Why it matters | What to check next |
|---|---|---|
| `Performance issues with large Excel files.` | `Large files may lead to slow processing and memory issues.` | `Test the parser with various file sizes to assess performance.` |
| `Incorrect data type handling.` | `Data types in columns may not be as expected, requiring conversion.` | `Verify data types in the Excel file and implement appropriate conversion logic.` |

---

## 6. Next Steps

| Priority | Step | Expected result |
|---:|---|---|
| 1 | `Research and evaluate Python libraries: openpyxl, formulas, eparse.` | `Selection of the most suitable library based on capabilities and performance.` |
| 2 | `Obtain an example Excel file or a detailed description of its structure.` | `Clear understanding of the Excel file's layout and data types.` |
| 3 | `Define the criteria for selecting columns.` | `A clear and documented method for identifying the desired columns.` |

---

## 7. Conversation Notes

```text
Turn 1
Lisa: Эм... ну, типа, а что, если это... как, работает?
User: Я хочу сделать парсер для excell на пайтон
Lisa response: Парсер для Excel на Python? Блин, звучит... ну, технично. А зачем он тебе нужен, конкретно?
Idea scores: {'cohesion_score': 72, 'complexity_score': 44, 'technicality_score': 15, 'feasibility_score': 54}

Turn 2
Lisa: А для кого ты его делаешь?
User: Хочу, чтобы он читал таблицу, находил нужные колонки и собирал из них нормальный JSON для дальнейшей обработки.
Lisa response: Так, понятно, JSON для обработки. А какие колонки ты имеешь в виду? Можешь пример привести, чтобы я поняла, что именно тебе нужно собирать?
Idea scores: {'cohesion_score': 80, 'complexity_score': 70, 'technicality_score': 33, 'feasibility_score': 70}
```

---

## 8. Next Session Prompt

```text
You are continuing work on Excel to JSON Parser.

Read this handoff first. Then report:
- what the project is;
- what is clear;
- what is still vague;
- the highest-risk assumption;
- the next useful question or action.

Do not invent missing details. Ask for clarification when a decision depends on unknown context.
```
