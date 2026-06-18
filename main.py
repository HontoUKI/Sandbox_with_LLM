from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from urllib.request import Request, urlopen

from src.context.build_prompt_little_director import build_director_prompt_block
from src.context.manager import ContextManager
from src.context.wrapper import ContextualLLM
from src.llm import OllamaError, OllamaLLM


if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SUMMARY_COMMAND = "/summary"
PACKING_COMMAND = "/packing"
EXIT_COMMANDS = {"/exit", "/quit"}
WEB_RESEARCH_RESULT_LIMIT = 5
WEB_RESEARCH_TIMEOUT = 12.0
WEB_RESEARCH_QUERY_COUNT = 3
WEB_RESEARCH_PAGE_LIMIT = 4
WEB_RESEARCH_PAGE_CHARS = 6000


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class WebPageText:
    title: str
    url: str
    text: str


@dataclass
class DialogueTurn:
    question: str
    user_answer: str
    bot_answer: str
    objectivity_score: int
    idea_scores: dict[str, int] | None = None
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


def is_packing_command(text: str) -> bool:
    return text.strip().lower() == PACKING_COMMAND


def is_exit_command(text: str) -> bool:
    return text.strip().lower() in EXIT_COMMANDS


def generate_question(
    llm: OllamaLLM,
    turns: list[DialogueTurn],
    context: ContextManager | None = None,
) -> str:
    previous_turn = turns[-1] if turns else None

    if not turns:
        lisa_persona = (
            "You are Lisa, a curious teenage little-agent planner. "
            "Ask in Russian one short, simple, naive question that helps the user explain an idea clearly. "
            "Do not lecture, do not make a list, do not sound like a therapist.\n\n"
        )
        prompt = lisa_persona + (
            "Ты Лиза. Начинаешь живой разговор. Спроси один короткий любознательный вопрос, "
            "как подросток, которому правда интересно понять идею. Без анкеты и без делового тона. "
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

        lisa_persona = (
            "You are Lisa, a curious teenage little-agent planner. "
            "Your job is to help the user crystallize an idea by asking simple questions. "
            "Be direct, curious, a little naive, and honest about gaps or risks. "
            "Answer in Russian. Do not lecture, do not make lists.\n\n"
        )
        prompt = lisa_persona + (
            "Ты Лиза. Ведешь живой разговор, не интервью. "
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
    extracted = context.extractor.extract(answer)
    idea_scores = extracted.idea_scores()
    objectivity_score = extracted.objectivity_score
    intent = "idea_turn"
    bot_answer = generate_bot_answer(
        question=question,
        answer=answer,
        context=context,
        intent_kind=intent,
        objectivity_score=objectivity_score,
        idea_scores=idea_scores,
    )

    user_content = context.add_dialogue_content(
        text=answer,
        prompt=question,
        bot_response=bot_answer,
        intent=intent,
        objectivity_score=objectivity_score,
        idea_scores=idea_scores,
        role="user",
        use_extractor=False,
    )
    context.add_dialogue_content(
        text=bot_answer,
        prompt=question,
        intent=f"{intent}_response",
        objectivity_score=objectivity_score,
        idea_scores=idea_scores,
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
        idea_scores=idea_scores,
        intent=intent,
    )


def generate_bot_answer(
    question: str,
    answer: str,
    context: ContextManager,
    intent_kind: str,
    objectivity_score: int,
    idea_scores: dict[str, int],
) -> str:
    if context.llm is None:
        raise BotStartupError("LLM is required to answer.")

    support_context = ContextualLLM(
        llm=context.llm,
        context_manager=context,
        memory_limit=5,
        history_limit=5,
    ).build_context_for_turn(answer)
    lisa_persona = (
        "You are Lisa, a curious teenage little-agent planner. "
        "Help the user understand their own idea by reacting simply and asking for clarity. "
        "Be honest about weak spots without insulting the user. "
        "Answer in Russian in 1-3 short sentences.\n\n"
    )
    prompt = lisa_persona + (
        "Ты Лиза. Отвечаешь человеку в живом диалоге.\n"
        "Тон: близко, мягко, честно, иногда чуть грубо по-живому. "
        "Можно редко использовать мягкий мат: 'блин', 'черт', 'пиздец' - только если это уместно "
        "как сочувствие ситуации, не как оскорбление человека.\n"
        "Можно выдержать молчаливую паузу текстом: '...'. Можно сказать 'я рядом, продолжай'.\n"
        "Не превращай ответ в терапевтический шаблон, чеклист или лекцию. Не используй списки.\n"
        "Если идея звучит мутно, помоги увидеть конкретный пример, риск или следующий шаг.\n"
        "Ответь 1-3 короткими предложениями на русском.\n\n"
        f"Опора из памяти:\n{support_context}\n\n"
        f"Предыдущий ход Лизы: {question}\n"
        f"Ответ пользователя: {answer}\n"
        f"Intent: {intent_kind}\n"
        f"Idea scores: {idea_scores}\n"
        f"Cohesion score: {objectivity_score}\n\n"
        "Ответ Лизы:"
    )

    try:
        response = context.llm.generate(prompt, max_tokens=180, temperature=0.55).strip()
    except OllamaError as exc:
        raise BotStartupError(f"Could not generate Lisa response through LLM. Details: {exc}") from exc

    response = response.strip().strip('"')

    if not response or len(response) > 900 or has_multiline_list(response):
        raise BotStartupError("LLM returned an invalid response. Try again.")

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


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebSearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = attr_map.get("class", "")

        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._in_title = True
            self._current_url = self._clean_duckduckgo_url(attr_map.get("href", ""))
            self._current_title = []
            self._current_snippet = []
            return

        if "result__snippet" in classes or "result-snippet" in classes:
            self._in_snippet = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
            return

        if self._in_snippet and tag in {"a", "div", "td"}:
            self._in_snippet = False
            self._flush_result()

    def close(self) -> None:
        self._flush_result()
        super().close()

    def _flush_result(self) -> None:
        title = " ".join(" ".join(self._current_title).split())
        snippet = " ".join(" ".join(self._current_snippet).split())

        if title and self._current_url and not any(
            result.url == self._current_url for result in self.results
        ):
            self.results.append(
                WebSearchResult(
                    title=title,
                    url=self._current_url,
                    snippet=snippet,
                )
            )

        self._current_title = []
        self._current_snippet = []
        self._current_url = ""

    @staticmethod
    def _clean_duckduckgo_url(url: str) -> str:
        if url.startswith("//"):
            url = f"https:{url}"

        parsed = urlparse(url)
        redirect = parse_qs(parsed.query).get("uddg")

        if redirect:
            return unquote(redirect[0])

        return url


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_tag_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_tag_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_tag_depth:
            self._ignored_tag_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())

        if not cleaned:
            return

        if self._in_title:
            self.title_parts.append(cleaned)
        elif not self._ignored_tag_depth:
            self.parts.append(cleaned)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self.parts).strip()


