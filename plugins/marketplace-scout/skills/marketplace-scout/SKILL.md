---
name: marketplace-scout
description: >
  This skill should be used when the user asks to "search Facebook Marketplace",
  "find deals on Marketplace", "compare marketplace listings", "find used products",
  "search for deals", "find items to flip", "marketplace arbitrage", "resell for profit",
  "check marketplace prices", "browse marketplace near me", or "show me a dashboard of
  marketplace deals". Also covers mentions of secondhand goods, used electronics, local
  marketplace shopping, price comparisons, or buying items to resell. Supports both
  personal deal-finding and resale arbitrage workflows.
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
  - AskUserQuestion
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
- **`references/csv-schema.md`** — 41-column CSV header, per-field rules, grading output shape, and `searches.json` index
- **`references/resale-arbitrage.md`** — Complete resale/flip mode: profitable categories, eBay cross-referencing, modified grading weights
- **`references/shipping-estimates.md`** — Shipping cost table by item category and eBay fee calculations
- **`references/image-extraction.md`** — Playwright code pattern for extracting product images from listing pages
- **`references/anti-detection.md`** — Wait timings and scroll/wait policy for Marketplace browser loops
- **`references/dashboard-guidelines.md`** — Accessibility, styling, and responsive rules for dashboard modifications

## Examples

- **`examples/sample-output.csv`** — 3-row sample demonstrating the 41-column CSV schema with proper escaping, JSON-in-CSV, and signed percentages
- **`examples/sample-searches.json`** — Sample search index entry showing the expected format

## Dashboard

The `assets/dashboard/` directory contains a complete Vite + React + TypeScript dashboard application. On first run, if no `dashboard/` directory exists in the working directory, scaffold it by copying `assets/dashboard/` to `./dashboard/` and running `npm install`. On subsequent runs, just update the data files and tell the user to refresh.

## Workflow

### Prerequisites

Confirm the Playwright browser tools (`browser_navigate` and the rest of the `mcp__plugin_playwright_playwright__browser_*` set) are available in this session. If they are missing, stop: tell the user to run `/plugin install playwright@claude-plugins-official`, then `/reload-plugins` or restart, and invoke this skill again. Do not retry the browser loop without those tools.

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

Read `references/anti-detection.md` before navigating or scrolling. Then for each search term:

1. Navigate to `https://www.facebook.com/marketplace/search/?query={encoded_search_term}&exact=false`
2. Set location and radius on the first search only (clear location field, select autocomplete suggestion, set radius, apply)
3. Scroll to load results
4. Extract up to 30 listings: title, price, location, URL, condition
5. Filter out wrong products, over-budget items, below-condition items
6. Between search terms, wait per that file (use this time for market research)

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

Follow `references/anti-detection.md` between listing visits. For each deep-dive listing:
- Navigate to the listing URL, extract full description, photo count, condition, days listed
- **Click through ALL photos** — look for "About This Mac" screenshots, spec stickers, serial numbers, system profiler screens
- **Extract the product image URL** for the dashboard card display (see image extraction below)
- Check seller profile: name, rating, reviews, account age, response time, other listings
- For vague listings, escalate: read description, check photos, check structured attributes, visit seller profile. If still unknown, mark "Specs unverified" and grade conservatively.

**Image extraction** — save a product photo locally for each listing. Facebook CDN URLs expire quickly, so images must be downloaded during the scrape and saved to `./data/images/`.

For each listing page already open in Playwright:
Extract a product image per listing and save to `./data/images/{listing_id}.jpg`. Set `image_url` in the CSV to `/data/images/{listing_id}.jpg`. Leave `image_url` empty if no image can be extracted — the dashboard shows a styled placeholder with the search term. See `references/image-extraction.md` for the browser code pattern and fallback selectors.

### 6. Grade Each Listing

Consult `references/grading-algorithm.md` for the full grading algorithm. Apply the five weighted categories (Price Value 35%, Seller Trust 25%, Listing Quality 20%, Red Flags 15%, Condition vs Price 5%) and compute the final grade.

For resale arbitrage mode, consult `references/resale-arbitrage.md` for modified grading weights that prioritize flip profitability, and `references/shipping-estimates.md` for shipping cost estimates and eBay fee calculations.

Read `references/csv-schema.md` for grading output rules before recording a grade.

### 7. Save to CSV and Update Search Index

Read `references/csv-schema.md` before writing the CSV.

Generate timestamped filename: `marketplace_results_{YYYY-MM-DD_HH-mm}.csv`

Write to `./data/{filename}` using that schema. See `examples/sample-output.csv` for a filled example.

Update `./data/searches.json` (create if missing) — append a new entry using the `searches.json` shape in that file.

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

When modifying the dashboard, follow the compatibility rules in `references/dashboard-guidelines.md`.

## Guardrails

- **Anti-detection:** Follow `references/anti-detection.md` for wait times and scroll/wait policy.
- **Location persistence:** Only set location once for the first search. Subsequent searches inherit it.
- **Photo investigation:** Always click through all listing photos. Spec details hidden in photos are the difference between a bad grade and a good one.
- **Conservative grading:** When specs cannot be confirmed after full investigation, assume the lower-end configuration. Note the potential upside.
- **Data integrity:** Follow `references/csv-schema.md` for CSV escaping, empty-field defaults, and `searches.json` validity.
- **Dashboard scaffolding:** Only copy `assets/dashboard/` on first run. Never overwrite an existing dashboard directory — the user may have customized it.
