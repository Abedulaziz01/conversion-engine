from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "enrichment" / "output" / "hiring_signal_brief.json"
BENCH_SUMMARY_PATH = ROOT / "docs" / "bench_summary.md"

MODULE_PATHS = {
    "crunchbase_lookup": ROOT / "enrichment" / "crunchbase_lookup.py",
    "funding_detector": ROOT / "enrichment" / "funding_detector.py",
    "layoffs_checker": ROOT / "enrichment" / "layoffs_checker.py",
    "job_scraper": ROOT / "enrichment" / "job_scraper.py",
    "leadership_detector": ROOT / "enrichment" / "leadership_detector.py",
    "ai_maturity_scorer": ROOT / "enrichment" / "ai_maturity_scorer.py",
    "competitor_gap": ROOT / "enrichment" / "competitor_gap.py",
}


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def employee_midpoint(raw_value: Any) -> int | None:
    if raw_value in (None, "", "null", "None"):
        return None
    text = str(raw_value).strip()
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        return (int(match.group(1)) + int(match.group(2))) // 2
    if text.isdigit():
        return int(text)
    return None


def extract_domain(website: str | None) -> str | None:
    if not website:
        return None
    value = str(website).strip()
    value = re.sub(r"^https?://", "", value)
    return value.strip("/").lower() or None


def load_bench_skills() -> dict[str, int]:
    skills: dict[str, int] = {}
    if not BENCH_SUMMARY_PATH.exists():
        return skills

    for line in BENCH_SUMMARY_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"-\s*(.+?):\s*(\d+)\s*$", line.strip())
        if match:
            skills[match.group(1)] = int(match.group(2))
    return skills


def infer_available_skills(job_posts: dict[str, Any], ai_maturity: dict[str, Any]) -> dict[str, int]:
    role_titles = [str(title) for title in job_posts.get("role_titles", [])]
    text = " ".join(role_titles).lower()

    skills = {
        "Python": text.count("python"),
        "Data Platform": sum(text.count(token) for token in ["data", "platform", "pipeline"]),
        "API Integration": sum(text.count(token) for token in ["api", "integration", "backend"]),
        "CRM Workflow": sum(text.count(token) for token in ["crm", "salesforce", "hubspot"]),
        "Scheduling Automation": sum(text.count(token) for token in ["calendar", "scheduling", "operations"]),
        "AI/ML": sum(text.count(token) for token in ["ai", "ml", "machine learning", "llm"]),
        "Observability": sum(text.count(token) for token in ["observability", "monitoring", "telemetry"]),
    }

    signals = ai_maturity.get("signals", {})
    if signals.get("ml_stack", {}).get("found"):
        skills["AI/ML"] = max(skills["AI/ML"], 2)
    if signals.get("exec_commentary", {}).get("found"):
        skills["Data Platform"] = max(skills["Data Platform"], 1)
    return skills


def build_bench_match(job_posts: dict[str, Any], ai_maturity: dict[str, Any]) -> dict[str, Any]:
    needed_skills = load_bench_skills()
    available_skills = infer_available_skills(job_posts, ai_maturity)

    matched = []
    for skill, needed_count in needed_skills.items():
        if available_skills.get(skill, 0) > 0:
            matched.append(skill)

    available_labels = [
        f"{skill} x{count}" for skill, count in available_skills.items() if count > 0
    ]

    matched_ratio = (len(matched) / len(needed_skills)) if needed_skills else 0.0
    confidence = "high" if matched_ratio >= 0.5 else "medium" if matched_ratio > 0 else "low"

    return {
        "matched": bool(matched),
        "needed_skills": [f"{skill} x{count}" for skill, count in needed_skills.items()],
        "available_skills": available_labels,
        "confidence": confidence,
    }


def derive_icp_segments(
    funding: dict[str, Any],
    layoffs: dict[str, Any],
    leadership: dict[str, Any],
    ai_maturity: dict[str, Any],
    firmographics: dict[str, Any],
) -> list[str]:
    segments: list[str] = []
    employee_count = employee_midpoint(firmographics.get("employee_count"))

    if funding.get("funding_event"):
        segments.append("Segment 1")

    if layoffs.get("layoff_event") and employee_count is not None and 200 <= employee_count <= 2000:
        segments.append("Segment 2")

    if leadership.get("leadership_change"):
        segments.append("Segment 3")

    if int(ai_maturity.get("ai_maturity_score", 0) or 0) >= 2:
        segments.append("Segment 4")

    return segments


def save_result(result: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def build_master_brief(company_name: str) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()

    crunchbase_lookup = load_module(MODULE_PATHS["crunchbase_lookup"], "crunchbase_lookup_module")
    funding_detector = load_module(MODULE_PATHS["funding_detector"], "funding_detector_module")
    layoffs_checker = load_module(MODULE_PATHS["layoffs_checker"], "layoffs_checker_module")
    job_scraper = load_module(MODULE_PATHS["job_scraper"], "job_scraper_module")
    leadership_detector = load_module(MODULE_PATHS["leadership_detector"], "leadership_detector_module")
    ai_maturity_scorer = load_module(MODULE_PATHS["ai_maturity_scorer"], "ai_maturity_scorer_module")
    competitor_gap = load_module(MODULE_PATHS["competitor_gap"], "competitor_gap_module")

    firmographics = crunchbase_lookup.build_result(company_name)
    funding = funding_detector.detect_funding_event(company_name)
    layoffs = layoffs_checker.check_layoffs(company_name)
    leadership = leadership_detector.detect_leadership_change(company_name)
    ai_maturity = ai_maturity_scorer.score_company(company_name)
    competitor_brief = competitor_gap.build_brief(company_name)

    company_domain = extract_domain(firmographics.get("website"))
    if company_domain:
        job_posts = asyncio.run(job_scraper.scrape_jobs(company_domain))
    else:
        job_posts = {
            "company_domain": None,
            "roles_now": 0,
            "roles_60d_ago": 0,
            "change_pct": None,
            "engineering_roles_now": 0,
            "role_titles": [],
            "scrape_timestamp": None,
            "robots_respected": True,
            "reason": "no_company_domain_available",
        }

    bench_match = build_bench_match(job_posts, ai_maturity)
    icp_segments = derive_icp_segments(funding, layoffs, leadership, ai_maturity, firmographics)

    result = {
        "company": firmographics.get("company") or company_name,
        "crunchbase_id": firmographics.get("crunchbase_id"),
        "enriched_at": firmographics.get("last_enriched_at"),
        "firmographics": firmographics,
        "funding_event": funding.get("funding_event"),
        "layoff_event": layoffs.get("layoff_event"),
        "job_posts": job_posts,
        "leadership_change": leadership.get("leadership_change"),
        "ai_maturity": ai_maturity,
        "competitor_gap": competitor_brief,
        "icp_segments": icp_segments,
        "bench_match": bench_match,
    }

    save_result(result)
    elapsed = time.perf_counter() - start
    return result, elapsed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/build_brief.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result, elapsed = build_master_brief(company_name)
    print(json.dumps(result, indent=2))
    print(f"Total time: {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
