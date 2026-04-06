import { CaretUp, CaretDown, Warning } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import GradeBadge from './GradeBadge'
import { sortListings } from '@/utils/sort'

interface ListingTableProps {
  listings: Listing[]
  sortField: keyof Listing
  sortAsc: boolean
  onSort: (field: keyof Listing) => void
  onSelect: (listing: Listing) => void
}

type SortableField = { key: keyof Listing; label: string; width?: string }

const COLUMNS: SortableField[] = [
  { key: 'grade', label: 'Grade', width: '72px' },
  { key: 'title', label: 'Title' },
  { key: 'price', label: 'Price', width: '90px' },
  { key: 'priceVsMarket', label: 'vs Mkt', width: '80px' },
  { key: 'sellerRating', label: 'Seller', width: '70px' },
  { key: 'condition', label: 'Cond.', width: '90px' },
  { key: 'location', label: 'Location', width: '110px' },
  { key: 'redFlags', label: 'Flags', width: '50px' },
]

export default function ListingTable({ listings, sortField, sortAsc, onSort, onSelect }: ListingTableProps) {
  const sorted = sortListings(listings, sortField, sortAsc)

  if (listings.length === 0) {
    return <div className="empty-state">No listings match your filters.</div>
  }

  const handleRowKey = (e: React.KeyboardEvent, listing: Listing) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(listing)
    }
  }

  return (
    <div className="table-wrapper">
      <table className="data-table">
        <thead>
          <tr>
            {COLUMNS.map(col => (
              <th
                key={col.key}
                onClick={() => onSort(col.key)}
                style={{ width: col.width }}
              >
                <span className="table-sort-indicator">
                  {col.label}
                  {sortField === col.key && (
                    sortAsc
                      ? <CaretUp size={10} weight="bold" color="var(--color-accent)" />
                      : <CaretDown size={10} weight="bold" color="var(--color-accent)" />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(l => {
            const pctColor = l.priceVsMarket <= -10
              ? 'var(--color-grade-a)'
              : l.priceVsMarket >= 10
                ? 'var(--color-grade-f)'
                : 'var(--color-text-secondary)'

            return (
              <tr
                key={l.id}
                onClick={() => onSelect(l)}
                onKeyDown={e => handleRowKey(e, l)}
                tabIndex={0}
                role="button"
              >
                <td><GradeBadge grade={l.grade} size="sm" /></td>
                <td className="table-cell-title">{l.title}</td>
                <td className="table-cell-price">${l.price.toLocaleString()}</td>
                <td style={{ '--grade-color': pctColor, color: pctColor, fontWeight: 500 } as React.CSSProperties}>
                  {l.priceVsMarket > 0 ? '+' : ''}{l.priceVsMarket}%
                </td>
                <td>{l.sellerRating ?? '-'}</td>
                <td>{l.condition}</td>
                <td>{l.location}</td>
                <td>
                  {l.redFlags.length > 0 && (
                    <Warning size={13} weight="fill" color="var(--color-grade-f)" />
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
