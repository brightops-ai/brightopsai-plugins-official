import { useState, useEffect } from 'react'
import Header from '@/components/Header'
import StatsBar from '@/components/StatsBar'
import Sidebar from '@/components/Sidebar'
import ListingGrid from '@/components/ListingGrid'
import ListingTable from '@/components/ListingTable'
import DetailPanel from '@/components/DetailPanel'
import ViewToggle from '@/components/ViewToggle'
import SearchTabs from '@/components/SearchTabs'
import { useListings } from '@/hooks/useListings'
import type { SearchSession, SearchIndex } from '@/types/listing'
import { CircleNotch } from '@phosphor-icons/react'

export default function App() {
  const [activeSearch, setActiveSearch] = useState<SearchSession | null>(null)
  const [csvUrl, setCsvUrl] = useState('/data/latest.csv')

  // Load searches.json on mount to get the latest search
  useEffect(() => {
    fetch('/data/searches.json')
      .then(r => r.json())
      .then((data: SearchIndex) => {
        if (data.searches.length > 0) {
          const latest = data.searches[data.searches.length - 1]
          setActiveSearch(latest)
          setCsvUrl(`/data/${latest.csvFile}`)
        }
      })
      .catch(() => {
        // Fall back to latest.csv if no searches.json
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

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', gap: '12px', flexDirection: 'column',
      }}>
        <CircleNotch size={28} weight="bold" color="var(--color-accent)"
          style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text-secondary)' }}>
          Loading listings...
        </span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', flexDirection: 'column', gap: '12px',
      }}>
        <p style={{ color: 'var(--color-grade-f)', fontWeight: 600, fontFamily: 'var(--font-display)', fontSize: 18 }}>
          Failed to load listings
        </p>
        <p style={{ color: 'var(--color-text-secondary)', fontSize: 12 }}>{error}</p>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 11 }}>
          Make sure a CSV file exists at public/data/latest.csv
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Header listings={allListings} />

      <SearchTabs
        activeSearchId={activeSearch?.id ?? null}
        onSelectSearch={handleSelectSearch}
      />

      <div style={{ padding: '0.75rem 1.5rem' }}>
        <StatsBar
          totalCount={filteredListings.length}
          gradeDistribution={gradeDistribution}
          avgPriceVsMarket={avgPriceVsMarket}
          bestDeal={bestDeal}
          top10FlipStats={top10FlipStats}
          allFlipStats={allFlipStats}
        />
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar
          filters={filters}
          updateFilter={updateFilter}
          searchTerms={searchTerms}
          conditions={conditions}
          priceRange={priceRange}
        />

        <main style={{ flex: 1, overflow: 'auto', padding: '0.75rem 1.5rem 1.5rem' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: '0.75rem',
          }}>
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

      {selectedListing && (
        <DetailPanel listing={selectedListing} onClose={() => setSelectedListing(null)} />
      )}
    </div>
  )
}
