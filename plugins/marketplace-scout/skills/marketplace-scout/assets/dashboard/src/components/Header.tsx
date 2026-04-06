import { Binoculars, MapPin, Calendar, Sun, Moon } from '@phosphor-icons/react'
import type { Listing } from '@/types/listing'

interface HeaderProps {
  listings: Listing[]
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

export default function Header({ listings, theme, onToggleTheme }: HeaderProps) {
  const searchLocation = listings[0]?.searchLocation ?? 'Unknown'
  const searchRadius = listings[0]?.searchRadius ?? 0
  const dateScraped = listings[0]?.dateScraped ?? 'Unknown'

  return (
    <header className="header">
      <div className="header-brand">
        <Binoculars size={22} weight="duotone" color="var(--color-accent)" />
        <h1 className="header-title">Marketplace Scout</h1>
      </div>

      <div className="header-actions">
        <span className="header-meta-item">
          <MapPin size={12} weight="fill" color="var(--color-teal)" />
          {searchLocation} &middot; {searchRadius}mi
        </span>
        <span className="header-meta-item">
          <Calendar size={12} weight="fill" color="var(--color-text-muted)" />
          {dateScraped}
        </span>
        <button
          onClick={onToggleTheme}
          className="theme-toggle"
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          title={theme === 'light' ? 'Midnight Editorial' : 'Anthropic Editorial'}
        >
          {theme === 'light'
            ? <Moon size={16} weight="duotone" />
            : <Sun size={16} weight="duotone" />
          }
        </button>
      </div>
    </header>
  )
}
