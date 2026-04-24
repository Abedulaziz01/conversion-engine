from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.qualifier import qualify_reply


EMAIL_LOG_PATH = ROOT / "agent" / "email_log.jsonl"
BRIEF_PATH = ROOT / "enrichment" / "output" / "hiring_signal_brief.json"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_log(entry: dict[str, Any]) -> None:
    EMAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_email_log() -> list[dict[str, Any]]:
    if not EMAIL_LOG_PATH.exists():
        return []
    rows = []
    for line in EMAIL_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def find_original_outbound(message_id: str) -> dict[str, Any] | None:
    for row in reversed(load_email_log()):
        if row.get("event_type") == "outbound_email" and row.get("message_id") == message_id:
            return row
    return None


def process_reply(payload: dict[str, Any]) -> dict[str, Any]:
    sender_email = payload.get("sender_email") or payload.get("from")
    body_text = payload.get("body_text") or payload.get("text") or payload.get("body")
    timestamp = payload.get("timestamp") or utc_now()
    original_message_id = payload.get("original_message_id") or payload.get("message_id")

    if not sender_email or not body_text or not original_message_id:
        raise ValueError("Reply payload must include sender_email, body_text, and original_message_id")

    original = find_original_outbound(str(original_message_id))
    trace_id = original.get("trace_id") if original else None

    hiring_signal_brief = None
    if BRIEF_PATH.exists():
        hiring_signal_brief = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))

    reply_entry = {
        "event_type": "inbound_email_reply",
        "timestamp": timestamp,
        "sender_email": sender_email,
        "body_text": body_text,
        "original_message_id": original_message_id,
        "trace_id": trace_id,
    }
    append_log(reply_entry)

    qualification = qualify_reply(
        reply_entry,
        hiring_signal_brief,
        sender_email=sender_email,
        trace_id=trace_id,
    )
    qualification_entry = {
        "event_type": "qualification_result",
        "timestamp": utc_now(),
        "sender_email": sender_email,
        "trace_id": trace_id,
        "qualification_status": qualification.get("route"),
        "qualification_detail": qualification,
    }
    append_log(qualification_entry)

    return {
        "reply_logged": True,
        "trace_id": trace_id,
        "qualification": qualification,
    }


class ReplyWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhooks/email-reply":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw_body)
            result = process_reply(payload)
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def run_server(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), ReplyWebhookHandler)
    print(f"Reply webhook listening on http://127.0.0.1:{port}/webhooks/email-reply")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    port = 8000
    if argv and len(argv) > 1:
        port = int(argv[1])
    run_server(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
