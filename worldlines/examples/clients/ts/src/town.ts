// 石津镇 · 雾退之夜 — the walkable pixel town (the same game as the Godot example's game/town/town.gd).
//
// The host owns the world (where you are, who is here, the time, whether a fight is on); this page draws it and turns
// what you do into a line you say. Walking, doorways and looking at things happen here first — the scene changes at
// once and the host hears about it as a beat in the background. Free words only exist inside an interaction: someone's
// ring, or the battle ring. Pictures come from the art pack (../art/stoneford-town/art.json).
import { type BeatEvent, type BeatKinds, type TurnResult, WorldLinesClient, speaker } from './client.ts'
import { type HostState, HostReads } from './host.ts'
import { Art } from './art.ts'

type V = { x: number; y: number }
type Face = 'down' | 'up' | 'left' | 'right'
interface Actor { who: string; x: number; y: number; face: Face; moving: boolean; sheet: HTMLImageElement | null; meta: any; color: string; hurt: number; down: boolean; follow?: boolean; kind: string; t: number }
interface Target { kind: 'npc' | 'spot' | 'exit'; at: V; who?: string; label?: string; says?: string; desc?: string; to?: string; actor?: Actor }

const VIEW = { w: 480, h: 270 }   // the stage, in the people's pixels
const UP = 4                      // drawn ×4: the scene at its full 1920×1080, the people as crisp ×4 pixels
const SPEED = 72, REACH = 30
const $ = <T extends HTMLElement = HTMLElement>(sel: string) => document.querySelector(sel) as T
const el = (tag: string, cls = '', text = '') => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e }
const v = (p: any, d: V = { x: 240, y: 220 }): V => (Array.isArray(p) && p.length >= 2 ? { x: +p[0], y: +p[1] } : d)
const dist = (a: V, b: V) => Math.hypot(a.x - b.x, a.y - b.y)
const now = () => performance.now() / 1000

let client: WorldLinesClient, reads: HostReads, art: Art, kinds: BeatKinds
let pack: any, meta: any = {}, layersByScene: Record<string, { img: string; base: number }[]> = {}
let state: HostState & Record<string, any> = {}
let vars: Record<string, any> = {}, specs: Record<string, any> = {}
let zoneId = '', zone: any = {}, walk: V[] = [], blocks: number[][] = []
let mask: ImageData | null = null
let bg: HTMLImageElement | null = null
let cut: { img: HTMLImageElement; base: number }[] = []
let player: Actor
let people: Actor[] = []
let target: Target | null = null
let moveTo: V | null = null, pending: Target | null = null
let busy = false, inBattle = false, ended = false
let mode: 'walk' | 'talk' | 'battle' = 'walk'
let talkWith: Target | null = null
const queue: { text: string; kind: 'bg' | 'talk'; wire: string }[] = []
let wordsFor: Record<string, string> | null = null   // what the words typed in a ring belong to: {kind, approach?, target}
// every interaction goes out as one line the host's interaction node takes (move · examine · talk · approach · encounter);
// its own graph judges, lands and settles it. Words typed in a fight go to the fight as they are.
const ix = (d: Record<string, unknown>, words = '') => `<interaction>${JSON.stringify(d)}</interaction>${words}`
let capUntil = 0
let lastBeat = '', lastBoard = false, lastOptions: string[] = []
let seg: { body: HTMLElement; who: string; beat: string; raw: string } | null = null
let foes: Record<string, { actor: Actor; name: string; hp: number; max: number }> = {}
let battleActors: Actor[] = []
const keys = new Set<string>()
const imgs = new Map<string, Promise<HTMLImageElement | null>>()
const shake = { t: 0 }

function image(rel?: string): Promise<HTMLImageElement | null> {
  const u = art.url(rel)
  if (!u) return Promise.resolve(null)
  if (!imgs.has(u)) imgs.set(u, new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = u }))
  return imgs.get(u)!
}

// ── start: take over the page from the title screen ─────────────────────────────────────────────────────────────
export async function startTown(c: WorldLinesClient, r: HostReads, a: Art, k: BeatKinds) {
  client = c; reads = r; art = a; kinds = k; pack = a.pack as any
  document.body.classList.add('town')
  document.title = `${pack.title || '石津镇'} · WorldLines`
  meta = await fetch(art.url('sprites/index.json')!).then(x => (x.ok ? x.json() : {})).catch(() => ({}))
  layersByScene = await fetch(art.url('scenes/layers.json')!).then(x => (x.ok ? x.json() : {})).catch(() => ({}))
  build()
  client.setHandlers({
    onChunk, onBeat, onAsk,
    onTurnStarted: () => { seg = null; lastBeat = ''; lastBoard = false },
    onConnection: (s, d) => { if (s === 'retrying') toast(`和主进程断开了,正在重连…(${d || ''})`, 'bad') },
  })
  await refresh()
  await enterZone(state.player_location || '', '')
  caption(pack.pitch || '')
  requestAnimationFrame(frame)
}

// ── the page ────────────────────────────────────────────────────────────────────────────────────────────────────
let cv: HTMLCanvasElement, ctx: CanvasRenderingContext2D, names: HTMLElement, prompt: HTMLElement, ring: HTMLElement
let dlg: HTMLElement, face: HTMLImageElement, beatTag: HTMLElement, lines: HTMLElement, opts: HTMLElement, compose: HTMLFormElement, input: HTMLInputElement
let bars: HTMLElement, pops: HTMLElement, banner: HTMLElement, fade: HTMLElement

