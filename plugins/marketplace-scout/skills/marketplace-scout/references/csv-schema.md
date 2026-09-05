# CSV schema and search index

Required shapes for `${CLAUDE_PLUGIN_DATA}/data/*.csv` and `${CLAUDE_PLUGIN_DATA}/data/searches.json`. See `examples/sample-output.csv` and `examples/sample-searches.json` for filled examples.

## CSV header

Write this header as the first row, in this order (41 columns):

```
id,search_term,title,price,market_price_low,market_price_high,market_price_median,price_vs_market,grade,grade_breakdown,summary,condition,seller_name,seller_rating,seller_reviews,seller_account_age,seller_response_time,location,distance,description,photo_count,photos_original,red_flags,listing_url,listing_age,vendor_url,vendor_price,review_url,review_score,shipping_estimate_low,shipping_estimate_high,ebay_fees,net_profit_low,net_profit_high,roi_low,roi_high,platform,image_url,date_scraped,search_location,search_radius
```

## Grading output rules

- Only output grades from the `GradeLetter` union: `A+`, `A`, `B`, `C`, `D`, `F`. Never output grade `X` or any other value.
- If grading fails or specs cannot be determined after full investigation, default to grade `F` with a red flag explanation (e.g. `"Specs unverified — graded conservatively as F"`). Do not use a placeholder grade.
- `grade_breakdown` must be a JSON object with exactly 5 string fields: `priceValue`, `sellerTrust`, `listingQuality`, `redFlags`, `conditionConsistency`. Each value must be a single letter grade (`A+`, `A`, `B`, `C`, `D`, or `F`) as a string — never a number, array, or nested object.

Store `grade_breakdown` in the CSV as a JSON string:

```json
{"priceValue":"B","sellerTrust":"A","listingQuality":"B","redFlags":"A","conditionConsistency":"B"}
```

## Per-field rules

- `red_flags` is comma-separated.
- `price_vs_market` is a signed integer percentage (negative = below market).
- Escape commas in text fields by wrapping the field in double quotes.
- Always populate `platform` with `"facebook"` or `"ebay"` — the dashboard reads this field directly and must not infer platform from URL parsing.
- Never leave price-like fields (`price`, `market_price_low`, `market_price_high`, `market_price_median`, `vendor_price`, `shipping_estimate_low`, `shipping_estimate_high`, `ebay_fees`, `net_profit_low`, `net_profit_high`) empty — use `0` for unknown values.
- Always include pre-computed `shipping_estimate_low`, `shipping_estimate_high`, `ebay_fees`, `net_profit_low`, `net_profit_high`, `roi_low`, and `roi_high` with real calculated values — the dashboard should not re-derive these.
- `image_url` may be empty when no image could be extracted.
- Validate the final CSV row count matches the expected listing count before writing the file.

## `searches.json` shape

The file is a JSON object with a `searches` array. Create it if missing (`{"searches": []}`). Append one session object per run:

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

Verify the file is valid JSON before appending.
