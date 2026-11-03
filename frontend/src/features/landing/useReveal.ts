import { useEffect, useRef, useState } from 'react'

/**
 * Reports `true` once an element has scrolled into view, and then stays true (a reveal plays
 * once, it does not replay). Without IntersectionObserver (old browsers, jsdom) everything is
 * simply visible, so content is never left hidden. The CSS decides what "visible" looks like and
 * switches the motion off for prefers-reduced-motion.
 */
export function useReveal<T extends HTMLElement>(threshold = 0.18) {
  const ref = useRef<T>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold, rootMargin: '0px 0px -6% 0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [threshold])

  return { ref, visible }
}
