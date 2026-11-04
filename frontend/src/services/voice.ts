/**
 * Voice service: uploads a WAV recording to the backend, which forwards it to Meta's hosted Muse Voice Transcribe
 * model. The browser never sees `MODEL_API_KEY` and never talks to Meta directly.
 *
 * Binds `POST /api/v1/voice/transcribe` (`backend/api/routers/voice.py`). Resolves a `ServiceResult`; no transcript is
 * ever invented when the backend is unreachable or the model is unavailable.
 */
import { buildRequestUrl, kindForStatus, MESSAGES } from './client'
import { projectScopeHeaders } from './projectScope'
import type { ServiceResult } from './types'
import { serviceError } from './types'

const TRANSCRIBE_PATH = '/api/v1/voice/transcribe'
const TRANSCRIBE_TIMEOUT_MS = 90_000
const MAX_BACKEND_MESSAGE_CHARS = 200

export interface VoiceTranscription {
  text: string
  duration_seconds: number | null
  model: string
  provider: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** The backend's voice errors are sanitised and actionable ("no speech was detected"); show them when present. */
async function backendMessage(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (isRecord(body) && isRecord(body.error) && typeof body.error.message === 'string') {
      const message = body.error.message.trim()
      if (message && message.length <= MAX_BACKEND_MESSAGE_CHARS) return message
    }
  } catch {
    // fall through to the generic message
  }
  return null
}

export async function transcribeRecording(
  wav: Blob,
  signal?: AbortSignal,
): Promise<ServiceResult<VoiceTranscription>> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TRANSCRIBE_TIMEOUT_MS)
  const onAbort = () => controller.abort()
  signal?.addEventListener('abort', onAbort)
  try {
    const form = new FormData()
    form.append('audio', wav, 'recording.wav')
    const response = await fetch(
      buildRequestUrl(
        (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, ''),
        TRANSCRIBE_PATH,
      ),
      {
        method: 'POST',
        headers: { Accept: 'application/json', ...projectScopeHeaders() },
        body: form,
        signal: controller.signal,
      },
    )
    if (!response.ok) {
      const kind = kindForStatus(response.status)
      const detail = await backendMessage(response)
      return {
        state: 'error',
        error: { kind, message: detail ?? MESSAGES[kind], status: response.status },
      }
    }
    const data: unknown = await response.json()
    if (!isRecord(data) || typeof data.text !== 'string' || data.text.trim() === '') {
      return serviceError('unexpected', MESSAGES.unexpected)
    }
    return {
      state: 'ok',
      data: {
        text: data.text.trim(),
        duration_seconds: typeof data.duration_seconds === 'number' ? data.duration_seconds : null,
        model: typeof data.model === 'string' ? data.model : '',
        provider: typeof data.provider === 'string' ? data.provider : '',
      },
    }
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      return serviceError('cancelled', MESSAGES.cancelled)
    }
    return serviceError('network', MESSAGES.network)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}
