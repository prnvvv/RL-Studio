import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Catalog } from '../studio/studioTypes'
import type { ProjectSummary } from '../../schemas/projects'
import { createProjectService } from '../../services/projects'
import type { ProjectService } from '../../services/projects'
import { createStudioService } from '../../services/studio'
import { ACCEPTED_DOCUMENT_EXTENSIONS } from '../../schemas/projects'
import { documentProblem } from './projectFormat'

interface CreateProjectDialogProps {
  onCreated: (project: ProjectSummary) => void
  onCancel: () => void
  service?: ProjectService
  loadCatalog?: () => Promise<Catalog | null>
}

const defaultService = createProjectService()
const studio = createStudioService()

async function defaultCatalog(): Promise<Catalog | null> {
  const result = await studio.getCatalog()
  return result.state === 'ok' ? result.data : null
}

/**
 * Creates a project. Only the name is required: agent, environment and intent can all be added later, and the
 * project exists (with its id) before any intent or document is attached to it.
 */
export function CreateProjectDialog({
  onCreated,
  onCancel,
  service = defaultService,
  loadCatalog = defaultCatalog,
}: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [agent, setAgent] = useState('')
  const [environment, setEnvironment] = useState('')
  const [statement, setStatement] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [created, setCreated] = useState<ProjectSummary | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
    let live = true
    void loadCatalog().then((value) => {
      if (live) setCatalog(value)
    })
    return () => {
      live = false
    }
  }, [loadCatalog])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && !pending) onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel, pending])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    const trimmed = name.trim()
    if (trimmed === '') {
      setError('Enter a project name.')
      return
    }
    if (file) {
      const problem = documentProblem(file)
      if (problem) {
        setError(problem)
        return
      }
    }
    setPending(true)
    setError(null)
    const result = await service.createProject({
      name: trimmed,
      ...(description.trim() ? { description: description.trim() } : {}),
      ...(agent ? { agent: { agent } } : {}),
      ...(environment ? { environment: { environment } } : {}),
      ...(statement.trim() ? { intent: { statement: statement.trim() } } : {}),
    })
    if (result.state === 'error') {
      setPending(false)
      setError(`The project was not created. ${result.error.message}`)
      return
    }
    const project = result.data
    const notes: string[] = []
    const intent = project.intent as { error?: { message?: string } } | undefined
    if (intent?.error) {
      notes.push(
        'The project was created, but the expectation could not be processed yet. You can resubmit it in the project.',
      )
    }
    if (file) {
      const upload = await service.uploadDocument(project.project_id, file)
      if (upload.state === 'error') {
        notes.push(`The document was not uploaded. ${upload.error.message}`)
      } else if (upload.data.document.extraction_status !== 'extracted') {
        notes.push(
          `The document was stored but no text could be read from it: ${upload.data.document.extraction_error ?? 'unknown reason'}.`,
        )
      } else {
        const processed = await service.submitIntent(project.project_id, {
          document_ids: [upload.data.document.document_id],
        })
        if (processed.state === 'error') {
          notes.push(
            'The document was uploaded, but its requirements could not be processed yet. You can retry in the project.',
          )
        }
      }
    }
    setPending(false)
    if (notes.length === 0) {
      onCreated(project)
      return
    }
    setCreated(project)
    setWarnings(notes)
  }

  return (
    <div className="pj-overlay" role="presentation">
      <div className="pj-dialog" role="dialog" aria-modal="true" aria-labelledby="pj-create-title">
        <h2 id="pj-create-title">Create project</h2>
        <p className="pj-dialog__lead">
          Only a name is required. Add the agent, environment and expectations now or later.
        </p>
        {created ? (
          <div className="pj-form">
            {warnings.map((w) => (
              <p key={w} className="pj-error" role="status">
                {w}
              </p>
            ))}
            <div className="pj-dialog__foot">
              <button
                type="button"
                className="pj-btn pj-btn--solid"
                onClick={() => onCreated(created)}
              >
                Open project
              </button>
            </div>
          </div>
        ) : (
          <form className="pj-form" onSubmit={(e) => void submit(e)} noValidate>
            <div className="pj-field">
              <label htmlFor="pj-name">Project name</label>
              <input
                id="pj-name"
                ref={nameRef}
                className="pj-input"
                value={name}
                maxLength={120}
                onChange={(e) => setName(e.target.value)}
                disabled={pending}
                autoComplete="off"
              />
            </div>
            <div className="pj-field">
              <label htmlFor="pj-desc">Description (optional)</label>
              <textarea
                id="pj-desc"
                className="pj-textarea"
                value={description}
                maxLength={2000}
                onChange={(e) => setDescription(e.target.value)}
                disabled={pending}
              />
            </div>
            <div className="pj-row">
              <div className="pj-field">
                <label htmlFor="pj-agent">Agent (optional)</label>
                <select
                  id="pj-agent"
                  className="pj-select"
                  value={agent}
                  onChange={(e) => setAgent(e.target.value)}
                  disabled={pending}
                >
                  <option value="">Configure later</option>
                  {(catalog?.agents ?? []).map((a) => (
                    <option key={a.key} value={a.key}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="pj-field">
                <label htmlFor="pj-env">Environment (optional)</label>
                <select
                  id="pj-env"
                  className="pj-select"
                  value={environment}
                  onChange={(e) => setEnvironment(e.target.value)}
                  disabled={pending}
                >
                  <option value="">Configure later</option>
                  {(catalog?.environments ?? []).map((env) => (
                    <option key={env.key} value={env.key}>
                      {env.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="pj-field">
              <label htmlFor="pj-intent">What should the agent achieve? (optional)</label>
              <textarea
                id="pj-intent"
                className="pj-textarea"
                value={statement}
                maxLength={20000}
                onChange={(e) => setStatement(e.target.value)}
                disabled={pending}
                placeholder="e.g. The final episode reward must be at least 100."
              />
              <span className="pj-hint">
                Interpreted into requirements you review and confirm. Nothing is verified until a
                training run exists.
              </span>
            </div>
            <div className="pj-field">
              <label htmlFor="pj-doc">Requirements document (optional)</label>
              <input
                id="pj-doc"
                className="pj-input"
                type="file"
                accept={ACCEPTED_DOCUMENT_EXTENSIONS.join(',')}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={pending}
              />
              <span className="pj-hint">README, Markdown, TXT, PDF or DOCX, up to 2 MB.</span>
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
              <button type="submit" className="pj-btn pj-btn--solid" disabled={pending}>
                {pending ? 'Creating…' : 'Create project'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
