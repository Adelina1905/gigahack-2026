from __future__ import annotations

import contextlib
import io
import json
import random
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from pathlib import Path

from eval_rag import (
    main,
    progress_snapshot,
    write_progress,
    FAIL,
    NA,
    PASS,
    aggregate,
    duplicate_choices,
    exit_code,
    format_summary,
    load_cases,
    main,
    normalize_label,
    percentile,
    score_case,
    uncited_sentences,
)

ORDER_2026 = "municipal-6391b1ed92a78864ebb8fef5"
RASCANI_2023 = "municipal-4eee98680b335f45c0132aef"
PARENTING_GUIDE = "municipal-abf68e1ce64001574044697c"


def citation(doc_id: str, index: int = 1, title: str = "Titlu") -> dict:
    return {"id": f"S{index}", "documentId": doc_id, "title": title, "url": "https://example.md/doc", "exactQuote": "q"}


def reply(status: str, answer: str = "", citations: list | None = None, choices: list | None = None, **extra) -> dict:
    return {"mode": "rag", "status": status, "answer": answer, "citations": citations or [],
            "clarificationChoices": choices, **extra}


ANSWERABLE = {
    "id": "ans", "kind": "answerable", "question": "q", "language": "ro",
    "expect": {"status": ["SUPPORTED", "PARTIAL"], "acceptableDocumentIds": ["municipal-a"],
               "acceptableTitlePatterns": ["teren de fotbal"], "answerPattern": "704"},
}
OFF_TOPIC = {
    "id": "off", "kind": "off_topic", "question": "pizza",
    "expect": {"status": ["NOT_FOUND"], "reasons": ["NO_RELEVANT_EVIDENCE", "OUT_OF_SCOPE"], "maxCitations": 0},
}
YEARLY = {
    "id": "year", "kind": "yearly_topic", "question": "clasa I 2026",
    "expect": {"status": ["SUPPORTED", "PARTIAL"], "requiredDocumentIds": [ORDER_2026],
               "acceptableDocumentIds": [ORDER_2026], "forbiddenDocumentIds": [RASCANI_2023]},
}
AMBIGUOUS = {
    "id": "amb", "kind": "ambiguous", "question": "turneu",
    "expect": {"status": ["NEEDS_CLARIFICATION"], "acceptableDocumentIds": ["municipal-x", "municipal-y", "municipal-z"],
               "duplicateGroups": [["municipal-y", "municipal-z"]]},
}
LACKS_VALUE = {
    "id": "lack", "kind": "lacks_value", "question": "program",
    "expect": {"status": ["NOT_FOUND", "SUPPORTED", "PARTIAL"], "reasons": ["EVIDENCE_LACKS_VALUE"],
               "acceptableDocumentIds": ["municipal-a"], "valuePattern": r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}"},
}


