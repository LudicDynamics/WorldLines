import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X, User, LogOut, Globe2, UserCircle, Download } from 'lucide-react'
import { Logo } from './Logo'
import { useI18n, LANGS, LANG_LABEL } from './i18n'
import { useAuth } from './auth'

const NAV: { href: string; key: string; external?: boolean }[] = [
  { href: '/worlds', key: 'nav.worlds' },
  { href: '/souls', key: 'nav.souls' },
  // 同源化:创作入口 = 账户沙盒里的 LocalShell 创作门(老 CreatePage 退役;
  // hub 原生路径,Remote 没有 /local)
  { href: '/create', key: 'nav.create' },
  {
    href: 'https://docs.worldlines.gg/docs/getting-started/introduction',
    key: 'nav.docs',
    external: true,
  },
]

// Popovers render as viewport-fixed panels under the header with a
// full-screen click-catcher. Fixed positioning + z-[200] sidesteps any
// clipping/stacking from the fixed header (and the play overlay).
function Pop({
  open,
  onClose,
  children,
}: {
  open: boolean
  onClose: () => void
  children: ReactNode
}) {
  if (!open) return null
  return (
    <>
      <div className="fixed inset-0 z-[190]" onClick={onClose} />
      <div className="fixed right-4 md:right-12 top-[58px] z-[200]">
        {children}
      </div>
    </>
  )
}

function LangSwitcher() {
  const { lang, setLang } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="hover-link inline-flex items-center gap-1 text-[12px] text-[var(--color-text-secondary)]"
        aria-label="Language"
      >
        <Globe2 className="w-3.5 h-3.5" />
        {LANG_LABEL[lang]}
      </button>
      <Pop open={open} onClose={() => setOpen(false)}>
        <div className="rounded-md border border-[var(--color-border-light)] bg-[var(--color-bg)] py-1 min-w-[120px] shadow-xl">
          {LANGS.map((l) => (
            <button
              key={l}
              onClick={() => {
                setLang(l)
                setOpen(false)
              }}
              className="block w-full text-left px-3 py-1.5 text-[12px] hover:bg-[var(--color-bg-card-inner)]"
              style={{
                color:
                  l === lang
                    ? 'var(--color-accent)'
                    : 'var(--color-text-secondary)',
              }}
            >
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
      </Pop>
    </div>
  )
}

function AuthControl() {
  const { t } = useI18n()
  const { handle, signedIn, signOut, devStub } = useAuth()
  const [open, setOpen] = useState(false)

  // 替身模式(HUB_AUTH_REQUIRED=0 的本地/dev 栈,服务端声明):
  // 明牌徽章,不给任何登录/登出入口 —— 一眼可辨不是生产态。
  if (devStub)
    return (
      <span
        className="inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-md"
        style={{
          border: '1px dashed var(--color-accent)',
          color: 'var(--color-accent)',
        }}
        title="HUB_AUTH_REQUIRED=0"
      >
        <User className="w-3 h-3" /> {handle} · 本地测试账户
      </span>
    )

  // Public-launch gate. When signup is closed:
  //   - already-signed-in users still see their account control (so they
  //     can sign out — flipping the flag must never lock real users out)
  //   - anonymous users see nothing here (the entire "Sign in" entry is
  //     hidden to match the /signup page's coming-soon stance)
  const signupEnabled = import.meta.env.VITE_SIGNUP_ENABLED === 'true'
  if (!signupEnabled && !signedIn) return null

  if (signedIn)
    return (
      <div className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="hover-link inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)]"
        >
          <User className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
          {handle}
        </button>
        <Pop open={open} onClose={() => setOpen(false)}>
          <div className="rounded-md border border-[var(--color-border-light)] bg-[var(--color-bg)] py-1 min-w-[180px] shadow-xl">
            <Link
              to="/account"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 w-full text-left px-3 py-1.5 text-[12px] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-card-inner)] no-underline"
            >
              <UserCircle className="w-3 h-3" /> {t('auth.account')}
            </Link>
            <button
              onClick={() => {
                signOut()
                setOpen(false)
              }}
              className="flex items-center gap-2 w-full text-left px-3 py-1.5 text-[12px] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-card-inner)]"
            >
              <LogOut className="w-3 h-3" /> {t('auth.signOut')}
            </button>
          </div>
        </Pop>
      </div>
    )

  // Anonymous entry → route to /signup, the single identifier-first flow
  // (checkEmail → password for accounts that have one, magic link only
  // for new / passwordless accounts). The old inline "send link" dropdown
  // here bypassed that lookup and ALWAYS emailed a link even to users who
  // had a password — so it never let them just type their password.
  return (
    <Link
      to="/signup"
      className="hover-btn inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium"
      style={{ background: 'var(--color-accent)', color: '#0A0A0A', textDecoration: 'none' }}
    >
      <User className="w-3.5 h-3.5" /> {t('auth.signIn')}
    </Link>
  )
}

export function Header() {
  const { t } = useI18n()
  const [mobileOpen, setMobileOpen] = useState(false)

  const links = NAV.map((l) => (
    <a
      key={l.href}
      href={l.href}
      onClick={() => setMobileOpen(false)}
      className="hover-link text-[13px] text-[var(--color-text-secondary)]"
      style={{ fontFamily: 'var(--font-sans)' }}
      {...(l.external ? { target: '_blank', rel: 'noreferrer' } : {})}
    >
      {t(l.key)}
    </a>
  ))

  return (
    <header className="fixed top-0 left-0 right-0 flex items-center justify-between px-5 md:px-12 h-16 w-full z-50 bg-[var(--color-bg)] border-b border-[var(--color-border)]">
      <Logo />

      <div className="hidden md:flex items-center gap-6">
        <nav className="flex items-center gap-6">{links}</nav>
        <div className="flex items-center gap-4 pl-2 border-l border-[var(--color-border)]">
          <a
            href="https://worldlines.gg/#download"
            target="_blank"
            rel="noreferrer"
            className="hover-btn inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)] px-3 py-1.5 rounded-md border border-[var(--color-border-light)]"
            style={{ textDecoration: 'none' }}
          >
            <Download className="w-3.5 h-3.5" /> {t('nav.download')}
          </a>
          <LangSwitcher />
          <AuthControl />
        </div>
      </div>

      <button
        className="md:hidden p-2 text-[var(--color-text-secondary)]"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Toggle menu"
      >
        {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {mobileOpen && (
        <div className="absolute top-full left-0 right-0 z-50 flex flex-col gap-5 px-5 py-6 bg-[var(--color-bg)] border-b border-[var(--color-border)] page-enter">
          <div className="flex flex-col gap-4">{links}</div>
          <div className="flex items-center justify-between pt-3 border-t border-[var(--color-border)]">
            <LangSwitcher />
            <AuthControl />
          </div>
        </div>
      )}
    </header>
  )
}
