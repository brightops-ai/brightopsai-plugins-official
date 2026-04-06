import { useState, useMemo } from 'react'
import { ArrowSquareOut, TrendUp, Info, SlidersHorizontal } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import GradeBadge from '@/components/GradeBadge'

interface FlipRow {
  listing: Listing
  ebayFees: number
  estShipping: number
  profit: number
  roi: number
}

function computeFlips(listings: Listing[]): FlipRow[] {
  const rows: FlipRow[] = []
  for (const l of listings) {
    if (l.marketPriceMedian <= 0 || l.price <= 0 || l.grade === 'F') continue
    const ebayFees = Math.round(l.marketPriceMedian * 0.13)
    const estShipping = l.price > 400 ? 25 : l.price > 100 ? 15 : 10
    const profit = Math.round(l.marketPriceMedian - ebayFees - estShipping - l.price)
    if (profit > 0) {
      const roi = Math.round((profit / l.price) * 100)
      rows.push({ listing: l, ebayFees, estShipping, profit, roi })
    }
  }
  return rows.sort((a, b) => b.roi - a.roi)
}

interface FlipsViewProps {
  listings: Listing[]
  onSelect: (listing: Listing) => void
}

export default function FlipsView({ listings, onSelect }: FlipsViewProps) {
  const allFlips = useMemo(() => computeFlips(listings), [listings])
  const [minProfit, setMinProfit] = useState(0)

  const maxProfit = useMemo(
    () => allFlips.length > 0 ? Math.max(...allFlips.map(f => f.profit)) : 0,
    [allFlips]
  )

  const flips = useMemo(
    () => allFlips.filter(f => f.profit >= minProfit),
    [allFlips, minProfit]
  )

  if (allFlips.length === 0) {
    return (
      <div className="flips-empty">
        <Info size={32} weight="duotone" color="var(--color-accent)" />
        <h3 className="flips-empty-title">No flip opportunities yet</h3>
        <p className="flips-empty-desc">
          No listings in this search have a market median price high enough
          to turn a profit after eBay fees (13%) and estimated shipping.
          Try broadening your search or check a different search session.
        </p>
        <div className="flips-empty-hints">
          <span className="flips-empty-hint">Profit = median sell price − eBay fees − shipping − buy price</span>
          <span className="flips-empty-hint">Items graded F are excluded</span>
          <span className="flips-empty-hint">Shipping: $10 (&lt;$100), $15 ($100–400), $25 ($400+)</span>
        </div>
      </div>
    )
  }

  const totalProfit = flips.reduce((s, f) => s + f.profit, 0)
  const totalInvestment = flips.reduce((s, f) => s + f.listing.price, 0)
  const avgRoi = totalInvestment > 0 ? Math.round((totalProfit / totalInvestment) * 100) : 0

  return (
    <div className="flips-view">
      <div className="flips-summary">
        <div className="flips-summary-item">
          <span className="mono-label">Flippable</span>
          <span className="flips-summary-value">{flips.length} items</span>
        </div>
        <div className="flips-summary-item">
          <span className="mono-label">Total Investment</span>
          <span className="flips-summary-value">${totalInvestment.toLocaleString()}</span>
        </div>
        <div className="flips-summary-item">
          <span className="mono-label">Est. Total Profit</span>
          <span className="flips-summary-value flips-summary-value--accent">
            ${totalProfit.toLocaleString()}
          </span>
        </div>
        <div className="flips-summary-item">
          <span className="mono-label">Avg ROI</span>
          <span className="flips-summary-value flips-summary-value--accent">
            {avgRoi}%
          </span>
        </div>
      </div>

      <div className="profit-slider">
        <div className="profit-slider-header">
          <SlidersHorizontal size={14} color="var(--color-accent)" />
          <span className="profit-slider-label">Min Profit</span>
          <span className="profit-slider-value">${minProfit}</span>
        </div>
        <input
          type="range"
          min={0}
          max={maxProfit}
          step={1}
          value={minProfit}
          onChange={e => setMinProfit(Number(e.target.value))}
          className="profit-slider-input"
          aria-label="Minimum profit threshold"
        />
        <div className="profit-slider-range">
          <span>$0</span>
          <span>${maxProfit}</span>
        </div>
      </div>

      {flips.length === 0 ? (
        <div className="empty-state">
          No flips meet the ${minProfit} minimum profit threshold.
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Grade</th>
                <th>Title</th>
                <th>Buy</th>
                <th>Sell (Median)</th>
                <th>Fees</th>
                <th>Shipping</th>
                <th>Net Profit</th>
                <th>ROI</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {flips.map(({ listing: l, ebayFees, estShipping, profit, roi }) => (
                <tr key={l.id} onClick={() => onSelect(l)} tabIndex={0} role="button"
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(l) } }}>
                  <td><GradeBadge grade={l.grade} size="sm" /></td>
                  <td className="table-cell-title">{l.title}</td>
                  <td className="table-cell-price">${l.price.toLocaleString()}</td>
                  <td>${l.marketPriceMedian.toLocaleString()}</td>
                  <td className="text-muted">${ebayFees}</td>
                  <td className="text-muted">${estShipping}</td>
                  <td>
                    <span className="flip-profit">
                      <TrendUp size={12} weight="bold" />
                      ${profit}
                    </span>
                  </td>
                  <td>
                    <span className="flip-roi">{roi}%</span>
                  </td>
                  <td>
                    <a
                      href={l.listingUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={e => e.stopPropagation()}
                      className="btn link-btn"
                    >
                      <ArrowSquareOut size={11} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
