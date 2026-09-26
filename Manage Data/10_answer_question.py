"""Compatibility CLI for municipal RAG v3."""

import re
from typing import Any

from municipal_rag.answering import main


def build_evidence(search_response: dict[str, Any], min_score: float, *_: Any, **__: Any) -> list[dict[str, Any]]:
    """Legacy adapter retained for integrations while v3 uses expose_evidence."""
    selected, seen = [], set()
    for result in search_response.get("results", []):
        if float(result.get("score", 0)) < min_score:
            continue
        for citation in result.get("citations") or []:
            passage_id, quote = citation.get("passageId"), citation.get("quote")
            if not passage_id or passage_id in seen or not isinstance(quote, str) or not quote.strip():
                continue
            seen.add(passage_id)
            selected.append({"id": f"S{len(selected)+1}", "passageId": passage_id, "quote": quote,
                "documentId": result.get("documentId"), "title": result.get("title"),
                "sourceUrl": citation.get("sourceUrl"), "locator": citation.get("locator") or {},
                "indexingStatus": result.get("indexingStatus")})
    return selected


def split_answer_segments(text: str) -> list[str]:
    protected = re.sub(r"\b(str|bd|dl|dna|nr|mun|sec)\.", lambda match: match.group(0)[:-1] + "<DOT>", text, flags=re.I)
    protected = re.sub(r"\b([A-ZĂÂÎȘȚ][a-zăâîșț]{0,2})\.", lambda match: match.group(1) + "<DOT>", protected)
    return [item.replace("<DOT>", ".") for item in re.split(r"(?<=[.!?])\s+|\n+", protected) if item.strip()]


def validate_answer(answer: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    status = answer.get("informationStatus")
    identifiers = answer.get("evidenceIds")
    if status not in {"SUPPORTED", "PARTIAL", "NOT_FOUND", "CONTRADICTION"} or not isinstance(identifiers, list):
        raise RuntimeError("Invalid answer contract")
    valid = {item["id"] for item in evidence}
    inline = set(re.findall(r"\[(S\d+)\]", str(answer.get("answer", ""))))
    if set(identifiers) - valid or inline - valid:
        raise RuntimeError("Answer cited unknown evidence IDs")
    if inline != set(identifiers):
        raise RuntimeError("Inline citations and evidenceIds do not match")
    if status in {"PARTIAL", "NOT_FOUND"} and not answer.get("limitations"):
        raise RuntimeError(f"A {status} answer must explain missing information")
    indexed = {item["id"]: item for item in evidence}
    for segment in split_answer_segments(str(answer.get("answer", ""))):
        words = re.findall(r"[^\W\d_]+", re.sub(r"\[S\d+\]", "", segment), re.UNICODE)
        if len(words) < 4:
            continue
        cited = re.findall(r"\[(S\d+)\]", segment)
        if not cited:
            raise RuntimeError("Factual sentence has no immediate citation")
        documents = [indexed[item].get("documentId") for item in dict.fromkeys(cited)]
        if len(documents) != len(set(documents)):
            raise RuntimeError("A sentence cites the same document more than once")
        claimed = set(re.findall(r"\d+(?:[.,]\d+)?", re.sub(r"\[S\d+\]", "", segment)))
        if claimed:
            if len(set(documents)) > 1:
                raise RuntimeError("A numeric sentence cites multiple documents")
            available = {number for item in cited for number in re.findall(r"\d+(?:[.,]\d+)?", str(indexed[item].get("quote", "")))}
            if claimed - available:
                raise RuntimeError("A numeric claim is absent from cited evidence")


if __name__ == "__main__":
    raise SystemExit(main())
