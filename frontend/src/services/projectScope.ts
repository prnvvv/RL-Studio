/**
 * The project the application is currently operating in, as seen by the HTTP/stream layer.
 *
 * The backend enforces isolation (every run-owned record belongs to exactly one project, or is legacy/unassigned);
 * this module only tells it which project the user has open. It is set by `ActiveProjectProvider` and read by the
 * API client, the WebSocket/stream URL builders and the upload helpers, so no request can forget it.
 */
const HEADER = 'X-Project-ID'
const QUERY = 'project_id'

let scope: string | null = null

export function setProjectScope(projectId: string | null): void {
  scope = projectId
}

export function getProjectScope(): string | null {
  return scope
}

/** Header to merge into a request (empty when no project is open). */
export function projectScopeHeaders(): Record<string, string> {
  return scope === null ? {} : { [HEADER]: scope }
}

/**
 * Browsers cannot set headers on a WebSocket or EventSource, so streams carry the scope as `?project_id=`.
 * Returns the URL unchanged when no project is open.
 */
export function withProjectScope(url: string): string {
  if (scope === null) return url
  const parsed = new URL(url, 'http://placeholder.invalid')
  parsed.searchParams.set(QUERY, scope)
  const isAbsolute = /^[a-z][a-z0-9+.-]*:/i.test(url)
  return isAbsolute ? parsed.toString() : `${parsed.pathname}${parsed.search}${parsed.hash}`
}
