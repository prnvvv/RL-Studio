import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfigPanel } from './ConfigPanel'
import { ControlToolbar } from './ControlToolbar'
import { LibraryPanel } from './LibraryPanel'
import { CATALOG } from './studioFixtures'
import {
  controlAvailability,
  emptyDraft,
  primaryAction,
  selectAgent,
  selectEnvironment,
} from './studioConfig'
import type { SessionStatus } from './studioTypes'

describe('primary action', () => {
  const pick = (status: SessionStatus | null, pending: 'pause' | null = null, canInit = true) =>
    primaryAction(status, controlAvailability(status, pending, canInit))

  it('moves emphasis through the session lifecycle', () => {
    expect(pick(null)).toBe('initialize')
    expect(pick(null, null, false)).toBeNull()
    expect(pick('initialized')).toBe('train')
    expect(pick('running')).toBe('pause')
    expect(pick('paused')).toBe('resume')
    expect(pick('completed')).toBe('initialize')
  })
})

describe('ControlToolbar', () => {
  const base = {
    pendingCommand: null,
    busy: null,
    speed: 1,
    initializeHint: null,
    viewMode: '3d' as const,
    webgl: true,
    onInitialize: vi.fn(),
    onCommand: vi.fn(),
    onSpeed: vi.fn(),
    onResetCamera: vi.fn(),
    onViewModeChange: vi.fn(),
    manual: { available: true, active: false, hint: '← / A' },
    onToggleManual: vi.fn(),
    compare: { active: false, available: true, onToggle: vi.fn() },
    brain: { active: false, available: true, onToggle: vi.fn() },
  }
  const renderBar = (status: SessionStatus | null, busy: string | null = null) =>
    render(
      <ControlToolbar
        {...base}
        busy={busy}
        status={status}
        availability={controlAvailability(status, null, true)}
      />,
    )

  it('makes Train the high-contrast action when initialized, and Pause when running', () => {
    const { unmount } = renderBar('initialized')
    expect(screen.getByRole('button', { name: 'Train' })).toHaveClass('btn--primary')
    expect(screen.getByRole('button', { name: 'Resume' })).not.toHaveClass('btn--primary')
    unmount()
    renderBar('running')
    expect(screen.getByRole('button', { name: 'Pause' })).toHaveClass('btn--primary')
    expect(screen.getByRole('button', { name: 'Train' })).not.toHaveClass('btn--primary')
  })

  it('separates training controls from viewport controls and keeps the render toggle with the latter', () => {
    renderBar('initialized')
    const viewport = screen.getByRole('group', { name: 'Viewport' })
    expect(within(viewport).getByRole('group', { name: 'Render mode' })).toBeInTheDocument()
    expect(within(viewport).getByRole('button', { name: 'Reset camera' })).toBeInTheDocument()
    expect(
      within(screen.getByRole('group', { name: 'Training' })).getByRole('button', {
        name: 'Train',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveAttribute('data-status', 'initialized')
  })

  it('shows a spinner and blocks every control while a command is in flight', () => {
    renderBar('initialized', 'start')
    expect(
      screen.getByRole('button', { name: /Starting/ }).querySelector('.spinner'),
    ).not.toBeNull()
    for (const button of within(screen.getByRole('group', { name: 'Training' })).getAllByRole(
      'button',
    )) {
      expect(button).toBeDisabled()
    }
  })

  it('disables the 3D toggle without WebGL and reports mode changes', () => {
    const onViewModeChange = vi.fn()
    render(
      <ControlToolbar
        {...base}
        webgl={false}
        onViewModeChange={onViewModeChange}
        status={null}
        availability={controlAvailability(null, null, true)}
      />,
    )
    expect(screen.getByRole('button', { name: '3D' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '2D' }))
    expect(onViewModeChange).toHaveBeenCalledWith('2d')
  })
})

describe('ConfigPanel tooltips', () => {
  const draft = selectEnvironment(
    CATALOG,
    selectAgent(CATALOG, emptyDraft(CATALOG), 'PPO'),
    'cartpole',
  )

  it('gives every hyperparameter an accessible help tooltip with range and default', () => {
    render(
      <ConfigPanel
        catalog={CATALOG}
        draft={draft}
        errors={{}}
        disabled={false}
        onChange={vi.fn()}
      />,
    )
    const clip = screen.getByRole('button', { name: 'About Clip range' })
    const tip = document.getElementById(clip.getAttribute('aria-describedby') ?? '')
    expect(tip).toHaveAttribute('role', 'tooltip')
    expect(tip).toHaveTextContent(/clipped to 1 ± this value/)
    expect(tip).toHaveTextContent('Range 0.05 to 0.5 · Default 0.2')
    expect(screen.getByRole('button', { name: 'About GAE lambda' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'About Learning rate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'About Gamma' })).toBeInTheDocument()
  })

  it('hides learning-only settings for an uploaded model and explains why', () => {
    const custom = selectEnvironment(
      CATALOG,
      selectAgent(CATALOG, emptyDraft(CATALOG), 'custom:mdl_abcdef123456'),
      'cartpole',
    )
    render(
      <ConfigPanel
        catalog={CATALOG}
        draft={custom}
        errors={{}}
        disabled={false}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByText(/runs inference only/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Checkpoint every')).toBeNull()
    expect(screen.queryByLabelText('Evaluation episodes')).toBeNull()
    expect(screen.getByLabelText('Total timesteps')).toBeInTheDocument()
  })
})

describe('LibraryPanel', () => {
  const props = {
    catalog: CATALOG,
    locked: false,
    onSelectAgent: vi.fn(),
    onSelectEnvironment: vi.fn(),
    onConfigure: vi.fn(),
    uploadModel: vi.fn(),
    uploadEnvironment: vi.fn(),
    onRemove: vi.fn().mockResolvedValue(undefined),
  }

  it('lists uploaded models with their inferred details and offers both upload cards', () => {
    render(<LibraryPanel {...props} draft={emptyDraft(CATALOG)} />)
    expect(screen.getByText('uploaded')).toBeInTheDocument()
    expect(screen.getByText(/PPO \(inferred\) · 4 inputs → 2 discrete · zip/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Drag & drop a custom model/ })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Drag & drop a custom grid environment/ }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Pickle and ONNX files are not accepted/)).toBeInTheDocument()
  })

  it('shows a prominent Configure shortcut once something is selected', () => {
    const { rerender } = render(<LibraryPanel {...props} draft={emptyDraft(CATALOG)} />)
    expect(screen.queryByRole('button', { name: 'Configure →' })).toBeNull()
    rerender(<LibraryPanel {...props} draft={selectAgent(CATALOG, emptyDraft(CATALOG), 'PPO')} />)
    fireEvent.click(screen.getByRole('button', { name: 'Configure →' }))
    expect(props.onConfigure).toHaveBeenCalled()
  })

  it('requires a second click to remove an uploaded model, and never offers it for built-ins', async () => {
    render(<LibraryPanel {...props} draft={emptyDraft(CATALOG)} />)
    expect(screen.getAllByRole('button', { name: /^Remove / })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Remove My policy' }))
    expect(props.onRemove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removing My policy' }))
    expect(props.onRemove).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'model', id: 'mdl_abcdef123456' }),
    )
  })

  it('freezes the upload cards while a session is active', () => {
    render(<LibraryPanel {...props} locked draft={emptyDraft(CATALOG)} />)
    expect(screen.getByRole('button', { name: /Drag & drop a custom model/ })).toBeDisabled()
  })
})
