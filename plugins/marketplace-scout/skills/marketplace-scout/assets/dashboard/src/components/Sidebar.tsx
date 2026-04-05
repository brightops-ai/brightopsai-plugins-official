import { Funnel, Warning } from '@phosphor-icons/react'
import type { FilterState } from '@/types/listing'

interface SidebarProps {
  filters: FilterState
  updateFilter: <K extends keyof FilterState>(key: K, value: FilterState[K]) => void
  searchTerms: string[]
  conditions: string[]
  priceRange: [number, number]
}

const GRADES = ['A+', 'A', 'B', 'C', 'D', 'F']

export default function Sidebar({ filters, updateFilter, searchTerms, conditions, priceRange }: SidebarProps) {
  function toggleGrade(grade: string) {
    const next = new Set(filters.grades)
    if (next.has(grade)) next.delete(grade)
    else next.add(grade)
    updateFilter('grades', next)
  }

  function toggleCondition(cond: string) {
    const next = new Set(filters.conditions)
    if (next.has(cond)) next.delete(cond)
    else next.add(cond)
    updateFilter('conditions', next)
  }

  function toggleSearchTerm(term: string) {
    const next = new Set(filters.searchTerms)
    if (next.has(term)) next.delete(term)
    else next.add(term)
    updateFilter('searchTerms', next)
  }

  return (
    <aside style={{
      width: 220,
      flexShrink: 0,
      padding: '0.875rem',
      borderRight: '1px solid var(--color-border)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: '1.25rem',
      animation: 'fadeIn 0.3s var(--ease-out)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13,
      }}>
        <Funnel size={14} weight="duotone" color="var(--color-accent)" /> Filters
      </div>

      <FilterSection title="Grade">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
          {GRADES.map(g => (
            <button
              key={g}
              className={`chip ${filters.grades.has(g) ? 'active' : ''}`}
              onClick={() => toggleGrade(g)}
            >
              {g}
            </button>
          ))}
        </div>
      </FilterSection>

      <FilterSection title="Price">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input
            type="number"
            placeholder={`$${priceRange[0]}`}
            onChange={e => updateFilter('priceMin', e.target.value ? Number(e.target.value) : null)}
            className="input"
          />
          <span style={{ color: 'var(--color-text-muted)', fontSize: 10 }}>&ndash;</span>
          <input
            type="number"
            placeholder={`$${priceRange[1]}`}
            onChange={e => updateFilter('priceMax', e.target.value ? Number(e.target.value) : null)}
            className="input"
          />
        </div>
      </FilterSection>

      {conditions.length > 0 && (
        <FilterSection title="Condition">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {conditions.map(c => (
              <button
                key={c}
                className={`chip ${filters.conditions.has(c) ? 'active' : ''}`}
                onClick={() => toggleCondition(c)}
                style={{ justifyContent: 'flex-start' }}
              >
                {c}
              </button>
            ))}
          </div>
        </FilterSection>
      )}

      <FilterSection title="Seller">
        <select
          onChange={e => updateFilter('minSellerRating', e.target.value ? Number(e.target.value) : null)}
          className="input"
          style={{ cursor: 'pointer' }}
        >
          <option value="">Any rating</option>
          <option value="4.5">4.5+ stars</option>
          <option value="4">4+ stars</option>
          <option value="3.5">3.5+ stars</option>
        </select>
      </FilterSection>

      <FilterSection title="Flags">
        <label style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontSize: 11, cursor: 'pointer', color: 'var(--color-text-secondary)',
          fontFamily: 'var(--font-mono)',
        }}>
          <input
            type="checkbox"
            checked={!filters.showRedFlagged}
            onChange={e => updateFilter('showRedFlagged', !e.target.checked)}
            style={{ accentColor: 'var(--color-accent)' }}
          />
          <Warning size={12} weight="fill" color="var(--color-grade-f)" />
          Hide flagged
        </label>
      </FilterSection>

      {searchTerms.length > 1 && (
        <FilterSection title="Search Term">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {searchTerms.map(t => (
              <button
                key={t}
                className={`chip ${filters.searchTerms.size === 0 || filters.searchTerms.has(t) ? 'active' : ''}`}
                onClick={() => toggleSearchTerm(t)}
                style={{ justifyContent: 'flex-start' }}
              >
                {t}
              </button>
            ))}
          </div>
        </FilterSection>
      )}
    </aside>
  )
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mono-label" style={{ marginBottom: 6 }}>
        {title}
      </div>
      {children}
    </div>
  )
}
