import { X, ArrowSquareOut, Storefront, Article, ShieldCheck, Star, Clock, Images, Warning, MapPin } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import GradeBadge from './GradeBadge'
import { getGradeColor } from '@/utils/grades'

interface DetailPanelProps {
  listing: Listing
  onClose: () => void
}

export default function DetailPanel({ listing, onClose }: DetailPanelProps) {
  const pctColor = listing.priceVsMarket <= -10
    ? 'var(--color-grade-a)'
    : listing.priceVsMarket >= 10
      ? 'var(--color-grade-f)'
      : 'var(--color-text-secondary)'

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', justifyContent: 'flex-end' }}>
      <div className="panel-overlay" onClick={onClose} />
      <div className="panel" style={{
        padding: '1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <GradeBadge grade={listing.grade} size="lg" />
          <button
            onClick={onClose}
            className="btn"
            style={{ padding: 6 }}
          >
            <X size={16} />
          </button>
        </div>

        <div>
          <h2 style={{
            fontFamily: 'var(--font-display)',
            fontSize: 18,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            marginBottom: 8,
            lineHeight: 1.3,
          }}>{listing.title}</h2>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6 }}>
            <span style={{
              fontFamily: 'var(--font-display)',
              fontSize: 26,
              fontWeight: 800,
              letterSpacing: '-0.03em',
            }}>
              ${listing.price.toLocaleString()}
            </span>
            <span className="badge" style={{
              background: `color-mix(in srgb, ${pctColor} 12%, transparent)`,
              border: `1px solid color-mix(in srgb, ${pctColor} 25%, transparent)`,
              color: pctColor,
              fontSize: 11,
            }}>
              {listing.priceVsMarket > 0 ? '+' : ''}{listing.priceVsMarket}% vs market
            </span>
          </div>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4,
          }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              padding: '5px 12px', borderRadius: 'var(--radius-pill)',
              background: 'var(--color-surface-hover)',
              border: '1px solid var(--color-border)',
              fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
              color: 'var(--color-text)',
            }}>
              <span style={{ color: 'var(--color-text-secondary)', fontWeight: 400, fontSize: 11 }}>Market</span>
              ${listing.marketPriceLow} – ${listing.marketPriceHigh}
            </span>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              padding: '5px 12px', borderRadius: 'var(--radius-pill)',
              background: 'var(--color-teal-dim)',
              border: '1px solid rgba(45, 212, 191, 0.2)',
              fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
              color: 'var(--color-teal)',
            }}>
              <span style={{ fontWeight: 400, fontSize: 11, opacity: 0.8 }}>Median</span>
              ${listing.marketPriceMedian}
            </span>
            {listing.vendorPrice && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 'var(--radius-pill)',
                background: 'var(--color-accent-dim)',
                border: '1px solid var(--color-accent-border)',
                fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
                color: 'var(--color-accent)',
              }}>
                <span style={{ fontWeight: 400, fontSize: 11, opacity: 0.8 }}>Retail</span>
                ${listing.vendorPrice.toLocaleString()}
              </span>
            )}
          </div>
        </div>

        <Section title="Summary">
          <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--color-text)' }}>{listing.summary}</p>
        </Section>

        <Section title="Grade Breakdown">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <GradeRow label="Price Value" weight="35%" grade={listing.gradeBreakdown.priceValue} />
            <GradeRow label="Seller Trust" weight="25%" grade={listing.gradeBreakdown.sellerTrust} />
            <GradeRow label="Listing Quality" weight="20%" grade={listing.gradeBreakdown.listingQuality} />
            <GradeRow label="Red Flags" weight="15%" grade={listing.gradeBreakdown.redFlags} />
            <GradeRow label="Condition/Price" weight="5%" grade={listing.gradeBreakdown.conditionConsistency} />
          </div>
        </Section>

        <Section title="Seller">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <InfoRow icon={<ShieldCheck size={13} />} label="Name" value={listing.sellerName} />
            <InfoRow icon={<Star size={13} />} label="Rating" value={listing.sellerRating !== null ? `${listing.sellerRating} stars (${listing.sellerReviews} reviews)` : 'No ratings'} />
            <InfoRow icon={<Clock size={13} />} label="Account" value={listing.sellerAccountAge || 'Unknown'} />
            <InfoRow icon={<Clock size={13} />} label="Response" value={listing.sellerResponseTime || 'Unknown'} />
          </div>
        </Section>

        {listing.redFlags.length > 0 && (
          <Section title="Red Flags">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {listing.redFlags.map((flag, i) => (
                <span key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  fontSize: 12, color: 'var(--color-grade-f)',
                  fontFamily: 'var(--font-mono)',
                }}>
                  <Warning size={12} weight="fill" /> {flag}
                </span>
              ))}
            </div>
          </Section>
        )}

        <Section title="Details">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <InfoRow icon={<MapPin size={13} />} label="Location" value={`${listing.location} (${listing.distance})`} />
            <InfoRow icon={<Images size={13} />} label="Photos" value={`${listing.photoCount} (${listing.photosOriginal ? 'original' : 'possibly stock'})`} />
            <InfoRow icon={<Clock size={13} />} label="Listed" value={listing.listingAge || 'Unknown'} />
            {listing.description && (
              <div style={{
                marginTop: 8, padding: '10px 12px',
                background: 'var(--color-bg)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--color-border-subtle)',
                fontSize: 12, color: 'var(--color-text)', lineHeight: 1.65,
                fontFamily: 'var(--font-mono)',
              }}>
                {listing.description}
              </div>
            )}
          </div>
        </Section>

        <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
          <a href={listing.listingUrl} target="_blank" rel="noopener noreferrer" className="btn btn-accent">
            <ArrowSquareOut size={13} /> Open Listing
          </a>
          {listing.vendorUrl && (
            <a href={listing.vendorUrl} target="_blank" rel="noopener noreferrer" className="btn">
              <Storefront size={13} /> Vendor
            </a>
          )}
          {listing.reviewUrl && (
            <a href={listing.reviewUrl} target="_blank" rel="noopener noreferrer" className="btn">
              <Article size={13} /> Review
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mono-label" style={{ marginBottom: 8 }}>{title}</h3>
      {children}
    </div>
  )
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
      <span style={{ color: 'var(--color-text-secondary)', opacity: 0.7 }}>{icon}</span>
      <span style={{ color: 'var(--color-text-secondary)', minWidth: 70, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{label}</span>
      <span style={{ color: 'var(--color-text)' }}>{value}</span>
    </div>
  )
}

function GradeRow({ label, weight, grade }: { label: string; weight: string; grade: string }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      fontSize: 13, padding: '4px 0',
    }}>
      <span style={{ color: 'var(--color-text)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        {label} <span style={{ color: 'var(--color-text-secondary)', fontSize: 11 }}>({weight})</span>
      </span>
      <span style={{ fontWeight: 600, color: getGradeColor(grade), fontFamily: 'var(--font-mono)', fontSize: 13 }}>{grade || '-'}</span>
    </div>
  )
}
