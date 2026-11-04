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
vi.mock('../pages/ProjectsPage', () => ({ ProjectsPage: () => <div data-testid="projects" /> }))
vi.mock('../pages/ProjectWorkspacePage', () => ({
  ProjectWorkspacePage: () => <div data-testid="workspace" />,
}))

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

  it('serves the project dashboard and a project workspace by direct route', () => {
    renderAt('/projects')
    expect(screen.getByTestId('projects')).toBeInTheDocument()
  })

  it('opens a project workspace from a direct link', () => {
    renderAt('/projects/prj_0123456789abcdef')
    expect(screen.getByTestId('workspace')).toBeInTheDocument()
  })

  it('safely 404s on the removed /environments page instead of rendering or redirecting', () => {
    renderAt('/environments')
    expect(screen.getByText('This page does not exist')).toBeInTheDocument()
    expect(screen.queryByTestId('studio')).not.toBeInTheDocument()
  })

  it('redirects the retired /training page into the Studio training view', () => {
    renderAt('/training')
    expect(screen.getByTestId('studio')).toHaveTextContent('/studio?view=training')
  })
})