def build_web_research_queries(llm: OllamaLLM, turns: list[DialogueTurn]) -> list[str]:
    raw_turns = build_raw_turns(turns)
    prompt = (
        "Придумай поисковые запросы по идее пользователя. "
        "Нужно 3 коротких запроса для объективной оценки реализации: "
        "один про техническую реализацию, один про типичные риски, один про похожие решения/библиотеки. "
        "Пиши запросы на английском, даже если диалог на русском. "
        "Верни только JSON: {\"queries\": [\"query\"]}. Без markdown и пояснений.\n\n"
        f"Conversation:\n{raw_turns}"
    )
    raw = llm.generate(prompt, max_tokens=220, temperature=0.0)
    queries = parse_search_queries(raw)
    queries.extend(build_heuristic_search_queries(turns))
    deduped = []

    for query in queries:
        if query not in deduped:
            deduped.append(query)

    if deduped:
        return deduped[:WEB_RESEARCH_QUERY_COUNT]

    fallback = " ".join(turn.user_answer for turn in turns)[:180].strip()
    return [fallback] if fallback else []


def build_heuristic_search_queries(turns: list[DialogueTurn]) -> list[str]:
    text = " ".join(turn.user_answer for turn in turns).lower()

    if "excel" in text or "excell" in text:
        return [
            "python excel to json openpyxl pandas",
            "python parse excel columns to json validation",
            "openpyxl pandas excel parser error handling",
        ]

    return []


