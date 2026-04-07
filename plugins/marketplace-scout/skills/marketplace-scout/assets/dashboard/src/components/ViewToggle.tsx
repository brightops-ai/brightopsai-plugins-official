import { SquaresFour, Table } from '@phosphor-icons/react'
import type { ViewMode } from '@/types/listing'

interface ViewToggleProps {
  viewMode: ViewMode
  onChange: (mode: ViewMode) => void
}

export default function ViewToggle({ viewMode, onChange }: ViewToggleProps) {
  return (
    <div className="view-toggle">
      <button
        className={`view-toggle-btn ${viewMode === 'grid' ? 'view-toggle-btn--active' : ''}`}
        aria-label="Grid view"
        aria-pressed={viewMode === 'grid'}
        onClick={() => onChange('grid')}
        tabIndex={0}
      >
        <SquaresFour size={14} weight={viewMode === 'grid' ? 'fill' : 'regular'} />
      </button>
      <button
        className={`view-toggle-btn ${viewMode === 'table' ? 'view-toggle-btn--active' : ''}`}
        aria-label="Table view"
        aria-pressed={viewMode === 'table'}
        onClick={() => onChange('table')}
        tabIndex={0}
      >
        <Table size={14} weight={viewMode === 'table' ? 'fill' : 'regular'} />
      </button>
    </div>
  )
}
