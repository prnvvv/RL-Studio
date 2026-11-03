import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StudioService } from '../../services/studio'
import { useBattle } from './useBattle'
import type { BattleSnapshot, SessionSnapshot } from './studioTypes'

// The hook opens a live stream per side; these tests are about orchestration, not sockets.
vi.mock('./studioConnection', () => ({ connectSession: vi.fn(() => vi.fn()) }))

const side = (id: string, which: 'a' | 'b', agent: string): SessionSnapshot =>
  ({
    session_id: id,
    run_id: `${id}_r1`,
    name: `${which.toUpperCase()} · ${agent} on cartpole`,
    status: 'initialized',
    pending_command: null,
    agent,
    environment: 'cartpole',
    battle: { battle_id: 'bat_11111111', side: which },
    config: {
      agent,
      environment: 'cartpole',
      agent_params: {},
      env_params: {},
      training: { seed: 7 },
    },
    created_at: '',
    started_at: null,
    finished_at: null,
    error: null,
    progress: {
      run_id: 'r',
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
    seq: 0,
    frame: null,
  }) as SessionSnapshot

const snapshot: BattleSnapshot = {
  battle_id: 'bat_11111111',
  a: side('ses_aaaaaaaa', 'a', 'PPO'),
  b: side('ses_bbbbbbbb', 'b', 'DQN'),
  comparison: {
    metrics: {} as never,
    leader: null,
    leader_basis: 'current_reward_avg',
    same_environment: true,
    same_seed: true,
  },
}

const request = {
  environment: 'cartpole',
  env_params: {},
  training: { seed: 7 },
  a: { agent: 'PPO', agent_params: {} },
  b: { agent: 'DQN', agent_params: {} },
}

function service(overrides: Partial<StudioService> = {}): StudioService {
  return {
    createBattle: vi.fn().mockResolvedValue({ state: 'ok', data: snapshot }),
    battleCommand: vi.fn().mockResolvedValue({
      state: 'ok',
      data: {
        battle_id: 'bat_11111111',
        a: {
          session_id: 'ses_aaaaaaaa',
          status: 'running',
          pending_command: null,
          idempotent: false,
        },
        b: {
          session_id: 'ses_bbbbbbbb',
          status: 'running',
          pending_command: null,
          idempotent: false,
        },
      },
    }),
    setBattleSpeed: vi.fn().mockResolvedValue({ state: 'ok', data: {} }),
    ...overrides,
  } as unknown as StudioService
}

afterEach(() => vi.clearAllMocks())

describe('useBattle', () => {
  it('creates a battle and loads both sides into their own stores', async () => {
    const svc = service()
    const { result } = renderHook(() => useBattle(svc))
    let ok = false
    await act(async () => {
      ok = await result.current.create(request)
    })
    expect(ok).toBe(true)
    expect(svc.createBattle).toHaveBeenCalledWith(request)
    await waitFor(() => expect(result.current.battleId).toBe('bat_11111111'))
    expect(result.current.stateA.sessionId).toBe('ses_aaaaaaaa')
    expect(result.current.stateB.sessionId).toBe('ses_bbbbbbbb')
    expect(result.current.combined.name).toBe('PPO on cartpole')
  })

  it('reports a failed creation without adopting anything', async () => {
    const svc = service({
      createBattle: vi
        .fn()
        .mockResolvedValue({ state: 'error', error: { kind: 'invalid_request', message: 'bad' } }),
    })
    const { result } = renderHook(() => useBattle(svc))
    await act(async () => {
      expect(await result.current.create(request)).toBe(false)
    })
    expect(result.current.battleId).toBeNull()
    expect(result.current.notice).toMatchObject({ tone: 'error' })
  })

  it('applies battle commands to both sides and ignores a double click', async () => {
    const svc = service()
    const { result } = renderHook(() => useBattle(svc))
    await act(async () => {
      await result.current.create(request)
    })
    await act(async () => {
      await Promise.all([result.current.command('start'), result.current.command('start')])
    })
    expect(svc.battleCommand).toHaveBeenCalledTimes(1)
    expect(result.current.stateA.status).toBe('running')
    expect(result.current.stateB.status).toBe('running')
  })

  it('surfaces a side that could not comply instead of hiding it', async () => {
    const svc = service({
      battleCommand: vi.fn().mockResolvedValue({
        state: 'ok',
        data: {
          battle_id: 'bat_11111111',
          a: {
            session_id: 'ses_aaaaaaaa',
            status: 'paused',
            pending_command: null,
            idempotent: false,
          },
          b: { error: 'Cannot pause a session that is completed', status: 'completed' },
        },
      }),
    })
    const { result } = renderHook(() => useBattle(svc))
    await act(async () => {
      await result.current.create(request)
    })
    await act(async () => {
      await result.current.command('pause')
    })
    expect(result.current.notice).toMatchObject({ tone: 'warning' })
    expect(result.current.notice?.message).toContain('Side B could not pause')
  })

  it('forgets the battle when leaving Compare mode', async () => {
    const svc = service()
    const { result } = renderHook(() => useBattle(svc))
    await act(async () => {
      await result.current.create(request)
    })
    act(() => result.current.leave())
    expect(result.current.battleId).toBeNull()
    expect(result.current.stateA.sessionId).toBeNull()
  })
})
