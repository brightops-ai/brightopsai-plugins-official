import type { Listing } from '@/types/listing'
import ListingCard from './ListingCard'

interface ListingGridProps {
  listings: Listing[]
  onSelect: (listing: Listing) => void
}

export default function ListingGrid({ listings, onSelect }: ListingGridProps) {
  if (listings.length === 0) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
        No listings match your filters.
      </div>
    )
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
      gap: '1rem',
    }}>
      {listings.map((l, i) => (
        <ListingCard key={l.id} listing={l} onClick={() => onSelect(l)} index={i} />
      ))}
    </div>
  )
}
