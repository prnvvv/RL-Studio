/**
 * Warehouse simulation service (@planned contract).
 *
 * Person 2 does not expose recorded environment state yet (episode replay
 * endpoints are documented for coordination in the approved plan). Real mode
 * calls the planned paths below and callers receive honest `not_found` /
 * `unavailable` results until they exist. With `VITE_USE_MOCKS=true`, the
 * demo fixtures from `src/mocks/simulation.ts` are returned wrapped in
 * `MockData` so the viewer carries the shared `Sample data` label; unknown
 * run ids stay honest `not_found` even in mock mode.
 */
import type { SimulationReplay } from '../schemas/simulation'
import type { MockData } from '../mocks/index'
import type { ServiceResult } from './types'
import { api, recordNotFound } from './client'
import { labeledMockData, mocksEnabled } from '../mocks/index'
import { mockSimulationAdapter } from '../mocks/simulation'

type WithMock<T> = T | MockData<T>

/** @planned recorded episode replay for a run. */
export function runSimulationPath(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/simulation`
}

export interface SimulationService {
  getRunSimulation(runId: string): Promise<ServiceResult<WithMock<SimulationReplay>>>
}

/** Real-mode call against the planned endpoint; honest errors until it exists. */
const realAdapter: SimulationService = {
  getRunSimulation(runId) {
    return api.get<SimulationReplay>(runSimulationPath(runId))
  },
}

/** Mock-mode adapter: labeled payloads, unknown ids map to stable not_found. */
const mockedAdapter: SimulationService = {
  async getRunSimulation(runId) {
    const outcome = await mockSimulationAdapter.getRunSimulation(runId)
    return outcome === null ? recordNotFound() : { state: 'ok', data: labeledMockData(outcome) }
  },
}

/** Select the adapter from the mock opt-in flag. */
export function createSimulationService(): SimulationService {
  return mocksEnabled() ? mockedAdapter : realAdapter
}
