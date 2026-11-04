import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Unit tests exercise pages in isolation, not Clerk. Provide a signed-out,
// loaded session so components that read auth state do not need a real
// ClerkProvider (which would require network and a publishable key).
vi.mock('@clerk/react', () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useUser: () => ({ isLoaded: true, isSignedIn: false, user: null }),
  useAuth: () => ({ isLoaded: true, isSignedIn: false, userId: null }),
  SignIn: () => null,
  SignOutButton: () => null,
}))

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