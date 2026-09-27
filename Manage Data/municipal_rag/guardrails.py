"""Deterministic decisions that keep RAG answers strict.

Every function here is pure: it takes plain data (interpreted constraints, exposed evidence dicts,
model verdicts) and returns plain data, so the rules are unit-tested without models or Qdrant.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any
from urllib.parse import unquote, urlparse

LANGUAGES = ("ro", "ru", "en")
ANSWER_TYPES = ("hours", "date", "amount", "person", "place", "procedure", "legal_act", "list", "other")
SCREEN_REASONS = ("RELEVANT", "DIFFERENT_EVENT", "DIFFERENT_PERIOD", "DIFFERENT_ENTITY", "TOPIC_ONLY")
# The screen labels relevant passages RELEVANT_A, RELEVANT_B, ...: one letter per distinct subject the question could mean.
SUBJECT_GROUPS = ("A", "B", "C", "D")
SCREEN_CODES = tuple(f"RELEVANT_{group}" for group in SUBJECT_GROUPS) + SCREEN_REASONS[1:]
NOT_FOUND_REASONS = ("NO_RELEVANT_EVIDENCE", "EVIDENCE_LACKS_VALUE", "CLAIMS_UNVERIFIED", "OUT_OF_SCOPE")
CONFLICT_REASON = "CONFLICTING_DOCUMENTS"
# Categories that describe a document's form or owner rather than its subject never count against a passage.
GENERIC_CATEGORIES = {"legal_act", "district_admin", "transparency", "services", "other_services", "none", ""}
SECTORS = {"botanica": "Botanica", "buiucani": "Buiucani", "centru": "Centru", "ciocana": "Ciocana", "rascani": "Râșcani"}
FILE_EXTENSION = re.compile(r"\.(?:pdf|docx?|xlsx?|odt|ods|rtf|pptx?|jpe?g|png|zip|rar)$", re.I)
MARKER = re.compile(r"\[S[1-9][0-9]*\]")
YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
ACRONYM = re.compile(r"\b[A-ZĂÂÎȘȚ]{3,8}\b")
NOT_ACRONYMS = {"III", "VII", "VIII", "XII", "XIV", "XV", "XX", "XXI", "ANEXA", "NOTA", "PDF", "SRL", "ORDON", "DECIDE"}
STREET = re.compile(r"\b(?:str|strada|stradela|bd|bulevardul|sos|soseaua|aleea|calea|ul|ulitsa)\.?\s+((?:[a-z][\w-]*\.?\s*){1,3})")
STREET_STOPWORDS = {"din", "nr", "si", "sau", "cu", "de", "la", "in", "pe", "sectorul", "mun", "or", "orasul", "chisinau"}
ABBREVIATIONS = {"nr", "str", "bd", "art", "alin", "lit", "pct", "or", "mun", "sec", "dl", "dna", "prof", "dr", "tel",
    "ex", "etc", "vs", "st", "no", "mr", "mrs", "sos", "ул", "д", "г", "ст", "им", "gr", "cca", "aprox", "resp"}

EN_WORDS = {"the", "what", "which", "who", "whom", "when", "where", "why", "how", "is", "are", "was", "were", "do", "much", "many",
    "did", "does", "has", "have", "at", "in", "by", "from", "start", "starts", "cost", "awarded", "title", "need", "get",
    "does", "did", "can", "could", "should", "i", "my", "you", "your", "of", "to", "for", "and", "on", "about",
    "street", "hours", "school", "city", "hall", "tax", "taxes", "please", "tell", "me", "there", "this", "that", "with"}
RO_WORDS = {"si", "este", "sunt", "care", "ce", "cum", "cine", "unde", "cand", "de", "la", "in", "pentru", "pe", "din",
    "cu", "sa", "vreau", "despre", "al", "ale", "lui", "un", "o", "strada", "programul", "lucru", "copilul", "meu",
    "mea", "se", "au", "fost", "facut", "primaria", "sectorul", "anul", "ul", "ului", "sau", "nu", "dar", "ma"}

HOURS_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b(?:ora|orele|ore)\s+\d{1,2}\b|\bnon-?stop\b|\b24\s*/\s*[247]\b|круглосуточно|\bс\s+\d{1,2}\b")
MONTHS = (r"ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|noiembrie|decembrie|"
    r"январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|"
    r"january|february|march|april|may|june|july|august|september|october|november|december")
DATE_VALUE_RE = re.compile(rf"\b\d{{1,2}}[./-]\d{{1,2}}(?:[./-]\d{{2,4}})?\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b\d{{1,2}}\s+(?:{MONTHS})\b|\b(?:{MONTHS})\s+\d{{1,2}}\b|(?<!\d)(?:19|20)\d{{2}}(?!\d)", re.I)
NUMBER_WORDS = (r"unu|una|doi|doua|trei|patru|cinci|sase|sapte|opt|noua|zece|suta|sute|mie|mii|milion\w*|"
    r"один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|сто|тысяч\w*|миллион\w*|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million")
# "amount" covers money and quantities (100 citizens, 4 tonnes), so any number answers it.
QUANTITY_RE = re.compile(rf"\d|\b(?:{NUMBER_WORDS})\b", re.I)
AMOUNT_RE = re.compile(r"\d[\d\s.,]*\s*(?:mii\s+|milioane\s+|mln\.?\s+|тыс\.?\s+|млн\.?\s+)?(?:lei|mdl|eur|euro|usd|\$|€|%|лей|леев|лея|евро|рубл\w*|bani|dolari|dollars?)", re.I)
LEGAL_ACT_RE = re.compile(r"\b(?:ordin\w*|hotarar\w*|hotarir\w*|decizi\w*|dispozit\w*|lege|legea|legii|legilor|regulament\w*|codul|cod|"
    r"закон\w*|приказ\w*|постановлени\w*|решени\w*|распоряжени\w*|кодекс\w*|law|laws|order|decision|regulation\w*|decree|act)\b"
    r"|\bnr\.?\s*\d|№\s*\d|\bno\.\s*\d", re.I)
DETERMINISTIC_VALUES = {"hours": HOURS_RE, "date": DATE_VALUE_RE, "amount": QUANTITY_RE, "legal_act": LEGAL_ACT_RE}
LEGAL_QUESTION = re.compile(r"\b(?:legisla\w*|lege|legea|legi|legile|legii|ordin\w*|hotarar\w*|hotarir\w*|regulament\w*|act\w* normativ\w*|"
    r"законодательств\w*|закон\w*|приказ\w*|постановлени\w*|legislation|law|laws|order|regulation\w*)\b", re.I)
HOURS_QUESTION = re.compile(r"\b(?:program\w* de lucru|orar\w*|ore\w* de (?:lucru|primire|audien\w*)|program\w* de (?:primire|audien\w*)|"
    r"график\w* работы|часы работы|режим работы|working hours|opening hours|office hours|business hours)\b", re.I)
YEARLY_QUESTION = re.compile(r"\b(?:inscri\w*|copil\w* (?:\w+ )?(?:la|in) scoal\w*|clasa (?:i|1|intai)|an\w* (?:de studii|scolar)|impozit\w*|taxe|taxa|taxele|admiter\w*|tabere?|"
    r"tabara|burs\w*|запис\w*|зачислен\w*|учебн\w* год\w*|налог\w*|enrol\w*|school year|admission\w*|tax|taxes)\b", re.I)

TYPE_NAMES = {
    "ro": {"hours": "programul de lucru", "date": "data sau perioada cerută", "amount": "suma sau valoarea cerută",
        "person": "persoana cerută", "place": "locul sau adresa cerută", "procedure": "procedura cerută",
        "legal_act": "actul normativ cerut", "list": "lista cerută", "other": "informația cerută"},
    "ru": {"hours": "график работы", "date": "запрошенная дата или период", "amount": "запрошенная сумма или значение",
        "person": "запрошенное лицо", "place": "запрошенное место или адрес", "procedure": "запрошенная процедура",
        "legal_act": "запрошенный нормативный акт", "list": "запрошенный список", "other": "запрошенная информация"},
    "en": {"hours": "the working hours", "date": "the requested date or period", "amount": "the requested amount or value",
        "person": "the requested person", "place": "the requested place or address", "procedure": "the requested procedure",
        "legal_act": "the requested legal act", "list": "the requested list", "other": "the requested information"},
}
NOT_FOUND_TEMPLATES = {
    "NO_RELEVANT_EVIDENCE": {
        "ro": "Nu am găsit în documentele municipale disponibile informații care să răspundă la această întrebare.",
        "ru": "В доступных муниципальных документах не найдено информации, отвечающей на этот вопрос.",
        "en": "I found no information in the available municipal documents that answers this question."},
    "EVIDENCE_LACKS_VALUE": {
        "ro": "Am găsit documente municipale pe această temă, dar niciunul nu conține {value}.",
        "ru": "Найдены муниципальные документы по этой теме, но ни один из них не содержит: {value}.",
        "en": "I found municipal documents on this topic, but none of them contains {value}."},
    "CLAIMS_UNVERIFIED": {
        "ro": "Nu am putut confirma un răspuns din documentele găsite, de aceea nu ofer unul.",
        "ru": "Не удалось подтвердить ответ по найденным документам, поэтому ответ не приводится.",
        "en": "I could not confirm an answer from the documents found, so I am not giving one."},
    "OUT_OF_SCOPE": {
        "ro": "Întrebarea nu ține de serviciile sau documentele municipale ale Chișinăului, așa că nu pot răspunde din sursele disponibile.",
        "ru": "Вопрос не относится к муниципальным услугам или документам Кишинёва, поэтому ответить по доступным источникам нельзя.",
        "en": "This question is not about Chișinău municipal services or documents, so I cannot answer it from the available sources."},
}
CLARIFICATION_TEMPLATES = {
    "ro": "Am găsit mai multe documente diferite care se potrivesc la fel de bine întrebării. La care dintre ele vă referiți?",
    "ru": "Найдено несколько разных документов, одинаково подходящих к вопросу. Какой из них вы имеете в виду?",
    "en": "I found several different documents that match the question equally well. Which one do you mean?",
}
# Earlier wordings stay recognisable so clarification follow-ups keep working for stored chats.
LEGACY_CLARIFICATIONS = (
    "Nu sunt sigur la ce document vă referiți",
    "Я не уверен, какой документ вы имеете в виду",
)
OUTDATED_TEMPLATES = {
    "ro": "Atenție: sursele găsite sunt din {years} și pot să nu mai fie actuale.",
    "ru": "Внимание: найденные источники датированы {years} г. и могут быть неактуальны.",
    "en": "Note: the sources found date from {years} and may be out of date.",
}


def fold(text: Any) -> str:
    """Casefolded text without diacritics (ș/ş, ț/ţ, ă, â, î fold to ASCII); Cyrillic is kept."""
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", fold(text))


def detect_language(text: str, hint: str | None = None) -> str:
    """ro/ru/en: Cyrillic means Russian; otherwise function words decide, then the interpreter's hint, then Romanian."""
    if re.search(r"[А-Яа-яЁё]", text):
        return "ru"
    tokens = words(text)
    english = sum(token in EN_WORDS for token in tokens)
    romanian = sum(token in RO_WORDS for token in tokens)
    if english > romanian:
        return "en"
    if romanian > english:
        return "ro"
    # Diacritics only break ties: English questions often name places such as "Chișinău".
    if re.search(r"[ăâîșşțţ]", text, re.I):
        return "ro"
    return hint if hint in LANGUAGES else "ro"


