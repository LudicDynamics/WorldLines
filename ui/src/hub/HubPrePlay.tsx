// Hub 进场页(D4 stepper 的 hosted 版,PLAY-FUSION §四 / HUB-GOLIVE P1.5):
// ①世界确认(registry)②模式 ③账户/配额(hosted 插槽 —— 取代 local 的
// 模型接入)→ 创建网关会话 → 进共享 PlayStage。老 PlayPage 的入口继任者,
// URL 形状不变(/play/:kind/:slug),店面各处链接零改动。
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchRegistry, coverFor, type Kind as RegKind, type RegistryEntry } from '../shared/registry'
import { useI18n } from '../shared/i18n'
import { useAuth } from '../shared/auth'
import { startSession } from '../play/playClient'
import { localEndpoint } from '../local/localClient'

const S: Record<string, Record<string, string>> = {
  zh: {
    title: '进入世界',
    step1: '① 世界确认',
    step2: '② 游玩模式',
    step3: '③ 账户',
    modeNative: '以世界原生模式运行 — multi-agent 世界全员角色上场,与本地游玩一致',
    account: '账户',
    signedOut: '未登录 — 本地/开发栈可直接进入;线上将要求登录',
    go: '进入世界 ▸',
    starting: '正在唤醒世界…',
    failed: '会话创建失败:',
    back: '‹ 返回详情',
  },
  en: {
    title: 'Enter the world',
    step1: '① World',
    step2: '② Mode',
    step3: '③ Account',
    modeNative: 'Runs in the world\u2019s native mode — multi-agent worlds bring every character, same as local play',
    account: 'Account',
    signedOut: 'Signed out — dev stacks proceed; production will require login',
    go: 'Enter ▸',
    starting: 'Waking the world…',
    failed: 'Session failed: ',
    back: '‹ Back',
  },
  ja: {
    title: 'ワールドへ',
    step1: '① ワールド確認',
    step2: '② モード',
    step3: '③ アカウント',
    modeNative: 'ワールド本来のモードで実行 — multi-agent ワールドは全キャラクターが登場',
    account: 'アカウント',
    signedOut: '未ログイン — 開発環境ではそのまま入れます',
    go: '入場 ▸',
    starting: 'ワールドを起こしています…',
    failed: 'セッション失敗:',
    back: '‹ 戻る',
  },
  ko: {
    title: '월드 입장',
    step1: '① 월드 확인',
    step2: '② 모드',
    step3: '③ 계정',
    modeNative: '월드 고유 모드로 실행 — multi-agent 월드는 모든 캐릭터가 등장',
    account: '계정',
    signedOut: '로그아웃 상태 — 개발 스택은 바로 입장',
    go: '입장 ▸',
    starting: '월드를 깨우는 중…',
    failed: '세션 실패: ',
    back: '‹ 뒤로',
  },
}

/** registry 条目物化进账户库(引擎的 hub download 面)。已在库则幂等失败
 *  也无妨 —— 调用方只在"直接进场失败"后兜底调用。 */
