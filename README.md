# Gold & Silver Price API (Free)

A free self-updating JSON API for Chennai gold and silver prices, scraped daily from [goodreturns.in](https://www.goodreturns.in/gold-rates/chennai.html).

## How It Works

```
GitHub Actions (daily 8:30 AM IST)
        ↓
   scraper.py runs
        ↓
   Scrapes goodreturns.in
        ↓
   Saves JSON to /api/
        ↓
   Commits & pushes to repo
        ↓
GitHub Pages serves JSON as your free API
```

---

## Setup Steps (One-Time)

### 1. Create GitHub Repository
1. Go to https://github.com/new
2. Name it `gold-api` (or any name)
3. Set it to **Public**
4. Click **Create repository**

### 2. Push this code
```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/gold-api.git
git push -u origin main
```

### 3. Enable GitHub Pages
1. Go to your repo → **Settings** → **Pages**
2. Under **Source**, select `Deploy from a branch`
3. Branch: `main`, Folder: `/ (root)`
4. Click **Save**

### 4. Your Free API is Live!

| Endpoint | URL |
|---|---|
| All prices | `https://YOUR_USERNAME.github.io/gold-api/api/gold_prices.json` |
| Gold only | `https://YOUR_USERNAME.github.io/gold-api/api/gold.json` |
| Silver only | `https://YOUR_USERNAME.github.io/gold-api/api/silver.json` |
| Price history | `https://YOUR_USERNAME.github.io/gold-api/api/history.json` |

Replace `YOUR_USERNAME` with your GitHub username.

---

## API Response Format

### `gold_prices.json`
```json
{
  "city": "Chennai",
  "currency": "INR",
  "last_updated": "2026-09-20T03:00:00Z",
  "date": "2026-09-20",
  "gold": {
    "22k": {
      "today": 58000,
      "yesterday": 57800,
      "week_ago": 57200,
      "month_ago": 55000,
      "year_ago": 49000
    },
    "24k": {
      "today": 63000,
      "yesterday": 62800,
      "week_ago": 62000,
      "month_ago": 60000,
      "year_ago": 53000
    }
  },
  "silver": {
    "today": 850,
    "yesterday": 845,
    "week_ago": 830,
    "month_ago": 800,
    "year_ago": 700
  }
}
```

### `history.json`
```json
[
  {
    "date": "2026-09-20",
    "gold_22k_today": 58000,
    "gold_24k_today": 63000,
    "silver_today": 850
  }
]
```
History keeps the last 365 days automatically.

---

## Using in Your Mobile App

```javascript
// React Native / JavaScript
const API_URL = "https://YOUR_USERNAME.github.io/gold-api/api/gold_prices.json";

fetch(API_URL)
  .then(res => res.json())
  .then(data => {
    console.log("Gold 22K today:", data.gold["22k"].today);
    console.log("Gold 24K today:", data.gold["24k"].today);
    console.log("Silver today:", data.silver.today);
  });
```

---

## Manual Update

Go to **Actions** tab in your GitHub repo → click **Update Gold & Silver Prices** → **Run workflow**.

---

## Cost

| Service | Cost |
|---|---|
| GitHub Actions | Free (2000 min/month) |
| GitHub Pages | Free |
| Custom domain | Optional (free with .github.io) |
| **Total** | **₹0 / $0** |