function build() {
  const root = el('div'); root.id = 'town'
  root.innerHTML = `
    <canvas id="t-stage" width="1920" height="1080"></canvas>
    <div id="t-names"></div><div id="t-bars"></div><div id="t-pops"></div>
    <div id="t-hud" class="t-card"><b id="t-place"></b><span id="t-time"></span><span id="t-fog"></span></div>
    <div id="t-goals" class="t-card"><small>出北门之前</small><div id="t-goal-list"></div><div id="t-meters"></div></div>
    <div id="t-keys">WASD / 点地面 走 · E 互动 · M 地图 · H 记录 · Esc 离开</div>
    <div id="t-prompt" hidden></div>
    <section id="t-dlg" hidden>
      <img id="t-face" alt="">
      <div class="t-mid"><div id="t-beat"></div><div id="t-lines"></div>
        <form id="t-compose" hidden><input id="t-say" autocomplete="off"><button>说</button></form></div>
      <div id="t-opts"></div>
    </section>
    <div id="t-ring" hidden></div>
    <div id="t-banner"></div>
    <div id="t-log" class="overlay" hidden><div class="sheet"><button class="x" data-close>×</button><h2>记录</h2><div id="t-log-body"></div></div></div>
    <div id="t-map" class="overlay" hidden></div>
    <div id="t-fade"></div>`
  document.body.append(root)
  cv = $('#t-stage'); ctx = cv.getContext('2d')!; ctx.imageSmoothingEnabled = false
  names = $('#t-names'); prompt = $('#t-prompt'); ring = $('#t-ring'); dlg = $('#t-dlg'); face = $('#t-face') as HTMLImageElement
  beatTag = $('#t-beat'); lines = $('#t-lines'); opts = $('#t-opts'); compose = $('#t-compose') as HTMLFormElement; input = $('#t-say') as HTMLInputElement
  bars = $('#t-bars'); pops = $('#t-pops'); banner = $('#t-banner'); fade = $('#t-fade')
  compose.addEventListener('submit', e => { e.preventDefault(); const t = input.value; hideInput(); enqueue(t, 'talk', inBattle || !wordsFor ? t : ix(wordsFor, t)) })
  document.querySelectorAll('#town [data-close]').forEach(b => b.addEventListener('click', () => (b.closest('.overlay') as HTMLElement).hidden = true))
  cv.addEventListener('click', onClick)
  addEventListener('keydown', onKey)
  addEventListener('keyup', e => keys.delete(e.key.toLowerCase()))
  addEventListener('resize', placeDom)
}

// ── reading the host ────────────────────────────────────────────────────────────────────────────────────────────
async function refresh() {
  const [s, sc] = await Promise.all([reads.state(), reads.schema()])
  if (s) state = s as any
  vars = {}; specs = {}
  for (const x of sc) { vars[x.name] = x.value; specs[x.name] = x }
  drawHud()
}

const minutes = (day: number, clock: string) => { const [h, m] = clock.split(':').map(Number); return (day - 1) * 1440 + (h || 0) * 60 + (m || 0) }

function drawHud() {
  const here = state.player_location || zoneId
  $('#t-place').textContent = zoneOf(here).name || state.places?.[here] || here
  const day = Number(vars['time.day'] ?? 1), clock = String(vars['time.clock'] ?? '')
  $('#t-time').textContent = `第 ${day} 天 · ${clock}`
  const fog = pack.fog
  if (fog && clock.includes(':')) {
    const left = minutes(fog.day, fog.clock) - minutes(day, clock)
    $('#t-fog').textContent = left > 0 ? `离${fog.label || '雾退'}还有 ${Math.floor(left / 60)} 小时 ${String(left % 60).padStart(2, '0')} 分` : '雾退开了 —— 北路能走'
  }
  $('#t-goal-list').innerHTML = (pack.goals || []).map((g: any) => {
    const ok = Number(vars[g.var] ?? 0) >= 1
    return `<div class="${ok ? 'ok' : ''}">${ok ? '✓' : '○'}&nbsp; ${g.label}</div>`
  }).join('')
  $('#t-meters').innerHTML = (pack.meters || []).filter((m: any) => vars[m.var] != null)
    .map((m: any) => `<span>${m.label} ${vars[m.var]}${specs[m.var]?.max != null ? '/' + specs[m.var].max : ''}</span>`).join('')
}

function zoneOf(id: string): any {
  const zs = pack.zones || {}
  if (zs[id]) return zs[id]
  const tail = id.split('/').pop()
  for (const k in zs) if (k.split('/').pop() === tail) return zs[k]
  return {}
}
const sameZone = (a: string, b: string) => a === b || a.split('/').pop() === b.split('/').pop()

function canon(name: string): string {
  const n = pack.speakers?.[name] || name
  for (const k in pack.people || {}) if (n.startsWith(k)) return k
  return n
}
const personOf = (name: string): any => pack.people?.[canon(name)] || {}

// ── the town on screen ──────────────────────────────────────────────────────────────────────────────────────────
async function enterZone(id: string, from: string) {
  fade.classList.add('on'); await new Promise(r => setTimeout(r, 180))
  zoneId = id; zone = zoneOf(id); moveTo = null; pending = null; target = null
  if (!zone.name) zone = { name: state.places?.[id] || id, walk: [[40, 150], [440, 150], [440, 260], [40, 260]], exits: [], npcs: [], spawn: [240, 220] }
  bg = await image(zone.scene)
  walk = (zone.walk || []).map((p: any) => v(p)); blocks = zone.block || []
  const sceneFile: string = zone.scene || ''
  const m = await image(zone.mask || sceneFile.replace(/\.(png|jpg)$/, '') + '-walk.png')
  mask = null
  if (m) { const c = document.createElement('canvas'); c.width = m.width; c.height = m.height; const x = c.getContext('2d')!; x.drawImage(m, 0, 0); mask = x.getImageData(0, 0, m.width, m.height) }
  const key = sceneFile.split('/').pop()!.replace(/\.(png|jpg)$/, '')
  cut = []
  for (const l of zone.layers || layersByScene[key] || []) { const im = await image(l.img); if (im) cut.push({ img: im, base: l.base }) }
  let spawn = v(zone.spawn)
  for (const e of zone.exits || []) if (from && sameZone(e.to, from)) { const a = v(e.at), b = v(zone.spawn); spawn = { x: a.x + (b.x - a.x) * 0.3, y: a.y + (b.y - a.y) * 0.3 } }
  people = []
  player = await actor(pack.player || '旅人', spawn, 'player')
  player.face = spawn.y > 200 ? 'up' : 'down'
  for (const n of zone.npcs || []) {
    const a = await actor(n.who, v(n.at), (personOf(n.who).tags || []).includes('mob') ? 'mob' : 'npc')
    a.face = n.face || 'down'; people.push(a)
  }
  await placeSouls()
  drawHud(); buildNames()
  fade.classList.remove('on')
}

