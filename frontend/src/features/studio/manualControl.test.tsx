import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ControlToolbar } from './ControlToolbar'
import { actionForKey, controlHint } from './humanControl'
import { controlAvailability } from './studioConfig'
import { StudioStore } from './studioStore'
import type { StudioEvent } from './studioTypes'
import { useManualControl } from './useManualControl'

describe('key mapping', () => {
  it('maps arrows and WASD to CartPole pushes', () => {
    expect(actionForKey('cartpole', 'ArrowLeft')).toBe(0)
    expect(actionForKey('cartpole', 'D')).toBe(1)
    expect(actionForKey('cartpole', 'ArrowUp')).toBeNull()
  })

  it('maps four directions for the warehouse grid in the backend action order', () => {
    const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']
    expect(keys.map((k) => actionForKey('grid_maze', k))).toEqual([0, 1, 2, 3])
    expect(['w', 's', 'a', 'd'].map((k) => actionForKey('grid_maze', k))).toEqual([0, 1, 2, 3])
  })

  it('has no mapping for unknown environments', () => {
    expect(actionForKey('mystery', 'ArrowLeft')).toBeNull()
    expect(actionForKey(null, 'ArrowLeft')).toBeNull()
    expect(controlHint('mystery')).toBeNull()
    expect(controlHint('cartpole')).toMatch(/push left/)
  })
})

function Probe({ active, send }: { active: boolean; send: (a: number) => void }) {
  useManualControl(active, 'cartpole', send)
  return <input aria-label="field" />
}

describe('useManualControl', () => {
  it('sends the mapped action and prevents the default scroll while active', () => {
    const send = vi.fn()
    render(<Probe active send={send} />)
    const event = new KeyboardEvent('keydown', {
      key: 'ArrowRight',
      cancelable: true,
      bubbles: true,
    })
    window.dispatchEvent(event)
    expect(send).toHaveBeenCalledWith(1)
    expect(event.defaultPrevented).toBe(true)
  })

  it('does nothing while inactive, for unmapped keys, or when typing in a field', () => {
    const send = vi.fn()
    const { rerender } = render(<Probe active={false} send={send} />)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    rerender(<Probe active send={send} />)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x' }))
    fireEvent.keyDown(screen.getByLabelText('field'), { key: 'ArrowLeft' })
    expect(send).not.toHaveBeenCalled()
  })

  it('stops listening when control is released', () => {
    const send = vi.fn()
    const { rerender } = render(<Probe active send={send} />)
    rerender(<Probe active={false} send={send} />)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    expect(send).not.toHaveBeenCalled()
  })
})

describe('store manual-control state', () => {
  const event = (seq: number, type: string, payload: Record<string, unknown>): StudioEvent => ({
    schema_version: '1.0',
    seq,
    type,
    session_id: 'ses_aaaaaaaa',
    timestamp: '',
    payload,
  })

  it('follows control events and clears them on reset', () => {
    const store = new StudioStore()
    store.applySnapshot({
      session_id: 'ses_aaaaaaaa',
      run_id: 'ses_aaaaaaaa_r1',
      name: 'n',
      status: 'running',
      pending_command: null,
      agent: 'PPO',
      environment: 'cartpole',
      config: {
        agent: 'PPO',
        environment: 'cartpole',
        agent_params: {},
        env_params: {},
        training: {},
      },
      created_at: '',
      started_at: null,
      finished_at: null,
      error: null,
      progress: null as never,
      checkpoints: [],
      scene: {},
      episodes: [],
      updates: [],
      evaluations: [],
      seq: 0,
      frame: null,
    })
    expect(store.getState().controls).toEqual({ human: false, human_steps: 0 })
    store.applyEvent(event(1, 'control', { human: true, human_steps: 3 }))
    expect(store.getState().controls).toEqual({ human: true, human_steps: 3 })
    store.applyEvent(event(2, 'reset', {}))
    expect(store.getState().controls.human).toBe(false)
  })

  it('only sends while a socket is attached', () => {
    const store = new StudioStore()
    expect(store.send({ type: 'action', action: 1 })).toBe(false)
    const sent: unknown[] = []
    store.setSender((m) => (sent.push(m), true))
    expect(store.send({ type: 'action', action: 1 })).toBe(true)
    store.setSender(null)
    expect(store.send({ type: 'action', action: 1 })).toBe(false)
    expect(sent).toEqual([{ type: 'action', action: 1 }])
  })
})

describe('manual control toolbar button', () => {
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
  }

  it('toggles between taking and releasing control', () => {
    const onToggleManual = vi.fn()
    const { rerender } = render(
      <ControlToolbar
        {...base}
        status="running"
        availability={controlAvailability('running', null, true)}
        manual={{ available: true, active: false, hint: '← / A' }}
        onToggleManual={onToggleManual}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Take control' }))
    expect(onToggleManual).toHaveBeenCalled()
    rerender(
      <ControlToolbar
        {...base}
        status="running"
        availability={controlAvailability('running', null, true)}
        manual={{ available: true, active: true, hint: '← / A' }}
        onToggleManual={onToggleManual}
      />,
    )
    expect(screen.getByRole('button', { name: 'Release control' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('is unavailable before training starts and for environments without a mapping', () => {
    const { rerender } = render(
      <ControlToolbar
        {...base}
        status="initialized"
        availability={controlAvailability('initialized', null, true)}
        manual={{ available: false, active: false, hint: '← / A' }}
        onToggleManual={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Take control' })).toBeDisabled()
    rerender(
      <ControlToolbar
        {...base}
        status="running"
        availability={controlAvailability('running', null, true)}
        manual={{ available: false, active: false, hint: null }}
        onToggleManual={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Take control' })).toHaveAttribute(
      'title',
      expect.stringContaining('no keyboard mapping'),
    )
  })
})
