export interface GradeBreakdown {
  priceValue: string
  sellerTrust: string
  listingQuality: string
  redFlags: string
  conditionConsistency: string
}

export interface Listing {
  id: string
  searchTerm: string
  title: string
  price: number
  marketPriceLow: number
  marketPriceHigh: number
  marketPriceMedian: number
  priceVsMarket: number
  grade: string
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
}

export type GradeLetter = 'A+' | 'A' | 'B' | 'C' | 'D' | 'F'
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
