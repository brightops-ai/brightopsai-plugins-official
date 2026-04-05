# Shipping Estimates & Fee Calculations

Use the user's location zip code as the origin. Estimate shipping to both coasts to create a realistic range.

## Shipping Estimate Table

| Item Category | Weight Est. | Ship Low (nearby) | Ship High (cross-country) | Best Method |
|--------------|-------------|-------------------|--------------------------|-------------|
| Batteries/small tools | 1-3 lbs | $8 | $14 | USPS Priority Small Flat Rate ($10.40) |
| Power tool kits | 5-10 lbs | $12 | $22 | USPS Priority Medium Flat Rate ($17.10) or UPS Ground |
| Combo kits/large tools | 10-20 lbs | $18 | $32 | UPS Ground or USPS Priority Large Flat Rate ($22.80) |
| LEGO small sets (<500pc) | 1-2 lbs | $7 | $12 | USPS First Class or Priority Small FR |
| LEGO medium sets (500-2000pc) | 3-6 lbs | $12 | $20 | USPS Priority Medium FR |
| LEGO large sets (2000+pc) | 8-15 lbs | $18 | $30 | UPS Ground |
| Guitars (electric) | 10-15 lbs | $35 | $55 | UPS Ground (oversized) |
| Guitars (acoustic) | 8-12 lbs | $40 | $65 | UPS Ground (oversized) |
| KitchenAid mixers | 20-30 lbs | $25 | $40 | UPS Ground |
| Small kitchen items | 2-5 lbs | $9 | $16 | USPS Priority |
| Blenders (Vitamix) | 10-15 lbs | $15 | $28 | UPS Ground |
| Gaming consoles | 5-8 lbs | $12 | $20 | USPS Priority Medium FR |
| Sneakers (1 pair) | 3-4 lbs | $10 | $16 | USPS Priority |
| Camera bodies/lenses | 2-4 lbs | $10 | $16 | USPS Priority (insured) |
| Collectibles/cards | <1 lb | $5 | $8 | USPS First Class |
| Phones/AirPods | <1 lb | $5 | $9 | USPS First Class or Priority Small FR |

**Pro tip:** When searching eBay sold listings, check whether the sold price included free shipping — if so, the seller ate the shipping cost and that must be subtracted from the sale price for a true comparable.

## CSV Columns for Resale Mode

These additional columns appear in the CSV when running in resale arbitrage mode:

| Column | Description |
|--------|-------------|
| `shipping_estimate_low` | Cheapest shipping option (nearby buyer) |
| `shipping_estimate_high` | Most expensive (cross-country) |
| `ebay_fees` | 13% of eBay median sold price |
| `net_profit_low` | Profit if shipping is high (worst case) |
| `net_profit_high` | Profit if shipping is low (best case) |
| `roi_low` | Worst-case ROI percentage |
| `roi_high` | Best-case ROI percentage |
