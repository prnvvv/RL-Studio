import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChaosPanel } from './ChaosPanel'
import { StudioStore } from './studioStore'
import { DEFAULT_CHAOS, type StudioEvent } from './studioTypes'

const base = {
  kinds: ['impulse', 'slip', 'sensor_noise'],
  chaos: DEFAULT_CHAOS,
  available: true,
  canTrigger: true,
}

describe('ChaosPanel', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('explains itself and disables every control until a session exists', () => {
    render(
      <ChaosPanel
        {...base}
        available={false}
        canTrigger={false}
        onChange={vi.fn()}
        onTrigger={vi.fn()}
      />,
    )
    expect(screen.getByText(/Initialize a session to use chaos mode/)).toBeInTheDocument()
    expect(screen.getByLabelText('Chaos mode')).toBeDisabled()
    expect(screen.getAllByRole('button', { name: 'Trigger now' })[0]).toBeDisabled()
  })

  it('sends the toggle, per-disturbance selection and triggers to the backend', () => {
    const onChange = vi.fn()
    const onTrigger = vi.fn()
    render(
      <ChaosPanel
        {...base}
        chaos={{ ...DEFAULT_CHAOS, kinds: ['slip'] }}
        onChange={onChange}
        onTrigger={onTrigger}
      />,
    )
    fireEvent.click(screen.getByLabelText('Chaos mode'))
    expect(onChange).toHaveBeenCalledWith({ enabled: true })
    fireEvent.click(screen.getByRole('checkbox', { name: /Sudden force/ }))
    expect(onChange).toHaveBeenCalledWith({ kinds: ['slip', 'impulse'] })
    fireEvent.click(screen.getByRole('checkbox', { name: /Actuator slip/ }))
    expect(onChange).toHaveBeenCalledWith({ kinds: [] })
    fireEvent.click(screen.getAllByRole('button', { name: 'Trigger now' })[1])
    expect(onTrigger).toHaveBeenCalledWith('slip')
  })

  it('commits the intensity once, after the slider settles', () => {
    const onChange = vi.fn()
    render(<ChaosPanel {...base} onChange={onChange} onTrigger={vi.fn()} />)
    const slider = screen.getByLabelText('Intensity')
    fireEvent.change(slider, { target: { value: '0.5' } })
    fireEvent.change(slider, { target: { value: '0.8' } })
    expect(onChange).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ intensity: 0.8 })
  })

  it('reports counts from the backend and handles environments without chaos', () => {
    const { rerender } = render(
      <ChaosPanel
        {...base}
        chaos={{ ...DEFAULT_CHAOS, events: 3, noise_steps: 40 }}
        onChange={vi.fn()}
        onTrigger={vi.fn()}
      />,
    )
    expect(screen.getByText(/Injected so far/)).toHaveTextContent(
      '3 disturbances · sensor noise on 40 steps',
    )
    rerender(<ChaosPanel {...base} kinds={[]} onChange={vi.fn()} onTrigger={vi.fn()} />)
    expect(screen.getByText(/does not support chaos mode/)).toBeInTheDocument()
  })
})

describe('store chaos state', () => {
  it('follows control events', () => {
    const store = new StudioStore()
    const event: StudioEvent = {
      schema_version: '1.0',
      seq: 1,
      type: 'control',
      session_id: 'ses_aaaaaaaa',
      timestamp: '',
      payload: {
        human: false,
        human_steps: 0,
        brain: false,
        chaos: { enabled: true, intensity: 0.7, kinds: ['slip'], events: 2, noise_steps: 0 },
      },
    }
    store.applySnapshot({ session_id: 'ses_aaaaaaaa', seq: 0 } as never)
    store.applyEvent(event)
    expect(store.getState().controls.chaos).toEqual({
      enabled: true,
      intensity: 0.7,
      kinds: ['slip'],
      events: 2,
      noise_steps: 0,
    })
  })
})
