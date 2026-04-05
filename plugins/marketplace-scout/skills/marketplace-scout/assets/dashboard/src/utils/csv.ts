import Papa from 'papaparse'
import type { Listing, GradeBreakdown } from '@/types/listing'

interface CsvRow {
  [key: string]: string
}

function parseGradeBreakdown(raw: string): GradeBreakdown {
  try {
    return JSON.parse(raw)
  } catch {
    return {
      priceValue: '',
      sellerTrust: '',
      listingQuality: '',
      redFlags: '',
      conditionConsistency: '',
    }
  }
}

function toNumber(val: string): number {
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

function toNumberOrNull(val: string): number | null {
  if (!val || val.trim() === '') return null
  const n = parseFloat(val)
  return isNaN(n) ? null : n
}

function rowToListing(row: CsvRow): Listing {
  return {
    id: row.id ?? '',
    searchTerm: row.search_term ?? '',
    title: row.title ?? '',
    price: toNumber(row.price),
    marketPriceLow: toNumber(row.market_price_low),
    marketPriceHigh: toNumber(row.market_price_high),
    marketPriceMedian: toNumber(row.market_price_median),
    priceVsMarket: toNumber(row.price_vs_market),
    grade: row.grade ?? '',
    gradeBreakdown: parseGradeBreakdown(row.grade_breakdown ?? '{}'),
    summary: row.summary ?? '',
    condition: row.condition ?? '',
    sellerName: row.seller_name ?? '',
    sellerRating: toNumberOrNull(row.seller_rating),
    sellerReviews: toNumber(row.seller_reviews),
    sellerAccountAge: row.seller_account_age ?? '',
    sellerResponseTime: row.seller_response_time ?? '',
    location: row.location ?? '',
    distance: row.distance ?? '',
    description: row.description ?? '',
    photoCount: toNumber(row.photo_count),
    photosOriginal: row.photos_original === 'true',
    redFlags: row.red_flags ? row.red_flags.split(',').map(s => s.trim()).filter(Boolean) : [],
    listingUrl: row.listing_url ?? '',
    listingAge: row.listing_age ?? '',
    vendorUrl: row.vendor_url ?? '',
    vendorPrice: toNumberOrNull(row.vendor_price),
    reviewUrl: row.review_url ?? '',
    reviewScore: row.review_score ?? '',
    dateScraped: row.date_scraped ?? '',
    searchLocation: row.search_location ?? '',
    searchRadius: toNumber(row.search_radius),
  }
}

export async function loadListingsFromCsv(url: string): Promise<Listing[]> {
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error(`Failed to load CSV from ${response.url || url}: ${response.status} ${response.statusText}`)
  }

  const text = await response.text()

  return new Promise((resolve, reject) => {
    Papa.parse<CsvRow>(text, {
      header: true,
      skipEmptyLines: true,
      complete(results) {
        resolve(results.data.map(rowToListing))
      },
      error(err: Error) {
        reject(err)
      },
    })
  })
}