class HelperTest(unittest.TestCase):
    def test_normalize_label_folds_case_accents_and_punctuation(self):
        self.assertEqual(normalize_label("ÎNSCRIEREA la Grădinițe!"), normalize_label("inscrierea la gradinite"))

    def test_duplicate_choices_by_document_label_and_group(self):
        choices = [
            {"documentId": "d1", "label": "Înscrierea online"},
            {"documentId": "d1", "label": "Alt titlu"},           # same document
            {"documentId": "d2", "label": "inscrierea ONLINE"},   # same label
            {"documentId": "g1", "label": "Copie A"},
            {"documentId": "g2", "label": "Copie B"},             # same duplicate group
            {"documentId": "d3", "label": "Distinct"},
        ]
        self.assertEqual(duplicate_choices(choices, [["g1", "g2"]]), 3)
        self.assertEqual(duplicate_choices([], []), 0)

    def test_uncited_sentences_ignores_headings_and_short_fragments(self):
        answer = ("## Răspuns\nÎnscrierea se face online pe platforma e-școala [S1]. "
                  "Prima etapă durează până la sfârșitul lunii aprilie 2026. Da.")
        self.assertEqual(uncited_sentences(answer), (1, 2))

    def test_marker_after_sentence_punctuation_belongs_to_that_sentence(self):
        answer = "Lucrările au costat 704 000 lei din bugetul municipal. [S1]\nParticipanții au între 16 și 25 de ani. [S2]"
        self.assertEqual(uncited_sentences(answer), (0, 2))
        self.assertEqual(uncited_sentences("Lucrările au costat 704 000 lei. Au fost finalizate în 2024 [S1]."), (1, 2))

    def test_percentile_nearest_rank(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(percentile([4, 1, 3, 2], 50), 2)
        self.assertEqual(percentile(list(range(1, 21)), 95), 19)


class ScoreCaseTest(unittest.TestCase):
    def test_supported_answer_with_relevant_citations_passes(self):
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 000 lei [S1].", [citation("municipal-a")],
                                              reason=None, flags=[]), 1200.0)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["checks"]["citationRelevance"], PASS)
        self.assertEqual(result["checks"]["answerCited"], PASS)
        self.assertEqual(result["counts"]["unrelatedCitations"], 0)

    def test_citation_accepted_by_title_pattern(self):
        cited = [citation("municipal-other", title="Teren de fotbal la Liceul X")]
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 lei [S1].", cited))
        self.assertEqual(result["checks"]["citationRelevance"], PASS)

    def test_unrelated_citation_is_counted_and_fails(self):
        cited = [citation("municipal-a", 1), citation(PARENTING_GUIDE, 2, "Suport informațional")]
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 lei [S1][S2].", cited))
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"]["citationRelevance"], FAIL)
        self.assertEqual(result["counts"]["unrelatedCitations"], 1)

    def test_answer_without_citations_is_uncited(self):
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 lei."))
        self.assertTrue(result["counts"]["uncitedAnswer"])
        self.assertEqual(result["checks"]["answerCited"], FAIL)

    def test_answer_with_citations_but_no_markers_is_uncited(self):
        result = score_case(ANSWERABLE, reply("PARTIAL", "Costul este 704 lei.", [citation("municipal-a")]))
        self.assertTrue(result["counts"]["uncitedAnswer"])

    def test_dangling_marker_fails(self):
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 lei [S1][S4].", [citation("municipal-a")]))
        self.assertEqual(result["checks"]["noDanglingMarkers"], FAIL)
        self.assertFalse(result["counts"]["uncitedAnswer"])

    def test_answer_content_mismatch_fails(self):
        result = score_case(ANSWERABLE, reply("SUPPORTED", "Costul nu este precizat clar [S1].", [citation("municipal-a")]))
        self.assertEqual(result["checks"]["answerContent"], FAIL)

    def test_llm_mode_answer_is_uncited(self):
        response = {"mode": "llm", "status": "OK", "answer": "Iată o rețetă de pizza.", "citations": []}
        result = score_case(OFF_TOPIC, response)
        self.assertTrue(result["counts"]["uncitedAnswer"])
        self.assertEqual(result["checks"]["status"], FAIL)

    def test_off_topic_not_found_passes_and_checks_reason(self):
        result = score_case(OFF_TOPIC, reply("NOT_FOUND", "Nu am găsit.", reason="OUT_OF_SCOPE", flags=[]))
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["checks"]["reason"], PASS)

    def test_off_topic_wrong_reason_fails(self):
        result = score_case(OFF_TOPIC, reply("NOT_FOUND", "Nu am găsit.", reason="CLAIMS_UNVERIFIED", flags=[]))
        self.assertEqual(result["checks"]["reason"], FAIL)

    def test_older_service_without_reason_marks_reason_na(self):
        result = score_case(OFF_TOPIC, reply("NOT_FOUND", "Nu am găsit."))
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks"]["reason"], NA)
        self.assertFalse(result["counts"]["reasonReported"])
        self.assertNotIn("flags", result["response"])

    def test_any_citation_on_off_topic_is_unrelated(self):
        result = score_case(OFF_TOPIC, reply("SUPPORTED", "Pizza [S1].", [citation(PARENTING_GUIDE)]))
        self.assertEqual(result["counts"]["unrelatedCitations"], 1)
        self.assertEqual(result["checks"]["citationCount"], FAIL)

    def test_any_clarification_choice_on_off_topic_is_unrelated(self):
        choices = [{"documentId": "municipal-p", "label": "Proiect A"}, {"documentId": "municipal-q", "label": "Proiect B"}]
        result = score_case(OFF_TOPIC, reply("NEEDS_CLARIFICATION", "La care proiect vă referiți?", choices=choices))
        self.assertEqual(result["counts"]["unrelatedChoices"], 2)
        self.assertEqual(result["checks"]["choiceRelevance"], FAIL)
        self.assertEqual(result["counts"]["unrelatedCitations"], 0)

    def test_not_found_with_citations_breaks_contract(self):
        result = score_case(OFF_TOPIC, reply("NOT_FOUND", "Nu.", [citation(PARENTING_GUIDE)], reason="NO_RELEVANT_EVIDENCE"))
        self.assertEqual(result["checks"]["notFoundWithoutCitations"], FAIL)

    def test_yearly_topic_requires_current_order_and_flags_outdated_copy(self):
        good = score_case(YEARLY, reply("SUPPORTED", "Înscrierea începe în aprilie [S1].", [citation(ORDER_2026)]))
        self.assertTrue(good["passed"], good["failures"])
        stale = score_case(YEARLY, reply("SUPPORTED", "Înscrierea începe în aprilie [S1].", [citation(RASCANI_2023)]))
        self.assertEqual(stale["checks"]["requiredDocuments"], FAIL)
        self.assertEqual(stale["checks"]["noOutdatedSources"], FAIL)
        self.assertEqual(stale["counts"]["outdatedDocuments"], 1)
        self.assertEqual(stale["counts"]["unrelatedCitations"], 0)  # outdated is scored separately

    def test_outdated_choice_in_clarification_counts(self):
        choices = [{"documentId": ORDER_2026, "label": "2026"}, {"documentId": RASCANI_2023, "label": "2023"}]
        result = score_case(YEARLY, reply("NEEDS_CLARIFICATION", "Care?", choices=choices))
        self.assertEqual(result["checks"]["status"], FAIL)
        self.assertEqual(result["counts"]["outdatedDocuments"], 1)

    def test_clarification_with_relevant_distinct_choices_passes(self):
        choices = [{"documentId": "municipal-x", "label": "Turneu 2025"}, {"documentId": "municipal-y", "label": "Turneu 2026"}]
        result = score_case(AMBIGUOUS, reply("NEEDS_CLARIFICATION", "La care turneu vă referiți?", choices=choices))
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["checks"]["choiceRelevance"], PASS)
        self.assertEqual(result["checks"]["answerCited"], NA)

    def test_clarification_with_duplicate_and_unrelated_choices_fails(self):
        choices = [{"documentId": "municipal-y", "label": "Copie Buiucani"},
                   {"documentId": "municipal-z", "label": "Copie Centru"},
                   {"documentId": PARENTING_GUIDE, "label": "Ghid parental"}]
        result = score_case(AMBIGUOUS, reply("NEEDS_CLARIFICATION", "Care?", choices=choices))
        self.assertEqual(result["counts"]["duplicateChoices"], 1)
        self.assertEqual(result["counts"]["unrelatedChoices"], 1)
        self.assertEqual(result["checks"]["noDuplicateChoices"], FAIL)
        self.assertEqual(result["checks"]["choiceRelevance"], FAIL)

    def test_clarification_needs_two_distinct_choices(self):
        choices = [{"documentId": "municipal-y", "label": "A"}, {"documentId": "municipal-z", "label": "B"}]
        result = score_case(AMBIGUOUS, reply("NEEDS_CLARIFICATION", "Care?", choices=choices))
        self.assertEqual(result["checks"]["clarificationChoices"], FAIL)

    def test_lacks_value_not_found_with_reason_passes(self):
        result = score_case(LACKS_VALUE, reply("NOT_FOUND", "Nu conține programul.", reason="EVIDENCE_LACKS_VALUE"))
        self.assertTrue(result["passed"], result["failures"])

    def test_lacks_value_answer_without_value_fails_and_with_value_passes(self):
        vague = score_case(LACKS_VALUE, reply("SUPPORTED", "Direcția are mai multe secții [S1].", [citation("municipal-a")]))
        self.assertEqual(vague["checks"]["valuePresentWhenAnswered"], FAIL)
        concrete = score_case(LACKS_VALUE, reply("SUPPORTED", "Programul este 08:00 - 17:00 [S1].", [citation("municipal-a")]))
        self.assertEqual(concrete["checks"]["valuePresentWhenAnswered"], PASS)

    def test_request_error_is_a_failed_case(self):
        result = score_case(ANSWERABLE, None, 5.0, "HTTP 503: unavailable")
        self.assertFalse(result["passed"])
        self.assertIsNone(result["response"])


