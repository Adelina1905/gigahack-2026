from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from municipal_rag import guardrails


TODAY = date(2026, 9, 27)
ORDER_2026 = {"id": "S1", "documentId": "order-2026", "score": .82, "category": "education", "publisher": "chisinauedu.dgets.md",
    "publishedDate": "2026-03-18", "url": "https://chisinauedu.dgets.md/storage/orders/1773840248_scan-2025-09-16-14-36-53-916.pdf",
    "title": "Ordin nr. 01/1-7/345 din 17.03.2026 Cu privire la organizarea înscrierii copiilor în clasa I în anul de studii 2026-2027",
    "exactQuote": "Se aprobă calendarul înscrierii copiilor în clasa I pentru anul de studii 2026-2027."}
COPY_2023 = {"id": "S2", "documentId": "riscani-2023", "score": .84, "category": "education", "publisher": "detsriscani.md",
    "district": "Râșcani", "publishedDate": "2023-04-04", "url": "https://mecc.gov.md/sites/default/files/ordin_278_cl_i_2023-2024.pdf",
    "title": "Setul de acte necesare pentru înscriere este disponibil aici , inclusiv formularul de cerere care urmează a fi completat.",
    "exactQuote": "Buletinul de identitate al părintelui; certificatul de naștere al copilului."}
COPY_2022 = {"id": "S3", "documentId": "buiucani-2022", "score": .83, "category": "education", "publisher": "buiucanidets.md",
    "district": "Buiucani", "publishedDate": "2022-03-31", "url": "https://mec.gov.md/sites/default/files/lista_acte_cerere.pdf",
    "title": "Setul de acte necesare pentru înscriere este disponibil aici , de asemenea și modelul de cerere.",
    "exactQuote": "Lista actelor necesare care se anexează la cererea pentru înscrierea copiilor în clasa I."}
PARENTING = {"id": "S4", "documentId": "dgams-guide", "score": .81, "category": "healthcare", "publisher": "dgams.md",
    "publishedDate": "2024-05-02", "url": "https://dgams.md/files/Suport_informational_RO_web.pdf",
    "title": "Suport informațional_RO_(web)", "exactQuote": "Sfaturi pentru părinți despre pregătirea copilului pentru școală."}


class LanguageAndTypeTests(unittest.TestCase):
    def test_language_detection_covers_romanian_russian_and_english(self) -> None:
        self.assertEqual(guardrails.detect_language("Care este programul de lucru al DGTPCC?"), "ro")
        self.assertEqual(guardrails.detect_language("vreau sa aflu cum sa dau copilul la scoala"), "ro")
        self.assertEqual(guardrails.detect_language("Какой график работы примэрии?"), "ru")
        self.assertEqual(guardrails.detect_language("What are the working hours of the city hall?"), "en")
        self.assertEqual(guardrails.detect_language("How much did the football pitch works at the Liviu Deleanu lyceum in Chișinău cost?"), "en")
        self.assertEqual(guardrails.detect_language("Who was awarded the title of Honorary Citizen of Chișinău municipality in July 2026?"), "en")
        self.assertEqual(guardrails.detect_language("DGTPCC?", "en"), "en")
        self.assertEqual(guardrails.detect_language("DGTPCC?"), "ro")

    def test_keyword_answer_types_override_the_interpreter(self) -> None:
        self.assertEqual(guardrails.expected_answer_type("vreau sa aflu despre legislatiile cum sa dau copilul la scoala", "procedure"), "legal_act")
        self.assertEqual(guardrails.expected_answer_type("Care este programul de lucru al DGTPCC?", "other"), "hours")
        self.assertEqual(guardrails.expected_answer_type("Какой график работы?", "other"), "hours")
        self.assertEqual(guardrails.expected_answer_type("Cât costă parcarea?", "amount"), "amount")
        self.assertEqual(guardrails.expected_answer_type("Ce este?", "nonsense"), "other")

    def test_yearly_topics(self) -> None:
        self.assertTrue(guardrails.is_yearly_topic("cum sa dau copilul meu la scoala"))
        self.assertTrue(guardrails.is_yearly_topic("Înscrierea în clasa I"))
        self.assertTrue(guardrails.is_yearly_topic("Care sunt impozitele locale?"))
        self.assertFalse(guardrails.is_yearly_topic("Ce lucrări s-au făcut pe strada Vasile Alecsandri?"))
        self.assertTrue(guardrails.is_yearly_topic("Programul de burse", hint=True))


