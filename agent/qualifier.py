from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.bench_checker import check_bench_capacity
from agent.human_handoff import handoff_to_human
from agent.icp_classifier import classify_brief


def detect_intent(reply_text: str) -> str:
    text = reply_text.lower()
    hostile_patterns = [
        "remove me",
        "stop emailing",
        "unsubscribe",
        "leave me alone",
        "immediately",
    ]
    dismissive_patterns = [
        "not interested",
        "no thanks",
        "pass",
        "not a fit",
    ]
    interested_patterns = [
        "interested",
        "yes",
        "let's talk",
        "we're looking",
        "we are looking",
        "looking to scale",
        "book",
        "call",
    ]

    if any(pattern in text for pattern in hostile_patterns):
        return "hostile"
    if any(pattern in text for pattern in dismissive_patterns):
        return "dismissive"
    if any(pattern in text for pattern in interested_patterns):
        return "interested"
    return "neutral"


def asks_for_pricing_beyond_public_tier(reply_text: str) -> bool:
    text = reply_text.lower()
    pricing_markers = ["pricing", "price", "how much", "quote", "rate", "cost"]
    quantity_markers = ["team of", "engineers", "developer", "developers", "headcount", "capacity", "for 6", "for 8", "for 10"]
    return any(marker in text for marker in pricing_markers) and any(marker in text for marker in quantity_markers)


def extract_capacity_request(reply_text: str) -> tuple[str | None, int | None]:
    text = reply_text.lower()
    count_match = re.search(r"\b(\d+)\b", text)
    requested_count = int(count_match.group(1)) if count_match else None

    technology_map = {
        "python": "Python engineers",
        "data": "Data Platform",
        "api": "API Integration",
        "crm": "CRM Workflow",
        "scheduling": "Scheduling Automation",
        "ai": "AI/ML",
        "ml": "AI/ML",
        "go": "Go engineers",
    }
    for token, technology in technology_map.items():
        if token in text and requested_count is not None:
            return technology, requested_count
    return None, None


def segment_questions(segment_name: str) -> list[str]:
    mapping = {
        "Segment 1": [
            "What stack are your engineers working in?",
            "What's your target team size in the next 6 months?",
        ],
        "Segment 2": [
            "What roles are you looking to transition to an offshore model first?",
        ],
        "Segment 3": [
            "What's on your 90-day roadmap that needs more engineering capacity?",
        ],
        "Segment 4": [
            "What's the specific capability you're trying to build — is this a migration, greenfield, or augmentation?",
        ],
    }
    return mapping.get(segment_name, [])


def qualify_reply(
    reply_text: str | dict[str, Any],
    hiring_signal_brief: dict[str, Any] | None = None,
    *,
    sender_email: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    if isinstance(reply_text, dict):
        reply_event = reply_text
        body_text = str(reply_event.get("body_text") or "")
        sender_email = sender_email or reply_event.get("sender_email")
        trace_id = trace_id or reply_event.get("trace_id")
        hiring_signal_brief = hiring_signal_brief or reply_event.get("hiring_signal_brief")
    else:
        body_text = str(reply_text)

    brief = hiring_signal_brief or {}
    classification = classify_brief(brief) if brief else {"segments": [], "generic_outreach": True}
    intent = detect_intent(body_text)
    company = brief.get("company") if isinstance(brief, dict) else None

    if intent in {"hostile", "dismissive"}:
        handoff = handoff_to_human(
            f"{intent}_reply",
            sender_email=sender_email,
            trace_id=trace_id,
            company=company,
        )
        return {
            "intent": intent,
            "route": "human_handoff",
            "handoff": handoff,
            "automated_follow_up": False,
        }

    if asks_for_pricing_beyond_public_tier(body_text):
        handoff = handoff_to_human(
            "pricing_question_beyond_public_tier",
            sender_email=sender_email,
            trace_id=trace_id,
            company=company,
        )
        return {
            "intent": intent,
            "route": "human_handoff",
            "handoff": handoff,
            "automated_follow_up": False,
        }

    technology, requested_count = extract_capacity_request(body_text)
    bench_result = None
    if technology and requested_count:
        bench_result = check_bench_capacity(technology, requested_count)
        if not bench_result.get("confirmed"):
            handoff = handoff_to_human(
                "bench_capacity_unclear",
                sender_email=sender_email,
                trace_id=trace_id,
                company=company,
            )
            return {
                "intent": intent,
                "route": "human_handoff",
                "handoff": handoff,
                "bench_check": bench_result,
                "automated_follow_up": False,
            }

    segment_names = [segment["segment"] for segment in classification.get("segments", [])]
    questions: list[str] = []
    for segment_name in segment_names:
        for question in segment_questions(segment_name):
            if question not in questions:
                questions.append(question)

    if not questions and classification.get("generic_outreach"):
        questions = ["Would it be useful to understand what type of delivery support would be most helpful right now?"]

    return {
        "intent": intent,
        "route": "automated_qualification",
        "segments": segment_names,
        "qualifying_questions": questions,
        "bench_check": bench_result,
        "automated_follow_up": True,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print('Usage: python agent/qualifier.py "reply text" "path/to/hiring_signal_brief.json"')
        return 1

    reply_text = argv[1]
    brief_path = Path(argv[2]).resolve()
    if not brief_path.exists():
        print(json.dumps({"error": f"Brief not found: {brief_path}"}, indent=2))
        return 1

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    result = qualify_reply(reply_text, brief)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
