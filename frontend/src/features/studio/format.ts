export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) return value.toExponential(2)
  return value.toFixed(digits)
}

export function formatInt(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : Math.round(value).toLocaleString('en-US')
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

/** Keep at most `max` points by uniform striding, always keeping the last. */
export function downsample<T>(items: T[], max: number): T[] {
  if (items.length <= max) return items
  const stride = items.length / max
  const out: T[] = []
  for (let i = 0; i < max - 1; i += 1) out.push(items[Math.floor(i * stride)])
  out.push(items[items.length - 1])
  return out
}
