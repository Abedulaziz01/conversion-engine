from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BENCH_SUMMARY_PATH = ROOT / "docs" / "bench_summary.md"


def load_bench_summary() -> dict[str, int]:
    availability: dict[str, int] = {}
    if not BENCH_SUMMARY_PATH.exists():
        return availability

    for line in BENCH_SUMMARY_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"-\s*(.+?):\s*(\d+)\s*$", line.strip())
        if match:
            availability[match.group(1).strip()] = int(match.group(2))
    return availability


def normalize_technology_name(technology: str) -> str:
    text = technology.lower().strip()
    aliases = {
        "python engineers": "Python",
        "python engineer": "Python",
        "python": "Python",
        "data engineers": "Data Platform",
        "data engineer": "Data Platform",
        "data platform": "Data Platform",
        "go engineers": "Go",
        "go engineer": "Go",
        "go": "Go",
        "api": "API Integration",
        "api integration": "API Integration",
        "crm": "CRM Workflow",
        "scheduling": "Scheduling Automation",
        "ai": "AI/ML",
        "ml": "AI/ML",
        "ai/ml": "AI/ML",
        "observability": "Observability",
    }
    return aliases.get(text, technology.strip())


def check_bench_capacity(technology: str, requested_count: int) -> dict[str, Any]:
    technology_key = normalize_technology_name(technology)
    availability = load_bench_summary()
    available_count = availability.get(technology_key, 0)

    if available_count >= requested_count and requested_count > 0:
        return {
            "technology": technology_key,
            "requested": requested_count,
            "available": available_count,
            "confirmed": True,
            "route_to_human_handoff": False,
        }

    return {
        "technology": technology_key,
        "requested": requested_count,
        "available": available_count,
        "confirmed": False,
        "route_to_human_handoff": True,
        "reason": "bench_capacity_unclear_or_unavailable",
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print('Usage: python agent/bench_checker.py "Python engineers" 4')
        return 1

    technology = argv[1]
    try:
        requested_count = int(argv[2])
    except ValueError:
        print(json.dumps({"error": "Requested count must be an integer"}, indent=2))
        return 1

    result = check_bench_capacity(technology, requested_count)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