async function placeSouls() {
  const free: any[] = zone.free || [[260, 210]]
  let i = 0
  for (const s of state.souls || []) {
    const who = canon(s.name || '')
    const follows = followsFlag(who)
    if (!follows && !sameZone(s.location || '', zoneId)) continue
    if (people.some(p => p.who === who)) continue
    const at = follows ? { x: player.x - 22, y: player.y + 6 } : v(free[i++ % free.length])
    const a = await actor(who, at, 'soul'); a.follow = follows; people.push(a)
  }
}

function followsFlag(who: string): boolean {
  const f = pack.follow?.[who]
  return !!(f && vars['flag.' + f.flag])
}

async function actor(who: string, at: V, kind: string): Promise<Actor> {
  const p = personOf(who)
  const sheet = p.sprite ? await image(`sprites/${p.sprite}.png`) : null
  return { who, x: at.x, y: at.y, face: 'down', moving: false, sheet, meta: meta[p.sprite] || {}, color: p.color || '#8aa07a', hurt: 0, down: false, kind, t: Math.random() * 3 }
}

const depth = (a: Actor) => Math.min(1, Math.max(0.68, 0.72 + 0.28 * (a.y - 110) / 150))

function canStand(p: V): boolean {
  if (mask) {
    const x = Math.floor(p.x * mask.width / VIEW.w), y = Math.floor(p.y * mask.height / VIEW.h)
    if (x < 0 || y < 0 || x >= mask.width || y >= mask.height || mask.data[(y * mask.width + x) * 4] < 128) return false
  } else if (walk.length >= 3 && !inside(p, walk)) return false
  return !blocks.some(b => dist(p, { x: b[0], y: b[1] }) < b[2])
}

function inside(p: V, poly: V[]): boolean {
  let c = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++)
    if ((poly[i].y > p.y) !== (poly[j].y > p.y) && p.x < (poly[j].x - poly[i].x) * (p.y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x) c = !c
  return c
}

// stage ↔ page
function k(): { s: number; ox: number; oy: number } {
  const r = cv.getBoundingClientRect()
  const s = Math.min(r.width / VIEW.w, r.height / VIEW.h)
  return { s, ox: r.left + (r.width - VIEW.w * s) / 2, oy: r.top + (r.height - VIEW.h * s) / 2 }
}
const toScreen = (p: V) => { const q = k(); return { x: q.ox + p.x * q.s, y: q.oy + p.y * q.s } }
const toWorld = (x: number, y: number) => { const q = k(); return { x: (x - q.ox) / q.s, y: (y - q.oy) / q.s } }

// ── the frame: walk, draw, place the labels ─────────────────────────────────────────────────────────────────────
let last = now()
function frame() {
  const t = now(), dt = Math.min(0.05, t - last); last = t
  if (player && !inBattle) step(dt)
  draw(dt)
  placeDom()
  requestAnimationFrame(frame)
}

const typing = () => document.activeElement === input || !ring.hidden || !$('#t-map').hidden || !$('#t-log').hidden

function step(dt: number) {
  let dx = 0, dy = 0
  if (!typing()) {
    dx = +(keys.has('d') || keys.has('arrowright')) - +(keys.has('a') || keys.has('arrowleft'))
    dy = +(keys.has('s') || keys.has('arrowdown')) - +(keys.has('w') || keys.has('arrowup'))
  }
  if (dx || dy) { moveTo = null; pending = null }
  else if (moveTo) { const ddx = moveTo.x - player.x, ddy = moveTo.y - player.y; if (Math.hypot(ddx, ddy) < 2) moveTo = null; else { dx = ddx; dy = ddy } }
  player.moving = !!(dx || dy)
  if (player.moving) {
    const l = Math.hypot(dx, dy), sx = dx / l * SPEED * dt, sy = dy / l * SPEED * dt
    for (const [ax, ay] of [[sx, sy], [sx, 0], [0, sy]]) if (canStand({ x: player.x + ax, y: player.y + ay })) { player.x += ax; player.y += ay; break }
    player.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up')
  }
  for (const a of people) if (a.follow) {
    const gx = player.x - a.x, gy = player.y - a.y, g = Math.hypot(gx, gy)
    a.moving = g > 24
    if (a.moving) { a.x += gx / g * SPEED * 0.95 * dt; a.y += gy / g * SPEED * 0.95 * dt; a.face = Math.abs(gx) > Math.abs(gy) ? (gx > 0 ? 'right' : 'left') : (gy > 0 ? 'down' : 'up') }
  }
  if (pending && dist(player, pending.at) < REACH) { const p = pending; pending = null; moveTo = null; interact(p) }
  pickTarget()
  if (mode === 'talk' && talkWith && dist(player, talkWith.at) > 56 && !busy) endTalk()
  if (mode === 'walk' && !dlg.hidden && !busy && !queue.length && now() > capUntil) dlg.hidden = true
}

