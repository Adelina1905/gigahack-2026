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


def interpret_query(question: str, config: RagConfig, api_key: str) -> dict[str, Any]:
    language = "ru" if CYRILLIC.search(question) else "ro"
    parsed = chat_json(config.generator_model,
        "Interpret this Romanian or Russian municipal question. For Russian, translate it faithfully to Romanian; for Romanian, normalize without adding facts. Extract entities, locations, dates, factTypes, multipleProjects and historicalIntent. Return JSON including normalizedRomanianQuery.",
        question, api_key)
    normalized = str(parsed.get("normalizedRomanianQuery") or (question if language == "ro" else "")).strip()
    if not normalized:
        raise RuntimeError("Query interpreter returned no Romanian retrieval query")
    historical = bool(re.search(r"\b(?:19|20)\d{2}\b|\b(?:istoric|istorică|versiunea din|la data de|în anul|историческ\w*|по состоянию)\b", question, re.I))
    multiple_projects = bool(re.search(r"\b(?:compară|comparați|proiectele|documentele|mai multe proiecte|сравн(?:и|ите)|проекты|документы)\b", question, re.I))
    return {"language": language, "normalizedRomanianQuery": normalized, "constraints": {
        "entities": parsed.get("entities", []), "locations": parsed.get("locations", []),
        "dates": parsed.get("dates", []), "factTypes": parsed.get("factTypes", []),
        "multipleProjects": multiple_projects,
        "historicalIntent": historical,
    }}


def rrf(dense: list[Any], sparse: list[Any], k: int = 60) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for channel, points in (("dense", dense), ("sparse", sparse)):
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
    if url:
        return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=30)
    return QdrantClient(path=str((path or Path(__file__).resolve().parents[1] / "data" / "08_qdrant").resolve()))


def retrieve(question: str, interpreted: dict[str, Any], config: RagConfig, api_key: str, path: Path | None = None, url: str | None = None, explain: bool = False) -> dict[str, Any]:
    dense_query = embed(question, config.embedding_model, api_key)
    indices, values = bm25_sparse(interpreted["normalizedRomanianQuery"])
    limits = config.raw["retrieval"]
    client = client_for(path, url)
    try:
        dense = client.query_points(config.evidence_alias, query=dense_query, using="dense", limit=int(limits["denseCandidates"]), with_payload=True).points
        sparse = client.query_points(config.evidence_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=int(limits["sparseCandidates"]), with_payload=True).points
        catalog = client.query_points(config.catalog_alias, query=models.SparseVector(indices=indices, values=values), using="sparse", limit=10, with_payload=True).points
    finally:
        client.close()
    fused = rrf(dense, sparse, int(limits["rrfK"]))
    catalog_ranks = {str((point.payload or {}).get("documentId")): rank for rank, point in enumerate(catalog, 1)}
    for item in fused:
        document_id = str((item["point"].payload or {}).get("documentId"))
        if document_id in catalog_ranks:
            item["score"] += 1.0 / (int(limits["rrfK"]) + catalog_ranks[document_id])
            item["ranks"]["catalog"] = catalog_ranks[document_id]
    fused.sort(key=lambda item: (-item["score"], str(item["point"].id)))
    grouped = group_documents(fused, int(limits["maxPerDocument"]))[:int(limits["rerankCandidates"])]
    ranked = rerank(interpreted["normalizedRomanianQuery"], grouped, config, api_key)
    minimum = float(config.raw["thresholds"]["minimumRerankScore"])
    output = []
    for item in [value for value in ranked if value["rerankScore"] >= minimum][:int(limits["finalEvidence"])]:
        output.append({**(item["point"].payload or {}), "retrieval": {"fusedScore": item["score"], "denseRank": item["ranks"].get("dense"), "sparseRank": item["ranks"].get("sparse"), "rerankedPosition": item["rerankRank"], "rerankScore": item["rerankScore"]}})
    return {"evidence": output, "diagnostics": ({"dense": len(dense), "sparse": len(sparse), "catalog": len(catalog), "fused": len(fused), "grouped": len(grouped)} if explain else None)}
