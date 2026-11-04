/**
 * WAV encoding for Meta Muse Voice Transcribe, which accepts only mono 16-bit PCM WAV at 16 kHz or 24 kHz.
 *
 * Pure encoding (no model, no network). `recordingToWav` decodes whatever the browser's MediaRecorder produced and
 * resamples it to 16 kHz mono through the Web Audio API.
 */

export const TARGET_SAMPLE_RATE = 16_000

/** Encode mono float samples (-1..1) as a 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2
  const dataLength = samples.length * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + dataLength, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true) // PCM fmt chunk size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * bytesPerSample, true) // byte rate
  view.setUint16(32, bytesPerSample, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeText(36, 'data')
  view.setUint32(40, dataLength, true)
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i] ?? 0))
    view.setInt16(44 + i * bytesPerSample, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

/** Decode a recorded blob and resample it to mono 16 kHz WAV. Rejects when the browser cannot decode it. */
export async function recordingToWav(recording: Blob): Promise<Blob> {
  const AudioContextCtor = window.AudioContext
  const OfflineCtor = window.OfflineAudioContext
  if (typeof AudioContextCtor !== 'function' || typeof OfflineCtor !== 'function') {
    throw new Error('Web Audio is unavailable')
  }
  const context = new AudioContextCtor()
  try {
    const decoded = await context.decodeAudioData(await recording.arrayBuffer())
    const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_SAMPLE_RATE))
    const offline = new OfflineCtor(1, frames, TARGET_SAMPLE_RATE)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination) // channel down-mix to mono happens in the 1-channel destination
    source.start()
    const rendered = await offline.startRendering()
    return encodeWav(rendered.getChannelData(0), TARGET_SAMPLE_RATE)
  } finally {
    void context.close()
  }
}
