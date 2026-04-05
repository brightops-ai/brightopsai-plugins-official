import { CaretUp, CaretDown, Warning } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'
import GradeBadge from './GradeBadge'
import { compareGrades } from '@/utils/grades'

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

function sortListings(listings: Listing[], field: keyof Listing, asc: boolean): Listing[] {
  return [...listings].sort((a, b) => {
    let cmp = 0
    if (field === 'grade') {
      cmp = compareGrades(a.grade, b.grade)
    } else {
      const va = a[field]
      const vb = b[field]
      if (typeof va === 'number' && typeof vb === 'number') cmp = va - vb
      else cmp = String(va ?? '').localeCompare(String(vb ?? ''))
    }
    return asc ? cmp : -cmp
  })
}

export default function ListingTable({ listings, sortField, sortAsc, onSort, onSelect }: ListingTableProps) {
  const sorted = sortListings(listings, sortField, sortAsc)

  if (listings.length === 0) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        No listings match your filters.
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto', animation: 'fadeIn 0.3s var(--ease-out)' }}>
      <table className="data-table">
        <thead>
          <tr>
            {COLUMNS.map(col => (
              <th
                key={col.key}
                onClick={() => onSort(col.key)}
                style={{ width: col.width }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
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
              <tr key={l.id} onClick={() => onSelect(l)}>
                <td><GradeBadge grade={l.grade} size="sm" /></td>
                <td style={{
                  fontFamily: 'var(--font-display)', fontWeight: 500,
                  maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  letterSpacing: '-0.01em',
                }}>{l.title}</td>
                <td style={{ fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                  ${l.price.toLocaleString()}
                </td>
                <td style={{ color: pctColor, fontWeight: 500 }}>
                  {l.priceVsMarket > 0 ? '+' : ''}{l.priceVsMarket}%
                </td>
                <td>{l.sellerRating ?? '-'}</td>
                <td style={{ fontSize: 11 }}>{l.condition}</td>
                <td style={{ fontSize: 11 }}>{l.location}</td>
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
