import { Seal, SealCheck, SealWarning } from '@phosphor-icons/react'
import { getGradeColor } from '@/utils/grades'

interface GradeBadgeProps {
  grade: string
  size?: 'sm' | 'md' | 'lg'
}

const SIZES = { sm: 14, md: 18, lg: 24 }
const FONT_SIZES = { sm: '10px', md: '12px', lg: '15px' }

function GradeIcon({ grade, size }: { grade: string; size: number }) {
  const color = getGradeColor(grade)
  if (grade === 'A+' || grade === 'A') return <SealCheck size={size} weight="fill" color={color} />
  if (grade === 'F' || grade === 'D') return <SealWarning size={size} weight="fill" color={color} />
  return <Seal size={size} weight="fill" color={color} />
}

export default function GradeBadge({ grade, size = 'md' }: GradeBadgeProps) {
  const color = getGradeColor(grade)
  const iconSize = SIZES[size]
  const fontSize = FONT_SIZES[size]

  return (
    <span className="badge" style={{
      background: `color-mix(in srgb, ${color} 12%, transparent)`,
      border: `1px solid color-mix(in srgb, ${color} 25%, transparent)`,
      color,
      fontSize,
      fontWeight: 600,
      gap: 3,
    }}>
      <GradeIcon grade={grade} size={iconSize} />
      {grade}
    </span>
  )
}
