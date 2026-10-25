import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Testing Library auto-cleans when it can detect the global afterEach; doing it
// explicitly keeps DOM and storage state from leaking between files.
afterEach(() => {
  cleanup()
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})
