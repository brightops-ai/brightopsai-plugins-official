import { z } from 'zod'

export interface GradeBreakdown {
  priceValue: string
  sellerTrust: string
  listingQuality: string
  redFlags: string
  conditionConsistency: string
}

export type Platform = 'facebook' | 'ebay' | 'other'

export const GradeLetterValues = ['A+', 'A', 'B', 'C', 'D', 'F'] as const
export type GradeLetter = (typeof GradeLetterValues)[number]

export interface Listing {
  id: string
  searchTerm: string
  title: string
  price: number
  marketPriceLow: number
  marketPriceHigh: number
  marketPriceMedian: number
  priceVsMarket: number
  grade: GradeLetter
  gradeBreakdown: GradeBreakdown
  summary: string
  condition: string
  sellerName: string
  sellerRating: number | null
  sellerReviews: number
  sellerAccountAge: string
  sellerResponseTime: string
  location: string
  distance: string
  description: string
  photoCount: number
  photosOriginal: boolean
  redFlags: string[]
  listingUrl: string
  listingAge: string
  vendorUrl: string
  vendorPrice: number | null
  reviewUrl: string
  reviewScore: string
  dateScraped: string
  searchLocation: string
  searchRadius: number
  platform: Platform
  shippingEstimateLow: number
  shippingEstimateHigh: number
  ebayFees: number
  netProfitLow: number
  netProfitHigh: number
  roiLow: number
  roiHigh: number
  imageUrl?: string
}

export type ViewMode = 'grid' | 'table'

export interface SearchSession {
  id: string
  timestamp: string
  label: string
  searchTerms: string[]
  location: string
  radius: number
  maxPrice: number | null
  csvFile: string
  listingCount: number
  gradeDistribution: Record<string, number>
}

export interface SearchIndex {
  searches: SearchSession[]
}

// --- Zod schemas for runtime validation ---

export const SearchSessionSchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  label: z.string(),
  searchTerms: z.array(z.string()),
  location: z.string(),
  radius: z.number(),
  maxPrice: z.number().nullable(),
  csvFile: z.string(),
  listingCount: z.number(),
  gradeDistribution: z.record(z.string(), z.number()),
})

export const SearchIndexSchema = z.object({
  searches: z.array(SearchSessionSchema),
})

export interface FlipStats {
  totalProfit: number
  totalInvestment: number
  avgRoi: number
  itemCount: number
  estTurnaroundDays: string
}

export interface FilterState {
  grades: Set<string>
  priceMin: number | null
  priceMax: number | null
  conditions: Set<string>
  minSellerRating: number | null
  showRedFlagged: boolean
  searchTerms: Set<string>
}
