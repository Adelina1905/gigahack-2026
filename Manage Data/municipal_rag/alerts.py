"""In-app project alerts: topic extraction from resident questions and matching against an update feed.

The update feed is precomputed offline (build_alert_feed.py), including document embeddings. While serving,
only topic queries are embedded; feed documents are never embedded here.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import re
import struct
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, Sequence

from .config import ROOT


LOGGER = logging.getLogger(__name__)

DEFAULT_FEED = ROOT / "config" / "alerts_feed.demo.json"
EMBEDDING_ENCODING = "float16-base64-le"
MAX_TOPICS = 4
MAX_LABEL = 80
MAX_QUERY = 300
MAX_EXCERPT = 400

# Calibrated on config/alerts_feed.demo.json (qwen3-embedding-8b, instructed queries, cosine clamped to 0..1):
# typical topic queries score a median ~0.45 against the feed, unrelated documents rarely exceed 0.58, and
# related ones score 0.6-0.85, so 0.6 yields 0-7 matches per topic out of 60.
DEFAULT_EMBEDDING_THRESHOLD = 0.6
# Qwen3 embeddings expect an instruction on the query side only; feed documents are embedded without one.
QUERY_INSTRUCTION = ("Instruct: Given a topic a resident follows, retrieve Chișinău municipal announcements "
                     "and documents about it\nQuery: ")
# Share of the query's (weighted) keywords found in a document; about half of the key terms must match.
DEFAULT_LEXICAL_THRESHOLD = 0.5

Embedder = Callable[[str], Sequence[float]]
JsonCompleter = Callable[[str, str, dict[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------- data


@dataclass(frozen=True)
class FeedDocument:
    document_id: str
    title: str
    url: str | None
    source: str | None
    district: str | None
    category: str | None
    published_date: str | None
    excerpt: str
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Topic:
    label: str
    query: str


@dataclass(frozen=True)
class TopicQuery:
    id: str
    query: str
    min_score: float | None = None


@dataclass(frozen=True)
class AlertMatch:
    topic_id: str
    document: FeedDocument
    score: float


@dataclass(frozen=True)
class MatchResult:
    matcher: Literal["embedding", "lexical"]
    matches: list[AlertMatch]


# ---------------------------------------------------------------- text helpers


_COMBINING = re.compile(r"[̀-ͯ]")
_TOKEN = re.compile(r"[a-z0-9а-я]+")
_ROMANIAN_SUFFIXES = ("urilor", "ului", "ilor", "elor", "iile", "ile", "ele", "lor", "ul", "ua", "ei", "ii",
                      "le", "a", "e", "i", "u")
STOPWORDS = frozenset("""
a ai al ale am ar are as au ca care ce cei cel cele cum cu da dar de despre din dintre do este eu fi fie
in intr intre la le lui ma mai mea meu mi mie mult nu noi o ori pe pentru poate prin sa sau se si sunt ta
te tu un una unde unei unui va voi vreau cand cine cat cate acest aceasta aceste acesti acel acea asta
avea aveti buna ziua salut va rog multumesc imi spuneti spune stiu exista trebuie putea pot
chisinau chisinaului municipiul municipiului mun primaria primariei oras orasul
и в во на не что как где когда кто это эти этот та те то по с со к ко о об от до для из за или а но же ли
бы вы мы я он она они мне меня мой моя есть был была было будет можно нужно надо какие какой какая
здравствуйте пожалуйста спасибо кишинев кишиневе кишинева
""".split())


def normalize(text: str) -> str:
    """Lowercase and strip diacritics (Romanian ă/â/î/ș/ț in either cedilla or comma form, Cyrillic й/ё)."""
    return _COMBINING.sub("", unicodedata.normalize("NFKD", text.lower()))


def stem(token: str) -> str:
    if token.isascii():
        for suffix in _ROMANIAN_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                token = token[: -len(suffix)]
                break
    return token[:7]


def keywords(text: str) -> list[str]:
    """Distinct content-word stems of a text, in order of first appearance."""
    seen: dict[str, None] = {}
    for token in _TOKEN.findall(normalize(text)):
        if len(token) >= 3 and token not in STOPWORDS and not token.isdigit():
            seen.setdefault(stem(token), None)
    return list(seen)


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-–") + "…"


def encode_vector(vector: Sequence[float]) -> str:
    return base64.b64encode(struct.pack(f"<{len(vector)}e", *vector)).decode("ascii")


def decode_vector(value: str) -> tuple[float, ...]:
    raw = base64.b64decode(value)
    return struct.unpack(f"<{len(raw) // 2}e", raw)


def _unit(vector: Sequence[float]) -> tuple[float, ...] | None:
    norm = math.sqrt(sum(value * value for value in vector))
    return None if norm == 0 else tuple(value / norm for value in vector)


# ---------------------------------------------------------------- feed


class UpdateFeed(Protocol):
    def documents(self) -> Sequence[FeedDocument]: ...


class JsonUpdateFeed:
    """The demo update feed exported by build_alert_feed.py; loaded once, read-only."""

    def __init__(self, path: Path = DEFAULT_FEED) -> None:
        self._documents = self._load(path)

    def documents(self) -> Sequence[FeedDocument]:
        return self._documents

    @staticmethod
    def _load(path: Path) -> list[FeedDocument]:
        if not path.is_file():
            LOGGER.warning("Alert feed %s is missing; alerts will never match", path)
            return []
        value = json.loads(path.read_text(encoding="utf-8"))
        encoding = value.get("embeddingEncoding")
        documents = []
        for item in value.get("documents", []):
            vector = item.get("embedding")
            embedding = decode_vector(vector) if isinstance(vector, str) and encoding == EMBEDDING_ENCODING else None
            documents.append(FeedDocument(
                document_id=str(item["documentId"]), title=str(item["title"]), url=item.get("url"),
                source=item.get("source"), district=item.get("district"), category=item.get("category"),
                published_date=item.get("publishedDate"), excerpt=clip(str(item.get("excerpt") or ""), MAX_EXCERPT),
                embedding=embedding))
        return documents


class StaticUpdateFeed:
    """An in-memory feed, handy for tests and fixtures."""

    def __init__(self, documents: Sequence[FeedDocument]) -> None:
        self._documents = list(documents)

    def documents(self) -> Sequence[FeedDocument]:
        return self._documents


# ---------------------------------------------------------------- matchers


class Matcher(Protocol):
    name: Literal["embedding", "lexical"]
    default_threshold: float

    def is_available(self) -> bool: ...

    def scores(self, query: str) -> list[float]:
        """One score in 0..1 per feed document, aligned with feed.documents()."""
        ...


class EmbeddingMatcher:
    """Cosine similarity between an embedded topic query and the feed's precomputed document embeddings."""

    name: Literal["embedding"] = "embedding"

    def __init__(self, feed: UpdateFeed, embedder: Embedder,
                 default_threshold: float = DEFAULT_EMBEDDING_THRESHOLD, cache_size: int = 1024) -> None:
        self.default_threshold = default_threshold
        self._embedder = embedder
        self._cache: OrderedDict[str, tuple[float, ...] | None] = OrderedDict()
        self._cache_size = cache_size
        documents = feed.documents()
        self._vectors = [None if item.embedding is None else _unit(item.embedding) for item in documents]

    def is_available(self) -> bool:
        return bool(self._vectors) and all(vector is not None for vector in self._vectors)

    def scores(self, query: str) -> list[float]:
        vector = self._query_vector(query)
        results = []
        for document in self._vectors:
            if vector is None or document is None or len(document) != len(vector):
                results.append(0.0)
            else:
                results.append(max(0.0, min(1.0, sum(a * b for a, b in zip(vector, document)))))
        return results

    def _query_vector(self, query: str) -> tuple[float, ...] | None:
        key = " ".join(query.split())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        vector = _unit([float(value) for value in self._embedder(key)])
        self._cache[key] = vector
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return vector


