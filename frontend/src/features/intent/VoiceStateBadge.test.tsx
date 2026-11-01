import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { VoiceStateBadge } from './VoiceStateBadge'

describe('VoiceStateBadge', () => {
  it('labels every documented dictation state in text', () => {
    const { rerender } = render(<VoiceStateBadge state="idle" />)
    expect(screen.getByText('Dictation ready')).toBeInTheDocument()

    rerender(<VoiceStateBadge state="listening" />)
    expect(screen.getByText('Listening')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()

    rerender(<VoiceStateBadge state="recognised" />)
    expect(screen.getByText('Speech recognised — review the inserted text')).toBeInTheDocument()

    rerender(<VoiceStateBadge state="unsupported" />)
    expect(screen.getByText('Dictation unavailable in this browser')).toBeInTheDocument()

    rerender(<VoiceStateBadge state="permission_denied" />)
    expect(screen.getByText('Microphone permission denied')).toBeInTheDocument()

    rerender(<VoiceStateBadge state="error" />)
    expect(screen.getByText('Dictation error')).toBeInTheDocument()
  })

  it('shows the engine message for errors and announces it as an alert', () => {
    render(<VoiceStateBadge state="error" message="No speech was detected." />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Dictation error')).toBeInTheDocument()
    expect(screen.getByText('No speech was detected.')).toBeInTheDocument()
  })
})
