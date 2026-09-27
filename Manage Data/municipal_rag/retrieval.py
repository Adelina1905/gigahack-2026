from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from .api import chat_json, embed, request_json
from .config import RagConfig
from .sparse import bm25_sparse

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
FACT_QUERIES = {
    "amount": "lucrări accese curți blocuri sumă buget contract valoare lei milioane alocare",
    "duration": "lucrări accese curți blocuri durată perioadă executare luni zile termen",
    "count": "lucrări accese curți blocuri număr câte accese proiecte străzi obiecte",
    "status": "lucrări accese curți blocuri stadiu statut planificat licitație achiziție desfășurare finalizat",
    "date": "dată an lună termen calendaristic",
}


def requested_fact_slots(question: str, constraints: dict[str, Any] | None = None) -> list[str]:
    text = " ".join([question, *(str(value) for value in (constraints or {}).get("factTypes") or [])]).casefold()
    slots: list[str] = []
    patterns = {
        "amount": r"\b(?:sum[aă]\w*|buget\w*|contract\w*|valoar\w*|lei|mdl|milioane?|alocat\w*)\b",
        "duration": r"\b(?:durat\w*|perioad\w*|termen\w*|luni|zile|execut\w*)\b",
        "count": r"\b(?:num[aă]r\w*|c[aâ]te\s+(?:accese|proiecte|str[aă]zi|obiecte)|accese\w*|proiecte\w*)\b",
        "status": r"\b(?:stadi\w*|statut\w*|etap\w*|planificat\w*|licita\w*|achizi\w*|desf[aă][șs]ur\w*|finalizat\w*)\b",
        "date": r"\b(?:data|dat[aă]|c[aâ]nd|anul|luna|calendar)\b",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text, re.I):
            slots.append(name)
    return slots


def atomic_queries(interpreted: dict[str, Any]) -> list[dict[str, str]]:
    constraints = interpreted.get("constraints") or {}
    locations = [str(value).strip() for value in constraints.get("locations") or [] if str(value).strip()]
    facts = requested_fact_slots(str(interpreted.get("normalizedRomanianQuery") or ""), constraints)
    if len(locations) * len(facts) < 2:
        return []
    location_keys = {value.casefold() for value in locations}
    entities = [str(value).strip() for value in constraints.get("entities") or []
                if str(value).strip() and str(value).strip().casefold() not in location_keys
                and not requested_fact_slots(str(value), {})]
    subject = " ".join(entities[:3])
    return [{"scope": location, "factType": fact,
             "query": " ".join(value for value in (subject, location, FACT_QUERIES[fact]) if value)}
            for location in locations for fact in facts][:16]


def interpret_query(question: str, config: RagConfig, api_key: str) -> dict[str, Any]:
    language = "ru" if CYRILLIC.search(question) else "ro"
    parsed = chat_json(config.generator_model,
        "Interpret this Romanian or Russian municipal question. For Russian, translate it faithfully to Romanian; for Romanian, normalize without adding facts. Extract entities, locations, dates, factTypes, multipleProjects and historicalIntent. Return JSON including normalizedRomanianQuery.",
        question, api_key)
    normalized = str(parsed.get("normalizedRomanianQuery") or (question if language == "ro" else "")).strip()
    if not normalized:
        raise RuntimeError("Query interpreter returned no Romanian retrieval query")
    historical = bool(re.search(r"\b(?:19|20)\d{2}\b|\b(?:istoric|istorică|versiunea din|la data de|în anul|историческ\w*|по состоянию)\b", question, re.I))
    locations = parsed.get("locations", [])
    unique_locations = {_location.casefold().strip() for _location in map(str, locations) if _location.strip()}
    multiple_projects = len(unique_locations) > 1 or bool(re.search(
        r"\b(?:compară|comparați|proiectele|documentele|mai multe proiecte|сравн(?:и|ите)|проекты|документы)\b",
        question, re.I,
    ))
    return {"language": language, "normalizedRomanianQuery": normalized, "constraints": {
        "entities": parsed.get("entities", []), "locations": locations,
        "dates": parsed.get("dates", []), "factTypes": parsed.get("factTypes", []),
        "multipleProjects": multiple_projects,
        "historicalIntent": historical,
    }}


def rrf(dense: list[Any], sparse: list[Any], k: int = 60) -> list[dict[str, Any]]:
    return rrf_channels([("dense", dense), ("sparse", sparse)], k)


