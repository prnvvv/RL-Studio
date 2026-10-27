import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { AppearanceSection } from './AppearanceSection'

function renderSection() {
  render(
    <ThemeProvider>
      <AppearanceSection />
    </ThemeProvider>,
  )
}

describe('AppearanceSection', () => {
  it('reflects the active theme and states it in text', () => {
    renderSection()

    expect(screen.getByRole('radio', { name: /^Dark/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /^Light/ })).not.toBeChecked()
    expect(screen.getByRole('status')).toHaveTextContent('Currently using the dark theme.')
  })

  it('applies a theme change to the document root', () => {
    renderSection()

    fireEvent.click(screen.getByRole('radio', { name: /^Light/ }))

    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(screen.getByRole('radio', { name: /^Light/ })).toBeChecked()
    expect(screen.getByRole('status')).toHaveTextContent('Currently using the light theme.')
  })

  it('persists the preference to the single browser storage key', () => {
    renderSection()

    fireEvent.click(screen.getByRole('radio', { name: /^Light/ }))

    expect(window.localStorage.getItem('self-healing-rl-studio-theme')).toBe('light')
  })

  it('does not offer a theme option the application cannot render', () => {
    renderSection()

    const radios = screen.getAllByRole('radio')
    expect(radios.map((radio) => radio.getAttribute('value'))).toEqual(['dark', 'light'])
    // No "system" or "high contrast" option is invented.
    expect(screen.queryByRole('radio', { name: /system|contrast/i })).not.toBeInTheDocument()
  })

  it('is reachable and operable from the keyboard', () => {
    renderSection()

    const dark = screen.getByRole('radio', { name: /^Dark/ })
    dark.focus()
    expect(dark).toHaveFocus()

    // Native radio group: arrow keys move selection.
    fireEvent.keyDown(dark, { key: 'ArrowRight' })
    fireEvent.click(screen.getByRole('radio', { name: /^Light/ }))
    expect(screen.getByRole('radio', { name: /^Light/ })).toBeChecked()
  })
})
