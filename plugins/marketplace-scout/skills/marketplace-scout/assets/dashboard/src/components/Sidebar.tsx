import { Funnel, Warning, CaretLeft, CaretRight } from '@phosphor-icons/react'
import type { FilterState } from '@/types/listing'

interface SidebarProps {
  filters: FilterState
  updateFilter: <K extends keyof FilterState>(key: K, value: FilterState[K]) => void
  searchTerms: string[]
  conditions: string[]
  priceRange: [number, number]
  collapsed: boolean
  onToggleCollapse: () => void
}

const GRADES = ['A+', 'A', 'B', 'C', 'D', 'F']

export default function Sidebar({
  filters, updateFilter, searchTerms, conditions, priceRange,
  collapsed, onToggleCollapse,
}: SidebarProps) {
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
    <aside className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
      <div className="sidebar-header">
        {!collapsed && (
          <>
            <Funnel size={14} weight="duotone" color="var(--color-accent)" />
            <span>Filters</span>
          </>
        )}
        <button
          className="sidebar-collapse-btn"
          onClick={onToggleCollapse}
          aria-label={collapsed ? 'Expand filters' : 'Collapse filters'}
          tabIndex={0}
        >
          {collapsed
            ? <CaretRight size={14} />
            : <CaretLeft size={14} />
          }
        </button>
      </div>

      {!collapsed && (
        <>
          <FilterSection title="Grade">
            <div className="filter-chips-row">
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
            <div className="filter-price-range">
              <input
                type="number"
                placeholder={`$${priceRange[0]}`}
                onChange={e => updateFilter('priceMin', e.target.value ? Number(e.target.value) : null)}
                className="input"
              />
              <span className="filter-price-sep">&ndash;</span>
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
              <div className="filter-chips-col">
                {conditions.map(c => (
                  <button
                    key={c}
                    className={`chip ${filters.conditions.has(c) ? 'active' : ''}`}
                    onClick={() => toggleCondition(c)}
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
            >
              <option value="">Any rating</option>
              <option value="4.5">4.5+ stars</option>
              <option value="4">4+ stars</option>
              <option value="3.5">3.5+ stars</option>
            </select>
          </FilterSection>

          <FilterSection title="Flags">
            <label className="filter-flag-label">
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
              <div className="filter-chips-col">
                {searchTerms.map(t => (
                  <button
                    key={t}
                    className={`chip ${filters.searchTerms.size === 0 || filters.searchTerms.has(t) ? 'active' : ''}`}
                    onClick={() => toggleSearchTerm(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </FilterSection>
          )}
        </>
      )}
    </aside>
  )
}

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="filter-section-title mono-label">{title}</div>
      {children}
    </div>
  )
}
