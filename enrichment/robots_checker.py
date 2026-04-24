from __future__ import annotations

import json
import sys
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

USER_AGENT = "conversion-engine-bot"

ALWAYS_BLOCKED = [
    "amazon.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
]


def is_scraping_allowed(url: str, *, user_agent: str = USER_AGENT) -> dict:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "URL must include scheme and domain, "
            "for example https://stripe.com"
        )

    domain = parsed.netloc.lower().replace("www.", "")
    for blocked in ALWAYS_BLOCKED:
        if blocked in domain:
            return {
                "url": url,
                "robots_url": f"{parsed.scheme}://{parsed.netloc}/robots.txt",
                "allowed": False,
                "status": "blocked_by_policy",
                "reason": f"{domain} is in the always-blocked list"
            }

    robots_url = urljoin(
        f"{parsed.scheme}://{parsed.netloc}", "/robots.txt"
    )
    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        parser.read()
        allowed = parser.can_fetch(user_agent, url)
        also_check = parser.can_fetch("*", url)
        final_allowed = bool(allowed and also_check)
        status = "ok"
    except Exception:
        final_allowed = False
        status = "unreachable"

    return {
        "url": url,
        "robots_url": robots_url,
        "allowed": final_allowed,
        "status": status,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            'Usage: python enrichment/robots_checker.py '
            '"https://example.com/path"'
        )
        return 1

    result = is_scraping_allowed(argv[1].strip())
    print(f"Scraping allowed: {result['allowed']}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))