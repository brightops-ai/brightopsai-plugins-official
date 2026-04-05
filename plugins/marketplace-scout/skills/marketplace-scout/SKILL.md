---
name: marketplace-scout
description: >
  This skill should be used when the user asks to "search Facebook Marketplace",
  "find deals on Marketplace", "compare marketplace listings", "find used products",
  "search for deals", "find items to flip", "marketplace arbitrage", or "resell for profit".
  Also trigger when the user mentions secondhand goods, used electronics, local marketplace
  shopping, price comparisons for items on a marketplace, or wants to find items to buy and
  resell. Also activates for "check marketplace prices", "browse marketplace near me",
  or "show me a dashboard of marketplace deals". Covers both personal deal-finding and
  resale arbitrage workflows.
argument-hint: "[product or category to search for]"
allowed-tools:
  - mcp__plugin_playwright_playwright__browser_navigate
  - mcp__plugin_playwright_playwright__browser_snapshot
  - mcp__plugin_playwright_playwright__browser_click
  - mcp__plugin_playwright_playwright__browser_type
  - mcp__plugin_playwright_playwright__browser_wait_for
  - mcp__plugin_playwright_playwright__browser_press_key
  - mcp__plugin_playwright_playwright__browser_hover
  - mcp__plugin_playwright_playwright__browser_take_screenshot
  - mcp__plugin_playwright_playwright__browser_evaluate
  - mcp__plugin_playwright_playwright__browser_select_option
  - mcp__plugin_playwright_playwright__browser_run_code
  - mcp__plugin_playwright_playwright__browser_tabs
  - WebSearch
  - WebFetch
  - Write
  - Read
  - Bash
  - Edit
---

# Marketplace Scout

A marketplace research assistant that searches Facebook Marketplace, analyzes listings against fair market prices, grades them A+ through F, saves results to CSV, and launches an interactive dashboard.

## References

- **`references/grading-algorithm.md`** — Full grading weights, formulas, red flag definitions, and grade boundaries
- **`references/resale-arbitrage.md`** — Complete resale/flip mode: profitable categories, eBay cross-referencing, modified grading weights
- **`references/shipping-estimates.md`** — Shipping cost table by item category and eBay fee calculations

## Examples

- **`examples/sample-output.csv`** — 3-row sample demonstrating the 37-column CSV schema with proper escaping, JSON-in-CSV, and signed percentages
- **`examples/sample-searches.json`** — Sample search index entry showing the expected format

## Dashboard

The `assets/dashboard/` directory contains a complete Vite + React + TypeScript dashboard application. On first run, if no `dashboard/` directory exists in the working directory, scaffold it by copying `assets/dashboard/` to `./dashboard/` and running `npm install`. On subsequent runs, just update the data files and tell the user to refresh.

## Workflow

### 1. Gather Search Parameters

Ask the user (one at a time via AskUserQuestion):

1. "What are you looking for?" — accept comma-separated items
2. "Search location?" — city and state, default to last used if available
3. "Search radius in miles?" — default 25
4. "Max price? (optional, press Enter to skip)"
5. "Min condition? (new, like new, good, fair, any)" — default "any"

Parse the first answer into separate search terms by splitting on commas.

### 2. Verify Facebook Login

Navigate to `https://www.facebook.com/marketplace/` using Playwright. Take a snapshot. If a login form appears, tell the user to log in manually in the Playwright browser and confirm when ready.

### 3. Search Facebook Marketplace

For each search term:

1. Navigate to `https://www.facebook.com/marketplace/search/?query={encoded_search_term}&exact=false`
2. Set location and radius on the first search only (clear location field, type slowly, select autocomplete suggestion, set radius, apply)
3. Scroll 2-3 times (random 1-3s pauses) to load results
4. Extract up to 30 listings: title, price, location, URL, condition
5. Filter out wrong products, over-budget items, below-condition items
6. Between search terms, wait 30-60 seconds (use this time for market research)

### 4. Market Research

For each unique product type, use WebSearch and WebFetch:

- **Fair market price:** Search `"{product}" sold site:ebay.com` and `"{product}" price site:swappa.com` — extract low/high/median prices
- **Price ceiling:** Search `"{product}" site:apple.com/shop/refurbished` (or manufacturer refurbished)
- **Vendor link:** Search `"{product}" buy official site` — get retail URL and price
- **Review link:** Search `"{product}" review site:wirecutter.com OR site:tomsguide.com OR site:rtings.com` — get URL and score