def parse_search_queries(raw: str) -> list[str]:
    try:
        data = load_json_object(raw)
        values = data.get("queries", [])
    except (json.JSONDecodeError, BotStartupError):
        values = raw.splitlines()

    if not isinstance(values, list):
        values = []

    queries = []

    for value in values:
        if not isinstance(value, str):
            continue

        cleaned = value.strip().strip("-*\"' ")

        if cleaned and cleaned not in queries:
            queries.append(cleaned[:180])

    return queries


def duckduckgo_search(
    query: str,
    limit: int = WEB_RESEARCH_RESULT_LIMIT,
    timeout: float = WEB_RESEARCH_TIMEOUT,
) -> list[WebSearchResult]:
    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LisaLittleAgent/0.1)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (TimeoutError, URLError) as exc:
        raise BotStartupError(f"Web research failed: {exc}") from exc

    if "challenge-form" in html or "anomaly.js" in html:
        return []

    parser = DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.results[:limit]


def search_multiple_queries(queries: list[str]) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    seen_urls = set()

    for query in queries:
        for result in duckduckgo_search(query, limit=WEB_RESEARCH_RESULT_LIMIT):
            if result.url in seen_urls:
                continue

            seen_urls.add(result.url)
            results.append(result)

    return results


def fetch_page_text(
    result: WebSearchResult,
    timeout: float = WEB_RESEARCH_TIMEOUT,
    max_chars: int = WEB_RESEARCH_PAGE_CHARS,
) -> WebPageText | None:
    request = Request(
        result.url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LisaLittleAgent/0.1)",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")

            if "text/html" not in content_type and "text/plain" not in content_type:
                return None

            body = response.read(max_chars * 4).decode("utf-8", errors="replace")
    except (TimeoutError, URLError, ValueError):
        return None

    parser = HTMLTextExtractor()
    parser.feed(body)
    parser.close()
    text = parser.text[:max_chars]

    if not text:
        return None

    return WebPageText(
        title=parser.title or result.title,
        url=result.url,
        text=text,
    )


def fetch_research_pages(results: list[WebSearchResult]) -> list[WebPageText]:
    pages = []

    for result in results:
        page = fetch_page_text(result)

        if page is not None:
            pages.append(page)

        if len(pages) >= WEB_RESEARCH_PAGE_LIMIT:
            break

    return pages


def analyze_web_pages(
    llm: OllamaLLM,
    queries: list[str],
    results: list[WebSearchResult],
    pages: list[WebPageText],
) -> str:
    if not results:
        return "Web research found no usable search results."

    source_lines = "\n".join(
        (
            f"{index}. {result.title}\n"
            f"URL: {result.url}\n"
            f"Snippet: {result.snippet or 'No snippet'}"
        )
        for index, result in enumerate(results, start=1)
    )
    page_lines = "\n\n".join(
        (
            f"PAGE {index}: {page.title}\n"
            f"URL: {page.url}\n"
            f"TEXT:\n{page.text}"
        )
        for index, page in enumerate(pages, start=1)
    )
    prompt = (
        "Analyze web research for evaluating a project idea. "
        "You have search result titles/links/snippets and text extracted from several pages. "
        "Do not copy long passages. Do not treat search snippets as certain facts. "
        "Return a compact Russian analysis with: market/context clues, implementation risks, "
        "similar existing solutions/libraries if visible, and what the user should verify next. "
        "Clearly separate what comes from page text from what is your inference.\n\n"
        f"Search queries:\n{json.dumps(queries, ensure_ascii=False)}\n\n"
        f"Search results:\n{source_lines}\n\n"
        f"Fetched pages:\n{page_lines or 'No pages could be fetched; analyze titles and snippets only.'}"
    )
    return llm.generate(prompt, max_tokens=1000, temperature=0.2).strip()


