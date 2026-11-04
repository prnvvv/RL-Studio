/**
 * Assistant service: `POST /api/v1/assistant/chat` (`backend/api/routers/assistant.py`).
 *
 * The general assistant never needs an incident. Naming an incident switches to the incident investigator, which
 * answers from that incident's persisted evidence. The project comes from the active-project scope header, never
 * from the request body. A provider failure is an error result, never an invented answer.
 */
import type { ServiceResult } from './types'
import { api } from './client'

const SLOW_MS = 120_000

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  message: string
  history: ChatTurn[]
  run_id?: string | null
  incident_id?: string | null
}

export interface ChatResponse {
  reply: string
  mode: 'general' | 'incident'
  task: string
  model: string
  fallback_used: boolean
  note: string | null
  context: {
    project_id: string | null
    run_id: string | null
    incident_id: string | null
    /** What persisted data the answer could draw on. */
    sources: string[]
    /** What the assistant did not have (shown so a gap is never mistaken for an answer). */
    not_available: string[]
  }
}

export interface AssistantService {
  chat(request: ChatRequest, signal?: AbortSignal): Promise<ServiceResult<ChatResponse>>
}

export function createAssistantService(): AssistantService {
  return {
    chat(request, signal) {
      const body: Record<string, unknown> = { message: request.message, history: request.history }
      if (request.run_id) body.run_id = request.run_id
      if (request.incident_id) body.incident_id = request.incident_id
      return api.post<ChatResponse>('/api/v1/assistant/chat', { jsonBody: body, signal, timeoutMs: SLOW_MS })
    },
  }
}
