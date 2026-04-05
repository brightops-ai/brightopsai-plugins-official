import type { Listing, FilterState } from '@/types/listing'

export function createDefaultFilters(): FilterState {
  return {
    grades: new Set(['A+', 'A', 'B', 'C', 'D', 'F']),
    priceMin: null,
    priceMax: null,
    conditions: new Set(),
    minSellerRating: null,
    showRedFlagged: true,
    searchTerms: new Set(),
  }
}

export function applyFilters(listings: Listing[], filters: FilterState): Listing[] {
  return listings.filter(l => {
    if (!filters.grades.has(l.grade)) return false
    if (filters.priceMin !== null && l.price < filters.priceMin) return false
    if (filters.priceMax !== null && l.price > filters.priceMax) return false
    if (filters.conditions.size > 0 && !filters.conditions.has(l.condition)) return false
    if (filters.minSellerRating !== null && l.sellerRating !== null && l.sellerRating < filters.minSellerRating) return false
    if (!filters.showRedFlagged && l.redFlags.length > 0) return false
    if (filters.searchTerms.size > 0 && !filters.searchTerms.has(l.searchTerm)) return false
    return true
  })
}

export function getUniqueSearchTerms(listings: Listing[]): string[] {
  return [...new Set(listings.map(l => l.searchTerm))].sort()
}

export function getUniqueConditions(listings: Listing[]): string[] {
  return [...new Set(listings.map(l => l.condition))].filter(Boolean).sort()
}

export function getPriceRange(listings: Listing[]): [number, number] {
  if (listings.length === 0) return [0, 1000]
  const prices = listings.map(l => l.price)
  return [Math.min(...prices), Math.max(...prices)]
}
