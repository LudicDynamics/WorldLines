// LocalShell layout (docs/WEBUI-UNIFICATION.md L1) — the local engine's own
// chrome: no Hub header, no auth gate. All /local/* pages render inside this
// frame and talk to `neonrp web` via localClient.
//
// Two switchable palettes:黑 = visionrp desktop tokens
// (rp-visionrp/src/renderer/styles.css:black surfaces + green primary);
// 白 = archive-room 档案纸(rp-visionrp/proto/archive-room:aged paper +
// ink + 褪红/金/teal)。☀/☾ 切换,localStorage 持久。
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getMeta, localEndpoint, type LocalMeta } from './localClient'
import { WELCOMED_KEY } from './LocalWelcome'
import { LANGS, LANG_LABEL, useLocalT, type Lang } from './i18n'
import { useHostedChrome } from './hostedChrome'

type Theme = 'dark' | 'light'

const THEMES: Record<Theme, React.CSSProperties> = {
  dark: {
    // 统一暗阶(docs/DESIGN-TOKENS.md,niko 画布定稿):四级层次
    // bg → surface(卡) → elevated(嵌板) → line,中性无蓝偏。
    background: '#0B0B0D',
    color: 'var(--lc-text)',
    '--lc-text': '#F5F5F7',
    '--lc-panel': '#101014', // surface-card
    '--lc-panel2': '#15151A', // surface-elevated
    '--lc-line': '#26262C', // border-default
    '--lc-dim': '#A2A2AB', // text-secondary
    '--lc-faint': '#6C6C75', // text-muted
    '--lc-candle': '#34E879', // accent-primary(green)
    '--lc-candle-soft': '#34E87922', // accent-glow
    '--lc-live': '#06B6D4', // accent-cyan
    '--lc-on-accent': '#06210F', // 绿底墨绿字(比纯黑柔)
    // 可视化 token(封面渐变/图形随主题):夜色深渐变
    '--lc-cov1': '32% 30%',
    '--lc-cov2': '28% 18%',
    '--lc-cov3': '24% 12%',
  } as React.CSSProperties,
  light: {
    // 白 = archive-room 档案纸(rp-visionrp/proto/archive-room/index.html
    // :root):做旧纸底 + 墨字 + 褪红/金/青灰绿 —— Belle Époque 档案室的
    // 阅读感,入口在 visionrp Tauri 原型里。
    background: '#f4f1ea', // --paper
    color: '#3a352f',
    '--lc-text': '#3a352f', // --ink
    '--lc-panel': '#fbf9f4', // --card
    '--lc-panel2': '#efeae0', // --paper2
    '--lc-line': '#d9d2c4', // --line
    '--lc-dim': '#6f6657', // --ink2
    '--lc-faint': '#9a9081', // --muted
    '--lc-candle': '#b5654a', // --accent 褪红
    '--lc-candle-soft': '#b5654a18',
    '--lc-live': '#5d7d75', // --teal
    '--lc-on-accent': '#fff', // 褪红底白字(archive-room .wchip.on)
    // 可视化 token:水彩纸色(淡彩高明度,对标 .card .ph 的 tan→sage)
    '--lc-cov1': '28% 78%',
    '--lc-cov2': '24% 70%',
    '--lc-cov3': '20% 62%',
  } as React.CSSProperties,
}

