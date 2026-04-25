from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from agent.email_composer import compose_email
from agent.email_sender import deliver_email, load_env_file
from agent.icp_classifier import classify_brief
from agent.qualifier import qualify_reply
from agent.reply_handler import process_reply
from agent.sms_consent_manager import handle_consent_command
from agent.sms_sender import send_sms
from enrichment.build_brief import build_master_brief


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
BRIEF_PATH = ROOT / "enrichment" / "output" / "hiring_signal_brief.json"
EMAIL_LOG_PATH = ROOT / "agent" / "email_log.jsonl"
SMS_LOG_PATH = ROOT / "agent" / "sms_log.jsonl"
SMS_CONSENT_LOG_PATH = ROOT / "agent" / "sms_consent_log.jsonl"
SCORE_LOG_PATH = ROOT / "eval" / "score_log.json"

DEMO_COMPANIES = {
    "AI-first startup: Jogg AI": {
        "company": "Jogg AI",
        "scenario": "Best for showing AI-oriented firmographics and a stronger AI narrative.",
    },
    "AI + industrial: Matevo Chemicals": {
        "company": "Matevo Chemicals",
        "scenario": "Good for showing AI-related company context in a more technical industrial setting.",
    },
    "Tech / FinTech: CoorB": {
        "company": "CoorB",
        "scenario": "Useful for a smaller digital finance and process-automation scenario.",
    },
}


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_outbound_message_id() -> str | None:
    for row in reversed(load_jsonl(EMAIL_LOG_PATH)):
        if row.get("event_type") == "outbound_email" and row.get("message_id"):
            return str(row["message_id"])
    return None


def render_json(data: Any) -> None:
    st.code(json.dumps(data, indent=2), language="json")


