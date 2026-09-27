from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from municipal_rag.retrieval import add_following_context, eligible_with_context


def point(identifier: str, line: int, quote: str) -> SimpleNamespace:
    return SimpleNamespace(id=identifier, payload={
        "evidenceId": identifier,
        "documentId": "school-enrolment",
        "versionId": "2026",
        "citationText": quote,
        "evidenceKind": "body",
        "sourceLocator": {"startLine": line},
    })


class RetrievalContextTests(unittest.TestCase):
    def test_numbered_items_following_a_heading_reach_reranking(self):
        heading = point("heading", 7, "Pașii pentru înregistrare pe platformă:")
        step_one = point("step-1", 9, "Pasul 1: Autentificați-vă pe platformă")
        step_two = point("step-2", 11, "Pasul 2: Selectați instituția")
        unrelated = point("later", 19, "Procesul se desfășoară în două etape")
        candidates = [{"point": heading, "score": 0.8, "ranks": {"dense": 1}}]

        expanded = add_following_context(
            candidates,
            {("school-enrolment", "2026"): [unrelated, step_two, heading, step_one]},
            maximum_per_anchor=2,
        )

        self.assertEqual([item["point"].id for item in expanded], ["heading", "step-1", "step-2"])
        self.assertEqual(expanded[1]["ranks"], {"contextAfter": 1})
        self.assertEqual(expanded[1]["contextAnchorId"], "heading")

    def test_plain_body_passage_does_not_expand(self):
        body = point("body", 1, "Părinții consultă instrucțiunile online.")
        next_passage = point("next", 3, "Altă informație")
        candidates = [{"point": body, "score": 0.8, "ranks": {"dense": 1}}]

        expanded = add_following_context(
            candidates,
            {("school-enrolment", "2026"): [body, next_passage]},
        )

        self.assertEqual([item["point"].id for item in expanded], ["body"])

    def test_context_survives_when_its_heading_passes_the_threshold(self):
        heading = {"point": point("heading", 7, "Pașii:"), "rerankScore": 0.8}
        step = {"point": point("step", 9, "Pasul 1"), "rerankScore": 0.1, "contextAnchorId": "heading"}
        unrelated = {"point": point("unrelated", 20, "Altceva"), "rerankScore": 0.1}

        eligible = eligible_with_context([heading, step, unrelated], 0.22)

        self.assertEqual([item["point"].id for item in eligible], ["heading", "step"])


if __name__ == "__main__":
    unittest.main()
