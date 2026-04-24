from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CRUNCHBASE_LOOKUP_PATH = ROOT / "enrichment" / "crunchbase_lookup.py"
DATA_PATH = ROOT / "data" / "crunchbase_sample.json"
RECENT_WINDOW_DAYS = 180


def load_crunchbase_lookup_module():
    spec = importlib.util.spec_from_file_location("crunchbase_lookup_module", CRUNCHBASE_LOOKUP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Crunchbase lookup module from {CRUNCHBASE_LOOKUP_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rows() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


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
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_round_name(title: str) -> str | None:
    match = re.search(r"(Series A|Series B)", title, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).title()


def extract_investors(round_item: dict[str, Any]) -> list[str]:
    investors = []
    for investor in round_item.get("lead_investors", []) or []:
        if isinstance(investor, dict) and investor.get("name"):
            investors.append(str(investor["name"]))
    return investors


def compute_confidence(date_present: bool, amount_present: bool) -> str:
    if date_present and amount_present:
        return "high"
    if date_present or amount_present:
        return "medium"
    return "low"


def find_matching_row(crunchbase_id: str | None) -> dict[str, Any] | None:
    if not crunchbase_id:
        return None
    for row in load_rows():
        if row.get("id") == crunchbase_id:
            return row
    return None


def detect_funding_event(company_name: str) -> dict[str, Any]:
    crunchbase_lookup = load_crunchbase_lookup_module()
    company_record = crunchbase_lookup.build_result(company_name)

    if not company_record.get("found"):
        return {
            "funding_event": None,
            "latest_series_a_b_round": None,
            "reason": "company_not_found",
        }

    row = find_matching_row(company_record.get("crunchbase_id"))
    if row is None:
        return {
            "funding_event": None,
            "latest_series_a_b_round": None,
            "reason": "company_row_not_found",
        }

    rounds = parse_jsonish(row.get("funding_rounds_list"), [])
    if not isinstance(rounds, list):
        return {
            "funding_event": None,
            "latest_series_a_b_round": None,
            "reason": "invalid_funding_rounds_data",
        }

    today = datetime.now(UTC).date()
    best_event = None
    latest_series_a_b_round = None

    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue

        title = str(round_item.get("title") or "")
        round_name = extract_round_name(title)
        if round_name not in {"Series A", "Series B"}:
            continue

        date_text = str(round_item.get("announced_on") or "").strip()[:10]
        if not date_text:
            continue

        try:
            announced_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_ago = (today - announced_date).days
        money = round_item.get("money_raised", {}) or {}
        amount_usd = safe_int(money.get("value_usd")) if isinstance(money, dict) else None

        event = {
            "found": True,
            "round": round_name,
            "amount_usd": amount_usd,
            "date": date_text,
            "days_ago": days_ago,
            "investors": extract_investors(round_item),
            "confidence": compute_confidence(
                date_present=True,
                amount_present=amount_usd is not None,
            ),
        }

        if latest_series_a_b_round is None or event["date"] > latest_series_a_b_round["date"]:
            latest_series_a_b_round = dict(event)

        if days_ago < 0 or days_ago > RECENT_WINDOW_DAYS:
            continue

        if best_event is None or event["date"] > best_event["date"]:
            best_event = event

    if best_event is not None:
        return {
            "funding_event": best_event,
            "latest_series_a_b_round": latest_series_a_b_round,
            "reason": None,
        }

    if latest_series_a_b_round is not None:
        return {
            "funding_event": None,
            "latest_series_a_b_round": latest_series_a_b_round,
            "reason": f"latest_series_a_b_round_is_older_than_{RECENT_WINDOW_DAYS}_days",
        }

    return {
        "funding_event": None,
        "latest_series_a_b_round": None,
        "reason": "no_series_a_or_b_round_found",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/funding_detector.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = detect_funding_event(company_name)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
