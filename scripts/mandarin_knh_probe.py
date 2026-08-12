#!/usr/bin/env python3
"""Temporary narrow probe for Mandarin Airlines' official booking form.

This is intentionally route/date-specific acquisition research, not a production crawler.
It uses vanilla Playwright only, performs no CAPTCHA/stealth/proxy bypass, and writes
DOM metadata so the exact booking interaction can be implemented deterministically.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://www.mandarin-airlines.com/b2c/BookingNPurchase"
OUT = Path("artifacts/mandarin-knh-probe")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
        response = await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(5_000)

        metadata = await page.evaluate(
            """() => ({
              url: location.href,
              title: document.title,
              inputs: [...document.querySelectorAll('input')].map((e, i) => ({
                i, id: e.id, name: e.name, type: e.type, value: e.value,
                placeholder: e.placeholder, checked: e.checked,
                outerHTML: e.outerHTML.slice(0, 800)
              })),
              selects: [...document.querySelectorAll('select')].map((e, i) => ({
                i, id: e.id, name: e.name, value: e.value,
                options: [...e.options].map(o => ({value: o.value, text: o.textContent.trim()})),
                outerHTML: e.outerHTML.slice(0, 1200)
              })),
              buttons: [...document.querySelectorAll('button')].map((e, i) => ({
                i, id: e.id, name: e.name, type: e.type,
                text: e.textContent.trim(), outerHTML: e.outerHTML.slice(0, 1000)
              })),
              forms: [...document.querySelectorAll('form')].map((e, i) => ({
                i, id: e.id, name: e.name, action: e.action, method: e.method,
                outerHTML: e.outerHTML.slice(0, 2000)
              }))
            })"""
        )
        metadata["http_status"] = response.status if response else None
        (OUT / "dom.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "page.html").write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(OUT / "page.png"), full_page=True)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
