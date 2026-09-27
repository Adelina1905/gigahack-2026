from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from typing import Any


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from municipal_rag import guardrails
from municipal_rag.answering import CLAIMS_SCHEMA, SCREEN_MARKER, AnswerDependencies, ambiguity, answer, dense_text, run_answer
from municipal_rag.config import load_config
from municipal_rag.retrieval import INTERPRETER_SCHEMA
from municipal_rag.verification import VERDICT_SCHEMA, deterministic_issues, verifier_prompt


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


def payload(document_id: str, evidence_id: str, score: float, quote: str, **metadata: Any) -> dict[str, Any]:
    return {"documentId": document_id, "evidenceId": evidence_id, "versionId": "v1", "evidenceKind": "body", "citationText": quote,
            "sourceLocator": {"page": 1}, "metadata": {"title": metadata.pop("title", f"Document {document_id}"), **metadata},
            "retrieval": {"rerankScore": score}}


class FakeModels:
    """Hand-written model and search calls; each schema gets its canned response and every call is recorded."""

    def __init__(self, evidence: list[dict[str, Any]], interpretation: dict[str, Any] | None = None,
                 irrelevant: set[str] = frozenset(), claims: list[list[dict[str, Any]]] | None = None,
                 rejected: set[str] = frozenset(), generation_status: str = "SUPPORTED",
                 subjects: dict[str, str] | None = None) -> None:
        self.evidence = evidence
        self.interpretation = interpretation or {}
        self.irrelevant = irrelevant
        self.claims = list(claims or [])
        self.rejected = rejected
        self.generation_status = generation_status
        self.subjects = subjects or {}
        self.calls: list[tuple[str, dict[str, Any] | str]] = []
        self.embedded: list[str] = []
        self.retrieved: list[str] = []
        self.retrieval_queries: list[str] = []

    def dependencies(self) -> AnswerDependencies:
        return AnswerDependencies(chat=self.chat, embed=self.embed, retrieve=self.retrieve, today=lambda: date(2026, 9, 27))

    def chat(self, model: str, system: str, user: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            body: dict[str, Any] | str = json.loads(user)
        except json.JSONDecodeError:
            body = user
        if schema is INTERPRETER_SCHEMA:
            self.calls.append(("interpret", body))
            question = body["question"] if isinstance(body, dict) else body
            return {"standaloneQuestion": question, "language": "ro", "normalizedRomanianQuery": question, "entities": [],
                    "streets": [], "locations": [], "dates": [], "factTypes": [], "answerType": "other", "yearlyTopic": False,
                    "topicCategory": "none", "inScope": True, **self.interpretation}
        if system.startswith(SCREEN_MARKER):
            self.calls.append(("screen", body))
            assert schema is not None and schema["required"] == [passage["id"] for passage in body["passages"]]
            return {passage["id"]: "TOPIC_ONLY" if passage["documentId"] in self.irrelevant else
                    f"RELEVANT_{self.subjects.get(passage['documentId'], 'A')}" for passage in body["passages"]}
        if schema is CLAIMS_SCHEMA:
            self.calls.append(("generate", body))
            claims = self.claims.pop(0) if self.claims else []
            return {"status": self.generation_status if claims else "NOT_FOUND", "claims": claims}
        if schema is VERDICT_SCHEMA:
            self.calls.append(("verify", body))
            return {"supported": body["claim"] not in self.rejected, "reason": "checked"}
        raise AssertionError(f"unexpected model call: {system[:60]}")

    def embed(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [1.0, 0.0]

    def retrieve(self, question: str, interpreted: dict[str, Any], dense: list[float]) -> dict[str, Any]:
        self.retrieved.append(question)
        self.retrieval_queries.append(interpreted.get("retrievalQuery"))
        return {"evidence": [dict(value) for value in self.evidence], "diagnostics": None}

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]


ORDER = payload("order-2026", "e-order", .82, "Se aprobă calendarul înscrierii copiilor în clasa I pentru anul de studii 2026-2027.",
    title="Ordin nr. 01/1-7/345 din 17.03.2026 Cu privire la organizarea înscrierii copiilor în clasa I în anul de studii 2026-2027",
    publisher="chisinauedu.dgets.md", publishedDate="2026-03-18", category="education",
    sourceUrl="https://chisinauedu.dgets.md/storage/orders/1773840248_scan-2025-09-16.pdf")
COPY_2023 = payload("riscani-2023", "e-riscani", .84, "Buletinul de identitate al părintelui și certificatul de naștere al copilului.",
    title="Setul de acte necesare pentru înscriere este disponibil aici , inclusiv formularul de cerere.",
    publisher="detsriscani.md", publishedDate="2023-04-04", category="education", district="Râșcani",
    sourceUrl="https://mecc.gov.md/sites/default/files/ordin_278_cl_i_2023-2024.pdf")
COPY_2022 = payload("buiucani-2022", "e-buiucani", .83, "Lista actelor necesare care se anexează la cererea pentru înscrierea în clasa I.",
    title="Setul de acte necesare pentru înscriere este disponibil aici , de asemenea și modelul de cerere.",
    publisher="buiucanidets.md", publishedDate="2022-03-31", category="education", district="Buiucani",
    sourceUrl="https://mec.gov.md/sites/default/files/lista_acte_cerere.pdf")
GUIDE = payload("dgams-guide", "e-guide", .81, "Sfaturi pentru părinți despre pregătirea copilului pentru școală.",
    title="Suport informațional_RO_(web)", publisher="dgams.md", publishedDate="2024-05-02", category="healthcare",
    sourceUrl="https://dgams.md/files/Suport_informational_RO_web.pdf")
ENROLMENT = "vreau sa aflu despre legislatiile cum sa dau copilul meu la scoala"


class RunAnswerTests(unittest.TestCase):
    config = load_config()

    def run_answer(self, models: FakeModels, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return run_answer(question, history or [], self.config, models.dependencies())

    def test_enrolment_keeps_the_current_order_and_cites_only_it(self) -> None:
        models = FakeModels([COPY_2023, COPY_2022, ORDER, GUIDE], {"topicCategory": "education"}, irrelevant={"dgams-guide"},
            claims=[[{"text": "Înscrierea în clasa I pentru 2026-2027 este reglementată de Ordinul nr. 01/1-7/345 din 17.03.2026.", "evidenceIds": ["S3"]}]])
        result = self.run_answer(models, ENROLMENT)
        self.assertEqual((result["status"], result["reason"]), ("SUPPORTED", None))
        self.assertEqual(result["flags"], ["OFF_TOPIC_DROPPED:1", "DUPLICATES_MERGED:1"])
        self.assertEqual([citation["documentId"] for citation in result["citations"]], ["order-2026"])
        citation = result["citations"][0]
        self.assertEqual((citation["id"], citation["publisher"], citation["publishedDate"], citation["outdated"]),
                         ("S1", "chisinauedu.dgets.md", "2026-03-18", False))
        self.assertTrue(result["answer"].endswith("[S1]"))
        self.assertEqual(result["interpretedConstraints"]["answerType"], "legal_act")
        screened = [passage["documentId"] for passage in models.calls[1][1]["passages"]]
        self.assertEqual(screened, ["riscani-2023", "order-2026", "dgams-guide"])
        self.assertEqual(models.kinds(), ["interpret", "screen", "generate", "verify"])

    def test_off_topic_question_is_out_of_scope_without_screen_or_citations(self) -> None:
        models = FakeModels([payload("event", "e1", .41, "Rețetă de pizza la festival."), payload("x", "e2", .30, "Altceva.")],
                            {"inScope": False})
        result = self.run_answer(models, "rețeta de pizza napoletană")
        self.assertEqual((result["status"], result["reason"], result["citations"]), ("NOT_FOUND", "OUT_OF_SCOPE", []))
        self.assertEqual(result["flags"], ["OFF_TOPIC_DROPPED:2"])
        self.assertEqual(result["answer"], guardrails.not_found_answer("ro", "OUT_OF_SCOPE"))
        self.assertEqual(models.kinds(), ["interpret"])

    def test_other_year_is_dropped_before_the_screen(self) -> None:
        event = payload("wc-2026", "e1", .7, "Meciurile Campionatului Mondial 2026 vor fi transmise în Piața Marii Adunări Naționale.",
                        publishedDate="2026-06-10")
        models = FakeModels([event], {"inScope": False, "language": "ro"})
        result = self.run_answer(models, "Cine a câștigat Campionatul Mondial de fotbal 2022?")
        self.assertEqual((result["status"], result["reason"], result["flags"]), ("NOT_FOUND", "OUT_OF_SCOPE", ["OFF_TOPIC_DROPPED:1"]))
        self.assertNotIn("screen", models.kinds())

    def test_relevant_documents_without_the_hours_are_evidence_lacks_value(self) -> None:
        structure = payload("dgtpcc", "e1", .8, "Structura DGTPCC cuprinde trei secții și un serviciu.", title="DGTPCC")
        models = FakeModels([structure], claims=[[{"text": "DGTPCC are trei secții și un serviciu.", "evidenceIds": ["S1"]}]])
        result = self.run_answer(models, "Care este programul de lucru al DGTPCC?")
        self.assertEqual((result["status"], result["reason"], result["citations"]), ("NOT_FOUND", "EVIDENCE_LACKS_VALUE", []))
        self.assertIn("programul de lucru", result["answer"])

    def test_generator_finding_nothing_in_relevant_documents_is_evidence_lacks_value(self) -> None:
        models = FakeModels([payload("a", "e1", .8, "Text despre subiect.")], claims=[[], []])
        result = self.run_answer(models, "Cât costă abonamentul?")
        self.assertEqual((result["status"], result["reason"], result["flags"]), ("NOT_FOUND", "EVIDENCE_LACKS_VALUE", ["CORRECTION_ROUND"]))
        self.assertEqual(models.kinds(), ["interpret", "screen", "generate", "generate"])

    def test_empty_first_generation_is_retried_once(self) -> None:
        claim = {"text": "Abonamentul costă 300 lei.", "evidenceIds": ["S1"]}
        models = FakeModels([payload("a", "e1", .8, "Abonamentul lunar costă 300 lei.")], claims=[[], [claim]])
        result = self.run_answer(models, "Cât costă abonamentul?")
        self.assertEqual((result["status"], result["flags"]), ("SUPPORTED", ["CORRECTION_ROUND"]))

    def test_rejected_claims_after_correction_are_claims_unverified(self) -> None:
        claim = {"text": "Lucrările au costat mult.", "evidenceIds": ["S1"]}
        models = FakeModels([payload("a", "e1", .8, "Lucrări de reparație.")], claims=[[claim], [claim]], rejected={claim["text"]})
        result = self.run_answer(models, "Ce lucrări s-au făcut?")
        self.assertEqual((result["status"], result["reason"], result["citations"]), ("NOT_FOUND", "CLAIMS_UNVERIFIED", []))
        self.assertEqual(result["flags"], ["CLAIMS_REJECTED:1/1", "CORRECTION_ROUND"])
        self.assertEqual(models.kinds(), ["interpret", "screen", "generate", "verify", "generate", "verify"])

    def test_partial_answer_counts_rejected_claims(self) -> None:
        good = {"text": "Au fost reparate trotuarele.", "evidenceIds": ["S1"]}
        bad = {"text": "Au fost plantați copaci.", "evidenceIds": ["S1"]}
        models = FakeModels([payload("a", "e1", .8, "Au fost reparate trotuarele.")], claims=[[good, bad], [good, bad]], rejected={bad["text"]})
        result = self.run_answer(models, "Ce lucrări s-au făcut?")
        self.assertEqual((result["status"], result["reason"]), ("PARTIAL", None))
        # Half of the claims survived, so no correction round is spent.
        self.assertEqual(result["flags"], ["CLAIMS_REJECTED:1/2"])
        self.assertEqual(result["answer"], "Au fost reparate trotuarele. [S1]")
        self.assertEqual(models.kinds(), ["interpret", "screen", "generate", "verify", "verify"])

    def test_a_worse_correction_keeps_the_first_rounds_verified_claims(self) -> None:
        good = {"text": "Au fost reparate trotuarele.", "evidenceIds": ["S1"]}
        bad = [{"text": f"Afirmație falsă {index}.", "evidenceIds": ["S1"]} for index in range(2)]
        models = FakeModels([payload("a", "e1", .8, "Au fost reparate trotuarele.")], claims=[[good, *bad], bad],
                            rejected={item["text"] for item in bad})
        result = self.run_answer(models, "Ce lucrări s-au făcut?")
        self.assertEqual((result["status"], result["answer"]), ("PARTIAL", "Au fost reparate trotuarele. [S1]"))
        self.assertEqual(result["flags"], ["CLAIMS_REJECTED:2/3", "CORRECTION_ROUND"])

    def test_conflicting_documents_are_a_contradiction(self) -> None:
        models = FakeModels([payload("a", "e1", .8, "Taxa este 100 lei."), payload("b", "e2", .5, "Taxa este 200 lei.")],
            claims=[[{"text": "Taxa este 100 lei.", "evidenceIds": ["S1"]}, {"text": "Taxa este 200 lei.", "evidenceIds": ["S2"]}]],
            generation_status="CONTRADICTION")
        result = self.run_answer(models, "Cât este taxa?")
        self.assertEqual((result["status"], result["reason"]), ("CONTRADICTION", "CONFLICTING_DOCUMENTS"))
        self.assertEqual(len(result["citations"]), 2)

    def test_only_outdated_sources_are_answered_with_a_dated_warning(self) -> None:
        models = FakeModels([COPY_2023], {"language": "ro"},
            claims=[[{"text": "Se depun buletinul părintelui și certificatul de naștere al copilului.", "evidenceIds": ["S1"]}]])
        result = self.run_answer(models, "Ce acte trebuie pentru înscrierea în clasa I?")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertIn("OUTDATED_SOURCES", result["flags"])
        self.assertTrue(result["citations"][0]["outdated"])
        self.assertIn("2023", result["answer"].splitlines()[-1])
        self.assertEqual(guardrails.uncited_segments(result["answer"], {"S1"}), [])

    def test_distinct_strong_documents_ask_with_readable_labels_then_the_pick_is_answered(self) -> None:
        first = payload("parking-a", "e1", .8, "Parcarea pe strada A costă 10 lei pe oră.", title="Decizie nr. 1/2 din 2026-01-10 — Cu privire la parcarea A",
                        publisher="actelocale.gov.md", publishedDate="2026-01-10")
        second = payload("parking-b", "e2", .78, "Parcarea pe strada B costă 15 lei pe oră.", title="Decizie nr. 3/4 din 2026-02-11 — Cu privire la parcarea B",
                         publisher="actelocale.gov.md", publishedDate="2026-02-11")
        subjects = {"parking-a": "A", "parking-b": "B"}
        # When the screen puts both documents under one subject there is nothing to ask.
        self.assertNotEqual(self.run_answer(FakeModels([first, second]), "Cât costă parcarea?")["status"], "NEEDS_CLARIFICATION")
        # Colliding documents with nothing verified are not offered as choices: the answer is "no information".
        unanswered = self.run_answer(FakeModels([first, second], subjects=subjects), "Cât costă parcarea?")
        self.assertEqual((unanswered["status"], unanswered.get("clarificationChoices"), unanswered["citations"]), ("NOT_FOUND", None, []))
        models = FakeModels([first, second], subjects=subjects, claims=[[
            {"text": "Parcarea pe strada A costă 10 lei pe oră.", "evidenceIds": ["S1"]},
            {"text": "Parcarea pe strada B costă 15 lei pe oră.", "evidenceIds": ["S2"]}]])
        result = self.run_answer(models, "Cât costă parcarea?")
        self.assertEqual((result["status"], result["reason"]), ("NEEDS_CLARIFICATION", None))
        labels = [choice["label"] for choice in result["clarificationChoices"]]
        self.assertEqual(labels, ["Decizie nr. 1/2 — parcarea A · actelocale.gov.md · 10.01.2026",
                                  "Decizie nr. 3/4 — parcarea B · actelocale.gov.md · 11.02.2026"])
        self.assertEqual(result["answer"], guardrails.clarification_question("ro"))
        self.assertEqual([citation["documentId"] for citation in result["citations"]], ["parking-a", "parking-b"])
        history = [{"role": "user", "content": "Cât costă parcarea?"},
                   {"role": "assistant", "content": result["answer"] + "".join(f"\n- {label}" for label in labels)}]
        picked = FakeModels([first, second], claims=[[{"text": "Parcarea pe strada B costă 15 lei pe oră.", "evidenceIds": ["S2"]}]], subjects=subjects)
        scoped = self.run_answer(picked, labels[1], history)
        self.assertEqual(scoped["status"], "SUPPORTED")
        self.assertEqual([citation["documentId"] for citation in scoped["citations"]], ["parking-b"])
        self.assertEqual(picked.calls[0][1], "Cât costă parcarea?")
        self.assertEqual([passage["documentId"] for passage in picked.calls[2][1]["evidence"]], ["parking-b"])

    def test_follow_up_is_rewritten_and_re_embedded(self) -> None:
        history = [{"role": "user", "content": "Care este programul DGETS?"}, {"role": "assistant", "content": "Luni-vineri 8:00-17:00. [S1]"}]
        models = FakeModels([], {"standaloneQuestion": "Care este programul DGETS sâmbăta?"})
        result = self.run_answer(models, "Și sâmbăta?", history)
        self.assertEqual(models.calls[0][1]["recentTurns"], history)
        self.assertEqual(models.embedded, ["Și sâmbăta?", "Care este programul DGETS sâmbăta?"])
        self.assertEqual(models.retrieved, ["Care este programul DGETS sâmbăta?"])
        self.assertEqual((result["status"], result["reason"], result["standaloneQuestion"]),
                         ("NOT_FOUND", "NO_RELEVANT_EVIDENCE", "Care este programul DGETS sâmbăta?"))

    def test_documents_on_one_subject_are_answered_together_instead_of_asking(self) -> None:
        order = payload("order", "e1", .8, "Înscrierea în clasa I începe la 1 aprilie 2026.", title="Ordin nr. 1 din 17.03.2026")
        news = payload("news", "e2", .79, "Etapa I de înscriere în clasa I începe la 1 aprilie 2026.", title="Începe înscrierea")
        models = FakeModels([order, news], {"answerType": "date"},
            claims=[[{"text": "Înscrierea în clasa I începe la 1 aprilie 2026.", "evidenceIds": ["S2"]}]])
        result = self.run_answer(models, "Când începe înscrierea în clasa I 2026?")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertEqual(result["answer"], "Înscrierea în clasa I începe la 1 aprilie 2026. [S1]")
        self.assertEqual([citation["documentId"] for citation in result["citations"]], ["news"])

    def test_distinct_unnamed_instances_are_clarified_even_for_list_questions(self) -> None:
        first = payload("lyceum-a", "e1", .8, "La terenul de fotbal al liceului A s-a schimbat gazonul.", title="Teren de fotbal la Liceul A")
        second = payload("lyceum-b", "e2", .79, "La terenul de fotbal al liceului B s-a instalat iluminat.", title="Stadion la Liceul B")
        models = FakeModels([first, second], {"answerType": "list"}, subjects={"lyceum-a": "A", "lyceum-b": "B"}, claims=[[
            {"text": "La terenul de fotbal al liceului A s-a schimbat gazonul.", "evidenceIds": ["S1"]},
            {"text": "La terenul de fotbal al liceului B s-a instalat iluminat.", "evidenceIds": ["S2"]}]])
        result = self.run_answer(models, "Ce lucrări s-au făcut la terenul de fotbal al liceului?")
        self.assertEqual(result["status"], "NEEDS_CLARIFICATION")
        self.assertEqual([choice["documentId"] for choice in result["clarificationChoices"]], ["lyceum-a", "lyceum-b"])

    def test_out_of_scope_questions_are_not_answered_from_themed_passages(self) -> None:
        film = payload("film", "e1", .7, "Seară de film în scuarul Mihai Eminescu.")
        models = FakeModels([film], {"inScope": False, "language": "ru"})
        result = self.run_answer(models, "Посоветуй хороший фильм на вечер.")
        self.assertEqual((result["status"], result["reason"], result["citations"]), ("NOT_FOUND", "OUT_OF_SCOPE", []))
        self.assertEqual(models.kinds(), ["interpret"])

    def test_conflicting_values_from_one_document_are_not_a_contradiction(self) -> None:
        models = FakeModels([payload("a", "e1", .8, "Proiectul X costă 100 lei. Proiectul Y costă 200 lei.")],
            claims=[[{"text": "Bugetul este 100 lei.", "evidenceIds": ["S1"]}, {"text": "Bugetul este 200 lei.", "evidenceIds": ["S1"]}]],
            generation_status="CONTRADICTION")
        result = self.run_answer(models, "Care este bugetul academiei?")
        self.assertEqual((result["status"], result["reason"], result["citations"]), ("NOT_FOUND", "CLAIMS_UNVERIFIED", []))

    def test_list_questions_combine_tied_documents_about_one_subject(self) -> None:
        first = payload("works-a", "e1", .8, "Au fost reparate trotuarele pe str. Vasile Alecsandri.")
        second = payload("works-b", "e2", .79, "S-a aplicat un strat bituminos pe str. Vasile Alecsandri.")
        models = FakeModels([first, second], {"answerType": "list", "streets": ["Vasile Alecsandri"]},
            claims=[[{"text": "Au fost reparate trotuarele.", "evidenceIds": ["S1"]}, {"text": "S-a aplicat un strat bituminos.", "evidenceIds": ["S2"]}]])
        result = self.run_answer(models, "Ce lucrări s-au făcut pe strada Vasile Alecsandri?")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertEqual([citation["documentId"] for citation in result["citations"]], ["works-a", "works-b"])

    def test_yearly_topics_without_a_year_search_for_the_current_year(self) -> None:
        models = FakeModels([], {"normalizedRomanianQuery": "înscrierea în clasa I"})
        self.run_answer(models, "Cum înscriu copilul în clasa I?")
        self.assertEqual(models.embedded, ["Cum înscriu copilul în clasa I? 2026"])
        self.assertEqual(models.retrieval_queries, ["înscrierea în clasa I 2026"])
        flagged = FakeModels([], {"yearlyTopic": True, "normalizedRomanianQuery": "programele de vacanță"})
        self.run_answer(flagged, "Ce programe de vacanță există?")
        self.assertEqual(flagged.embedded, ["Ce programe de vacanță există?", "Ce programe de vacanță există? 2026"])
        explicit = FakeModels([], {"normalizedRomanianQuery": "înscrierea în clasa I 2025"})
        self.run_answer(explicit, "Înscrierea în clasa I 2025")
        self.assertEqual((explicit.embedded, explicit.retrieval_queries), (["Înscrierea în clasa I 2025"], ["înscrierea în clasa I 2025"]))
        self.assertEqual(dense_text("Taxe locale", True, date(2027, 1, 5)), "Taxe locale 2027")

    def test_english_question_gets_english_templates(self) -> None:
        models = FakeModels([], {"language": "en"})
        result = self.run_answer(models, "What are the opening hours of the city hall?")
        self.assertEqual(result["detectedLanguage"], "en")
        self.assertEqual(result["answer"], guardrails.not_found_answer("en", "NO_RELEVANT_EVIDENCE"))

    def test_model_failures_become_unavailable(self) -> None:
        class Broken(FakeModels):
            def retrieve(self, question: str, interpreted: dict[str, Any], dense: list[float]) -> dict[str, Any]:
                raise RuntimeError("qdrant down")
        result = answer("Q?", dependencies=Broken([]).dependencies())
        self.assertEqual((result["status"], result["confidence"]["reasons"]), ("UNAVAILABLE", ["qdrant down"]))

    def test_multi_intent_answer_reports_coverage_per_requirement(self) -> None:
        first = payload("shop", "e1", .8, "Comerciantul depune notificarea privind inițierea activității de comerț.")
        first["retrieval"]["requirementIds"] = ["R1"]
        requirements = [
            {"id": "R1", "question": "Ce notificare trebuie depusă?", "normalizedRomanianQuery": "notificare comerț",
             "answerType": "procedure", "yearlyTopic": False, "topicCategory": "services"},
            {"id": "R2", "question": "Care este taxa actuală?", "normalizedRomanianQuery": "taxă magazin actuală",
             "answerType": "amount", "yearlyTopic": True, "topicCategory": "services"},
        ]
        claim = {"text": "Comerciantul trebuie să depună notificarea de inițiere a activității de comerț.",
                 "requirementId": "R1", "evidenceIds": ["S1"]}
        models = FakeModels([first], {"requirements": requirements}, claims=[[claim]])
        result = self.run_answer(models, "Cum deschid magazinul și care este taxa actuală?")
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual([(item["id"], item["status"]) for item in result["coverage"]],
                         [("R1", "ANSWERED"), ("R2", "MISSING")])
        self.assertIn("Care este taxa actuală?", result["answer"])
        verification = next(body for kind, body in models.calls if kind == "verify")
        self.assertEqual(verification["question"], "Ce notificare trebuie depusă?")

    def test_rejected_extra_draft_does_not_make_complete_answer_partial(self) -> None:
        evidence = payload("lumteh", "e1", .8,
                           "Î.M. Lumteh întreține iluminatul public. Defecțiunile se raportează pe eu.chisinau.md.")
        requirements = [
            {"id": "R1", "question": "Cine întreține iluminatul public?",
             "normalizedRomanianQuery": "întreținere iluminat public", "answerType": "organization",
             "yearlyTopic": False, "topicCategory": "services"},
            {"id": "R2", "question": "Unde se raportează defecțiunile?",
             "normalizedRomanianQuery": "raportare iluminat defect", "answerType": "procedure",
             "yearlyTopic": False, "topicCategory": "services"},
        ]
        accepted = "Î.M. Lumteh întreține iluminatul public."
        accepted_second = "Defecțiunile se raportează pe eu.chisinau.md."
        unsupported = "Programul de lucru este non-stop."
        models = FakeModels([evidence], {"requirements": requirements}, claims=[[
            {"text": accepted, "requirementId": "R1", "evidenceIds": ["S1"]},
            {"text": accepted_second, "requirementId": "R2", "evidenceIds": ["S1"]},
            {"text": unsupported, "requirementId": "R1", "evidenceIds": ["S1"]},
        ]], rejected={unsupported})
        result = self.run_answer(models, "Cine întreține iluminatul public și unde se raportează defecțiunile?")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertEqual([item["status"] for item in result["coverage"]], ["ANSWERED", "ANSWERED"])
        self.assertEqual([claim["text"] for claim in result["claims"]], [accepted, accepted_second])


class VerificationTests(unittest.TestCase):
    EVIDENCE = {"S1": {"documentId": "a", "evidenceKind": "body", "title": "Ordin nr. 01/1-7/345 din 17.03.2026",
                       "exactQuote": "Înscrierea începe la 01.04.2026 și costă 0 lei."}}

    def test_numbers_may_come_from_the_title_or_parts_of_a_quoted_date(self) -> None:
        self.assertEqual(deterministic_issues({"text": "Ordinul nr. 01/1-7/345 stabilește începutul pe 1 April 2026.", "evidenceIds": ["S1"]}, self.EVIDENCE), [])
        self.assertEqual(deterministic_issues({"text": "Costă 50 lei.", "evidenceIds": ["S1"]}, self.EVIDENCE), ["UNSUPPORTED_NUMBER:50"])

    def test_model_checked_answer_types_extend_the_verifier_prompt(self) -> None:
        self.assertIn("a person", verifier_prompt("person"))
        self.assertEqual(verifier_prompt("hours"), verifier_prompt("other"))

    def test_financial_stage_must_be_stated_by_the_source(self) -> None:
        evidence = {"S1": {"documentId": "a", "evidenceKind": "body", "title": "Proiect",
                           "exactQuote": "Din bugetul municipal au fost alocați 370.000 lei."}}
        unsupported = deterministic_issues(
            {"text": "Au fost cheltuiți efectiv 370.000 lei.", "evidenceIds": ["S1"]}, evidence)
        self.assertIn("UNSUPPORTED_FINANCIAL_STAGE:SPENT", unsupported)
        self.assertNotIn("UNSUPPORTED_FINANCIAL_STAGE:ALLOCATED", deterministic_issues(
            {"text": "Au fost alocați 370.000 lei.", "evidenceIds": ["S1"]}, evidence))


if __name__ == "__main__":
    unittest.main()
