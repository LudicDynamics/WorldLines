// The game: title → play (scene · cast · dialogue · choices) · map · clues · ending.
// What the beats are comes from the host (beat-kinds); what the world looks like comes from its art pack. Nothing here
// names a particular beat or world.
import { WorldLinesClient, explain, speaker, type BeatEvent, type BeatKinds } from './client.ts'
import { HostReads, type HostState } from './host.ts'
import { Art, type Clue } from './art.ts'
import { DiceTray, liftRolls } from './dice.ts'

const $ = <T extends HTMLElement = HTMLElement>(sel: string) => document.querySelector(sel) as T
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

let client: WorldLinesClient
let reads: HostReads
let art: Art = new Art({ world: '' }, '/')
let kinds: BeatKinds = { kinds: {} }
let dice: DiceTray
let state: HostState = {}
let vars: Record<string, unknown> = {}
let clock = ''
let found = new Set<string>()
let seg: { el: HTMLElement; body: HTMLElement; who: string; beat?: string; raw: string } | null = null
let lastBeat: string | undefined
let speaking = ''
let busy = false

const kindOf = (b?: string) => (b && kinds.kinds[b]) || {}
const startKind = () => kindOf(kinds.start)
const label = (b?: string) => kindOf(b).label || b || ''

// ── title ────────────────────────────────────────────────────────────────────────────────────────────────────────
async function showTitle(world: string | null) {
  art = await Art.load(world)
  const p = art.pack
  $('#title-art').style.backgroundImage = (await art.has(p.title_art)) ? `url(${art.url(p.title_art)})` : ''
  $('#title-name').textContent = p.title || 'WorldLines'
  $('#title-sub').textContent = p.subtitle || ''
  $('#title-pitch').textContent = p.pitch || ''
}

async function connect(e: Event) {
  e.preventDefault()
  const token = $<HTMLInputElement>('#token').value.trim()
  const msg = $('#title-msg')
  msg.textContent = '连接中……'
  client?.close()
  reads = new HostReads('', token)
  client = new WorldLinesClient('', token, {
    onChunk, onBeat, onAsk,
    onTurnStarted: () => { seg = null; lastBeat = undefined },
    onConnection: (s, d) => { $('#conn').textContent = s === 'retrying' ? `和主进程断开了,正在重连…(${d || ''})` : '' },
  })
  try {
    await client.connect()
    const world = await reads.templateId()
    if (world && world !== art.pack.world) await showTitle(world)
    kinds = await client.beatKinds()
    if ((art.pack as { game?: string }).game === 'town') {   // a walkable town (石津镇): its own screen on the same client
      $('#title').hidden = true
      const { startTown } = await import('./town.ts')
      await startTown(client, reads, art, kinds)
      return
    }
    dice = new DiceTray($('#dice'), (await art.has(art.pack.dice)) ? art.url(art.pack.dice) : null)
    document.body.classList.add('playing')
    await refresh()
    hints()
    narrate(art.pack.pitch || '', '')
    $<HTMLInputElement>('#say').focus()
  } catch (err) { msg.textContent = explain(err) }
}

// ── the world on screen: scene, cast, meters, clues ──────────────────────────────────────────────────────────────
async function refresh() {
  const [s, v] = await Promise.all([reads.state(), reads.vars()])
  state = s || state; vars = v
  const here = state.player_location
  $('#place').textContent = (here && state.places?.[here]) || here || ''
  $('#clock').textContent = clock || String(vars['time.clock'] ?? '')
  await setScene(here)
  await drawCast(here)
  drawMeters()
  await drawClues()
  const ending = await reads.settlement()
  if (ending) await showEnding(ending)
}

let sceneUrl = ''
async function setScene(place?: string) {
  // the place's own picture; not drawn yet → the world's key art, dimmed, with the place's name on it
  const own = art.scene(place), hasOwn = await art.has(own)
  const rel = hasOwn ? own : (art.pack.fallback_scene || art.pack.title_art)
  const url = (await art.has(rel)) ? art.url(rel)! : ''
  if (url + place === sceneUrl) return
  sceneUrl = url + place
  const [a, b] = [$('#scene-a'), $('#scene-b')]
  const next = a.classList.contains('on') ? b : a, prev = next === a ? b : a
  next.style.backgroundImage = url ? `url(${url})` : ''
  next.classList.toggle('placeholder', !url)
  next.classList.toggle('stand-in', !!url && !hasOwn)
  next.dataset.label = hasOwn ? '' : ((place && state.places?.[place]) || '')
  next.classList.add('on'); prev.classList.remove('on')
}

