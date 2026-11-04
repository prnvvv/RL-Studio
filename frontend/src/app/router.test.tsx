import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'

vi.mock('../pages/StudioPage', () => ({
  StudioPage: () => {
    const { pathname, search } = useLocation()
    return <div data-testid="studio">{pathname + search}</div>
  },
}))
vi.mock('../pages/HomePage', () => ({ HomePage: () => <div data-testid="landing" /> }))

import { AppRouter } from './router'

function renderAt(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('AppRouter', () => {
  it('serves the landing page at / and the Studio at /studio', () => {
    renderAt('/')
    expect(screen.getByTestId('landing')).toBeInTheDocument()
  })

  it('redirects the retired /training page into the Studio training view', () => {
    renderAt('/training')
    expect(screen.getByTestId('studio')).toHaveTextContent('/studio?view=training')
  })
})
