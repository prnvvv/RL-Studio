import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

type Theme = 'dark' | 'light'

interface ThemeContextValue {
  theme: Theme
  toggleTheme: (origin?: { x: number; y: number }) => void
  setTheme: (theme: Theme, origin?: { x: number; y: number }) => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

const THEME_STORAGE_KEY = 'self-healing-rl-studio-theme'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
  if (stored === 'dark' || stored === 'light') return stored
  return 'dark'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  const setTheme = (newTheme: Theme, origin?: { x: number; y: number }) => {
    if (newTheme === theme) return
    const root = document.documentElement
    const apply = () => {
      setThemeState(newTheme)
      root.dataset.theme = newTheme
    }
    const startViewTransition = (document as Document & { startViewTransition?: (cb: () => void) => { finished: Promise<void> } }).startViewTransition
    if (origin && typeof startViewTransition === 'function') {
      const radius = Math.hypot(
        Math.max(origin.x, window.innerWidth - origin.x),
        Math.max(origin.y, window.innerHeight - origin.y),
      )
      root.style.setProperty('--theme-x', `${origin.x}px`)
      root.style.setProperty('--theme-y', `${origin.y}px`)
      root.style.setProperty('--theme-r', `${radius}px`)
      root.classList.add('theme-animating')
      const transition = startViewTransition.call(document, apply)
      transition.finished.finally(() => root.classList.remove('theme-animating'))
    } else {
      apply()
    }
  }

  const toggleTheme = (origin?: { x: number; y: number }) => {
    setTheme(theme === 'dark' ? 'light' : 'dark', origin)
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