async function drawCast(place?: string) {
  const cast = $('#cast'); cast.replaceChildren()
  const here = (state.souls || []).filter(s => s.location === place).map(s => s.name)
  const npcs = (art.pack.npcs_by_place?.[place || ''] || []).map(id => art.pack.portraits?.[id]?.name || id)
  for (const name of [...new Set([...npcs, ...here])]) {
    const rel = art.portraitOf(name)
    const fig = document.createElement('figure'); fig.className = 'actor'; fig.dataset.name = name
    if (rel && await art.has(rel)) fig.innerHTML = `<img src="${art.url(rel)}" alt="${esc(name)}"><figcaption>${esc(name)}</figcaption>`
    else fig.innerHTML = `<div class="silhouette"></div><figcaption>${esc(name)}</figcaption>`
    cast.append(fig)
  }
  highlight(speaking)
}

function highlight(name: string) {
  speaking = name
  document.querySelectorAll<HTMLElement>('#cast .actor').forEach(f => f.classList.toggle('speaking', !!name && f.dataset.name === name))
}

function drawMeters() {
  const box = $('#meters'); box.replaceChildren()
  for (const [key, m] of Object.entries(art.pack.meters || { 'player.hp': { label: 'HP', max: state.player_hp?.max || 10 } })) {
    const val = Number(vars[key] ?? (key === 'player.hp' ? state.player_hp?.current : NaN))
    if (Number.isNaN(val)) continue
    const max = key === 'player.hp' && state.player_hp?.max ? state.player_hp.max : m.max
    const el = document.createElement('div'); el.className = 'meter'
    el.innerHTML = `<span>${esc(m.label)}</span><i><b style="width:${Math.max(0, Math.min(100, (val / max) * 100))}%"></b></i><em>${val}</em>`
    box.append(el)
  }
  void reads.conditions().then(cs => { for (const c of cs) { const t = document.createElement('span'); t.className = 'cond'; t.textContent = c.name + (c.props.turns ? ` · ${c.props.turns}` : ''); box.append(t) } })
}

async function drawClues() {
  const clues = art.pack.clues || []
  const unlocked = clues.filter(c => Number(vars[c.when.var] ?? -1) >= c.when.gte)
  for (const c of unlocked) if (!found.has(c.id)) { found.add(c.id); await toastClue(c) }
  $('#clue-count').textContent = String(found.size)
  $('#clue-btn').hidden = !clues.length
  const grid = $('#clue-grid'); grid.replaceChildren()
  for (const c of clues) {
    const got = found.has(c.id), card = document.createElement('div'); card.className = `clue ${got ? '' : 'locked'}`
    const pic = got && await art.has(c.art) ? `<img src="${art.url(c.art)}" alt="">` : `<div class="clue-ph">${got ? '🔍' : '？'}</div>`
    card.innerHTML = `${pic}<b>${got ? esc(c.title) : '还没找到'}</b>${got && c.text ? `<p>${esc(c.text)}</p>` : ''}`
    grid.append(card)
  }
}

async function toastClue(c: Clue) {
  const t = $('#toast')
  t.innerHTML = `<span>获得线索</span><b>${esc(c.title)}</b>`
  t.hidden = false
  setTimeout(() => { t.hidden = true }, 2600)
}

// ── the dialogue: streamed prose in titled blocks, rolls lifted out ──────────────────────────────────────────────
function block(cls: string, who: string, text = '') {
  const el = document.createElement('div'); el.className = `line ${cls}`
  el.innerHTML = `<div class="who">${esc(who)}</div><div class="say"></div>`
  const body = el.querySelector('.say') as HTMLElement; body.textContent = text
  $('#log').append(el); scrollLog()
  return { el, body }
}
function narrate(text: string, who: string) { if (text) block('note', who, text) }
function scrollLog() { const l = $('#log'); if (l.scrollHeight - l.scrollTop - l.clientHeight < 140) l.scrollTop = l.scrollHeight }