class AggregateTest(unittest.TestCase):
    def results(self):
        return [
            score_case(ANSWERABLE, reply("SUPPORTED", "Costul este 704 lei [S1].", [citation("municipal-a")]), 1000.0),
            score_case(dict(ANSWERABLE, id="ans2"), reply("NOT_FOUND", "Nu am găsit."), 2000.0),
            score_case(OFF_TOPIC, reply("SUPPORTED", "Pizza.", [citation(PARENTING_GUIDE)]), 3000.0),
            score_case(YEARLY, reply("SUPPORTED", "Aprilie [S1].", [citation(RASCANI_2023)]), 4000.0),
            score_case(AMBIGUOUS, reply("NEEDS_CLARIFICATION", "Care?", choices=[
                {"documentId": "municipal-x", "label": "X"}, {"documentId": PARENTING_GUIDE, "label": "Ghid"}]), 5000.0),
            score_case(LACKS_VALUE, None, None, "timeout"),
        ]

    def test_metrics(self):
        metrics = aggregate(self.results())
        self.assertEqual(metrics["cases"], 6)
        self.assertEqual(metrics["requestErrors"], 1)
        self.assertEqual(metrics["unrelatedCitations"], 1)
        self.assertEqual(metrics["scoredCitations"], 3)
        self.assertEqual(metrics["uncitedAnswers"], 1)          # the off-topic "Pizza." answer
        self.assertEqual(metrics["answerBearingReplies"], 3)
        self.assertEqual(metrics["falseNotFound"], 1)
        self.assertEqual(metrics["answerableCases"], 3)          # two answerable + one yearly
        self.assertEqual(metrics["clarificationPrecision"], 0.5)
        self.assertEqual(metrics["ambiguousClarifiedRate"], 1.0)
        self.assertEqual(metrics["outdatedSourceRate"], 1.0)
        self.assertEqual(metrics["latencyP50Ms"], 3000.0)
        self.assertEqual(metrics["latencyP95Ms"], 5000.0)
        self.assertFalse(metrics["reasonReported"])
        self.assertEqual(exit_code(metrics), 1)

    def test_clean_suite_exits_zero(self):
        metrics = aggregate([score_case(OFF_TOPIC, reply("NOT_FOUND", "Nu.", reason="OUT_OF_SCOPE", flags=[]), 10.0)])
        self.assertEqual(exit_code(metrics), 0)
        self.assertIsNone(metrics["unrelatedCitationRate"])
        self.assertTrue(metrics["reasonReported"])

    def test_summary_lists_every_case(self):
        results = self.results()
        text = format_summary({"url": "http://x", "metrics": aggregate(results), "cases": results})
        for item in results:
            self.assertIn(item["id"], text)
        self.assertIn("unrelated-citation rate", text)


