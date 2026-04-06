import { Binoculars, ArrowsClockwise, ChartLine } from '@phosphor-icons/react'

export type AppTab = 'scouts' | 'flips' | 'analytics'

interface NavTabsProps {
  activeTab: AppTab
  onChange: (tab: AppTab) => void
  flipCount: number
}

const TABS: { id: AppTab; label: string; icon: typeof Binoculars }[] = [
  { id: 'scouts', label: 'Scouts', icon: Binoculars },
  { id: 'flips', label: 'Flips', icon: ArrowsClockwise },
  { id: 'analytics', label: 'Analytics', icon: ChartLine },
]

export default function NavTabs({ activeTab, onChange, flipCount }: NavTabsProps) {
  return (
    <nav className="nav-tabs">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          className={`nav-tab ${activeTab === id ? 'nav-tab--active' : ''}`}
          onClick={() => onChange(id)}
          role="tab"
          aria-selected={activeTab === id}
          tabIndex={0}
        >
          <Icon size={14} weight={activeTab === id ? 'fill' : 'regular'} />
          {label}
          {id === 'flips' && flipCount > 0 && (
            <span className="nav-tab-count">{flipCount}</span>
          )}
        </button>
      ))}
    </nav>
  )
}
