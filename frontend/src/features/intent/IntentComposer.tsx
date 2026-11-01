import { useRef, useState } from 'react'
import type { ExtractedRequirementDraft, IntentExtractionStatus, IntentSubmissionResult, RequirementDecision } from '../../schemas/intent'
import type { IntentSubmissionOutcome } from '../../services/intentRequirements'
import { MOCK_DATA_LABEL, type MockData } from '../../mocks'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { FormField } from '../../components/ui/FormField'
import { TextArea } from '../../components/ui/TextArea'
import { ErrorState } from '../../components/ui/ErrorState'
import { VoiceDictationControl } from './VoiceDictationControl'
import { createWebSpeechTranscriber, type VoiceTranscriber } from './voiceTranscriber'
import { RequirementReviewList } from '../requirements/RequirementReviewList'

interface IntentComposerProps {
  /**
   * Submit the statement for extraction. Returns the service outcome; the
   * composer renders every shape it can produce honestly (accepted /
   * ambiguous / unsupported / error) and never invents drafts.
   */
  onSubmit: (text: string) => Promise<IntentSubmissionOutcome>
  /** Review decision wired by the parent (recorded via the requirements service). */
  onDecide: (draft: ExtractedRequirementDraft, decision: RequirementDecision) => Promise<void>
  transcriber?: VoiceTranscriber
}

const HINT =
  'Supported statements describe goal reward, step penalty, collision penalty, observation fidelity, or episode termination.'

interface ReviewedDraft {
  draft: ExtractedRequirementDraft
  decision: RequirementDecision | null
}

function unwrap(data: IntentSubmissionResult | MockData<IntentSubmissionResult>): IntentSubmissionResult {
  if ('label' in data && 'data' in data) return data.data
  return data
}

/**
 * Natural-language intent composer with optional browser dictation.
 *
 * Dictation inserts recognised text at the cursor of the fully editable
 * input and never triggers submission — submitting intent is always an
 * explicit action on reviewed text (approved voice decision D).
 */
export function IntentComposer({ onSubmit, onDecide, transcriber = createWebSpeechTranscriber() }: IntentComposerProps) {
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [outcome, setOutcome] = useState<IntentSubmissionOutcome | null>(null)
  const [reviewed, setReviewed] = useState<ReviewedDraft[]>([])
  const [extractionStatus, setExtractionStatus] = useState<IntentExtractionStatus | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [errorCopy, setErrorCopy] = useState<string | null>(null)
  const [sampleData, setSampleData] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  async function submit() {
    const statement = text.trim()
    if (!statement) return
    setSubmitting(true)
    try {
      const result = await onSubmit(statement)
      setOutcome(result)
      if (result.state === 'ok') {
        setSampleData('label' in result.data)
        const payload = unwrap(result.data)
        setExtractionStatus(payload.extraction_status)
        setWarnings(payload.warnings)
        setReviewed(payload.requirements.map((draft) => ({ draft, decision: null })))
      } else {
        setSampleData(false)
        setExtractionStatus(null)
        setWarnings([])
        setReviewed([])
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function decide(draft: ExtractedRequirementDraft, decision: RequirementDecision) {
    if (draft.requirement_id === null) {
      // An id-less draft cannot be recorded; say so instead of pretending.
      setErrorCopy('This draft has no recorded id yet, so its decision cannot be submitted.')
      return
    }
    setErrorCopy(null)
    setPendingId(draft.requirement_id)
    try {
      await onDecide(draft, decision)
      setReviewed((current) =>
        current.map((item) =>
          item.draft.requirement_id === draft.requirement_id ? { ...item, decision } : item,
        ),
      )
    } catch {
      // The decision failed; keep every other draft intact and say so.
      setErrorCopy('The review decision could not be recorded. Try again.')
    } finally {
      setPendingId(null)
    }
  }

  function insertAtCursor(inserted: string) {
    if (!inserted) return
    const area = textareaRef.current
    const start = area?.selectionStart ?? text.length
    const end = area?.selectionEnd ?? text.length
    const before = text.slice(0, start)
    const after = text.slice(end)
    const joiner = before && !/\s$/.test(before) ? ' ' : ''
    const next = `${before}${joiner}${inserted}${after}`
    setText(next)
    requestAnimationFrame(() => {
      const caret = before.length + joiner.length + inserted.length
      if (textareaRef.current) {
        textareaRef.current.focus()
        textareaRef.current.setSelectionRange(caret, caret)
      }
    })
  }

  if (outcome && outcome.state === 'error') {
    const retryable = outcome.error.kind !== 'cancelled'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <ErrorState
          title="The intent could not be submitted"
          description={outcome.error.message}
          action={
            retryable ? (
              <button
                type="button"
                onClick={() => {
                  void submit()
                }}
                style={{
                  padding: '6px 14px',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Try again
              </button>
            ) : undefined
          }
        />
        {/* The statement stays editable after a recoverable failure; retry
            resubmits what the developer has in the field now. */}
        <FormField label="Intended behaviour" hint={HINT}>
          {(associatedProps) => (
            <TextArea
              value={text}
              onChange={(event) => setText(event.target.value)}
              {...associatedProps}
            />
          )}
        </FormField>
        <VoiceDictationControl transcriber={transcriber} onFinalTranscript={insertAtCursor} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 320px', minWidth: 0 }}>
          <FormField label="Intended behaviour" hint={HINT} error={errorCopy ?? undefined}>
            {(associatedProps) => (
              <TextArea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="e.g. The goal reward must be 100."
                {...associatedProps}
              />
            )}
          </FormField>
        </div>
        <div style={{ flex: '0 1 auto', minWidth: 0 }}>
          <VoiceDictationControl transcriber={transcriber} onFinalTranscript={insertAtCursor} />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => {
            void submit()
          }}
          disabled={submitting || text.trim() === ''}
          aria-busy={submitting || undefined}
          style={{
            padding: '8px 16px',
            background: 'var(--text-primary)',
            color: 'var(--bg-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            cursor: submitting || text.trim() === '' ? 'not-allowed' : 'pointer',
            opacity: submitting || text.trim() === '' ? 0.6 : 1,
            fontFamily: 'var(--font-sans)',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
          }}
        >
          Submit intent
        </button>
        {sampleData && <StatusBadge label={MOCK_DATA_LABEL} tone="quiet" glyph="dot" />}
      </div>
      {submitting && (
        <span role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          Submitting intent for extraction…
        </span>
      )}

      {extractionStatus && (
        <RequirementReviewList
          extractionStatus={extractionStatus}
          warnings={warnings}
          pendingId={pendingId}
          items={reviewed}
          onDecide={(draft, decision) => {
            void decide(draft, decision)
          }}
        />
      )}
    </div>
  )
}
