import { describe, expect, it, vi } from 'vitest'
import {
  createWebSpeechTranscriber,
  detectSpeechRecognitionCtor,
  type SpeechRecognitionCtor,
  type SpeechRecognitionLike,
  type SpeechRecognitionResultLike,
} from './voiceTranscriber'

/**
 * Scripted fake of the engine surface used by the state mapping. The test
 * controls the handlers the adapter assigns, emulating the real callbacks.
 */
class FakeSpeechRecognition implements SpeechRecognitionLike {
  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 1

  start: () => void = () => {}
  stop: () => void = () => {}

  onresult: SpeechRecognitionLike['onresult'] = null
  onerror: SpeechRecognitionLike['onerror'] = null
  onend: SpeechRecognitionLike['onend'] = null
}

function resultLike(text: string, isFinal: boolean): SpeechRecognitionResultLike {
  return { isFinal, 0: { transcript: text, confidence: isFinal ? 0.9 : 0.5 } }
}

function makeCtor(): { ctor: SpeechRecognitionCtor; instances: FakeSpeechRecognition[] } {
  const instances: FakeSpeechRecognition[] = []
  const ctor = class extends FakeSpeechRecognition {
    constructor() {
      super()
      instances.push(this)
    }
  }
  return { ctor: ctor as unknown as SpeechRecognitionCtor, instances }
}

describe('detectSpeechRecognitionCtor', () => {
  it('prefers the standard engine and falls back to the webkit-prefixed one', () => {
    const standard = makeCtor()
    const webkit = makeCtor()
    vi.stubGlobal('SpeechRecognition', standard.ctor)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    try {
      expect(detectSpeechRecognitionCtor()).toBe(standard.ctor)
      vi.stubGlobal('SpeechRecognition', undefined)
      vi.stubGlobal('webkitSpeechRecognition', webkit.ctor)
      expect(detectSpeechRecognitionCtor()).toBe(webkit.ctor)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('returns null when neither engine exists', () => {
    vi.stubGlobal('SpeechRecognition', undefined)
    vi.stubGlobal('webkitSpeechRecognition', undefined)
    try {
      expect(detectSpeechRecognitionCtor()).toBeNull()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('createWebSpeechTranscriber — unsupported engine', () => {
  it('reports unsupported and ignores start instead of failing', () => {
    const events: string[] = []
    const transcriber = createWebSpeechTranscriber(null)
    transcriber.subscribe((event) => {
      if (event.type === 'state') events.push(event.state)
    })

    expect(transcriber.supported).toBe(false)
    // Nothing is emitted merely from subscribing: the control reads
    // `supported` directly for the initial render.
    expect(events).toEqual([])

    transcriber.start()
    expect(events).toEqual(['unsupported'])
  })
})

describe('createWebSpeechTranscriber — supported engine', () => {
  it('emits listening on start and idle on clean end', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const states: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state') states.push(event.state)
    })

    transcriber.start()
    expect(states).toEqual(['listening'])
    expect(instances).toHaveLength(1)
    expect(instances[0].interimResults).toBe(true)

    instances[0].onend?.()
    expect(states).toEqual(['listening', 'idle'])
  })

  it('emits interim transcripts without settling, then finalises with recognised', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const events: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'transcript') events.push(`${event.final}:${event.text}`)
      if (event.type === 'state') events.push(`state:${event.state}`)
    })

    transcriber.start()
    instances[0].onresult?.({
      resultIndex: 0,
      results: [resultLike('goal reward', false)],
    })

    expect(events).toEqual(['state:listening', 'false:goal reward'])

    instances[0].onresult?.({
      resultIndex: 0,
      results: [resultLike('goal reward must equal 100.', true)],
    })
    expect(events).toEqual([
      'state:listening',
      'false:goal reward',
      'true:goal reward must equal 100.',
      'state:recognised',
    ])
  })

  it('maps a denied microphone to permission_denied and holds it through onend', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const states: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state') states.push(event.state)
    })

    transcriber.start()
    instances[0].onerror?.({ error: 'not-allowed' })
    instances[0].onend?.()

    expect(states).toEqual(['listening', 'permission_denied'])
  })

  it('maps service denial like the browser permission path', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const states: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state') states.push(event.state)
    })

    transcriber.start()
    instances[0].onerror?.({ error: 'service-not-allowed' })
    expect(states).toEqual(['listening', 'permission_denied'])
  })

  it('maps unknown and known engine errors to error with safe messages', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const received: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state' && event.state === 'error') received.push(event.message)
    })

    transcriber.start()
    instances[0].onerror?.({ error: 'no-speech' })
    instances[0].onerror?.({ error: 'network' })
    instances[0].onerror?.({ error: 'totally-unknown-kind' })

    expect(received).toEqual([
      'No speech was detected.',
      'Speech recognition is unavailable offline or the service could not be reached.',
      'Dictation failed.',
    ])
  })

  it('allows a fresh start after a settled session', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    const states: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state') states.push(event.state)
    })

    transcriber.start()
    instances[0].onresult?.({ resultIndex: 0, results: [resultLike('done', true)] })
    instances[0].onend?.()

    transcriber.start()
    expect(states).toEqual(['listening', 'recognised', 'listening'])
    expect(instances).toHaveLength(2)
  })

  it('ignores a second start while a session is active', () => {
    const { ctor, instances } = makeCtor()
    const transcriber = createWebSpeechTranscriber(ctor)
    transcriber.start()
    transcriber.start()
    expect(instances).toHaveLength(1)
  })

  it('stop requests engine stop; the end handler settles to idle', () => {
    const { ctor, instances } = makeCtor()
    let stopRequested = false
    const transcriber = createWebSpeechTranscriber(ctor)
    const states: string[] = []
    transcriber.subscribe((event) => {
      if (event.type === 'state') states.push(event.state)
    })

    transcriber.start()
    instances[0].stop = () => {
      stopRequested = true
      instances[0].onend?.()
    }
    transcriber.stop()
    expect(stopRequested).toBe(true)
    expect(states).toEqual(['listening', 'idle'])
  })
})