def expected_answer_type(question: str, hint: str | None = None) -> str:
    """Keyword rules win over the interpreter for legislation and working-hours questions."""
    folded = fold(question)
    if HOURS_QUESTION.search(folded):
        return "hours"
    if LEGAL_QUESTION.search(folded):
        return "legal_act"
    return hint if hint in ANSWER_TYPES else "other"


def is_yearly_topic(question: str, hint: bool = False) -> bool:
    return bool(hint) or bool(YEARLY_QUESTION.search(fold(question)))


def years_in(text: str) -> set[int]:
    return {int(value) for value in YEAR.findall(str(text or ""))}


def street_keys(streets: list[str], query: str) -> set[str]:
    """Distinctive (last) token of each street the question names, from the interpreter and the Romanian query."""
    names = [str(item) for item in streets if str(item).strip()]
    names.extend(match.group(1) for match in STREET.finditer(fold(query)))
    keys = set()
    for name in names:
        tokens = [token for token in words(name) if len(token) >= 4 and token not in STREET_STOPWORDS
                  and token not in {"strada", "stradela", "bulevardul", "soseaua", "aleea", "calea"}]
        if tokens:
            keys.add(tokens[-1])
    return keys


def sectors_in(text: str, explicit_only: bool) -> set[str]:
    folded = fold(text)
    found = {name for name in SECTORS if re.search(rf"\bsector\w*\s+{name}\b", folded)}
    if not explicit_only:
        found |= {name for name in SECTORS if name != "centru" and re.search(rf"\b{name}\b", folded)}
    return found


