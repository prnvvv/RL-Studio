import { useEffect, useState } from 'react'

/**
 * Tracks whether a CSS media query currently matches, re-evaluating on
 * viewport changes. Used only for JS-driven responsive behaviour that CSS
 * alone cannot express, such as collapsing navigation into a labelled menu;
 * purely visual breakpoints stay in CSS (`src/styles/layout.css`).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query)
    const listener = (event: MediaQueryListEvent) => setMatches(event.matches)

    setMatches(mediaQueryList.matches)
    mediaQueryList.addEventListener('change', listener)
    return () => mediaQueryList.removeEventListener('change', listener)
  }, [query])

  return matches
}
