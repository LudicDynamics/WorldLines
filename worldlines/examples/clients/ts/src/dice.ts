// Checks the narrator writes into the prose — "[调查员 说服(问出钥匙): 96 > 35] → 大失败" — lifted out and rolled on screen.
export interface Roll { who: string; skill: string; why: string; roll: number; op: string; target: number; outcome: string; good: boolean }

const LINE = /\[([^\s\][]+) ([^(\][]+?)\(([^)]*)\): (\d+) (>|<|≤|<=|≥|>=) (\d+)\] → ([^\s\n]+)/g
const GOOD = /大成功|成功|critical|success|成功した|성공/i
const BAD = /失败|fumble|failure|失敗|실패/i

/** The checks in a piece of prose, and the prose without them. */
export function liftRolls(text: string): { rolls: Roll[]; rest: string } {
  const rolls: Roll[] = []
  const rest = text.replace(LINE, (_m, who, skill, why, roll, op, target, outcome) => {
    rolls.push({ who, skill: skill.trim(), why, roll: +roll, op, target: +target, outcome, good: GOOD.test(outcome) && !BAD.test(outcome) })
    return ''
  }).replace(/\n{3,}/g, '\n\n')
  return { rolls, rest }
}

/** Plays rolls one after another in the overlay: digits spin, then land on the result. */
export class DiceTray {
  private el: HTMLElement
  private queue: Roll[] = []
  private busy = false
  private faceUrl: string | null
  constructor(el: HTMLElement, faceUrl: string | null) { this.el = el; this.faceUrl = faceUrl }

  push(rolls: Roll[]): void {
    this.queue.push(...rolls)
    if (!this.busy) void this.next()
  }

  private async next(): Promise<void> {
    const r = this.queue.shift()
    if (!r) { this.busy = false; return }
    this.busy = true
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    this.el.innerHTML = `<div class="die-card">
      ${this.faceUrl ? `<img class="die-face" src="${this.faceUrl}" alt="" onerror="this.remove()">` : ''}
      <div class="die-who">${esc(r.who)} · ${esc(r.skill)}</div>
      <div class="die-why">${esc(r.why)}</div>
      <div class="die-pair"><span class="d10 tens">00</span><span class="d10 units">0</span></div>
      <div class="die-total"></div>
      <div class="die-target">目标 ${esc(r.op)} ${r.target}</div>
      <div class="die-out"></div></div>`
    this.el.hidden = false
    const tens = this.el.querySelector('.tens') as HTMLElement, units = this.el.querySelector('.units') as HTMLElement
    const out = this.el.querySelector('.die-out') as HTMLElement
    const spin = reduce ? 0 : 14
    for (let i = 0; i < spin; i++) {
      tens.textContent = String(Math.floor(Math.random() * 10) * 10).padStart(2, '0'); units.textContent = String(Math.floor(Math.random() * 10))
      await wait(45 + i * 6)
    }
    const v = r.roll === 100 ? 100 : r.roll
    tens.textContent = v === 100 ? '00' : String(Math.floor(v / 10) * 10).padStart(2, '0'); units.textContent = String(v % 10)
    ;(this.el.querySelector('.die-total') as HTMLElement).textContent = String(r.roll)
    out.textContent = r.outcome; out.className = `die-out ${r.good ? 'good' : 'bad'}`
    await wait(reduce ? 900 : 1500)
    this.el.hidden = true
    void this.next()
  }
}

const wait = (ms: number) => new Promise(res => setTimeout(res, ms))
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