function pickTarget() {
  let best: Target | null = null, bd = REACH
  for (const a of people) { const d = dist(player, a); if (d < bd && !a.follow) { bd = d; best = { kind: 'npc', who: a.who, at: { x: a.x, y: a.y }, actor: a } } }
  for (const s of zone.spots || []) { const d = dist(player, v(s.at)); if (d < bd + 6) { bd = d; best = { kind: 'spot', label: s.label, says: s.says, desc: s.desc, at: v(s.at) } } }
  for (const e of zone.exits || []) { const d = dist(player, v(e.at)); if (d < bd) { bd = d; best = { kind: 'exit', to: e.to, label: e.label, says: e.says, at: v(e.at) } } }
  target = best
  if (!best || busy || typing() || inBattle) { prompt.hidden = true; return }
  prompt.textContent = best.kind === 'npc' ? `E · 和${best.who}……` : best.kind === 'spot' ? `E · ${best.label}` : `E · 前往 ${best.label}`
  prompt.hidden = false
  const p = toScreen(best.at)
  prompt.style.left = `${p.x - prompt.offsetWidth / 2}px`; prompt.style.top = `${p.y - 80}px`
}

function draw(dt: number) {
  ctx.save()
  ctx.setTransform(UP, 0, 0, UP, 0, 0); ctx.imageSmoothingEnabled = false
  if (shake.t > 0) { shake.t -= dt; ctx.translate(Math.round(Math.random() * 6 - 3), Math.round(Math.random() * 4 - 2)) }
  ctx.fillStyle = '#1b2230'; ctx.fillRect(0, 0, VIEW.w, VIEW.h)
  if (bg) ctx.drawImage(bg, 0, 0, VIEW.w, VIEW.h)
  else { ctx.fillStyle = '#2c3a4a'; ctx.beginPath(); walk.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.fill() }
  if (!inBattle) for (const e of zone.exits || []) {   // doorways glow a little, so you can see where the street goes
    const a = v(e.at); ctx.fillStyle = 'rgba(255,204,115,.16)'; ctx.beginPath(); ctx.arc(a.x, a.y, 9, 0, 7); ctx.fill()
    ctx.fillStyle = 'rgba(255,217,140,.45)'; ctx.beginPath(); ctx.arc(a.x, a.y, 4, 0, 7); ctx.fill()
  }
  // people and the scene's cut-outs, back to front: you walk behind a lamp post whose base is nearer than your feet
  const items: { y: number; draw: () => void }[] = []
  for (const a of inBattle ? battleActors : [player, ...people]) if (a) items.push({ y: a.y, draw: () => drawActor(a, dt) })
  if (!inBattle) for (const c of cut) items.push({ y: c.base, draw: () => ctx.drawImage(c.img, 0, 0, VIEW.w, VIEW.h) })
  items.sort((a, b) => a.y - b.y).forEach(i => i.draw())
  ctx.restore()
}

function drawActor(a: Actor, dt: number) {
  a.t += dt; a.hurt = Math.max(0, a.hurt - dt)
  const s = inBattle ? 1 : depth(a)
  ctx.save(); ctx.translate(Math.round(a.x), Math.round(a.y)); ctx.scale(s, s)
  ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.beginPath(); ctx.ellipse(0, 0, 11, 3.5, 0, 0, 7); ctx.fill()
  const bob = a.moving ? -Math.abs(Math.sin(a.t * 11)) * 1.5 : Math.sin(a.t * 1.8) * 0.4
  if (a.hurt > 0 && Math.floor(a.hurt * 20) % 2 === 0) ctx.filter = 'sepia(1) saturate(6) hue-rotate(-40deg)'
  else if (a.down) ctx.filter = 'grayscale(1) brightness(.7)'
  const f = a.meta.frame || 64, foot = a.meta.foot ?? 60
  if (a.sheet) {
    const col = ({ down: 0, right: 1, left: 1, up: 2 } as const)[a.face]
    if (a.down) ctx.rotate(a.face === 'left' ? -Math.PI / 2 : Math.PI / 2)
    if (a.face === 'left') ctx.scale(-1, 1)
    ctx.drawImage(a.sheet, col * f, 0, f, f, -f / 2, -foot + (a.down ? 0 : bob), f, f)
  } else {
    const h = a.down ? 14 : 40
    ctx.fillStyle = a.color; ctx.fillRect(-8, -h + 10 + bob, 16, h - 10)
    ctx.beginPath(); ctx.arc(0, -h + 6 + bob, 7, 0, 7); ctx.fill()
    ctx.fillStyle = '#111'; ctx.font = '10px sans-serif'; ctx.fillText(a.who.slice(0, 1), -5, -h + 10 + bob)
  }
  ctx.restore()
}

function buildNames() {
  names.innerHTML = ''
  for (const a of people) { const l = el('div', 't-name', a.who); (l as any).actor = a; names.append(l) }
  for (const e of zone.exits || []) { const l = el('div', 't-exit', '› ' + e.label); (l as any).at = v(e.at); names.append(l) }
}

function placeDom() {
  if (!cv) return
  for (const l of Array.from(names.children) as any[]) {
    l.hidden = inBattle
    if (l.at) { const p = toScreen(l.at); l.style.left = `${p.x - l.offsetWidth / 2}px`; l.style.top = `${p.y + 10}px`; continue }
    const a: Actor = l.actor, h = ((a.meta.foot ?? 60) - (a.meta.top ?? 6)) * depth(a)
    const p = toScreen({ x: a.x, y: a.y - h - 4 }); l.style.left = `${p.x - l.offsetWidth / 2}px`; l.style.top = `${p.y - 20}px`
  }
  for (const b of Array.from(bars.children) as any[]) { const p = toScreen({ x: b.actor.x, y: b.actor.y + 6 }); b.style.left = `${p.x - 75}px`; b.style.top = `${p.y}px` }
}

