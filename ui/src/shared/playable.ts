/**
 * Curated "playable right now" list — decoupled from the S3 hub
 * registry. A scene can be hosted-playable (the gateway has it via
 * HOSTED_PLAY_SCENES, or it's a downloadable world) WITHOUT being
 * published to SoulHub/WorldHub. The catalog reads S3; this list is
 * what the gateway can actually run, so the UI always has a clickable
 * way into play even for unpublished scenes.
 *
 * Keep in sync with the gateway's HOSTED_PLAY_SCENES + downloadable
 * worlds. This is a stopgap until the registry carries a `playable`
 * flag (a v0.2 protocol bump).
 */
import type { Kind } from './registry'

export type Playable = {
  kind: Kind
  /** Catalog / route slug — matches the S3 registry entry. */
  slug: string
  /**
   * Gateway scene id to actually run. The published bundle slug and the
   * hosted-scene slug can differ (e.g. the `elena` soul bundle is played
   * via the `elena-talk` dialogue scene). Defaults to `slug`.
   */
  sceneSlug?: string
  name: string
  blurb: string
  /**
   * Forced story background — pinned at the top of the logs as
   * Narration the instant the scene loads, so play always starts with
   * the premise set, never on a blank stage. Markdown is supported.
   */
  intro: string
  /** Short action cue shown as the live line under the background. */
  cue: string
}

export const PLAYABLE: Playable[] = [
  {
    kind: 'souls',
    slug: 'elena',
    sceneSlug: 'elena-talk',
    name: 'Elena — Quiet Parlor',
    blurb:
      'A dialogue-only scene. Sit across from Elena and talk — soft-spoken, amnesiac, a pendant she keeps touching.',
    intro:
      '### The Quiet Parlor\n\nA small room, late. One lamp, a low table, two chairs. Rain somewhere far off.\n\n**Elena** sits across from you — soft-spoken, careful, one hand drifting to the pendant at her throat without seeming to notice. She remembers almost nothing from before about a year ago, and does not pretend otherwise. The pendant grows warm at things she cannot explain; she has no answers for it, only the noticing.\n\nThere is nothing to solve here. No map, no quest. Just this room, and a conversation that can go either way.',
    cue: '*She looks up as you settle in, and waits. Say something to her.*',
  },
  {
    kind: 'worlds',
    slug: 'dark-train',
    name: 'Dark Train',
    blurb:
      'A train that never reaches the station. You wake in a carriage with a ticket and no memory of buying it.',
    intro:
      '### The Dark Train\n\nYou wake in a moving carriage. Rain streaks the black windows, and there is no station in the dark beyond them — there has not been one for a long time.\n\nA **ticket** rests in your hand. You do not remember buying it, boarding, or where it says you are going. The seat across from you is empty. The train does not slow.\n\nThis is a world, not a script — it remembers what you do. Where you go, who you wake, what you take: it keeps.',
    cue: '*The carriage sways. What do you do?*',
  },
]

export function playableFor(kind: Kind, slug: string): Playable | undefined {
  return PLAYABLE.find((p) => p.kind === kind && p.slug === slug)
}

// Worlds: compute's _resolve_scene already auto-downloads any
// catalog-published world via `neonrp world download <slug>`, so the
// browser-play button should appear for every world in WorldHub — the
// curated PLAYABLE list above only contributes nice intro/cue copy
// when present (`playableFor` still returns it). For souls, gating
// remains: a soul needs a paired scene to act in, and the generic
// soul-talk wrapper that lifts the gate is shipping on the compute
// side (next-door's task #54).
export function isPlayable(kind: Kind, slug: string): boolean {
  if (!slug) return false
  // All published worlds and souls are playable. Worlds auto-download
  // via `neonrp world download`; souls are injected into the soul-talk
  // template via _materialize_soul_session on the play gateway.
  if (kind === 'worlds' || kind === 'souls') return true
  return false
}
