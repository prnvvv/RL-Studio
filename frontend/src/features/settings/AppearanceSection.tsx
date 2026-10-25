import { useTheme } from '../../contexts/ThemeContext'

const options = [
  {
    value: 'dark',
    label: 'Dark',
    description: 'Pure black surfaces with near-white text. The primary reference theme.',
  },
  {
    value: 'light',
    label: 'Light',
    description: 'Soft light-grey surfaces with near-black text. Same layout and density.',
  },
] as const

/**
 * Theme preference.
 *
 * Both controls and the header toggle read and write the single `ThemeContext`
 * value, so there is one preference store, not two. Persistence is the existing
 * browser `localStorage` entry; nothing here touches a backend.
 */
export function AppearanceSection() {
  const { theme, setTheme } = useTheme()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <fieldset className="choice-group" style={{ margin: 0 }}>
        <legend
          style={{
            padding: 0,
            marginBottom: 'var(--space-2)',
            fontSize: 'var(--text-sm)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Theme
        </legend>

        {options.map((option) => (
          <label key={option.value} className="choice-option">
            <input
              type="radio"
              name="theme"
              value={option.value}
              checked={theme === option.value}
              onChange={() => setTheme(option.value)}
            />
            <span style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <span
                style={{
                  fontSize: 'var(--text-sm)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {option.label}
              </span>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {option.description}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <p
        role="status"
        aria-live="polite"
        style={{
          margin: 0,
          fontSize: 'var(--text-xs)',
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        Currently using the {theme} theme. The selection is saved in this browser only
        (`self-healing-rl-studio-theme`) and is not synced to an account. Changing the theme does
        not affect runs, data, or backend state.
      </p>
    </div>
  )
}
