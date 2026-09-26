"""Export a small demo update feed for in-app project alerts from the scraper corpus (offline, one-off).

Reads the scraper's manifest.sqlite read-only, picks recent, diverse, well-titled tier 1-2 Romanian documents,
and writes config/alerts_feed.demo.json with a clean excerpt and a precomputed embedding per document
(float16, base64). The serving process never embeds feed documents; it only embeds topic queries.

    .venv/bin/python build_alert_feed.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from municipal_rag.alerts import DEFAULT_FEED, EMBEDDING_ENCODING, MAX_EXCERPT, clip, encode_vector, normalize
from municipal_rag.api import request_json
from municipal_rag.config import load_config, load_dotenv


DEFAULT_SCRAPER_DATA = Path("/home/debian/gigahack-scraper/poc/data")

# Bucket -> (sources, title/text regex over normalized text or None, per-bucket quota weight).
BUCKETS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "events_culture": (("visit.chisinau.md", "e-tineret.md", "chisinaucentru.md", "botanica.md", "rascani.md",
                        "preturabuiucani.md", "ciocana.md", "chisinauedu.dgets.md", "extrascolar.md"),
                       r"festival|concert|eveniment|sarbator|expozit|cultur|turis|spectacol|tineret|voluntar"),
    "education": (("detsriscani.md", "buiucanidets.md", "detscentru.md", "detsbotanica.md", "chisinauedu.dgets.md",
                   "extrascolar.md", "escoala.chisinau.md", "educatieonline.md"),
                  r"scoal|scoli|gradinit|liceu|elev|educat|inscrier|an(ul)? de studii|examen|olimpiad|profesor"),
    "transport": (("rtec.md", "mobilitatechisinau.md", "autourban.md", "actelocale.gov.md"),
                  r"troleibuz|autobuz|transport|ruta|trafic|parcar|strada|circulat"),
    "utilities": (("acc.md", "dglca.md", "infocom.md", "liftservice.md", "actelocale.gov.md", "chisinaucentru.md",
                   "botanica.md"),
                  r"\bapa\b|apei|canaliz|termic|incalz|caldur|ascensor|lift|iluminat|salubr|deseu|amenaj"),
    "healthcare": (("help.chisinau.md", "dgams.md", "amt-centru.md", "amt-ciocana.md", "amt-botanica.md",
                    "amtriscani.md", "amtbuiucani.md", "actelocale.gov.md", "rascani.md", "botanica.md",
                    "chisinaucentru.md"),
                   r"medic|sanat|vaccin|clinic|spital|screening|pacient|consult"),
    "social_help": (("dgams.md", "help.chisinau.md", "actelocale.gov.md", "botanica.md", "rascani.md"),
                    r"social|ajutor|refugiat|vulnerabil|dizabilit|compensat|varstnic|fara domiciliu|beneficiar"),
    "local_acts": (("actelocale.gov.md",), r"cu privire la"),
    "district_admin": (("chisinaucentru.md", "botanica.md", "rascani.md", "preturabuiucani.md", "ciocana.md"), None),
}

TITLE_NOISE = re.compile(
    r"^(tur retur|trimestrul|primaria municipiului chisinau|plan (de achizitii|provizoriu|suplimentar)|"
    r"cheltuieli transparente|regulamentul de activitate|transparenta decizionala|anexa|raport|"
    r"formular|programare|pagina web|contacte|despre|pretura sectorului|la multi ani|registrul|acord aditional|"
    r"servicii in vigoare|rapoarte|circulara|functii vacante|anul \d{4}|gimnaziul nr|liceul teoretic|"
    r"direc[tț]ia (educatie|generala)|imsp|rezultate(le)? concurs)|achizit|functi(a|ei|ilor) public|"
    r"cheltuieli transp|ocuparea func|concursul (pentru|privind)|plan de (actiuni|investitii)|scrisoare|"
    r"regulament|legi,|concediu|declaratia de raspundere|strategia de comunicare|cheltuiel|sedint|"
    r"persoanelor responsabile|^ims\W", re.I)
TITLE_SUFFIX = re.compile(r"\s*(?:[–—|-]\s*(?:pretura|regia|help\.chisinau|chisinau$|mobilitatechisinau|"
                          r"direc[tţț]ia|primăria|primaria|s\.a\.|apă-canal|dglca)[^–—|]*|\s+-\s+\S+\.md)$", re.I)


def clean_title(title: str) -> str:
    title = " ".join(title.split())
    for _ in range(2):
        title = TITLE_SUFFIX.sub("", title).strip()
    return title


def clean_text(text: str, title: str) -> str:
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = re.sub(r"[*_`>|]+", " ", text)
    text = " ".join(text.split())
    if normalize(text).startswith(normalize(title)[:60]):
        text = text[len(title):].lstrip(" .:–-")
    return text


def canonical_url(record: dict[str, Any], manifest_urls: list[str]) -> str | None:
    return ((record.get("act") or {}).get("detail_url") or (record.get("urls") or [{}])[0].get("url")
            or (manifest_urls[0] if manifest_urls else None))


def candidates(connection: sqlite3.Connection, data: Path, since: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT e.sha1, e.text_path, e.doc_date, e.chars, c.tier,
                  (SELECT d.source FROM documents d WHERE d.sha1 = e.sha1 AND d.file_path IS NOT NULL LIMIT 1) AS source
           FROM extracted e JOIN curation c ON c.sha1 = e.sha1
           WHERE c.tier IN (1, 2) AND e.status = 'ok' AND e.text_path IS NOT NULL AND e.lang = 'ro'
             AND e.doc_date >= ? AND e.chars BETWEEN 300 AND 60000
             AND EXISTS (SELECT 1 FROM documents d WHERE d.sha1 = e.sha1 AND d.file_path IS NOT NULL)
           ORDER BY e.doc_date DESC, e.sha1""", (since,)).fetchall()
    result = []
    for sha1, text_path, doc_date, _, tier, source in rows:
        path = data / text_path
        if not path.is_file():
            continue
        result.append({"sha1": sha1, "path": path, "date": doc_date, "tier": tier, "source": source})
    return result


