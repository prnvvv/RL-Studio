import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
}

export function LogoMark(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" {...stroke} {...props}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="4.5" />
      <path d="M12 8 16 10.2v3.6L12 16l-4-2.2v-3.6z" />
    </svg>
  )
}

export function CubeIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" {...stroke} {...props}>
      <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9z" />
      <path d="M4 7.5 12 12l8-4.5M12 12v9" />
    </svg>
  )
}

export function PulseIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" {...stroke} {...props}>
      <path d="M3 12h4l2.5-6 4 12L16 12h5" />
    </svg>
  )
}

export function CycleIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" {...stroke} {...props}>
      <path d="M20 11a8 8 0 0 0-14.3-4.5L4 8.5M4 4v4.5h4.5" />
      <path d="M4 13a8 8 0 0 0 14.3 4.5L20 15.5M20 20v-4.5h-4.5" />
    </svg>
  )
}

export function ArrowIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" {...stroke} {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  )
}

export function PlayIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" {...stroke} {...props}>
      <rect x="2.5" y="2.5" width="15" height="15" rx="4.5" />
      <path d="M8.3 7.2 12.6 10l-4.3 2.8z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" {...stroke} {...props}>
      <path d="m4 6 4 4 4-4" />
    </svg>
  )
}

export function SparkleIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden focusable={false} {...props}>
      <path
        d="M12 2c.6 5.2 4.8 9.4 10 10-5.2.6-9.4 4.8-10 10-.6-5.2-4.8-9.4-10-10 5.2-.6 9.4-4.8 10-10z"
        fill="currentColor"
      />
    </svg>
  )
}