class RuleTests(unittest.TestCase):
    def constraints(self, question: str, normalized: str | None = None, **interpreted: object) -> dict[str, object]:
        return guardrails.question_constraints(question, normalized or question, interpreted)

    def test_explicit_other_year_is_a_different_period(self) -> None:
        rules = self.constraints("Cine a câștigat Campionatul Mondial de fotbal 2022?")
        event = {"title": "Vizionarea meciurilor Campionatului Mondial 2026 în Piața Marii Adunări Naționale",
                 "exactQuote": "Meciurile vor fi transmise pe ecran mare.", "publishedDate": "2026-06-10"}
        self.assertEqual(guardrails.rule_conflict(event, rules), "DIFFERENT_PERIOD")
        self.assertIsNone(guardrails.rule_conflict({**event, "title": "Rezultatele sezonului 2022"}, rules))

    def test_passage_without_years_is_judged_by_its_publication_date(self) -> None:
        rules = self.constraints("Bugetul pentru 2022")
        self.assertEqual(guardrails.rule_conflict({"title": "Anunț", "exactQuote": "Text", "publishedDate": "2025-01-01"}, rules), "DIFFERENT_PERIOD")
        self.assertIsNone(guardrails.rule_conflict({"title": "Anunț", "exactQuote": "Text", "publishedDate": "2023-01-01"}, rules))
        self.assertIsNone(guardrails.rule_conflict({"title": "Anunț", "exactQuote": "Text"}, rules))

    def test_other_street_is_a_different_entity_diacritics_insensitive(self) -> None:
        rules = self.constraints("Ce lucrări s-au făcut pe strada Vasile Alecsandri?", streets=["Vasile Alecsandri"])
        self.assertEqual(rules["streets"], ["alecsandri"])
        other = {"title": "Reparația apeductului", "exactQuote": "Lucrări pe str. Ștefan cel Mare din Stăuceni."}
        same = {"title": "Reparații", "exactQuote": "Au fost reparate trotuarele pe str. Vasile ALECSANDRI."}
        silent = {"title": "Apeduct Stăuceni", "exactQuote": "S-a construit un apeduct nou."}
        self.assertEqual(guardrails.rule_conflict(other, rules), "DIFFERENT_ENTITY")
        self.assertIsNone(guardrails.rule_conflict(same, rules))
        self.assertIsNone(guardrails.rule_conflict(silent, rules))

    def test_street_is_parsed_from_the_romanian_query_when_the_interpreter_misses_it(self) -> None:
        rules = self.constraints("Что сделали на улице Александри?", "Ce lucrări s-au făcut pe strada Vasile Alecsandri?")
        self.assertEqual(rules["streets"], ["alecsandri"])

    def test_other_sector_and_sibling_institution_are_different_entities(self) -> None:
        rules = self.constraints("Programul DETS sectorul Râșcani")
        self.assertEqual(rules["sectors"], ["rascani"])
        self.assertEqual(guardrails.rule_conflict({"title": "Program", "exactQuote": "Luni", "district": "Buiucani"}, rules), "DIFFERENT_ENTITY")
        self.assertIsNone(guardrails.rule_conflict({"title": "Program", "exactQuote": "DETS Luni", "district": "Râșcani"}, rules))
        rules = self.constraints("Care este programul de lucru al DGTPCC?")
        self.assertEqual(guardrails.rule_conflict({"title": "DGETS", "exactQuote": "Structura DGETS"}, rules), "DIFFERENT_ENTITY")
        self.assertIsNone(guardrails.rule_conflict({"title": "DGTPCC", "exactQuote": "Structura DGTPCC"}, rules))

    def test_category_mismatch_lowers_the_score_but_keeps_the_passage(self) -> None:
        rules = self.constraints("cum sa dau copilul la scoala", topicCategory="education")
        kept, dropped = guardrails.apply_rules([PARENTING, ORDER_2026], rules, .85)
        self.assertEqual(dropped, [])
        self.assertEqual([item["documentId"] for item in kept], ["order-2026", "dgams-guide"])
        self.assertTrue(kept[1]["categoryMismatch"])
        self.assertAlmostEqual(kept[1]["effectiveScore"], .81 * .85)
        generic = guardrails.apply_rules([{**PARENTING, "category": "legal_act"}], rules, .85)[0]
        self.assertFalse(generic[0]["categoryMismatch"])


