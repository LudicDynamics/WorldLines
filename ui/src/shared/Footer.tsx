import { useI18n } from './i18n'

const FOOTER: {
  catKey: string
  links: { labelKey?: string; label?: string; href: string }[]
}[] = [
  {
    catKey: 'foot.product',
    links: [
      {
        labelKey: 'foot.documentation',
        href: 'https://docs.worldlines.gg/docs/getting-started/introduction',
      },
      {
        labelKey: 'foot.starter',
        href: 'https://github.com/LudicDynamics/stoneford-worldlines',
      },
    ],
  },
  {
    catKey: 'foot.community',
    links: [
      { label: 'Discord', href: 'https://discord.gg/HJYWbdqWrE' },
      { labelKey: 'foot.archive', href: 'https://ludics.space' },
    ],
  },
  {
    catKey: 'foot.hub',
    links: [
      { labelKey: 'foot.worldhubSpec', href: 'https://github.com/LudicDynamics' },
      { labelKey: 'foot.soulhubSpec', href: 'https://github.com/LudicDynamics' },
    ],
  },
  {
    catKey: 'foot.company',
    links: [
      { labelKey: 'foot.about', href: 'https://ludicdynamics.com' },
      { labelKey: 'foot.blog', href: 'https://ludicdynamics.com/blog/en' },
    ],
  },
]

export function Footer() {
  const { t } = useI18n()
  return (
    <footer className="relative flex flex-col gap-3 px-5 md:px-12 py-6 w-full bg-[var(--color-bg)] mt-16 border-t border-[var(--color-border)]">
      <div className="flex flex-col md:flex-row justify-between gap-6 md:gap-0 w-full">
        <div className="flex flex-col gap-2 max-w-[320px]">
          <span
            className="text-[18px] text-[var(--color-text-primary)]"
            style={{ fontFamily: 'var(--font-display)', letterSpacing: 0.5 }}
          >
            Worldlines · Hub
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text-tertiary)]">
            {t('foot.tagline')}
          </span>
        </div>

        <div className="flex flex-row flex-wrap gap-6 md:gap-10">
          {FOOTER.map((group) => (
            <div key={group.catKey} className="flex flex-col gap-2">
              <span
                className="text-[12px] font-semibold text-[var(--color-text-primary)] uppercase tracking-[1px]"
                style={{ fontFamily: 'var(--font-sans)' }}
              >
                {t(group.catKey)}
              </span>
              {group.links.map((l) => (
                <a
                  key={l.labelKey ?? l.label ?? l.href}
                  href={l.href}
                  target="_blank"
                  rel="noreferrer"
                  className="hover-link text-[12px] text-[var(--color-text-secondary)]"
                  style={{ fontFamily: 'var(--font-sans)' }}
                >
                  {l.labelKey ? t(l.labelKey) : l.label}
                </a>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="w-full h-px bg-[var(--color-border)] mt-4" />
      <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
        © {new Date().getFullYear()} Ludic Dynamics · {t('foot.rights')}
      </span>
    </footer>
  )
}