class LexicalMatcher:
    """Diacritic-insensitive keyword overlap; title hits count fully, excerpt/metadata hits partially."""

    name: Literal["lexical"] = "lexical"

    def __init__(self, feed: UpdateFeed, default_threshold: float = DEFAULT_LEXICAL_THRESHOLD,
                 body_weight: float = 0.7) -> None:
        self.default_threshold = default_threshold
        self._body_weight = body_weight
        self._documents = []
        for item in feed.documents():
            title = set(keywords(item.title))
            body = set(keywords(" ".join(filter(None, [item.excerpt, item.category, item.district, item.source]))))
            self._documents.append((title, body))

    def is_available(self) -> bool:
        return True

    def scores(self, query: str) -> list[float]:
        terms = keywords(query)
        if not terms:
            return [0.0] * len(self._documents)
        results = []
        for title, body in self._documents:
            hits = sum(1.0 if term in title else self._body_weight if term in body else 0.0 for term in terms)
            results.append(round(min(1.0, hits / len(terms)), 4))
        return results


# ---------------------------------------------------------------- topic extraction


class TopicExtractor(Protocol):
    def extract(self, questions: Sequence[str], existing_labels: Sequence[str]) -> list[Topic]: ...


@dataclass(frozen=True)
class _Theme:
    label: str
    query: str
    patterns: tuple[str, ...]


