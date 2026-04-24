from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "crunchbase_sample.json"
OUTPUT_PATH = ROOT / "enrichment" / "output" / "crunchbase_brief.json"


def normalize_name(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = re.sub(r"\b(incorporated|inc|corp|corporation|company|co|llc|ltd|limited)\b", "", cleaned)
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


def safe_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def employee_count_value(raw_value: Any) -> int | str | None:
    if raw_value in (None, "", "null", "None"):
        return None
    text = str(raw_value).strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        return (low + high) // 2
    return text


def extract_industry(row: dict[str, Any]) -> str | None:
    industries = parse_jsonish(row.get("industries"), [])
    if isinstance(industries, list) and industries:
        first = industries[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("id")
        return str(first)
    return None


def extract_founders(row: dict[str, Any]) -> list[str]:
    founders = parse_jsonish(row.get("founders"), [])
    results: list[str] = []
    if isinstance(founders, list):
        for founder in founders:
            if isinstance(founder, dict):
                name = founder.get("value") or founder.get("name")
            else:
                name = str(founder)
            if name:
                results.append(str(name))
    return results


def extract_city_country(row: dict[str, Any]) -> tuple[str | None, str | None]:
    location = row.get("location")
    city = None
    country = None
    location_items = parse_jsonish(location, [])
    if isinstance(location_items, list) and location_items:
        names = [
            str(item.get("name")).strip()
            for item in location_items
            if isinstance(item, dict) and item.get("name")
        ]
        if names:
            city = names[0]
            country = names[-2] if len(names) >= 2 else names[-1]
    else:
        location_text = str(location or "").strip()
        if location_text:
            parts = [part.strip() for part in location_text.split(",") if part.strip()]
            if parts:
                city = parts[0]
                country = parts[-1]

    country_code = str(row.get("country_code") or "").strip()
    country_map = {
        "US": "United States",
        "GB": "United Kingdom",
        "NL": "Netherlands",
        "CA": "Canada",
        "DE": "Germany",
        "FR": "France",
        "IN": "India",
    }
    if not country and country_code:
        country = country_map.get(country_code, country_code)
    return city, country


def extract_total_funding(row: dict[str, Any]) -> int | None:
    funds_total = parse_jsonish(row.get("funds_total"), {})
    if isinstance(funds_total, dict):
        amount = funds_total.get("value_usd") or funds_total.get("value")
        if amount is not None:
            return safe_int(amount)
    return safe_int(row.get("funds_raised"))


def extract_last_funding_date(row: dict[str, Any]) -> str | None:
    rounds = parse_jsonish(row.get("funding_rounds_list"), [])
    dates: list[str] = []
    if isinstance(rounds, list):
        for round_item in rounds:
            if isinstance(round_item, dict):
                value = str(round_item.get("announced_on") or round_item.get("date") or "").strip()
                if value:
                    dates.append(value[:10])
    return max(dates) if dates else None


def extract_funding_rounds(row: dict[str, Any]) -> int | None:
    raw = row.get("funding_rounds")
    if isinstance(raw, dict):
        count = raw.get("num_funding_rounds") or raw.get("value")
        return safe_int(count)
    return safe_int(raw)


def load_rows() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def score_match(search_term: str, candidate: str) -> float:
    normalized_search = normalize_name(search_term)
    normalized_candidate = normalize_name(candidate)
    if not normalized_candidate:
        return 0.0
    if normalized_search == normalized_candidate:
        return 1.0
    if normalized_search in normalized_candidate or normalized_candidate in normalized_search:
        return 0.96
    return SequenceMatcher(None, normalized_search, normalized_candidate).ratio()


def find_best_row(company_name: str, rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    best_row = None
    best_score = 0.0
    for row in rows:
        candidate_names = [
            str(row.get("name") or ""),
            str(row.get("legal_name") or ""),
            str(row.get("id") or ""),
        ]
        row_score = max(score_match(company_name, candidate) for candidate in candidate_names)
        if row_score > best_score:
            best_row = row
            best_score = row_score
    return best_row, best_score


def build_result(company_name: str) -> dict[str, Any]:
    rows = load_rows()
    row, score = find_best_row(company_name, rows)
    enriched_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if row is None or score < 0.74:
        return {
            "found": False,
            "company": company_name,
            "crunchbase_id": None,
            "last_enriched_at": enriched_at,
        }

    city, country = extract_city_country(row)
    result = {
        "found": True,
        "company": row.get("name") or company_name,
        "employee_count": employee_count_value(row.get("num_employees")),
        "industry": extract_industry(row),
        "city": city,
        "country": country,
        "total_funding_usd": extract_total_funding(row),
        "last_funding_date": extract_last_funding_date(row),
        "funding_rounds": extract_funding_rounds(row),
        "founders": extract_founders(row),
        "website": row.get("website"),
        "description": row.get("full_description") or row.get("about"),
        "crunchbase_id": row.get("id"),
        "match_score": round(score, 4),
        "last_enriched_at": enriched_at,
    }
    return result


def save_result(result: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/crunchbase_lookup.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = build_result(company_name)
    save_result(result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
