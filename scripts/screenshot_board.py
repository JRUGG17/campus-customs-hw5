"""Screenshot the React board for each resolved ticket (needs the backend on :8000 and the page on :5173).

Run from hw5/:  venv/bin/python scripts/screenshot_board.py
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "output" / "screens"
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:5173")
    page.wait_for_selector(".work-order")
    for tid in (101, 102, 103):
        page.locator(f".work-order:has-text('№ {tid}')").click()
        page.wait_for_selector(".verdict", timeout=15000)
        page.locator(".feed").evaluate("e => e.scrollTop = 0")
        time.sleep(1.5)
        stamp = page.locator(".work-order.selected .stamp").inner_text()
        page.screenshot(path=str(OUT / f"ticket_{tid}.png"), full_page=True)
        print(tid, "stamp:", stamp, "| checking:", page.locator(".till-digits").inner_text())
    print("console errors:", errors)
    browser.close()