# Patterns are regexes over normalize()d text, anchored at a word start.
THEMES: tuple[_Theme, ...] = (
    _Theme("Transport public", "transport public rute troleibuz autobuz orar circulație",
           ("troleibuz", "autobuz", "microbuz", "transport", "rut(a|ei|e|ele)\\b", "orar", "calator",
            "троллейбус", "тролейбус", "автобус", "маршрут", "транспорт")),
    _Theme("Lucrări la drumuri și trafic", "reparație străzi drumuri trafic rutier suspendare circulație",
           ("strad", "strazi", "drum", "trafic", "asfalt", "carosabil", "trotuar", "pod\\b",
            "дорог", "улиц", "пробк", "асфальт", "тротуар")),
    _Theme("Parcări", "parcare parcări publice locuri de parcare", ("parcar", "парков")),
    _Theme("Apă și canalizare", "apă potabilă canalizare deconectare apă Apă-Canal",
           ("apa\\b", "apei\\b", "canaliz", "apa-canal", "вод[аыуе]", "водопровод", "канализ")),
    _Theme("Încălzire și agent termic", "încălzire agent termic apă caldă termoficare",
           ("incalz", "caldur", "termic", "termoficar", "calorifer", "apa calda", "отоплен", "тепл", "батаре",
            "горяч")),
    _Theme("Școli și grădinițe", "școli grădinițe educație înscriere elevi instituții de învățământ",
           ("scoal", "scoli", "gradinit", "liceu", "elev", "educat", "invatam", "inscrier", "profesor",
            "школ", "детск", "сад\\b", "садик", "лице", "учени", "образован")),
    _Theme("Sănătate și servicii medicale", "servicii medicale centre de sănătate asistență medicală vaccinare",
           ("medic", "spital", "sanat", "clinic", "vaccin", "policlinic", "врач", "больниц", "поликлиник",
            "здоров", "вакцин", "медицин")),
    _Theme("Asistență socială", "asistență socială ajutor material compensații persoane vulnerabile",
           ("social", "ajutor", "pensi", "dizabilit", "compensat", "vulnerabil", "refugiat", "помощ", "пенси",
            "социальн", "компенсац", "инвалид", "беженц")),
    _Theme("Evenimente și cultură", "evenimente culturale festival concert sărbători expoziție",
           ("eveniment", "festival", "concert", "cultur", "sarbato", "expozit", "teatr", "muze", "turis",
            "событ", "фестивал", "концерт", "культур", "праздн", "выставк", "театр", "музе")),
    _Theme("Tineret și sport", "tineret sport voluntariat centre de tineret granturi",
           ("tiner", "sport", "voluntar", "молодеж", "спорт", "волонт")),
    _Theme("Decizii și acte locale", "decizii dispoziții Consiliul Municipal acte locale hotărâri",
           ("decizi", "dispozit", "consiliul", "hotarar", "regulament", "решени", "распоряжен", "постановлен",
            "совет")),
    _Theme("Salubrizare și deșeuri", "salubrizare colectare deșeuri gunoi curățenie",
           ("gunoi", "deseu", "salubr", "curaten", "мусор", "отход", "уборк")),
    _Theme("Locuințe și blocuri", "blocuri locative ascensoare lifturi locuințe asociații de proprietari",
           ("bloc", "lift", "ascensor", "locuint", "apartament", "лифт", "квартир", "жиль")),
    _Theme("Comerț și autorizări", "comerț autorizații de funcționare patente piețe alimentație publică",
           ("comert", "autorizat", "licent", "patent", "piat", "торгов", "разрешени", "рынк", "рынок")),
)

DISTRICTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Botanica", ("botanica", "ботаник")),
    ("Buiucani", ("buiucani", "буюкан")),
    ("Centru", ("sectorul centru", "sector centru", "центр")),
    ("Ciocana", ("ciocana", "чекан")),
    ("Râșcani", ("rascani", "riscani", "рышкан")),
)


def _compile(patterns: Sequence[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?<![\\w])(?:{normalize(pattern)})" for pattern in patterns))


class KeywordTopicExtractor:
    """Deterministic fallback: known municipal themes (RO/RU triggers), else the question's key words."""

    def __init__(self) -> None:
        self._themes = [(theme, _compile(theme.patterns)) for theme in THEMES]
        self._districts = [(name, _compile(patterns)) for name, patterns in DISTRICTS]

    def extract(self, questions: Sequence[str], existing_labels: Sequence[str]) -> list[Topic]:
        text = normalize("\n".join(questions))
        hits = [(len(pattern.findall(text)), index, theme) for index, (theme, pattern) in enumerate(self._themes)]
        ranked = [theme for count, _, theme in sorted(hits, key=lambda item: (-item[0], item[1])) if count]
        districts = [name for name, pattern in self._districts if pattern.search(text)]
        district = districts[0] if len(districts) == 1 else None
        topics = []
        for theme in ranked:
            if district:
                topics.append(Topic(f"{theme.label} – sectorul {district}", f"{theme.query} sectorul {district}"))
            else:
                topics.append(Topic(theme.label, theme.query))
        if not topics:
            topics = [topic for topic in map(self._from_words, questions) if topic is not None]
        return finalize_topics(topics, existing_labels)

    @staticmethod
    def _from_words(question: str) -> Topic | None:
        if re.search(r"[Ѐ-ӿ]", question):
            return None  # Only Romanian output is allowed; unknown Russian phrasing has no safe translation.
        words = [word for word in re.findall(r"[^\W\d_][\w-]*", question)
                 if len(word) >= 3 and normalize(word) not in STOPWORDS]
        if len(words) < 1:
            return None
        phrase = " ".join(words[:5])
        return Topic(phrase[:1].upper() + phrase[1:], phrase)


TOPIC_SYSTEM = (
    "You turn a resident's questions to Chișinău city hall into 0 to 4 alert topics, so the resident can be "
    "notified when new municipal documents or announcements about those subjects are published. "
    "Each topic has a short human-readable Romanian label (at most 60 characters, e.g. 'Orarul troleibuzelor', "
    "'Deconectări de apă în Botanica') and a Romanian search query (at most 25 words) with the key terms and "
    "close synonyms. Questions may be in Romanian or Russian; always answer in Romanian with correct diacritics. "
    "Keep street, district and institution names. Merge overlapping subjects, skip greetings and small talk, and "
    "never return a topic equivalent to one of the existing labels. Return {\"topics\": []} when nothing fits."
)
TOPIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "query"],
        "properties": {"label": {"type": "string"}, "query": {"type": "string"}},
    }}},
}


