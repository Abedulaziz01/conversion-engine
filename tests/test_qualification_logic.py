from __future__ import annotations

import unittest

from agent.bench_checker import check_bench_capacity
from agent.qualifier import qualify_reply


def make_brief() -> dict:
    return {
        "company": "Example Co",
        "firmographics": {"employee_count": 300},
        "funding_event": None,
        "layoff_event": None,
        "leadership_change": None,
        "ai_maturity": {"ai_maturity_score": 0},
    }


class QualificationLogicTests(unittest.TestCase):
    def test_interested_reply_from_segment_one(self) -> None:
        brief = make_brief()
        brief["funding_event"] = {"round": "Series A", "days_ago": 64, "confidence": "high"}

        result = qualify_reply("Interesting — yes we're looking to scale our Python team", brief)
        self.assertEqual(result["route"], "automated_qualification")
        self.assertIn("What stack are your engineers working in?", result["qualifying_questions"])
        self.assertIn("What's your target team size in the next 6 months?", result["qualifying_questions"])

    def test_hostile_reply_routes_to_handoff(self) -> None:
        brief = make_brief()
        result = qualify_reply("Remove me from your list immediately", brief, sender_email="user@example.com", trace_id="trace-1")
        self.assertEqual(result["route"], "human_handoff")
        self.assertFalse(result["automated_follow_up"])

    def test_pricing_question_routes_to_handoff(self) -> None:
        brief = make_brief()
        result = qualify_reply("What exactly does this cost for a team of 6?", brief, sender_email="user@example.com", trace_id="trace-2")
        self.assertEqual(result["route"], "human_handoff")
        self.assertFalse(result["automated_follow_up"])

    def test_bench_checker_confirms_python_capacity(self) -> None:
        result = check_bench_capacity("Python engineers", 3)
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["available"], 4)

    def test_bench_checker_blocks_unavailable_capacity(self) -> None:
        result = check_bench_capacity("Go engineers", 8)
        self.assertFalse(result["confirmed"])
        self.assertTrue(result["route_to_human_handoff"])


if __name__ == "__main__":
    unittest.main()
