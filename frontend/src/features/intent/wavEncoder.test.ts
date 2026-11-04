import { describe, expect, it } from 'vitest'
import { encodeWav, TARGET_SAMPLE_RATE } from './wavEncoder'

async function viewOf(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer())
}

describe('encodeWav', () => {
  it('writes a mono 16-bit PCM WAV header at the requested rate', async () => {
    const view = await viewOf(
      encodeWav(new Float32Array([0, 0.5, -0.5, 1, -1]), TARGET_SAMPLE_RATE),
    )
    const text = (offset: number, length: number) =>
      String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)))
    expect(text(0, 4)).toBe('RIFF')
    expect(text(8, 4)).toBe('WAVE')
    expect(text(12, 4)).toBe('fmt ')
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(16_000)
    expect(view.getUint16(34, true)).toBe(16) // bits per sample
    expect(text(36, 4)).toBe('data')
    expect(view.getUint32(40, true)).toBe(10) // 5 samples x 2 bytes
    expect(view.byteLength).toBe(44 + 10)
    expect(view.getUint32(4, true)).toBe(view.byteLength - 8)
  })

  it('scales and clamps samples into 16-bit range', async () => {
    const view = await viewOf(encodeWav(new Float32Array([0, 1, -1, 2, -2]), 16_000))
    const sample = (i: number) => view.getInt16(44 + i * 2, true)
    expect([sample(0), sample(1), sample(2)]).toEqual([0, 32767, -32768])
    expect([sample(3), sample(4)]).toEqual([32767, -32768]) // out-of-range input is clamped, never wrapped
  })

  it('labels the blob as audio/wav', () => {
    expect(encodeWav(new Float32Array(1), 16_000).type).toBe('audio/wav')
  })
})
