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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {hasFlipData && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '0.75rem',
          animation: 'fadeInUp 0.4s var(--ease-out) both',
        }}>
          <div className="card" style={{
            padding: '1rem 1.25rem',
            background: 'linear-gradient(135deg, var(--color-surface) 0%, rgba(34, 197, 94, 0.04) 100%)',
            border: '1px solid rgba(34, 197, 94, 0.15)',
            animation: 'fadeInUp 0.4s var(--ease-out) both',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 'var(--radius)',
                background: 'rgba(34, 197, 94, 0.12)',
              }}>
                <Rocket size={16} weight="fill" color="var(--color-grade-a)" />
              </div>
              <span className="mono-label">Top 10 Flips</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
              <span style={{
                fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 800,
                color: 'var(--color-grade-a)', letterSpacing: '-0.03em',
              }}>
                ${top10FlipStats.totalProfit.toLocaleString()}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 12,
                color: 'var(--color-grade-a)', opacity: 0.8,
              }}>
                profit
              </span>
            </div>
            <div style={{
              display: 'flex', gap: 12, flexWrap: 'wrap',
              fontFamily: 'var(--font-mono)', fontSize: 11,
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-text-secondary)' }}>
                <Wallet size={12} color="var(--color-text-secondary)" />
                ${top10FlipStats.totalInvestment.toLocaleString()} invested
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-accent)' }}>
                <CurrencyDollar size={12} />
                {top10FlipStats.avgRoi}% avg ROI
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-teal)' }}>
                <Clock size={12} />
                {top10FlipStats.estTurnaroundDays} days
              </span>
            </div>
          </div>

          <div className="card" style={{
            padding: '1rem 1.25rem',
            background: 'linear-gradient(135deg, var(--color-surface) 0%, rgba(245, 158, 11, 0.04) 100%)',
            border: '1px solid rgba(245, 158, 11, 0.15)',
            animation: 'fadeInUp 0.4s var(--ease-out) 60ms both',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 28, height: 28, borderRadius: 'var(--radius)',
                background: 'var(--color-accent-dim)',
              }}>
                <CurrencyDollar size={16} weight="fill" color="var(--color-accent)" />
              </div>
              <span className="mono-label">All {allFlipStats.itemCount} Flippable Items</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
              <span style={{
                fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 800,
                color: 'var(--color-accent)', letterSpacing: '-0.03em',
              }}>
                ${allFlipStats.totalProfit.toLocaleString()}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 12,
                color: 'var(--color-accent)', opacity: 0.8,
              }}>
                total profit
              </span>
            </div>
            <div style={{
              display: 'flex', gap: 12, flexWrap: 'wrap',
              fontFamily: 'var(--font-mono)', fontSize: 11,
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-text-secondary)' }}>
                <Wallet size={12} color="var(--color-text-secondary)" />
                ${allFlipStats.totalInvestment.toLocaleString()} invested
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-accent)' }}>
                <CurrencyDollar size={12} />
                {allFlipStats.avgRoi}% avg ROI
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--color-teal)' }}>
                <Clock size={12} />
                {allFlipStats.estTurnaroundDays} days
              </span>
            </div>
          </div>
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '0.75rem',
        animation: 'fadeInUp 0.4s var(--ease-out) both',
      }}>
        <StatCard
          icon={<Package size={18} weight="duotone" />}
          label="Listings"
          value={String(totalCount)}
          delay={0}
        />
        <StatCard
          icon={<ChartBar size={18} weight="duotone" />}
          label="Grades"
          value=""
          delay={1}
        >
          <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginTop: 2 }}>
            {Object.entries(gradeDistribution).map(([grade, count]) => (
              count > 0 && (
                <span key={grade} style={{
                  fontSize: 11,
                  fontWeight: 500,
                  fontFamily: 'var(--font-mono)',
                  color: getGradeColor(grade),
                  padding: '1px 5px',
                  borderRadius: 'var(--radius-pill)',
                  background: `color-mix(in srgb, ${getGradeColor(grade)} 10%, transparent)`,
                }}>
                  {grade}:{count}
                </span>
              )
            ))}
          </div>
        </StatCard>
        <StatCard
          icon={<TrendDown size={18} weight="duotone" />}
          label="Avg vs Market"
          value={`${avgPriceVsMarket > 0 ? '+' : ''}${avgPriceVsMarket}%`}
          valueColor={avgPriceVsMarket <= 0 ? 'var(--color-grade-a)' : 'var(--color-grade-f)'}
          delay={2}
        />
        <StatCard
          icon={<Trophy size={18} weight="duotone" />}
          label="Best Deal"
          value={bestDeal ? `$${bestDeal.price}` : 'N/A'}
          valueColor="var(--color-accent)"
          subtitle={bestDeal ? bestDeal.title.slice(0, 30) : undefined}
          delay={3}
        />
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, valueColor, subtitle, children, delay }: {
  icon: React.ReactNode
  label: string
  value: string
  valueColor?: string
  subtitle?: string
  children?: React.ReactNode
  delay: number
}) {
  return (
    <div className="card" style={{
      display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
      padding: '0.75rem 1rem',
      animation: `fadeInUp 0.4s var(--ease-out) ${delay * 60}ms both`,
    }}>
      <div style={{
        color: 'var(--color-accent)',
        marginTop: 2,
        opacity: 0.8,
      }}>{icon}</div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div className="mono-label" style={{ marginBottom: 2 }}>
          {label}
        </div>
        {value && (
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.05rem',
            fontWeight: 700,
            color: valueColor ?? 'var(--color-text)',
            letterSpacing: '-0.02em',
          }}>
            {value}
          </div>
        )}
        {subtitle && (
          <div style={{
            fontSize: 11, color: 'var(--color-text-secondary)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{subtitle}</div>
        )}
        {children}
      </div>
    </div>
  )
}