def load_record(connection: sqlite3.Connection, candidate: dict[str, Any]) -> dict[str, Any] | None:
    record = json.loads(candidate["path"].read_text(encoding="utf-8"))
    title = clean_title(str(record.get("title") or ""))
    if not 30 <= len(title) <= 220 or len(title.split()) < 5 or TITLE_NOISE.search(normalize(title)) or record.get("quality_flags"):
        return None
    pages = record.get("pages")
    text = " ".join(page.get("text", "") for page in pages) if pages is not None else str(record.get("text") or "")
    text = clean_text(text, title)
    if len(text) < 200:
        return None
    urls = [row[0] for row in connection.execute(
        "SELECT url FROM documents WHERE sha1 = ? AND file_path IS NOT NULL ORDER BY url", (candidate["sha1"],))]
    date = candidate["date"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate["date"] or "") else None
    return {
        "documentId": candidate["sha1"], "title": title, "url": canonical_url(record, urls),
        "source": record.get("source") or candidate["source"], "district": record.get("district"),
        "category": record.get("category"), "publishedDate": date, "excerpt": clip(text, MAX_EXCERPT),
        "_text": text,
    }


def select(connection: sqlite3.Connection, pool: list[dict[str, Any]], total: int,
           per_source: int) -> list[dict[str, Any]]:
    quota = max(1, -(-total // len(BUCKETS)))
    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    source_counts: dict[str, int] = defaultdict(int)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in pool:
        by_source[candidate["source"]].append(candidate)
    cache: dict[str, dict[str, Any] | None] = {}

    def record(candidate: dict[str, Any]) -> dict[str, Any] | None:
        if candidate["sha1"] not in cache:
            cache[candidate["sha1"]] = load_record(connection, candidate)
        return cache[candidate["sha1"]]

    for bucket, (sources, pattern) in BUCKETS.items():
        regex = re.compile(pattern) if pattern else None
        taken = 0
        cursors = {source: 0 for source in sources}
        while taken < quota and any(cursors[source] < len(by_source[source]) for source in sources):
            for source in sources:  # Round-robin across sources for diversity.
                if taken >= quota:
                    break
                items = by_source[source]
                while cursors[source] < len(items):
                    candidate = items[cursors[source]]
                    cursors[source] += 1
                    cap = per_source * 3 if source == "actelocale.gov.md" else per_source
                    if candidate["sha1"] in seen_ids or source_counts[source] >= cap:
                        continue
                    item = record(candidate)
                    if item is None:
                        continue
                    key = normalize(item["title"])[:70]
                    haystack = normalize(item["title"])
                    if key in seen_titles or (regex is not None and not regex.search(haystack)):
                        continue
                    seen_ids.add(candidate["sha1"])
                    seen_titles.add(key)
                    source_counts[source] += 1
                    chosen.append({**item, "bucket": bucket})
                    taken += 1
                    break
        print(f"[select] {bucket}: {taken}", file=sys.stderr)
    return chosen[:total]


def embed_documents(items: list[dict[str, Any]], model: str, api_key: str, batch: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(items), batch):
        texts = [f"{item['title']}\n{item['_text'][:2000]}" for item in items[start:start + batch]]
        response = request_json("embeddings", {"model": model, "input": texts, "input_type": "search_document",
                                               "encoding_format": "float"}, api_key)
        data = sorted(response.get("data") or [], key=lambda entry: entry.get("index", 0))
        if len(data) != len(texts):
            raise RuntimeError(f"Expected {len(texts)} embeddings, received {len(data)}")
        vectors.extend([float(value) for value in entry["embedding"]] for entry in data)
        print(f"[embed] {len(vectors)}/{len(items)}", file=sys.stderr)
    return vectors


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the demo alerts update feed from the scraper corpus.")
    parser.add_argument("--scraper-data", type=Path, default=DEFAULT_SCRAPER_DATA,
                        help="Scraper data directory holding manifest.sqlite and text/.")
    parser.add_argument("--output", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--count", type=int, default=60, help="Number of documents to export.")
    parser.add_argument("--per-source", type=int, default=6, help="Maximum documents from one source.")
    parser.add_argument("--since", default="2025-01-01", help="Earliest document date (YYYY-MM-DD).")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--no-embeddings", action="store_true", help="Write the feed without embeddings.")
    arguments = parser.parse_args()
    if not 1 <= arguments.count <= 500:
        parser.error("--count must be between 1 and 500")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    load_dotenv()
    config = load_config()
    database = arguments.scraper_data / "manifest.sqlite"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30)
    pool = candidates(connection, arguments.scraper_data, arguments.since)
    items = select(connection, pool, arguments.count, arguments.per_source)
    connection.close()

    embedded = False
    api_key = os.environ.get(arguments.api_key_env, "").strip()
    if not arguments.no_embeddings:
        try:
            vectors = embed_documents(items, config.embedding_model, api_key, arguments.batch_size)
            for item, vector in zip(items, vectors):
                item["embedding"] = encode_vector(vector)
            embedded = True
        except Exception as error:  # noqa: BLE001 - still write a lexical-only feed.
            reason = str(error).replace(api_key, "***") if api_key else str(error)
            print(f"[embed] unavailable, writing feed without embeddings: {reason}", file=sys.stderr)

    documents = [{key: value for key, value in item.items() if not key.startswith("_") and key != "bucket"}
                 for item in items]
    feed = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "gigahack-scraper manifest.sqlite (tiers 1-2)",
        "embeddingModel": config.embedding_model if embedded else None,
        "embeddingEncoding": EMBEDDING_ENCODING if embedded else None,
        "documents": documents,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(feed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    buckets: dict[str, int] = defaultdict(int)
    categories: dict[str, int] = defaultdict(int)
    for item in items:
        buckets[item["bucket"]] += 1
        categories[str(item["category"])] += 1
    print(json.dumps({"output": str(arguments.output), "documents": len(documents), "embeddings": embedded,
                      "bytes": arguments.output.stat().st_size, "buckets": buckets, "categories": categories},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
