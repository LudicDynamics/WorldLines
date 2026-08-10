import { useNavigate } from 'react-router-dom'
import { Check, ArrowRight, Zap, Cloud, Github } from 'lucide-react'
import { useAuth } from '../shared/auth'
import { useI18n } from '../shared/i18n'
import { stripeCheckout } from '../shared/identity'
import { track } from '../shared/analytics'
import { useState } from 'react'

export function PricingPage() {
  const { t } = useI18n()
  const { signedIn, tier } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  async function upgrade() {
    if (!signedIn) {
      navigate('/signup')
      return
    }
    setBusy(true)
    try {
      const { url } = await stripeCheckout()
      track('pricing_upgrade_clicked', { tier })
      window.location.href = url
    } catch {
      setBusy(false)
    }
  }

  const isPaid = tier === 'paid'

  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <div className="text-center mb-12">
        <h1
          className="text-[var(--color-text-primary)] mb-3"
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(28px, 4vw, 40px)',
            lineHeight: 1.15,
          }}
        >
          {t('pricing.title')}
        </h1>
        <p
          className="text-[var(--color-text-tertiary)] max-w-[480px] mx-auto"
          style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6 }}
        >
          {t('pricing.subtitle')}
        </p>
      </div>

      {/* Why we charge */}
      <div
        className="mx-auto mb-10 max-w-[560px] rounded-xl border p-5 flex gap-4"
        style={{
          borderColor: 'var(--color-border-light)',
          background: 'var(--color-bg-card-inner)',
        }}
      >
        <Cloud
          className="w-5 h-5 mt-0.5 shrink-0"
          style={{ color: 'var(--color-accent-dim)' }}
        />
        <div>
          <div
            className="font-mono text-[10px] tracking-[0.18em] uppercase mb-1.5"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {t('pricing.whyTitle')}
          </div>
          <p
            className="text-[13px]"
            style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}
          >
            {t('pricing.whyBody')}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-[640px] mx-auto">
        {/* Free */}
        <div
          className="rounded-xl border p-6 flex flex-col gap-4"
          style={{
            borderColor: 'var(--color-border-light)',
            background: 'var(--color-bg-card)',
          }}
        >
          <div>
            <span
              className="font-mono text-[10px] tracking-[0.18em] uppercase"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {t('pricing.freeLabel')}
            </span>
            <div className="mt-2 flex items-baseline gap-1">
              <span
                className="font-bold text-[var(--color-text-primary)]"
                style={{ fontSize: 28 }}
              >
                $0
              </span>
              <span
                className="text-[13px]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                / {t('pricing.month')}
              </span>
            </div>
          </div>
          <ul className="flex flex-col gap-2.5">
            {[
              t('pricing.freePlays'),
              t('pricing.freeCreate'),
              t('pricing.freeCatalog'),
            ].map((item, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[13px]"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <Check className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--color-text-tertiary)' }} />
                {item}
              </li>
            ))}
          </ul>
          <button
            disabled
            className="rounded-md px-4 py-2.5 text-[13px] font-medium opacity-40"
            style={{
              background: 'var(--color-bg-card-inner)',
              color: 'var(--color-text-secondary)',
            }}
          >
            {t('pricing.currentPlan')}
          </button>
        </div>

        {/* Paid */}
        <div
          className="rounded-xl border p-6 flex flex-col gap-4 relative"
          style={{
            borderColor: 'var(--color-accent-dim)',
            background: 'var(--color-bg-card)',
          }}
        >
          {isPaid && (
            <span
              className="absolute -top-2.5 right-4 font-mono text-[10px] tracking-[0.14em] px-2.5 py-0.5 rounded-full"
              style={{
                background: 'var(--color-accent)',
                color: '#0A0A0A',
              }}
            >
              {t('pricing.yourPlan')}
            </span>
          )}
          <div>
            <span
              className="font-mono text-[10px] tracking-[0.18em] uppercase"
              style={{ color: 'var(--color-accent-dim)' }}
            >
              {t('pricing.paidLabel')}
            </span>
            <div className="mt-2 flex items-baseline gap-1">
              <span
                className="font-bold"
                style={{ color: 'var(--color-accent)', fontSize: 28 }}
              >
                $5
              </span>
              <span
                className="text-[13px]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                / {t('pricing.month')}
              </span>
            </div>
          </div>
          <ul className="flex flex-col gap-2.5">
            {[
              t('pricing.paidPlays'),
              t('pricing.paidCreate'),
              t('pricing.paidSupport'),
            ].map((item, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[13px]"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <Check className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--color-accent-dim)' }} />
                {item}
              </li>
            ))}
          </ul>
          {isPaid ? (
            <button
              disabled
              className="rounded-md px-4 py-2.5 text-[13px] font-medium opacity-40"
              style={{
                background: 'var(--color-bg-card-inner)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {t('pricing.currentPlan')}
            </button>
          ) : (
            <button
              onClick={upgrade}
              disabled={busy}
              className="hover-btn inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-[13px] font-medium disabled:opacity-40"
              style={{ background: 'var(--color-accent)', color: '#0A0A0A' }}
            >
              <Zap className="w-4 h-4" />
              {busy ? '...' : t('pricing.upgrade')}
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Self-host alternative */}
      <div
        className="mt-10 mx-auto max-w-[640px] rounded-xl border p-6"
        style={{
          borderColor: 'var(--color-border-light)',
          background: 'var(--color-bg-card)',
        }}
      >
        <div
          className="font-mono text-[10px] tracking-[0.18em] uppercase mb-2"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          {t('pricing.selfHostTitle')}
        </div>
        <p
          className="text-[13px] mb-4"
          style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}
        >
          {t('pricing.selfHostBody')}
        </p>
        <a
          href="https://github.com/LudicDynamics/WorldLines"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-[13px] hover:opacity-80"
          style={{ color: 'var(--color-accent)' }}
        >
          <Github className="w-4 h-4" />
          {t('pricing.selfHostCta')}
        </a>
      </div>

      <p className="mt-8 text-center text-[11px] text-[var(--color-text-tertiary)]">
        {t('pricing.footer')}
      </p>
    </main>
  )
}

export default PricingPage