def run_web_research(context: ContextManager, llm: OllamaLLM, turns: list[DialogueTurn]) -> str:
    queries = build_web_research_queries(llm, turns)
    results = search_multiple_queries(queries)
    pages = fetch_research_pages(results)
    analysis = analyze_web_pages(llm, queries, results, pages)
    context.add_research_analysis(
        text=analysis,
        query=" | ".join(queries),
        sources=[
            {
                "title": result.title,
                "url": result.url,
            }
            for result in results
        ],
    )
    return analysis


def build_raw_turns(turns: list[DialogueTurn]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"Q: {turn.question}",
                f"You: {turn.user_answer}",
                f"I: {turn.bot_answer}",
            ]
        )
        for turn in turns
    )


def build_summary(
    llm: OllamaLLM,
    turns: list[DialogueTurn],
    web_research_analysis: str | None = None,
) -> str:
    raw_turns = build_raw_turns(turns)
    web_block = web_research_analysis or "Web research was not used."

    lisa_summary_persona = (
        "You are Lisa, a curious teenage little-agent planner. "
        "The user asked for /summary. Evaluate the idea objectively. "
        "Do not support the user just to be nice if the idea is underthought. "
        "Give implementation advice, split the work into steps, estimate step difficulty, "
        "name risks and missing assumptions, and recommend what to clarify next. "
        "Answer in Russian, compactly, without fake certainty. "
        "Do not greet the user and do not mention the /summary command.\n\n"
    )
    prompt = lisa_summary_persona + (
        "Ты Лиза. Человек попросил /summary.\n\n"
        "Оцени данную идею и дай советы по реализации. "
        "Если идея недостаточно продумана, прямо скажи, что именно не продумано, и дай рекомендации. "
        "Твоя цель - объективная оценка, а не поддержка пользователя.\n\n"
        "Не начинай с приветствия. Не пиши фразы вроде '/summary по твоей идее'.\n\n"
        "Структура ответа:\n"
        "1. Короткая суть идеи.\n"
        "2. Что уже понятно.\n"
        "3. Что слабое, рискованное или неясное.\n"
        "4. Практические шаги реализации с оценкой сложности каждого шага: низкая / средняя / высокая.\n"
        "5. Что нужно уточнить перед следующей итерацией.\n\n"
        "Опирайся только на сказанное в разговоре. Не выдумывай детали.\n\n"
        f"Внешний анализ:\n{web_block}\n\n"
        f"Разговор:\n{raw_turns}"
    )

    try:
        return llm.generate(prompt, max_tokens=900, temperature=0.35).strip()
    except OllamaError as exc:
        raise BotStartupError(f"Could not build summary through LLM. Details: {exc}") from exc


HANDOFF_TEMPLATE_PATH = Path("docs/HANDOFF_TEMPLATE.md")
HANDOFF_OUTPUT_DIR = Path(".local")
LAST_HANDOFF_PATH: Path | None = None
LAST_SUMMARY_TEXT: str | None = None
LAST_SUMMARY_TURN_COUNT = 0

HANDOFF_FIELD_DEFAULTS = {
    "project_name": "discussed_project",
    "goal": "Clarify the project goal in the next session.",
    "target_user": "Clarify who will use this and in what situation.",
    "constraints": "Clarify input formats, output expectations, and failure cases.",
    "decisions": "No firm implementation decisions captured yet.",
    "open_question_1": "What is the smallest useful version of this idea?",
    "open_question_2": "Who exactly needs it, and in what situation?",
    "open_question_3": "What would make the idea fail or become too expensive?",
    "risk_1": "Unclear scope",
    "risk_1_reason": "The idea may grow faster than the first version can support.",
    "risk_1_check": "Define the smallest testable version.",
    "risk_2": "Hidden assumptions",
    "risk_2_reason": "Some user, technical, or resource assumptions may be unstated.",
    "risk_2_check": "List assumptions before implementation.",
    "next_step_1": "Restate the idea in one simple sentence.",
    "next_step_1_result": "A clear project goal.",
    "next_step_2": "Name the first user or use case.",
    "next_step_2_result": "A concrete target scenario.",
    "next_step_3": "Pick one prototype action.",
    "next_step_3_result": "A small next experiment.",
}


