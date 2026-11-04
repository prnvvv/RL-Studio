import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { ProjectSummary } from '../../schemas/projects'

interface DeleteProjectDialogProps {
  project: ProjectSummary
  pending: boolean
  error: string | null
  onConfirm: (confirmName: string) => void
  onCancel: () => void
}

/** Deleting needs the exact project name typed back. Data is retained; the project is only hidden. */
export function DeleteProjectDialog({
  project,
  pending,
  error,
  onConfirm,
  onCancel,
}: DeleteProjectDialogProps) {
  const [typed, setTyped] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const matches = typed.trim() === project.name

  useEffect(() => {
    inputRef.current?.focus()
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  function submit(event: FormEvent) {
    event.preventDefault()
    if (matches && !pending) onConfirm(typed.trim())
  }

  return (
    <div className="pj-overlay" role="presentation">
      <div className="pj-dialog" role="dialog" aria-modal="true" aria-labelledby="pj-del-title">
        <h2 id="pj-del-title">Delete project</h2>
        <p className="pj-dialog__lead">
          “{project.name}” will be removed from your project list. Its training runs, evidence,
          verification results, incidents and uploaded documents are kept and are not deleted.
        </p>
        <form className="pj-form" onSubmit={submit}>
          <div className="pj-field">
            <label htmlFor="pj-del-name">Type the project name to confirm</label>
            <input
              id="pj-del-name"
              ref={inputRef}
              className="pj-input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              disabled={pending}
              autoComplete="off"
            />
          </div>
          {error ? (
            <p className="pj-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="pj-dialog__foot">
            <button type="button" className="pj-btn" onClick={onCancel} disabled={pending}>
              Cancel
            </button>
            <button type="submit" className="pj-btn pj-btn--danger" disabled={!matches || pending}>
              {pending ? 'Deleting…' : 'Delete project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