async function hubDownload(kind: 'worlds' | 'souls', query: string): Promise<void> {
  const r = await fetch(`${localEndpoint()}/api/v1/local/hub/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, query }),
  })
  const d = (await r.json().catch(() => ({}))) as { ok?: boolean; error?: string }
  if (!r.ok || !d.ok) throw new Error(d.error || `download → ${r.status}`)
}

export function HubPrePlay() {
  const { kind = 'worlds', slug = '' } = useParams()
  const nav = useNavigate()
  const { lang } = useI18n()
  const tt = useMemo(() => S[lang] ?? S.en, [lang])
  const [entry, setEntry] = useState<RegistryEntry | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const { signedIn, handle, devStub } = useAuth()

  // Soul Talk 同源化(niko):souls 目录条目不走网关会话,直接进 LocalShell
  // 的原生流 —— 确保 soul 在账户库(不在则从 registry 下载)→
  // /local/preplay/soul-talk?cast=<id>(与本地角色库/工坊的开聊完全一致)。
  useEffect(() => {
    if (kind !== 'souls' || !slug) return
    let alive = true
    ;(async () => {
      try {
        const r = await fetch(`${localEndpoint()}/api/v1/local/souls`)
        const d = (await r.json().catch(() => ({}))) as {
          souls?: { sid: string; dir_name?: string }[]
        }
        const hit = (d.souls || []).find(
          (s) => s.sid === slug || (s.dir_name || '').startsWith(slug),
        )
        if (!hit) await hubDownload('souls', slug)
        if (!alive) return
        nav(`/play/prep/soul-talk?cast=${encodeURIComponent(hit?.dir_name || hit?.sid || slug)}`, {
          replace: true,
        })
      } catch (e) {
        if (alive) setErr(String((e as Error).message || e))
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, slug])

  useEffect(() => {
    let alive = true
    fetchRegistry(kind as RegKind)
      .then((r) => {
        if (!alive) return
        const list = (kind === 'souls' ? r.souls : r.worlds) ?? []
        setEntry(list.find((x) => x.slug === slug) ?? null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [kind, slug])

  async function go() {
    setBusy(true)
    setErr('')
    try {
      let res
      try {
        res = await startSession(kind as 'worlds' | 'souls', slug)
      } catch {
        // 非内置世界:引擎按 slug 解析不到 → 从 registry 物化进账户库
        // 再试一次(HUB-GOLIVE §P5 世界下载的另一半)。
        await hubDownload('worlds', slug)
        res = await startSession(kind as 'worlds' | 'souls', slug)
      }
      nav(`/play/session/${encodeURIComponent(res.session_id)}`, {
        state: {
          opening: res.note || '',
          worldName: entry?.name || slug,
          messages: res.messages ?? null,
        },
      })
    } catch (e) {
      setErr(String((e as Error).message || e))
      setBusy(false)
    }
  }

  const panel: React.CSSProperties = {
    background: 'var(--color-bg-card)',
    border: '1px solid var(--color-border)',
    borderRadius: 14,
    padding: 20,
  }

  return (
    <div className="max-w-[720px] mx-auto px-6 py-10 flex flex-col gap-5">
      <button
        onClick={() => nav(-1)}
        className="text-left text-[13px]"
        style={{ color: 'var(--color-text-tertiary)', background: 'none', border: 0, cursor: 'pointer' }}
      >
        {tt.back}
      </button>
      <h1 className="text-[24px] font-semibold" style={{ color: 'var(--color-text-primary)' }}>
        {tt.title}
      </h1>

      <section style={panel}>
        <div className="text-[12px] mb-3" style={{ color: 'var(--color-accent)' }}>{tt.step1}</div>
        <div className="flex gap-4 items-center">
          <div
            className="w-[96px] h-[64px] rounded-lg shrink-0"
            style={{
              background: (() => {
                const u = coverFor(kind as RegKind, slug, entry)
                return u ? `url(${u}) center/cover` : 'linear-gradient(135deg,#2E1F4E,#101014)'
              })(),
            }}
          />
          <div>
            <div className="font-semibold text-[16px]" style={{ color: 'var(--color-text-primary)' }}>
              {entry?.name || slug}
            </div>
            <div className="text-[12.5px] mt-1" style={{ color: 'var(--color-text-secondary)' }}>
              {entry?.changelog || ''}
            </div>
          </div>
        </div>
      </section>

      <section style={panel}>
        <div className="text-[12px] mb-3" style={{ color: 'var(--color-accent)' }}>{tt.step2}</div>
        {/* HUB-GOLIVE §P2 根治:沙盒引擎按世界清单原生绑定(与 local 启动
            同一条路径),模式不再是网关侧的开关 —— 这里如实陈述。 */}
        <div className="text-[13px]" style={{ color: 'var(--color-text-secondary)' }}>
          {tt.modeNative}
        </div>
      </section>

      <section style={panel}>
        <div className="text-[12px] mb-3" style={{ color: 'var(--color-accent)' }}>{tt.step3}</div>
        <div className="text-[13px]" style={{ color: 'var(--color-text-secondary)' }}>
          {devStub
            ? `${tt.account}: ${handle} · 本地测试账户`
            : signedIn
              ? `${tt.account}: ${handle} ✓`
              : tt.signedOut}
        </div>
      </section>

      {err ? (
        <div className="text-[13px]" style={{ color: '#F87171' }}>
          {tt.failed}
          {err}
        </div>
      ) : null}
      <button
        onClick={go}
        disabled={busy}
        className="py-3 rounded-xl font-semibold text-[15px]"
        style={{ background: 'var(--color-accent)', color: '#0A0A0A', border: 0, cursor: busy ? 'wait' : 'pointer', opacity: busy ? 0.7 : 1 }}
        data-testid="hub-preplay-go"
      >
        {busy ? tt.starting : tt.go}
      </button>
    </div>
  )
}
