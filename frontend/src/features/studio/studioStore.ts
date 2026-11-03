/**
 * Client-side mirror of one backend training session.
 *
 * The backend is the source of truth: this store only applies the snapshot and
 * ordered events it receives. High-frequency simulation frames are kept out of
 * React state on purpose (`frame` is read by the renderer every animation
 * frame) so a 30 Hz stream does not re-render the workspace.
 */
import type {
  CheckpointRecord,
  CommandResult,
  ControlState,
  EpisodeRecord,
  EvaluationRecord,
  FramePayload,
  LogEntry,
  Progress,
  SessionConfig,
  SessionSnapshot,
  SessionStatus,
  StudioEvent,
  UpdateRecord,
} from './studioTypes'

export type ConnectionState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed'

export const MAX_LOGS = 2000
export const MAX_EPISODES = 5000
export const MAX_UPDATES = 2000

export interface StudioState {
  sessionId: string | null
  runId: string | null
  name: string | null
  status: SessionStatus | null
  pendingCommand: 'pause' | null
  error: string | null
  scene: Record<string, unknown> | null
  config: SessionConfig | null
  progress: Progress | null
  episodes: EpisodeRecord[]
  updates: UpdateRecord[]
  evaluations: EvaluationRecord[]
  checkpoints: CheckpointRecord[]
  logs: LogEntry[]
  lastSeq: number
  connection: ConnectionState
  controls: ControlState
  /** Increments whenever the backend resets the run, so views can clear local view state. */
  resetCount: number
}

export const emptyState: StudioState = {
  sessionId: null,
  runId: null,
  name: null,
  status: null,
  pendingCommand: null,
  error: null,
  scene: null,
  config: null,
  progress: null,
  episodes: [],
  updates: [],
  evaluations: [],
  checkpoints: [],
  logs: [],
  lastSeq: 0,
  connection: 'idle',
  controls: { human: false, human_steps: 0 },
  resetCount: 0,
}

type Listener = () => void

function tail<T>(items: T[], max: number): T[] {
  return items.length > max ? items.slice(items.length - max) : items
}

function toLogEntry(event: StudioEvent): LogEntry {
  const payload = event.payload
  return {
    seq: event.seq,
    timestamp: event.timestamp,
    session_id: event.session_id,
    level: payload.level as LogEntry['level'],
    category: payload.category as LogEntry['category'],
    message: String(payload.message ?? ''),
    run_id: String(payload.run_id ?? ''),
    episode_id: typeof payload.episode_id === 'number' ? payload.episode_id : null,
    meta: (payload.meta as Record<string, unknown>) ?? {},
  }
}

function isStatus(value: unknown): value is SessionStatus {
  return typeof value === 'string'
}

/** Live connection telemetry. Mutable by design: sampled by the overlay, never rendered per message. */
export interface StreamStats {
  /** Simulation frames received since the store was created. */
  frames: number
  /** Last measured WebSocket round-trip time (ms), or null before the first pong. */
  rttMs: number | null
}

export class StudioStore {
  private state: StudioState = emptyState
  private listeners = new Set<Listener>()
  private frameListeners = new Set<Listener>()
  private notifyScheduled = false

  /** Latest simulation frame. Mutable by design; read from the render loop. */
  frame: FramePayload | null = null
  /** Bumped for every frame so cheap consumers can detect change. */
  frameVersion = 0
  readonly stream: StreamStats = { frames: 0, rttMs: null }
  private sender: ((message: unknown) => boolean) | null = null

  getState = (): StudioState => this.state

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  subscribeFrame = (listener: Listener): (() => void) => {
    this.frameListeners.add(listener)
    return () => this.frameListeners.delete(listener)
  }

  private set(next: StudioState): void {
    this.state = next
    if (this.notifyScheduled) return
    this.notifyScheduled = true
    // Coalesce bursts of events into one React update per tick.
    const flush = () => {
      this.notifyScheduled = false
      this.listeners.forEach((listener) => listener())
    }
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(flush)
    else setTimeout(flush, 0)
  }

  clear(): void {
    this.frame = null
    this.frameVersion += 1
    this.frameListeners.forEach((listener) => listener())
    this.set({ ...emptyState })
  }

