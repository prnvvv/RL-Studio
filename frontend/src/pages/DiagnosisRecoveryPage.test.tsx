import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ActiveProjectProvider } from '../contexts/ActiveProjectContext'
import { ThemeProvider } from '../contexts/ThemeContext'
import { DiagnosisRecoveryPage } from './DiagnosisRecoveryPage'

describe('DiagnosisRecoveryPage', () => {
  it('offers the assistant even when no project, run or incident exists', () => {
    render(
      <ThemeProvider>
        <ActiveProjectProvider>
          <MemoryRouter initialEntries={['/diagnosis-recovery']}>
            <DiagnosisRecoveryPage />
          </MemoryRouter>
        </ActiveProjectProvider>
      </ThemeProvider>,
    )
    expect(screen.getByRole('heading', { name: /Diagnosis & Recovery/ })).toBeInTheDocument()
    expect(screen.getByLabelText('Ask the assistant')).toBeInTheDocument()
    expect(screen.getByText('General assistant')).toBeInTheDocument()
    expect(screen.getByText(/does not need an incident/i)).toBeInTheDocument()
  })
})
