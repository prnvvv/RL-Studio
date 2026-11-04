import { CanvasTexture, SRGBColorSpace } from 'three'

interface GridTextureOptions {
  /** Pixels per cell edge (the canvas is cols*cellPx by rows*cellPx, capped for memory). */
  cellPx?: number
  /** Line thickness in canvas pixels. */
  lineWidth?: number
  /** Fade the lines out towards the rim; inner radius where fading starts (0-1 of the half-size). */
  fadeFrom?: number | null
}

const MAX_SIDE = 4096

/**
 * Grid texture for a ground plane. Lines are thick and fully opaque so the grid reads clearly against
 * the dark floor; WebGL line primitives are always 1px wide, so the grid is drawn as a texture.
 * Returns null when no 2D canvas is available.
 */
export function makeGridTexture(
  lineColor: string,
  cols: number,
  rows: number,
  { cellPx = 64, lineWidth = 5, fadeFrom = null }: GridTextureOptions = {},
): CanvasTexture | null {
  const scale = Math.min(1, MAX_SIDE / (Math.max(cols, rows) * cellPx))
  const width = Math.max(2, Math.round(cols * cellPx * scale))
  const height = Math.max(2, Math.round(rows * cellPx * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  ctx.strokeStyle = lineColor
  ctx.lineWidth = lineWidth
  // Inset by half a line so the outer border is not clipped by the canvas edge.
  const inset = lineWidth / 2
  for (let i = 0; i <= cols; i += 1) {
    const x = Math.min(width - inset, Math.max(inset, (i * width) / cols))
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, height)
    ctx.stroke()
  }
  for (let j = 0; j <= rows; j += 1) {
    const y = Math.min(height - inset, Math.max(inset, (j * height) / rows))
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(width, y)
    ctx.stroke()
  }

  if (fadeFrom !== null) {
    const r = Math.min(width, height) / 2
    const fade = ctx.createRadialGradient(
      width / 2,
      height / 2,
      r * fadeFrom,
      width / 2,
      height / 2,
      r,
    )
    fade.addColorStop(0, 'rgba(0, 0, 0, 1)')
    fade.addColorStop(1, 'rgba(0, 0, 0, 0.25)') // never fades to nothing: the edge stays visible
    ctx.globalCompositeOperation = 'destination-in'
    ctx.fillStyle = fade
    ctx.fillRect(0, 0, width, height)
  }

  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

/** Square ground grid whose lines stay fully visible near the centre and soften towards the rim. */
export function makeFadedGridTexture(lineColor: string, cells = 28): CanvasTexture | null {
  return makeGridTexture(lineColor, cells, cells, { cellPx: 36, lineWidth: 4, fadeFrom: 0.55 })
}