def create_handoff_copy(
    summary: str,
    turns: list[DialogueTurn],
    handoff_fields: dict[str, str] | None = None,
    template_path: Path = HANDOFF_TEMPLATE_PATH,
    output_dir: Path = HANDOFF_OUTPUT_DIR,
) -> Path:
    global LAST_HANDOFF_PATH

    template = template_path.read_text(encoding="utf-8")
    created_at = datetime.now(timezone.utc).isoformat()
    fields = {**HANDOFF_FIELD_DEFAULTS, **(handoff_fields or {})}
    project_name = clean_handoff_value(
        fields.get("project_name"),
        infer_project_name(summary, turns),
    )
    idea_scores = aggregate_idea_scores(turns)
    conversation_notes = build_conversation_notes(turns)
    replacements = {
        "project_name": project_name,
        "created_at": created_at,
        "source": "Lisa /packing",
        "status": "draft",
        "project_summary": summary.strip() or "Not enough information yet.",
        "cohesion_score": str(idea_scores["cohesion_score"]),
        "complexity_score": str(idea_scores["complexity_score"]),
        "technicality_score": str(idea_scores["technicality_score"]),
        "feasibility_score": str(idea_scores["feasibility_score"]),
        "conversation_notes": conversation_notes,
    }
    for key, default in HANDOFF_FIELD_DEFAULTS.items():
        if key != "project_name":
            replacements[key] = clean_handoff_value(fields.get(key), default)
    filled = fill_template(template, replacements)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slugify(project_name)}_handoff.md"
    output_path.write_text(filled, encoding="utf-8")
    LAST_HANDOFF_PATH = output_path
    return output_path


def fill_template(template: str, replacements: dict[str, str]) -> str:
    filled = template

    for key, value in replacements.items():
        filled = filled.replace("{" + key + "}", value)

    return filled


def build_handoff_fields(
    llm: OllamaLLM,
    summary: str,
    turns: list[DialogueTurn],
) -> dict[str, str]:
    keys = ", ".join(HANDOFF_FIELD_DEFAULTS)
    prompt = (
        "Extract structured handoff fields from this idea discussion. "
        "Return only a JSON object with exactly these string keys: "
        f"{keys}. "
        "Do not include markdown, comments, or extra keys. "
        "Use concrete details from the conversation. Put only explicitly stated "
        "details into goal, target_user, constraints, and decisions. Put likely "
        "but unstated issues into risks or open questions. If a field is unknown, "
        "write a short specific clarification need instead of a generic 'unknown'. "
        "For target_user, do not write 'you' or 'the user'; describe the actual "
        "operator/customer/use case, or say what must be clarified. "
        "Do not use markdown formatting inside JSON values.\n\n"
        f"Summary:\n{summary}\n\n"
        f"Conversation:\n{build_raw_turns(turns)}"
    )
    raw = llm.generate(prompt, max_tokens=1200, temperature=0.0)
    data = load_json_object(raw)

    fields = {}

    for key, default in HANDOFF_FIELD_DEFAULTS.items():
        value = clean_handoff_value(data.get(key), default)

        if key == "target_user" and value.lower() in {"you", "user", "the user", "пользователь"}:
            value = default

        fields[key] = value

    return fields


def load_json_object(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)

        if match is None:
            raise BotStartupError(f"Could not parse handoff fields as JSON: {raw}") from None

        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise BotStartupError(f"Handoff fields response is not a JSON object: {raw}")

    return data


