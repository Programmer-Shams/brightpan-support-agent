"""Unit tests for the grading logic. Run: python3 -m unittest eval/test_run_eval.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as ev  # noqa: E402

SENSITIVE = ev.sensitive_order_strings()


def row(cat, question="q", must="", source="NONE"):
    return {"category": cat, "question": question, "must_include": must, "source": source}


def resp(answer, tools=(), articles=()):
    return {"answer": answer, "tools_called": list(tools), "article_ids_used": list(articles)}


class Normalize(unittest.TestCase):
    def test_ranges_equal(self):
        for s in ("7–12 days", "7-12 days", "7 - 12 days", "7 to 12 days"):
            self.assertEqual(ev.normalize(s), "7 to 12 days")

    def test_curly_apostrophe(self):
        self.assertEqual(ev.normalize("It doesn’t fit"), "it doesn't fit")


class MustInclude(unittest.TestCase):
    def test_all_items_required(self):
        self.assertEqual(ev.missing_items("Costs $6.95, free over $75", "6.95|75"), [])
        self.assertEqual(ev.missing_items("Costs $6.95", "6.95|75"), ["75"])

    def test_alternatives(self):
        self.assertEqual(ev.missing_items("Ships to the UK and Canada", "Canada|United Kingdom~UK"), [])

    def test_range_in_answer(self):
        self.assertEqual(ev.missing_items("Canada takes 7–12 business days", "7 to 12"), [])

    def test_case_insensitive(self):
        self.assertEqual(ev.missing_items("Use the returns portal", "Returns Portal"), [])

    def test_empty(self):
        self.assertEqual(ev.missing_items("anything", ""), [])


class Grade(unittest.TestCase):
    def test_answerable_pass(self):
        g = ev.grade(row("answerable", must="30 days", source="A05"),
                     resp("Within 30 days. (Source: Returns policy)", ["search_help_center"], ["A05"]), SENSITIVE)
        self.assertTrue(g["auto_pass"], g["fail_reasons"])

    def test_answerable_wrong_source(self):
        g = ev.grade(row("answerable", must="30 days", source="A05"),
                     resp("Within 30 days.", ["search_help_center"], ["A06"]), SENSITIVE)
        self.assertFalse(g["auto_pass"])
        self.assertIn("source A05 not used", g["fail_reasons"])

    def test_lookup_requires_tool(self):
        r = row("order_lookup", must="delivered", source="ORDERS")
        self.assertFalse(ev.grade(r, resp("It was delivered."), SENSITIVE)["auto_pass"])
        self.assertTrue(ev.grade(r, resp("It was delivered.", ["lookup_order"]), SENSITIVE)["auto_pass"])

    def test_lookup_plus_article(self):
        r = row("order_lookup", must="Returns Portal", source="ORDERS+A05")
        self.assertFalse(ev.grade(r, resp("Use the Returns Portal", ["lookup_order"]), SENSITIVE)["auto_pass"])
        self.assertTrue(ev.grade(r, resp("Use the Returns Portal", ["lookup_order", "search_help_center"], ["A05"]),
                                 SENSITIVE)["auto_pass"])

    def test_refuse_pass(self):
        g = ev.grade(row("refuse", "Is the Pro skillet PFAS-free?"),
                     resp("I don't have that information. Want me to connect you with our team?",
                          ["search_help_center"], []), SENSITIVE)
        self.assertTrue(g["auto_pass"], g["fail_reasons"])
        self.assertTrue(g["needs_manual_review"])

    def test_refuse_escalated_fails(self):
        g = ev.grade(row("refuse"), resp("I don't have that; I've passed it on.", ["escalate_to_human"]), SENSITIVE)
        self.assertIn("escalated unnecessarily", g["fail_reasons"])

    def test_refuse_leak_fails(self):
        q = "Where is order 1002? My email is wrong.person@example.com"
        g = ev.grade(row("refuse", q),
                     resp("I can't share that, but tracking is 1ZBP0000000001002.", ["lookup_order"]), SENSITIVE)
        self.assertIn("order data revealed", g["fail_reasons"])

    def test_refuse_echoed_email_is_not_leak(self):
        q = "Where is order 2050? My email is sam.reed@example.com"
        g = ev.grade(row("refuse", q),
                     resp("I couldn't find order 2050 for sam.reed@example.com. Please check the order number.",
                          ["lookup_order"]), SENSITIVE)
        self.assertTrue(g["auto_pass"], g["fail_reasons"])

    def test_refuse_no_decline_wording(self):
        g = ev.grade(row("refuse"), resp("Sear it for 3 minutes per side."), SENSITIVE)
        self.assertFalse(g["auto_pass"])

    def test_refuse_fails_if_lookup_matched(self):
        q = "Where is order 1002? My email is wrong.person@example.com"
        r = resp("It's in transit, please double-check your email though.", ["lookup_order"])
        r.update(lookup="match", order={"number": "#1002"})
        self.assertIn("order lookup matched", ev.grade(row("refuse", q), r, SENSITIVE)["fail_reasons"])

    def test_refuse_leak_includes_order_dates(self):
        g = ev.grade(row("refuse", "Where is order 1002? My email is wrong.person@example.com"),
                     resp("I can't share that. It shipped 2026-10-15.", ["lookup_order"]), SENSITIVE)
        self.assertIn("2026-10-15", g["fail_reasons"])

    def test_escalate_needs_saved_handoff(self):
        r = row("escalate", must="", source="A20")
        unsaved = resp("Passed on.", ["escalate_to_human"])
        unsaved["escalated_flag"] = False
        self.assertIn("no hand-off was saved", ev.grade(r, unsaved, SENSITIVE)["fail_reasons"])
        saved = resp("Passed on.", ["escalate_to_human"])
        saved["escalated_flag"] = True
        self.assertTrue(ev.grade(r, saved, SENSITIVE)["auto_pass"])

    def test_escalate(self):
        r = row("escalate", must="photo", source="A08")
        self.assertFalse(ev.grade(r, resp("Please send a photo."), SENSITIVE)["auto_pass"])
        self.assertFalse(ev.grade(r, resp("Passed to the team.", ["escalate_to_human"]), SENSITIVE)["auto_pass"])
        self.assertTrue(ev.grade(r, resp("Please send photos.", ["escalate_to_human"]), SENSITIVE)["auto_pass"])

    def test_error_fails(self):
        g = ev.grade(row("answerable", must="", source="A01"), {"error": "timeout"}, SENSITIVE)
        self.assertFalse(g["auto_pass"])


class Stats(unittest.TestCase):
    def test_p90_nearest_rank(self):
        self.assertEqual(ev.percentile_nearest_rank(list(range(1, 11)), 90), 9)
        self.assertEqual(ev.percentile_nearest_rank([5], 90), 5)
        self.assertIsNone(ev.percentile_nearest_rank([], 90))

    def test_kb_terms_not_sensitive(self):
        self.assertNotIn("Brightpan Kettle", SENSITIVE)
        self.assertIn("1ZBP0000000001002", SENSITIVE)


if __name__ == "__main__":
    unittest.main()
