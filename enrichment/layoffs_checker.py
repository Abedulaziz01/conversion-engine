from __future__ import annotations

import csv
import json
import re
import sys
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "layoffs.csv"
RECENT_WINDOW_DAYS = 120


def normalize_name(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = re.sub(r"_\d+$", "", cleaned)
    cleaned = re.sub(
        r"\b(platforms|incorporated|inc|corp|corporation|company|co|llc|ltd|limited)\b",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def score_match(search_term: str, candidate: str) -> float:
    normalized_search = normalize_name(search_term)
    normalized_candidate = normalize_name(candidate)
    if not normalized_search or not normalized_candidate:
        return 0.0
    if normalized_search == normalized_candidate:
        return 1.0
    if normalized_search in normalized_candidate or normalized_candidate in normalized_search:
        return 0.96
    return SequenceMatcher(None, normalized_search, normalized_candidate).ratio()


def safe_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_rows() -> list[dict[str, Any]]:
    with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_layoff_event(row: dict[str, Any], days_ago: int) -> dict[str, Any]:
    percentage = str(row.get("percentage") or "").strip()
    if percentage and not percentage.endswith("%"):
        percentage = f"{percentage}%"

    return {
        "found": True,
        "date": str(row.get("date") or "")[:10],
        "days_ago": days_ago,
        "headcount_cut": safe_int(row.get("layoffs")),
        "percentage_cut": percentage or None,
        "source_url": row.get("source"),
        "confidence": "high",
    }


def check_layoffs(company_name: str) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    best_match = None
    best_score = 0.0
    latest_match_event = None

    for row in load_rows():
        candidate = str(row.get("company") or "")
        score = score_match(company_name, candidate)
        if score < 0.74:
            continue

        date_text = str(row.get("date") or "").strip()[:10]
        try:
            event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_ago = (today - event_date).days
        if days_ago < 0:
            continue

        event = build_layoff_event(row, days_ago)
        if latest_match_event is None or event["date"] > latest_match_event["date"]:
            latest_match_event = event

        if days_ago > RECENT_WINDOW_DAYS:
            if score > best_score:
                best_score = score
            continue

        if best_match is None or score > best_score or (
            score == best_score and event["date"] > best_match["date"]
        ):
            best_match = event
            best_score = score

    if best_match is not None:
        return {
            "layoff_event": best_match,
            "latest_matching_layoff": latest_match_event,
            "reason": None,
        }

    if latest_match_event is not None:
        return {
            "layoff_event": None,
            "latest_matching_layoff": latest_match_event,
            "reason": f"latest_matching_layoff_is_older_than_{RECENT_WINDOW_DAYS}_days",
        }

    return {
        "layoff_event": None,
        "latest_matching_layoff": None,
        "reason": "company_not_found_in_layoffs_data",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/layoffs_checker.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = check_layoffs(company_name)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