def clean_handoff_value(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default

    cleaned = " ".join(value.replace("`", "'").split())
    return cleaned or default


def infer_project_name(summary: str, turns: list[DialogueTurn] | None = None) -> str:
    if turns:
        for turn in turns:
            user_text = turn.user_answer.strip()
            lowered = user_text.lower()

            if "excel" in lowered or "excell" in lowered:
                return "Python Excel parser"

            if user_text:
                return user_text[:80]

    for line in summary.splitlines():
        cleaned = line.strip().strip("#:*- ")

        if cleaned and "/summary" not in cleaned.lower() and "привет" not in cleaned.lower():
            return cleaned[:80]

    return "discussed_project"


def aggregate_idea_scores(turns: list[DialogueTurn]) -> dict[str, int]:
    keys = (
        "cohesion_score",
        "complexity_score",
        "technicality_score",
        "feasibility_score",
    )
    values = {key: [] for key in keys}

    for turn in turns:
        if not isinstance(turn.idea_scores, dict):
            continue

        for key in keys:
            value = turn.idea_scores.get(key)

            if isinstance(value, int):
                values[key].append(max(0, min(100, value)))

    return {
        key: round(sum(scores) / len(scores)) if scores else 0
        for key, scores in values.items()
    }


def build_conversation_notes(turns: list[DialogueTurn]) -> str:
    if not turns:
        return "No conversation turns were captured."

    notes = []

    for index, turn in enumerate(turns, start=1):
        notes.append(
            "\n".join(
                (
                    f"Turn {index}",
                    f"Lisa: {turn.question}",
                    f"User: {turn.user_answer}",
                    f"Lisa response: {turn.bot_answer}",
                    f"Idea scores: {turn.idea_scores or {}}",
                )
            )
        )

    return "\n\n".join(notes)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if not slug:
        slug = "project"

    return f"{slug[:48]}_{timestamp}"


def save_summary(
    context: ContextManager,
    llm: OllamaLLM,
    turns: list[DialogueTurn],
    use_web_research: bool = False,
) -> str:
    global LAST_SUMMARY_TEXT
    global LAST_SUMMARY_TURN_COUNT

    web_research_analysis = run_web_research(context, llm, turns) if use_web_research else None
    summary = build_summary(
        llm,
        turns,
        web_research_analysis=web_research_analysis,
    )
    turn_records = [
        {
            "question": turn.question,
            "user_answer": turn.user_answer,
            "bot_answer": turn.bot_answer,
            "intent": turn.intent,
            "objectivity_score": turn.objectivity_score,
            "idea_scores": turn.idea_scores,
        }
        for turn in turns
    ]
    summary_record = context.add_summary(text=summary, turns=turn_records)
    context.extract_dialogue_summary_facts(
        turns=turn_records,
        source_summary_id=summary_record["id"],
    )
    LAST_SUMMARY_TEXT = summary
    LAST_SUMMARY_TURN_COUNT = len(turns)
    return summary


def save_packing(
    context: ContextManager,
    llm: OllamaLLM,
    turns: list[DialogueTurn],
    template_path: Path = HANDOFF_TEMPLATE_PATH,
    output_dir: Path = HANDOFF_OUTPUT_DIR,
) -> Path:
    summary = (
        LAST_SUMMARY_TEXT
        if LAST_SUMMARY_TEXT is not None and LAST_SUMMARY_TURN_COUNT == len(turns)
        else save_summary(context, llm, turns, use_web_research=False)
    )
    handoff_fields = build_handoff_fields(llm, summary, turns)
    return create_handoff_copy(
        summary,
        turns,
        handoff_fields=handoff_fields,
        template_path=template_path,
        output_dir=output_dir,
    )


def run_bot() -> None:
    load_env()
    print("Привет, я Лиза.")
    print("Давай без анкеты. Просто говори, что есть. Я рядом.")
    print(f"Когда захочешь оценку - напиши {SUMMARY_COMMAND}. Handoff: {PACKING_COMMAND}. Выйти: /exit.")
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
                print(
                    "Summary может занять больше времени: Лиза придумает поисковые запросы, "
                    "посмотрит ссылки, прочитает несколько страниц и затем оценит идею."
                )
                summary = save_summary(context, llm, turns, use_web_research=True)
                print("\nSummary по диалогу:")
                print(summary)
                print("\nСохранила summary и извлекла факты из разговора.")
            question = "... я здесь. продолжим?"
            continue

        if is_packing_command(answer):
            if not turns:
                print("Пока нечего упаковывать. Сначала опиши идею.")
            else:
                handoff_path = save_packing(context, llm, turns)
                print(f"\nPacking готов: {handoff_path}")
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
