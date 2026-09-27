from __future__ import annotations

import sys
import unittest
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from municipal_rag.answering import ambiguity


def item(document_id: str, score: float) -> dict[str, object]:
    return {"documentId": document_id, "metadata": {"title": f"Doc {document_id}"}, "retrieval": {"rerankScore": score}}


SINGLE_PROJECT = {"constraints": {"multipleProjects": False}}


class AmbiguityTests(unittest.TestCase):
    def test_strong_tied_documents_ask_which_one_is_meant(self) -> None:
        choices = ambiguity([item("a", .87), item("a", .86), item("b", .84), item("c", .83), item("d", .82)], SINGLE_PROJECT, .88, .6)
        self.assertEqual(choices, [{"documentId": "a", "label": "Doc a"}, {"documentId": "b", "label": "Doc b"},
                                   {"documentId": "c", "label": "Doc c"}])

    def test_weak_ties_are_left_to_generation(self) -> None:
        self.assertEqual(ambiguity([item("a", .41), item("b", .40)], SINGLE_PROJECT, .88, .6), [])

    def test_clear_winner_is_not_ambiguous(self) -> None:
        self.assertEqual(ambiguity([item("a", .82), item("b", .64)], SINGLE_PROJECT, .88, .6), [])

    def test_multiple_project_questions_are_not_ambiguous(self) -> None:
        self.assertEqual(ambiguity([item("a", .9), item("b", .9)], {"constraints": {"multipleProjects": True}}, .88, .6), [])


if __name__ == "__main__":
    unittest.main()