class LlmTopicExtractor:
    """Topic extraction through an injected structured-JSON completer; any failure uses the fallback."""

    def __init__(self, complete_json: JsonCompleter, fallback: TopicExtractor,
                 max_question_chars: int = 12000) -> None:
        self._complete_json = complete_json
        self._fallback = fallback
        self._max_question_chars = max_question_chars

    def extract(self, questions: Sequence[str], existing_labels: Sequence[str]) -> list[Topic]:
        lines, used = [], 0
        for question in reversed(questions):  # Most recent questions win when the prompt must be trimmed.
            line = "- " + " ".join(question.split())[:1000]
            if used + len(line) > self._max_question_chars:
                break
            lines.insert(0, line)
            used += len(line)
        existing = "\n".join(f"- {label}" for label in existing_labels) or "(none)"
        user = f"Existing labels:\n{existing}\n\nResident questions:\n" + "\n".join(lines)
        try:
            value = self._complete_json(TOPIC_SYSTEM, user, TOPIC_SCHEMA)
            items = value["topics"]
            if not isinstance(items, list):
                raise ValueError("topics is not a list")
            topics = [Topic(str(item["label"]), str(item["query"])) for item in items if isinstance(item, dict)]
        except Exception as error:  # noqa: BLE001 - LLM failures must never fail the request.
            LOGGER.warning("Topic extraction LLM failed, using keyword fallback: %s", type(error).__name__)
            return self._fallback.extract(questions, existing_labels)
        return finalize_topics(topics, existing_labels)


def finalize_topics(topics: Sequence[Topic], existing_labels: Sequence[str]) -> list[Topic]:
    """Trim to contract limits, drop blanks and case-insensitive duplicates of each other or existingLabels."""
    seen = {" ".join(label.split()).casefold() for label in existing_labels}
    result = []
    for topic in topics:
        label = clip(topic.label, MAX_LABEL)
        query = clip(topic.query, MAX_QUERY) or clip(label, MAX_QUERY)
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        result.append(Topic(label, query))
        if len(result) == MAX_TOPICS:
            break
    return result


# ---------------------------------------------------------------- service


class AlertService:
    """Topic extraction plus feed matching; embedding scores when possible, lexical otherwise."""

    def __init__(self, feed: UpdateFeed, extractor: TopicExtractor, lexical: Matcher,
                 embedding: Matcher | None = None) -> None:
        self._feed = feed
        self._extractor = extractor
        self._lexical = lexical
        self._embedding = embedding

    def topics(self, questions: Sequence[str], existing_labels: Sequence[str]) -> list[Topic]:
        return self._extractor.extract(questions, existing_labels)

    def match(self, topics: Sequence[TopicQuery], excluded_document_ids: Sequence[str], limit: int) -> MatchResult:
        if self._embedding is not None and self._embedding.is_available():
            try:
                return self._match_with(self._embedding, topics, excluded_document_ids, limit)
            except Exception as error:  # noqa: BLE001 - fall back to lexical on any embedding failure.
                LOGGER.warning("Embedding matcher failed, using lexical fallback: %s", type(error).__name__)
        return self._match_with(self._lexical, topics, excluded_document_ids, limit)

    def _match_with(self, matcher: Matcher, topics: Sequence[TopicQuery], excluded: Sequence[str],
                    limit: int) -> MatchResult:
        documents = self._feed.documents()
        excluded_ids = set(excluded)
        best: dict[int, AlertMatch] = {}
        for topic in topics:
            threshold = matcher.default_threshold if topic.min_score is None else topic.min_score
            for index, score in enumerate(matcher.scores(topic.query)):
                document = documents[index]
                if score < threshold or document.document_id in excluded_ids:
                    continue
                current = best.get(index)
                if current is None or score > current.score:
                    best[index] = AlertMatch(topic.id, document, round(score, 4))
        ranked = sorted(best.values(), key=lambda item: (-item.score, item.document.document_id))
        return MatchResult(matcher.name, ranked[:limit])


def create_alert_service(api_key: str, embedding_model: str, generator_model: str, *,
                         use_ai: bool = True, feed_path: Path = DEFAULT_FEED) -> AlertService:
    """Real wiring: embeddings + LLM topics when an API key is set and AI is allowed, lexical/keyword otherwise."""
    from .api import chat_json, embed

    feed = JsonUpdateFeed(feed_path)
    keyword = KeywordTopicExtractor()
    lexical = LexicalMatcher(feed)
    if not (use_ai and api_key):
        return AlertService(feed, keyword, lexical)

    def embedder(text: str) -> list[float]:
        return embed(QUERY_INSTRUCTION + text, embedding_model, api_key)

    def complete_json(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return chat_json(generator_model, system, user, api_key, schema)

    return AlertService(feed, LlmTopicExtractor(complete_json, keyword), lexical, EmbeddingMatcher(feed, embedder))
