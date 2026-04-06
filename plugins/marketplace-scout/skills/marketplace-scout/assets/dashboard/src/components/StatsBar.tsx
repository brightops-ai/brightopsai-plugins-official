import { ChartBar, TrendDown, Trophy, Package, CurrencyDollar, Rocket, Clock, Wallet } from '@phosphor-icons/react'
import type { Listing, FlipStats } from '@/types/listing'
import { getGradeColor } from '@/utils/grades'

interface StatsBarProps {
  totalCount: number
  gradeDistribution: Record<string, number>
  avgPriceVsMarket: number
  bestDeal: Listing | null
  top10FlipStats: FlipStats
  allFlipStats: FlipStats
}

export default function StatsBar({ totalCount, gradeDistribution, avgPriceVsMarket, bestDeal, top10FlipStats, allFlipStats }: StatsBarProps) {
  const hasFlipData = allFlipStats.totalProfit > 0

  return (
    <div className="stats-container">
      {hasFlipData && (
        <div className="hero-stats-grid">
          <div className="card hero-stat-card">
            <div className="hero-stat-header">
              <div className="hero-stat-icon hero-stat-icon--teal">
                <Rocket size={18} weight="fill" color="var(--color-teal)" />
              </div>
              <span className="hero-stat-label">Top 10 Flips</span>
            </div>
            <div className="hero-stat-value-row">
              <span className="hero-stat-value hero-stat-value--teal">
                ${top10FlipStats.totalProfit.toLocaleString()}
              </span>
              <span className="hero-stat-suffix">profit</span>
            </div>
            <div className="hero-stat-meta">
              <span className="stat-meta-item">
                <Wallet size={12} /> ${top10FlipStats.totalInvestment.toLocaleString()} invested
              </span>
              <span className="stat-meta-item stat-meta-item--accent">
                <CurrencyDollar size={12} /> {top10FlipStats.avgRoi}% avg ROI
              </span>
              <span className="stat-meta-item">
                <Clock size={12} /> {top10FlipStats.estTurnaroundDays} days
              </span>
            </div>
          </div>

          <div className="card hero-stat-card">
            <div className="hero-stat-header">
              <div className="hero-stat-icon hero-stat-icon--accent">
                <CurrencyDollar size={18} weight="fill" color="var(--color-accent)" />
              </div>
              <span className="hero-stat-label">All {allFlipStats.itemCount} Flippable</span>
            </div>
            <div className="hero-stat-value-row">
              <span className="hero-stat-value hero-stat-value--accent">
                ${allFlipStats.totalProfit.toLocaleString()}
              </span>
              <span className="hero-stat-suffix">total profit</span>
            </div>
            <div className="hero-stat-meta">
              <span className="stat-meta-item">
                <Wallet size={12} /> ${allFlipStats.totalInvestment.toLocaleString()} invested
              </span>
              <span className="stat-meta-item stat-meta-item--accent">
                <CurrencyDollar size={12} /> {allFlipStats.avgRoi}% avg ROI
              </span>
              <span className="stat-meta-item">
                <Clock size={12} /> {allFlipStats.estTurnaroundDays} days
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="stats-secondary">
        <div className="stats-secondary-item">
          <span className="stats-secondary-icon"><Package size={16} weight="duotone" /></span>
          <div>
            <div className="mono-label">Listings</div>
            <div className="stats-secondary-value">{totalCount}</div>
          </div>
        </div>

        <div className="stats-secondary-item">
          <span className="stats-secondary-icon"><ChartBar size={16} weight="duotone" /></span>
          <div>
            <div className="mono-label">Grades</div>
            <div className="stats-grade-pills">
              {Object.entries(gradeDistribution).map(([grade, count]) => (
                count > 0 && (
                  <span
                    key={grade}
                    className="stats-grade-pill"
                    style={{
                      '--grade-color': getGradeColor(grade),
                      color: 'var(--grade-color)',
                      background: `color-mix(in srgb, var(--grade-color) 10%, transparent)`,
                    } as React.CSSProperties}
                  >
                    {grade}:{count}
                  </span>
                )
              ))}
            </div>
          </div>
        </div>

        <div className="stats-secondary-item">
          <span className="stats-secondary-icon"><TrendDown size={16} weight="duotone" /></span>
          <div>
            <div className="mono-label">Avg vs Market</div>
            <div
              className="stats-secondary-value"
              style={{
                '--value-color': avgPriceVsMarket <= 0 ? 'var(--color-grade-a)' : 'var(--color-grade-f)',
                color: 'var(--value-color)',
              } as React.CSSProperties}
            >
              {avgPriceVsMarket > 0 ? '+' : ''}{avgPriceVsMarket}%
            </div>
          </div>
        </div>

        <div className="stats-secondary-item">
          <span className="stats-secondary-icon"><Trophy size={16} weight="duotone" /></span>
          <div>
            <div className="mono-label">Best Deal</div>
            <div className="stats-secondary-value stats-secondary-value--accent">
              {bestDeal ? `$${bestDeal.price}` : 'N/A'}
            </div>
            {bestDeal && (
              <div className="stats-secondary-subtitle">{bestDeal.title.slice(0, 30)}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
