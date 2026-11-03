import { describe, expect, it } from 'vitest'
import { StudioStore } from './studioStore'
import type { SessionSnapshot, StudioEvent } from './studioTypes'

function snapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    session_id: 'ses_aaaaaaaa',
    run_id: 'ses_aaaaaaaa_r1',
    name: 'PPO on cartpole',
    status: 'initialized',
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
    progress: {
      run_id: 'ses_aaaaaaaa_r1',
      timestep: 0,
      total_timesteps: 1000,
      fraction: 0,
      episodes: 0,
      elapsed_seconds: 0,
      steps_per_second: 0,
      current_reward_avg: null,
      mean_reward: null,
      best_reward: null,
      success_rate: null,
      collisions: 0,
      disturbances: 0,
      last_termination: null,
      env_state: {},
      speed: 1,
    },
    checkpoints: [],
    scene: {},
    episodes: [],
    updates: [],
    evaluations: [],
    seq: 5,
    frame: null,
    logs: [],
    ...overrides,
  }
}

function event(seq: number, type: string, payload: Record<string, unknown>): StudioEvent {
  return {
    schema_version: '1.0',
    seq,
    type,
    session_id: 'ses_aaaaaaaa',
    timestamp: '2026-01-01T00:00:00Z',
    payload,
  }
}

describe('StudioStore', () => {
  it('ignores events at or below the snapshot sequence and other sessions', () => {
    const store = new StudioStore()
    store.applySnapshot(snapshot())
    store.applyEvent(event(5, 'lifecycle', { status: 'running' }))
    expect(store.getState().status).toBe('initialized')
    store.applyEvent({
      ...event(6, 'lifecycle', { status: 'running' }),
      session_id: 'ses_bbbbbbbb',
    })
    expect(store.getState().status).toBe('initialized')
    store.applyEvent(event(6, 'lifecycle', { status: 'running' }))
    expect(store.getState().status).toBe('running')
    expect(store.getState().lastSeq).toBe(6)
  })

  it('drops duplicate and out-of-order events', () => {
    const store = new StudioStore()
    store.applySnapshot(snapshot())
    store.applyEvent(event(7, 'episodes', { episodes: [{ episode: 1 }] }))
    store.applyEvent(event(7, 'episodes', { episodes: [{ episode: 1 }] }))
    store.applyEvent(event(6, 'episodes', { episodes: [{ episode: 0 }] }))
    expect(store.getState().episodes).toHaveLength(1)
  })

  it('appends metrics, logs, and checkpoints from events', () => {
    const store = new StudioStore()
    store.applySnapshot(snapshot())
    store.applyEvent(event(6, 'update', { timestep: 10, update: 1, value_loss: 0.5 }))
    store.applyEvent(
      event(7, 'log', { level: 'WARNING', category: 'FAULT', message: 'm', run_id: 'r', meta: {} }),
    )
    store.applyEvent(event(8, 'checkpoint', { checkpoint_id: 'ckpt_1' }))
    const state = store.getState()
    expect(state.updates[0].value_loss).toBe(0.5)
    expect(state.logs[0]).toMatchObject({ level: 'WARNING', category: 'FAULT' })
    expect(state.checkpoints).toHaveLength(1)
  })

  it('clears run metrics on a backend reset and counts it', () => {
    const store = new StudioStore()
    store.applySnapshot(snapshot({ episodes: [{ episode: 1 } as never] }))
    store.applyEvent(event(6, 'reset', { run_id: 'ses_aaaaaaaa_r2' }))
    expect(store.getState().episodes).toEqual([])
    expect(store.getState().resetCount).toBe(1)
  })

  it('a fresh snapshot after reconnect replaces state including logs', () => {
    const store = new StudioStore()
    store.applySnapshot(snapshot())
    store.applyEvent(
      event(6, 'log', {
        level: 'INFO',
        category: 'TRAINING',
        message: 'old',
        run_id: 'r',
        meta: {},
      }),
    )
    store.applySnapshot(snapshot({ seq: 20, status: 'running', logs: [] }))
    expect(store.getState().logs).toEqual([])
    expect(store.getState().status).toBe('running')
    expect(store.getState().lastSeq).toBe(20)
  })

  it('keeps frames outside React state', () => {
    const store = new StudioStore()
    const before = store.getState()
    store.applyFrame({
      timestep: 1,
      episode: 1,
      episode_step: 1,
      action: 0,
      reward: 1,
      episode_reward: 1,
      collision: false,
      disturbance: false,
      done: false,
      state: { x: 0 },
    })
    expect(store.frame?.timestep).toBe(1)
    expect(store.getState()).toBe(before)
  })
})
