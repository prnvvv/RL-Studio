import type { EpisodeRecord } from './studioTypes'

/** The highest-reward episode in the list (the earliest one on a tie), or null when empty. */
export function findBestEpisode(episodes: EpisodeRecord[]): EpisodeRecord | null {
  let best: EpisodeRecord | null = null
  for (const episode of episodes) {
    if (best === null || episode.reward > best.reward) best = episode
  }
  return best
}
