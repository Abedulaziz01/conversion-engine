import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        urls = [
            "https://stripe.com/jobs",
            "https://stripe.com/careers",
            "https://stripe.com/jobs/search",
        ]

        for url in urls:
            try:
                r = await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=20000
                )
                await page.wait_for_timeout(3000)
                title = await page.title()
                content = await page.content()
                job_count = content.lower().count("engineer")
                status = r.status if r else "failed"
                print(f"URL: {url}")
                print(f"  Status: {status}")
                print(f"  Title: {title}")
                print(f"  Engineer mentions: {job_count}")
                print()
            except Exception as e:
                print(f"URL: {url} FAILED: {e}")

        await browser.close()

asyncio.run(check())