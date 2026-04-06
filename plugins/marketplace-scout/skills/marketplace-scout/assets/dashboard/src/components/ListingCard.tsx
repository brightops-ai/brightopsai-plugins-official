import { Star, Clock, Warning, ArrowSquareOut, Storefront, Article, MapPin, Crosshair, Package } from '@phosphor-icons/react'
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

  const hasProfit = listing.netProfitHigh > 0

  return (
    <div
      onClick={onClick}
      className="listing-card"
      style={{
        '--fade-delay': `${index * 40}ms`,
        '--price-color': priceColor,
        '--pct-color': pctColor,
      } as React.CSSProperties}
    >
      {listing.imageUrl ? (
        <img
          src={listing.imageUrl}
          alt={listing.title}
          className="listing-card-image"
        />
      ) : (
        <div className="listing-card-image-placeholder">
          <Package size={24} />
          <span>{listing.searchTerm}</span>
        </div>
      )}

      <div className="listing-card-hero">
        <span className="listing-card-price">
          ${listing.price.toLocaleString()}
        </span>
        <GradeBadge grade={listing.grade} size="sm" />
      </div>

      <div className="listing-card-pct">
        {listing.priceVsMarket > 0 ? '+' : ''}{listing.priceVsMarket}% vs market
      </div>

      {hasProfit && (
        <div className="listing-card-roi">
          Est. +${listing.netProfitLow}&ndash;${listing.netProfitHigh} / {listing.roiLow}&ndash;{listing.roiHigh}% ROI
        </div>
      )}

      <h3 className="listing-card-title">
        {listing.title}
      </h3>

      <p className="listing-card-summary">
        {listing.summary}
      </p>

      {listing.redFlags.length > 0 && (
        <span className="listing-card-flags">
          <Warning size={12} weight="fill" /> {listing.redFlags.length} red flag{listing.redFlags.length > 1 ? 's' : ''}
        </span>
      )}

      <div className="listing-card-footer">
        {listing.sellerRating !== null && listing.sellerRating > 0 && (
          <span className="listing-card-footer-item">
            <Star size={10} weight="fill" color="var(--color-accent)" /> {listing.sellerRating}
          </span>
        )}
        {listing.sellerAccountAge && listing.sellerAccountAge !== 'unknown' && (
          <span className="listing-card-footer-item">
            <Clock size={10} /> {listing.sellerAccountAge}
          </span>
        )}
        <span className="listing-card-footer-item">
          <MapPin size={10} /> {listing.location}
        </span>
        {listing.condition && listing.condition !== 'unknown' && (
          <span className="listing-card-condition">
            {listing.condition}
          </span>
        )}
      </div>

      <div className="listing-card-actions">
        <LinkButton href={listing.listingUrl} icon={<ArrowSquareOut size={11} />} label="View" />
        {listing.vendorUrl && <LinkButton href={listing.vendorUrl} icon={<Storefront size={11} />} label="Retail" />}
        {listing.reviewUrl && <LinkButton href={listing.reviewUrl} icon={<Article size={11} />} label="Review" />}
        <button
          type="button"
          className="scout-btn"
          onClick={e => e.stopPropagation()}
        >
          <Crosshair size={11} /> Scout
        </button>
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
      className="link-btn"
    >
      {icon} {label}
    </a>
  )
}
