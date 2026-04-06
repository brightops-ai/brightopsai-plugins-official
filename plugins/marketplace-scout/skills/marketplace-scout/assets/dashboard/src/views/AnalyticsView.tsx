import type { Listing, FlipStats } from '@/types/listing'
import { getGradeColor } from '@/utils/grades'

interface AnalyticsViewProps {
  listings: Listing[]
  gradeDistribution: Record<string, number>
  avgPriceVsMarket: number
  top10FlipStats: FlipStats
  allFlipStats: FlipStats
}

export default function AnalyticsView({
  listings,
  gradeDistribution,
  avgPriceVsMarket,
  top10FlipStats,
  allFlipStats,
}: AnalyticsViewProps) {
  const totalListings = listings.length
  const maxGradeCount = Math.max(...Object.values(gradeDistribution), 1)

  const avgPrice = totalListings > 0
    ? Math.round(listings.reduce((s, l) => s + l.price, 0) / totalListings)
    : 0

  const conditionCounts: Record<string, number> = {}
  for (const l of listings) {
    const c = l.condition || 'Unknown'
    conditionCounts[c] = (conditionCounts[c] ?? 0) + 1
  }

  return (
    <div className="analytics-view">
      <div className="analytics-hero">
        <div className="analytics-hero-card">
          <span className="mono-label">Total Listings</span>
          <span className="analytics-hero-value">{totalListings}</span>
        </div>
        <div className="analytics-hero-card">
          <span className="mono-label">Avg Price</span>
          <span className="analytics-hero-value">${avgPrice.toLocaleString()}</span>
        </div>
        <div className="analytics-hero-card">
          <span className="mono-label">Avg vs Market</span>
          <span className="analytics-hero-value" style={{
            '--value-color': avgPriceVsMarket <= 0 ? 'var(--color-grade-a)' : 'var(--color-grade-f)',
            color: 'var(--value-color)',
          } as React.CSSProperties}>
            {avgPriceVsMarket > 0 ? '+' : ''}{avgPriceVsMarket}%
          </span>
        </div>
        <div className="analytics-hero-card">
          <span className="mono-label">Flippable Items</span>
          <span className="analytics-hero-value">{allFlipStats.itemCount}</span>
        </div>
        <div className="analytics-hero-card">
          <span className="mono-label">Est. Total Profit</span>
          <span className="analytics-hero-value analytics-hero-value--accent">
            ${allFlipStats.totalProfit.toLocaleString()}
          </span>
        </div>
        <div className="analytics-hero-card">
          <span className="mono-label">Top 10 ROI</span>
          <span className="analytics-hero-value analytics-hero-value--teal">
            {top10FlipStats.avgRoi}%
          </span>
        </div>
      </div>

      <div className="analytics-sections">
        <div className="analytics-section">
          <h3 className="section-title">Grade Distribution</h3>
          <div className="grade-chart">
            {Object.entries(gradeDistribution).map(([grade, count]) => (
              <div key={grade} className="grade-chart-row">
                <span className="grade-chart-label" style={{
                  '--grade-color': getGradeColor(grade),
                  color: 'var(--grade-color)',
                } as React.CSSProperties}>
                  {grade}
                </span>
                <div className="grade-chart-bar-track">
                  <div
                    className="grade-chart-bar"
                    style={{
                      '--bar-width': `${(count / maxGradeCount) * 100}%`,
                      '--grade-color': getGradeColor(grade),
                    } as React.CSSProperties}
                  />
                </div>
                <span className="grade-chart-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="analytics-section">
          <h3 className="section-title">Condition Breakdown</h3>
          <div className="condition-list">
            {Object.entries(conditionCounts)
              .sort(([, a], [, b]) => b - a)
              .map(([cond, count]) => (
                <div key={cond} className="condition-item">
                  <span className="condition-label">{cond}</span>
                  <span className="condition-count">{count}</span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  )
}
