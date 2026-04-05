# Resale Arbitrage Mode

When the user asks to find items to **flip**, **resell**, or do **marketplace arbitrage**, the goal shifts from "find the best deal for personal use" to "find items that can be bought locally and resold on eBay for 20%+ profit after fees."

## Step A: Identify Profitable Categories

Research the best resale categories. Consistently profitable categories for FB Marketplace to eBay arbitrage:

1. **Power Tools** (Milwaukee, DeWalt, Makita) — 20-60% margins, fast sellers
2. **LEGO** (retired/sealed sets) — 30-200% margins, collectors pay premium
3. **Musical Instruments** (Fender, Gibson guitars) — 25-100% margins
4. **Kitchen/Home** (KitchenAid mixers, Vitamix, Dyson) — 20-50% margins
5. **Gaming** (consoles, retro games, limited editions) — 25-50% margins
6. **Apple Electronics** (iPhones, AirPods, iPads) — 15-30% margins, very fast
7. **Camera Gear** (Sony, Canon lenses) — 20-40% margins
8. **Sneakers/Streetwear** (Jordans, Dunks, vintage tees) — 30-100% margins
9. **Collectibles** (Funko Pops, trading cards, vintage toys) — 50-200% margins
10. **Fitness Equipment** (Bowflex, Peloton, Rogue) — 25-50% margins

Ask the user how many categories to cover and their budget per item. Default: all 10 categories, max $1000 per item, minimum 20% profit margin.

### Search Terms Per Category

- Power Tools: "Milwaukee tool", "DeWalt kit", "Makita"
- LEGO: "LEGO sealed retired", "LEGO Star Wars sealed"
- Guitars: "Fender guitar", "Gibson guitar", "guitar amp"
- Kitchen: "KitchenAid", "Vitamix", "Dyson"
- Gaming: "Nintendo Switch", "PS5 bundle", "retro console"
- Apple: "iPhone Pro", "AirPods Pro", "iPad"
- Cameras: "Sony camera", "Canon lens"
- Sneakers: "Jordan 1", "Nike Dunk", "Yeezy"
- Collectibles: "Funko Pop", "Pokemon sealed", "trading cards"
- Fitness: "Bowflex dumbbells", "Peloton", "weight plates"

Collect at least 5 listings per category.

## Step B: Cross-Reference eBay Sold Prices

For each promising listing, use WebSearch to find the eBay sold price:

Search: `"{exact product name and model}" sold site:ebay.com`

Extract:
- eBay sold price (median of recent sold listings)
- Number of recent sales (indicates demand/velocity)
- Average days to sell

## Step C: Calculate Profit After Fees

```
eBay fees = 13% of sale price (includes final value fee + payment processing)
Shipping = range estimate based on item category (see shipping-estimates.md)
Net profit LOW = eBay sold price - eBay fees - shipping HIGH - buy price
Net profit HIGH = eBay sold price - eBay fees - shipping LOW - buy price
ROI LOW = Net profit LOW / buy price x 100
ROI HIGH = Net profit HIGH / buy price x 100
```

Only include items with **20%+ ROI in the best case (roi_high)**. Flag items where roi_low drops below 10% as "thin margin" in red_flags.

## Step D: Grade for Resale (Modified Weights)

- **Profit Margin (40% weight)**: ROI after all eBay fees and shipping
  - A+: 60%+ ROI
  - A: 40-60% ROI
  - B: 20-40% ROI
  - C: 10-20% ROI (marginal)
  - D: <10% ROI (not worth the effort)

- **Sell Speed (25% weight)**: How fast it moves on eBay
  - A: Sells in 1-3 days (batteries, Apple products, popular tools)
  - B: Sells in 3-7 days (most tools, kitchen items, gaming)
  - C: Sells in 7-14 days (guitars, LEGO, collectibles)
  - D: Sells in 14+ days (niche items)

- **Risk Level (20% weight)**: Chance of problems
  - A: New/sealed, brand-name, easy to verify authenticity
  - B: Used but verifiable condition, well-known brand
  - C: Condition hard to assess, may need testing
  - D: Counterfeits common, condition critical, fragile shipping

- **Effort (15% weight)**: Work involved in the flip
  - A: Buy, photograph, list, ship in a flat rate box
  - B: Needs cleaning/testing, standard packaging
  - C: Needs careful packaging, heavy/awkward to ship
  - D: Needs repairs, complex shipping, lots of buyer questions

## Step E: Present Results

For each item, include a detailed flip analysis in the summary field:

```
GOOD FLIP: Buy $70 on FBMP -> Sell $120 on eBay.
eBay fees (13%): $16. Shipping: $10-17 (USPS Priority Medium FR from 30078).
Net profit: $17-24 (ROI: 24-34%). Sells in 3-5 days. Low risk — sealed new item.
```

Always show the shipping range (low = nearby buyer, high = cross-country), the fee amount, and both worst-case and best-case profit/ROI.

Sort results by ROI descending. Group by category. Present a "Top 10 Best Flips" summary table showing: Item, Buy Price, eBay Sell Price, Net Profit, ROI%, Days to Sell.

## Step F: Investigate Ambiguous Listings

Many of the best flip opportunities hide behind vague listings — a seller who doesn't know what they have often prices it too low. When encountering a vague listing at an unexpectedly low price:

1. Click into the listing and read the full description
2. Click through ALL photos — look for model numbers, serial numbers, brand markings
3. Check structured attributes (Facebook sometimes auto-fills brand/model)
4. If still ambiguous, check the seller's other listings for context
5. Cross-reference whatever is found on eBay to verify the profit potential

The best flips often come from listings titled things like "guitar" ($150) that turn out to be a Fender Player Stratocaster ($600 on eBay).
