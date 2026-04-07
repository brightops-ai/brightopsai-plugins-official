import { X, ArrowSquareOut, Storefront, Article, ShieldCheck, Star, Clock, Images, Warning, MapPin, TrendUp } from '@phosphor-icons/react'
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
    <div className="detail-panel-wrapper">
      <div className="panel-overlay" onClick={onClose} />
      <div className="panel">
        <div className="panel-content">
          <div className="panel-header">
            <GradeBadge grade={listing.grade} size="lg" />
            <button onClick={onClose} className="btn" aria-label="Close panel">
              <X size={16} />
            </button>
          </div>

          <div>
            <h2 className="panel-title">{listing.title}</h2>
            <div className="panel-price-row">
              <span className="panel-price">${listing.price.toLocaleString()}</span>
              <span
                className="badge"
                style={{ '--grade-color': pctColor, background: `color-mix(in srgb, ${pctColor} 10%, transparent)`, color: pctColor } as React.CSSProperties}
              >
                {listing.priceVsMarket > 0 ? '+' : ''}{listing.priceVsMarket}% vs market
              </span>
            </div>

            {listing.netProfitHigh > 0 && (
              <div className="listing-card-roi">
                <TrendUp size={13} weight="bold" />
                Est. profit ${listing.netProfitLow}–${listing.netProfitHigh} / {listing.roiLow}–{listing.roiHigh}% ROI
              </div>
            )}

            <div className="panel-chips">
              <span className="price-chip price-chip--default">
                <span className="price-chip-label">Market</span>
                ${listing.marketPriceLow} – ${listing.marketPriceHigh}
              </span>
              <span className="price-chip price-chip--teal">
                <span className="price-chip-label">Median</span>
                ${listing.marketPriceMedian}
              </span>
              {listing.vendorPrice && (
                <span className="price-chip price-chip--accent">
                  <span className="price-chip-label">Retail</span>
                  ${listing.vendorPrice.toLocaleString()}
                </span>
              )}
            </div>
          </div>

          <div className="detail-section">
            <h3 className="detail-section-title mono-label">Summary</h3>
            <p className="panel-summary">{listing.summary}</p>
          </div>

          <div className="detail-section">
            <h3 className="detail-section-title mono-label">Grade Breakdown</h3>
            <div className="grade-breakdown">
              <GradeRow label="Price Value" weight="35%" grade={listing.gradeBreakdown.priceValue} />
              <GradeRow label="Seller Trust" weight="25%" grade={listing.gradeBreakdown.sellerTrust} />
              <GradeRow label="Listing Quality" weight="20%" grade={listing.gradeBreakdown.listingQuality} />
              <GradeRow label="Red Flags" weight="15%" grade={listing.gradeBreakdown.redFlags} />
              <GradeRow label="Condition/Price" weight="5%" grade={listing.gradeBreakdown.conditionConsistency} />
            </div>
          </div>

          <div className="detail-section">
            <h3 className="detail-section-title mono-label">Seller</h3>
            <div className="info-rows">
              <InfoRow icon={<ShieldCheck size={13} />} label="Name" value={listing.sellerName} />
              <InfoRow icon={<Star size={13} />} label="Rating" value={listing.sellerRating !== null ? `${listing.sellerRating} stars (${listing.sellerReviews} reviews)` : 'No ratings'} />
              <InfoRow icon={<Clock size={13} />} label="Account" value={listing.sellerAccountAge || 'Unknown'} />
              <InfoRow icon={<Clock size={13} />} label="Response" value={listing.sellerResponseTime || 'Unknown'} />
            </div>
          </div>

          {listing.redFlags.length > 0 && (
            <div className="detail-section">
              <h3 className="detail-section-title mono-label">Red Flags</h3>
              <div className="info-rows">
                {listing.redFlags.map((flag, i) => (
                  <span key={i} className="red-flag-item">
                    <Warning size={12} weight="fill" /> {flag}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="detail-section">
            <h3 className="detail-section-title mono-label">Details</h3>
            <div className="info-rows">
              <InfoRow icon={<MapPin size={13} />} label="Location" value={`${listing.location} (${listing.distance})`} />
              <InfoRow icon={<Images size={13} />} label="Photos" value={`${listing.photoCount} (${listing.photosOriginal ? 'original' : 'possibly stock'})`} />
              <InfoRow icon={<Clock size={13} />} label="Listed" value={listing.listingAge || 'Unknown'} />
              {listing.description && (
                <div className="description-block">{listing.description}</div>
              )}
            </div>
          </div>

          {listing.ebayFees > 0 && (
            <div className="detail-section">
              <h3 className="detail-section-title mono-label">Flip Economics</h3>
              <div className="info-rows">
                <InfoRow icon={<TrendUp size={13} />} label="eBay Fees" value={`$${listing.ebayFees}`} />
                <InfoRow icon={<TrendUp size={13} />} label="Shipping" value={`$${listing.shippingEstimateLow}–$${listing.shippingEstimateHigh}`} />
                <InfoRow icon={<TrendUp size={13} />} label="Net Profit" value={`$${listing.netProfitLow}–$${listing.netProfitHigh}`} />
                <InfoRow icon={<TrendUp size={13} />} label="ROI" value={`${listing.roiLow}–${listing.roiHigh}%`} />
              </div>
            </div>
          )}

          <div className="panel-actions">
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
    </div>
  )
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="info-row">
      <span className="info-row-icon">{icon}</span>
      <span className="info-row-label">{label}</span>
      <span>{value}</span>
    </div>
  )
}

function GradeRow({ label, weight, grade }: { label: string; weight: string; grade: string }) {
  return (
    <div className="grade-row">
      <span className="grade-row-label">
        {label} <span className="grade-row-weight">({weight})</span>
      </span>
      <span
        className="grade-row-value"
        style={{ '--grade-color': getGradeColor(grade), color: 'var(--grade-color)' } as React.CSSProperties}
      >
        {grade || '-'}
      </span>
    </div>
  )
}
