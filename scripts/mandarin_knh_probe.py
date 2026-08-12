#!/usr/bin/env python3
"""Temporary narrow probe for Mandarin Airlines' official booking form.

Route/date-specific acquisition research only, not a production crawler. Uses vanilla
Playwright and ordinary browser interaction. It does not synthesize or bypass a
Cloudflare Turnstile response, CAPTCHA, stealth/fingerprint checks, or proxies.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://www.mandarin-airlines.com/b2c/BookingNPurchase"
OUT = Path("artifacts/mandarin-knh-probe")
ROUTES = (("KHH", "KNH"), ("TSA", "KNH"))
DEPARTURE = "2026-08-20"
RETURN = "2026-08-23"


async def set_date(page, selector: str, value: str) -> None:
    await page.locator(selector).evaluate(
        """(el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )


async def query(browser, origin: str, destination: str) -> dict:
    page = await browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
    response = await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(4_000)

    # Ordinary UI interaction. Do not touch cf_turnstile_response.
    await page.locator("#trip_return").check()
    await page.locator("#departureCity1").select_option(origin)
    await page.wait_for_timeout(500)
    await page.locator("#arrivalCity1").select_option(destination)
    await set_date(page, "#rtDeptDate1", DEPARTURE)
    await set_date(page, "#rtRetDate1", RETURN)

    pre = {
        "origin": origin,
        "destination": destination,
        "departure": DEPARTURE,
        "return": RETURN,
        "http_status": response.status if response else None,
        "turnstile_field_present": await page.locator("#cf_turnstile_response").count() > 0,
        "turnstile_value_present_before_click": bool(
            await page.locator("#cf_turnstile_response").input_value()
        ),
    }

    await page.locator("#querybtn").click()
    await page.wait_for_timeout(15_000)

    body = await page.locator("body").inner_text()
    result = {
        **pre,
        "final_url": page.url,
        "title": await page.title(),
        "body_excerpt": body[:12_000],
        "challenge_text_detected": any(
            token in body.lower()
            for token in ("captcha", "turnstile", "verify you are human", "驗證您是人類", "機器人")
        ),
        "buttons": await page.locator("button").all_inner_texts(),
        "links": (await page.locator("a").all_inner_texts())[:100],
    }

    slug = f"{origin.lower()}-{destination.lower()}-{DEPARTURE}-{RETURN}"
    (OUT / f"{slug}.txt").write_text(body, encoding="utf-8")
    (OUT / f"{slug}.html").write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(OUT / f"{slug}.png"), full_page=True)
    await page.close()
    return result


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        results = []
        for origin, destination in ROUTES:
            try:
                results.append(await query(browser, origin, destination))
            except Exception as exc:  # probe evidence should retain failures cleanly
                results.append({
                    "origin": origin,
                    "destination": destination,
                    "departure": DEPARTURE,
                    "return": RETURN,
                    "error": type(exc).__name__,
                    "message": str(exc)[:2000],
                })
        (OUT / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
