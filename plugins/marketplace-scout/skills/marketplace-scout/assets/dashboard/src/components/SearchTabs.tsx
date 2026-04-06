import { useEffect } from 'react'
import type { SearchSession } from '@/types/listing'
import { MagnifyingGlass, Clock } from '@phosphor-icons/react'

interface SearchTabsProps {
  sessions: SearchSession[]
  activeSearchId: string | null
  onSelectSearch: (session: SearchSession) => void
}

export default function SearchTabs({ sessions, activeSearchId, onSelectSearch }: SearchTabsProps) {
  useEffect(() => {
    if (!activeSearchId && sessions.length > 0) {
      onSelectSearch(sessions[sessions.length - 1])
    }
  }, [activeSearchId, onSelectSearch, sessions])

  if (sessions.length <= 1) return null

  return (
    <div className="search-tabs-wrapper">
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
              tabIndex={0}
            >
              <MagnifyingGlass size={12} weight={isActive ? 'bold' : 'regular'} />
              <span>{session.label}</span>
              <span className="tab-count">{session.listingCount}</span>
              <span className="tab-time">
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
