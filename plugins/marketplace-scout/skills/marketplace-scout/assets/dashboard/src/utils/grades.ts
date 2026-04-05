const GRADE_COLORS: Record<string, string> = {
  'A+': 'var(--color-grade-aplus)',
  'A': 'var(--color-grade-a)',
  'B': 'var(--color-grade-b)',
  'C': 'var(--color-grade-c)',
  'D': 'var(--color-grade-d)',
  'F': 'var(--color-grade-f)',
}

const GRADE_ORDER: string[] = ['A+', 'A', 'B', 'C', 'D', 'F']

export function getGradeColor(grade: string): string {
  return GRADE_COLORS[grade] ?? 'var(--color-text-muted)'
}

export function getGradeOrder(grade: string): number {
  const idx = GRADE_ORDER.indexOf(grade)
  return idx === -1 ? 99 : idx
}

export function compareGrades(a: string, b: string): number {
  return getGradeOrder(a) - getGradeOrder(b)
}

export function getGradeDistribution(listings: { grade: string }[]): Record<string, number> {
  const dist: Record<string, number> = {}
  for (const g of GRADE_ORDER) dist[g] = 0
  for (const l of listings) {
    dist[l.grade] = (dist[l.grade] ?? 0) + 1
  }
  return dist
}
