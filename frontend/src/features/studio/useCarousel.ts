import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

export interface CarouselEdges {
  /** Content is hidden past the left edge. */
  start: boolean
  /** Content is hidden past the right edge. */
  end: boolean
}

/**
 * Scroll state for a horizontally scrolling, snap-aligned row of cards: which edges still hide
 * content (so the view can fade only those), page-wise scrolling for mouse users, and bringing
 * the selected card into view. Native overflow handles trackpads and touch.
 */
export function useCarousel(dependency?: unknown) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState<CarouselEdges>({ start: false, end: false })

  const update = useCallback(() => {
    const track = trackRef.current
    if (!track) return
    const start = track.scrollLeft > 4
    const end = track.scrollLeft + track.clientWidth < track.scrollWidth - 4
    setEdges((previous) =>
      previous.start === start && previous.end === end ? previous : { start, end },
    )
  }, [])

  // Re-measure whenever the cards change, and when the row is resized.
  useLayoutEffect(update, [update, dependency])
  useEffect(() => {
    const track = trackRef.current
    if (!track || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(track)
    return () => observer.disconnect()
  }, [update])

  const page = useCallback((direction: 1 | -1) => {
    const track = trackRef.current
    if (!track) return
    track.scrollBy?.({ left: direction * track.clientWidth * 0.8, behavior: 'smooth' })
  }, [])

  /** Scroll the row (never the page) so the selected card is fully visible. */
  const reveal = useCallback(() => {
    const track = trackRef.current
    const selected = track?.querySelector<HTMLElement>('[aria-checked="true"]')
    if (!track || !selected) return
    const card = selected.parentElement ?? selected
    const left = card.offsetLeft - track.offsetLeft
    const right = left + card.offsetWidth
    if (left < track.scrollLeft) track.scrollTo?.({ left: left - 8, behavior: 'smooth' })
    else if (right > track.scrollLeft + track.clientWidth)
      track.scrollTo?.({ left: right - track.clientWidth + 8, behavior: 'smooth' })
  }, [])

  return { trackRef, edges, update, page, reveal }
}
