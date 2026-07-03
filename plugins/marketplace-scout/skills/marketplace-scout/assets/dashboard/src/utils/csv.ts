import Papa from 'papaparse'
import type { Listing, GradeBreakdown, GradeLetter, Platform } from '@/types/listing'
import { GradeLetterValues } from '@/types/listing'

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

function parseGrade(raw: string): GradeLetter {
  const trimmed = raw?.trim() ?? ''
  if ((GradeLetterValues as readonly string[]).includes(trimmed)) {
    return trimmed as GradeLetter
  }
  return 'F'
}

const PLATFORM_VALUES: readonly Platform[] = ['facebook', 'ebay', 'other']

function parsePlatform(raw: string | undefined): Platform {
  const trimmed = raw?.trim().toLowerCase() ?? ''
  if ((PLATFORM_VALUES as readonly string[]).includes(trimmed)) {
    return trimmed as Platform
  }
  return 'other'
}

function rowToListing(row: CsvRow): Listing {
  const listingUrl = row.listing_url ?? ''
  return {
    id: row.id ?? '',
    searchTerm: row.search_term ?? '',
    title: row.title ?? '',
    price: toNumber(row.price),
    marketPriceLow: toNumber(row.market_price_low),
    marketPriceHigh: toNumber(row.market_price_high),
    marketPriceMedian: toNumber(row.market_price_median),
    priceVsMarket: toNumber(row.price_vs_market),
    grade: parseGrade(row.grade),
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
    listingUrl,
    listingAge: row.listing_age ?? '',
    vendorUrl: row.vendor_url ?? '',
    vendorPrice: toNumberOrNull(row.vendor_price),
    reviewUrl: row.review_url ?? '',
    reviewScore: row.review_score ?? '',
    dateScraped: row.date_scraped ?? '',
    searchLocation: row.search_location ?? '',
    searchRadius: toNumber(row.search_radius),
    platform: parsePlatform(row.platform),
    imageUrl: row.image_url || undefined,
    shippingEstimateLow: toNumber(row.shipping_estimate_low),
    shippingEstimateHigh: toNumber(row.shipping_estimate_high),
    ebayFees: toNumber(row.ebay_fees),
    netProfitLow: toNumber(row.net_profit_low),
    netProfitHigh: toNumber(row.net_profit_high),
    roiLow: toNumber(row.roi_low),
    roiHigh: toNumber(row.roi_high),
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
        if (results.errors.length > 0) {
          const fatal = results.errors.filter(e => e.type === 'Delimiter' || e.type === 'FieldMismatch')
          for (const err of results.errors) {
            console.warn(`[CSV] Row ${err.row ?? '?'}: ${err.type} — ${err.message}`)
          }
          if (fatal.length > 0 && results.data.length === 0) {
            reject(new Error(`CSV parsing failed: ${fatal[0].message}`))
            return
          }
        }
        resolve(results.data.map(rowToListing))
      },
      error(err: Error) {
        reject(err)
      },
    })
  })
}
