// 导入三选项面板(niko 定稿的新导入 UX):卡片入工坊后,右侧对话顶部
// 出三条转换路径 —— ①制定转换计划(分批,大卡推荐)②白模一次性
// ③手动修改。指令由服务端组装(import-status),前端只负责发送。
// 另有 ImportProgressPin:①进行中时钉在对话上方的进度条 + 「继续下一批」。
import { importSourceUrl, type ImportStatus } from './localClient'
import { useLocalT } from './i18n'

function fmtSize(bytes?: number): string {
  const b = bytes || 0
  return b >= 1024 ? `${Math.round(b / 1024)}KB` : `${b}B`
}

/** 源卡参考条:PNG 显示缩略,其余显示格式芯片。 */
function SourceChip({ st }: { st: ImportStatus }) {
  const { t } = useLocalT()
  const isPng = st.format === 'png-card'
  return (
    <div
      className="flex items-center gap-2.5 rounded-lg border px-2.5 py-2"
      style={{ borderColor: 'var(--lc-line)', background: 'var(--lc-panel)' }}
    >
      {isPng ? (
        <img
          src={importSourceUrl()}
          alt="source card"
          className="rounded-md object-cover"
          style={{ width: 34, height: 46, objectPosition: 'top' }}
        />
      ) : (
        <span className="text-[16px]">▤</span>
      )}
      <div className="min-w-0">
        <div className="text-[11.5px] font-semibold truncate">{t('imp.source')}</div>
        <div className="font-mono text-[10.5px] truncate" style={{ color: 'var(--lc-faint)' }}>
          {st.source_rel} · {fmtSize(st.bytes)}
          {(st.entries || 0) > 0 ? ` · ${t('imp.entries', { n: String(st.entries) })}` : ''}
        </div>
      </div>
    </div>
  )
}

export function ImportOptionsPanel({
  status,
  running,
  onSend,
  onDismiss,
}: {
  status: ImportStatus
  running: boolean
  onSend: (cmd: string) => void
  onDismiss: () => void
}) {
  const { t } = useLocalT()
  const opt =
    'text-left text-[12.5px] rounded-lg px-3 py-2 cursor-pointer border disabled:opacity-50'
  return (
    <div
      className="rounded-xl border p-4 flex flex-col gap-2.5"
      style={{ background: 'var(--lc-panel2)', borderColor: 'var(--lc-candle)' }}
      data-testid="import-options"
    >
      <div className="text-[13px] font-semibold">{t('imp.title')}</div>
      <SourceChip st={status} />
      {status.recommend_plan && (
        <p className="m-0 text-[11.5px]" style={{ color: 'var(--lc-candle)' }}>
          {t('imp.recommend')}
        </p>
      )}
      <button
        disabled={running || !status.start_command}
        onClick={() => status.start_command && onSend(status.start_command)}
        className={opt}
        style={{ borderColor: 'var(--lc-candle)', color: 'var(--lc-candle)', background: 'transparent' }}
      >
        ① {t('imp.opt1')}
        {status.recommend_plan ? ` · ${t('imp.recommended')}` : ''}
        <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-dim)' }}>
          {t('imp.opt1Sub')}
        </span>
      </button>
      <button
        disabled={running || !status.oneshot_command}
        onClick={() => status.oneshot_command && onSend(status.oneshot_command)}
        className={opt}
        style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-text)', background: 'transparent' }}
      >
        ② {t('imp.opt2')}
        <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-dim)' }}>
          {t('imp.opt2Sub')}
        </span>
      </button>
      <button
        disabled={running}
        onClick={onDismiss}
        className={opt}
        style={{ borderColor: 'var(--lc-line)', color: 'var(--lc-dim)', background: 'transparent' }}
      >
        ③ {t('imp.opt3')}
        <span className="block text-[11px] mt-0.5" style={{ color: 'var(--lc-faint)' }}>
          {t('imp.opt3Sub')}
        </span>
      </button>
    </div>
  )
}

/** ①进行中:对话上方常驻进度 + 继续按钮(计划完成自动消失)。 */
export function ImportProgressPin({
  status,
  running,
  onSend,
}: {
  status: ImportStatus
  running: boolean
  onSend: (cmd: string) => void
}) {
  const { t } = useLocalT()
  const plan = status.plan
  if (!plan || plan.complete) return null
  return (
    <div
      className="flex items-center gap-2 rounded-lg border px-3 py-2 text-[12px]"
      style={{ background: 'var(--lc-candle-soft)', borderColor: 'var(--lc-candle)' }}
      data-testid="import-progress"
    >
      <span className="font-mono" style={{ color: 'var(--lc-candle)' }}>
        {t('imp.progress', { done: String(plan.done), total: String(plan.total) })}
      </span>
      <span className="min-w-0 truncate" style={{ color: 'var(--lc-dim)' }}>
        {plan.next_title ? t('imp.next', { title: plan.next_title }) : ''}
      </span>
      <button
        disabled={running || !status.resume_command}
        onClick={() => status.resume_command && onSend(status.resume_command)}
        className="ml-auto shrink-0 text-[11.5px] font-semibold rounded-md px-2.5 py-1 cursor-pointer border-0 disabled:opacity-50"
        style={{ background: 'var(--lc-candle)', color: 'var(--lc-on-accent)' }}
      >
        {t('imp.continue')}
      </button>
    </div>
  )
}
