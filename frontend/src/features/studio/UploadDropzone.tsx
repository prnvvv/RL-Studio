import { UploadCloudIcon } from './libraryVisuals'
import { useRef, useState, type DragEvent } from 'react'
import type { UploadPhase } from '../../services/studio'

export type UploadOutcome = { ok: true; message: string } | { ok: false; message: string }

export interface UploadHooks {
  onPhase: (phase: UploadPhase) => void
  onProgress: (fraction: number) => void
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading'; name: string; progress: number }
  | { kind: 'validating'; name: string }
  | { kind: 'ready'; name: string; message: string }
  | { kind: 'error'; name: string; message: string }

interface Props {
  /** Drop-zone headline, e.g. "Drag & drop a custom model". */
  label: string
  /** Accepted extensions including the dot, lower-case. */
  accept: string[]
  hint: string
  maxBytes?: number
  /** Disables the zone (for example while a session is running). */
  disabled?: boolean
  /** Sends the file to the backend. Phases are reported through `hooks`. */
  upload: (file: File, hooks: UploadHooks) => Promise<UploadOutcome>
  /** Optional format example shown under a disclosure. */
  example?: { summary: string; text: string }
}

const STEPS: Array<[string, string]> = [
  ['uploading', 'Uploading'],
  ['validating', 'Validating'],
  ['done', 'Ready'],
]

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot < 0 ? '' : name.slice(dot).toLowerCase()
}

/**
 * Drag-and-drop plus file-browser upload card. The state shown is the real
 * request state: bytes sent, then the backend inspecting the file, then the
 * backend's verdict. Nothing here decides whether a file is valid beyond cheap
 * extension and size pre-checks; the backend is authoritative.
 */
export function UploadDropzone({
  label,
  accept,
  hint,
  maxBytes,
  disabled = false,
  upload,
  example,
}: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const busyRef = useRef(false)
  const busy = phase.kind === 'uploading' || phase.kind === 'validating'
  const blocked = disabled || busy

  async function handleFile(file: File) {
    if (busyRef.current || disabled) return
    const ext = extensionOf(file.name)
    if (!accept.includes(ext)) {
      setPhase({
        kind: 'error',
        name: file.name,
        message: `Unsupported file type${ext ? ` ${ext}` : ''}. Accepted: ${accept.join(', ')}.`,
      })
      return
    }
    if (maxBytes !== undefined && file.size > maxBytes) {
      setPhase({
        kind: 'error',
        name: file.name,
        message: `File is larger than the ${Math.round(maxBytes / 1024 / 1024)} MB limit.`,
      })
      return
    }
    busyRef.current = true
    setPhase({ kind: 'uploading', name: file.name, progress: 0 })
    try {
      const outcome = await upload(file, {
        onPhase: (next) =>
          setPhase((current) => {
            if (next === 'validating') return { kind: 'validating', name: file.name }
            return current.kind === 'uploading'
              ? current
              : { kind: 'uploading', name: file.name, progress: 0 }
          }),
        onProgress: (fraction) =>
          setPhase((current) =>
            current.kind === 'uploading'
              ? { ...current, progress: Math.min(1, Math.max(0, fraction)) }
              : current,
          ),
      })
      setPhase(
        outcome.ok
          ? { kind: 'ready', name: file.name, message: outcome.message }
          : { kind: 'error', name: file.name, message: outcome.message },
      )
    } catch {
      setPhase({ kind: 'error', name: file.name, message: 'The upload failed unexpectedly.' })
    } finally {
      busyRef.current = false
    }
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file && !blocked) void handleFile(file)
  }

  const activeStep =
    phase.kind === 'uploading'
      ? 'uploading'
      : phase.kind === 'validating'
        ? 'validating'
        : phase.kind === 'ready'
          ? 'done'
          : null

  return (
    <div
      className="dropzone"
      data-dragging={dragging || undefined}
      data-disabled={disabled || undefined}
      onDragOver={(event) => {
        event.preventDefault()
        if (!blocked) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <button
        type="button"
        className="dropzone__target"
        disabled={blocked}
        aria-describedby={`${label.replace(/\W+/g, '-')}-hint`}
        onClick={() => inputRef.current?.click()}
      >
        <span className="dropzone__icon" aria-hidden="true">
          <UploadCloudIcon />
        </span>
        <span className="dropzone__title">{label}</span>
        <span id={`${label.replace(/\W+/g, '-')}-hint`} className="dropzone__hint">
          {hint}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        hidden
        accept={accept.join(',')}
        aria-label={label}
        data-testid="upload-input"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) void handleFile(file)
        }}
      />
      <div className="dropzone__actions">
        <button
          type="button"
          className="btn btn--ghost"
          disabled={blocked}
          onClick={() => inputRef.current?.click()}
        >
          {busy && <span className="spinner" aria-hidden="true" />}
          {busy ? 'Working…' : 'Upload'}
        </button>
      </div>

      {phase.kind !== 'idle' && (
        <>
          {activeStep !== null && (
            <div className="dropzone__steps" aria-hidden="true">
              {STEPS.map(([key, text]) => (
                <span key={key} data-active={key === activeStep}>
                  {text}
                </span>
              ))}
            </div>
          )}
          {phase.kind === 'uploading' && (
            <div
              className="dropzone__bar"
              role="progressbar"
              aria-label="Upload progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(phase.progress * 100)}
            >
              <div style={{ width: `${phase.progress * 100}%` }} />
            </div>
          )}
          <div
            className="dropzone__status"
            data-phase={phase.kind}
            role={phase.kind === 'error' ? 'alert' : 'status'}
          >
            {busy && <span className="spinner" aria-hidden="true" />}
            <span>
              {phase.kind === 'uploading' && `Uploading ${phase.name}…`}
              {phase.kind === 'validating' && `Validating ${phase.name} on the backend…`}
              {phase.kind === 'ready' && `Ready — ${phase.message}`}
              {phase.kind === 'error' && `Error — ${phase.message}`}
            </span>
          </div>
        </>
      )}

      {example && (
        <details>
          <summary
            style={{ cursor: 'pointer', marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)' }}
          >
            {example.summary}
          </summary>
          <pre className="dropzone__example">{example.text}</pre>
        </details>
      )}
    </div>
  )
}
