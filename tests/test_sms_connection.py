from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEFAULT_AT_BASE_URL = "https://api.sandbox.africastalking.com"


def console_symbol(preferred: str, fallback: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        preferred.encode(encoding)
    except UnicodeEncodeError:
        return fallback
    return preferred


SUCCESS_SYMBOL = console_symbol("[OK]", "[OK]")
FAIL_SYMBOL = console_symbol("[FAIL]", "[FAIL]")
WARN_SYMBOL = console_symbol("[WARN]", "[WARN]")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def is_missing(value: str | None) -> bool:
    if value is None:
        return True

    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return True

    return cleaned.startswith("your_")


def get_env(*names: str, required: bool = True) -> str | None:
    for name in names:
        value = os.getenv(name)
        if not is_missing(value):
            return value

    if required:
        joined = ", ".join(names)
        raise RuntimeError(f"Set {joined} in .env or in your shell before running this test.")

    return None


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    form_body: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    body = urllib.parse.urlencode(form_body or {}).encode("utf-8")
    final_headers = dict(headers or {})
    final_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = urllib.request.Request(
        url=url,
        data=body,
        headers=final_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return response.getcode(), json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {payload}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def warn_if_mismatched(username: str, base_url: str) -> None:
    is_sandbox_user = username.strip().lower() == "sandbox"
    is_sandbox_url = "sandbox" in base_url.lower()

    if is_sandbox_user != is_sandbox_url:
        print(
            f"{WARN_SYMBOL} username/base URL look mismatched: "
            f"username={username}, base_url={base_url}"
        )


def test_sms() -> None:
    username = get_env("AFRICASTALKING_USERNAME")
    api_key = get_env("AFRICASTALKING_API_KEY")
    to_phone = get_env("TEST_PHONE_TO", "AFRICASTALKING_TEST_TO")
    shortcode = get_env("AFRICASTALKING_SHORTCODE", required=False)
    base_url = (
        get_env("AFRICASTALKING_BASE_URL", required=False) or DEFAULT_AT_BASE_URL
    ).rstrip("/")

    warn_if_mismatched(username, base_url)

    form_body = {
        "username": username,
        "to": to_phone,
        "message": "conversion-engine SMS test",
    }
    if shortcode:
        form_body["from"] = shortcode

    _, response = request_json(
        "POST",
        f"{base_url}/version1/messaging",
        headers={
            "apiKey": api_key,
            "Accept": "application/json",
        },
        form_body=form_body,
    )

    sms_data = response.get("SMSMessageData", {})
    recipients = sms_data.get("Recipients", [])
    if not recipients:
        raise RuntimeError(f"Unexpected response: {response}")

    first = recipients[0]
    status = str(first.get("status", ""))
    status_code = str(first.get("statusCode", ""))

    if "success" not in status.lower() and status_code != "101":
        raise RuntimeError(f"Unexpected recipient response: {first}")

    environment_label = "sandbox" if "sandbox" in base_url.lower() else "live"
    print(
        f"{SUCCESS_SYMBOL} AFRICAS_TALKING connected "
        f"({environment_label}, message id {first.get('messageId', 'n/a')})"
    )


def main() -> int:
    load_env_file(ENV_PATH)

    try:
        test_sms()
    except Exception as exc:
        print(f"{FAIL_SYMBOL} AFRICAS_TALKING failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