function onChunk(raw: string, beat?: string) {
  const { who, text } = speaker(raw)
  if (!seg || seg.who !== who || seg.beat !== beat) {
    const div = beat && lastBeat && beat !== lastBeat ? kindOf(beat).divider_from?.[lastBeat] : undefined
    if (div) { const d = document.createElement('div'); d.className = 'divider'; d.textContent = div; $('#log').append(d) }
    if (beat) { lastBeat = beat; $('#beat').textContent = label(beat); $('#beat').className = `beat ${kindOf(beat).tone || ''}` }
    const tone = kindOf(beat).tone
    const title = who || kindOf(beat).live || (beat ? `主持 · ${label(beat)}` : '主持')
    seg = { ...block(who ? 'soul' : (tone === 'plan' || tone === 'res' ? tone : ''), title), who, beat, raw: '' }
    highlight(who)
  }
  seg.raw += text
  seg.raw = liftAway(seg.raw, seg.el)
  const { rolls, rest } = liftRolls(seg.raw)
  if (rolls.length) { dice.push(rolls); seg.raw = rest; for (const r of rolls) chip(seg.el, `${r.who} ${r.skill} ${r.roll}/${r.target} · ${r.outcome}`, r.good ? 'good' : 'bad') }
  seg.body.textContent = seg.raw.replace(/^\n+/, '')
  // a host line that quotes someone ("管家:「…」") lights that portrait
  if (!who) { const m = /(?:^|\n)([^\n:：「]{1,8})[:：]「[^」]*$/.exec(seg.raw); if (m && art.pack.speakers?.[m[1]]) highlight(m[1]) }
  scrollLog()
}

/** "// 异地 · 温妮 @ 门厅:…" — a character's turn somewhere else — folded into a small card under the block. */
const AWAY = /(?:^|\n)\/\/ ([^·\n]+) · ([^@\n]+?) @ ([^:：\n]+)[:：]([^\n]*)(?=\n|$)/g
function liftAway(raw: string, at: HTMLElement, final = false): string {
  return raw.replace(AWAY, (all, _tag, who, where, said, offset, whole) => {
    if (!final && offset + all.length >= whole.length) return all   // the line may still be arriving
    const d = document.createElement('details'); d.className = 'away'
    d.innerHTML = `<summary>✓ ${esc(who.trim())} <span>@ ${esc(where.trim())}</span></summary><p>${esc(said.trim())}</p>`
    at.append(d)
    return ''
  })
}

function chip(at: HTMLElement, text: string, cls = '') {
  let box = at.querySelector('.chips') as HTMLElement | null
  if (!box) { box = document.createElement('div'); box.className = 'chips'; at.append(box) }
  const c = document.createElement('span'); c.className = `chip ${cls}`; c.textContent = text; box.append(c)
}

function onBeat(ev: BeatEvent) {
  const at = seg?.el
  if (ev.kind === 'state.changed' && at) {
    for (const o of ((ev.applied as Record<string, unknown>[] | undefined) || []).slice(0, 6)) {
      if (o.var === 'time.clock') { clock = String(o.to ?? ''); continue }
      if (o.op === 'move_to' || !o.var) continue
      const m = art.pack.meters?.[String(o.var)]   // only what the player can read; plot stages show as clues
      if (!m) continue
      const delta = Number(o.to) - Number(o.from)
      chip(at, `${m.label} ${Number.isFinite(delta) ? (delta > 0 ? '+' : '') + delta : '→ ' + o.to}`, delta < 0 ? 'bad' : 'ok')
    }
  } else if (ev.kind === 'dice' && at) chip(at, `🎲 ${String(ev.request || '')} → ${String(ev.answer || '')}`)
}

async function onAsk(question: string, options: string[]): Promise<string | null> {
  const box = $('#choices'); box.replaceChildren()
  const q = document.createElement('div'); q.className = 'ask'; q.textContent = question; box.append(q)
  return new Promise(res => {
    for (const o of options) { const b = document.createElement('button'); b.textContent = o; b.onclick = () => { box.replaceChildren(); res(o) }; box.append(b) }
    if (!options.length) res(null)
  })
}

function hints() {
  $<HTMLInputElement>('#say').placeholder = startKind().placeholder || '说你想做什么'
  const s = $('#sugg'); s.replaceChildren()
  for (const c of startKind().chips || []) { const b = document.createElement('button'); b.type = 'button'; b.textContent = c; b.onclick = () => play(c); s.append(b) }
}

function choices(opts: string[]) {
  const box = $('#choices'); box.replaceChildren()
  for (const o of opts.flatMap(x => x.split('|')).map(x => x.trim()).filter(Boolean).slice(0, 4)) { const b = document.createElement('button'); b.textContent = o.replace(/^\d+[.、)]\s*/, ''); b.onclick = () => play(b.textContent || o); box.append(b) }
}

async function play(text: string) {
  text = text.trim(); if (!text || busy) return
  busy = true; document.body.classList.add('busy')
  $('#choices').replaceChildren(); $<HTMLInputElement>('#say').value = ''
  block('you', startKind().you ? `你 · ${startKind().you}` : '你', text)
  try {
    const r = await client.send(text)
    if (!r.success) narrate(`这一句没跑完:${r.error || '未知错误'}`, '')
    else if (!r.assistant_message && !seg) narrate('世界没有回应 —— 看一下主进程的日志(模型连得上吗?)', '')
    const opts = r.options?.length ? r.options : optionsIn(r.assistant_message || '')
    if (opts.length) choices(opts)
  } catch (err) { narrate(explain(err), '') }
  document.querySelectorAll<HTMLElement>('#log .line').forEach(el => {   // the turn is over: fold what was still open
    const body = el.querySelector('.say') as HTMLElement
    const t = liftAway(body.textContent || '', el, true); if (t !== body.textContent) body.textContent = t.replace(/\n+$/, '')
  })
  seg = null; busy = false; document.body.classList.remove('busy')
  highlight('')
  await refresh(); hints()
  $<HTMLInputElement>('#say').focus()
}