### 5. Tiered Deep-Dive

Sort listings by price attractiveness. Deep-dive priority:

1. **Vague listings that could be great deals** — titles missing key specs where price suggests a higher-end config. These need investigation first.
2. **Top 10-15 by price attractiveness** — lowest price relative to market research.

For each deep-dive listing:
- Navigate to the listing URL, extract full description, photo count, condition, days listed
- **Click through ALL photos** — look for "About This Mac" screenshots, spec stickers, serial numbers, system profiler screens
- Check seller profile: name, rating, reviews, account age, response time, other listings
- For vague listings, escalate: read description, check photos, check structured attributes, visit seller profile. If still unknown, mark "Specs unverified" and grade conservatively.

Anti-detection: wait 2-5s between listings, 5-15s pause every 5 listings.

### 6. Grade Each Listing

Consult `references/grading-algorithm.md` for the full grading algorithm. Apply the five weighted categories (Price Value 35%, Seller Trust 25%, Listing Quality 20%, Red Flags 15%, Condition vs Price 5%) and compute the final grade.

For resale arbitrage mode, consult `references/resale-arbitrage.md` for modified grading weights that prioritize flip profitability, and `references/shipping-estimates.md` for shipping cost estimates and eBay fee calculations.

### 7. Save to CSV and Update Search Index

Generate timestamped filename: `marketplace_results_{YYYY-MM-DD_HH-mm}.csv`

Write to `./data/{filename}` with columns:

```
id,search_term,title,price,market_price_low,market_price_high,market_price_median,price_vs_market,grade,grade_breakdown,summary,condition,seller_name,seller_rating,seller_reviews,seller_account_age,seller_response_time,location,distance,description,photo_count,photos_original,red_flags,listing_url,listing_age,vendor_url,vendor_price,review_url,review_score,shipping_estimate_low,shipping_estimate_high,ebay_fees,net_profit_low,net_profit_high,roi_low,roi_high,date_scraped,search_location,search_radius
```

See `examples/sample-output.csv` for the expected format. Rules:
- `grade_breakdown` is a JSON string
- `red_flags` is comma-separated
- `price_vs_market` is a signed integer percentage (negative = below market)
- Escape commas in text fields by wrapping in double quotes

Update `./data/searches.json` (create if missing) — append a new entry:

```json
{
  "id": "YYYY-MM-DD_HH-mm",
  "timestamp": "ISO 8601",
  "label": "Short summary of search terms",
  "searchTerms": ["term1", "term2"],
  "location": "City, ST",
  "radius": 25,
  "maxPrice": null,
  "csvFile": "marketplace_results_YYYY-MM-DD_HH-mm.csv",
  "listingCount": 32,
  "gradeDistribution": {"A": 3, "B": 11, "C": 11, "D": 3, "F": 4}
}
```

Copy both files to `./dashboard/public/data/` and maintain `latest.csv` as a copy of the newest CSV.

### 8. Launch Dashboard

Check if the dashboard exists at `./dashboard/`. If not, scaffold it from the plugin's `assets/dashboard/` directory:

```bash
cp -r "${CLAUDE_PLUGIN_ROOT}/skills/marketplace-scout/assets/dashboard/" ./dashboard/
cd dashboard && npm install
```

Check if the dev server is already running on port 5173. If running, tell the user to refresh. If not:

```bash
cd dashboard && npm run dev
```

Summarize findings: total listings per search term, grade distribution, top 3 deals with grades and prices, critical red flags, and changes from prior searches if applicable.

## Guardrails

- **Anti-detection:** Randomize wait times between actions (2-5s between listings, 30-60s between searches, 5-15s every 5 listings). Never navigate in predictable patterns.
- **Location persistence:** Only set location once for the first search. Subsequent searches inherit it.
- **Photo investigation:** Always click through all listing photos. Spec details hidden in photos are the difference between a bad grade and a good one.
- **Conservative grading:** When specs cannot be confirmed after full investigation, assume the lower-end configuration. Note the potential upside.
- **Data integrity:** Always escape CSV fields containing commas. Verify `searches.json` has valid JSON before appending.
- **Dashboard scaffolding:** Only copy `assets/dashboard/` on first run. Never overwrite an existing dashboard directory — the user may have customized it.