// ── input ───────────────────────────────────────────────────────────────────────────────────────────────────────
function onClick(e: MouseEvent) {
  if (!ring.hidden) { closeRing(); return }
  if (inBattle) { battleRing(); return }
  const w = toWorld(e.clientX, e.clientY)
  for (const a of people) {
    const h = ((a.meta.foot ?? 60) - (a.meta.top ?? 6)) * depth(a)
    if (w.x > a.x - 12 && w.x < a.x + 12 && w.y > a.y - h && w.y < a.y + 2) { pending = { kind: 'npc', who: a.who, at: { x: a.x, y: a.y }, actor: a }; moveTo = nearestStand({ x: a.x, y: a.y }); return }
  }
  for (const x of zone.exits || []) if (dist(w, v(x.at)) < 14) { pending = { kind: 'exit', to: x.to, label: x.label, says: x.says, at: v(x.at) }; moveTo = nearestStand(v(x.at)); return }
  moveTo = nearestStand(w)
}

function nearestStand(p: V): V {
  if (canStand(p)) return p
  for (let i = 0; i < 24; i++) { const q = { x: p.x + (player.x - p.x) * i / 24, y: p.y + (player.y - p.y) * i / 24 }; if (canStand(q)) return q }
  return { x: player.x, y: player.y }
}

function onKey(e: KeyboardEvent) {
  const key = e.key.toLowerCase()
  if (document.activeElement === input) { if (key === 'escape') hideInput(); return }
  keys.add(key)
  if (key === 'escape') {
    if (!ring.hidden) closeRing()
    else if (!$('#t-map').hidden || !$('#t-log').hidden) { $('#t-map').hidden = true; $('#t-log').hidden = true }
    else if (mode === 'talk') endTalk()
    return
  }
  if (!ring.hidden && /^[1-9]$/.test(key)) { (ring.querySelector(`[data-n="${key}"]`) as HTMLButtonElement)?.click(); return }
  if (key === 'e' || key === ' ') {
    e.preventDefault()
    if (inBattle) battleRing()
    else if (mode === 'talk' && talkWith) openRing(talkWith)
    else if (target) interact(target)
  } else if (key === 'm') openMap()
  else if (key === 'h' || key === 'l') $('#t-log').hidden = !$('#t-log').hidden
}

async function interact(t: Target) {
  if (t.kind === 'exit') {   // the scene changes now; the host hears about it as a beat in the background
    const name = zoneOf(t.to!).name || t.label
    if (zoneOf(t.to!).name) await enterZone(t.to!, zoneId)
    enqueue(t.says || `我去${name}。`, 'bg', ix({ kind: 'move', to: t.to }))
  } else if (t.kind === 'spot') {
    if (t.desc) caption(t.desc)
    enqueue(t.says || '', 'bg', ix({ kind: 'examine', what: t.label || '', says: t.says || '' }))
  } else {
    player.face = faceTo(player, t.at)
    openRing(t)
  }
}
const faceTo = (a: V, b: V): Face => (Math.abs(b.x - a.x) > Math.abs(b.y - a.y) ? (b.x > a.x ? 'right' : 'left') : (b.y > a.y ? 'down' : 'up'))

// ── rings: approaches are suggestions, not commands; 自己说 lives only here ─────────────────────────────────────
function openRing(t: Target) {
  const who = t.who!, tags: string[] = personOf(who).tags || []
  const list = (pack.approaches || []).filter((a: any) => (!a.when || tags.includes(a.when)) && (!tags.includes('mob') || ['talk', 'persuade', 'fight'].includes(a.id)))
    .map((a: any) => ({ ...a, who }))
  showRing(who, toScreen({ x: t.at.x, y: t.at.y - 24 }), list, t)
}

function battleRing() {
  if (busy || !inBattle) return
  const me = battleActors[0]
  showRing('你的行动', toScreen({ x: me?.x ?? 140, y: (me?.y ?? 172) - 30 }), (pack.battle?.commands || []).map((c: any) => ({ ...c, battle: true })), null)
}

function showRing(head: string, c: V, list: any[], t: Target | null) {
  ring.innerHTML = ''
  const x = Math.min(Math.max(c.x, 220), innerWidth - 220), y = Math.min(Math.max(c.y, 200), innerHeight - 340), r = 150
  list.forEach((a, i) => {
    const ang = -Math.PI / 2 + 2 * Math.PI * i / list.length
    const b = el('button', 't-opt') as HTMLButtonElement; b.dataset.n = String(i + 1)
    b.innerHTML = `${a.icon ? `<img src="${art.url(a.icon)}" alt="">` : ''}<span>${i + 1} ${a.label}</span>`
    b.style.left = `${x + Math.cos(ang) * r - 54}px`; b.style.top = `${y + Math.sin(ang) * r - (a.icon ? 46 : 26)}px`
    b.onclick = e => { e.stopPropagation(); pick(a, t) }
    ring.append(b)
  })
  const own = el('button', 't-own', '自己说……') as HTMLButtonElement
  own.style.left = `${x - 60}px`; own.style.top = `${y - 20}px`; own.onclick = e => { e.stopPropagation(); ownWords(t) }
  const h = el('div', 't-ring-head', head); h.style.left = `${x - 80}px`; h.style.top = `${y - r - 90}px`
  ring.append(own, h)
  ring.onclick = () => closeRing()
  ring.hidden = false; prompt.hidden = true
}
function closeRing() { ring.hidden = true; ring.innerHTML = '' }

