/**
 * Server-backed dictation: record with the microphone, encode to WAV, and let the backend transcribe it with Meta's
 * hosted Muse Voice Transcribe model (`POST /api/v1/voice/transcribe`).
 *
 * Implements the existing `VoiceTranscriber` boundary, so the dictation UI is unchanged. Honest states only:
 * microphone permission is requested on an explicit `start()`, `transcribing` is reported while the backend works, a
 * failure is surfaced with its message, and nothing is inserted or submitted here (the composer owns that).
 */
import { transcribeRecording } from '../../services/voice'
import type { ServiceResult } from '../../services/types'
import type { VoiceTranscription } from '../../services/voice'
import type { TranscriberEvent, VoiceTranscriber } from './voiceTranscriber'
import { recordingToWav } from './wavEncoder'

/** Backend limit is 10 MB of 16 kHz mono WAV (about five minutes); stop well inside it. */
export const MAX_RECORDING_MS = 240_000

export interface MediaRecorderLike {
  state: string
  ondataavailable: ((event: { data: Blob }) => void) | null
  onstop: (() => void) | null
  start(): void
  stop(): void
}

export interface ServerTranscriberDeps {
  getUserMedia: (constraints: MediaStreamConstraints) => Promise<MediaStream>
  createRecorder: (stream: MediaStream) => MediaRecorderLike
  toWav: (recording: Blob) => Promise<Blob>
  transcribe: (wav: Blob) => Promise<ServiceResult<VoiceTranscription>>
  maxRecordingMs?: number
}

function browserDeps(): ServerTranscriberDeps | null {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return null
  const hasMic = typeof navigator.mediaDevices?.getUserMedia === 'function'
  const hasRecorder = typeof window.MediaRecorder === 'function'
  const hasAudio =
    typeof window.AudioContext === 'function' && typeof window.OfflineAudioContext === 'function'
  if (!hasMic || !hasRecorder || !hasAudio) return null
  return {
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createRecorder: (stream) => new MediaRecorder(stream) as unknown as MediaRecorderLike,
    toWav: recordingToWav,
    transcribe: (wav) => transcribeRecording(wav),
  }
}

export function createServerTranscriber(
  deps: ServerTranscriberDeps | null = browserDeps(),
): VoiceTranscriber {
  type Listener = (event: TranscriberEvent) => void
  const listeners = new Set<Listener>()
  let busy = false
  let recorder: MediaRecorderLike | null = null
  let autoStop: ReturnType<typeof setTimeout> | null = null

  const emit = (event: TranscriberEvent) => {
    for (const listener of listeners) listener(event)
  }
  const fail = (message: string) => emit({ type: 'state', state: 'error', message })

  async function finish(chunks: Blob[], stream: MediaStream, active: ServerTranscriberDeps) {
    for (const track of stream.getTracks()) track.stop()
    try {
      if (chunks.length === 0) {
        fail('No audio was recorded.')
        return
      }
      emit({ type: 'state', state: 'transcribing', message: undefined })
      let wav: Blob
      try {
        wav = await active.toWav(new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' }))
      } catch {
        fail('This browser could not prepare the recording for transcription.')
        return
      }
      const result = await active.transcribe(wav)
      if (result.state === 'ok') {
        emit({ type: 'transcript', text: result.data.text, final: true })
        emit({ type: 'state', state: 'recognised', message: undefined })
      } else {
        fail(result.error.message)
      }
    } finally {
      busy = false
      recorder = null
    }
  }

  return {
    supported: deps !== null,

    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },

    start() {
      if (busy) return
      if (deps === null) {
        emit({ type: 'state', state: 'unsupported', message: undefined })
        return
      }
      const active = deps
      busy = true
      void (async () => {
        let stream: MediaStream
        try {
          stream = await active.getUserMedia({ audio: true })
        } catch (cause) {
          busy = false
          const name = cause instanceof DOMException ? cause.name : ''
          if (name === 'NotAllowedError' || name === 'SecurityError') {
            emit({ type: 'state', state: 'permission_denied', message: undefined })
          } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
            fail('No microphone is available.')
          } else {
            fail('The microphone could not be started.')
          }
          return
        }
        const chunks: Blob[] = []
        const instance = active.createRecorder(stream)
        recorder = instance
        instance.ondataavailable = (event) => {
          if (event.data.size > 0) chunks.push(event.data)
        }
        instance.onstop = () => {
          if (autoStop !== null) clearTimeout(autoStop)
          autoStop = null
          void finish(chunks, stream, active)
        }
        instance.start()
        emit({ type: 'state', state: 'listening', message: undefined })
        autoStop = setTimeout(() => {
          if (instance.state === 'recording') instance.stop()
        }, active.maxRecordingMs ?? MAX_RECORDING_MS)
      })()
    },

    stop() {
      if (recorder && recorder.state === 'recording') recorder.stop()
    },
  }
}
