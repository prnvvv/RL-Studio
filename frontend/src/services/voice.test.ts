import { afterEach, describe, expect, it, vi } from 'vitest'
import { transcribeRecording } from './voice'

const wav = new Blob([new Uint8Array([82, 73, 70, 70])], { type: 'audio/wav' })

function stubFetch(response: Response | Error | DOMException) {
  const fn = vi.fn(async () => {
    if (!(response instanceof Response)) throw response
    return response
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe('transcribeRecording', () => {
  it('posts the WAV to the backend as multipart form data and returns the transcript', async () => {
    const fetchFn = stubFetch(
      new Response(
        JSON.stringify({
          text: ' the reward should exceed 200 ',
          duration_seconds: 2.5,
          model: 'muse-voice-transcribe-1.0',
          provider: 'meta',
        }),
        { status: 200 },
      ),
    )
    const result = await transcribeRecording(wav)
    expect(result).toEqual({
      state: 'ok',
      data: {
        text: 'the reward should exceed 200',
        duration_seconds: 2.5,
        model: 'muse-voice-transcribe-1.0',
        provider: 'meta',
      },
    })
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/voice/transcribe')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('audio')).toBeInstanceOf(Blob)
    // the browser never sends or holds a provider credential
    expect(JSON.stringify(init.headers ?? {})).not.toMatch(/authorization|MODEL_API_KEY/i)
  })

  it('surfaces the backend error message for an invalid recording', async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          error: { code: 'AI-009', message: 'no speech was detected in the recording' },
        }),
        { status: 422 },
      ),
    )
    expect(await transcribeRecording(wav)).toMatchObject({
      state: 'error',
      error: {
        kind: 'invalid_request',
        status: 422,
        message: 'no speech was detected in the recording',
      },
    })
  })

  it('falls back to generic copy when the error body is not usable', async () => {
    stubFetch(new Response('not json', { status: 503 }))
    expect(await transcribeRecording(wav)).toMatchObject({
      state: 'error',
      error: { kind: 'unavailable', message: 'The service is currently unavailable.' },
    })
  })

  it('reports an unreachable backend as a network error and never invents a transcript', async () => {
    stubFetch(new TypeError('failed to fetch'))
    expect(await transcribeRecording(wav)).toMatchObject({
      state: 'error',
      error: { kind: 'network' },
    })
  })

  it('treats an empty or malformed success body as unexpected', async () => {
    stubFetch(new Response(JSON.stringify({ text: '  ' }), { status: 200 }))
    expect(await transcribeRecording(wav)).toMatchObject({
      state: 'error',
      error: { kind: 'unexpected' },
    })
  })

  it('reports an aborted request as cancelled', async () => {
    stubFetch(new DOMException('aborted', 'AbortError'))
    expect(await transcribeRecording(wav)).toMatchObject({
      state: 'error',
      error: { kind: 'cancelled' },
    })
  })
})
