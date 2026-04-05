# Grading Algorithm

## Price Value (35% weight)

Compare listing price to market_price_median:

| Grade | Threshold |
|-------|-----------|
| A+ | 40%+ below median |
| A | 25-40% below |
| B | 10-25% below |
| C | Within 10% of median |
| D | 10-25% above |
| F | 25%+ above |

## Seller Trust (25% weight)

Score each signal then take the weighted average:

- **Account age:** <3mo=F, 3-12mo=C, 1-3yr=B, 3yr+=A
- **Star rating:** 4.5+=A, 4.0-4.4=B, 3.5-3.9=C, <3.5=D, none=C
- **Review count:** 10+=A, 5-9=B, 1-4=C, 0=D
- **Response time:** <1hr=A, few hours=B, slow/none=C

## Listing Quality (20% weight)

- **Photos:** 5+ original=A, 3-4=B, 1-2=C, stock/catalog=F
- **Description:** detailed specs+condition+reason=A, decent=B, minimal=C, vague/copy-paste=D

## Red Flags (15% weight - penalty only)

### CRITICAL (caps grade at C max)
- Price 50%+ below market
- Brand-new account + high-value item
- Stock/catalog photos
- Shipping-only local item

### HIGH (deduct from score)
- Single blurry photo
- Location mismatch
- Many identical items from same seller
- Vague description

## Condition vs Price (5% weight)

- "Like new" at used price = A (bonus)
- "Good" at near-new price = D (penalty)
- Consistent = B

## Final Grade Calculation

Convert each category grade to numeric (A+=4.3, A=4.0, B=3.0, C=2.0, D=1.0, F=0), apply weights, convert back:

| Score Range | Grade |
|-------------|-------|
| 3.8+ | A+ |
| 3.5-3.79 | A |
| 2.5-3.49 | B |
| 1.5-2.49 | C |
| 0.5-1.49 | D |
| <0.5 | F |

If any critical red flag is present, cap the final grade at C.

Write a 2-3 sentence summary explaining the grade.

## Grade Breakdown JSON Format

Store in the CSV `grade_breakdown` column as a JSON string:

```json
{"priceValue":"B","sellerTrust":"A","listingQuality":"B","redFlags":"A","conditionConsistency":"B"}
```
