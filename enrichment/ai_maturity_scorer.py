from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CRUNCHBASE_LOOKUP_PATH = ROOT / "enrichment" / "crunchbase_lookup.py"
JOB_SCRAPER_PATH = ROOT / "enrichment" / "job_scraper.py"
SNAPSHOT_PATH = ROOT / "data" / "job_posts_snapshot.json"
CRUNCHBASE_DATA_PATH = ROOT / "data" / "crunchbase_sample.json"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_token(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split("/")[0]
    cleaned = cleaned.split(".")[0]
    cleaned = re.sub(
        r"\b(platforms|incorporated|inc|corp|corporation|company|co|llc|ltd|limited|technologies|technology)\b",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_jsonish(value: Any, default: Any) -> Any:
    if value in (None, "", "null", "None"):
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def contains_keyword(text: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def load_crunchbase_row(company_name: str, crunchbase_id: str | None) -> dict[str, Any] | None:
    if not crunchbase_id:
        return None
    rows = json.loads(CRUNCHBASE_DATA_PATH.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("id") == crunchbase_id:
            return row
    company_token = normalize_token(company_name)
    for row in rows:
        if normalize_token(str(row.get("name") or "")) == company_token:
            return row
    return None


def extract_domain(website: str | None) -> str | None:
    if not website:
        return None
    value = website if website.startswith(("http://", "https://")) else f"https://{website}"
    parsed = urlparse(value)
    domain = parsed.netloc or parsed.path
    return domain.lower().strip("/") or None


def score_to_int(total: float) -> int:
    # Bands map weighted evidence into the 0-3 brief score used downstream:
    # 0 = no credible AI adoption signal
    # 1 = isolated or weak AI evidence worth monitoring
    # 2 = multiple AI signals that justify AI-oriented outreach
    # 3 = strong AI maturity where AI capacity is likely strategic
    if total < 0.75:
        return 0
    if total < 1.75:
        return 1
    if total < 2.5:
        return 2
    return 3


def assess_confidence(found_count: int) -> str:
    if found_count >= 3:
        return "high"
    if found_count >= 1:
        return "medium"
    return "low"


def default_signal(weight: str, detail: str) -> dict[str, Any]:
    return {
        "found": False,
        "detail": detail,
        "contribution": 0.0,
        "weight": weight,
    }


def score_ai_roles(company_name: str, crunchbase_record: dict[str, Any]) -> dict[str, Any]:
    website = crunchbase_record.get("website")
    domain = extract_domain(str(website)) if website else None
    if domain is None:
        return default_signal("high", "No website domain in Crunchbase record, so job-post signal is unavailable")

    job_scraper = load_module(JOB_SCRAPER_PATH, "job_scraper_module")
    try:
        scrape_result = asyncio.run(job_scraper.scrape_jobs(domain))
    except Exception as exc:
        return default_signal("high", f"Job scraper unavailable: {exc}")

    if scrape_result.get("scraping_blocked"):
        return default_signal("high", f"Robots.txt blocked scraping for {domain}")
    if scrape_result.get("missing_dependency"):
        return default_signal("high", str(scrape_result.get("error")))

    roles_now = int(scrape_result.get("roles_now") or 0)
    engineering_roles = int(scrape_result.get("engineering_roles_now") or 0)
    titles = scrape_result.get("role_titles") or []
    ai_ml_count = 0
    for title in titles:
        title_lower = str(title).lower()
        if any(token in title_lower for token in ["ai", "ml", "machine learning", "data scientist", "research scientist", "llm"]):
            ai_ml_count += 1

    if engineering_roles <= 0:
        return default_signal("high", f"No engineering roles found for {domain}")

    ratio = ai_ml_count / engineering_roles
    contribution = min(1.0, round(ratio, 2))
    if ai_ml_count <= 0:
        return default_signal(
            "high",
            f"Found {engineering_roles} engineering roles but no explicit AI/ML titles",
        )

    return {
        "found": True,
        "detail": f"{ai_ml_count} of {engineering_roles} engineering roles are AI/ML",
        "contribution": contribution,
        "weight": "high",
    }


def score_ml_leadership(row: dict[str, Any]) -> dict[str, Any]:
    ai_titles = [
        "head of ai",
        "vp data",
        "chief scientist",
        "chief science officer",
        "chief ai officer",
        "head of machine learning",
        "head of data science",
    ]
    candidate_sources = [
        row.get("leadership_hire"),
        row.get("people_highlights"),
        row.get("full_description"),
        row.get("about"),
    ]
    combined = " ".join(str(source or "") for source in candidate_sources).lower()
    for title in ai_titles:
        if title in combined:
            return {
                "found": True,
                "detail": f"Detected leadership signal containing '{title}'",
                "contribution": 1.0,
                "weight": "high",
            }
    return default_signal("high", "No named AI/ML leader found in available Crunchbase people data")


def score_github_activity(row: dict[str, Any]) -> dict[str, Any]:
    social_links = parse_jsonish(row.get("social_media_links"), [])
    github_links = [link for link in social_links if isinstance(link, str) and "github.com" in link.lower()]
    if not github_links:
        return default_signal("medium", "No GitHub organization URL found in Crunchbase social links")
    return {
        "found": True,
        "detail": f"GitHub organization link found: {github_links[0]}",
        "contribution": 0.25,
        "weight": "medium",
    }


def score_exec_commentary(row: dict[str, Any]) -> dict[str, Any]:
    commentary_sources = [
        row.get("news"),
        row.get("about"),
        row.get("full_description"),
    ]
    combined = " ".join(str(source or "") for source in commentary_sources).lower()
    keywords = ["artificial intelligence", "machine learning", "generative ai", "data science", "deep learning"]
    for keyword in keywords:
        if contains_keyword(combined, keyword):
            return {
                "found": True,
                "detail": f"Executive or company commentary references '{keyword}'",
                "contribution": 0.5,
                "weight": "medium",
            }
    return default_signal("medium", "No executive AI commentary found in Crunchbase descriptions or press mentions")


def score_ml_stack(row: dict[str, Any]) -> dict[str, Any]:
    tools = parse_jsonish(row.get("builtwith_tech"), [])
    modern_ml_tools = []
    keywords = {
        "pytorch",
        "tensorflow",
        "hugging face",
        "databricks",
        "mlflow",
        "openai",
        "anthropic",
        "vertex ai",
        "sagemaker",
        "langchain",
        "weights & biases",
        "wappalyzer",
    }
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").lower()
        if any(keyword in name for keyword in keywords):
            modern_ml_tools.append(str(tool.get("name")))

    if not modern_ml_tools:
        return default_signal("low", "No modern ML stack tools detected in BuiltWith data")

    return {
        "found": True,
        "detail": f"Detected ML stack tools: {', '.join(modern_ml_tools[:3])}",
        "contribution": 0.25,
        "weight": "low",
    }


def score_strategic_comms(row: dict[str, Any]) -> dict[str, Any]:
    funding_sources = [
        row.get("news"),
        row.get("funding_rounds_list"),
        row.get("about"),
        row.get("full_description"),
    ]
    combined = " ".join(str(source or "") for source in funding_sources).lower()
    keywords = ["ai", "artificial intelligence", "machine learning", "deep learning", "foundation model"]
    for keyword in keywords:
        if contains_keyword(combined, keyword):
            return {
                "found": True,
                "detail": f"AI language appears in fundraising or company communications via '{keyword}'",
                "contribution": 0.25,
                "weight": "low",
            }
    return default_signal("low", "No AI messaging found in fundraising or strategic communications")


def score_company(company_name: str) -> dict[str, Any]:
    crunchbase_lookup = load_module(CRUNCHBASE_LOOKUP_PATH, "crunchbase_lookup_module")
    crunchbase_record = crunchbase_lookup.build_result(company_name)
    row = load_crunchbase_row(company_name, crunchbase_record.get("crunchbase_id"))

    if not crunchbase_record.get("found") or row is None:
        signals = {
            "ai_roles": default_signal("high", "Company not found in available Crunchbase data"),
            "ml_leadership": default_signal("high", "Company not found in available Crunchbase data"),
            "github_activity": default_signal("medium", "Company not found in available Crunchbase data"),
            "exec_commentary": default_signal("medium", "Company not found in available Crunchbase data"),
            "ml_stack": default_signal("low", "Company not found in available Crunchbase data"),
            "strategic_comms": default_signal("low", "Company not found in available Crunchbase data"),
        }
        return {
            "company": company_name,
            "ai_maturity_score": 0,
            "confidence": "low",
            "signals": signals,
        }

    signals = {
        "ai_roles": score_ai_roles(company_name, crunchbase_record),
        "ml_leadership": score_ml_leadership(row),
        "github_activity": score_github_activity(row),
        "exec_commentary": score_exec_commentary(row),
        "ml_stack": score_ml_stack(row),
        "strategic_comms": score_strategic_comms(row),
    }
    total = round(sum(float(signal["contribution"]) for signal in signals.values()), 2)
    found_count = sum(1 for signal in signals.values() if signal["found"])

    return {
        "company": crunchbase_record.get("company") or company_name,
        "ai_maturity_score": score_to_int(total),
        "confidence": assess_confidence(found_count),
        "total_contribution": total,
        "signals": signals,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/ai_maturity_scorer.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = score_company(company_name)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
