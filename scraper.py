import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, date
import re

# ── Browser-like headers to avoid 403 blocks ──────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

BASE_URL = "https://www.goodreturns.in/gold-rates/chennai.html"


def clean_price(text: str) -> float | None:
    """Remove ₹, commas, spaces and return float."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape_gold_prices() -> dict:
    """Scrape gold and silver prices from goodreturns.in Chennai page."""
    try:
        response = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch page: {e}")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")

    result = {
        "city": "Chennai",
        "currency": "INR",
        "last_updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": date.today().isoformat(),
        "gold": {
            "22k": {},
            "24k": {},
        },
        "silver": {},
    }

    # ── Parse gold price tables ────────────────────────────────────────────────
    # goodreturns uses tables with class "gold-silver-table" or similar
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            price_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            price_24k_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            price_22k = clean_price(price_text)
            price_24k = clean_price(price_24k_text)

            # Map row labels to time periods
            if "today" in label or "1 day" in label:
                if price_22k:
                    result["gold"]["22k"]["today"] = price_22k
                if price_24k:
                    result["gold"]["24k"]["today"] = price_24k
            elif "yesterday" in label:
                if price_22k:
                    result["gold"]["22k"]["yesterday"] = price_22k
                if price_24k:
                    result["gold"]["24k"]["yesterday"] = price_24k
            elif "week" in label or "7 day" in label:
                if price_22k:
                    result["gold"]["22k"]["week_ago"] = price_22k
                if price_24k:
                    result["gold"]["24k"]["week_ago"] = price_24k
            elif "month" in label or "30 day" in label:
                if price_22k:
                    result["gold"]["22k"]["month_ago"] = price_22k
                if price_24k:
                    result["gold"]["24k"]["month_ago"] = price_24k
            elif "year" in label or "365 day" in label or "annual" in label:
                if price_22k:
                    result["gold"]["22k"]["year_ago"] = price_22k
                if price_24k:
                    result["gold"]["24k"]["year_ago"] = price_24k

    # ── Fallback: look for specific CSS classes used by goodreturns ───────────
    # The site uses spans/divs with class patterns like "gold-price-today"
    price_blocks = soup.find_all(["span", "div", "td"], class_=re.compile(r"gold|silver|rate|price", re.I))
    for block in price_blocks:
        class_str = " ".join(block.get("class", [])).lower()
        text = block.get_text(strip=True)

        if not text or not re.search(r"\d", text):
            continue

        price = clean_price(text)
        if price is None:
            continue

        if "22k" in class_str or "22-karat" in class_str:
            if "today" in class_str:
                result["gold"]["22k"]["today"] = price
        elif "24k" in class_str or "24-karat" in class_str:
            if "today" in class_str:
                result["gold"]["24k"]["today"] = price

    # ── Try to get today's price from page title / hero section ───────────────
    # Many gold price sites have a hero/banner with today's rate
    for selector in [".gold-rate-today", ".goldrate", "#gold-rate", ".rates-table"]:
        block = soup.select_one(selector)
        if block:
            numbers = re.findall(r"[\d,]+", block.get_text())
            numbers = [clean_price(n) for n in numbers if clean_price(n) and clean_price(n) > 1000]
            if len(numbers) >= 1 and not result["gold"]["22k"].get("today"):
                result["gold"]["22k"]["today"] = numbers[0]
            if len(numbers) >= 2 and not result["gold"]["24k"].get("today"):
                result["gold"]["24k"]["today"] = numbers[1]

    # ── Silver prices ─────────────────────────────────────────────────────────
    silver_page_url = "https://www.goodreturns.in/silver-rates/chennai.html"
    try:
        silver_resp = requests.get(silver_page_url, headers=HEADERS, timeout=15)
        silver_soup = BeautifulSoup(silver_resp.text, "html.parser")
        s_tables = silver_soup.find_all("table")
        for table in s_tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(strip=True).lower()
                price = clean_price(cells[1].get_text(strip=True))
                if price is None:
                    continue
                if "today" in label:
                    result["silver"]["today"] = price
                elif "yesterday" in label:
                    result["silver"]["yesterday"] = price
                elif "week" in label:
                    result["silver"]["week_ago"] = price
                elif "month" in label:
                    result["silver"]["month_ago"] = price
                elif "year" in label:
                    result["silver"]["year_ago"] = price
    except Exception as e:
        print(f"[WARN] Silver scrape failed: {e}")

    return result


def save_json(data: dict, output_dir: str = "api") -> None:
    os.makedirs(output_dir, exist_ok=True)

    # Main combined file
    path = os.path.join(output_dir, "gold_prices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved → {path}")

    # Separate convenience files
    gold_path = os.path.join(output_dir, "gold.json")
    with open(gold_path, "w", encoding="utf-8") as f:
        json.dump({
            "city": data["city"],
            "currency": data["currency"],
            "date": data["date"],
            "last_updated": data["last_updated"],
            **data.get("gold", {})
        }, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved → {gold_path}")

    silver_path = os.path.join(output_dir, "silver.json")
    with open(silver_path, "w", encoding="utf-8") as f:
        json.dump({
            "city": data["city"],
            "currency": data["currency"],
            "date": data["date"],
            "last_updated": data["last_updated"],
            "silver": data.get("silver", {})
        }, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved → {silver_path}")

    # History: append today's entry to history.json
    history_path = os.path.join(output_dir, "history.json")
    history = []
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    # Remove existing entry for today (avoid duplicates)
    history = [h for h in history if h.get("date") != data.get("date")]
    history.append({
        "date": data["date"],
        "gold_22k_today": data["gold"]["22k"].get("today"),
        "gold_24k_today": data["gold"]["24k"].get("today"),
        "silver_today": data["silver"].get("today"),
    })

    # Keep last 365 days
    history = sorted(history, key=lambda x: x["date"])[-365:]
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved → {history_path}")


if __name__ == "__main__":
    print(f"[INFO] Scraping gold prices — {datetime.utcnow().isoformat()}")
    data = scrape_gold_prices()

    if not data:
        print("[ERROR] No data scraped. Exiting.")
        exit(1)

    print(json.dumps(data, indent=2))
    save_json(data)
    print("[DONE] All files updated.")