  setConnection(connection: ConnectionState): void {
    if (this.state.connection !== connection) this.set({ ...this.state, connection })
  }

  applySnapshot(snapshot: SessionSnapshot): void {
    this.frame = snapshot.frame
    this.frameVersion += 1
    this.frameListeners.forEach((listener) => listener())
    this.set({
      ...this.state,
      sessionId: snapshot.session_id,
      runId: snapshot.run_id,
      name: snapshot.name,
      status: snapshot.status,
      pendingCommand: snapshot.pending_command,
      error: snapshot.error,
      scene: snapshot.scene,
      config: snapshot.config,
      progress: snapshot.progress,
      episodes: snapshot.episodes ?? [],
      updates: snapshot.updates ?? [],
      evaluations: snapshot.evaluations ?? [],
      checkpoints: snapshot.checkpoints ?? [],
      logs: (snapshot.logs ?? []).map(toLogEntry),
      lastSeq: snapshot.seq,
      controls: snapshot.controls ?? { human: false, human_steps: 0 },
    })
  }

  /** Called by the connection when its socket opens (and with null when it closes). */
  setSender(sender: ((message: unknown) => boolean) | null): void {
    this.sender = sender
  }

  /** Send a message to the backend over the live stream. False when there is no open socket. */
  send(message: unknown): boolean {
    return this.sender !== null && this.sender(message)
  }

  recordRtt(rttMs: number): void {
    if (Number.isFinite(rttMs) && rttMs >= 0) this.stream.rttMs = rttMs
  }

  applyFrame(frame: FramePayload): void {
    this.stream.frames += 1
    this.frame = frame
    this.frameVersion += 1
    this.frameListeners.forEach((listener) => listener())
  }

  /** Adopt a command acknowledgement; the stream confirms the transition. */
  applyCommandResult(result: CommandResult): void {
    if (result.session_id !== this.state.sessionId) return
    this.set({ ...this.state, status: result.status, pendingCommand: result.pending_command })
  }

  applyEvent(event: StudioEvent): void {
    const state = this.state
    if (event.session_id !== state.sessionId || event.seq <= state.lastSeq) return
    const payload = event.payload
    const base = { ...state, lastSeq: event.seq }

    switch (event.type) {
      case 'lifecycle': {
        const status = payload.status
        if (!isStatus(status)) return this.set(base)
        this.set({
          ...base,
          status,
          pendingCommand: null,
          runId: typeof payload.run_id === 'string' ? payload.run_id : base.runId,
          error: typeof payload.error === 'string' ? payload.error : base.error,
        })
        return
      }
      case 'progress':
        this.set({ ...base, progress: payload as unknown as Progress })
        return
      case 'episodes': {
        const incoming = (payload.episodes as EpisodeRecord[]) ?? []
        this.set({ ...base, episodes: tail([...base.episodes, ...incoming], MAX_EPISODES) })
        return
      }
      case 'update':
        this.set({
          ...base,
          updates: tail([...base.updates, payload as unknown as UpdateRecord], MAX_UPDATES),
        })
        return
      case 'evaluation':
        this.set({
          ...base,
          evaluations: [...base.evaluations, payload as unknown as EvaluationRecord],
        })
        return
      case 'checkpoint':
        this.set({
          ...base,
          checkpoints: [...base.checkpoints, payload as unknown as CheckpointRecord],
        })
        return
      case 'control':
        this.set({
          ...base,
          controls: {
            human: payload.human === true,
            human_steps: typeof payload.human_steps === 'number' ? payload.human_steps : 0,
          },
        })
        return
      case 'speed':
        this.set(
          base.progress && typeof payload.speed === 'number'
            ? { ...base, progress: { ...base.progress, speed: payload.speed } }
            : base,
        )
        return
      case 'reset':
        this.set({
          ...base,
          episodes: [],
          updates: [],
          evaluations: [],
          checkpoints: [],
          error: null,
          controls: { human: false, human_steps: 0 },
          resetCount: base.resetCount + 1,
        })
        return
      case 'log':
        this.set({ ...base, logs: tail([...base.logs, toLogEntry(event)], MAX_LOGS) })
        return
      default:
        this.set(base)
    }
  }
}
