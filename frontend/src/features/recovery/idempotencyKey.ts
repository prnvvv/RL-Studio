/**
 * Idempotency-key generation for consequential POST requests.
 *
 * One key per intent: a submit flow that may be retried after a timeout must
 * reuse the same key so the backend cannot create a second record for the
 * repeated intent (root AGENTS.md §8, frontend/AGENTS.md §15.3).
 */
export function createIdempotencyKey(): string {
  const cryptoRef = globalThis.crypto as Crypto | undefined
  if (typeof cryptoRef?.randomUUID === 'function') {
    return cryptoRef.randomUUID()
  }
  // Fallback for environments without crypto.randomUUID (e.g. some jsdom
  // configurations); uniqueness within a session is what matters here.
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
