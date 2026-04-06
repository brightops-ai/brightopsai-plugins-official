import { useState, useMemo } from 'react'
import { SortAscending } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import ListingCard from './ListingCard'
import { sortListings } from '@/utils/sort'

type SortKey = 'grade' | 'price-asc' | 'price-desc' | 'deal' | 'distance'

const SORT_CONFIG: Record<SortKey, { field: keyof Listing; asc: boolean }> = {
  'grade': { field: 'grade', asc: true },
  'price-asc': { field: 'price', asc: true },
  'price-desc': { field: 'price', asc: false },
  'deal': { field: 'priceVsMarket', asc: true },
  'distance': { field: 'distance', asc: true },
}

const SORT_OPTIONS: [SortKey, string][] = [
  ['grade', 'Best Grade'],
  ['deal', 'Best Deal %'],
  ['price-asc', 'Price Low'],
  ['price-desc', 'Price High'],
  ['distance', 'Nearest'],
]

interface ListingGridProps {
  listings: Listing[]
  onSelect: (listing: Listing) => void
}

export default function ListingGrid({ listings, onSelect }: ListingGridProps) {
  const [sortKey, setSortKey] = useState<SortKey>('grade')
  const { field, asc } = SORT_CONFIG[sortKey]
  const sorted = useMemo(() => sortListings(listings, field, asc), [listings, field, asc])

  if (listings.length === 0) {
    return <div className="empty-state">No listings match your filters.</div>
  }

  return (
    <div>
      <div className="listing-grid-sort">
        <SortAscending size={14} color="var(--color-text-muted)" />
        <span className="listing-grid-sort-label">Sort:</span>
        {SORT_OPTIONS.map(([key, label]) => (
          <button
            key={key}
            className={`sort-btn ${sortKey === key ? 'sort-btn--active' : ''}`}
            onClick={() => setSortKey(key)}
            tabIndex={0}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="listing-grid">
        {sorted.map((l, i) => (
          <ListingCard key={l.id} listing={l} onClick={() => onSelect(l)} index={i} />
        ))}
      </div>
    </div>
  )
}