def rrf_channels(channels: list[tuple[str, list[Any]]], k: int = 60) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for channel, points in channels:
        for rank, point in enumerate(points, start=1):
            item = combined.setdefault(str(point.id), {"point": point, "score": 0.0, "ranks": {}})
            item["score"] += 1.0 / (k + rank)
            item["ranks"][channel] = rank
    return sorted(combined.values(), key=lambda item: (-item["score"], str(item["point"].id)))


def group_documents(items: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    selected = []
    for item in items:
        document_id = str((item["point"].payload or {}).get("documentId", ""))
        if counts[document_id] >= maximum:
            continue
        counts[document_id] += 1
        selected.append(item)
    return selected


def prioritize_atomic(items: list[dict[str, Any]], atomic_count: int, limit: int,
                      maximum_per_document: int | None = None) -> list[dict[str, Any]]:
    """Reserve one slot per atomic channel, then fill by the existing global order."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    document_counts: defaultdict[str, int] = defaultdict(int)

    def add(item: dict[str, Any]) -> bool:
        point_id = str(item["point"].id)
        document_id = str((item["point"].payload or {}).get("documentId", ""))
        if point_id in seen or len(selected) >= limit:
            return False
        if maximum_per_document is not None and document_counts[document_id] >= maximum_per_document:
            return False
        seen.add(point_id)
        document_counts[document_id] += 1
        selected.append(item)
        return True

    for index in range(atomic_count):
        channel = f"atomic:{index}"
        candidates = sorted((item for item in items if channel in item.get("ranks", {})),
                            key=lambda item: (item["ranks"][channel], -float(item.get("score", 0))))
        for candidate in candidates:
            if add(candidate):
                break
    for item in items:
        add(item)
    return selected


def rerank(query: str, candidates: list[dict[str, Any]], config: RagConfig, api_key: str) -> list[dict[str, Any]]:
    documents = [str((item["point"].payload or {}).get("retrievalText") or (item["point"].payload or {}).get("text") or "") for item in candidates]
    if not documents:
        return []
    response = request_json("rerank", {"model": config.reranker_model, "query": query, "documents": documents,
        "top_n": len(documents), "instruction": "Prefer direct body evidence matching the same municipal project, place and period. A headline alone is insufficient."}, api_key)
    results = response.get("results") or response.get("data")
    if not isinstance(results, list):
        raise RuntimeError("Managed reranker returned no ranked results")
    ranked = []
    for rank, result in enumerate(results, start=1):
        index = result.get("index") if isinstance(result, dict) else None
        if isinstance(index, int) and 0 <= index < len(candidates):
            item = dict(candidates[index])
            item["rerankScore"] = float(result.get("relevance_score", result.get("score", 0)))
            item["rerankRank"] = rank
            ranked.append(item)
    if not ranked:
        raise RuntimeError("Managed reranker returned invalid indexes")
    return ranked


def client_for(path: Path | None, url: str | None) -> QdrantClient:
    url = url or os.environ.get("QDRANT_URL", "").strip() or (
        "http://127.0.0.1:6333" if path is None else None
    )
    if url:
        return QdrantClient(
            url=url,
            api_key=os.environ.get("QDRANT_API_KEY") or None,
            timeout=30,
            prefer_grpc=True,
        )
    return QdrantClient(path=str((path or Path(__file__).resolve().parents[1] / "data" / "08_qdrant").resolve()))


def locator_order(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
    locator = item.get("sourceLocator") or {}
    return (
        int(locator.get("pageIndex", locator.get("page", 0)) or 0),
        int(locator.get("startLine", locator.get("blockIndex", 0)) or 0),
        int(locator.get("charStart", 0) or 0),
        int(locator.get("charEnd", 0) or 0),
        str(item.get("evidenceId") or item.get("chunkId") or ""),
    )


def neighboring_payloads(selected: list[dict[str, Any]], document_payloads: dict[str, list[dict[str, Any]]],
                         maximum: int) -> list[dict[str, Any]]:
    """Add immediate source neighbors without displacing reranked evidence."""
    result = list(selected)
    seen = {str(item.get("evidenceId") or item.get("chunkId") or "") for item in result}
    for selected_item in selected:
        if len(result) >= maximum:
            break
        document_id = str(selected_item.get("documentId") or "")
        ordered = sorted(document_payloads.get(document_id, []), key=locator_order)
        selected_id = str(selected_item.get("evidenceId") or selected_item.get("chunkId") or "")
        position = next((index for index, item in enumerate(ordered)
                         if str(item.get("evidenceId") or item.get("chunkId") or "") == selected_id), None)
        if position is None:
            continue
        for neighbor_index in (position - 1, position + 1):
            if not 0 <= neighbor_index < len(ordered) or len(result) >= maximum:
                continue
            neighbor = ordered[neighbor_index]
            key = str(neighbor.get("evidenceId") or neighbor.get("chunkId") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append({**neighbor, "retrieval": {"neighborOf": selected_id}})
    return result


def expand_neighbors(selected: list[dict[str, Any]], config: RagConfig, path: Path | None,
                     url: str | None, maximum: int) -> list[dict[str, Any]]:
    document_ids = list(dict.fromkeys(str(item.get("documentId") or "") for item in selected if item.get("documentId")))[:3]
    if not document_ids or len(selected) >= maximum:
        return selected
    client = client_for(path, url)
    payloads: dict[str, list[dict[str, Any]]] = {}
    try:
        for document_id in document_ids:
            records: list[dict[str, Any]] = []
            offset = None
            while len(records) < 500:
                batch, offset = client.scroll(
                    config.evidence_alias,
                    scroll_filter=models.Filter(must=[models.FieldCondition(
                        key="documentId", match=models.MatchValue(value=document_id)
                    )]),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                records.extend(dict(point.payload or {}) for point in batch)
                if offset is None:
                    break
            payloads[document_id] = records
    finally:
        client.close()
    return neighboring_payloads(selected, payloads, maximum)


def retrieve(question: str, interpreted: dict[str, Any], config: RagConfig, api_key: str, path: Path | None = None, url: str | None = None, explain: bool = False) -> dict[str, Any]:
    dense_query = embed(question, config.embedding_model, api_key)
    indices, values = bm25_sparse(interpreted["normalizedRomanianQuery"])
    limits = config.raw["retrieval"]
    client = client_for(path, url)
    decomposed = atomic_queries(interpreted)
    try:
        dense = client.query_points(config.evidence_alias, query=dense_query, using="dense", limit=int(limits["denseCandidates"]), with_payload=True).points
        sparse = client.query_points(config.evidence_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=int(limits["sparseCandidates"]), with_payload=True).points
        atomic_sparse: list[tuple[str, list[Any]]] = []
        for index, item in enumerate(decomposed):
            atomic_indices, atomic_values = bm25_sparse(item["query"])
            points = client.query_points(
                config.evidence_alias,
                query=models.SparseVector(indices=atomic_indices, values=atomic_values),
                using="sparse",
                limit=min(12, int(limits["sparseCandidates"])),
                with_payload=True,
            ).points
            atomic_sparse.append((f"atomic:{index}", points))
        catalog = client.query_points(config.catalog_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=10, with_payload=True).points
    finally:
        client.close()
    fused = rrf_channels([("dense", dense), ("sparse", sparse), *atomic_sparse], int(limits["rrfK"]))
    catalog_ranks = {str((point.payload or {}).get("documentId")): rank for rank, point in enumerate(catalog, 1)}
    for item in fused:
        document_id = str((item["point"].payload or {}).get("documentId"))
        if document_id in catalog_ranks:
            item["score"] += 1.0 / (int(limits["rrfK"]) + catalog_ranks[document_id])
            item["ranks"]["catalog"] = catalog_ranks[document_id]
    fused.sort(key=lambda item: (-item["score"], str(item["point"].id)))
    grouped = prioritize_atomic(
        fused, len(decomposed), int(limits["rerankCandidates"]), int(limits["maxPerDocument"])
    )
    ranked = rerank(interpreted["normalizedRomanianQuery"], grouped, config, api_key)
    minimum = float(config.raw["thresholds"]["minimumRerankScore"])
    output = []
    eligible = [value for value in ranked if value["rerankScore"] >= minimum]
    final_items = prioritize_atomic(eligible, len(decomposed), int(limits["finalEvidence"]))
    for item in final_items:
        atomic_matches = [decomposed[int(key.split(":", 1)[1])] for key in item["ranks"]
                          if key.startswith("atomic:")]
        output.append({**(item["point"].payload or {}), "retrieval": {"fusedScore": item["score"], "denseRank": item["ranks"].get("dense"), "sparseRank": item["ranks"].get("sparse"), "atomicMatches": atomic_matches, "rerankedPosition": item["rerankRank"], "rerankScore": item["rerankScore"]}})
    output = expand_neighbors(output, config, path, url, int(limits["finalEvidence"]) + 6)
    return {"evidence": output, "atomicQueries": decomposed,
            "diagnostics": ({"dense": len(dense), "sparse": len(sparse), "atomicQueries": len(decomposed),
                             "atomicCandidates": sum(len(points) for _, points in atomic_sparse),
                             "catalog": len(catalog), "fused": len(fused), "grouped": len(grouped)} if explain else None)}
