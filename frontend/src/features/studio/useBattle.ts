import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { sessionStreamUrl, type SessionCommand, type StudioService } from '../../services/studio'
import type { ServiceError } from '../../services/types'
import { combineState } from './battle'
import { connectSession } from './studioConnection'
import { StudioStore } from './studioStore'
import type { BattleRequest, BattleSideResult, BattleSnapshot } from './studioTypes'

export interface BattleNotice {
  tone: 'info' | 'warning' | 'error'
  message: string
}

function describe(action: string, error: ServiceError): string {
  if (error.kind === 'timeout' || error.kind === 'network') {
    return `${action} did not complete and its outcome is unknown. ${error.message}`
  }
  return `${action} failed. ${error.message}`
}

function isCommandOutcome(
  result: BattleSideResult,
): result is Extract<BattleSideResult, { session_id: string }> {
  return 'session_id' in result
}

/**
 * Owns a battle: two backend sessions (same environment, same seed) with one
 * live stream and one store each. Lifecycle commands go to the battle
 * endpoints so both sides are driven together; statuses come from the streams.
 */
export function useBattle(service: StudioService) {
  const storeA = useMemo(() => new StudioStore(), [])
  const storeB = useMemo(() => new StudioStore(), [])
  const stateA = useSyncExternalStore(storeA.subscribe, storeA.getState)
  const stateB = useSyncExternalStore(storeB.subscribe, storeB.getState)
  const [battleId, setBattleId] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<BattleNotice | null>(null)
  const busyRef = useRef<string | null>(null)
  const disposers = useRef<Array<() => void>>([])

  const disconnect = useCallback(() => {
    disposers.current.forEach((dispose) => dispose())
    disposers.current = []
  }, [])

  const adopt = useCallback(
    (snapshot: BattleSnapshot) => {
      disconnect()
      storeA.clear()
      storeB.clear()
      storeA.applySnapshot(snapshot.a)
      storeB.applySnapshot(snapshot.b)
      disposers.current = [
        connectSession(storeA, { url: (after) => sessionStreamUrl(snapshot.a.session_id, after) }),
        connectSession(storeB, { url: (after) => sessionStreamUrl(snapshot.b.session_id, after) }),
      ]
      setBattleId(snapshot.battle_id)
    },
    [disconnect, storeA, storeB],
  )

  useEffect(() => disconnect, [disconnect])

  const create = useCallback(
    async (request: BattleRequest): Promise<boolean> => {
      if (busyRef.current !== null) return false
      busyRef.current = 'initialize'
      setBusy('initialize')
      setNotice(null)
      const result = await service.createBattle(request)
      busyRef.current = null
      setBusy(null)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describe('Creating the battle', result.error) })
        return false
      }
      adopt(result.data)
      return true
    },
    [adopt, service],
  )

  const applyResults = useCallback(
    (a: BattleSideResult, b: BattleSideResult, command: string) => {
      const problems: string[] = []
      for (const [side, store, result] of [
        ['A', storeA, a],
        ['B', storeB, b],
      ] as const) {
        if (isCommandOutcome(result)) store.applyCommandResult(result)
        else problems.push(`Side ${side} could not ${command}: ${result.error}`)
      }
      if (problems.length > 0) setNotice({ tone: 'warning', message: problems.join(' ') })
    },
    [storeA, storeB],
  )

  const command = useCallback(
    async (name: SessionCommand): Promise<boolean> => {
      if (battleId === null || busyRef.current !== null) return false
      busyRef.current = name
      setBusy(name)
      setNotice(null)
      const result = await service.battleCommand(battleId, name)
      busyRef.current = null
      setBusy(null)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describe(`The ${name} request`, result.error) })
        return false
      }
      applyResults(result.data.a, result.data.b, name)
      return true
    },
    [applyResults, battleId, service],
  )

  const setSpeed = useCallback(
    async (speed: number) => {
      if (battleId === null) return
      const result = await service.setBattleSpeed(battleId, speed)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describe('Changing speed', result.error) })
      }
    },
    [battleId, service],
  )

  /** Leave Compare mode: close both streams and forget the battle (the backend keeps its records). */
  const leave = useCallback(() => {
    disconnect()
    storeA.clear()
    storeB.clear()
    setBattleId(null)
    setNotice(null)
  }, [disconnect, storeA, storeB])

  const combined = useMemo(
    () =>
      battleId === null
        ? stateA
        : combineState(stateA, stateB, stateA.name?.replace(/^A · /, '') ?? null),
    [battleId, stateA, stateB],
  )

  return {
    battleId,
    storeA,
    storeB,
    stateA,
    stateB,
    combined,
    busy,
    notice,
    create,
    adopt,
    command,
    setSpeed,
    leave,
  }
}
