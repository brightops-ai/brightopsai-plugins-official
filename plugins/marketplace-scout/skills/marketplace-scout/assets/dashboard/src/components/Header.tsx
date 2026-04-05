import { Binoculars, MapPin, Calendar } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'

interface HeaderProps {
  listings: Listing[]
}

export default function Header({ listings }: HeaderProps) {
  const searchLocation = listings[0]?.searchLocation ?? 'Unknown'
  const searchRadius = listings[0]?.searchRadius ?? 0
  const dateScraped = listings[0]?.dateScraped ?? 'Unknown'
  const searchTerms = [...new Set(listings.map(l => l.searchTerm))]

  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0.875rem 1.5rem',
      background: 'var(--color-surface)',
      borderBottom: '1px solid var(--color-border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Binoculars size={22} weight="duotone" color="var(--color-accent)" />
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.15rem',
            fontWeight: 700,
            letterSpacing: '-0.02em',
            background: 'linear-gradient(135deg, var(--color-text) 0%, var(--color-text-secondary) 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Marketplace Scout
          </h1>
        </div>

        <div style={{
          width: 1, height: 20,
          background: 'var(--color-border)',
        }} />

        <div style={{
          display: 'flex', gap: '0.75rem',
          fontSize: 11, color: 'var(--color-text-muted)',
          fontFamily: 'var(--font-mono)',
        }}>
          {searchTerms.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {searchTerms.map((term) => (
                <span key={term} className="badge" style={{
                  background: 'var(--color-accent-dim)',
                  color: 'var(--color-accent)',
                  border: '1px solid var(--color-accent-border)',
                }}>
                  {term}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{
        display: 'flex', gap: '1rem',
        fontSize: 11, color: 'var(--color-text-muted)',
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.02em',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <MapPin size={12} weight="fill" color="var(--color-teal)" />
          {searchLocation} &middot; {searchRadius}mi
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Calendar size={12} weight="fill" color="var(--color-text-muted)" />
          {dateScraped}
        </span>
      </div>
    </header>
  )
}
