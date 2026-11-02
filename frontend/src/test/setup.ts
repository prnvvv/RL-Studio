import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom does not implement matchMedia. Default to "does not match" (a desktop
// viewport never matches a narrow-width query) so components using
// `useMediaQuery` render their wide-viewport layout unless a test explicitly
// stubs `window.matchMedia` to exercise the narrow case.
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}

// Testing Library auto-cleans when it can detect the global afterEach; doing it
// explicitly keeps DOM and storage state from leaking between files.
afterEach(() => {
  cleanup()
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})