def question_constraints(question: str, normalized: str, interpreted: dict[str, Any]) -> dict[str, Any]:
    """Explicit years, streets, sectors and acronyms the question names; used by rule_conflict."""
    text = f"{question}\n{normalized}"
    return {
        "years": sorted(years_in(text)),
        "streets": sorted(street_keys(list(interpreted.get("streets") or []), normalized)),
        "sectors": sorted(sectors_in(text, explicit_only=False)),
        "acronyms": sorted({value for value in ACRONYM.findall(question) if value not in NOT_ACRONYMS}),
        "topicCategory": str(interpreted.get("topicCategory") or "none"),
    }


def passage_text(item: dict[str, Any]) -> str:
    heading = item.get("heading") or []
    return " ".join([str(item.get("title") or ""), " ".join(str(value) for value in heading),
                     str(item.get("exactQuote") or ""), url_basename(item.get("url"))])


def rule_conflict(item: dict[str, Any], constraints: dict[str, Any]) -> str | None:
    """Screen reason when the passage explicitly names another period, street, sector or sibling institution."""
    text = passage_text(item)
    folded = fold(text)
    question_years = set(constraints.get("years") or [])
    if question_years:
        mentioned = years_in(text)
        published = published_year(item)
        if mentioned:
            if not mentioned & question_years and published not in question_years:
                return "DIFFERENT_PERIOD"
        elif published is not None and published > max(question_years) + 1:
            return "DIFFERENT_PERIOD"
    keys = set(constraints.get("streets") or [])
    if keys and not any(re.search(rf"\b{re.escape(key)}\b", folded) for key in keys):
        named = [match.group(1) for match in STREET.finditer(folded)]
        if any(words(name) for name in named):
            return "DIFFERENT_ENTITY"
    sectors = set(constraints.get("sectors") or [])
    district = fold(item.get("district"))
    if sectors and district in SECTORS and district not in sectors and not sectors & sectors_in(text, explicit_only=False):
        return "DIFFERENT_ENTITY"
    acronyms = set(constraints.get("acronyms") or [])
    if acronyms and not any(re.search(rf"\b{re.escape(fold(value))}\b", folded) for value in acronyms):
        others = {value for value in ACRONYM.findall(text) if value not in NOT_ACRONYMS}
        if any(other[:2] == value[:2] for other in others for value in acronyms):
            return "DIFFERENT_ENTITY"
    return None


