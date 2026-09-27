import unittest

from municipal_rag.answering import (
    atomic_coverage_ledger,
    candidate_profile,
    coverage_ledger,
    evidence_for_scopes,
    evidence_for_selected_title,
    format_atomic_answer,
    format_scoped_answer,
    headline_only_amount,
    partial_intro,
    requested_atomic_cells,
    requested_scopes,
    resolve_ambiguity,
    split_explicit_selection,
)
from municipal_rag.verification import claim_scope_constraints, deterministic_issues, minimize_numeric_evidence


def evidence(document_id: str, title: str, quote: str, score: float) -> dict:
    return {
        "documentId": document_id,
        "metadata": {"title": title, "district": "Chișinău"},
        "citationText": quote,
        "retrievalText": f"{title} {quote}",
        "retrieval": {"rerankScore": score},
    }


class AmbiguityResolutionTests(unittest.TestCase):
    def test_clarification_selection_is_parsed_and_matches_only_chosen_title(self) -> None:
        original, selected = split_explicit_selection(
            'Câte accese sunt în Botanica?\nDocument selectat pentru clarificare: "Proiect Botanica"'
        )
        self.assertEqual(original, "Câte accese sunt în Botanica?")
        self.assertEqual(selected, "Proiect Botanica")
        items = [evidence("a", "Proiect Botanica", "73 de accese", .8),
                 evidence("b", "Proiect general", "60 mln lei", .9)]
        self.assertEqual([item["documentId"] for item in evidence_for_selected_title(items, selected)], ["a"])

    def test_single_title_with_requested_location_bypasses_clarification(self) -> None:
        interpreted = {"normalizedRomanianQuery": "Câte accese sunt în Botanica?",
                       "constraints": {"entities": ["accese"], "locations": ["Botanica"],
                                       "dates": [], "multipleProjects": False}}
        direct = evidence("botanica", "Accese reparate în sectorul Botanica", "Vor fi 73 de accese.", .79)
        general = evidence("general", "Căi de acces spre curțile de bloc", "În Botanica sunt lucrări.", .81)
        selected, choices, _, diagnostics = resolve_ambiguity([general, direct], interpreted, .88)
        self.assertEqual({item["documentId"] for item in selected}, {"botanica"})
        self.assertEqual(choices, [])
        self.assertIn(diagnostics["decision"], {"exact-title-override", "location-title-override"})

    def test_complex_question_builds_location_fact_matrix(self) -> None:
        interpreted = {
            "normalizedRomanianQuery": "Compară suma, durata, numărul acceselor și stadiul pentru Botanica și Buiucani",
            "constraints": {"locations": ["Botanica", "Buiucani"],
                            "factTypes": ["financiar", "durată", "număr", "stadiu"]},
        }
        cells = requested_atomic_cells(interpreted)
        self.assertEqual(len(cells), 8)
        self.assertEqual(cells[0], {"scope": "Botanica", "factType": "amount"})

    def test_simple_question_does_not_use_atomic_matrix(self) -> None:
        interpreted = {"normalizedRomanianQuery": "Care este stadiul în Botanica?",
                       "constraints": {"locations": ["Botanica"], "factTypes": ["stadiu"]}}
        self.assertEqual(requested_atomic_cells(interpreted), [])

    def test_atomic_ledger_and_table_preserve_each_missing_cell(self) -> None:
        cells = [
            {"scope": "Botanica", "factType": "count"},
            {"scope": "Botanica", "factType": "status"},
            {"scope": "Buiucani", "factType": "count"},
            {"scope": "Buiucani", "factType": "status"},
        ]
        claims = [
            {"text": "În Botanica sunt menționate 73 de accese.", "evidenceIds": ["S1"]},
            {"text": "În Buiucani este planificată procedura de achiziție.", "evidenceIds": ["S2"]},
        ]
        sources = [
            {"id": "S1", "title": "Botanica", "exactQuote": "În Botanica sunt menționate 73 de accese."},
            {"id": "S2", "title": "Buiucani", "exactQuote": "În Buiucani este planificată procedura de achiziție."},
        ]
        ledger = atomic_coverage_ledger(cells, claims, sources)
        self.assertEqual([item["status"] for item in ledger],
                         ["CONFIRMED", "UNCONFIRMED", "UNCONFIRMED", "CONFIRMED"])
        answer = format_atomic_answer(claims, ledger, "ro")
        self.assertIn("| Sector | Număr | Stadiu |", answer)
        self.assertIn("73 de accese. [S1]", answer)
        self.assertIn("Neconfirmat", answer)

    def test_requested_scopes_are_deduplicated_without_hardcoded_districts(self) -> None:
        interpreted = {"constraints": {"locations": ["Botanica", "botanica", "Durlești"]}}
        self.assertEqual(requested_scopes(interpreted), ["Botanica", "Durlești"])

    def test_coverage_requires_scope_in_claim_not_only_in_shared_evidence(self) -> None:
        sources = [{
            "id": "S1", "title": "Lucrări în Botanica și Buiucani",
            "exactQuote": "În Botanica lucrările au început. Pentru Buiucani urmează achiziția.",
        }]
        claims = [{"text": "În Botanica lucrările au început.", "evidenceIds": ["S1"]}]
        ledger = coverage_ledger(["Botanica", "Buiucani"], claims, sources)
        self.assertEqual([item["status"] for item in ledger], ["CONFIRMED", "UNCONFIRMED"])
        self.assertEqual(ledger[1]["candidateEvidenceCount"], 1)

    def test_scoped_answer_never_silently_omits_requested_location(self) -> None:
        claims = [{"text": "În Botanica lucrările au început.", "evidenceIds": ["S1"]}]
        ledger = [
            {"scope": "Botanica", "status": "CONFIRMED"},
            {"scope": "Buiucani", "status": "UNCONFIRMED"},
        ]
        answer = format_scoped_answer(claims, ledger, "ro", True)
        self.assertIn("În Botanica lucrările au început. [S1]", answer)
        self.assertIn("Buiucani: informația pentru acest punct nu a putut fi confirmată", answer)

    def test_claim_verification_scope_does_not_require_other_requested_locations(self) -> None:
        constraints = {"locations": ["Botanica", "Buiucani", "Ciocana"], "multipleProjects": True}
        scoped = claim_scope_constraints("În Botanica vor fi reabilitate 73 de accese.", constraints)
        self.assertEqual(scoped["locations"], ["Botanica"])
        self.assertFalse(scoped["multipleProjects"])

    def test_recovery_evidence_is_isolated_per_requested_scope(self) -> None:
        sources = [
            {"id": "S1", "title": "Lucrări Buiucani", "exactQuote": "Lucrările au început la 24 iulie."},
            {"id": "S2", "title": "Accese municipale", "exactQuote": "În Buiucani urmează achiziția."},
        ]
        self.assertEqual([item["id"] for item in evidence_for_scopes(sources, ["Buiucani"])], ["S2"])

    def test_long_claim_with_details_absent_from_quote_is_rejected(self) -> None:
        sources = {"S1": {
            "documentId": "d1", "evidenceKind": "body", "title": "Lucrări Botanica",
            "exactQuote": "Reparația acceselor către curțile de bloc din Botanica a început în octombrie 2022.",
        }}
        claim = {"text": (
            "În Botanica, lucrările includ decaparea betonului asfaltic și a bordurilor, "
            "ridicarea capacelor căminelor, amenajarea fundației și aplicarea straturilor de asfalt."
        ), "evidenceIds": ["S1"]}
        self.assertIn("LOW_LEXICAL_ENTAILMENT", deterministic_issues(claim, sources))

    def test_partial_intro_uses_dynamic_location_scope(self) -> None:
        text = partial_intro({"language": "ro", "constraints": {"locations": ["Botanica", "Buiucani"]}})
        self.assertIn("Botanica, Buiucani", text)
        self.assertIn("nu confirmă complet", text)

    def test_exact_title_entity_match_overrides_close_rerank_scores(self) -> None:
        interpreted = {
            "normalizedRomanianQuery": "Conform articolului despre cele 60 milioane de lei, ce sumă a fost alocată pentru reparația acceselor către curțile de blocuri din Chișinău?",
            "constraints": {
                "entities": ["60 milioane de lei", "reparația acceselor către curțile de blocuri", "Chișinău"],
                "locations": ["Chișinău"], "dates": [], "multipleProjects": False,
            },
        }
        exact = evidence("exact", "60 mln lei din bugetul municipal pentru anul curent au fost alocate pentru reparația acceselor către curțile de blocuri din Chișinău", "Au fost alocate 60 milioane lei.", .82)
        related = evidence("related", "Zeci de accese către curțile de bloc din sectorul Botanica sunt în proces de reparație", "Pentru alte sectoare au fost alocate 60 milioane lei în anul trecut.", .86)
        selected, choices, _, diagnostics = resolve_ambiguity([related, exact], interpreted, .88)
        self.assertEqual({item["documentId"] for item in selected}, {"exact"})
        self.assertEqual(choices, [])
        self.assertEqual(diagnostics["decision"], "exact-title-override")

    def test_genuinely_distinct_compatible_projects_request_clarification(self) -> None:
        interpreted = {
            "normalizedRomanianQuery": "Care proiect municipal de renovare din Chișinău este vizat?",
            "constraints": {"entities": ["proiect municipal de renovare"], "locations": ["Chișinău"],
                            "dates": [], "multipleProjects": False},
        }
        first = evidence("street", "Reabilitarea străzii Alba Iulia", "Proiect municipal de renovare în Chișinău.", .80)
        second = evidence("boulevard", "Modernizarea bulevardului Dacia", "Proiect municipal de renovare în Chișinău.", .76)
        _, choices, reasons, diagnostics = resolve_ambiguity([first, second], interpreted, .88)
        self.assertEqual([item["documentId"] for item in choices], ["street", "boulevard"])
        self.assertTrue(reasons)
        self.assertEqual(diagnostics["decision"], "needs-clarification")
        self.assertIn("matchReasons", choices[0])

    def test_period_conflict_removes_candidate_from_ambiguity(self) -> None:
        interpreted = {
            "normalizedRomanianQuery": "Ce sumă a fost alocată în anul curent pentru lucrări?",
            "constraints": {"entities": ["sumă alocată", "lucrări"], "locations": [],
                            "dates": ["anul curent"], "multipleProjects": False},
        }
        old = evidence("old", "Lucrări municipale", "În anul trecut au fost alocate 20 milioane lei.", .9)
        profile = candidate_profile(old, interpreted)
        self.assertFalse(profile["compatible"])

    def test_verifier_rejects_wrong_period_and_quoted_project(self) -> None:
        sources = {"S1": {"documentId": "d1", "evidenceKind": "body", "title": "Alt proiect",
                           "exactQuote": "În anul trecut au fost alocate 60 milioane lei."}}
        claim = {"text": "60 milioane lei au fost alocate în anul curent.", "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources, 'În articolul «Proiectul acceselor către curți în anul curent», ce sumă a fost alocată?')
        self.assertIn("QUESTION_EVIDENCE_TIME_CONFLICT", issues)
        self.assertIn("PROJECT_TITLE_MISMATCH", issues)

    def test_amount_question_rejects_unrelated_count_claim(self) -> None:
        sources = {"S1": {"documentId": "d1", "evidenceKind": "body", "title": "Accese",
                           "exactQuote": "bd. Dacia – 10 accese"}}
        claim = {"text": "Au fost reparate 10 accese.", "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources, "Ce sumă a fost alocată pentru lucrări?")
        self.assertIn("REQUESTED_AMOUNT_MISSING", issues)

    def test_headline_amount_is_partial_when_body_does_not_corroborate_it(self) -> None:
        item = evidence("d1", "60 mln lei au fost alocate pentru reparații", "Au fost reparate 10 accese.", .9)
        interpreted = {"normalizedRomanianQuery": "Ce sumă de 60 milioane de lei a fost alocată?",
                       "constraints": {"factTypes": ["financiar"]}}
        result = headline_only_amount([item], interpreted)
        self.assertIsNotNone(result)
        self.assertEqual(result["citation"]["evidenceKind"], "headline")
        self.assertIn("60 milioane lei", result["amount"])

    def test_numeric_claim_is_narrowed_to_matching_location_passage(self) -> None:
        sources = {
            "S1": {"title": "Lucrări Botanica", "exactQuote": "bd. Dacia – 10 accese"},
            "S2": {"title": "Alt proiect", "exactQuote": "Au fost reparate 10 accese în alt sector"},
            "S3": {"title": "Listă generală", "exactQuote": "În total sunt 73 de accese"},
        }
        claim = {"text": "Pe bulevardul Dacia au fost reparate 10 accese.",
                 "evidenceIds": ["S1", "S2", "S3"]}
        repaired = minimize_numeric_evidence(claim, sources)
        self.assertEqual(repaired["evidenceIds"], ["S1"])

    def test_rejects_one_contract_value_applied_to_multiple_sectors(self) -> None:
        sources = {"S1": {
            "documentId": "d1", "evidenceKind": "body", "title": "Reparația acceselor",
            "exactQuote": (
                "Valoarea totală a contractului este de 14 mln lei și urmează a fi executat "
                "într-o perioadă de 6 luni. Asemenea lucrări sunt preconizate pentru alte "
                "sectoare, iar pentru sec. Buiucani urmează achiziția publică."
            ),
        }}
        claim = {"text": "Pentru Botanica și Buiucani suma este de 14 mln lei, iar durata este de 6 luni.",
                 "evidenceIds": ["S1"]}
        constraints = {"locations": ["Botanica", "Buiucani"], "multipleProjects": True}
        issues = deterministic_issues(claim, sources,
            "Care este suma și perioada pentru Botanica și Buiucani?", constraints)
        self.assertIn("UNSUPPORTED_LOCATION:botanica", issues)
        self.assertIn("NUMBER_LOCATION_SCOPE_MISMATCH:14:buiucani", issues)
        self.assertIn("NUMBER_LOCATION_SCOPE_MISMATCH:6:buiucani", issues)

    def test_accepts_separate_numeric_claim_with_local_scope(self) -> None:
        sources = {"S1": {
            "documentId": "d1", "evidenceKind": "body", "title": "Lucrări Botanica",
            "exactQuote": "În sectorul Botanica, contractul este de 5 mln lei și durează 3 luni.",
        }}
        claim = {"text": "În Botanica, contractul este de 5 mln lei și durează 3 luni.",
                 "evidenceIds": ["S1"]}
        constraints = {"locations": ["Botanica", "Buiucani"], "multipleProjects": True}
        issues = deterministic_issues(claim, sources,
            "Care sunt sumele și perioadele pentru Botanica și Buiucani?", constraints)
        self.assertFalse(any(value.startswith(("UNSUPPORTED_LOCATION", "NUMBER_LOCATION_SCOPE_MISMATCH",
                                               "MISSING_CLAIM_LOCATION_SCOPE")) for value in issues))

    def test_street_abbreviation_matches_full_location(self) -> None:
        sources = {"S1": {"documentId": "d1", "evidenceKind": "list", "title": "Accese",
                           "exactQuote": "bd. Dacia – 10 accese"}}
        claim = {"text": "Pe bulevardul Dacia au fost reparate 10 accese.", "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources,
            "Câte accese au fost reparate pe bulevardul Dacia?",
            {"locations": ["bulevardul Dacia"]})
        self.assertNotIn("UNSUPPORTED_LOCATION:bulevardul dacia", issues)
        self.assertNotIn("NUMBER_LOCATION_SCOPE_MISMATCH:10:bulevardul dacia", issues)

    def test_rejects_completed_claim_for_future_procurement(self) -> None:
        sources = {"S1": {
            "documentId": "d1", "evidenceKind": "body", "title": "Lucrări Buiucani",
            "exactQuote": "Pentru sectorul Buiucani urmează a fi demarată procedura de achiziție publică.",
        }}
        claim = {"text": "Lucrările din Buiucani au fost executate.", "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources, "Ce lucrări au fost executate în Buiucani?",
                                      {"locations": ["Buiucani"]})
        self.assertIn("PROJECT_STAGE_MISMATCH:buiucani", issues)

    def test_rejects_tender_evaluation_for_procurement_not_started(self) -> None:
        sources = {"S1": {
            "documentId": "d1", "evidenceKind": "body", "title": "Accese",
            "exactQuote": ("La moment este în faza de evaluare licitația pentru sec. Ciocana, "
                           "iar pentru sec. Buiucani urmează a fi demarată procedura de achiziție publică."),
        }}
        claim = {"text": "În Buiucani, licitația este în faza de evaluare.", "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources, "Care este stadiul în Buiucani?",
                                      {"locations": ["Buiucani"]})
        self.assertIn("PROJECT_STAGE_MISMATCH:buiucani", issues)

    def test_rejects_allocation_relabelled_as_contract_amount(self) -> None:
        sources = {"S1": {"documentId": "d1", "evidenceKind": "body", "title": "Buget Botanica",
                           "exactQuote": "Pentru Botanica au fost alocate 60 milioane lei."}}
        claim = {"text": "Suma contractului pentru Botanica este de 60 milioane lei.",
                 "evidenceIds": ["S1"]}
        issues = deterministic_issues(claim, sources, "Care este suma contractului pentru Botanica?",
                                      {"locations": ["Botanica"]})
        self.assertIn("AMOUNT_ROLE_MISMATCH:contract", issues)


if __name__ == "__main__":
    unittest.main()
