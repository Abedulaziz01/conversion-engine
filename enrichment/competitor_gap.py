from __future__ import annotations

"""Build a lightweight competitor-gap brief.

The output JSON uses a stable schema:
- target_company: normalized company name used in the brief
- sector: first one or two Crunchbase industries for quick context
- size_band: employee-range label derived from Crunchbase size data
- target_ai_maturity: 0-3 AI maturity score for the target
- competitors_scored: peer list with name, AI maturity, and employee count
- target_percentile: relative standing against peers
- gaps: up to three evidence-backed adoption gaps to reference in outreach
- reason: optional explanation when the target cannot be scored normally
"""

import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "enrichment" / "output" / "competitor_gap_brief.json"
CRUNCHBASE_DATA_PATH = ROOT / "data" / "crunchbase_sample.json"
CRUNCHBASE_LOOKUP_PATH = ROOT / "enrichment" / "crunchbase_lookup.py"
AI_SCORER_PATH = ROOT / "enrichment" / "ai_maturity_scorer.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def normalize_token(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = re.sub(
        r"\b(platforms|incorporated|inc|corp|corporation|company|co|llc|ltd|limited|technologies|technology)\b",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def load_rows() -> list[dict[str, Any]]:
    return json.loads(CRUNCHBASE_DATA_PATH.read_text(encoding="utf-8"))


def employee_midpoint(raw_value: Any) -> int | None:
    if raw_value in (None, "", "null", "None"):
        return None
    text = str(raw_value).strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        low = int(match.group(1))
        high = int(match.group(2))
        return (low + high) // 2
    return None


def employee_band_label(employee_count: int | None) -> str:
    if employee_count is None:
        return "unknown"
    bands = [
        (1, 10),
        (11, 50),
        (51, 100),
        (101, 250),
        (251, 500),
        (501, 1000),
        (1001, 5000),
        (5001, 1000000),
    ]
    for low, high in bands:
        if low <= employee_count <= high:
            return f"{low}-{high} employees"
    return f"{employee_count}+ employees"


def extract_industries(row: dict[str, Any]) -> list[str]:
    industries = parse_jsonish(row.get("industries"), [])
    values: list[str] = []
    if isinstance(industries, list):
        for item in industries:
            if isinstance(item, dict):
                value = item.get("value") or item.get("id")
            else:
                value = item
            if value:
                values.append(str(value))
    return values


def load_target_row(company_name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    crunchbase_lookup = load_module(CRUNCHBASE_LOOKUP_PATH, "crunchbase_lookup_module")
    lookup_result = crunchbase_lookup.build_result(company_name)
    if lookup_result.get("found"):
        crunchbase_id = lookup_result.get("crunchbase_id")
        for row in load_rows():
            if row.get("id") == crunchbase_id:
                return row, lookup_result

    target_token = normalize_token(company_name)
    for row in load_rows():
        row_names = [str(row.get("name") or ""), str(row.get("legal_name") or ""), str(row.get("id") or "")]
        if any(normalize_token(name) == target_token for name in row_names if name):
            return row, lookup_result
    return None, lookup_result


def competitor_match_score(target_row: dict[str, Any], candidate_row: dict[str, Any]) -> float:
    target_industries = set(extract_industries(target_row))
    candidate_industries = set(extract_industries(candidate_row))
    industry_overlap = len(target_industries & candidate_industries)

    target_size = employee_midpoint(target_row.get("num_employees"))
    candidate_size = employee_midpoint(candidate_row.get("num_employees"))
    size_score = 0.0
    if target_size and candidate_size:
        ratio = candidate_size / target_size
        if 0.5 <= ratio <= 2.0:
            size_score = 1 - abs(math.log(ratio, 2)) / 1.0
            size_score = max(size_score, 0.0)
    return industry_overlap * 10 + size_score


def find_competitors(target_row: dict[str, Any]) -> list[dict[str, Any]]:
    target_id = target_row.get("id")
    target_industries = set(extract_industries(target_row))
    target_size = employee_midpoint(target_row.get("num_employees"))
    if not target_industries or target_size is None:
        return []

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in load_rows():
        if row.get("id") == target_id:
            continue
        candidate_industries = set(extract_industries(row))
        candidate_size = employee_midpoint(row.get("num_employees"))
        if not candidate_industries or candidate_size is None:
            continue
        if not (target_industries & candidate_industries):
            continue
        ratio = candidate_size / target_size
        if not (0.5 <= ratio <= 2.0):
            continue
        candidates.append((competitor_match_score(target_row, row), row))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in candidates[:10]]


