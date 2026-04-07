import { useState, useEffect } from 'react'
import Header from '@/components/Header'
import NavTabs from '@/components/NavTabs'
import type { AppTab } from '@/components/NavTabs'
import StatsBar from '@/components/StatsBar'
import Sidebar from '@/components/Sidebar'
import ListingGrid from '@/components/ListingGrid'
import ListingTable from '@/components/ListingTable'
import DetailPanel from '@/components/DetailPanel'
import ViewToggle from '@/components/ViewToggle'
import SearchTabs from '@/components/SearchTabs'
import FlipsView from '@/views/FlipsView'
import AnalyticsView from '@/views/AnalyticsView'
import { useListings } from '@/hooks/useListings'
import { useTheme } from '@/hooks/useTheme'
import type { SearchSession, SearchIndex } from '@/types/listing'
import { CircleNotch } from '@phosphor-icons/react'

export default function App() {
  const { theme, toggleTheme } = useTheme()
  const [activeTab, setActiveTab] = useState<AppTab>('scouts')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [sessions, setSessions] = useState<SearchSession[]>([])
  const [activeSearch, setActiveSearch] = useState<SearchSession | null>(null)
  const [csvUrl, setCsvUrl] = useState('/data/latest.csv')

  useEffect(() => {
    fetch('/data/searches.json')
      .then(r => r.json())
      .then((data: SearchIndex) => {
        setSessions(data.searches)
        if (data.searches.length > 0) {
          const latest = data.searches[data.searches.length - 1]
          setActiveSearch(latest)
          setCsvUrl(`/data/${latest.csvFile}`)
        }
      })
      .catch(() => {
        setCsvUrl('/data/latest.csv')
      })
  }, [])

  const handleSelectSearch = (session: SearchSession) => {
    setActiveSearch(session)
    setCsvUrl(`/data/${session.csvFile}`)
  }

  const {
    allListings,
    filteredListings,
    filters,
    updateFilter,
    viewMode,
    setViewMode,
    selectedListing,
    setSelectedListing,
    sortField,
    sortAsc,
    toggleSort,
    loading,
    error,
    searchTerms,
    conditions,
    priceRange,
    gradeDistribution,
    bestDeal,
    avgPriceVsMarket,
    top10FlipStats,
    allFlipStats,
  } = useListings(csvUrl)

  const flipCount = allListings.filter(l => l.netProfitHigh > 0 && l.grade !== 'F').length

  if (loading) {
    return (
      <div className="centered-message">
        <CircleNotch size={28} weight="bold" color="var(--color-accent)" className="loading-spinner" />
        <span className="loading-text">Loading listings...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="centered-message">
        <p className="error-title">Failed to load listings</p>
        <p className="error-message">{error}</p>
        <p className="loading-text">Make sure a CSV file exists at public/data/latest.csv</p>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Header listings={allListings} theme={theme} onToggleTheme={toggleTheme} />

      <NavTabs activeTab={activeTab} onChange={setActiveTab} flipCount={flipCount} />

      {activeTab === 'scouts' && (
        <>
          <SearchTabs
            sessions={sessions}
            activeSearchId={activeSearch?.id ?? null}
            onSelectSearch={handleSelectSearch}
          />

          <div className="stats-wrapper">
            <StatsBar
              totalCount={filteredListings.length}
              gradeDistribution={gradeDistribution}
              avgPriceVsMarket={avgPriceVsMarket}
              bestDeal={bestDeal}
              top10FlipStats={top10FlipStats}
              allFlipStats={allFlipStats}
            />
          </div>

          <div className="app-main-area">
            <Sidebar
              filters={filters}
              updateFilter={updateFilter}
              searchTerms={searchTerms}
              conditions={conditions}
              priceRange={priceRange}
              collapsed={sidebarCollapsed}
              onToggleCollapse={() => setSidebarCollapsed(c => !c)}
            />

            <main className="main-content">
              <div className="main-toolbar">
                <span className="mono-label">
                  {filteredListings.length} listing{filteredListings.length !== 1 ? 's' : ''}
                </span>
                <ViewToggle viewMode={viewMode} onChange={setViewMode} />
              </div>

              {viewMode === 'grid' ? (
                <ListingGrid listings={filteredListings} onSelect={setSelectedListing} />
              ) : (
                <ListingTable
                  listings={filteredListings}
                  sortField={sortField}
                  sortAsc={sortAsc}
                  onSort={toggleSort}
                  onSelect={setSelectedListing}
                />
              )}
            </main>
          </div>
        </>
      )}

      {activeTab === 'flips' && (
        <div className="main-content">
          <FlipsView listings={allListings} onSelect={setSelectedListing} />
        </div>
      )}

      {activeTab === 'analytics' && (
        <div className="main-content">
          <AnalyticsView
            listings={allListings}
            gradeDistribution={gradeDistribution}
            avgPriceVsMarket={avgPriceVsMarket}
            top10FlipStats={top10FlipStats}
            allFlipStats={allFlipStats}
          />
        </div>
      )}

      {selectedListing && (
        <DetailPanel listing={selectedListing} onClose={() => setSelectedListing(null)} />
      )}
    </div>
  )
}
