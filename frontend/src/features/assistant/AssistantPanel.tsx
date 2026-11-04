import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import {
  createAssistantService,
  type AssistantService,
  type ChatResponse,
  type ChatTurn,
} from '../../services/assistant'
import type { ServiceError } from '../../services/types'
import '../selfHealing/selfHealing.css'

interface Message extends ChatTurn {
  id: number
  context?: ChatResponse['context']
  note?: string | null
  model?: string
}

const SUGGESTIONS = [
  'What does the PPO clip range do, and when should I change it?',
  'How did my selected run perform, and what does that tell me?',
  'What should I try next to improve a low mean reward?',
]

const MAX_STORED = 40

function storageKey(projectId: string | null): string {
  return `rl-studio.assistant.${projectId ?? 'none'}`
}

function load(projectId: string | null): Message[] {
  try {
    const raw = window.sessionStorage.getItem(storageKey(projectId))
    const parsed = raw === null ? [] : (JSON.parse(raw) as Message[])
    return Array.isArray(parsed) ? parsed.slice(-MAX_STORED) : []
  } catch {
    return [] // a convenience only: the conversation simply starts empty
  }
}

function save(projectId: string | null, messages: Message[]): void {
  try {
    window.sessionStorage.setItem(storageKey(projectId), JSON.stringify(messages.slice(-MAX_STORED)))
  } catch {
    // not persisted; the conversation still works for this view
  }
}

interface AssistantPanelProps {
  projectId: string | null
  /** The run the page is about, when one is selected. Context only: the assistant answers without it. */
  runId: string | null
  /** A real, selected incident. Absent means the general assistant, which never requires one. */
  incidentId: string | null
  service?: AssistantService
}

/**
 * The conversational assistant. It answers with or without an incident: the general assistant explains RL concepts and
 * answers about the selected project and run from persisted records, and says what is not recorded instead of guessing.
 * With an incident chosen, the user can switch to the incident investigator, which answers from that incident's evidence.
 */
