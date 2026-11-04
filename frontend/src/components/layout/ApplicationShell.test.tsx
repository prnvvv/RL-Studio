import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { ApplicationShell } from './ApplicationShell'

describe('ApplicationShell', () => {
  it('renders the product identity and primary navigation', () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/']}>
          <ApplicationShell>
            <h1>Content</h1>
          </ApplicationShell>
        </MemoryRouter>
      </ThemeProvider>,
    )

    expect(screen.getByText('RL Studio')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Training' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Environments' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Monitoring' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Diagnosis & Recovery' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
  })
})
