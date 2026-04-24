from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ROBOTS_CHECKER_PATH = ROOT / "enrichment" / "robots_checker.py"
SNAPSHOT_PATH = ROOT / "data" / "job_posts_snapshot.json"

NAVIGATION_NOISE = {
    "home", "about", "blog", "contact", "login", "sign in",
    "sign up", "search", "menu", "jobs", "careers", "our opportunity",
    "teams", "locations", "benefits", "culture", "faq", "resources",
    "apply", "back", "next", "previous", "load more", "view all",
    "settings", "privacy", "terms", "legal", "cookie", "accessibility",
    "my applications", "my profile", "account security", "sign out",
    "military careers", "hourly", "amazon newsletter", "application status",
    "legal disclosures and notices", "how we hire", "leadership principles",
    "working at amazon", "inclusive experiences", "accommodations",
}

ENGINEERING_KEYWORDS = [
    "engineer", "engineering", "developer", "software",
    "backend", "frontend", "full stack", "fullstack",
    "platform", "machine learning", "ml ", "ai ",
    "devops", "site reliability", "sre", "infrastructure",
    "qa", "test automation", "data engineer", "data scientist",
    "python", "golang", "java", "typescript", "rust",
]


def load_robots_checker():
    spec = importlib.util.spec_from_file_location(
        "robots_checker_module", ROBOTS_CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load robots checker from {ROBOTS_CHECKER_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_token(value: str) -> str:
    cleaned = value.lower().strip()
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split(".")[0]
    cleaned = re.sub(
        r"\b(inc|corp|company|co|llc|ltd|limited|"
        r"technologies|technology|platforms)\b",
        "", cleaned
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_role(title: str, department: str) -> str:
    haystack = f"{title} {department}".lower()
    return (
        "engineering"
        if any(kw in haystack for kw in ENGINEERING_KEYWORDS)
        else "non-engineering"
    )


def is_navigation_noise(title: str) -> bool:
    cleaned = title.strip().lower()
    if len(cleaned) < 5:
        return True
    if len(cleaned) > 120:
        return True
    if cleaned in NAVIGATION_NOISE:
        return True
    if any(cleaned.startswith(n) for n in NAVIGATION_NOISE):
        return True
    if re.search(r"(cookie|privacy|terms|copyright|©|\d{4})", cleaned):
        return True
    return False


def load_snapshot_count(company_domain: str) -> int:
    try:
        payload = json.loads(
            SNAPSHOT_PATH.read_text(encoding="utf-8")
        )
        companies = (
            payload.get("companies", [])
            if isinstance(payload, dict)
            else payload
        )
        target = normalize_token(company_domain)
        for company in companies:
            name = normalize_token(str(company.get("name") or ""))
            if name and (
                name == target or name in target or target in name
            ):
                try:
                    return int(company.get("open_roles", 0) or 0)
                except (TypeError, ValueError):
                    return 0
    except Exception:
        pass
    return 0


async def fetch_job_listings(
    company_domain: str,
) -> list[dict[str, str]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright "
            "and playwright install"
        ) from exc

    candidate_urls = [
        f"https://{company_domain}/careers",
        f"https://{company_domain}/jobs",
        f"https://jobs.{company_domain}",
        f"https://www.{company_domain}/careers",
        f"https://www.{company_domain}/jobs",
        f"https://{company_domain}/work-with-us",
        f"https://{company_domain}/open-positions",
    ]

    job_selectors = [
        "[data-job-title]",
        "[data-testid*='job']",
        "[class*='job-title']",
        "[class*='position-title']",
        "[class*='opening']",
        "[class*='role']",
        "h2",
        "h3",
        "article h2",
        "article h3",
        "li h2",
        "li h3",
    ]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            for url in candidate_urls:
                try:
                    response = await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=20000
                    )
                except Exception:
                    try:
                        response = await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=15000
                        )
                    except Exception:
                        continue

                if response is None or response.status >= 400:
                    continue

                await page.wait_for_timeout(2000)

                listings: list[dict[str, str]] = []

                for selector in job_selectors:
                    try:
                        locators = page.locator(selector)
                        count = min(await locators.count(), 100)
                        for idx in range(count):
                            try:
                                card = locators.nth(idx)
                                text = (
                                    await card.text_content() or ""
                                ).strip()
                                if not text:
                                    continue
                                lines = [
                                    ln.strip()
                                    for ln in text.splitlines()
                                    if ln.strip()
                                ]
                                title = lines[0] if lines else text[:120]
                                department = (
                                    lines[1] if len(lines) > 1 else ""
                                )
                                if is_navigation_noise(title):
                                    continue
                                listings.append(
                                    {
                                        "title": title,
                                        "department": department,
                                    }
                                )
                            except Exception:
                                continue
                    except Exception:
                        continue

                    if len(listings) >= 3:
                        return dedupe(listings)

            return []

        finally:
            await browser.close()


def dedupe(listings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for item in listings:
        key = (
            item.get("title", "").strip().lower(),
            item.get("department", "").strip().lower(),
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def calc_change_pct(
    roles_now: int, roles_60d_ago: int
) -> float | None:
    if roles_60d_ago <= 0:
        return None
    return round(
        ((roles_now - roles_60d_ago) / roles_60d_ago) * 100, 1
    )


async def scrape_jobs(company_domain: str) -> dict[str, Any]:
    robots = load_robots_checker()
    careers_url = f"https://{company_domain}/careers"
    robots_result = robots.is_scraping_allowed(careers_url)

    if not robots_result["allowed"]:
        return {
            "scraping_blocked": True,
            "company_domain": company_domain,
            "robots_respected": True,
            "reason": robots_result.get("reason", "robots.txt blocked"),
        }

    listings = await fetch_job_listings(company_domain)
    roles_now = len(listings)
    roles_60d_ago = load_snapshot_count(company_domain)
    engineering_count = sum(
        1
        for item in listings
        if classify_role(item["title"], item["department"])
        == "engineering"
    )

    return {
        "company_domain": company_domain,
        "roles_now": roles_now,
        "roles_60d_ago": roles_60d_ago,
        "change_pct": calc_change_pct(roles_now, roles_60d_ago),
        "engineering_roles_now": engineering_count,
        "role_titles": [item["title"] for item in listings],
        "scrape_timestamp": (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "robots_respected": True,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('Usage: python enrichment/job_scraper.py "stripe.com"')
        return 1

    company_domain = argv[1].strip().lower()
    company_domain = re.sub(r"^https?://", "", company_domain)
    company_domain = company_domain.strip("/")

    if not company_domain:
        print("Company domain cannot be empty.")
        return 1

    try:
        result = asyncio.run(scrape_jobs(company_domain))
        print(json.dumps(result, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({
            "company_domain": company_domain,
            "error": str(exc),
        }, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))