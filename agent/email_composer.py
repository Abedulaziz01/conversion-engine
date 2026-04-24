from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.icp_classifier import classify_brief

BRIEF_PATH = ROOT / "enrichment" / "output" / "hiring_signal_brief.json"
TEMPLATE_DIR = ROOT / "docs" / "email_templates"


SEGMENT_TEMPLATE_MAP = {
    "Segment 1": "segment_1.txt",
    "Segment 2": "segment_2.txt",
    "Segment 3": "segment_3.txt",
    "Segment 4": "segment_4.txt",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_template(template_name: str) -> str:
    return (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")


def ensure_truth(condition: bool, error: str) -> None:
    if not condition:
        raise ValueError(error)


def build_job_signal_line(brief: dict[str, Any]) -> str:
    job_posts = brief.get("job_posts") or {}
    roles_now = int(job_posts.get("roles_now") or 0)
    change_pct = job_posts.get("change_pct")

    if roles_now < 5:
        return "Are you finding it difficult to add engineering capacity quickly enough right now?"

    ensure_truth(change_pct is not None, "Cannot mention job-post growth without a matching change_pct field")
    return f"We also noticed a {change_pct}% change in visible role volume based on the current public job-post snapshot."


def build_ai_signal_line(brief: dict[str, Any]) -> str:
    ai_maturity = brief.get("ai_maturity") or {}
    confidence = str(ai_maturity.get("confidence") or "low").lower()
    if confidence == "low":
        return "I may be missing context, but are AI or data-platform priorities becoming more important for the team this year?"

    signals = ai_maturity.get("signals") or {}
    positive = [
        signal["detail"]
        for signal in signals.values()
        if isinstance(signal, dict) and signal.get("found")
    ]
    if not positive:
        return "I may be missing context, but are AI or data-platform priorities becoming more important for the team this year?"
    return positive[0]


def build_competitor_line(brief: dict[str, Any]) -> str:
    competitor_gap = brief.get("competitor_gap") or {}
    gaps = competitor_gap.get("gaps") or []
    if not gaps:
        return ""
    first_gap = gaps[0]
    return f"For example, {first_gap.get('evidence')}"


def build_funding_tension_line(brief: dict[str, Any], classification: dict[str, Any]) -> str:
    segments = {segment["segment"] for segment in classification.get("segments", [])}
    if "Segment 1" in segments and "Segment 2" in segments:
        funding_event = brief.get("funding_event") or {}
        round_name = funding_event.get("round")
        return f"Interestingly, the same company also shows a recent {round_name}, which suggests growth pressure and efficiency pressure are happening at the same time."
    return ""


def build_leadership_line(brief: dict[str, Any]) -> str:
    leadership = brief.get("leadership_change") or {}
    if not leadership:
        return "That kind of transition often comes with a fresh review of delivery assumptions."
    title = leadership.get("title") or "engineering leader"
    days_ago = leadership.get("days_ago")
    return f"The public signal suggests a new {title} came in about {days_ago} days ago."


def build_generic_context_line(brief: dict[str, Any]) -> str:
    firmographics = brief.get("firmographics") or {}
    industry = firmographics.get("industry")
    if industry:
        return f"You look to be operating in {industry}, where execution bottlenecks often show up before teams want to talk about them."
    return "I do not want to assume too much from limited public data, so I will keep this simple."


def select_segment(classification: dict[str, Any], requested_segment: str | None) -> str | None:
    segments = classification.get("segments") or []
    blocked = classification.get("blocked_segments") or []

    if requested_segment:
        if requested_segment == "Segment 4":
            blocked_segment_4 = next((item for item in blocked if item.get("segment") == "Segment 4"), None)
            if blocked_segment_4:
                raise ValueError("Cannot compose Segment 4 pitch for AI maturity score 0")
        if any(segment.get("segment") == requested_segment for segment in segments):
            return requested_segment
        raise ValueError(f"Requested segment {requested_segment} is not available for this company")

    if classification.get("generic_outreach"):
        return None
    if not segments:
        return None
    return segments[0]["segment"]


def compose_email(brief: dict[str, Any], classification: dict[str, Any], requested_segment: str | None = None) -> dict[str, Any]:
    company_name = brief.get("company") or "the team"
    selected_segment = select_segment(classification, requested_segment)

    ai_score = int(((brief.get("ai_maturity") or {}).get("ai_maturity_score") or 0))
    if selected_segment == "Segment 4" and ai_score < 2:
        return {"error": "Cannot compose Segment 4 pitch for AI maturity score 0"}

    template_name = SEGMENT_TEMPLATE_MAP.get(selected_segment, "generic.txt")
    template = load_template(template_name)

    funding_event = brief.get("funding_event") or {}
    competitor_line = build_competitor_line(brief)
    ai_signal_line = build_ai_signal_line(brief)
    job_signal_line = build_job_signal_line(brief)
    leadership_line = build_leadership_line(brief)
    generic_context_line = build_generic_context_line(brief)
    funding_tension_line = build_funding_tension_line(brief, classification)

    funding_amount = funding_event.get("amount_usd")
    funding_round = funding_event.get("round")
    funding_days_ago = funding_event.get("days_ago")

    if "funding_amount" in template:
        ensure_truth(funding_amount is not None, "Every funding claim must have a matching amount in the brief")
    if "funding_round" in template:
        ensure_truth(funding_round is not None, "Every funding claim must have a matching round in the brief")
    if "funding_days_ago" in template:
        ensure_truth(funding_days_ago is not None, "Every funding timing claim must have matching days_ago in the brief")

    body = template.format(
        company_team=f"{company_name} team",
        company_name=company_name,
        funding_amount=f"${funding_amount:,.0f}" if isinstance(funding_amount, (int, float)) else "recent funding",
        funding_round=funding_round or "funding round",
        funding_days_ago=funding_days_ago if funding_days_ago is not None else "recently",
        competitor_line=competitor_line,
        ai_signal_line=ai_signal_line,
        job_signal_line=job_signal_line,
        leadership_line=leadership_line,
        generic_context_line=generic_context_line,
        funding_tension_line=funding_tension_line,
    ).strip()

    research_grounded = False
    if funding_event and funding_event.get("amount_usd") is not None:
        research_grounded = True
    if (brief.get("job_posts") or {}).get("change_pct") is not None:
        research_grounded = True
    if competitor_line:
        research_grounded = True

    variant = "research-grounded" if research_grounded else "generic"
    return {
        "company": company_name,
        "segment": selected_segment,
        "variant": variant,
        "email_text": body,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose an outbound email from the hiring signal brief")
    parser.add_argument("--company", required=True, help="Company name for the current brief")
    parser.add_argument("--segment", required=False, help="Force a specific ICP segment")
    args = parser.parse_args(argv)

    if not BRIEF_PATH.exists():
        print(json.dumps({"error": f"Brief not found: {BRIEF_PATH}"}, indent=2))
        return 1

    brief = load_json(BRIEF_PATH)
    if (brief.get("company") or "").lower() != args.company.lower():
        print(
            json.dumps(
                {
                    "error": (
                        f"Loaded brief is for '{brief.get('company')}', not '{args.company}'. "
                        "Run build_brief.py for the target company first."
                    )
                },
                indent=2,
            )
        )
        return 1

    classification = classify_brief(brief)
    try:
        result = compose_email(brief, classification, requested_segment=args.segment)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    if "error" in result:
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