class DuplicateTests(unittest.TestCase):
    def test_link_text_copies_merge_into_the_most_recent(self) -> None:
        kept, merged = guardrails.merge_duplicates([COPY_2022, COPY_2023, ORDER_2026])
        self.assertEqual(merged, 1)
        self.assertEqual([item["documentId"] for item in kept], ["riscani-2023", "order-2026"])

    def test_same_file_name_across_hosts_is_one_document(self) -> None:
        left = {"documentId": "a", "publishedDate": "2024-01-01", "title": "Anunț A", "url": "https://mec.gov.md/files/ordin_278.pdf", "exactQuote": "x"}
        right = {"documentId": "b", "publishedDate": "2025-01-01", "title": "Anunț B", "url": "https://mecc.gov.md/x/ordin_278.pdf", "exactQuote": "y"}
        kept, merged = guardrails.merge_duplicates([left, right])
        self.assertEqual(([item["documentId"] for item in kept], merged), (["b"], 1))

    def test_near_identical_quotes_merge_but_numeric_act_urls_do_not(self) -> None:
        quote = "Se aprobă regulamentul privind organizarea înscrierii copiilor în clasa întâi în instituțiile municipale"
        left = {"documentId": "a", "publishedDate": "2024-01-01", "title": "Înscrierea în clasa I", "url": "https://actelocale.gov.md/act/1/2073734", "exactQuote": quote}
        right = {"documentId": "b", "publishedDate": "2023-01-01", "title": "Înscrierea în clasa I!", "url": "https://actelocale.gov.md/act/9/2073734", "exactQuote": quote + "."}
        self.assertEqual(guardrails.merge_duplicates([left, right])[1], 1)
        other = {**right, "exactQuote": "Cu privire la acordul de amplasare pe terenul cu numărul cadastral indicat mai jos"}
        self.assertEqual(guardrails.merge_duplicates([left, other])[1], 0)

    def test_shared_boilerplate_does_not_merge_pages_about_different_places(self) -> None:
        quote = "Învelișul artificial pentru terenul de fotbal a fost pus la dispoziție de Federația Moldovenească de Fotbal"
        left = {"documentId": "a", "title": "Teren de fotbal la Liceul G. Călinescu", "exactQuote": quote}
        right = {"documentId": "b", "title": "Teren de sport LT A.I. Cuza", "exactQuote": quote}
        self.assertEqual(guardrails.merge_duplicates([left, right])[1], 0)

    def test_short_generic_titles_are_not_copies(self) -> None:
        left = {"documentId": "a", "title": "Anunț", "exactQuote": "x"}
        right = {"documentId": "b", "title": "Anunț", "exactQuote": "y"}
        self.assertEqual(guardrails.merge_duplicates([left, right])[1], 0)


