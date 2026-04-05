import { SquaresFour, Table } from '@phosphor-icons/react'
import type { ViewMode } from '@/types/listing'

interface ViewToggleProps {
  viewMode: ViewMode
  onChange: (mode: ViewMode) => void
}

export default function ViewToggle({ viewMode, onChange }: ViewToggleProps) {
  return (
    <div style={{
      display: 'flex',
      gap: 2,
      padding: 2,
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius)',
    }}>
      <ToggleButton active={viewMode === 'grid'} onClick={() => onChange('grid')}>
        <SquaresFour size={14} weight={viewMode === 'grid' ? 'fill' : 'regular'} />
      </ToggleButton>
      <ToggleButton active={viewMode === 'table'} onClick={() => onChange('table')}>
        <Table size={14} weight={viewMode === 'table' ? 'fill' : 'regular'} />
      </ToggleButton>
    </div>
  )
}

function ToggleButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '5px 9px',
        border: 'none',
        borderRadius: 'calc(var(--radius) - 2px)',
        background: active ? 'var(--color-accent-dim)' : 'transparent',
        color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
        cursor: 'pointer',
        transition: 'all var(--duration-fast) var(--ease-out)',
      }}
    >
      {children}
    </button>
  )
}
