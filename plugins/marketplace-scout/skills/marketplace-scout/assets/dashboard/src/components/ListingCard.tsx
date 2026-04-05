import { Star, Clock, Warning, ArrowSquareOut, Storefront, Article, MapPin } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import GradeBadge from './GradeBadge'

interface ListingCardProps {
  listing: Listing
  onClick: () => void
  index?: number
}

export default function ListingCard({ listing, onClick, index = 0 }: ListingCardProps) {
  const priceColor = listing.priceVsMarket <= -10
    ? 'var(--color-grade-a)'
    : listing.priceVsMarket >= 10
      ? 'var(--color-grade-f)'
      : 'var(--color-text)'

  const pctColor = listing.priceVsMarket <= 0
    ? 'var(--color-grade-a)'
    : 'var(--color-grade-f)'

  return (
    <div
      onClick={onClick}
      className="card"
      style={{
        padding: '0.875rem 1rem',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.625rem',
        animation: `fadeInUp 0.4s var(--ease-out) ${index * 40}ms both`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <GradeBadge grade={listing.grade} size="sm" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {listing.redFlags.length > 0 && (
            <span style={{
              color: 'var(--color-grade-f)', display: 'flex', alignItems: 'center',
              gap: 3, fontSize: 10, fontFamily: 'var(--font-mono)',
            }}>
              <Warning size={12} weight="fill" /> {listing.redFlags.length}
            </span>
          )}
          {listing.condition && listing.condition !== 'unknown' && (
            <span className="badge" style={{
              background: 'var(--color-surface-hover)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
              fontSize: 9,
            }}>
              {listing.condition}
            </span>
          )}
        </div>
      </div>

      <h3 style={{
        fontFamily: 'var(--font-display)',
        fontSize: 14,
        fontWeight: 600,
        lineHeight: 1.35,
        letterSpacing: '-0.01em',
        color: 'var(--color-text)',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {listing.title}
      </h3>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 20,
          fontWeight: 800,
          color: priceColor,
          letterSpacing: '-0.03em',
        }}>
          ${listing.price.toLocaleString()}
        </span>
        <span style={{
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          color: pctColor,
          padding: '1px 5px',
          borderRadius: 'var(--radius-pill)',
          background: `color-mix(in srgb, ${pctColor} 10%, transparent)`,
        }}>
          {listing.priceVsMarket > 0 ? '+' : ''}{listing.priceVsMarket}%
        </span>
      </div>

      <div style={{
        display: 'flex', gap: '0.625rem', fontSize: 11,
        color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)',
        flexWrap: 'wrap',
      }}>
        {listing.sellerRating !== null && listing.sellerRating > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <Star size={10} weight="fill" color="var(--color-accent)" /> {listing.sellerRating}
          </span>
        )}
        {listing.sellerAccountAge && listing.sellerAccountAge !== 'unknown' && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <Clock size={10} /> {listing.sellerAccountAge}
          </span>
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <MapPin size={10} /> {listing.location}
        </span>
      </div>

      <p style={{
        fontSize: 11, color: 'var(--color-text)', lineHeight: 1.5, opacity: 0.85,
        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {listing.summary}
      </p>

      <div style={{ display: 'flex', gap: '0.375rem', marginTop: 'auto', flexWrap: 'wrap' }}>
        <LinkButton href={listing.listingUrl} icon={<ArrowSquareOut size={11} />} label="View" />
        {listing.vendorUrl && <LinkButton href={listing.vendorUrl} icon={<Storefront size={11} />} label="Retail" />}
        {listing.reviewUrl && <LinkButton href={listing.reviewUrl} icon={<Article size={11} />} label="Review" />}
      </div>
    </div>
  )
}

function LinkButton({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={e => e.stopPropagation()}
      className="btn"
      style={{ fontSize: 10, padding: '3px 7px', gap: 3 }}
    >
      {icon} {label}
    </a>
  )
}