class ScreenRecencyAndClarificationTests(unittest.TestCase):
    def test_screen_keeps_only_passages_marked_relevant(self) -> None:
        items = [{"id": "S1", "documentId": "a"}, {"id": "S2", "documentId": "b"}, {"id": "S3", "documentId": "c"}, {"id": "S4", "documentId": "d"}]
        kept, dropped = guardrails.apply_screen(items, [
            {"id": "S1", "relevant": True, "reason": "RELEVANT"},
            {"id": "S2", "relevant": False, "reason": "DIFFERENT_EVENT"},
            {"id": "S3", "relevant": True, "reason": "TOPIC_ONLY"}])
        self.assertEqual([item["id"] for item in kept], ["S1"])
        self.assertEqual([(item["id"], item["reason"]) for item in dropped],
                         [("S2", "DIFFERENT_EVENT"), ("S3", "TOPIC_ONLY"), ("S4", "TOPIC_ONLY")])

    def test_screen_codes_carry_subject_groups(self) -> None:
        verdicts = guardrails.screen_verdicts({"S1": "RELEVANT_A", "S2": "RELEVANT_B", "S3": "DIFFERENT_PERIOD", "S4": "RELEVANT", "_managedResponse": {}})
        self.assertEqual(verdicts, [{"id": "S1", "relevant": True, "reason": "RELEVANT", "subject": "A"},
                                    {"id": "S2", "relevant": True, "reason": "RELEVANT", "subject": "B"},
                                    {"id": "S3", "relevant": False, "reason": "DIFFERENT_PERIOD", "subject": None}])
        kept, dropped = guardrails.apply_screen([{"id": "S1"}, {"id": "S2"}, {"id": "S3"}, {"id": "S4"}], verdicts)
        self.assertEqual([(item["id"], item["subject"]) for item in kept], [("S1", "A"), ("S2", "B")])
        self.assertEqual([item["id"] for item in dropped], ["S3", "S4"])

    def test_only_distinct_subjects_are_clarified(self) -> None:
        same = [{"documentId": "a", "subject": "A", "effectiveScore": .8}, {"documentId": "b", "subject": "A", "effectiveScore": .79}]
        self.assertEqual(guardrails.clarification_documents(same, False, .88, .6), [])
        distinct = [*same, {"documentId": "c", "subject": "B", "effectiveScore": .78}]
        self.assertEqual([item["documentId"] for item in guardrails.clarification_documents(distinct, False, .88, .6)], ["a", "c"])

    def test_recent_documents_win_for_yearly_topics(self) -> None:
        kept, outdated = guardrails.apply_recency([COPY_2023, ORDER_2026], True, [], TODAY, 365)
        self.assertEqual(([item["documentId"] for item in kept], outdated), (["order-2026"], False))

    def test_only_outdated_documents_are_kept_and_marked(self) -> None:
        kept, outdated = guardrails.apply_recency([COPY_2023, {**COPY_2022, "publishedDate": None}], True, [], TODAY, 365)
        self.assertTrue(outdated)
        self.assertEqual([item["outdated"] for item in kept], [True, False])

    def test_recency_is_ignored_when_the_question_names_a_year_or_is_not_yearly(self) -> None:
        self.assertEqual(guardrails.apply_recency([COPY_2023], True, [2023], TODAY, 365), ([COPY_2023], False))
        self.assertEqual(guardrails.apply_recency([COPY_2023], False, [], TODAY, 365), ([COPY_2023], False))

    def test_clarification_needs_two_distinct_strong_documents(self) -> None:
        def item(document: str, score: float) -> dict[str, object]:
            return {"documentId": document, "effectiveScore": score}
        self.assertEqual([value["documentId"] for value in guardrails.clarification_documents(
            [item("a", .87), item("a", .86), item("b", .84), item("c", .83), item("d", .82)], False, .88, .6)], ["a", "b", "c"])
        self.assertEqual(guardrails.clarification_documents([item("a", .9), item("a", .89)], False, .88, .6), [])
        self.assertEqual(guardrails.clarification_documents([item("a", .41), item("b", .40)], False, .88, .6), [])
        self.assertEqual(guardrails.clarification_documents([item("a", .82), item("b", .64)], False, .88, .6), [])
        self.assertEqual(guardrails.clarification_documents([item("a", .9), item("b", .9)], True, .88, .6), [])



class LabelTests(unittest.TestCase):
    def test_act_label_uses_type_number_subject_publisher_and_date(self) -> None:
        label = guardrails.choice_label(ORDER_2026)
        self.assertTrue(label.startswith("Ordin nr. 01/1-7/345 — organizarea înscrierii copiilor"), label)
        self.assertTrue(label.endswith(" · chisinauedu.dgets.md · 18.03.2026"), label)
        self.assertLessEqual(len(label), 110)

    def test_link_text_title_is_replaced_by_the_file_name(self) -> None:
        self.assertEqual(guardrails.choice_label(COPY_2023), "Ordin 278 cl i 2023-2024 · detsriscani.md · 04.04.2023")
        self.assertEqual(guardrails.choice_label(COPY_2022), "Lista acte cerere · buiucanidets.md · 31.03.2022")
        self.assertEqual(guardrails.choice_label(PARENTING), "Suport informational RO web · dgams.md · 02.05.2024")

    def test_unreadable_file_name_falls_back_to_the_title_text_before_the_link(self) -> None:
        label = guardrails.choice_label({**COPY_2023, "url": "https://x.md/1773840248_scan-2025-09-16.pdf"})
        self.assertEqual(label, "Setul de acte necesare pentru înscriere este disponibil · detsriscani.md · 04.04.2023")

    def test_generic_page_title_gets_the_heading_or_quote_opening(self) -> None:
        label = guardrails.choice_label({"title": "Noutăți", "publisher": "rtec.md", "publishedDate": "2026-09-18",
                                         "exactQuote": "Abonamentul lunar pentru transportul public costă 300 de lei începând cu luna octombrie 2026."})
        self.assertEqual(label, "Noutăți: Abonamentul lunar pentru transportul public costă 300 de lei începând · rtec.md · 18.09.2026")
        label = guardrails.choice_label({"title": "Fii informat", "heading": ["Tarife noi"], "publisher": "rtec.md"})
        self.assertEqual(label, "Fii informat: Tarife noi · rtec.md")

    def test_title_starting_with_a_number_gets_a_number_label(self) -> None:
        label = guardrails.choice_label({"title": "3/1 din 2025-05-30 — Cu privire la validarea rezultatelor consultărilor publice",
                                         "publisher": "actelocale.gov.md", "publishedDate": "2025-05-30"})
        self.assertEqual(label, "Nr. 3/1 — validarea rezultatelor consultărilor publice · actelocale.gov.md · 30.05.2025")

    def test_decision_label_and_cap(self) -> None:
        label = guardrails.choice_label({"title": "Decizie nr. 5/13-5 din 2025-11-20 — Cu privire la acordul de amplasare " + "x " * 80,
                                         "publisher": "actelocale.gov.md", "publishedDate": "2025-11-20"})
        self.assertTrue(label.startswith("Decizie nr. 5/13-5 — acordul de amplasare"), label)
        self.assertLessEqual(len(label), 110)
        self.assertIn("…", label)