function pick(a: any, t: Target | null) {
  closeRing()
  if (a.battle) { command(a); return }
  startTalk(t)
  const aid: string = a.id || 'talk'
  wordsFor = aid === 'talk' ? { kind: 'talk', target: a.who } : { kind: 'approach', approach: aid, target: a.who }
  if (aid === 'fight') {
    wordsFor = null
    const line = a.says.replace('{who}', a.who)
    confirmLine(a.confirm, line, ix({ kind: 'encounter', roster: `${a.who}×1` }, line)); return
  }
  if (a.prefill) { askWords(a.prefill.replace('{who}', a.who)); return }
  const line = a.says.replace('{who}', a.who)
  enqueue(line, 'talk', ix(wordsFor, line))
}

function startTalk(t: Target | null) {
  if (!t || inBattle) return
  mode = 'talk'; talkWith = t
  setFace(t.who!)
  boxMode('talk')
}
function endTalk() { mode = 'walk'; talkWith = null; hideInput(); dlg.hidden = true }
function ownWords(t: Target | null) { closeRing(); startTalk(t); wordsFor = t ? { kind: 'talk', target: t.who! } : null; askWords('') }
function askWords(text: string) { boxMode('talk'); compose.hidden = false; input.value = text; input.focus(); input.setSelectionRange(text.length, text.length) }
function hideInput() { input.blur(); compose.hidden = true }

function confirmLine(question: string, line: string, wire = '') {
  boxMode('talk'); opts.innerHTML = ''
  opts.append(el('div', 't-warn', question))
  const yes = el('button', '', '›  动手'); yes.onclick = () => enqueue(line, 'talk', wire)
  const no = el('button', '', '›  算了'); no.onclick = () => showOptions(lastOptions)
  opts.append(yes, no)
}

function boxMode(kind: 'caption' | 'talk') {
  dlg.hidden = false
  dlg.classList.toggle('caption', kind === 'caption')
  dlg.classList.toggle('battle', inBattle)
}

// ── turns: one at a time, in order; walking never waits for them ───────────────────────────────────────────────
function enqueue(text: string, kind: 'bg' | 'talk', wire = '') {
  text = text.trim()
  if (!text || ended) return
  queue.push({ text, kind, wire: wire || text })
  if (!busy) runQueue()
}
async function runQueue() { while (queue.length && !ended) { const q = queue.shift()!; await turn(q.text, q.kind, q.wire) } }
const say = (text: string) => (mode === 'talk' && wordsFor && !inBattle ? enqueue(text, 'talk', ix(wordsFor, text)) : enqueue(text, mode === 'walk' && !inBattle ? 'bg' : 'talk'))

function caption(text: string) {
  if (!text) return
  if (mode === 'walk' && !inBattle) { lines.innerHTML = ''; boxMode('caption') }
  line('', text, 'note'); capUntil = now() + 6
}

async function turn(text: string, kind: 'bg' | 'talk', wire: string) {
  busy = true; prompt.hidden = true
  const talk = kind === 'talk' || inBattle
  boxMode(talk ? 'talk' : 'caption')
  opts.innerHTML = ''; lines.innerHTML = ''; lastOptions = []
  line('你', text, 'you')
  let r: TurnResult
  try { r = await client.send(wire || text) } catch (e) { r = { success: false, error: String((e as Error).message || e) } }
  if (!r.success) line('', `这一句没跑完:${r.error || '未知错误'}`, 'note')
  else if (!r.assistant_message && !seg) line('', '世界没有回应 —— 看一下主进程的日志(模型连得上吗?)', 'note')
  let o = r.options?.length ? r.options : lastOptions
  if (!o.length) o = [...(r.assistant_message || '').matchAll(/[①②③④⑤]\s*([^①②③④⑤\n]+)/g)].map(m => m[1].trim())
  seg = null
  await afterTurn()   // the host's word on where you are lands before anything else can be done
  busy = false
  showOptions(o)
  capUntil = now() + 9
  if (inBattle && !queue.length) battleRing()
}

async function afterTurn() {
  await refresh()
  const here = state.player_location || zoneId
  const fighting = foeIds().length > 0
  if (fighting && !inBattle) await battleBegin()
  else if (inBattle && !fighting) await battleEnd()
  else if (inBattle) await battleSync()
  // the host has the last word on where you are — once nothing else is on its way
  if (!inBattle && !queue.length && here && !sameZone(here, zoneId)) { toast(`(${zoneOf(here).name || here})`); await enterZone(here, zoneId) }
  else if (!inBattle) { await placeSouls(); buildNames() }
  const s = await reads.settlement()
  if (s) showEnding(s)
}

function showOptions(list: string[]) {
  opts.innerHTML = ''; lastOptions = list
  let shown = 0
  for (const o of list) for (const part of o.split('|')) {
    const label = part.trim()
    if (!label || shown >= 4) continue
    shown++
    const b = el('button', '', '›  ' + label); b.onclick = () => say(label); opts.append(b)
  }
  const kd: any = kinds.kinds[lastBeat] || kinds.kinds[kinds.start || ''] || {}
  const chips: string[] = [...(kd.chips || []), ...(lastBoard ? kd.chips_when_board || [] : [])]
  if (chips.length) { const f = el('div', 't-chips'); for (const c of chips) { const b = el('button', c === '定' ? 'go' : '', c); b.onclick = () => say(c); f.append(b) } opts.append(f) }
  if (mode === 'talk' && talkWith) { const t = talkWith; const m = el('button', 'more', '…… 还想做点别的(E)'); m.onclick = () => openRing(t); opts.append(m) }
  input.placeholder = kd.placeholder || '说你想做什么'
}