export function LocalApp() {
  const [meta, setMeta] = useState<LocalMeta | null>(null)
  const [dead, setDead] = useState(false)
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem('wl-local-theme') as Theme) || 'dark'
    } catch {
      return 'dark'
    }
  })
  const loc = useLocation()
  const nav = useNavigate()
  const { t, lang, setLang } = useLocalT()
  // hosted(hub 入口复用)时导航语义整体切换:Remote 没有 Local 命名空间。
  const hosted = useHostedChrome()

  // 每次启动都过门面(visionrp start-screen 语义,PLAY-FUSION §四.1):
  // sessionStorage = 本 tab 生命周期 —— 新开 tab/重启浏览器必见门面;
  // 只挡壳根路由 /local,深链(/local/play 等)不劫持。
  useEffect(() => {
    if (loc.pathname !== '/local') return
    let welcomed = false
    try {
      welcomed = sessionStorage.getItem(WELCOMED_KEY) === '1'
    } catch {
      welcomed = true // storage 不可用就别拦路
    }
    if (!welcomed) nav('/local/welcome', { replace: true })
    // 只在挂载时判定一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    getMeta()
      .then(setMeta)
      .catch(() => setDead(true))
  }, [])

  function toggleTheme() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    try {
      localStorage.setItem('wl-local-theme', next)
    } catch {
      /* storage off */
    }
  }

  return (
    <div
      className={hosted ? 'w-full' : 'min-h-screen w-full'}
      style={
        {
          fontFamily: "'Inter',-apple-system,'PingFang SC',sans-serif",
          ...THEMES[theme],
        } as React.CSSProperties
      }
    >
      <div className="max-w-[1080px] mx-auto px-6 pb-16">
        {/* C9(niko 判词):chrome 属于壳。hosted 下顶栏由 Hub 的 App 布局
            (shared/Header)提供,LocalApp 不再渲染自己的头 —— 复用的是
            内容组件,不是 Local 的壳。local 单机渲染原样不变。 */}
        {!hosted && (
        <header className="flex items-center gap-4 py-5 border-b" style={{ borderColor: 'var(--lc-line)' }}>
          <Link to="/local" className="text-[17px] tracking-wide" style={{ fontWeight: 700 }}>
            World<span style={{ color: 'var(--lc-candle)' }}>Lines</span>
            <span className="ml-2 text-[11px]" style={{ color: 'var(--lc-faint)' }}>{t('app.local')}</span>
          </Link>
          <nav className="flex gap-1 text-[13px] ml-4">
            {(
              [
                ['/local', t('nav.home')],
                ['/local/observe', '▶ ' + t('nav.observe')],
                ['/local/create', t('nav.create')],
                ['/local/library', t('nav.library')],
                ['/local/settings', '⚙ ' + t('nav.settings')],
              ] as [string, string][]
            ).map(([to, label]) => (
              <Link
                key={to}
                to={to}
                className="px-3 py-1 rounded-lg"
                style={
                  (to === '/local' ? loc.pathname === '/local' : loc.pathname.startsWith(to))
                    ? { background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                    : { color: 'var(--lc-dim)' }
                }
              >
                {label}
              </Link>
            ))}
            <a
              href="https://hub.worldlines.gg"
              target="_blank"
              rel="noreferrer"
              className="px-3 py-1 rounded-lg"
              style={{ color: 'var(--lc-dim)' }}
            >
              ⇪ Hub
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-1">
            {LANGS.map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className="text-[12px] rounded-lg px-2 py-1 cursor-pointer border"
                style={
                  l === lang
                    ? { borderColor: 'var(--lc-candle)', background: 'var(--lc-candle-soft)', color: 'var(--lc-candle)' }
                    : { borderColor: 'var(--lc-line)', background: 'transparent', color: 'var(--lc-dim)' }
                }
              >
                {LANG_LABEL[l as Lang]}
              </button>
            ))}
          </div>
          <button
            onClick={toggleTheme}
            aria-label={t('app.themeToggle')}
            title={theme === 'dark' ? t('app.toLight') : t('app.toDark')}
            className="text-[13px] rounded-lg px-2.5 py-1 cursor-pointer border"
            style={{ borderColor: 'var(--lc-line)', background: 'var(--lc-panel)', color: 'var(--lc-dim)' }}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <span className="text-[11px] font-mono" style={{ color: 'var(--lc-faint)' }}>
            {dead ? (
              <span style={{ color: '#FF6B8A' }}>{t('app.engineDown')}</span>
            ) : meta ? (
              <>
                <span style={{ color: 'var(--lc-live)' }}>●</span> {t('app.localEngine')} · v{meta.engine_version}
              </>
            ) : (
              t('app.connecting')
            )}
          </span>
        </header>
        )}
        {dead ? (
          <div className="mt-16 text-center text-[14px]" style={{ color: 'var(--lc-dim)' }}>
            <p>{t('app.cantConnect', { ep: localEndpoint() })}</p>
            <p className="mt-2 font-mono text-[12px]" style={{ color: 'var(--lc-faint)' }}>
              cd NeonRP && uv run neonrp web
            </p>
          </div>
        ) : (
          <Outlet />
        )}
      </div>
    </div>
  )
}
