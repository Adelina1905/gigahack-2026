"""Create a 60 RO / 40 RU candidate set; every label still requires human approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def latest_documents(directory: Path) -> list[dict]:
    latest = {}
    for path in directory.glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        document_id = value.get("documentId")
        if document_id and (document_id not in latest or path.stat().st_mtime_ns > latest[document_id][0]):
            latest[document_id] = (path.stat().st_mtime_ns, value)
    return [latest[key][1] for key in sorted(latest)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "05_validated")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "questions.v1.jsonl")
    args = parser.parse_args()
    documents = latest_documents(args.input)
    if len(documents) < 60:
        raise SystemExit("At least 60 validated documents are required")
    cases = []
    case_types = ("direct_fact", "date", "amount", "location", "list", "comparison", "ambiguous", "title_only", "historical", "unanswerable")
    for index in range(100):
        language = "ro" if index < 60 else "ru"
        document = documents[index % len(documents)]
        title = document.get("title", "")
        case_type = case_types[index % len(case_types)]
        if case_type == "ambiguous":
            question = "Care este bugetul proiectului?" if language == "ro" else "Каков бюджет проекта?"
        elif case_type == "historical":
            question = (f"Ce informații erau raportate în 2022 despre «{title}»?" if language == "ro" else f"Какие сведения сообщались в 2022 году о «{title}»?")
        elif case_type == "unanswerable":
            question = "Care a fost temperatura exactă la inaugurare?" if language == "ro" else "Какой была точная температура на открытии?"
        elif case_type == "comparison":
            second = documents[(index + 1) % len(documents)].get("title", "")
            question = (f"Compară faptele din «{title}» și «{second}»." if language == "ro" else f"Сравните факты из «{title}» и «{second}».")
        else:
            question = (f"Ce informații verificabile oferă documentul «{title}»?" if language == "ro" else f"Какие проверяемые сведения содержит документ «{title}»?")
        split = "tuning" if index < 60 else "validation" if index < 80 else "test"
        cases.append({"id": f"{language}-{index+1:03d}", "language": language, "question": question,
            "split": split, "caseType": case_type, "answerability": "UNANSWERABLE" if case_type == "unanswerable" else "ANSWERABLE",
            "relevantDocumentIds": [] if case_type == "unanswerable" else [document["documentId"]], "relevantEvidenceIds": [],
            "expectedFacts": [], "clarificationExpected": case_type == "ambiguous", "forbiddenScopeCombinations": [],
            "reviewStatus": "PENDING"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in cases) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "cases": 100, "romanian": 60, "russian": 40, "reviewStatus": "PENDING"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
