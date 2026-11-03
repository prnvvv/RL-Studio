import { CanvasTexture, SRGBColorSpace } from 'three'

/**
 * A square grid texture whose lines fade out towards the edges, giving the
 * ground a sense of depth. Returns null when no 2D canvas is available.
 */
export function makeFadedGridTexture(
  lineColor: string,
  cells = 28,
  size = 1024,
): CanvasTexture | null {
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  ctx.strokeStyle = lineColor
  ctx.lineWidth = 2
  for (let i = 0; i <= cells; i += 1) {
    const at = (i * size) / cells
    ctx.beginPath()
    ctx.moveTo(at, 0)
    ctx.lineTo(at, size)
    ctx.moveTo(0, at)
    ctx.lineTo(size, at)
    ctx.stroke()
  }

  // Keep the lines opaque near the centre and fade them to nothing at the rim.
  const fade = ctx.createRadialGradient(
    size / 2,
    size / 2,
    size * 0.1,
    size / 2,
    size / 2,
    size / 2,
  )
  fade.addColorStop(0, 'rgba(0, 0, 0, 1)')
  fade.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.globalCompositeOperation = 'destination-in'
  ctx.fillStyle = fade
  ctx.fillRect(0, 0, size, size)

  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}