def category_mismatch(item: dict[str, Any], topic_category: str) -> bool:
    wanted, actual = fold(topic_category), fold(item.get("category"))
    return wanted not in GENERIC_CATEGORIES and actual not in GENERIC_CATEGORIES and wanted != actual


def apply_rules(items: list[dict[str, Any]], constraints: dict[str, Any], category_penalty: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop passages that contradict the question; a category mismatch lowers the score used for ranking and ties."""
    kept, dropped = [], []
    for item in items:
        reason = rule_conflict(item, constraints)
        if reason:
            dropped.append({"id": item.get("id"), "documentId": item.get("documentId"), "reason": reason, "source": "rule"})
            continue
        score = float(item.get("score") or 0.0)
        mismatch = category_mismatch(item, str(constraints.get("topicCategory") or ""))
        kept.append({**item, "categoryMismatch": mismatch, "effectiveScore": score * category_penalty if mismatch else score})
    kept.sort(key=lambda value: -float(value["effectiveScore"]))
    return kept, dropped


def url_basename(url: Any) -> str:
    try:
        path = urlparse(str(url or "")).path
    except ValueError:
        return ""
    return unquote(path.rstrip("/").rsplit("/", 1)[-1]) if path else ""


def file_key(url: Any) -> str | None:
    """Host-independent file name, only for real files (mec.gov.md and mecc.gov.md copies share it)."""
    name = fold(url_basename(url))
    if not FILE_EXTENSION.search(name) or len(FILE_EXTENSION.sub("", name)) < 5:
        return None
    return name


def is_anchor_title(title: str) -> bool:
    folded = fold(title).strip()
    return bool(re.search(r"\baici\b|\bclick\b|\bdescarca\w*\b|\bapasati\b|\bsubscribe\b", folded)
                or re.search(r"\s,\s", folded) or folded.endswith(","))


def is_file_title(title: str) -> bool:
    value = str(title or "").strip()
    return bool(value) and ("_" in value or bool(FILE_EXTENSION.search(value)))


def title_key(title: Any) -> str | None:
    """Normalized title for copy detection; anchor-text titles compare only their text before the link."""
    folded = fold(title)
    if is_anchor_title(str(title or "")):
        folded = re.split(r"\baici\b|\bclick\b|,", folded)[0]
    key = " ".join(re.findall(r"[^\W_]+", folded))
    return key if len(key) >= 30 else None


def quote_tokens(item: dict[str, Any]) -> set[str]:
    return set(words(str(item.get("exactQuote") or "")))


def near_identical(left: set[str], right: set[str], threshold: float = 0.85) -> bool:
    if len(left) < 8 or len(right) < 8:
        return False
    return len(left & right) / len(left | right) >= threshold


def similar_titles(left: str, right: str) -> bool:
    if any(is_anchor_title(value) or is_file_title(value) or not value.strip() for value in (left, right)):
        return True
    left_words, right_words = set(words(left)), set(words(right))
    return len(left_words & right_words) / max(1, len(left_words | right_words)) >= 0.6


def merge_duplicates(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Collapse copies of one document (same file name, title or near-identical quotes) into the most recent copy."""
    documents: list[str] = []
    for item in items:
        if str(item.get("documentId")) not in documents:
            documents.append(str(item.get("documentId")))
    parent = {document: document for document in documents}

    def root(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def join(left: str, right: str) -> None:
        parent[root(left)] = root(right)

    seen: dict[tuple[str, str], str] = {}
    for item in items:
        document = str(item.get("documentId"))
        for kind, key in (("file", file_key(item.get("url"))), ("title", title_key(item.get("title")))):
            if key is None:
                continue
            if (kind, key) in seen and seen[(kind, key)] != document:
                join(document, seen[(kind, key)])
            seen.setdefault((kind, key), document)
    # Near-identical quotes mark copies only when the titles agree too (or one is link text or a file name);
    # boilerplate shared by pages about different places must not merge them.
    tokens = [(str(item.get("documentId")), quote_tokens(item), str(item.get("title") or "")) for item in items]
    for index, (left_document, left, left_title) in enumerate(tokens):
        for right_document, right, right_title in tokens[index + 1:]:
            if left_document != right_document and near_identical(left, right) and similar_titles(left_title, right_title):
                join(left_document, right_document)
    best_score: dict[str, float] = {}
    dates: dict[str, str] = {}
    for item in items:
        document = str(item.get("documentId"))
        best_score[document] = max(best_score.get(document, 0.0), float(item.get("effectiveScore", item.get("score")) or 0.0))
        dates.setdefault(document, str(item.get("publishedDate") or ""))
    groups: dict[str, list[str]] = {}
    for document in documents:
        groups.setdefault(root(document), []).append(document)
    keep = {max(members, key=lambda value: (dates[value], best_score[value])) for members in groups.values()}
    return [item for item in items if str(item.get("documentId")) in keep], len(documents) - len(keep)


def screen_verdicts(codes: dict[str, Any]) -> list[dict[str, Any]]:
    """{S1: "RELEVANT_A", S2: "TOPIC_ONLY"} from the screen call into verdicts with a reason and a subject group."""
    verdicts = []
    for identifier, code in codes.items():
        if not isinstance(identifier, str) or not isinstance(code, str) or code not in SCREEN_CODES:
            continue
        relevant = code.startswith("RELEVANT_")
        verdicts.append({"id": identifier, "relevant": relevant, "reason": "RELEVANT" if relevant else code,
                         "subject": code.rsplit("_", 1)[1] if relevant else None})
    return verdicts


def apply_screen(items: list[dict[str, Any]], verdicts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep passages the screen marked relevant; a passage the screen did not label is dropped (fail closed)."""
    by_id: dict[str, dict[str, Any]] = {}
    for verdict in verdicts:
        if isinstance(verdict, dict) and isinstance(verdict.get("id"), str):
            by_id.setdefault(verdict["id"], verdict)
    kept, dropped = [], []
    for item in items:
        verdict = by_id.get(str(item.get("id"))) or {}
        reason = verdict.get("reason") if verdict.get("reason") in SCREEN_REASONS else "TOPIC_ONLY"
        if verdict.get("relevant") is True and reason == "RELEVANT":
            kept.append({**item, "subject": verdict.get("subject") or "A"})
        else:
            dropped.append({"id": item.get("id"), "documentId": item.get("documentId"),
                            "reason": reason if reason != "RELEVANT" else "TOPIC_ONLY", "source": "screen"})
    return kept, dropped


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def published_year(item: dict[str, Any]) -> int | None:
    parsed = parse_date(item.get("publishedDate"))
    return parsed.year if parsed else None


def apply_recency(items: list[dict[str, Any]], yearly: bool, question_years: list[int], today: date, window_days: int) -> tuple[list[dict[str, Any]], bool]:
    """For yearly topics asked without a year, keep only recent documents; when none is recent, mark the old ones outdated."""
    if not yearly or question_years:
        return items, False
    recent = [item for item in items if (parsed := parse_date(item.get("publishedDate"))) and 0 <= (today - parsed).days <= window_days]
    if recent:
        return recent, False
    marked = [{**item, "outdated": parse_date(item.get("publishedDate")) is not None} for item in items]
    return marked, any(item["outdated"] for item in marked)


def clarification_documents(items: list[dict[str, Any]], multiple_projects: bool, ratio: float, minimum_score: float) -> list[dict[str, Any]]:
    """Best passage of each subject to ask about, only when two or more distinct relevant subjects tie strongly.

    Passages without a screen subject count as their own subject per document.
    """
    if multiple_projects:
        return []
    # Documents about the same subject complement each other; only distinct subjects are alternatives to ask about.
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        subject = str(item.get("subject") or item.get("documentId"))
        if subject not in best or float(item.get("effectiveScore", 0)) > float(best[subject].get("effectiveScore", 0)):
            best[subject] = item
    ranked = sorted(best.values(), key=lambda value: -float(value.get("effectiveScore", 0)))
    if len(ranked) < 2:
        return []
    top = float(ranked[0].get("effectiveScore", 0))
    if top < minimum_score:
        return []
    tied = [item for item in ranked if float(item.get("effectiveScore", 0)) >= max(minimum_score, top * ratio)]
    return tied[:3] if len(tied) >= 2 else []


def display_date(value: Any) -> str | None:
    parsed = parse_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else None


def shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;:-—")
    if len(text) <= limit:
        return text
    cut = text[:max(1, limit - 1)]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-—") + "…"


ACT_TITLE = re.compile(r"^\s*(ordinul|ordin|decizia|decizie|dispozi[țţt]ia|dispozi[țţt]ie|hot[ăa]r[âîa]rea|hot[ăa]r[âîa]re|legea|lege|"
    r"regulamentul|regulament)\s+(?:nr\.?|№)\s*([^\s,;]+)", re.I)


def readable_subject(title: str, url: Any) -> str:
    """Subject for a choice label: act type/number plus subject, or a file-name derived subject for link-text titles."""
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    act = ACT_TITLE.match(title)
    if act:
        rest = title[act.end():]
        rest = re.sub(r"^\s*(?:din\s+[\d.\-/]+\s*)?", "", rest)
        rest = re.sub(r"^[\s—–-]*(?:cu privire la\s+)?", "", rest, flags=re.I)
        kind = act.group(1)[0].upper() + act.group(1)[1:].lower()
        return f"{kind} nr. {act.group(2)}" + (f" — {rest}" if rest else "")
    numbered = re.match(r"^\s*(?:nr\.?\s*)?(\d[\w/.-]*)\s+din\s+[\d.\-/]+\s*[—–-]?\s*(?:cu privire la\s+)?", title, re.I)
    if numbered:
        rest = title[numbered.end():]
        return f"Nr. {numbered.group(1)}" + (f" — {rest}" if rest else "")
    if title and not is_anchor_title(title) and not is_file_title(title):
        return title
    stem = FILE_EXTENSION.sub("", url_basename(url))
    stem = re.sub(r"^\d{6,}[_-]*", "", stem)
    candidate = re.sub(r"[_+]+|(?<=[^\d])-|-(?=[^\d])", " ", stem).strip()
    if [token for token in re.findall(r"[^\W\d_]{3,}", candidate) if fold(token) != "scan"] and len(candidate.split()) >= 2:
        return candidate[0].upper() + candidate[1:]
    fragment = re.split(r"\s+aici\b|\s+click\b|\s,|,", title.replace("_", " "), flags=re.I)[0]
    return fragment.strip() or title or "Document"


def choice_label(item: dict[str, Any], limit: int = 110) -> str:
    """Readable choice label from metadata: subject · publisher · dd.mm.yyyy, capped at `limit` characters.

    A generic page title ("Noutăți", "Anunț") is followed by the passage heading or the opening words of its quote.
    """
    suffix = " · ".join(value for value in (str(item.get("publisher") or item.get("district") or "").strip(),
                                             display_date(item.get("publishedDate"))) if value)
    subject = readable_subject(str(item.get("title") or ""), item.get("url"))
    if len(words(subject)) <= 2:
        detail = next((str(value) for value in item.get("heading") or [] if fold(value).strip() not in {"", fold(subject).strip()}), "")
        detail = detail or " ".join(str(item.get("exactQuote") or "").split()[:10])
        if detail:
            subject = f"{subject}: {detail}"
    if not suffix:
        return shorten(subject, limit)
    return f"{shorten(subject, max(20, limit - len(suffix) - 3))} · {suffix}"


def split_sentences(text: str) -> list[str]:
    """Sentence split that keeps abbreviations such as "str.", "nr." and initials inside their sentence."""
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", MARKER.sub("", str(text or "")))
    parts, start = [], 0
    for match in re.finditer(r"[.!?…]+\s+(?=[A-ZĂÂÎȘȚА-ЯЁ0-9\"„«(])", text):
        before = text[start:match.start()]
        previous = re.findall(r"[^\W_]+$", before)
        token = previous[0] if previous else ""
        if match.group(0).startswith(".") and (fold(token) in ABBREVIATIONS or len(token) == 1 or (token.isdigit() and len(token) <= 2)):
            continue
        parts.append(text[start:match.end()].strip())
        start = match.end()
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def render_answer(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int]:
    """Final deterministic citation check and rendering.

    Every sentence gets the [S#] markers of its claim; markers must point to retained passages, claims left without
    one are dropped, and only referenced passages are returned, renumbered S1.. in order of first use.
    Returns (text, claims, citations, droppedClaims).
    """
    retained = {str(item.get("id")): item for item in evidence}
    order: list[str] = []
    kept_claims, dropped = [], 0
    for claim in claims:
        identifiers = [value for value in dict.fromkeys(claim.get("evidenceIds") or []) if value in retained]
        sentences = split_sentences(str(claim.get("text") or ""))
        if not identifiers or not sentences:
            dropped += 1
            continue
        order.extend(value for value in identifiers if value not in order)
        kept_claims.append({**claim, "evidenceIds": identifiers, "sentences": sentences})
    mapping = {old: f"S{index}" for index, old in enumerate(order, 1)}
    citations = [{**retained[old], "id": mapping[old]} for old in order]
    lines, final_claims = [], []
    for claim in kept_claims:
        markers = " ".join(f"[{mapping[value]}]" for value in claim["evidenceIds"])
        lines.append(" ".join(f"{sentence} {markers}" for sentence in claim["sentences"]))
        final_claims.append({"text": " ".join(claim["sentences"]), "evidenceIds": [mapping[value] for value in claim["evidenceIds"]]})
    text = "\n".join(lines)
    if uncited_segments(text, {item["id"] for item in citations}):
        return "", [], [], len(claims)
    return text, final_claims, citations, dropped


def uncited_segments(text: str, allowed: set[str]) -> list[str]:
    """Answer sentences without a marker, or with a marker that points to no returned citation."""
    problems = []
    pieces = re.split(r"((?:\s*\[S[1-9][0-9]*\])+)", text)
    for index in range(0, len(pieces), 2):
        segment = pieces[index].strip()
        markers = MARKER.findall(pieces[index + 1]) if index + 1 < len(pieces) else []
        if not segment:
            continue
        if not markers or any(value[1:-1] not in allowed for value in markers) or len(split_sentences(segment)) != 1:
            problems.append(segment)
    return problems


def has_expected_value(claims: list[dict[str, Any]], answer_type: str, evidence: list[dict[str, Any]] | None = None) -> bool:
    """Hours, dates, amounts and legal acts must appear in at least one retained claim; other types are left to the verifier.

    A claim citing a passage of a legal act (by its document title) cites that act.
    """
    pattern = DETERMINISTIC_VALUES.get(answer_type)
    if pattern is None:
        return bool(claims)
    if any(pattern.search(fold(claim.get("text"))) or pattern.search(str(claim.get("text") or "")) for claim in claims):
        return True
    if answer_type != "legal_act":
        return False
    titles = {str(item.get("id")): str(item.get("title") or "") for item in evidence or []}
    return any(ACT_TITLE.match(titles.get(str(identifier), "")) for claim in claims for identifier in claim.get("evidenceIds") or [])


def not_found_reason(*, in_scope: bool, relevant: int, claims: int, lacks_value: bool) -> str:
    """Why nothing could be answered: out of scope or no relevant passage, the passages lack the value, or claims failed."""
    if relevant == 0:
        return "NO_RELEVANT_EVIDENCE" if in_scope else "OUT_OF_SCOPE"
    if claims == 0 or lacks_value:
        return "EVIDENCE_LACKS_VALUE"
    return "CLAIMS_UNVERIFIED"


def not_found_answer(language: str, reason: str, answer_type: str = "other") -> str:
    language = language if language in LANGUAGES else "ro"
    template = NOT_FOUND_TEMPLATES.get(reason, NOT_FOUND_TEMPLATES["NO_RELEVANT_EVIDENCE"])[language]
    return template.format(value=TYPE_NAMES[language].get(answer_type, TYPE_NAMES[language]["other"]))


def clarification_question(language: str) -> str:
    return CLARIFICATION_TEMPLATES.get(language, CLARIFICATION_TEMPLATES["ro"])


def outdated_note(language: str, citations: list[dict[str, Any]]) -> str:
    """Sentence naming the years of outdated sources, cited with their own markers so it passes the citation check."""
    outdated = [item for item in citations if item.get("outdated")]
    years = sorted({year for item in outdated if (year := published_year(item))})
    if not years:
        return ""
    markers = " ".join(f"[{item['id']}]" for item in outdated)
    return OUTDATED_TEMPLATES.get(language, OUTDATED_TEMPLATES["ro"]).format(years=", ".join(str(year) for year in years)) + f" {markers}"


def build_flags(*, off_topic: int = 0, duplicates: int = 0, outdated: bool = False, rejected: int = 0, total: int = 0, corrected: bool = False) -> list[str]:
    flags = []
    if off_topic:
        flags.append(f"OFF_TOPIC_DROPPED:{off_topic}")
    if duplicates:
        flags.append(f"DUPLICATES_MERGED:{duplicates}")
    if outdated:
        flags.append("OUTDATED_SOURCES")
    if rejected:
        flags.append(f"CLAIMS_REJECTED:{rejected}/{total}")
    if corrected:
        flags.append("CORRECTION_ROUND")
    return flags


def recent_history(history: list[dict[str, str]] | None, turns: int, limit: int = 600) -> list[dict[str, str]]:
    """The last `turns` user/assistant pairs, trimmed, for rewriting follow-up questions."""
    items = [{"role": str(item.get("role")), "content": str(item.get("content") or "")[:limit]}
             for item in history or [] if item.get("role") in {"user", "assistant"} and str(item.get("content") or "").strip()]
    return items[-2 * turns:] if turns > 0 else []


def clarification_followup(message: str, history: list[dict[str, str]] | None) -> tuple[str, str] | None:
    """(original question, chosen label) when the user answers our last clarification with one of its choices."""
    items = [item for item in history or [] if item.get("role") in {"user", "assistant"}]
    if len(items) < 2 or items[-1].get("role") != "assistant" or items[-2].get("role") != "user":
        return None
    content = str(items[-1].get("content") or "")
    known = list(CLARIFICATION_TEMPLATES.values()) + list(LEGACY_CLARIFICATIONS)
    if not any(content.strip().startswith(template) for template in known):
        return None
    labels = [line.strip()[2:].strip() for line in content.splitlines() if line.strip().startswith("- ")]
    if not labels:
        return None
    chosen = fold(message).strip(" .!?\"'«»-")
    ordinals = {"1": 0, "2": 1, "3": 2, "primul": 0, "prima": 0, "al doilea": 1, "a doua": 1, "al treilea": 2, "a treia": 2,
                "first": 0, "second": 1, "third": 2, "первый": 0, "первая": 0, "второй": 1, "вторая": 1, "третий": 2, "третья": 2}
    if chosen in ordinals and ordinals[chosen] < len(labels):
        return str(items[-2].get("content") or ""), labels[ordinals[chosen]]
    for label in labels:
        folded = fold(label)
        if chosen and (chosen == folded or (len(chosen) >= 8 and (folded.startswith(chosen) or chosen in folded)) or folded in chosen):
            return str(items[-2].get("content") or ""), label
    return None
