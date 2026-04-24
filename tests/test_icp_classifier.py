from __future__ import annotations

import unittest

from agent.icp_classifier import classify_brief


def make_brief() -> dict:
    return {
        "company": "Example Co",
        "firmographics": {"employee_count": 300},
        "funding_event": None,
        "layoff_event": None,
        "leadership_change": None,
        "ai_maturity": {"ai_maturity_score": 0},
    }


class IcpClassifierTests(unittest.TestCase):
    def test_recently_funded_startup(self) -> None:
        brief = make_brief()
        brief["funding_event"] = {
            "round": "Series A",
            "days_ago": 64,
            "confidence": "high",
        }
        brief["firmographics"]["employee_count"] = 80

        result = classify_brief(brief)
        self.assertEqual([segment["segment"] for segment in result["segments"]], ["Segment 1"])
        self.assertEqual(result["segments"][0]["confidence"], "high")

    def test_post_layoff_company_that_also_raised_money(self) -> None:
        brief = make_brief()
        brief["funding_event"] = {
            "round": "Series A",
            "days_ago": 120,
            "confidence": "high",
        }
        brief["layoff_event"] = {
            "days_ago": 90,
            "confidence": "high",
        }
        brief["firmographics"]["employee_count"] = 300

        result = classify_brief(brief)
        self.assertEqual(
            [segment["segment"] for segment in result["segments"]],
            ["Segment 1", "Segment 2"],
        )
        self.assertTrue(any("both fresh funding and post-layoff pressure" in note for note in result["notes"]))

    def test_company_with_ai_maturity_zero_blocks_segment_four(self) -> None:
        brief = make_brief()
        brief["ai_maturity"]["ai_maturity_score"] = 0

        result = classify_brief(brief)
        self.assertEqual(result["segments"], [])
        self.assertEqual(result["blocked_segments"][0]["segment"], "Segment 4")

    def test_company_with_new_cto_matches_segment_three(self) -> None:
        brief = make_brief()
        brief["leadership_change"] = {
            "title": "CTO",
            "days_ago": 78,
            "confidence": "medium",
        }

        result = classify_brief(brief)
        self.assertEqual([segment["segment"] for segment in result["segments"]], ["Segment 3"])

    def test_ambiguous_company_flags_generic_outreach(self) -> None:
        brief = make_brief()
        brief["leadership_change"] = {
            "title": "Head of Engineering",
            "days_ago": 45,
            "confidence": "low",
        }

        result = classify_brief(brief)
        self.assertEqual(result["recommendation"], "generic_outreach")
        self.assertTrue(result["generic_outreach"])


if __name__ == "__main__":
    unittest.main()
