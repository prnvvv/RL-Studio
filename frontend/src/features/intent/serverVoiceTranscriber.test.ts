import { describe, expect, it, vi } from 'vitest'
import {
  createServerTranscriber,
  type MediaRecorderLike,
  type ServerTranscriberDeps,
} from './serverVoiceTranscriber'
import type { TranscriberEvent } from './voiceTranscriber'

class FakeRecorder implements MediaRecorderLike {
  state = 'inactive'
  ondataavailable: MediaRecorderLike['ondataavailable'] = null
  onstop: MediaRecorderLike['onstop'] = null
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}

function setup(overrides: Partial<ServerTranscriberDeps> = {}) {
  const recorder = new FakeRecorder()
  const stopTrack = vi.fn()
  const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream
  const deps: ServerTranscriberDeps = {
    getUserMedia: vi.fn(async () => stream),
    createRecorder: () => recorder,
    toWav: vi.fn(async () => new Blob(['wav'], { type: 'audio/wav' })),
    transcribe: vi.fn(async () => ({
      state: 'ok' as const,
      data: { text: 'reward above 200', duration_seconds: 2, model: 'm', provider: 'meta' },
    })),
    ...overrides,
  }
  const transcriber = createServerTranscriber(deps)
  const events: TranscriberEvent[] = []
  transcriber.subscribe((event) => events.push(event))
  return { transcriber, recorder, events, deps, stopTrack }
}

const names = (events: TranscriberEvent[]) =>
  events.map((e) => (e.type === 'state' ? e.state : `transcript:${e.text}`))

const last = (events: TranscriberEvent[]) => events[events.length - 1]

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('createServerTranscriber', () => {
  it('is unsupported without browser recording support and reports it on start', () => {
    const transcriber = createServerTranscriber(null)
    const events: TranscriberEvent[] = []
    transcriber.subscribe((e) => events.push(e))
    transcriber.start()
    expect(transcriber.supported).toBe(false)
    expect(names(events)).toEqual(['unsupported'])
  })

  it('records, transcribes through the backend and emits the final transcript', async () => {
    const { transcriber, events, deps, stopTrack } = setup()
    transcriber.start()
    await flush()
    transcriber.stop()
    await flush()
    expect(names(events)).toEqual([
      'listening',
      'transcribing',
      'transcript:reward above 200',
      'recognised',
    ])
    expect(deps.transcribe).toHaveBeenCalledTimes(1)
    expect(stopTrack).toHaveBeenCalled() // the microphone is released
  })

  it('never invents a transcript when the backend fails, and surfaces its message', async () => {
    const { transcriber, events } = setup({
      transcribe: vi.fn(async () => ({
        state: 'error' as const,
        error: { kind: 'unavailable' as const, message: 'The service is currently unavailable.' },
      })),
    })
    transcriber.start()
    await flush()
    transcriber.stop()
    await flush()
    expect(names(events)).toEqual(['listening', 'transcribing', 'error'])
    expect(last(events)).toMatchObject({ message: 'The service is currently unavailable.' })
    expect(events.some((e) => e.type === 'transcript')).toBe(false)
  })

  it('maps a refused microphone permission to permission_denied', async () => {
    const { transcriber, events } = setup({
      getUserMedia: vi.fn(async () => {
        throw new DOMException('denied', 'NotAllowedError')
      }),
    })
    transcriber.start()
    await flush()
    expect(names(events)).toEqual(['permission_denied'])
  })

  it('reports a missing microphone and a recording the browser cannot encode', async () => {
    const missing = setup({
      getUserMedia: vi.fn(async () => {
        throw new DOMException('none', 'NotFoundError')
      }),
    })
    missing.transcriber.start()
    await flush()
    expect(last(missing.events)).toMatchObject({
      state: 'error',
      message: 'No microphone is available.',
    })

    const broken = setup({
      toWav: vi.fn(async () => {
        throw new Error('decode failed')
      }),
    })
    broken.transcriber.start()
    await flush()
    broken.transcriber.stop()
    await flush()
    expect(last(broken.events)).toMatchObject({ state: 'error' })
    expect(broken.deps.transcribe).not.toHaveBeenCalled()
  })

  it('ignores a second start while busy, then allows another recording', async () => {
    const { transcriber, deps } = setup()
    transcriber.start()
    transcriber.start()
    await flush()
    expect(deps.getUserMedia).toHaveBeenCalledTimes(1)
    transcriber.stop()
    await flush()
    transcriber.start()
    await flush()
    expect(deps.getUserMedia).toHaveBeenCalledTimes(2)
  })

  it('stops the recording by itself at the maximum duration', async () => {
    vi.useFakeTimers()
    try {
      const { transcriber, recorder, events } = setup({ maxRecordingMs: 50 })
      transcriber.start()
      await vi.advanceTimersByTimeAsync(0)
      expect(recorder.state).toBe('recording')
      await vi.advanceTimersByTimeAsync(60)
      expect(recorder.state).toBe('inactive')
      expect(names(events)).toContain('transcribing')
    } finally {
      vi.useRealTimers()
    }
  })
})