def score_company_name(company_name: str) -> dict[str, Any]:
    ai_scorer = load_module(AI_SCORER_PATH, "ai_maturity_scorer_module")
    return ai_scorer.score_company(company_name)


def signal_gap_detail(signal_key: str) -> str:
    labels = {
        "ai_roles": "AI/ML hiring signal",
        "ml_leadership": "dedicated ML/AI leadership role",
        "github_activity": "public GitHub AI activity",
        "exec_commentary": "executive AI commentary",
        "ml_stack": "modern ML tooling",
        "strategic_comms": "AI in strategic or fundraising communications",
    }
    return labels.get(signal_key, signal_key)


def compute_percentile_label(scored: list[dict[str, Any]], target_name: str) -> str:
    if not scored:
        return "unknown"
    ordered = sorted(scored, key=lambda item: item["ai_maturity"], reverse=True)
    index = next((idx for idx, item in enumerate(ordered) if item["name"] == target_name), None)
    if index is None:
        return "unknown"
    percentile = (index + 1) / len(ordered)
    if percentile <= 0.25:
        return "top quartile"
    if percentile >= 0.75:
        return "bottom quartile"
    return "middle"


def build_gap_entries(
    target_score: dict[str, Any],
    top_competitors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    target_signals = target_score.get("signals", {})

    for signal_key in [
        "ml_leadership",
        "ml_stack",
        "exec_commentary",
        "github_activity",
        "ai_roles",
        "strategic_comms",
    ]:
        target_signal = target_signals.get(signal_key, {})
        if target_signal.get("found"):
            continue

        evidence_companies = []
        for competitor in top_competitors:
            signal = competitor["score"]["signals"].get(signal_key, {})
            if signal.get("found"):
                evidence_companies.append(
                    {
                        "name": competitor["name"],
                        "detail": signal.get("detail", ""),
                    }
                )

        if not evidence_companies:
            continue

        named_examples = evidence_companies[:3]
        evidence = ". ".join(
            f"{item['name']}: {item['detail']}" for item in named_examples
        )
        gaps.append(
            {
                "gap": f"No {signal_gap_detail(signal_key)}",
                "evidence": evidence,
                "target_signal": target_signal.get("detail", "Signal not found for target company"),
            }
        )
        if len(gaps) >= 3:
            break

    return gaps


def build_brief(company_name: str) -> dict[str, Any]:
    target_row, lookup_result = load_target_row(company_name)
    target_score = score_company_name(company_name)

    if target_row is None:
        result = {
            "target_company": company_name,
            "sector": None,
            "size_band": "unknown",
            "target_ai_maturity": target_score.get("ai_maturity_score", 0),
            "competitors_scored": [
                {
                    "name": company_name,
                    "ai_maturity": target_score.get("ai_maturity_score", 0),
                    "employee_count": None,
                }
            ],
            "target_percentile": "unknown",
            "gaps": [],
            "reason": "target_company_not_found_in_crunchbase_sample",
        }
        return result

    target_name = str(target_row.get("name") or lookup_result.get("company") or company_name)
    sector = ", ".join(extract_industries(target_row)[:2]) or None
    target_employee_count = employee_midpoint(target_row.get("num_employees"))

    competitors = find_competitors(target_row)
    scored_competitors = []
    for row in competitors:
        competitor_name = str(row.get("name") or row.get("id") or "Unknown")
        competitor_score = score_company_name(competitor_name)
        scored_competitors.append(
            {
                "name": competitor_name,
                "ai_maturity": competitor_score.get("ai_maturity_score", 0),
                "employee_count": employee_midpoint(row.get("num_employees")),
                "score": competitor_score,
            }
        )

    target_entry = {
        "name": target_name,
        "ai_maturity": target_score.get("ai_maturity_score", 0),
        "employee_count": target_employee_count,
        "score": target_score,
    }
    scored_competitors.append(target_entry)
    scored_competitors.sort(key=lambda item: item["ai_maturity"], reverse=True)

    top_quartile = max(1, math.ceil(len(scored_competitors) / 4))
    top_competitors = scored_competitors[:top_quartile]
    gaps = build_gap_entries(target_score, top_competitors)

    result = {
        "target_company": target_name,
        "sector": sector,
        "size_band": employee_band_label(target_employee_count),
        "target_ai_maturity": target_score.get("ai_maturity_score", 0),
        "competitors_scored": [
            {
                "name": item["name"],
                "ai_maturity": item["ai_maturity"],
                "employee_count": item["employee_count"],
            }
            for item in scored_competitors
        ],
        "target_percentile": compute_percentile_label(scored_competitors, target_name),
        "gaps": gaps,
    }
    return result


def save_result(result: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/competitor_gap.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = build_brief(company_name)
    save_result(result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
