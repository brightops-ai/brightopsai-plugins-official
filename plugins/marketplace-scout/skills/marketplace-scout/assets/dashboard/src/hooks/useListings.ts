import { useState, useEffect, useMemo, useCallback } from 'react'
import type { Listing, FilterState, ViewMode, FlipStats } from '@/types/listing'
import { loadListingsFromCsv } from '@/utils/csv'
import { applyFilters, createDefaultFilters, getUniqueSearchTerms, getUniqueConditions, getPriceRange } from '@/utils/filters'
import { getGradeDistribution } from '@/utils/grades'

export function useListings(csvUrl: string) {
  const [allListings, setAllListings] = useState<Listing[]>([])
  const [filters, setFilters] = useState<FilterState>(createDefaultFilters)
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [sortField, setSortField] = useState<keyof Listing>('grade')
  const [sortAsc, setSortAsc] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setSelectedListing(null)
    setFilters(createDefaultFilters())
    loadListingsFromCsv(csvUrl)
      .then(setAllListings)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load CSV'))
      .finally(() => setLoading(false))
  }, [csvUrl])

  const filteredListings = useMemo(
    () => applyFilters(allListings, filters),
    [allListings, filters],
  )

  const searchTerms = useMemo(() => getUniqueSearchTerms(allListings), [allListings])
  const conditions = useMemo(() => getUniqueConditions(allListings), [allListings])
  const priceRange = useMemo(() => getPriceRange(allListings), [allListings])
  const gradeDistribution = useMemo(() => getGradeDistribution(filteredListings), [filteredListings])

  const bestDeal = useMemo(() => {
    if (filteredListings.length === 0) return null
    return filteredListings.reduce((best, l) =>
      l.priceVsMarket < best.priceVsMarket ? l : best
    )
  }, [filteredListings])

  const avgPriceVsMarket = useMemo(() => {
    if (filteredListings.length === 0) return 0
    const sum = filteredListings.reduce((acc, l) => acc + l.priceVsMarket, 0)
    return Math.round(sum / filteredListings.length)
  }, [filteredListings])

  // Flip profit calculations
  const computeFlipStats = (listings: Listing[]): FlipStats => {
    const flippable = listings.filter(l =>
      l.marketPriceMedian > 0 && l.price > 0 && l.grade !== 'X' && l.grade !== 'F'
    )
    if (flippable.length === 0) return { totalProfit: 0, totalInvestment: 0, avgRoi: 0, itemCount: 0, estTurnaroundDays: '—' }

    let totalProfit = 0
    let totalInvestment = 0
    for (const l of flippable) {
      const ebayFees = l.marketPriceMedian * 0.13
      const estShipping = l.price > 400 ? 25 : l.price > 100 ? 15 : 10
      const profit = l.marketPriceMedian - ebayFees - estShipping - l.price
      if (profit > 0) {
        totalProfit += profit
        totalInvestment += l.price
      }
    }
    const avgRoi = totalInvestment > 0 ? Math.round((totalProfit / totalInvestment) * 100) : 0
    const avgPrice = totalInvestment / flippable.length
    const days = avgPrice < 100 ? '3-5' : avgPrice < 300 ? '5-10' : avgPrice < 600 ? '7-14' : '10-21'

    return { totalProfit: Math.round(totalProfit), totalInvestment: Math.round(totalInvestment), avgRoi, itemCount: flippable.length, estTurnaroundDays: days }
  }

  const top10FlipStats = useMemo(() => {
    const sorted = [...filteredListings]
      .filter(l => l.marketPriceMedian > 0 && l.price > 0 && l.grade !== 'X' && l.grade !== 'F')
      .sort((a, b) => {
        const roiA = (a.marketPriceMedian * 0.87 - a.price) / a.price
        const roiB = (b.marketPriceMedian * 0.87 - b.price) / b.price
        return roiB - roiA
      })
      .slice(0, 10)
    return computeFlipStats(sorted)
  }, [filteredListings])

  const allFlipStats = useMemo(() => {
    return computeFlipStats(filteredListings)
  }, [filteredListings])

  const updateFilter = useCallback(<K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }, [])

  const toggleSort = useCallback((field: keyof Listing) => {
    setSortField(prev => {
      if (prev === field) {
        setSortAsc(a => !a)
        return prev
      }
      setSortAsc(true)
      return field
    })
  }, [])

  return {
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
  }
}
