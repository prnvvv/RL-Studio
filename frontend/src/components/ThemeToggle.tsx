import { useTheme } from '../contexts/ThemeContext'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      style={{
        padding: '6px 12px',
        background: 'var(--bg-panel)',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-sm)',
        cursor: 'pointer',
        fontSize: 'var(--text-sm)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      {theme === 'dark' ? 'Light' : 'Dark'}
    </button>
  )
}