function onChunk(raw: string, beat?: string) {
  const { who, text } = speaker(raw)
  const b = beat || ''
  if (!seg || seg.who !== who || seg.beat !== b) {
    const kd: any = kinds.kinds[b] || {}
    if (b && lastBeat && b !== lastBeat && kd.divider_from?.[lastBeat]) lines.append(el('div', 't-div', `—— ${kd.divider_from[lastBeat]} ——`))
    if (b) { lastBeat = b; beatTag.textContent = kd.live || kd.label || b; beatTag.className = kd.tone || '' }
    const name = who ? canon(who) : ''
    seg = { body: line(name || String(kd.host || '主持').split(' · ')[0], '', who ? 'who' : kd.tone || 'host'), who, beat: b, raw: '' }
    if (name) setFace(name)
  }
  seg.raw += text
  seg.raw = seg.raw.replace(/(?:^|\n)\/\/ ([^·\n]+) · ([^@\n]+?) @ ([^:：\n]+)[:：]([^\n]*)\n/g, (_m, _k, w, at, said) => { line('', `✓ ${w.trim()} @ ${at.trim()}:${said.trim()}`, 'note'); return '\n' })
  seg.body.textContent = seg.raw.trim()
  if (!who) {   // the host quoting someone — 卡斯:「…」 — lights them up
    const ms = [...seg.raw.matchAll(/(?:^|\n|。)([^\n:：「。,,]{1,10})[:：]?「/g)]
    const n = ms.length ? ms[ms.length - 1][1] : ''
    if (n && personOf(n).color) setFace(canon(n))
  }
  lines.scrollTop = lines.scrollHeight
}

function setFace(name: string) {
  const p = personOf(name)
  if (p.portrait) { face.src = art.url(p.portrait)!; face.hidden = false }
  const a = people.find(x => x.who === name)
  if (a && !inBattle) a.face = faceTo(a, player)
}

function line(who: string, text: string, cls: string): HTMLElement {
  const box = el('div', `t-line ${cls}`)
  if (who) box.append(el('div', 't-who', who))
  const body = el('div', 't-body', text); box.append(body)
  lines.append(box); lines.scrollTop = lines.scrollHeight
  const copy = box.cloneNode(true) as HTMLElement; $('#t-log-body').append(copy)
  new MutationObserver(() => { (copy.lastChild as HTMLElement).textContent = body.textContent }).observe(body, { childList: true, characterData: true, subtree: true })
  return body
}

function onBeat(ev: BeatEvent) {
  if (ev.kind === 'plan.beat') lastBoard = !!ev.board && Object.keys(ev.board as object).length > 0
  else if (ev.kind === 'resolve.beat' && Array.isArray(ev.options) && ev.options.length) lastOptions = ev.options as string[]
  else if (ev.kind === 'dice') rollDie(ev)
  else if (ev.kind === 'node.enter' && ev.node === 'combat' && !inBattle) refresh().then(battleBegin)
  else if (ev.kind === 'state.changed') for (const o of (ev.applied as any[]) || []) if (o && o.var) changed(o.var, o.from, o.to)
}

function changed(name: string, from: any, to: any) {
  if (typeof from !== 'number' || typeof to !== 'number') return
  const d = to - from; vars[name] = to
  const m = /^foe\.(.+)\.hp$/.exec(name)
  if (m && foes[m[1]]) { pop(foes[m[1]].actor, d); battleSync(); return }
  if (name === 'player.hp') { pop(inBattle ? battleActors[0] : player, d); return }
  for (const g of pack.goals || []) if (g.var === name && d > 0) toast(`✓ ${g.label}`, 'ok')
  for (const mt of pack.meters || []) if (mt.var === name && name !== 'player.hp') toast(`${mt.label} ${d > 0 ? '+' : ''}${d}`, d > 0 ? 'ok' : 'bad')
}

async function onAsk(question: string, options: string[]): Promise<string | null> {
  boxMode('talk'); opts.innerHTML = ''
  opts.append(el('div', 't-warn', question))
  return new Promise(res => { for (const o of options) { const b = el('button', '', '›  ' + o); b.onclick = () => { opts.innerHTML = ''; res(o) }; opts.append(b) } })
}

// ── the fight: the host narrates; the numbers are the combat layer's variables (foe.<id>.hp) ───────────────────
const foeIds = () => Object.keys(vars).filter(n => /^foe\..+\.hp$/.test(n)).map(n => n.slice(4, -3))
const foeName = (id: string) => String(specs[`foe.${id}.hp`]?.doc || id).split(' hp')[0]

async function battleBegin() {
  inBattle = true; mode = 'battle'; talkWith = null; moveTo = null; pending = null; prompt.hidden = true
  bg = await image(zone.battle || pack.battle?.default_scene)
  battleActors = []; foes = {}
  const me = await actor(pack.player || '旅人', { x: 140, y: 172 }, 'player'); me.face = 'right'; battleActors.push(me)
  let row = 0
  for (const p of people) if (p.kind === 'soul') { const a = await actor(p.who, { x: 100, y: 140 + row++ * 44 }, 'soul'); a.face = 'right'; battleActors.push(a) }
  await battleSync()
  boxMode('talk'); banner_('战斗开始')
  setTimeout(battleRing, 1200)
}

