/**
 * Minimal journey analytics (Hub-7). PostHog HTTP capture, no SDK.
 *
 * Principles:
 *  - Track the journey, not the person. NO content is ever sent —
 *    only structural facts (which kind/slug, which field, ok/fail).
 *  - No-op until VITE_POSTHOG_KEY is set, so dev/local stays silent.
 *  - Respects Do-Not-Track and a localStorage kill-switch.
 *  - Anonymous, stable, random distinct id. No email/handle in props.
 *  - Fire-and-forget; analytics must never block or break the UI.
 *
 * Swappable by design: only this module knows the transport. Self-host
 * vs. cloud is a host env var, not a code change.
 */

const KEY = import.meta.env.VITE_POSTHOG_KEY as string | undefined
const HOST =
  (import.meta.env.VITE_POSTHOG_HOST as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? 'https://us.i.posthog.com'

// Stamped on every event so PostHog dashboards/funnels can filter
// dev noise out of prod data. VITE_ENV overrides; otherwise Vite's
// PROD flag picks: production build → prod, dev server → dev.
const ENV =
  (import.meta.env.VITE_ENV as string | undefined) ??
  (import.meta.env.PROD ? 'prod' : 'dev')

const OPT_OUT_KEY = 'rp-hub:analytics-off'
const AID_KEY = 'rp-hub:aid'

function dnt(): boolean {
  try {
    return (
      navigator.doNotTrack === '1' ||
      (window as { doNotTrack?: string }).doNotTrack === '1'
    )
  } catch {
    return false
  }
}

function optedOut(): boolean {
  try {
    return localStorage.getItem(OPT_OUT_KEY) === '1'
  } catch {
    return false
  }
}

function enabled(): boolean {
  return !!KEY && !dnt() && !optedOut()
}

function distinctId(): string {
  try {
    let id = localStorage.getItem(AID_KEY)
    if (!id) {
      id =
        'a_' +
        (crypto?.randomUUID?.() ??
          Math.random().toString(36).slice(2) + Date.now().toString(36))
      localStorage.setItem(AID_KEY, id)
    }
    return id
  } catch {
    return 'a_anon'
  }
}

export type JourneyEvent =
  | 'play_entered'
  | 'play_session_started'
  | 'play_turn'
  | 'play_turn_3' // VN funnel: reached the 3rd turn = "hooked" signal
  | 'play_overload_retry'
  | 'play_left'
  // VN-LAUNCH funnel (wired when the VN ending flow lands; see AUTO-TODO):
  | 'play_ending_reached' // reached a story ending = completion-rate core
  | 'play_continue_or_replay' // chose to continue / replay another
  | 'play_share_clicked'
  | 'create_opened'
  | 'create_kind_chosen'
  | 'create_step_answered'
  | 'create_ready'
  | 'create_save_blocked'
  | 'create_published'
  | 'signup_started'
  | 'signup_verified'
  | 'signup_already_signed_in'
  | 'password_login'
  | 'registration_completed'
  | 'pricing_upgrade_clicked'

/** Fire-and-forget. Props must be structural only — never user text. */
export function track(
  event: JourneyEvent,
  props: Record<string, string | number | boolean> = {},
): void {
  if (!enabled()) return
  try {
    void fetch(`${HOST}/i/v0/e/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      keepalive: true,
      body: JSON.stringify({
        api_key: KEY,
        event,
        distinct_id: distinctId(),
        properties: { ...props, env: ENV, $lib: 'rp-hub' },
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {})
  } catch {
    /* analytics never throws into the UI */
  }
}

/**
 * Bridge anonymous → identified. Called after a successful verify(),
 * with the user's hub-issued handle (NEVER email — handle is the
 * platform's safe internal identifier).
 *
 * Sends PostHog's $identify with $anon_distinct_id so the prior
 * anonymous events become retroactively attributable to this handle,
 * and pins the local distinct_id for future events.
 */
export function identify(handle: string): void {
  if (!enabled()) return
  if (!handle) return
  const anon = distinctId()
  try {
    localStorage.setItem(AID_KEY, handle)
  } catch {
    /* storage off — events will keep using the prior anon id this session */
  }
  try {
    void fetch(`${HOST}/i/v0/e/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      keepalive: true,
      body: JSON.stringify({
        api_key: KEY,
        event: '$identify',
        distinct_id: handle,
        properties: {
          $anon_distinct_id: anon,
          $set: { handle, env: ENV },
          env: ENV,
          $lib: 'rp-hub',
        },
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {})
  } catch {
    /* never throw */
  }
}

/**
 * Reverse of identify(). Called on sign-out so subsequent events don't
 * pile up under the previous handle.
 */
export function resetIdentity(): void {
  try {
    localStorage.removeItem(AID_KEY)
  } catch {
    /* ignore */
  }
}

export function analyticsOptOut(): void {
  try {
    localStorage.setItem(OPT_OUT_KEY, '1')
  } catch {
    /* ignore */
  }
}

export function analyticsOptIn(): void {
  try {
    localStorage.removeItem(OPT_OUT_KEY)
  } catch {
    /* ignore */
  }
}
