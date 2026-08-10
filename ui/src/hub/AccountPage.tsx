/**
 * AccountPage — what the user owns + the sessions they hold.
 *
 * Four sections, each lazily fetched, each independently error-tolerant:
 *   - drafts (in-progress create studios — clickable to resume)
 *   - published (their wid/sid in the public WorldHub/SoulHub)
 *   - plays (which worlds/souls they've actually played — populated by
 *     compute via /me/play-touch; empty until compute deploys the hook)
 *   - sessions (every bearer issued for this account — revoke or
 *     "sign out everywhere" against a leaked token)
 *
 * Auth-gated route: redirects to /signup when no session.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Loader2, LogOut, Play, FileText, Globe, Sparkles,
  ShieldCheck, Trash2, Pencil, Upload, Check, Crown, ArrowRight,
  Copy, Terminal, Plus, Eye, EyeOff,
} from 'lucide-react'
import { useAuth } from '../shared/auth'
import { useI18n } from '../shared/i18n'
import {
  me, listSessions, revokeSession, revokeOtherSessions,
  unpublish, setVisibility, uploadBundle, stripePortal,
  listApiTokens, createApiToken, revokeApiToken,
  type UploadResult,
  type Me, type SessionEntry, type ApiToken, type ApiTokenCreated,
} from '../shared/identity'
import { listSaves, deleteSave, type PlaySave } from '../play/playClient'

function relTime(t?: number | null): string {
  if (!t) return ''
  const dt = Date.now() / 1000 - t
  if (dt < 60) return 'just now'
  if (dt < 3600) return `${Math.floor(dt / 60)}m ago`
  if (dt < 86400) return `${Math.floor(dt / 3600)}h ago`
  return `${Math.floor(dt / 86400)}d ago`
}

export function AccountPage() {
  const { t } = useI18n()
  const { signedIn, handle, signOut } = useAuth()
  const navigate = useNavigate()

  const [data, setData] = useState<Me | null>(null)
  const [sessions, setSessions] = useState<SessionEntry[] | null>(null)
  const [saves, setSaves] = useState<PlaySave[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Upload form state — kept inside AccountPage (not a child component)
  // so a successful upload can directly trigger a refetch of `data`
  // and the new entry appears in the Published list below without
  // any extra plumbing.
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadKind, setUploadKind] = useState<'world' | 'soul'>('world')
  const [uploadSlug, setUploadSlug] = useState('')
  const [uploadName, setUploadName] = useState('')
  const [uploadUnlisted, setUploadUnlisted] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [uploadErr, setUploadErr] = useState<string | null>(null)
  const [apiTokens, setApiTokens] = useState<ApiToken[] | null>(null)
  const [newToken, setNewToken] = useState<ApiTokenCreated | null>(null)
  const [tokenLabel, setTokenLabel] = useState('')
  const [tokenBusy, setTokenBusy] = useState(false)
  const [tokenErr, setTokenErr] = useState<string | null>(null)
  const [tokenCopied, setTokenCopied] = useState(false)

  useEffect(() => {
    if (!signedIn) {
      navigate('/signup')
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        // Three independent fetches — saves comes from compute (it
        // owns the .neonrp/sessions files); the other two come from
        // identity. Tolerate any single failure so the page still
        // renders the parts that did load.
        const [m, s, sv, at] = await Promise.all([
          me(),
          listSessions().catch(() => []),
          listSaves().catch(() => []),
          listApiTokens().catch(() => []),
        ])
        if (cancelled) return
        setData(m)
        setSessions(s)
        setSaves(sv)
        setApiTokens(at)
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [signedIn, navigate])

  async function doUpload() {
    if (!uploadFile || uploadBusy) return
    setUploadBusy(true)
    setUploadErr(null)
    setUploadResult(null)
    try {
      const r = await uploadBundle(uploadKind, uploadFile, {
        slug: uploadSlug.trim() || undefined,
        name: uploadName.trim() || undefined,
        unlisted: uploadUnlisted,
      })
      setUploadResult(r)
      // Reset form fields but keep the kind toggle (likely uploading
      // multiple of the same kind in a row).
      setUploadFile(null)
      setUploadSlug('')
      setUploadName('')
      // Refresh /me so the published list shows the new entry.
      try {
        const m = await me()
        setData(m)
      } catch {
        /* non-fatal */
      }
    } catch (e) {
      setUploadErr(e instanceof Error ? e.message : String(e))
    } finally {
      setUploadBusy(false)
    }
  }

  async function doUnpublish(p: { id: string; kind: string; name: string }) {
    if (busy) return
    if (
      !confirm(
        t('account.unpublishConfirm').replace('{name}', p.name || p.id),
      )
    )
      return
    setBusy(true)
    try {
      await unpublish(p.kind, p.id)
      // Refresh the /me payload so the published list re-renders
      // without the removed entry. listSessions stays valid.
      const m = await me()
      setData(m)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function doRevoke(id: string) {
    if (busy) return
    setBusy(true)
    try {
      await revokeSession(id)
      const fresh = await listSessions()
      setSessions(fresh)
    } finally {
      setBusy(false)
    }
  }

  async function doSetVisibility(
    p: { id: string; kind: string },
    unlisted: boolean,
  ) {
    if (busy) return
    setBusy(true)
    try {
      await setVisibility(p.kind, p.id, unlisted)
      const m = await me()
      setData(m)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function doDeleteSave(sid: string) {
    if (busy) return
    setBusy(true)
    try {
      await deleteSave(sid)
      setSaves((prev) => (prev ?? []).filter((s) => s.session_id !== sid))
    } catch {
      /* best-effort */
    } finally {
      setBusy(false)
    }
  }

  async function doRevokeOthers() {
    if (busy) return
    if (!confirm(t('account.revokeOthersConfirm'))) return
    setBusy(true)
    try {
      await revokeOtherSessions()
      const fresh = await listSessions()
      setSessions(fresh)
    } finally {
      setBusy(false)
    }
  }

  async function doCreateToken() {
    if (tokenBusy) return
    setTokenBusy(true)
    setTokenErr(null)
    setNewToken(null)
    try {
      const t = await createApiToken(tokenLabel.trim() || 'CLI')
      setNewToken(t)
      setTokenLabel('')
      // Refresh the list
      const fresh = await listApiTokens()
      setApiTokens(fresh)
    } catch (e) {
      setTokenErr(e instanceof Error ? e.message : String(e))
    } finally {
      setTokenBusy(false)
    }
  }

  async function doRevokeToken(tid: string) {
    if (tokenBusy) return
    if (!confirm(t('account.apiTokenRevokeConfirm'))) return
    setTokenBusy(true)
    try {
      await revokeApiToken(tid)
      const fresh = await listApiTokens()
      setApiTokens(fresh)
    } catch (e) {
      setTokenErr(e instanceof Error ? e.message : String(e))
    } finally {
      setTokenBusy(false)
    }
  }

  if (!signedIn) return null

  return (
    <section className="w-full max-w-[1100px] px-5 md:px-12 py-12 flex flex-col gap-10">
      <header className="flex flex-col gap-2">
        <span
          className="font-mono text-[11px] tracking-[0.18em]"
          style={{ color: 'var(--color-accent-dim)' }}
        >
          {t('account.tag')}
        </span>
        <h1
          className="text-[var(--color-text-primary)]"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(28px, 4vw, 42px)',
            lineHeight: 1.1,
          }}
        >
          {handle}
        </h1>
        {data?.uid && (
          <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
            uid · {data.uid}
          </span>
        )}
      </header>

      {/* ── Tier badge ──────────────────────────────────────── */}
      <div
        className="rounded-lg border p-4 flex items-center justify-between gap-4"
        style={{
          borderColor: 'var(--color-border-light)',
          background: 'var(--color-bg-card)',
        }}
      >
        <div className="flex items-center gap-3">
          <Crown
            className="w-5 h-5"
            style={{
              color:
                data?.tier === 'paid'
                  ? 'var(--color-accent)'
                  : 'var(--color-text-tertiary)',
            }}
          />
          <div>
            <div
              className="text-[14px] font-medium"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {data?.tier === 'paid' ? 'Supporter' : 'Free'}
            </div>
            <div
              className="text-[11px]"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {data?.tier === 'paid'
                ? data?.sub_cancel_at_period_end
                  ? t('account.subEnding').replace(
                      '{date}',
                      data.sub_period_end
                        ? new Date(data.sub_period_end * 1000).toLocaleDateString()
                        : '',
                    )
                  : 'Unlimited plays — thank you!'
                : (data?.daily_cap ?? 0) >= 100000
                  ? t('account.betaUnlimited')
                  : `${data?.plays_today ?? '?'} / ${data?.daily_cap ?? 10} plays today`}
            </div>
          </div>
        </div>
        {data?.tier === 'paid' ? (
          <button
            onClick={async () => {
              try {
                const { url } = await stripePortal()
                window.location.href = url
              } catch {
                /* ignore */
              }
            }}
            className="hover-btn inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium"
            style={{
              border: '1px solid var(--color-border-light)',
              color: 'var(--color-text-secondary)',
            }}
          >
            Manage
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        ) : (
          <button
            onClick={() => navigate('/pricing')}
            className="hover-btn inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium"
            style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
          >
            Upgrade
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* ── Complete account / password (shown until registered) ── */}
      <AccountSetup
        data={data}
        onDone={async () => {
          try {
            setData(await me())
          } catch {
            /* ignore */
          }
        }}
      />

      {/* ── API Tokens ──────────────────────────────────────── */}
      <Section
        title={t('account.apiTokens')}
        sub={t('account.apiTokensSub')}
        empty={false}
        emptyText=""
      >
        <div
          className="rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4 flex flex-col gap-3"
        >
          {/* Create new token */}
          <div className="flex items-center gap-2">
            <Terminal
              className="w-4 h-4 shrink-0"
              style={{ color: 'var(--color-text-muted)' }}
            />
            <input
              value={tokenLabel}
              onChange={(e) => setTokenLabel(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && doCreateToken()}
              disabled={tokenBusy}
              placeholder={t('account.apiTokenLabel')}
              className="flex-1 px-3 py-2 rounded border bg-transparent text-[12px] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] disabled:opacity-50"
              style={{
                borderColor: 'var(--color-border-light)',
                fontFamily: 'var(--font-mono)',
              }}
            />
            <button
              onClick={doCreateToken}
              disabled={tokenBusy}
              className="hover-btn inline-flex items-center gap-1.5 px-3 py-2 rounded text-[12px] font-medium disabled:opacity-40 shrink-0"
              style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
            >
              {tokenBusy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Plus className="w-3.5 h-3.5" />
              )}
              {t('account.apiTokenCreate')}
            </button>
          </div>

          {/* Newly created token — shown once */}
          {newToken && (
            <div
              className="rounded border p-3 flex flex-col gap-2"
              style={{
                borderColor: 'var(--color-accent-dim)',
                background: 'var(--color-bg-page)',
              }}
            >
              <span
                className="text-[11px] font-medium"
                style={{ color: 'var(--color-accent)' }}
              >
                {t('account.apiTokenNew')}
              </span>
              <div className="flex items-center gap-2">
                <code
                  className="flex-1 px-3 py-2 rounded text-[12px] break-all select-all"
                  style={{
                    background: 'var(--color-bg-card-inner)',
                    border: '1px solid var(--color-border-light)',
                    color: 'var(--color-text-primary)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {newToken.token}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(newToken.token)
                    setTokenCopied(true)
                    setTimeout(() => setTokenCopied(false), 2000)
                  }}
                  className="hover-btn shrink-0 p-2 rounded border border-[var(--color-border-light)]"
                >
                  {tokenCopied ? (
                    <Check className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
                  ) : (
                    <Copy className="w-4 h-4" style={{ color: 'var(--color-text-secondary)' }} />
                  )}
                </button>
              </div>
              <p
                className="font-mono text-[10px]"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('account.apiTokenUsage')}
              </p>
            </div>
          )}

          {tokenErr && (
            <span
              className="text-[12px]"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {tokenErr}
            </span>
          )}

          {/* Existing tokens */}
          {(apiTokens?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-1.5 pt-1 border-t border-[var(--color-border-light)]">
              {(apiTokens ?? []).map((tok) => (
                <div
                  key={tok.tid}
                  className="flex items-center gap-3 py-1.5"
                >
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="text-[13px] text-[var(--color-text-primary)] truncate">
                      {tok.label || tok.prefix}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--color-text-muted)] truncate">
                      {tok.prefix}... · {tok.last_used ? relTime(tok.last_used) : t('account.apiTokenNeverUsed')}
                    </span>
                  </div>
                  <button
                    onClick={() => doRevokeToken(tok.tid)}
                    disabled={tokenBusy}
                    className="hover-link text-[12px] inline-flex items-center gap-1 disabled:opacity-50 shrink-0"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    <Trash2 className="w-3.5 h-3.5" /> {t('account.apiTokenRevoke')}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>

      {err && (
        <div
          className="rounded-md border px-4 py-3 text-[13px]"
          style={{
            borderColor: 'var(--color-border-light)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text-tertiary)',
          }}
        >
          {err}
        </div>
      )}

      {/* ── Plays / Saves ─────────────────────────────────────── */}
      {/* Source of truth: compute.worldlines.gg/api/v1/play/saves —
          it owns the .neonrp/sessions files. `in_memory` indicates the
          ConversationSession is still warm; cold entries will cold-start
          (or use POST /play/resume once compute ships it). */}
      <Section
        title={t('account.plays')}
        sub={t('account.playsSub')}
        empty={!saves?.length}
        emptyText={t('account.playsEmpty')}
      >
        <div className="flex flex-col gap-4">
          {Object.entries(
            (saves ?? []).reduce(
              (acc, p) => {
                const k = `${p.kind}/${p.slug}`
                ;(acc[k] ||= []).push(p)
                return acc
              },
              {} as Record<string, PlaySave[]>,
            ),
          ).map(([k, group]) => {
            const first = group[0]
            const isSoulG = first.kind === 'souls'
            const accent = isSoulG ? 'var(--color-soul)' : 'var(--color-world)'
            const Icon = isSoulG ? Sparkles : Globe
            return (
              <div key={k} className="flex flex-col gap-1.5">
                {/* World header — click to its play entry screen. */}
                <Link
                  to={`/play/${first.kind}/${first.slug}`}
                  className="hover-link inline-flex items-center gap-2 self-start"
                  style={{ textDecoration: 'none' }}
                >
                  <Icon className="w-4 h-4 shrink-0" style={{ color: accent }} />
                  <span
                    className="text-[14px] text-[var(--color-text-primary)]"
                    style={{ fontFamily: 'var(--font-display)' }}
                  >
                    {first.name || first.slug}
                  </span>
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                    {group.length} {t('account.savesWord')}
                  </span>
                </Link>
                {/* Each save — continue (entry screen) or delete. */}
                {group.map((p) => (
                  <div
                    key={p.session_id}
                    className="flex items-center gap-2 rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] px-3 py-2 ml-6"
                  >
                    <Link
                      to={`/play/${p.kind}/${p.slug}`}
                      className="hover-link inline-flex items-center gap-2 flex-1 min-w-0"
                      style={{
                        textDecoration: 'none',
                        color: 'var(--color-text-secondary)',
                      }}
                    >
                      <Play
                        className="w-3.5 h-3.5 fill-current shrink-0"
                        style={{ color: accent }}
                      />
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)] truncate">
                        {relTime(p.last_modified)}
                        {p.in_memory ? (
                          <span
                            className="ml-2"
                            style={{ color: 'var(--color-accent)' }}
                          >
                            · {t('account.warm')}
                          </span>
                        ) : null}
                      </span>
                    </Link>
                    <button
                      onClick={() => doDeleteSave(p.session_id)}
                      disabled={busy}
                      title={t('play.deleteSave')}
                      className="hover-link p-1 disabled:opacity-50"
                      style={{ color: 'var(--color-text-tertiary)' }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </Section>

      {/* ── Drafts ────────────────────────────────────────────── */}
      <Section
        title={t('account.drafts')}
        sub={t('account.draftsSub')}
        empty={!data?.drafts?.length}
        emptyText={t('account.draftsEmpty')}
      >
        <div className="flex flex-col gap-2">
          {(data?.drafts ?? []).map((d) => (
            <Link
              key={d.draft_id}
              to={`/create/${d.kind}?draft=${encodeURIComponent(d.draft_id)}`}
              className="hover-card flex items-center gap-3 rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-3"
              style={{ textDecoration: 'none' }}
            >
              <FileText
                className="w-4 h-4"
                style={{ color: 'var(--color-accent)' }}
              />
              <span className="flex-1 text-[14px] text-[var(--color-text-primary)] truncate">
                {d.name}
              </span>
              <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                {d.kind} · {relTime(d.updated)}
              </span>
            </Link>
          ))}
        </div>
      </Section>

      {/* ── Upload from library ────────────────────────────────
          Any registered user can drop a zip directly into WorldHub /
          SoulHub here — no AWS creds, no CLI. The server validates
          the manifest, mints a unique slug, hashes the zip, pushes
          to S3, and writes the published row. */}
      <Section
        title={t('account.upload')}
        sub={t('account.uploadSub')}
        empty={false}
        emptyText=""
      >
        <div
          className="rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-4 flex flex-col gap-3"
        >
          {/* Kind toggle */}
          <div className="flex items-center gap-2">
            {(['world', 'soul'] as const).map((k) => {
              const on = uploadKind === k
              const accent =
                k === 'soul' ? 'var(--color-soul)' : 'var(--color-world)'
              const Icon = k === 'soul' ? Sparkles : Globe
              return (
                <button
                  key={k}
                  onClick={() => setUploadKind(k)}
                  disabled={uploadBusy}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-[12px] border disabled:opacity-50"
                  style={{
                    borderColor: on ? accent : 'var(--color-border-light)',
                    background: on ? `${accent}1a` : 'transparent',
                    color: on
                      ? 'var(--color-text-primary)'
                      : 'var(--color-text-tertiary)',
                  }}
                >
                  <Icon className="w-3.5 h-3.5" style={{ color: accent }} />
                  {k === 'world' ? t('account.uploadWorld') : t('account.uploadSoul')}
                </button>
              )
            })}
          </div>

          {/* File picker — also shows the chosen filename + size so
              the user knows we got the right one before submitting. */}
          <label
            className="flex items-center gap-2 px-3 py-2 rounded border border-dashed cursor-pointer text-[12px]"
            style={{
              borderColor: 'var(--color-border-light)',
              color: 'var(--color-text-tertiary)',
            }}
          >
            <Upload className="w-3.5 h-3.5" />
            {uploadFile
              ? `${uploadFile.name} · ${(uploadFile.size / 1024).toFixed(0)} KB`
              : t('account.uploadPickZip')}
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={uploadBusy}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setUploadFile(f)
                setUploadErr(null)
                setUploadResult(null)
                // Pre-fill the name field from the filename if empty
                // — author can still override before submit.
                if (f && !uploadName) {
                  setUploadName(f.name.replace(/\.zip$/i, '').replace(/[_-]+/g, ' '))
                }
              }}
              className="hidden"
            />
          </label>

          {/* Optional fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              value={uploadSlug}
              onChange={(e) => setUploadSlug(e.target.value)}
              disabled={uploadBusy}
              placeholder={t('account.uploadSlugPh')}
              className="px-3 py-2 rounded border bg-transparent text-[12px] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] disabled:opacity-50"
              style={{
                borderColor: 'var(--color-border-light)',
                fontFamily: 'var(--font-mono)',
              }}
            />
            <input
              value={uploadName}
              onChange={(e) => setUploadName(e.target.value)}
              disabled={uploadBusy}
              placeholder={t('account.uploadNamePh')}
              className="px-3 py-2 rounded border bg-transparent text-[12px] text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] disabled:opacity-50"
              style={{ borderColor: 'var(--color-border-light)' }}
            />
          </div>

          {/* Unlisted toggle — explicit so the user knows the default
              is private-by-hash. Flipping it makes the entry appear
              in the public catalog list (still anyone can already
              reach it by hash today; this only controls listing). */}
          <label className="inline-flex items-center gap-2 text-[12px] text-[var(--color-text-tertiary)]">
            <input
              type="checkbox"
              checked={uploadUnlisted}
              onChange={(e) => setUploadUnlisted(e.target.checked)}
              disabled={uploadBusy}
            />
            {t('account.uploadUnlisted')}
          </label>

          {/* Submit + result/error */}
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={doUpload}
              disabled={!uploadFile || uploadBusy}
              className="hover-btn inline-flex items-center gap-2 px-4 py-2 rounded text-[13px] font-medium disabled:opacity-40"
              style={{
                background: 'var(--color-accent)',
                color: '#0A0A0A',
              }}
            >
              {uploadBusy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              {t('account.uploadGo')}
            </button>
            {uploadResult && (
              <span
                className="inline-flex items-center gap-1.5 text-[12px]"
                style={{ color: 'var(--color-accent)' }}
              >
                <Check className="w-3.5 h-3.5" />
                {t('account.uploadOk').replace('{slug}', uploadResult.id)}
              </span>
            )}
            {uploadErr && (
              <span
                className="text-[12px]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {uploadErr}
              </span>
            )}
          </div>

          <p
            className="font-mono text-[10px] text-[var(--color-text-muted)]"
          >
            {t('account.uploadHint')}
          </p>
        </div>
      </Section>

      {/* ── Published ─────────────────────────────────────────── */}
      <Section
        title={t('account.published')}
        sub={t('account.publishedSub')}
        empty={!data?.published?.length}
        emptyText={t('account.publishedEmpty')}
      >
        <div className="flex flex-col gap-2">
          {(data?.published ?? []).map((p) => {
            const catalogKind = p.kind === 'soul' ? 'souls' : 'worlds'
            const accent =
              p.kind === 'soul'
                ? 'var(--color-soul)'
                : 'var(--color-world)'
            const Icon = p.kind === 'soul' ? Sparkles : Globe
            return (
              <div
                key={p.id}
                className="rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-3 flex items-center gap-3"
              >
                {/* Click main row → public detail page (consumer view). */}
                <Link
                  to={`/${catalogKind}/${p.id}`}
                  className="hover-link flex items-center gap-3 flex-1 min-w-0"
                  style={{ textDecoration: 'none' }}
                >
                  <Icon
                    className="w-4 h-4 shrink-0"
                    style={{ color: accent }}
                  />
                  <span className="flex-1 text-[14px] text-[var(--color-text-primary)] truncate">
                    {p.name}
                  </span>
                  {p.kind === 'soul' && p.values?.origin_world && (
                    <span
                      className="font-mono text-[10px] hidden md:inline truncate max-w-[140px]"
                      style={{ color: accent }}
                    >
                      {t('account.builtIn')} {p.values.origin_world}
                    </span>
                  )}
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)] hidden sm:inline">
                    {p.kind} · {p.id}
                  </span>
                </Link>
                {/* Public / hidden toggle — flips the catalog `unlisted`
                    flag. Hidden = only here in your account; public =
                    shows on the Hub. */}
                {(() => {
                  const hidden = !!p.entry?.unlisted
                  return (
                    <button
                      onClick={() => doSetVisibility(p, !hidden)}
                      disabled={busy}
                      title={hidden ? t('account.makePublic') : t('account.makeHidden')}
                      className="hover-link inline-flex items-center gap-1 text-[12px] disabled:opacity-50"
                      style={{ color: hidden ? 'var(--color-text-tertiary)' : accent }}
                    >
                      {hidden ? (
                        <EyeOff className="w-3.5 h-3.5" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                      <span className="hidden sm:inline">
                        {hidden ? t('account.hidden') : t('account.public')}
                      </span>
                    </button>
                  )
                })()}
                {/* Manage: open the publish-management page (name, desc,
                    cover, 立绘, visibility). Content editing lives behind
                    its "edit content" action — clicking here no longer
                    jumps straight into the create studio. */}
                <button
                  onClick={() =>
                    navigate(
                      `/manage/${encodeURIComponent(p.kind)}/${encodeURIComponent(p.id)}`,
                    )
                  }
                  disabled={busy}
                  title={t('account.edit')}
                  className="hover-link inline-flex items-center gap-1 text-[12px] disabled:opacity-50"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  <Pencil className="w-3.5 h-3.5" />{' '}
                  <span className="hidden sm:inline">{t('account.edit')}</span>
                </button>
                {/* Unpublish: drop from the personal published list.
                    The S3 zip stays (hash-addressed; anyone who already
                    has the hash keeps access) — only this user's
                    account view becomes clean. */}
                <button
                  onClick={() => doUnpublish(p)}
                  disabled={busy}
                  title={t('account.unpublish')}
                  className="hover-link inline-flex items-center gap-1 text-[12px] disabled:opacity-50"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )
          })}
        </div>
      </Section>

      {/* ── Sessions ──────────────────────────────────────────── */}
      <Section
        title={t('account.sessions')}
        sub={t('account.sessionsSub')}
        empty={!sessions?.length}
        emptyText={t('account.sessionsEmpty')}
      >
        <div className="flex flex-col gap-2">
          {(sessions ?? []).map((s) => (
            <div
              key={s.id}
              className="flex items-center gap-3 rounded border border-[var(--color-border-light)] bg-[var(--color-bg-card)] p-3"
            >
              <ShieldCheck
                className="w-4 h-4 shrink-0"
                style={{
                  color: s.is_current
                    ? 'var(--color-accent)'
                    : 'var(--color-text-muted)',
                }}
              />
              <div className="flex flex-col min-w-0 flex-1">
                <span className="text-[13px] text-[var(--color-text-primary)] truncate">
                  {s.is_current && (
                    <span
                      className="font-mono text-[10px] mr-2"
                      style={{ color: 'var(--color-accent)' }}
                    >
                      {t('account.thisDevice')}
                    </span>
                  )}
                  {s.issued_ua ?? t('account.unknownDevice')}
                </span>
                <span className="font-mono text-[10px] text-[var(--color-text-muted)] truncate">
                  {s.issued_ip ?? '—'} · {t('account.lastSeen')}{' '}
                  {relTime(s.last_seen)}
                </span>
              </div>
              {!s.is_current && (
                <button
                  onClick={() => doRevoke(s.id)}
                  disabled={busy}
                  className="hover-link text-[12px] inline-flex items-center gap-1 disabled:opacity-50"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  <Trash2 className="w-3.5 h-3.5" /> {t('account.revoke')}
                </button>
              )}
            </div>
          ))}
        </div>
        {(sessions?.length ?? 0) > 1 && (
          <button
            onClick={doRevokeOthers}
            disabled={busy}
            className="mt-3 inline-flex items-center gap-1.5 text-[12px] hover-link disabled:opacity-50"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {busy ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}{' '}
            {t('account.revokeOthers')}
          </button>
        )}
      </Section>

      {/* ── Sign out (this device only) ───────────────────────── */}
      <div className="pt-4 border-t border-[var(--color-border)]">
        <button
          onClick={() => {
            signOut()
            navigate('/')
          }}
          className="hover-link inline-flex items-center gap-2 text-[13px]"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <LogOut className="w-4 h-4" /> {t('auth.signOut')}
        </button>
      </div>
    </section>
  )
}

// Permanent "finish setting up your account" card — the home for users
// who deferred the registration gate, and the password entry point for
// every legacy account. Hidden once the account is fully registered.
function AccountSetup({
  data,
  onDone,
}: {
  data: Me | null
  onDone: () => Promise<void>
}) {
  const { t } = useI18n()
  const { completeRegistration } = useAuth()
  const [h, setH] = useState('')
  const [name, setName] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [done, setDone] = useState(false)

  if (!data) return null
  // Fully set up already → nothing to show.
  if (data.registered && data.has_password) return null

  async function submit() {
    if (busy || pw.length < 8) return
    setBusy(true)
    setErr('')
    try {
      await completeRegistration({
        password: pw,
        handle: h.trim() || undefined,
        displayName: name.trim() || undefined,
      })
      setDone(true)
      setPw('')
      await onDone()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (done) return null

  return (
    <div
      className="rounded-lg border p-5 flex flex-col gap-3"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-accent-dim)',
      }}
    >
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
        <span
          className="text-[15px] text-[var(--color-text-primary)]"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          {t('setup.title')}
        </span>
      </div>
      <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {t('setup.sub')}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          value={h}
          onChange={(e) => setH(e.target.value)}
          placeholder={data.handle}
          className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
          style={{ borderColor: 'var(--color-border-light)' }}
          data-gramm="false"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('setup.displayName')}
          className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
          style={{ borderColor: 'var(--color-border-light)' }}
          data-gramm="false"
        />
      </div>
      <input
        type="password"
        value={pw}
        onChange={(e) => setPw(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && submit()}
        autoComplete="new-password"
        placeholder={t('setup.password')}
        className="px-3 py-2 rounded-md border bg-transparent text-[14px] text-[var(--color-text-primary)] outline-none"
        style={{ borderColor: 'var(--color-border-light)' }}
      />
      {err && (
        <span className="text-[12px]" style={{ color: 'var(--color-danger, #e5484d)' }}>
          {err}
        </span>
      )}
      <button
        onClick={submit}
        disabled={busy || pw.length < 8}
        className="hover-btn self-start px-5 py-2 rounded-md text-[13px] font-semibold disabled:opacity-40"
        style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
      >
        {t('setup.submit')}
      </button>
    </div>
  )
}

function Section({
  title, sub, empty, emptyText, children,
}: {
  title: string
  sub?: string
  empty: boolean
  emptyText: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span
          className="font-mono text-[11px] tracking-[0.18em]"
          style={{ color: 'var(--color-accent)' }}
        >
          {title}
        </span>
        {sub && (
          <span className="text-[12px] text-[var(--color-text-tertiary)]">
            {sub}
          </span>
        )}
      </div>
      {empty ? (
        <span
          className="text-[12px] italic"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {emptyText}
        </span>
      ) : (
        children
      )}
    </div>
  )
}
