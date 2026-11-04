import type { ProjectStage, ProjectSummary, TrainingState } from '../../schemas/projects'
import { ACCEPTED_DOCUMENT_EXTENSIONS, MAX_DOCUMENT_BYTES } from '../../schemas/projects'

export const TRAINING_LABEL: Record<TrainingState, string> = {
  not_started: 'Training not started',
  active: 'Training active',
  completed: 'Training completed',
}

export function formatWhen(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? 'Unknown'
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** The agent/environment keys a project was configured with, or `null` when it is still unconfigured. */
export function configLabel(project: ProjectSummary, key: 'agent' | 'environment'): string | null {
  const value = (key === 'agent' ? project.agent : project.environment)[key]
  return typeof value === 'string' && value !== '' ? value : null
}

/** Client-side mirror of the backend's document checks, so an obvious mistake fails before upload. */
export function documentProblem(file: File): string | null {
  const lower = file.name.toLowerCase()
  if (!ACCEPTED_DOCUMENT_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `Unsupported file type. Use ${ACCEPTED_DOCUMENT_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_DOCUMENT_BYTES) return 'The file is larger than 2 MB.'
  return null
}

export const STAGE_LABEL: Record<ProjectStage, string> = {
  pre_training: 'Before training',
  during_training: 'During training',
  post_training: 'After training',
  project_level: 'Project level',
}