class CitationTests(unittest.TestCase):
    EVIDENCE = [{"id": "S1", "documentId": "a"}, {"id": "S2", "documentId": "b"}, {"id": "S3", "documentId": "c"}]

    def test_every_sentence_is_cited_and_citations_are_renumbered(self) -> None:
        text, claims, citations, dropped = guardrails.render_answer([
            {"text": "Lucrările pe str. Vasile Alecsandri au început în mai. Ele durează 3 luni.", "evidenceIds": ["S2"]},
            {"text": "Fără sursă.", "evidenceIds": ["S9"]},
            {"text": "Programul este 8:00-17:00 [S3].", "evidenceIds": ["S3", "S2"]}], self.EVIDENCE)
        self.assertEqual(text, "Lucrările pe str. Vasile Alecsandri au început în mai. [S1] Ele durează 3 luni. [S1]\n"
                               "Programul este 8:00-17:00. [S2] [S1]")
        self.assertEqual([item["id"] for item in citations], ["S1", "S2"])
        self.assertEqual([item["documentId"] for item in citations], ["b", "c"])
        self.assertEqual(claims[1]["evidenceIds"], ["S2", "S1"])
        self.assertEqual(dropped, 1)
        self.assertEqual(guardrails.uncited_segments(text, {"S1", "S2"}), [])

    def test_uncited_segments_finds_missing_and_unknown_markers(self) -> None:
        self.assertEqual(guardrails.uncited_segments("Prima. A doua. [S1]", {"S1"}), ["Prima. A doua."])
        self.assertEqual(guardrails.uncited_segments("Prima. [S4]", {"S1"}), ["Prima."])
        self.assertEqual(guardrails.uncited_segments("Fără marker", {"S1"}), ["Fără marker"])

    def test_expected_values(self) -> None:
        self.assertTrue(guardrails.has_expected_value([{"text": "Programul este luni-vineri, 8:00-17:00."}], "hours"))
        self.assertFalse(guardrails.has_expected_value([{"text": "Direcția are trei secții și un serviciu."}], "hours"))
        self.assertTrue(guardrails.has_expected_value([{"text": "Taxa este de 150 lei."}], "amount"))
        self.assertFalse(guardrails.has_expected_value([{"text": "Taxa se achită la ghișeu."}], "amount"))
        self.assertTrue(guardrails.has_expected_value([{"text": "De examinări au beneficiat 100 de cetățeni."}], "amount"))
        self.assertTrue(guardrails.has_expected_value([{"text": "Trebuie asigurate patru tone de apă."}], "amount"))
        self.assertTrue(guardrails.has_expected_value([{"text": "Înscrierea începe la 1 aprilie."}], "date"))
        self.assertTrue(guardrails.has_expected_value([{"text": "Înscrierea este reglementată de Ordinul nr. 01/1-7/345."}], "legal_act"))
        self.assertFalse(guardrails.has_expected_value([{"text": "Părinții depun cererea online."}], "legal_act"))
        self.assertTrue(guardrails.has_expected_value([{"text": "Oricare."}], "procedure"))
        cited_act = [{"text": "Părinții depun cererea online.", "evidenceIds": ["S1"]}]
        self.assertTrue(guardrails.has_expected_value(cited_act, "legal_act", [{"id": "S1", "title": ORDER_2026["title"]}]))
        self.assertFalse(guardrails.has_expected_value(cited_act, "legal_act", [{"id": "S1", "title": "Înscrierea copiilor"}]))


