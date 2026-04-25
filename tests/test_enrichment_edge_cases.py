from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from enrichment import build_brief, job_scraper, robots_checker


class RobotsCheckerEdgeCaseTests(unittest.TestCase):
    def test_mixed_robots_result_is_treated_as_blocked(self) -> None:
        class FakeRobotParser:
            def set_url(self, url: str) -> None:
                self.url = url

            def read(self) -> None:
                return None

            def can_fetch(self, user_agent: str, url: str) -> bool:
                return user_agent != "*"

        with patch.object(robots_checker, "RobotFileParser", FakeRobotParser):
            result = robots_checker.is_scraping_allowed("https://example.com/careers")

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["allowed"])


class JobScraperEdgeCaseTests(unittest.TestCase):
    def test_sparse_job_market_has_no_change_pct_without_baseline(self) -> None:
        self.assertIsNone(job_scraper.calc_change_pct(roles_now=1, roles_60d_ago=0))

    def test_build_master_brief_records_job_scraper_failure_context(self) -> None:
        def fake_load_module(path, module_name):
            if "crunchbase_lookup" in module_name:
                return SimpleNamespace(
                    build_result=lambda company_name: {
                        "company": company_name,
                        "website": "https://coorb.io",
                        "crunchbase_id": "coorb",
                        "last_enriched_at": "2026-04-25T00:00:00Z",
                    }
                )
            if "funding_detector" in module_name:
                return SimpleNamespace(detect_funding_event=lambda company_name: {"funding_event": None})
            if "layoffs_checker" in module_name:
                return SimpleNamespace(check_layoffs=lambda company_name: {"layoff_event": None})
            if "job_scraper" in module_name:
                return SimpleNamespace(scrape_jobs=lambda company_domain: None)
            if "leadership_detector" in module_name:
                return SimpleNamespace(detect_leadership_change=lambda company_name: {"leadership_change": None})
            if "ai_maturity_scorer" in module_name:
                return SimpleNamespace(score_company=lambda company_name: {"ai_maturity_score": 1, "signals": {}})
            if "competitor_gap" in module_name:
                return SimpleNamespace(build_brief=lambda company_name: {"target_company": company_name, "gaps": []})
            raise AssertionError(f"Unexpected module request: {module_name}")

        with patch.object(build_brief, "load_module", side_effect=fake_load_module):
            with patch.object(build_brief.asyncio, "run", side_effect=RuntimeError("playwright unavailable")):
                brief, _elapsed = build_brief.build_master_brief("CoorB")

        self.assertEqual(brief["job_posts"]["reason"], "job_scraper_failed")
        self.assertIn("playwright unavailable", brief["job_posts"]["error"])
        self.assertEqual(brief["bench_match"]["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
