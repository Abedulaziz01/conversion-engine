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
CRUNCHBASE_DATA_PATH = ROOT / "data" / "crunchbase_sample.json"
RECENT_WINDOW_DAYS = 90
TARGET_TITLES = [
    "cto",
    "vp engineering",
    "vp of engineering",
    "chief technology",
    "head of engineering",
]


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


def find_company_row(company_name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    crunchbase_lookup = load_module(CRUNCHBASE_LOOKUP_PATH, "crunchbase_lookup_module")
    lookup_result = crunchbase_lookup.build_result(company_name)

    if lookup_result.get("found"):
        crunchbase_id = lookup_result.get("crunchbase_id")
        for row in load_rows():
            if row.get("id") == crunchbase_id:
                return row, lookup_result

    token = normalize_token(company_name)
    for row in load_rows():
        candidate_names = [
            str(row.get("name") or ""),
            str(row.get("legal_name") or ""),
            str(row.get("id") or ""),
        ]
        if any(normalize_token(name) == token for name in candidate_names if name):
            return row, lookup_result

    return None, lookup_result


def extract_title(label: str) -> str | None:
    label_lower = label.lower()
    for title in TARGET_TITLES:
        if title in label_lower:
            if title == "cto":
                return "CTO"
            if title == "vp engineering":
                return "VP Engineering"
            if title == "vp of engineering":
                return "VP of Engineering"
            if title == "chief technology":
                return "Chief Technology Officer"
            if title == "head of engineering":
                return "Head of Engineering"
    return None


def extract_name(label: str, title: str | None) -> str | None:
    patterns = [
        r"appoints\s+(.+?)\s+as\s+",
        r"names\s+(.+?)\s+as\s+",
        r"welcomes\s+(.+?)\s+as\s+",
        r"announces\s+(.+?)\s+as\s+",
        r"joins\s+.+?\s+as\s+",
    ]
    for pattern in patterns:
        match = re.search(pattern, label, flags=re.IGNORECASE)
        if match and match.groups():
            return match.group(1).strip(" ,.-")

    if title:
        match = re.search(rf"(.+?)\s+{re.escape(title)}", label, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" ,.-")
            words = candidate.split()
            if 1 <= len(words) <= 5:
                return candidate
    return None


def build_change(event: dict[str, Any], days_ago: int, title: str, label: str) -> dict[str, Any]:
    person_name = extract_name(label, title)
    confidence = "medium" if person_name else "low"
    return {
        "found": True,
        "name": person_name,
        "title": title,
        "appointed_date": str(event.get("key_event_date") or "")[:10],
        "days_ago": days_ago,
        "confidence": confidence,
        "source": "crunchbase",
    }


def detect_leadership_change(company_name: str) -> dict[str, Any]:
    row, _ = find_company_row(company_name)
    if row is None:
        return {"leadership_change": None}

    events = parse_jsonish(row.get("leadership_hire"), [])
    if not isinstance(events, list) or not events:
        return {"leadership_change": None}

    today = datetime.now(UTC).date()
    for event in events:
        if not isinstance(event, dict):
            continue

        label = str(event.get("label") or "").strip()
        title = extract_title(label)
        if not title:
            continue

        date_text = str(event.get("key_event_date") or "").strip()[:10]
        if not date_text:
            continue

        try:
            event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_ago = (today - event_date).days
        if days_ago < 0 or days_ago > RECENT_WINDOW_DAYS:
            continue

        return {"leadership_change": build_change(event, days_ago, title, label)}

    return {"leadership_change": None}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/leadership_detector.py "Company Name"')
        return 1

    company_name = argv[1].strip()
    if not company_name:
        print("Company name cannot be empty.")
        return 1

    result = detect_leadership_change(company_name)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
