import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, date, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
GOLD_URL   = "https://www.goodreturns.in/gold-rates/chennai.html"
SILVER_URL = "https://www.goodreturns.in/silver-rates/chennai.html"
OUTPUT_DIR = "api"

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def clean_price(text: str):
    """Remove ₹, commas, HTML entities → float. Returns None if invalid."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).strip())
    try:
        val = float(cleaned)
        return val if val > 10 else None
    except ValueError:
        return None


def parse_gr_date(text: str):
    """Parse goodreturns date string 'Sep 20, 2026' → date object."""
    try:
        return datetime.strptime(text.strip(), "%b %d, %Y").date()
    except ValueError:
        return None


def date_to_period(row_date: date, today: date):
    """Map a historical date to a summary period label."""
    diff = (today - row_date).days
    if diff == 0:
        return "today"
    elif diff == 1:
        return "yesterday"
    elif 5 <= diff <= 8:
        return "week_ago"
    elif 25 <= diff <= 35:
        return "month_ago"
    elif 355 <= diff <= 375:
        return "year_ago"
    return None


def extract_cell(cell):
    """
    From a table cell like '₹15,584 <span>(+142)</span>',
    return (price_float, change_float).
    Modifies the cell in-place (removes the span).
    """
    change = None
    span = cell.find("span")
    if span:
        m = re.search(r"([+-]?\d[\d,]*)", span.get_text())
        if m:
            try:
                change = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        span.decompose()
    price = clean_price(cell.get_text(strip=True))
    return price, change


def get_date_tbody(soup: BeautifulSoup):
    """
    Both gold and silver pages have two <tbody class="tablebody">:
      [0] = gram/weight calculator rows
      [1] = date-indexed history rows  ← we want this one
    """
    tbodies = soup.find_all("tbody", class_="tablebody")
    return tbodies[1] if len(tbodies) > 1 else (tbodies[0] if tbodies else None)


# ── Gold ───────────────────────────────────────────────────────────────────────

def scrape_gold_summary(soup: BeautifulSoup, today: date) -> dict:
    """
    Returns summary periods: today / yesterday / week_ago
    Gold columns (per gram): DATE | 24K | 22K
    """
    result = {"22k": {}, "24k": {}}

    # Today from price cards (most reliable)
    span_22k = soup.find(id="22K-price")
    span_24k = soup.find(id="24K-price")
    if span_22k:
        result["22k"]["today"] = clean_price(span_22k.get_text())
    if span_24k:
        result["24k"]["today"] = clean_price(span_24k.get_text())

    tbody = get_date_tbody(soup)
    if tbody:
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            row_date = parse_gr_date(cells[0].get_text(strip=True))
            if not row_date:
                continue
            period = date_to_period(row_date, today)
            if not period:
                continue
            p24, _ = extract_cell(cells[1])
            p22, _ = extract_cell(cells[2])
            if p24 and period not in result["24k"]:
                result["24k"][period] = p24
            if p22 and period not in result["22k"]:
                result["22k"][period] = p22

    return result


def scrape_gold_10days(soup: BeautifulSoup) -> list:
    """
    Returns all rows from the 10-day gold history table.
    Each row: { date, 24k_per_gram, 22k_per_gram, 24k_change, 22k_change }

    Website table header: DATE | 24K | 22K  (prices are per gram)
    """
    rows = []
    tbody = get_date_tbody(soup)
    if not tbody:
        return rows

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        row_date = parse_gr_date(cells[0].get_text(strip=True))
        if not row_date:
            continue
        p24, c24 = extract_cell(cells[1])
        p22, c22 = extract_cell(cells[2])
        rows.append({
            "date":          row_date.isoformat(),
            "24k_per_gram":  p24,
            "22k_per_gram":  p22,
            "24k_change":    c24,
            "22k_change":    c22,
        })

    return rows


# ── Silver ─────────────────────────────────────────────────────────────────────

def scrape_silver_summary(soup: BeautifulSoup, today: date) -> dict:
    """
    Returns summary periods: today / yesterday / week_ago
    Silver table columns: DATE | 10 GRAM | 100 GRAM | 1 KG
    We store per_gram = 10g_price / 10
    """
    result = {}
    tbody = get_date_tbody(soup)

    if tbody:
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            row_date = parse_gr_date(cells[0].get_text(strip=True))
            if not row_date:
                continue
            period = date_to_period(row_date, today)
            if not period or period in result:
                continue
            # cells[1] = per 10 gram price  →  divide by 10 for per gram
            price_10g = clean_price(cells[1].get_text(strip=True))
            if price_10g:
                result[period] = round(price_10g / 10, 2)

    # Fallback from ticker (shows per kg: ₹2,60,000)
    if "today" not in result:
        for item in soup.select(".gr-wealth-ticker-item"):
            label = item.select_one(".gr-wealth-ticker-label")
            value = item.select_one(".gr-wealth-ticker-value")
            if label and "silver" in label.get_text().lower() and value:
                price_kg = clean_price(value.get_text())
                if price_kg:
                    result["today"] = round(price_kg / 1000, 2)
                break

    return result


def scrape_silver_10days(soup: BeautifulSoup) -> list:
    """
    Returns all rows from the 10-day silver history table.
    Each row: { date, per_gram, per_10g, per_kg, change_per_kg }

    Website table header: DATE | 10 GRAM | 100 GRAM | 1 KG
    """
    rows = []
    tbody = get_date_tbody(soup)
    if not tbody:
        return rows

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        row_date = parse_gr_date(cells[0].get_text(strip=True))
        if not row_date:
            continue

        per_10g  = clean_price(cells[1].get_text(strip=True))
        per_100g = clean_price(cells[2].get_text(strip=True))
        per_kg, change_per_kg = extract_cell(cells[3])

        rows.append({
            "date":          row_date.isoformat(),
            "per_gram":      round(per_10g / 10, 2) if per_10g else None,
            "per_10g":       per_10g,
            "per_100g":      per_100g,
            "per_kg":        per_kg,
            "change_per_kg": change_per_kg,
        })

    return rows


# ── JSON writers ───────────────────────────────────────────────────────────────

def write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK]  {path}")


def update_history(gold: dict, silver: dict, today_str: str) -> None:
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
        "silver_today_per_gram": silver.get("today"),
    })
    history = sorted(history, key=lambda x: x["date"])[-365:]
    write_json(history_path, history)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    today     = date.today()
    today_str = today.isoformat()
    now_str   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("[INFO] Scraping gold …")
    gold_soup = fetch(GOLD_URL)
    gold      = scrape_gold_summary(gold_soup, today)
    gold_10d  = scrape_gold_10days(gold_soup)

    print("[INFO] Scraping silver …")
    silver_soup = fetch(SILVER_URL)
    silver      = scrape_silver_summary(silver_soup, today)
    silver_10d  = scrape_silver_10days(silver_soup)

    print(f"[DEBUG] Gold 22K      : {gold['22k']}")
    print(f"[DEBUG] Gold 24K      : {gold['24k']}")
    print(f"[DEBUG] Silver /gram  : {silver}")
    print(f"[DEBUG] Gold 10-day rows   : {len(gold_10d)}")
    print(f"[DEBUG] Silver 10-day rows : {len(silver_10d)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── gold_prices.json  (single file — all data) ────────────────────────────
    write_json(f"{OUTPUT_DIR}/gold_prices.json", {
        "city":         "Chennai",
        "currency":     "INR",
        "last_updated": now_str,
        "date":         today_str,
        "gold": {
            "unit":        "per_gram",
            "summary":     gold,
            "last_10_days": gold_10d,
        },
        "silver": {
            "summary":     silver,
            "last_10_days": silver_10d,
        },
    })

    # ── history.json  (365-day rolling log, kept separate as it grows daily) ──
    update_history(gold, silver, today_str)

    print("[DONE] All files updated.")


if __name__ == "__main__":
    main()
