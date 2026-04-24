from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


CONFIDENCE_NUMERIC = {
    "high": 0.9,
    "medium": 0.7,
    "low": 0.5,
}


def load_brief(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_confidence_number(label: str) -> float:
    return CONFIDENCE_NUMERIC.get(label.lower(), 0.5)


def classify_segment_1(brief: dict[str, Any]) -> dict[str, Any] | None:
    funding_event = brief.get("funding_event")
    if not funding_event:
        return None

    round_name = str(funding_event.get("round") or "")
    days_ago = funding_event.get("days_ago")
    if round_name not in {"Series A", "Series B"}:
        return None
    if days_ago is None or int(days_ago) >= 180:
        return None

    confidence_label = str(funding_event.get("confidence") or "medium").lower()
    confidence_score = as_confidence_number(confidence_label)
    return {
        "segment": "Segment 1",
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "why": f"{round_name} funding event found {days_ago} days ago",
    }


def classify_segment_2(brief: dict[str, Any]) -> dict[str, Any] | None:
    layoff_event = brief.get("layoff_event")
    employee_count = ((brief.get("firmographics") or {}).get("employee_count"))
    if not layoff_event or employee_count is None:
        return None

    employee_count = int(employee_count)
    if not (200 <= employee_count <= 2000):
        return None

    confidence_label = str(layoff_event.get("confidence") or "medium").lower()
    confidence_score = as_confidence_number(confidence_label)
    return {
        "segment": "Segment 2",
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "why": f"Layoff event found and employee count {employee_count} is within 200-2000",
    }


def classify_segment_3(brief: dict[str, Any]) -> dict[str, Any] | None:
    leadership_change = brief.get("leadership_change")
    if not leadership_change:
        return None

    days_ago = leadership_change.get("days_ago")
    if days_ago is None or int(days_ago) >= 90:
        return None

    confidence_label = str(leadership_change.get("confidence") or "medium").lower()
    confidence_score = as_confidence_number(confidence_label)
    return {
        "segment": "Segment 3",
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "why": f"{leadership_change.get('title') or 'Leadership change'} found {days_ago} days ago",
    }


def classify_segment_4(brief: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ai_maturity = brief.get("ai_maturity") or {}
    ai_score = int(ai_maturity.get("ai_maturity_score", 0) or 0)
    if ai_score < 2:
        blocked = {
            "segment": "Segment 4",
            "blocked": True,
            "reason": f"AI maturity score is {ai_score}, so Segment 4 is blocked",
        }
        return None, blocked

    confidence_label = "high" if ai_score == 3 else "medium"
    confidence_score = as_confidence_number(confidence_label)
    segment = {
        "segment": "Segment 4",
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "why": f"AI maturity score is {ai_score}",
    }
    return segment, None


def classify_brief(brief: dict[str, Any]) -> dict[str, Any]:
    company = brief.get("company") or (brief.get("firmographics") or {}).get("company")
    segments: list[dict[str, Any]] = []
    blocked_segments: list[dict[str, Any]] = []
    notes: list[str] = []

    for classifier in (classify_segment_1, classify_segment_2, classify_segment_3):
        match = classifier(brief)
        if match is not None:
            segments.append(match)

    segment_4, blocked_4 = classify_segment_4(brief)
    if segment_4 is not None:
        segments.append(segment_4)
    if blocked_4 is not None:
        blocked_segments.append(blocked_4)

    matched_names = {segment["segment"] for segment in segments}
    if "Segment 1" in matched_names and "Segment 2" in matched_names:
        notes.append(
            "Segment 1 and Segment 2 both matched: the company shows both fresh funding and post-layoff pressure."
        )

    if not segments:
        recommendation = "generic_outreach"
        generic_outreach = True
    else:
        all_below_threshold = all(segment["confidence_score"] < 0.6 for segment in segments)
        generic_outreach = all_below_threshold
        recommendation = "generic_outreach" if generic_outreach else "segment_specific_pitch"
        if all_below_threshold:
            notes.append("All matched segment confidences are below 0.6, so generic outreach is safer.")

    return {
        "company": company,
        "segments": segments,
        "blocked_segments": blocked_segments,
        "generic_outreach": generic_outreach,
        "recommendation": recommendation,
        "notes": notes,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python agent/icp_classifier.py "enrichment/output/hiring_signal_brief.json"')
        return 1

    brief_path = Path(argv[1]).resolve()
    if not brief_path.exists():
        print(json.dumps({"error": f"File not found: {brief_path}"}, indent=2))
        return 1

    result = classify_brief(load_brief(brief_path))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
