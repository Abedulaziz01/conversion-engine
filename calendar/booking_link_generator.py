from __future__ import annotations

import argparse
import json
import os
import urllib.parse

import requests
from dotenv import load_dotenv


load_dotenv()

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
CALCOM_BASE_URL = (os.getenv("CALCOM_BASE_URL") or "http://localhost:3000").rstrip("/")
CALCOM_BOOKING_USERNAME = os.getenv("CALCOM_BOOKING_USERNAME") or "tenacious"
CALCOM_EVENT_TYPE_SLUG = os.getenv("CALCOM_EVENT_TYPE_SLUG") or "discovery"


def generate_booking_link(company_name: str, icp_segment: str) -> str | None:
    """
    Generates a Cal.com booking link pre-populated with prospect info.
    """

    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
    }

    event_slug = CALCOM_EVENT_TYPE_SLUG
    username = CALCOM_BOOKING_USERNAME

    if CALCOM_API_KEY:
        try:
            response = requests.get(
                f"{CALCOM_BASE_URL}/api/v1/event-types",
                headers=headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            print(f"Could not reach Cal.com API: {exc}")
            print("Falling back to .env booking slug.")
        else:
            if response.status_code == 200:
                event_types = response.json().get("event_types", [])
                if event_types:
                    event = event_types[0]
                    event_slug = event.get("slug") or event_slug
                    username = event.get("profile", {}).get("slug") or username
                else:
                    print("No event types found from API. Falling back to .env booking slug.")
            else:
                print(f"Could not fetch event types: {response.text}")
                print("Falling back to .env booking slug.")
    else:
        print("CALCOM_API_KEY not set. Falling back to .env booking slug.")

    notes = (
        f"Company: {company_name} | Segment: {icp_segment} | "
        "Outreach: Tenacious signal-grounded"
    )
    params = {
        "name": company_name,
        "notes": notes,
        "company": company_name,
        "segment": icp_segment,
    }
    booking_url = (
        f"{CALCOM_BASE_URL}/{urllib.parse.quote(username)}/{urllib.parse.quote(event_slug)}"
        f"?{urllib.parse.urlencode(params)}"
    )

    print(f"Booking link generated: {booking_url}")
    return booking_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Cal.com booking link")
    parser.add_argument("company", nargs="?", default="DataFlow Labs")
    parser.add_argument("segment", nargs="?", default="Segment 1")
    args = parser.parse_args(argv)

    url = generate_booking_link(args.company, args.segment)
    print(json.dumps({"booking_url": url}, indent=2))
    return 0 if url else 1


if __name__ == "__main__":
    raise SystemExit(main())
