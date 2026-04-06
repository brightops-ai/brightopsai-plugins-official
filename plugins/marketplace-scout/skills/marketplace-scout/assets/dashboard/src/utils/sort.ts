import type { Listing } from '@/types/listing'
import { compareGrades } from '@/utils/grades'

export function sortListings(listings: Listing[], field: keyof Listing, asc: boolean): Listing[] {
  return [...listings].sort((a, b) => {
    let cmp = 0
    if (field === 'grade') {
      cmp = compareGrades(a.grade, b.grade)
    } else if (field === 'distance') {
      const parseDist = (d: string) => { const n = parseFloat(d); return isNaN(n) ? 999 : n }
      cmp = parseDist(a.distance) - parseDist(b.distance)
    } else {
      const va = a[field]
      const vb = b[field]
      if (typeof va === 'number' && typeof vb === 'number') cmp = va - vb
      else cmp = String(va ?? '').localeCompare(String(vb ?? ''))
    }
    return asc ? cmp : -cmp
  })
}