class RescoreTest(unittest.TestCase):
    def test_rescore_reuses_saved_replies_without_network(self):
        saved = score_case(OFF_TOPIC, reply("SUPPORTED", "Pizza [S1].", [citation(PARENTING_GUIDE)]), 900.0)
        with tempfile.TemporaryDirectory() as folder:
            cases_path, old_path, new_path = (Path(folder) / name for name in ("cases.json", "old.json", "new.json"))
            cases_path.write_text(json.dumps({"cases": [OFF_TOPIC]}), encoding="utf-8")
            old_path.write_text(json.dumps({"url": "http://saved", "cases": [saved]}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--cases", str(cases_path), "--rescore", str(old_path), "--out", str(new_path)])
            report = json.loads(new_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(report["url"], "http://saved")
        self.assertEqual(report["metrics"]["unrelatedCitations"], 1)
        self.assertEqual(report["cases"][0]["latencyMs"], 900.0)


class CasesFileTest(unittest.TestCase):
    def test_questions_file_is_well_formed(self):
        cases = load_cases(Path(__file__).with_name("questions.json"))
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(cases), 35)
        kinds = {"answerable", "off_topic", "wrong_period", "lacks_value", "ambiguous", "yearly_topic", "duplicate_heavy"}
        self.assertEqual({case["kind"] for case in cases}, kinds)
        for case in cases:
            self.assertIn(case["language"], {"ro", "ru", "en"}, case["id"])
            self.assertTrue(case["expect"]["status"], case["id"])
            json.dumps(case)  # serialisable

    def test_only_filter_rejects_unknown_ids(self):
        path = Path(__file__).with_name("questions.json")
        self.assertEqual([case["id"] for case in load_cases(path, ["off-pizza-ro"])], ["off-pizza-ro"])
        with self.assertRaises(ValueError):
            load_cases(path, ["no-such-case"])


class ProgressTests(unittest.TestCase):
    def test_snapshot_counts_and_estimates_remaining_time(self) -> None:
        results = [{"id": "a", "passed": True}, {"id": "b", "passed": False}]
        snapshot = progress_snapshot(results, 5, 30.0, "http://x/v1/chat")
        self.assertEqual({key: snapshot[key] for key in ("done", "total", "passed", "failed", "lastCase", "elapsedS", "etaS", "finished")},
                         {"done": 2, "total": 5, "passed": 1, "failed": 1, "lastCase": "b", "elapsedS": 30, "etaS": 45, "finished": False})

    def test_snapshot_before_the_first_case_has_no_eta(self) -> None:
        snapshot = progress_snapshot([], 5, 0.0, "http://x/v1/chat")
        self.assertEqual((snapshot["done"], snapshot["etaS"], snapshot["lastCase"]), (0, None, None))

    def test_write_progress_replaces_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.progress.json"
            write_progress(path, {"done": 1})
            write_progress(path, {"done": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"done": 2})
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["run.progress.json"])


class NotFoundHandler(BaseHTTPRequestHandler):
    """A real in-process chat endpoint: every question gets a NOT_FOUND reply after a random delay."""

    active = 0
    peak = 0
    lock = threading.Lock()

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        with NotFoundHandler.lock:
            NotFoundHandler.active += 1
            NotFoundHandler.peak = max(NotFoundHandler.peak, NotFoundHandler.active)
        time.sleep(random.uniform(.05, .2))
        with NotFoundHandler.lock:
            NotFoundHandler.active -= 1
        body = json.dumps({"mode": "rag", "status": "NOT_FOUND", "answer": "Nu am găsit.", "citations": [],
                           "clarificationChoices": None, "reason": "NO_RELEVANT_EVIDENCE", "flags": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class ConcurrentRunTests(unittest.TestCase):
    def test_concurrent_run_keeps_case_order_and_finishes_progress(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), NotFoundHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        cases = [{"id": f"off-{index}", "question": f"întrebare {index}", "language": "ro", "kind": "off_topic",
                  "expect": {"status": ["NOT_FOUND"], "reason": ["NO_RELEVANT_EVIDENCE", "OUT_OF_SCOPE"], "maxCitations": 0}}
                 for index in range(8)]
        with tempfile.TemporaryDirectory() as directory:
            cases_path, out = Path(directory) / "cases.json", Path(directory) / "report.json"
            cases_path.write_text(json.dumps(cases), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--url", f"http://127.0.0.1:{server.server_port}/v1/chat", "--cases", str(cases_path),
                             "--out", str(out), "--concurrency", "4"])
            report = json.loads(out.read_text(encoding="utf-8"))
            progress = json.loads((Path(directory) / "report.json.progress.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual([item["id"] for item in report["cases"]], [case["id"] for case in cases])
        self.assertEqual((report["concurrency"], report["metrics"]["passed"]), (4, 8))
        self.assertEqual((progress["done"], progress["total"], progress["finished"]), (8, 8, True))
        self.assertGreater(NotFoundHandler.peak, 1)


if __name__ == "__main__":
    unittest.main()