def render_metric_row(score_log: list[dict[str, Any]] | None) -> None:
    if not score_log:
        return
    latest = score_log[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Run", latest.get("run_id", "n/a"))
    col2.metric("Pass@1", latest.get("pass_at_1", "n/a"))
    col3.metric("P50 Latency", latest.get("p50_latency_ms", "n/a"))
    col4.metric("Tasks Run", latest.get("tasks_run", "n/a"))


def main() -> None:
    load_env_file(ENV_PATH)
    st.set_page_config(page_title="Conversion Engine Demo", layout="wide")
    st.title("Conversion Engine Demo")
    st.caption("Research -> classification -> compose -> simulate send -> simulate reply -> inspect logs")

    with st.sidebar:
        st.header("Demo Inputs")
        selected_demo = st.selectbox("Demo Scenario", list(DEMO_COMPANIES.keys()))
        scenario_company = DEMO_COMPANIES[selected_demo]["company"]
        st.caption(DEMO_COMPANIES[selected_demo]["scenario"])
        company_name = st.text_input("Company Name", value=scenario_company)
        recipient = st.text_input("Recipient Email", value="abduvaio@gmail.com")
        sms_phone = st.text_input("SMS Phone", value="+251711704273")
        reply_text = st.text_area(
            "Reply Text",
            value="Interesting, yes we're looking to scale our Python team",
            height=120,
        )
        sms_message = st.text_input("SMS Message", value="Warm lead SMS test")
        st.markdown(f"Recommended sample company: `{scenario_company}`")
        st.markdown("Safe mode: outbound is simulated inside this demo.")

    score_log = load_json(SCORE_LOG_PATH)
    if isinstance(score_log, list) and score_log:
        render_metric_row(score_log)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        [
            "1. Brief",
            "2. Signals",
            "3. Classification",
            "4. Email",
            "5. Reply Flow",
            "6. Qualification",
            "7. SMS",
            "8. Logs",
        ]
    )

    with tab1:
        st.subheader("Hiring Signal Brief")
        st.markdown("This runs the enrichment pipeline and writes `enrichment/output/hiring_signal_brief.json`.")
        if st.button("Build Brief", use_container_width=True):
            with st.spinner("Building brief..."):
                brief, elapsed = build_master_brief(company_name)
                st.session_state["brief"] = brief
                st.session_state["brief_elapsed"] = elapsed
        brief = st.session_state.get("brief")
        if brief is None and BRIEF_PATH.exists():
            brief = load_json(BRIEF_PATH)
            st.session_state["brief"] = brief
        if brief:
            st.success(f"Brief ready in {st.session_state.get('brief_elapsed', 0):.2f}s")
            render_json(brief)

    with tab2:
        st.subheader("Signals And Scoring")
        brief = st.session_state.get("brief")
        if brief:
            firmographics = brief.get("firmographics") or {}
            ai_maturity = brief.get("ai_maturity") or {}
            competitor_gap = brief.get("competitor_gap") or {}

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("AI Maturity", ai_maturity.get("ai_maturity_score", 0))
            col2.metric("AI Confidence", ai_maturity.get("confidence", "low"))
            col3.metric("Leadership Change", "Yes" if brief.get("leadership_change") else "No")
            col4.metric("Funding Signal", "Yes" if brief.get("funding_event") else "No")

            st.markdown("Firmographics")
            render_json(
                {
                    "company": firmographics.get("company"),
                    "employee_count": firmographics.get("employee_count"),
                    "industry": firmographics.get("industry"),
                    "city": firmographics.get("city"),
                    "country": firmographics.get("country"),
                    "website": firmographics.get("website"),
                }
            )

            signal_col1, signal_col2 = st.columns(2)
            with signal_col1:
                st.markdown("Leadership Signal")
                render_json(brief.get("leadership_change"))
                st.markdown("Layoff Signal")
                render_json(brief.get("layoff_event"))
            with signal_col2:
                st.markdown("Funding Signal")
                render_json(brief.get("funding_event"))
                st.markdown("Bench Match")
                render_json(brief.get("bench_match"))

            st.markdown("AI Maturity Breakdown")
            render_json(ai_maturity)

            st.markdown("Competitor Gap")
            render_json(
                {
                    "target_percentile": competitor_gap.get("target_percentile"),
                    "competitors_scored": competitor_gap.get("competitors_scored"),
                    "gaps": competitor_gap.get("gaps"),
                }
            )
        else:
            st.info("Build a brief first.")

    with tab3:
        st.subheader("ICP Classification")
        brief = st.session_state.get("brief")
        if brief:
            classification = classify_brief(brief)
            st.session_state["classification"] = classification
            render_json(classification)
        else:
            st.info("Build a brief first.")

    with tab4:
        st.subheader("Compose And Simulate Send")
        brief = st.session_state.get("brief")
        classification = st.session_state.get("classification")
        if brief and classification:
            try:
                composed = compose_email(brief, classification)
            except ValueError as exc:
                composed = {"error": str(exc)}
            st.session_state["composed"] = composed
            render_json(composed)

            if "error" not in composed and st.button("Simulate Send Email", use_container_width=True):
                os.environ["LIVE_OUTBOUND"] = "false"
                result = deliver_email(
                    composed_email=composed,
                    recipient=recipient,
                    trace_id=str(brief.get("crunchbase_id") or company_name.lower().replace(" ", "-")),
                )
                st.session_state["send_result"] = result
            if st.session_state.get("send_result"):
                st.success("Simulated send logged.")
                render_json(st.session_state["send_result"])
        else:
            st.info("Build a brief first.")

    with tab5:
        st.subheader("Reply Handling Demo")
        st.markdown("This mirrors the `python agent\\reply_handler.py 8000` flow, but runs inside the app.")
        outbound_message_id = latest_outbound_message_id()
        st.text_input(
            "Latest Outbound Message ID",
            value=outbound_message_id or "",
            disabled=True,
        )
        if st.button("Simulate Reply", use_container_width=True):
            if not outbound_message_id:
                st.error("Send or simulate an email first so there is a message_id to attach the reply to.")
            else:
                result = process_reply(
                    {
                        "sender_email": recipient,
                        "body_text": reply_text,
                        "original_message_id": outbound_message_id,
                    }
                )
                st.session_state["reply_result"] = result
        if st.session_state.get("reply_result"):
            st.success("Reply processed and logged.")
            render_json(st.session_state["reply_result"])

        with st.expander("Equivalent terminal commands"):
            st.code(
                "python agent\\reply_handler.py 8000\n"
                "Get-Content agent\\email_log.jsonl",
                language="powershell",
            )

    with tab6:
        st.subheader("Qualification Logic")
        brief = st.session_state.get("brief")
        if brief:
            qualification = qualify_reply(reply_text, brief, sender_email=recipient, trace_id="streamlit-demo")
            st.session_state["qualification"] = qualification
            render_json(qualification)
        else:
            st.info("Build a brief first.")

    with tab7:
        st.subheader("SMS Consent And Gating")
        st.markdown("This uses the same warm-lead, STOP/UNSUB, HELP, and length checks as the terminal flow.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Simulate SMS Send", use_container_width=True):
                os.environ["LIVE_OUTBOUND"] = "false"
                sms_result = send_sms(sms_phone, sms_message)
                st.session_state["sms_result"] = sms_result
            if st.session_state.get("sms_result"):
                render_json(st.session_state["sms_result"])
        with col2:
            consent_command = st.selectbox("Consent Command", ["HELP", "STOP", "UNSUB"])
            if st.button("Apply Consent Command", use_container_width=True):
                os.environ["LIVE_OUTBOUND"] = "false"
                consent_result = handle_consent_command(sms_phone, consent_command)
                st.session_state["consent_result"] = consent_result
            if st.session_state.get("consent_result"):
                render_json(st.session_state["consent_result"])

        with st.expander("Equivalent terminal commands"):
            st.code(
                "python agent\\sms_sender.py --phone \"+251711704273\" --message \"Warm lead SMS test\"\n"
                "python agent\\sms_receiver.py 8010\n"
                "Get-Content agent\\sms_log.jsonl\n"
                "Get-Content agent\\sms_consent_log.jsonl",
                language="powershell",
            )

    with tab8:
        st.subheader("Logs")
        email_log = load_jsonl(EMAIL_LOG_PATH)
        st.markdown("Email log preview")
        render_json(email_log[-12:] if email_log else [])
        with st.expander("Terminal command for the same log"):
            st.code("Get-Content agent\\email_log.jsonl", language="powershell")

        st.markdown("SMS log preview")
        sms_log = load_jsonl(SMS_LOG_PATH)
        render_json(sms_log[-12:] if sms_log else [])

        st.markdown("SMS consent log preview")
        sms_consent_log = load_jsonl(SMS_CONSENT_LOG_PATH)
        render_json(sms_consent_log[-12:] if sms_consent_log else [])

        if isinstance(score_log, list) and score_log:
            st.markdown("Evaluation summary")
            render_json(score_log[-5:])


if __name__ == "__main__":
    main()
