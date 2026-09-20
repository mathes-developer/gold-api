import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, date, timezone

GOLD_URL   = "https://www.goodreturns.in/gold-rates/chennai.html"
SILVER_URL = "https://www.goodreturns.in/silver-rates/chennai.html"

OUTPUT_DIR = "api"


# ── Helpers ────────────────────────────────────────────────────────────────────

def clean_price(text: str) -> float | None:
    """Strip ₹, commas, spaces → float. Returns None if not a valid price."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).strip())
    try:
        val = float(cleaned)
        # Gold prices are always > 1000 INR per gram or per 10g
        return val if val > 100 else None
    except ValueError:
        return None


# ── Browser fetch ─────────────────────────────────────────────────────────────

async def fetch_html(url: str) -> str:
    """Launch headless Chromium, load page fully (JS executed), return HTML."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception:
            # fallback: just wait 5 sec after domcontentloaded
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(5_000)

        # Extra wait so JS tables finish rendering
        await page.wait_for_timeout(3_000)
        html = await page.content()
        await browser.close()
        return html


# ── Parser ────────────────────────────────────────────────────────────────────

PERIOD_MAP = {
    "today":     "today",
    "current":   "today",
    "yesterday": "yesterday",
    "week":      "week_ago",
    "7 day":     "week_ago",
    "month":     "month_ago",
    "30 day":    "month_ago",
    "year":      "year_ago",
    "365":       "year_ago",
    "annual":    "year_ago",
}


def detect_period(label: str) -> str | None:
    label = label.lower()
    for keyword, period in PERIOD_MAP.items():
        if keyword in label:
            return period
    return None


def parse_gold_from_html(html: str) -> dict:
    """
    Parse 22K and 24K gold prices from goodreturns.in rendered HTML.
    Returns: { "22k": {today, yesterday, week_ago, ...}, "24k": {...} }
    """
    soup = BeautifulSoup(html, "lxml")
    result = {"22k": {}, "24k": {}}

    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = cells[0].get_text(" ", strip=True)
            period = detect_period(label)
            if not period:
                continue

            # Collect all numeric prices from this row
            prices = []
            for cell in cells[1:]:
                p = clean_price(cell.get_text(strip=True))
                if p:
                    prices.append(p)

            # goodreturns typically: col1=22K, col2=24K
            if len(prices) >= 1 and period not in result["22k"]:
                result["22k"][period] = prices[0]
            if len(prices) >= 2 and period not in result["24k"]:
                result["24k"][period] = prices[1]

    # ── Fallback: scan all text nodes for large numbers near period keywords ──
    if not result["22k"].get("today"):
        for tag in soup.find_all(True):
            text = tag.get_text(" ", strip=True).lower()
            period = detect_period(text)
            if not period:
                continue
            nums = [clean_price(n) for n in re.findall(r"[\d,]+", text)]
            nums = [n for n in nums if n and n > 1000]
            if len(nums) >= 1 and period not in result["22k"]:
                result["22k"][period] = nums[0]
            if len(nums) >= 2 and period not in result["24k"]:
                result["24k"][period] = nums[1]

    return result


def parse_silver_from_html(html: str) -> dict:
    """Parse silver prices. Returns { today, yesterday, week_ago, ... }"""
    soup = BeautifulSoup(html, "lxml")
    result = {}
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            period = detect_period(label)
            if not period:
                continue
            price = clean_price(cells[1].get_text(strip=True))
            # Silver per 10g is usually between 50–5000 INR
            if price and price > 10 and period not in result:
                result[period] = price

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    today_str = date.today().isoformat()
    now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[INFO] Fetching gold page …")
    gold_html = await fetch_html(GOLD_URL)

    print(f"[INFO] Fetching silver page …")
    silver_html = await fetch_html(SILVER_URL)

    gold   = parse_gold_from_html(gold_html)
    silver = parse_silver_from_html(silver_html)

    print(f"[DEBUG] Gold  22K: {gold['22k']}")
    print(f"[DEBUG] Gold  24K: {gold['24k']}")
    print(f"[DEBUG] Silver  : {silver}")

    data = {
        "city":         "Chennai",
        "currency":     "INR",
        "last_updated": now_str,
        "date":         today_str,
        "gold":         gold,
        "silver":       silver,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── gold_prices.json (combined) ──────────────────────────────────────────
    _write(f"{OUTPUT_DIR}/gold_prices.json", data)

    # ── gold.json ────────────────────────────────────────────────────────────
    _write(f"{OUTPUT_DIR}/gold.json", {
        "city": data["city"], "currency": data["currency"],
        "date": today_str, "last_updated": now_str,
        **gold,
    })

    # ── silver.json ──────────────────────────────────────────────────────────
    _write(f"{OUTPUT_DIR}/silver.json", {
        "city": data["city"], "currency": data["currency"],
        "date": today_str, "last_updated": now_str,
        "silver": silver,
    })

    # ── history.json (last 365 days) ─────────────────────────────────────────
    history_path = f"{OUTPUT_DIR}/history.json"
    history = []
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    history = [h for h in history if h.get("date") != today_str]
    history.append({
        "date":           today_str,
        "gold_22k_today": gold["22k"].get("today"),
        "gold_24k_today": gold["24k"].get("today"),
        "silver_today":   silver.get("today"),
    })
    history = sorted(history, key=lambda x: x["date"])[-365:]
    _write(history_path, history)

    print("[DONE] All JSON files updated.")


def _write(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK]   {path}")


if __name__ == "__main__":
    asyncio.run(main())
