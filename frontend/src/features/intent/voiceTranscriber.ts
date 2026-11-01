/**
 * Voice transcription boundary and the browser-native implementation.
 *
 * `VoiceTranscriber` is a replaceable boundary (approved decision): today it
 * is the browser-native Web Speech API; a future server-side transcriber can
 * be swapped in behind the same interface without touching UI code.
 *
 * States are feature-detected and honest (`frontend/AGENTS.md` §16.2):
 * `unsupported` is reported when no Speech Recognition engine exists, and
 * permission is requested only on explicit user initiation (start()).
 * Nothing here submits or consumes the recognised text — transcription only.
 */

export type VoiceDictationState =
  'unsupported' | 'permission_denied' | 'idle' | 'listening' | 'recognised' | 'error'

export type TranscriberEvent =
  | { type: 'state'; state: Exclude<VoiceDictationState, 'error'>; message?: undefined }
  | { type: 'state'; state: 'error'; message: string }
  | { type: 'transcript'; text: string; final: boolean }

export interface VoiceTranscriber {
  /** Whether the browser exposes any Speech Recognition engine at all. */
  readonly supported: boolean
  /** Request microphone access and begin listening. */
  start(): void
  /** Stop listening. A transition to `idle` follows unless already settled. */
  stop(): void
  /** Register a listener; returns its unsubscribe function. */
  subscribe(listener: (event: TranscriberEvent) => void): () => void
}

/** Minimal structural type for the browser SpeechRecognition surface. */
export interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  onresult:
    ((event: { resultIndex: number; results: SpeechRecognitionResultLike[] }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
}

export interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string; confidence: number }
}

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike

/** Feature-detect the browser engines without assuming their names. */
export function detectSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const ctor = (window as unknown as Record<string, unknown>).SpeechRecognition
  const webkit = (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  if (typeof ctor === 'function') return ctor as SpeechRecognitionCtor
  if (typeof webkit === 'function') return webkit as SpeechRecognitionCtor
  return null
}

/** Non-sensitive, user-safe message per engine error kind. */
const ENGINE_ERROR_MESSAGES: Record<string, string> = {
  'no-speech': 'No speech was detected.',
  network: 'Speech recognition is unavailable offline or the service could not be reached.',
  'audio-capture': 'No microphone is available.',
  aborted: 'Dictation was interrupted.',
  'language-not-supported': 'The selected language is not supported for dictation.',
}

/** Map an engine error onto the honest dictation state. */
function stateForEngineError(kind: string): { state: VoiceDictationState; message: string } {
  if (kind === 'not-allowed' || kind === 'service-not-allowed') {
    return {
      state: 'permission_denied',
      message: 'Microphone permission was denied. Enable it in the browser to dictate.',
    }
  }
  return { state: 'error', message: ENGINE_ERROR_MESSAGES[kind] ?? 'Dictation failed.' }
}

export function createWebSpeechTranscriber(
  ctor: SpeechRecognitionCtor | null = detectSpeechRecognitionCtor(),
): VoiceTranscriber {
  type Listener = (event: TranscriberEvent) => void
  const listeners = new Set<Listener>()
  let recognition: SpeechRecognitionLike | null = null
  // Tracks the last emitted error state so engine `onend` fires do not clobber
  // a settled `permission_denied` / `error` state back to `idle`.
  let settled = false

  function emit(event: TranscriberEvent) {
    for (const listener of listeners) listener(event)
  }

  function emitState(state: Exclude<VoiceDictationState, 'error'>) {
    emit({ type: 'state', state, message: undefined })
  }

  return {
    supported: ctor !== null,

    subscribe(listener: Listener): () => void {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },

    start(): void {
      if (recognition || settled) return
      if (ctor === null) {
        emit({ type: 'state', state: 'unsupported', message: undefined })
        return
      }
      const instance = new ctor()
      instance.lang = document.documentElement.lang || 'en-US'
      instance.continuous = false
      instance.interimResults = true
      instance.maxAlternatives = 1
      instance.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i]
          const text = result[0].transcript
          if (result.isFinal) {
            emit({ type: 'transcript', text, final: true })
            settled = true
            emitState('recognised')
          } else {
            emit({ type: 'transcript', text, final: false })
          }
        }
      }
      instance.onerror = (event) => {
        // Errors settle the session; the engine's own `onend` must not
        // overwrite their terminal state back to `idle`.
        settled = true
        const mapped = stateForEngineError(event.error)
        if (mapped.state === 'permission_denied') {
          emit({ type: 'state', state: 'permission_denied', message: undefined })
        } else {
          emit({ type: 'state', state: 'error', message: mapped.message })
        }
      }
      instance.onend = () => {
        const wasSettled = settled
        recognition = null
        settled = false
        // The engine fires `onend` after errors and after results alike; only
        // resurface `idle` when nothing conclusive happened first.
        if (!wasSettled) emitState('idle')
      }
      recognition = instance
      emitState('listening')
      instance.start()
    },

    stop(): void {
      recognition?.stop()
    },
  }
}
