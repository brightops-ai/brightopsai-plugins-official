import { useState, useEffect } from 'react'
import type { SearchSession, SearchIndex } from '@/types/listing'
import { MagnifyingGlass, Clock } from '@phosphor-icons/react'

interface SearchTabsProps {
  activeSearchId: string | null
  onSelectSearch: (session: SearchSession) => void
}

export default function SearchTabs({ activeSearchId, onSelectSearch }: SearchTabsProps) {
  const [sessions, setSessions] = useState<SearchSession[]>([])

  useEffect(() => {
    fetch('/data/searches.json')
      .then(r => r.json())
      .then((data: SearchIndex) => {
        setSessions(data.searches)
      })
      .catch(() => setSessions([]))
  }, [])

  useEffect(() => {
    if (!activeSearchId && sessions.length > 0) {
      onSelectSearch(sessions[sessions.length - 1])
    }
  }, [activeSearchId, onSelectSearch, sessions])
  if (sessions.length <= 1) return null

  return (
    <div style={{ padding: '0.75rem 1.5rem 0' }}>
      <div className="tab-bar">
        {sessions.map((session) => {
          const isActive = session.id === activeSearchId
          const date = new Date(session.timestamp)
          const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

          return (
            <button
              key={session.id}
              className={`tab ${isActive ? 'active' : ''}`}
              onClick={() => onSelectSearch(session)}
            >
              <MagnifyingGlass size={12} weight={isActive ? 'bold' : 'regular'} />
              <span>{session.label}</span>
              <span className="tab-count">{session.listingCount}</span>
              <span style={{ fontSize: 10, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 3 }}>
                <Clock size={9} />
                {timeStr}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