async function battleSync() {
  const slots = [[345, 150], [405, 172], [330, 192], [420, 128], [385, 205], [300, 160]]
  const ids = foeIds()
  for (let i = 0; i < ids.length; i++) {
    const id = ids[i]
    if (!foes[id]) {
      const name = foeName(id)
      const f = (pack.battle?.foes || []).find((x: any) => !x.match || name.includes(x.match))
      const a = await actor(name, v(slots[i % slots.length]), 'foe')
      const sheet = await image(`sprites/${f?.sprite || 'bandit'}.png`); a.sheet = sheet; a.meta = meta[f?.sprite || 'bandit'] || {}; a.face = 'left'
      battleActors.push(a); foes[id] = { actor: a, name, hp: 0, max: 0 }
    }
    const hp = Number(vars[`foe.${id}.hp`] ?? 0), mx = specs[`foe.${id}.hp`]?.max
    foes[id].hp = hp; foes[id].max = mx != null ? Number(mx) : Math.max(hp, foes[id].max); foes[id].actor.down = hp <= 0
  }
  bars.innerHTML = ''
  for (const id in foes) {
    const f = foes[id], b = el('div', 't-bar') as any; b.actor = f.actor
    b.innerHTML = `<span>${f.name}  ${f.hp}/${f.max}</span><i style="width:${Math.max(0, f.hp) / Math.max(1, f.max) * 100}%"></i>`
    bars.append(b)
  }
  const meB = el('div', 't-bar me') as any; meB.actor = battleActors[0]
  meB.innerHTML = `<span>你  生命 ${vars['player.hp'] ?? '?'}/${specs['player.hp']?.max ?? '?'}</span>`; bars.append(meB)
}

function command(c: any) {
  if (c.prefill) { askWords(c.prefill); return }
  let text: string = c.says || ''
  if (c.target) {
    const alive = Object.keys(foes).filter(id => foes[id].hp > 0)
    if (alive.length > 1) {   // which one: a small ring of the foes still standing
      const a0 = foes[alive[0]].actor
      showRing('对谁?', toScreen({ x: a0.x, y: a0.y - 30 }), alive.map(id => ({ label: foes[id].name, says: text.replace('{target}', foes[id].name), battle: true })), null)
      return
    }
    text = text.replace('{target}', alive.length ? foes[alive[0]].name : '对方')
  }
  enqueue(text, 'talk')
}

async function battleEnd() {
  banner_('战斗结束')
  await new Promise(r => setTimeout(r, 1300))
  inBattle = false; mode = 'walk'; closeRing(); bars.innerHTML = ''; foes = {}; battleActors = []
  bg = await image(zone.scene)
}

function pop(a: Actor | undefined, d: number) {
  if (!a || !d) return
  if (d < 0) a.hurt = 0.5
  const p = toScreen({ x: a.x, y: a.y - 50 })
  const l = el('div', `t-pop ${d < 0 ? 'bad' : 'ok'}`, (d > 0 ? '+' : '') + d)
  l.style.left = `${p.x - 20}px`; l.style.top = `${p.y}px`; pops.append(l)
  setTimeout(() => l.remove(), 1000)
  shake.t = 0.18
}

function banner_(text: string) { banner.textContent = text; banner.classList.remove('on'); void banner.offsetWidth; banner.classList.add('on') }

// ── dice: the host's own numbers (dice events), rolled on screen ────────────────────────────────────────────────
const diceQ: BeatEvent[] = []
let rolling = false
function rollDie(ev: BeatEvent) { diceQ.push(ev); if (!rolling) nextDie() }
async function nextDie() {
  const ev = diceQ.shift()
  const box = document.getElementById('dice')!
  if (!ev) { rolling = false; box.hidden = true; return }
  rolling = true
  box.innerHTML = `<div class="t-die-card"><p>${String(ev.reason || ev.request || '')}</p><div class="t-die">?</div><small>${ev.vs != null ? `掷出 ≤ ${ev.vs} 成功` : ''}</small><b></b></div>`
  box.hidden = false
  const face = box.querySelector('.t-die')!, out = box.querySelector('b')!
  const sides = ev.vs != null && Number(ev.vs) > 20 ? 100 : 20   // a percentile check rolls d100, the combat layer d20
  for (let i = 0; i < 14; i++) { face.textContent = String(1 + Math.floor(Math.random() * sides)); await new Promise(r => setTimeout(r, 40 + i * 6)) }
  const total = ev.total ?? (Array.isArray(ev.rolls) ? (ev.rolls as number[])[0] : null)
  face.textContent = total != null ? String(total) : '·'
  if (ev.passed != null) { out.textContent = ev.passed ? '成功' : '失败'; out.className = ev.passed ? 'ok' : 'bad' }
  await new Promise(r => setTimeout(r, 1300))
  nextDie()
}

// ── map · toast · ending ────────────────────────────────────────────────────────────────────────────────────────
function openMap() {
  const m = pack.map || {}, box = $('#t-map')
  box.innerHTML = `<div class="t-map-sheet"><button class="x">×</button><img src="${art.url(m.picture)}" alt=""></div>`
  const sheet = box.firstElementChild as HTMLElement
  for (const id in m.at || {}) {
    const [x, y] = m.at[id], here = sameZone(id, zoneId)
    const b = el('button', here ? 'here' : '', (here ? '● ' : '') + (zoneOf(id).name || id))
    b.style.left = `${x * 100}%`; b.style.top = `${y * 100}%`
    b.onclick = () => { box.hidden = true; if (!here) say(`我去${zoneOf(id).name || id}。`) }
    sheet.append(b)
  }
  ;(sheet.querySelector('.x') as HTMLElement).onclick = () => (box.hidden = true)
  box.hidden = false
}

let toastTimer = 0
function toast(text: string, cls = '') {
  const t = document.getElementById('toast')!
  t.textContent = text; t.className = cls; t.hidden = false
  clearTimeout(toastTimer); toastTimer = window.setTimeout(() => (t.hidden = true), 2400)
}

function showEnding(s: NonNullable<Awaited<ReturnType<HostReads['settlement']>>>) {
  ended = true
  const id = s.exit?.id || '', e = pack.endings?.[id] || {}
  const box = $('#ending'); box.hidden = false
  $('#ending-kind').textContent = `结局 · ${e.title || id}`
  $('#ending-text').textContent = e.text || ''
  $('#ending-truth').textContent = s.epilogue || ''
}

export type { HostState }
