import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { PlaybackControls } from './PlaybackControls'
import { usePlayback } from '../../hooks/usePlayback'

const ADVANCE_MS = 100

/**
 * Test boundary matching real composition: a parent component owns the
 * playback hook and hands its controls down, so the controls re-render as
 * playback state changes.
 */
function PlaybackHarness({ min, max }: { min: number; max: number }) {
  const controls = usePlayback(min, max, ADVANCE_MS)
  return <PlaybackControls min={min} max={max} controls={controls} />
}

function sliderValue(): number {
  const slider = screen.getByRole('slider')
  return Number(slider.getAttribute('value'))
}

describe('PlaybackControls', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the recorded window on an accessible slider', () => {
    render(<PlaybackHarness min={796} max={825} />)
    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('min', '796')
    expect(slider).toHaveAttribute('max', '825')
    expect(slider).toHaveAttribute('value', '796')
    expect(slider).toHaveAccessibleName(/Playback timestep/i)
    // The cursor operates in the recording's own timestep units.
    expect(slider).toHaveAttribute('aria-valuetext', 'Timestep 796 of 825')
  })

  it('scrubs the cursor to any recorded timestep through the slider', () => {
    render(<PlaybackHarness min={796} max={825} />)
    fireEvent.change(screen.getByRole('slider'), { target: { value: '812' } })
    expect(screen.getByTestId('playback-status').textContent).toMatch(/Timestep 812 \/ 825/)
    // Scrubbing clamps at the recorded bounds — never beyond them.
    fireEvent.change(screen.getByRole('slider'), { target: { value: '9000' } })
    expect(sliderValue()).toBe(825)
  })

  it('toggles play and pause, disabling play at the recording end', () => {
    render(<PlaybackHarness min={796} max={825} />)
    act(() => screen.getByRole('button', { name: 'Play from current timestep' }).click())
    expect(screen.getByRole('button', { name: 'Pause playback' })).toBeInTheDocument()

    act(() => screen.getByRole('button', { name: 'Pause playback' }).click())
    expect(screen.getByRole('button', { name: 'Play from current timestep' })).toBeInTheDocument()

    // At the end, play is disabled: the recording cannot fabricate more.
    act(() => screen.getByRole('button', { name: 'Jump to end' }).click())
    expect(screen.getByRole('button', { name: 'Play from current timestep' })).toBeDisabled()
  })

  it('disables end-ward controls at the end and start-ward controls at the start', () => {
    render(<PlaybackHarness min={0} max={10} />)
    expect(screen.getByRole('button', { name: 'Jump to start' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Step back one recorded timestep' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Step forward one recorded timestep' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Jump to end' })).toBeEnabled()

    act(() => screen.getByRole('button', { name: 'Jump to end' }).click())
    expect(
      screen.getByRole('button', { name: 'Step forward one recorded timestep' }),
    ).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Jump to end' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Step back one recorded timestep' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Jump to start' })).toBeEnabled()
  })

  it('steps the cursor via the step controls and reports the position', () => {
    render(<PlaybackHarness min={796} max={825} />)
    act(() => screen.getByRole('button', { name: 'Step forward one recorded timestep' }).click())
    expect(sliderValue()).toBe(797)
    act(() => screen.getByRole('button', { name: 'Step back one recorded timestep' }).click())
    expect(sliderValue()).toBe(796)
    expect(screen.getByTestId('playback-status').textContent).toMatch(/Timestep 796 \/ 825/)
  })

  it('pauses the automatic advance when a manual control takes over', () => {
    render(<PlaybackHarness min={796} max={825} />)
    act(() => screen.getByRole('button', { name: 'Play from current timestep' }).click())
    // Advancing playback moves the slider...
    act(() => vi.advanceTimersByTime(ADVANCE_MS))
    expect(sliderValue()).toBe(797)
    // ...but a manual scrub stops the automatic advance.
    fireEvent.change(screen.getByRole('slider'), { target: { value: '800' } })
    act(() => vi.advanceTimersByTime(ADVANCE_MS * 5))
    expect(sliderValue()).toBe(800)
  })

  it('keeps jump buttons driving the cursor directly', () => {
    render(<PlaybackHarness min={796} max={825} />)
    act(() => screen.getByRole('button', { name: 'Jump to end' }).click())
    expect(sliderValue()).toBe(825)
    act(() => screen.getByRole('button', { name: 'Jump to start' }).click())
    expect(sliderValue()).toBe(796)
    expect(screen.getByRole('button', { name: 'Jump to start' })).toBeDisabled()
  })
})
