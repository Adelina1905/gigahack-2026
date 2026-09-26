"""Step 4: extract transparent dates and numeric facts without generating prose."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pipeline_core import DATA_DIRECTORY, read_json, stable_id, unique_preserving_order, write_versioned_json


DEFAULT_OUTPUT_DIRECTORY = DATA_DIRECTORY / "04_enriched"
ROMANIAN_MONTHS = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}
MONTH_PATTERN = "|".join(ROMANIAN_MONTHS)
MULTI_DAY_PATTERN = re.compile(
    rf"\b(?P<d1>\d{{1,2}})\s*/\s*(?P<d2>\d{{1,2}})\s+și\s+"
    rf"(?P<d3>\d{{1,2}})\s+(?P<month>{MONTH_PATTERN})\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
ROMANIAN_DATE_PATTERN = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{MONTH_PATTERN})\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
NUMERIC_DATE_PATTERN = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})[.]\s*(?P<month>\d{1,2})[.]\s*(?P<year>\d{4})(?!\d)"
)
ACADEMIC_YEAR_PATTERN = re.compile(r"(?<!\d)(?P<start>20\d{2})\s*[–-]\s*(?P<end>20\d{2})(?!\d)")
COMPACT_RANGE_PATTERN = re.compile(
    r"^(?P<start>\d{1,2})-(?P<end>\d{1,2})[.](?P<month>\d{1,2})(?:[.](?P<year>\d{4}))?$"
)
COMPACT_SINGLE_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})[.](?P<month>\d{1,2})(?:[.](?P<year>\d{4}))?$"
)
CROSS_MONTH_RANGE_PATTERN = re.compile(
    r"^(?P<start_day>\d{1,2})[.](?P<start_month>\d{1,2})-"
    r"(?P<end_day>\d{1,2})[.](?P<end_month>\d{1,2})(?:[.](?P<year>\d{4}))?$"
)


def date_fact(passage_id: str, source_text: str, value: str, qualifier: str) -> dict[str, Any]:
    return {
        "factId": stable_id("fact", passage_id, "date", value, source_text),
        "type": "date",
        "value": value,
        "qualifier": qualifier,
        "sourceText": source_text,
        "passageId": passage_id,
    }


def extract_date_facts(
    passage: dict[str, Any], warnings: list[str] | None = None
) -> list[dict[str, Any]]:
    text = passage["citationText"]
    passage_id = passage["passageId"]
    facts: list[dict[str, Any]] = []
    covered_spans: list[tuple[int, int]] = []

    for match in MULTI_DAY_PATTERN.finditer(text):
        month = ROMANIAN_MONTHS[match.group("month").lower()]
        year = int(match.group("year"))
        for group in ("d1", "d2", "d3"):
            try:
                parsed = date(year, month, int(match.group(group))).isoformat()
            except ValueError:
                if warnings is not None:
                    warnings.append("INVALID_DATE_IGNORED")
                continue
            facts.append(date_fact(passage_id, match.group(0), parsed, "explicit"))
        covered_spans.append(match.span())

    def covered(span: tuple[int, int]) -> bool:
        return any(span[0] >= start and span[1] <= end for start, end in covered_spans)

    for match in ROMANIAN_DATE_PATTERN.finditer(text):
        if covered(match.span()):
            continue
        try:
            parsed = date(
                int(match.group("year")),
                ROMANIAN_MONTHS[match.group("month").lower()],
                int(match.group("day")),
            ).isoformat()
        except ValueError:
            if warnings is not None:
                warnings.append("INVALID_DATE_IGNORED")
            continue
        facts.append(date_fact(passage_id, match.group(0), parsed, "explicit"))

    for match in NUMERIC_DATE_PATTERN.finditer(text):
        try:
            parsed = date(
                int(match.group("year")), int(match.group("month")), int(match.group("day"))
            ).isoformat()
        except ValueError:
            if warnings is not None:
                warnings.append("INVALID_DATE_IGNORED")
            continue
        facts.append(date_fact(passage_id, match.group(0), parsed, "explicit"))

    for match in ACADEMIC_YEAR_PATTERN.finditer(text):
        facts.append({
            "factId": stable_id("fact", passage_id, "academic_year", match.group(0)),
            "type": "academic_year",
            "value": {"startYear": int(match.group("start")), "endYear": int(match.group("end"))},
            "qualifier": "explicit",
            "sourceText": match.group(0),
            "passageId": passage_id,
        })
    return facts


def normalize_event_period(passage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    attributes = passage.get("attributes")
    if not isinstance(attributes, dict) or not attributes.get("periodRaw"):
        return [], []
    period = attributes["periodRaw"]
    years = {int(value) for value in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", period)}
    if not years:
        return [], ["EVENT_YEAR_MISSING"]
    if len(years) != 1:
        return [], ["EVENT_YEAR_AMBIGUOUS"]
    inherited_year = next(iter(years))
    facts: list[dict[str, Any]] = []
    for fragment in (re.sub(r"\s*-\s*", "-", part.strip()) for part in period.split("/")):
        range_match = COMPACT_RANGE_PATTERN.fullmatch(fragment)
        single_match = COMPACT_SINGLE_PATTERN.fullmatch(fragment)
        cross_month_match = CROSS_MONTH_RANGE_PATTERN.fullmatch(fragment)
        try:
            if cross_month_match:
                year = int(cross_month_match.group("year") or inherited_year)
                start = date(
                    year,
                    int(cross_month_match.group("start_month")),
                    int(cross_month_match.group("start_day")),
                ).isoformat()
                end = date(
                    year,
                    int(cross_month_match.group("end_month")),
                    int(cross_month_match.group("end_day")),
                ).isoformat()
                qualifier = "explicit_in_fragment" if cross_month_match.group("year") else "inherited_from_period"
            elif range_match:
                year = int(range_match.group("year") or inherited_year)
                month = int(range_match.group("month"))
                start = date(year, month, int(range_match.group("start"))).isoformat()
                end = date(year, month, int(range_match.group("end"))).isoformat()
                qualifier = "explicit_in_fragment" if range_match.group("year") else "inherited_from_period"
            elif single_match:
                year = int(single_match.group("year") or inherited_year)
                month = int(single_match.group("month"))
                start = end = date(year, month, int(single_match.group("day"))).isoformat()
                qualifier = "explicit_in_fragment" if single_match.group("year") else "inherited_from_period"
            else:
                return facts, ["EVENT_DATE_FORMAT_UNSUPPORTED"]
        except ValueError:
            return facts, ["EVENT_DATE_INVALID"]
        facts.append({
            "factId": stable_id("fact", passage["passageId"], "event_interval", fragment),
            "type": "event_interval",
            "value": {"startDate": start, "endDate": end},
            "qualifier": qualifier,
            "sourceText": fragment,
            "passageId": passage["passageId"],
        })
    return facts, []


def extract_numeric_facts(passage: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for line in passage["citationText"].splitlines():
        match = re.match(r"\s*[-•*]?\s*(?P<value>\d+)\s+(?P<label>[^;]+)", line)
        if not match:
            continue
        value = int(match.group("value"))
        label = match.group("label").strip().rstrip(".;")
        facts.append({
            "factId": stable_id("fact", passage["passageId"], "count", str(value), label),
            "type": "count",
            "value": value,
            "unit": label,
            "qualifier": "explicit",
            "sourceText": line.strip(),
            "passageId": passage["passageId"],
        })
    if passage.get("type") != "list":
        for match in re.finditer(
            r"\b(?P<value>\d+)\s+(?P<unit>zile|echipe(?:\s+de\s+verificare)?|instituții(?:\s+de\s+învățământ(?:\s+general)?)?)\b",
            passage["citationText"],
            re.IGNORECASE,
        ):
            facts.append({
                "factId": stable_id("fact", passage["passageId"], "count", match.group(0)),
                "type": "count",
                "value": int(match.group("value")),
                "unit": match.group("unit"),
                "qualifier": "explicit",
                "sourceText": match.group(0),
                "passageId": passage["passageId"],
            })
    for match in re.finditer(
        r"\bpeste\s+(?P<value>\d+)\s+mii(?:\s+de)?\s*(?P<unit>[^,.;\n]+)?",
        passage["citationText"],
        re.IGNORECASE,
    ):
        facts.append({
            "factId": stable_id("fact", passage["passageId"], "lower_bound", match.group(0)),
            "type": "count",
            "value": int(match.group("value")) * 1000,
            "unit": (match.group("unit") or "").strip() or None,
            "qualifier": "lower_bound",
            "sourceText": match.group(0),
            "passageId": passage["passageId"],
        })
    return facts


def enrich_document(input_path: Path) -> dict[str, Any]:
    document = read_json(input_path)
    passages = document.get("passages")
    if not isinstance(passages, list):
        raise ValueError("Structured document must contain passages.")
    all_facts: list[dict[str, Any]] = []
    document_warnings: list[str] = []
    for passage in passages:
        if not isinstance(passage, dict):
            raise ValueError("Every passage must be an object.")
        facts = extract_numeric_facts(passage)
        date_warnings: list[str] = []
        if passage.get("type") != "municipal_event":
            facts = extract_date_facts(passage, date_warnings) + facts
        event_facts, event_warnings = normalize_event_period(passage)
        facts.extend(event_facts)
        passage["facts"] = facts
        passage["warnings"] = unique_preserving_order(date_warnings + event_warnings)
        all_facts.extend(facts)
        document_warnings.extend(date_warnings + event_warnings)
    document["schemaVersion"] = "2.1"
    document["pipelineStage"] = "enriched"
    document["facts"] = all_facts
    document["warnings"] = unique_preserving_order(document_warnings)
    document["temporalContext"] = {
        "publishedDate": document.get("publishedDate"),
        "statisticsAsOf": document.get("publishedDate"),
    }
    return document


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract dates and numeric facts with citations.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        document = enrich_document(arguments.input)
        target, digest, created = write_versioned_json(
            arguments.output_dir.expanduser().resolve(),
            document["documentId"],
            "enriched",
            document,
        )
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "documentId": document["documentId"],
        "output": str(target),
        "passageCount": len(document["passages"]),
        "factCount": len(document["facts"]),
        "warningCount": len(document["warnings"]),
        "sha256": digest,
        "created": created,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