export function AssistantPanel({ projectId, runId, incidentId, service }: AssistantPanelProps) {
  const api = useMemo(() => service ?? createAssistantService(), [service])
  const [messages, setMessages] = useState<Message[]>(() => load(projectId))
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ServiceError | null>(null)
  const [investigator, setInvestigator] = useState(false)
  const counter = useRef(messages.reduce((max, m) => Math.max(max, m.id), 0))
  const logRef = useRef<HTMLDivElement>(null)
  const controllerRef = useRef<AbortController | null>(null)

  // A different project has its own conversation; nothing from the previous project stays on screen.
  useEffect(() => {
    setMessages(load(projectId))
    setError(null)
    setInvestigator(false)
  }, [projectId])

  // Leaving the incident leaves investigator mode.
  useEffect(() => {
    if (incidentId === null) setInvestigator(false)
  }, [incidentId])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages, pending])

  useEffect(() => () => controllerRef.current?.abort(), [])

  const asking = investigator && incidentId !== null ? incidentId : null

  const send = useCallback(
    async (text: string) => {
      const message = text.trim()
      if (message === '' || pending) return
      const history: ChatTurn[] = messages.map(({ role, content }) => ({ role, content }))
      const userMessage: Message = { id: ++counter.current, role: 'user', content: message }
      const next = [...messages, userMessage]
      setMessages(next)
      save(projectId, next)
      setDraft('')
      setError(null)
      setPending(true)
      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller
      const result = await api.chat(
        { message, history, run_id: runId, incident_id: asking },
        controller.signal,
      )
      if (controller.signal.aborted) return
      if (result.state === 'ok') {
        const reply: Message = {
          id: ++counter.current,
          role: 'assistant',
          content: result.data.reply,
          context: result.data.context,
          note: result.data.note,
          model: result.data.model,
        }
        const done = [...next, reply]
        setMessages(done)
        save(projectId, done)
      } else {
        setError(result.error)
      }
      setPending(false)
    },
    [api, asking, messages, pending, projectId, runId],
  )

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void send(draft)
    }
  }

  const lastUser = [...messages].reverse().find((m) => m.role === 'user')

  return (
    <div className="as">
      <div className="sh-row" style={{ justifyContent: 'space-between' }}>
        <div className="sh-chips" aria-label="Assistant scope">
          <StatusBadge
            label={asking ? `Incident investigator · ${asking.slice(0, 8)}…` : 'General assistant'}
            tone={asking ? 'strong' : 'neutral'}
            glyph="none"
          />
          <StatusBadge
            label={runId ? `Run ${runId}` : projectId ? 'No run selected' : 'No project open'}
            tone="quiet"
            glyph="none"
          />
        </div>
        <div className="sh-row">
          {incidentId !== null ? (
            <button
              type="button"
              className="sh-btn"
              aria-pressed={investigator}
              onClick={() => setInvestigator((v) => !v)}
            >
              {investigator ? 'Switch to general assistant' : 'Ask about the selected incident'}
            </button>
          ) : null}
          {messages.length > 0 ? (
            <button
              type="button"
              className="sh-btn"
              onClick={() => {
                setMessages([])
                save(projectId, [])
                setError(null)
              }}
            >
              Clear conversation
            </button>
          ) : null}
        </div>
      </div>

      <div className="as-log" ref={logRef} role="log" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 ? (
          <div className="sh-stack">
            <p className="sh-text">
              Ask anything about reinforcement learning, PPO, hyperparameters, metrics, verification,
              evaluation, diagnosis or recovery. No incident is needed.
              {runId
                ? ' Questions about your run use its recorded data.'
                : ' Select a run to ask about your own results.'}
            </p>
            <div className="sh-chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="sh-btn" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`as-msg${m.role === 'user' ? ' as-msg--user' : ''}`}>
              <span className="as-msg__who">{m.role === 'user' ? 'You' : 'Assistant'}</span>
              <p className="as-msg__body">{m.content}</p>
              {m.role === 'assistant' && m.context ? (
                <details className="sh-muted">
                  <summary>What this answer could draw on</summary>
                  <p className="sh-muted">
                    {m.context.sources.length > 0
                      ? `Recorded data: ${m.context.sources.join('; ')}.`
                      : 'No recorded project data was used: this is general knowledge.'}
                  </p>
                  {m.context.not_available.length > 0 ? (
                    <p className="sh-muted">Not available: {m.context.not_available.join('; ')}.</p>
                  ) : null}
                  {m.model ? <p className="sh-muted">Model: {m.model}</p> : null}
                  {m.note ? <p className="sh-muted">{m.note}</p> : null}
                </details>
              ) : null}
            </div>
          ))
        )}
        {pending ? (
          <p role="status" className="sh-muted">
            The assistant is thinking…
          </p>
        ) : null}
      </div>

      {error ? (
        <div role="alert" className="sh-note sh-note--alert">
          <strong>The assistant could not answer.</strong> {error.detail ?? error.message}
          {error.code ? ` (${error.code})` : ''}
          {lastUser ? (
            <>
              {' '}
              <button
                type="button"
                className="sh-btn"
                onClick={() => {
                  // drop the unanswered turn, then ask again
                  setMessages((current) => {
                    const trimmed = current.filter((m) => m.id !== lastUser.id)
                    save(projectId, trimmed)
                    return trimmed
                  })
                  void send(lastUser.content)
                }}
              >
                Try again
              </button>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="as-compose">
        <label className="sh-field" style={{ flex: 1 }}>
          <span>{asking ? 'Ask about this incident' : 'Ask the assistant'}</span>
          <textarea
            className="sh-textarea"
            value={draft}
            rows={2}
            maxLength={4000}
            placeholder="Type a question. Enter sends, Shift+Enter adds a line."
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
          />
        </label>
        <button
          type="button"
          className="sh-btn sh-btn--primary"
          disabled={pending || draft.trim() === ''}
          onClick={() => void send(draft)}
        >
          {pending ? 'Sending…' : 'Send'}
        </button>
      </div>
      <p className="sh-muted">
        Answers are advisory. Verification verdicts come from the deterministic engine, and nothing the
        assistant says is executed.
      </p>
    </div>
  )
}
