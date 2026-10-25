/**
 * Run-history view model.
 *
 * These are *display* fields derived from the documented Reports columns
 * (`frontend/AGENTS.md` §8.6), not a backend schema. Every value is already
 * formatted for display, and `null` means the backend did not supply it, so a
 * missing number can never be mistaken for a measured zero.
 *
 * The canonical run-record response shape is unconfirmed (TODO T-1402), so no
 * mapping from a backend payload is implemented here.
 */
export interface RunSummary {
  id: string
  environment: string | null
  steps: string | null
  successRate: string | null
  /** Rendered exactly as the backend reports it; never inferred from a metric. */
  status: string | null
  date: string | null
}

/** Fields a text filter is allowed to match against. */
function searchableText(run: RunSummary): string {
  return [run.id, run.environment, run.steps, run.successRate, run.status, run.date]
    .filter((value): value is string => value !== null)
    .join(' ')
    .toLowerCase()
}

/**
 * Case-insensitive substring filter over the loaded page of runs.
 *
 * This runs in the browser over an already-loaded bounded page. It is not a
 * substitute for a backend query: callers must not present it as server-side
 * search, and pagination/ordering remain the backend's responsibility.
 */
export function filterRuns(runs: RunSummary[], query: string): RunSummary[] {
  const needle = query.trim().toLowerCase()
  if (needle === '') return runs
  return runs.filter((run) => searchableText(run).includes(needle))
}