/** "你:① 一起搜 ② 去门厅问管家 ③ 去后院看泥印" / "1. … 2. …" at the end of the prose → choices */
function optionsIn(text: string): string[] {
  const circled = text.match(/[①②③④⑤]\s*[^①②③④⑤\n]+/g)
  if (circled?.length) return circled.map(s => s.replace(/^[①②③④⑤]\s*/, '').trim())
  const numbered = [...text.matchAll(/(?:^|\n)\s*\d+[.、]\s*([^\n]+)/g)].map(m => m[1].trim())
  return numbered.length >= 2 ? numbered : []
}

// ── map · clues · ending ─────────────────────────────────────────────────────────────────────────────────────────
async function openMap() {
  const m = art.pack.map, box = $('#map-body'); box.replaceChildren()
  const hasArt = await art.has(m?.art)
  box.style.backgroundImage = hasArt ? `url(${art.url(m?.art)})` : ''
  box.classList.toggle('drawn', !hasArt)
  if (!hasArt && m?.rooms) {   // no drawn map yet: the rooms joined by their doors
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 100 100'); svg.setAttribute('preserveAspectRatio', 'none'); svg.classList.add('links')
    for (const [a, b] of m.links || []) { const ra = m.rooms[a], rb = m.rooms[b]; if (!ra || !rb) continue
      const l = document.createElementNS('http://www.w3.org/2000/svg', 'line'); l.setAttribute('x1', String(ra.x)); l.setAttribute('y1', String(ra.y)); l.setAttribute('x2', String(rb.x)); l.setAttribute('y2', String(rb.y)); svg.append(l) }
    box.append(svg)
  }
  for (const [id, r] of Object.entries(m?.rooms || {})) {
    const b = document.createElement('button'); b.className = `room ${id === state.player_location ? 'here' : ''}`
    b.style.left = `${r.x}%`; b.style.top = `${r.y}%`
    b.innerHTML = `${esc(r.label)}${id === state.player_location ? '<small>你在这里</small>' : ''}`
    b.onclick = () => { $('#map').hidden = true; if (r.go && id !== state.player_location) play(r.go) }
    box.append(b)
  }
  $('#map').hidden = false
}

async function showEnding(s: NonNullable<Awaited<ReturnType<HostReads['settlement']>>>) {
  const id = s.exit?.id || ''
  const rel = art.pack.endings?.[id]
  $('#ending-art').style.backgroundImage = rel && await art.has(rel) ? `url(${art.url(rel)})` : ''
  $('#ending-kind').textContent = s.exit?.kind === 'ending' ? `结局 ${id}` : (s.exit?.kind === 'death' ? '你倒下了' : '理智崩溃')
  $('#ending-text').textContent = s.epilogue || ''
  $('#ending-truth').textContent = s.truth_reveal?.text || ''
  $('#ending-truth').hidden = !s.truth_reveal?.text
  $('#ending').hidden = false
}

// ── wiring ───────────────────────────────────────────────────────────────────────────────────────────────────────
$('#connect').addEventListener('submit', connect)
// dev convenience, like the Godot example's WL_TOKEN: `VITE_WL_TOKEN=… npm run dev` fills the token field
const devToken = (import.meta as { env?: Record<string, string> }).env?.VITE_WL_TOKEN
if (devToken) $<HTMLInputElement>('#token').value = devToken
$('#compose').addEventListener('submit', e => { e.preventDefault(); play($<HTMLInputElement>('#say').value) })
$('#stop').addEventListener('click', () => { client?.cancel().catch(err => narrate(explain(err), '')) })
$('#map-btn').addEventListener('click', openMap)
$('#clue-btn').addEventListener('click', () => { $('#clues').hidden = false })
document.querySelectorAll<HTMLElement>('[data-close]').forEach(b => b.addEventListener('click', () => { (b.closest('.overlay') as HTMLElement).hidden = true }))
$('#ending-back').addEventListener('click', () => { $('#ending').hidden = true; document.body.classList.remove('playing') })
void showTitle(new URLSearchParams(location.search).get('world') || 'pct-house')
