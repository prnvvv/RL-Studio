import { render, screen, act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StreamOverlay } from './StreamOverlay'
import { StudioStore } from './studioStore'
import { CATALOG, PPO } from './studioFixtures'
import { controlAvailability, draftFromConfig, emptyDraft, toSessionConfig } from './studioConfig'
import { ACTIVE_STATUSES, type SessionConfig } from './studioTypes'

describe('draftFromConfig', () => {
  it('reproduces the running session so the panels highlight what is actually running', () => {
    const running: SessionConfig = {
      agent: 'a2c',
      environment: 'warehouse',
      agent_params: { learning_rate: 0.0007 },
      env_params: { rows: 7 },
      training: { total_timesteps: 5000 },
    }
    const draft = draftFromConfig(CATALOG, running)
    expect(draft.agent).toBe('a2c')
    expect(draft.environment).toBe('warehouse')
    expect(draft.agent_params).toEqual({ learning_rate: 0.0007 })
    // Settings the session did not carry fall back to the catalog defaults, not to nothing.
    expect(draft.training.total_timesteps).toBe(5000)
    expect(Object.keys(draft.training).length).toBe(
      Object.keys(emptyDraft(CATALOG).training).length,
    )
    // And it round-trips into the same session config.
    expect(toSessionConfig(draft)?.agent).toBe('a2c')
  })

  it('does not alias the session config', () => {
    const config: SessionConfig = {
      agent: PPO.key,
      environment: 'cartpole',
      agent_params: { gamma: 0.9 },
      env_params: {},
      training: {},
    }
    const draft = draftFromConfig(CATALOG, config)
    draft.agent_params.gamma = 0.5
    expect(config.agent_params.gamma).toBe(0.9)
  })
})

describe('configuration lock', () => {
  it('releases after Stop: the session is no longer active and Initialize and Reset are offered', () => {
    expect(ACTIVE_STATUSES).not.toContain('stopped')
    const stopped = controlAvailability('stopped', null, true)
    expect(stopped.initialize).toBe(true)
    expect(stopped.reset).toBe(true)
    expect(stopped.train).toBe(false)
    // While it is running the configuration stays locked and Initialize is not offered.
    const running = controlAvailability('running', null, true)
    expect(running.initialize).toBe(false)
    expect(running.stop).toBe(true)
  })

  it('goes from stopping to stopped through lifecycle events', () => {
    const store = new StudioStore()
    store.applySnapshot({ session_id: 'ses_aaaaaaaa', seq: 0, status: 'running' } as never)
    const lifecycle = (seq: number, status: string) => ({
      schema_version: '1.0',
      seq,
      type: 'lifecycle' as const,
      session_id: 'ses_aaaaaaaa',
      timestamp: '',
      payload: { status },
    })
    store.applyEvent(lifecycle(1, 'stopping'))
    expect(ACTIVE_STATUSES).toContain(store.getState().status)
    store.applyEvent(lifecycle(2, 'stopped'))
    expect(ACTIVE_STATUSES).not.toContain(store.getState().status)
  })
})

describe('latency readout', () => {
  it('says "no reply" after repeated unanswered pings instead of a bare dash', async () => {
    const store = new StudioStore()
    render(<StreamOverlay store={store} />)
    expect(screen.getByText('Latency').parentElement).toHaveTextContent('—')
    for (let i = 0; i < 3; i += 1) store.recordPing()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 650))
    })
    expect(screen.getByText('Latency').parentElement).toHaveTextContent('no reply')
    store.recordRtt(12)
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 650))
    })
    expect(screen.getByText('Latency').parentElement).toHaveTextContent('12 ms')
  })
})

describe('backend offline', () => {
  it('disables every command while the stream is down, even for a running session', () => {
    const offline = controlAvailability('running', null, true, true)
    expect(Object.values(offline).every((value) => value === false)).toBe(true)
    // Back online, the same session offers its normal controls again.
    const online = controlAvailability('running', null, true, false)
    expect(online.pause).toBe(true)
    expect(online.stop).toBe(true)
  })
})