class ReplyTests(unittest.TestCase):
    def test_not_found_reasons(self) -> None:
        reason = guardrails.not_found_reason
        self.assertEqual(reason(in_scope=False, relevant=0, claims=0, lacks_value=False), "OUT_OF_SCOPE")
        self.assertEqual(reason(in_scope=True, relevant=0, claims=0, lacks_value=False), "NO_RELEVANT_EVIDENCE")
        self.assertEqual(reason(in_scope=True, relevant=2, claims=0, lacks_value=False), "EVIDENCE_LACKS_VALUE")
        self.assertEqual(reason(in_scope=True, relevant=2, claims=2, lacks_value=True), "EVIDENCE_LACKS_VALUE")
        self.assertEqual(reason(in_scope=True, relevant=2, claims=2, lacks_value=False), "CLAIMS_UNVERIFIED")

    def test_templates_exist_in_three_languages(self) -> None:
        for language in guardrails.LANGUAGES:
            for reason in guardrails.NOT_FOUND_REASONS:
                self.assertTrue(guardrails.not_found_answer(language, reason, "hours"))
            self.assertTrue(guardrails.clarification_question(language))
        self.assertIn("programul de lucru", guardrails.not_found_answer("ro", "EVIDENCE_LACKS_VALUE", "hours"))
        self.assertIn("working hours", guardrails.not_found_answer("en", "EVIDENCE_LACKS_VALUE", "hours"))

    def test_outdated_note_names_years_and_cites_them(self) -> None:
        note = guardrails.outdated_note("en", [{"id": "S1", "publishedDate": "2023-04-04", "outdated": True},
                                               {"id": "S2", "publishedDate": "2026-01-01", "outdated": False}])
        self.assertEqual(note, "Note: the sources found date from 2023 and may be out of date. [S1]")
        self.assertEqual(guardrails.outdated_note("ro", [{"id": "S1", "outdated": False}]), "")

    def test_flags(self) -> None:
        self.assertEqual(guardrails.build_flags(off_topic=3, duplicates=1, outdated=True, rejected=1, total=4, corrected=True),
                         ["OFF_TOPIC_DROPPED:3", "DUPLICATES_MERGED:1", "OUTDATED_SOURCES", "CLAIMS_REJECTED:1/4", "CORRECTION_ROUND"])
        self.assertEqual(guardrails.build_flags(), [])


class FollowupTests(unittest.TestCase):
    HISTORY = [{"role": "user", "content": "Ce acte trebuie pentru clasa I?"},
               {"role": "assistant", "content": guardrails.clarification_question("ro")
                + "\n- Ordin 278 cl i 2023-2024 · detsriscani.md · 04.04.2023\n- Lista acte cerere · buiucanidets.md · 31.03.2022"}]

    def test_picking_a_choice_label_rescopes_the_original_question(self) -> None:
        self.assertEqual(guardrails.clarification_followup("Lista acte cerere · buiucanidets.md · 31.03.2022", self.HISTORY),
                         ("Ce acte trebuie pentru clasa I?", "Lista acte cerere · buiucanidets.md · 31.03.2022"))
        self.assertEqual(guardrails.clarification_followup("2", self.HISTORY)[1], "Lista acte cerere · buiucanidets.md · 31.03.2022")
        self.assertEqual(guardrails.clarification_followup("ordin 278 cl i", self.HISTORY)[1],
                         "Ordin 278 cl i 2023-2024 · detsriscani.md · 04.04.2023")

    def test_other_messages_are_not_choices(self) -> None:
        self.assertIsNone(guardrails.clarification_followup("Și pentru grădiniță?", self.HISTORY))
        plain = [self.HISTORY[0], {"role": "assistant", "content": "Răspuns\n- Lista acte cerere"}]
        self.assertIsNone(guardrails.clarification_followup("Lista acte cerere", plain))
        self.assertIsNone(guardrails.clarification_followup("2", []))

    def test_recent_history_keeps_the_last_turns_trimmed(self) -> None:
        history = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}" * 400} for index in range(10)]
        recent = guardrails.recent_history(history, 3)
        self.assertEqual(len(recent), 6)
        self.assertTrue(recent[0]["content"].startswith("m4"))
        self.assertEqual(len(recent[-1]["content"]), 600)


if __name__ == "__main__":
    unittest.main()
