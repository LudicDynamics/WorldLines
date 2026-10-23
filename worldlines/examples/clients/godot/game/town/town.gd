# 石津镇 · 雾退之夜 — a walkable pixel town on a WorldLines host (Octopath-style).
#
# The host owns the world: where you are, who is here, what time it is, whether a fight is on. This screen only draws it
# and turns what you do into a line you say:
#   walk to a doorway + E   → "我去主街。"            (the host moves you, or tells you why not)
#   walk up to someone + E  → a ring of approaches   (交谈 · 打探 · 说服 · 交易 · 偷窃 · 邀请 · 委托 · 休息 · 动手)
#                             each one is only a suggested line — the host's orchestration judges it
#   Enter                    → say anything
# The options the host offers after each beat, the dice it rolls and the fight (foes are variables foe.<id>.hp while
# the combat layer is on) come from the protocol; pictures come from the art pack (../art/stoneford-town/art.json).
extends Control

const Actor = preload("res://game/town/actor.gd")

const INK := Color("#ece4d4")
const MUTED := Color("#9aa3b2")
const LAMP := Color("#e0a458")
const PLAN := Color("#86c9a4")
const RES := Color("#d98a6f")
const BAD := Color("#d0584c")
const MOSS := Color("#8fae7c")
const PANEL := Color(0.05, 0.062, 0.085, 0.9)
const VIEW := Vector2(480, 270)   # the stage, in the people's pixels
const UP := 4                     # drawn ×4: the scene at its full 1920×1080, the people as crisp ×4 pixels
const SPEED := 72.0
const REACH := 30.0

var client: Node
var art: RefCounted
var kinds := {}
var start := ""
var sans: Font
var serif: Font
var pack := {}
var meta := {}

var state := {}
var vars := {}
var specs := {}
var zone_id := ""
var zone := {}
var walk := PackedVector2Array()
var blocks: Array = []
var player: Actor
var people: Array = []        # [{node, who, kind: npc|soul|mob}]
var target := {}              # what E would act on: {kind: exit|npc|spot, at, ...}
var move_to := Vector2.INF
var pending := {}             # clicked someone: walk up, then open the ring
var busy := false
var in_battle := false
var foes := {}                # fid → {node, name, hp, max, bar}
var last_beat := ""
var last_board := false
var last_options: Array = []
var seg := {}
var dice_queue: Array = []
var dice_running := false
var ended := false
var mode := "walk"            # walk · talk (with someone) · battle — what the box at the bottom is for
var talk_with := {}           # the person you are talking to (their ring comes back after each beat)
var queue: Array = []         # lines waiting for the host: [{text, wire, kind: bg|talk}] — one beat at a time
var words_for := {}           # what the words typed in a ring belong to: {kind, approach?, target}
var cap_until := 0.0          # a background beat's caption stays this long
var held := {}                # movement keys down: physical keycode → last time an event said so (see _held)
var stuck := 0.0              # seconds the walk target has not got any nearer (a wall in the way → give up)
var mask: Image               # scenes/<id>-walk.png: white = ground you can stand on (else the walk polygon)

# stage
var vp: SubViewport
var view: TextureRect
var stage: Node2D
var bg: Sprite2D
var town_root: Node2D
var battle_root: Node2D
var fx: Node2D

# screen
var hud_place: Label
var hud_time: Label
var hud_fog: Label
var goals_box: VBoxContainer
var meters_box: HBoxContainer
var beat_tag: Label
var prompt: PanelContainer
var prompt_lbl: Label
var names: Control
var dlg: PanelContainer
var dlg_face: TextureRect
var dlg_scroll: ScrollContainer
var dlg_box: VBoxContainer
var opts_box: VBoxContainer
var input: LineEdit
var stop_btn: Button
var ring: Control
var bars: Control
var pops: Control
var log_layer: Control
var log_box: VBoxContainer
var map_layer: Control
var dice_layer: Control
var toast: PanelContainer
var banner: Label
var fade: ColorRect
var ending_layer: Control


# ── setup ────────────────────────────────────────────────────────────────────────────────────────────────────────
func setup(client_: Node, art_: RefCounted, kinds_: Dictionary, start_: String, sans_: Font, serif_: Font) -> void:
	client = client_; art = art_; kinds = kinds_; start = start_; sans = sans_; serif = serif_
	pack = art.pack
	meta = art.read_json("sprites/index.json")


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	if client:
		client.chunk.connect(_on_chunk)
		client.beat.connect(_on_beat)
		client.ask_user.connect(_on_ask)
		client.turn_started.connect(_on_turn_started)
		client.failed.connect(func(m: String) -> void: _toast(m, BAD))
		client.beat_kinds_loaded.connect(func(k: Dictionary) -> void: kinds = k.get("kinds", {}); start = str(k.get("start", "")))
		await _refresh()
		await _enter_zone(str(state.get("player_location", "")), "")
		_line_note(str(pack.get("pitch", "")))
		_show_options([])


func _build() -> void:
	var night := ColorRect.new(); night.color = Color("#07090d"); add_child(_full(night))
	vp = SubViewport.new(); vp.size = Vector2i(VIEW) * UP; vp.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	vp.transparent_bg = false; vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(vp)
	stage = Node2D.new(); stage.scale = Vector2(UP, UP); vp.add_child(stage)
	bg = Sprite2D.new(); bg.centered = false; stage.add_child(bg)
	var deco := Node2D.new(); deco.name = "deco"; stage.add_child(deco); deco.draw.connect(_draw_deco.bind(deco))
	town_root = Node2D.new(); town_root.y_sort_enabled = true; stage.add_child(town_root)
	battle_root = Node2D.new(); battle_root.y_sort_enabled = true; battle_root.visible = false; stage.add_child(battle_root)
	fx = Node2D.new(); stage.add_child(fx)
	view = TextureRect.new(); view.texture = vp.get_texture(); view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED; view.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	view.mouse_filter = Control.MOUSE_FILTER_STOP; view.gui_input.connect(_on_view_input)
	add_child(_full(view))

	names = Control.new(); names.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(names))
	bars = Control.new(); bars.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(bars))
	pops = Control.new(); pops.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(pops))

	# HUD — where · when · how long until the fog lifts | the three things · meters
	var hud := PanelContainer.new(); hud.add_theme_stylebox_override("panel", _box(PANEL, Color(1, 1, 1, 0.08), 10, 10))
	hud.position = Vector2(18, 16); hud.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(hud)
	var hv := VBoxContainer.new(); hv.add_theme_constant_override("separation", 2); hud.add_child(hv)
	hud_place = _label("", 22, INK, serif); hv.add_child(hud_place)
	hud_time = _label("", 13, MUTED); hv.add_child(hud_time)
	hud_fog = _label("", 13, LAMP); hv.add_child(hud_fog)
	var right := PanelContainer.new(); right.add_theme_stylebox_override("panel", _box(PANEL, Color(1, 1, 1, 0.08), 10, 10))
	right.set_anchors_preset(Control.PRESET_TOP_RIGHT); right.offset_left = -300; right.offset_right = -18; right.offset_top = 16
	right.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(right)
	var rv := VBoxContainer.new(); rv.add_theme_constant_override("separation", 4); right.add_child(rv)
	rv.add_child(_label("出北门之前", 12, MUTED))
	goals_box = VBoxContainer.new(); rv.add_child(goals_box)
	meters_box = HBoxContainer.new(); meters_box.add_theme_constant_override("separation", 12); rv.add_child(meters_box)
	var keys := _label("WASD / 点地面 走 · E 互动 · M 地图 · H 记录 · Esc 离开", 11, Color(0.6, 0.64, 0.7, 0.7))
	keys.set_anchors_preset(Control.PRESET_TOP_RIGHT); keys.offset_left = -420; keys.offset_right = -20; keys.offset_top = 0
	keys.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; keys.position.y = 2; add_child(keys)

	prompt = PanelContainer.new(); prompt.add_theme_stylebox_override("panel", _box(Color(0.06, 0.07, 0.09, 0.92), Color(0.88, 0.64, 0.35, 0.7), 6, 4))
	prompt.visible = false; prompt.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(prompt)
	prompt_lbl = _label("", 14, INK); prompt.add_child(prompt_lbl)

	# dialogue — portrait · who is speaking · the prose as it is written · the host's options
	dlg = PanelContainer.new(); dlg.add_theme_stylebox_override("panel", _box(Color(0.04, 0.05, 0.07, 0.93), Color(0.88, 0.64, 0.35, 0.35), 10, 14))
	dlg.set_anchors_preset(Control.PRESET_BOTTOM_WIDE); dlg.offset_left = 18; dlg.offset_right = -18; dlg.offset_top = -300; dlg.offset_bottom = -16
	add_child(dlg); dlg.visible = false
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 16); dlg.add_child(row)
	dlg_face = TextureRect.new(); dlg_face.custom_minimum_size = Vector2(170, 0); dlg_face.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	dlg_face.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED; row.add_child(dlg_face)
	var mid := VBoxContainer.new(); mid.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(mid)
	beat_tag = _label("", 11, MUTED); mid.add_child(beat_tag)
	dlg_scroll = ScrollContainer.new(); dlg_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL; dlg_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	mid.add_child(dlg_scroll)
	dlg_box = VBoxContainer.new(); dlg_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; dlg_box.add_theme_constant_override("separation", 10); dlg_scroll.add_child(dlg_box)
	var compose := HBoxContainer.new(); mid.add_child(compose)
	input = LineEdit.new(); input.size_flags_horizontal = Control.SIZE_EXPAND_FILL; input.placeholder_text = "说你想做什么(Enter)"
	input.text_submitted.connect(_on_submit); compose.add_child(input); compose.name = "compose"; compose.visible = false
	stop_btn = Button.new(); stop_btn.text = "■ 停"; stop_btn.visible = false; stop_btn.add_theme_color_override("font_color", BAD)
	stop_btn.pressed.connect(func() -> void: client.cancel()); compose.add_child(stop_btn)
	opts_box = VBoxContainer.new(); opts_box.custom_minimum_size = Vector2(360, 0); opts_box.add_theme_constant_override("separation", 6); row.add_child(opts_box)


	ring = Control.new(); ring.visible = false; add_child(_full(ring))
	banner = _label("", 44, LAMP, serif); banner.set_anchors_preset(Control.PRESET_CENTER); banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner.offset_left = -400; banner.offset_right = 400; banner.offset_top = -160; banner.offset_bottom = -100; banner.modulate.a = 0; add_child(banner)
	banner.add_theme_constant_override("outline_size", 8); banner.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	dice_layer = _overlay(Color(0.02, 0.025, 0.035, 0.5)); dice_layer.visible = false
	log_layer = _overlay(Color(0.02, 0.025, 0.035, 0.88)); log_layer.visible = false
	var ls := ScrollContainer.new(); ls.set_anchors_preset(Control.PRESET_FULL_RECT); ls.offset_left = 120; ls.offset_right = -120; ls.offset_top = 60; ls.offset_bottom = -60
	ls.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; log_layer.add_child(ls)
	log_box = VBoxContainer.new(); log_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; log_box.add_theme_constant_override("separation", 10); ls.add_child(log_box)
	map_layer = _overlay(Color(0.02, 0.025, 0.035, 0.9)); map_layer.visible = false
	toast = PanelContainer.new(); toast.add_theme_stylebox_override("panel", _box(PANEL, Color(0.88, 0.64, 0.35, 0.55)))
	toast.set_anchors_preset(Control.PRESET_CENTER_TOP); toast.offset_top = 22; toast.visible = false; toast.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(toast)
	ending_layer = _overlay(Color(0.02, 0.025, 0.035, 0.96)); ending_layer.visible = false
	fade = ColorRect.new(); fade.color = Color(0, 0, 0, 1); fade.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(fade))


# ── reading the host ─────────────────────────────────────────────────────────────────────────────────────────────
func _refresh() -> void:
	var s: Variant = await client.get_json("/state", {})
	if s is Dictionary and not (s as Dictionary).is_empty():
		state = s
	var sc: Variant = await client.get_json("/api/v1/play/schema", {})
	if sc is Dictionary:
		vars = {}; specs = {}
		for v in sc.get("variables", []):
			vars[str(v.get("name"))] = v.get("value"); specs[str(v.get("name"))] = v
	_draw_hud()


## A number as a person reads it: JSON numbers arrive as floats (24.0); whole ones lose the .0.
func _n(v: Variant) -> String:
	if v is float and is_equal_approx(v, roundf(v)):
		return str(int(v))
	return str(v)


func _var(name: String, fallback: Variant = 0) -> Variant:
	return vars.get(name, fallback) if vars.get(name) != null else fallback


func _minutes(day: int, clock: String) -> int:
	var hm := clock.split(":")
	return (day - 1) * 1440 + (int(hm[0]) * 60 + int(hm[1]) if hm.size() == 2 else 0)


func _draw_hud() -> void:
	var here := str(state.get("player_location", zone_id))
	hud_place.text = str(_zone(here).get("name", (state.get("places", {}) as Dictionary).get(here, here)))
	var day := int(_var("time.day", 1)); var clock := str(_var("time.clock", ""))
	hud_time.text = "第 %d 天 · %s" % [day, clock]
	var fog: Dictionary = pack.get("fog", {})
	if not fog.is_empty() and clock.contains(":"):
		var left := _minutes(int(fog.get("day", 7)), str(fog.get("clock", "00:00"))) - _minutes(day, clock)
		hud_fog.text = ("离%s还有 %d 小时 %02d 分" % [fog.get("label", "雾退"), left / 60, left % 60]) if left > 0 else "雾退开了 —— 北路能走"
	_clear(goals_box)
	for g in pack.get("goals", []):
		var ok := float(_var(str(g.get("var")), 0)) >= 1.0
		goals_box.add_child(_label(("✓  " if ok else "○  ") + str(g.get("label")), 14, MOSS if ok else INK))
	_clear(meters_box)
	for m in pack.get("meters", []):
		var v: Variant = vars.get(str(m.get("var")))
		if v == null:
			continue
		var mx: Variant = (specs.get(str(m.get("var")), {}) as Dictionary).get("max")
		meters_box.add_child(_label("%s %s%s" % [m.get("label"), _n(v), ("/" + _n(mx)) if mx != null else ""], 13, LAMP if str(m.get("var")) == "player.hp" else INK))


func _zone(id: String) -> Dictionary:
	var zs: Dictionary = pack.get("zones", {})
	if zs.has(id):
		return zs[id]
	for k in zs:   # "gate_north" and "T001/gate_north" are the same place
		if str(k).ends_with("/" + id) or id.ends_with("/" + str(k).get_file()):
			return zs[k]
	return {}


func _person(name: String) -> Dictionary:
	var ps: Dictionary = pack.get("people", {})
	var n := str((pack.get("speakers", {}) as Dictionary).get(name, name))
	if ps.has(n):
		return ps[n]
	for k in ps:
		if n.begins_with(str(k)):
			return ps[k]
	return {}


func _canon(name: String) -> String:
	var n := str((pack.get("speakers", {}) as Dictionary).get(name, name))
	for k in (pack.get("people", {}) as Dictionary):
		if n.begins_with(str(k)):
			return str(k)
	return n


# ── the town on screen ───────────────────────────────────────────────────────────────────────────────────────────
func _enter_zone(id: String, from: String) -> void:
	var tw := create_tween(); tw.tween_property(fade, "color:a", 1.0, 0.18); await tw.finished
	zone_id = id
	zone = _zone(id)
	move_to = Vector2.INF; pending = {}; target = {}; held.clear()
	if zone.is_empty():
		zone = {"name": str((state.get("places", {}) as Dictionary).get(id, id)), "walk": [[40, 150], [440, 150], [440, 260], [40, 260]], "exits": [], "npcs": [], "spawn": [240, 220]}
	_set_bg(zone.get("scene"))
	walk = PackedVector2Array()
	for p in zone.get("walk", []):
		walk.append(Vector2(p[0], p[1]))
	blocks = zone.get("block", [])
	var scene_file := str(zone.get("scene", ""))
	var mt: Texture2D = art.texture(zone.get("mask", scene_file.get_basename() + "-walk.png"))
	mask = mt.get_image() if mt else null
	for c in town_root.get_children():
		c.queue_free()
	people.clear()
	var spawn := _v(zone.get("spawn", [240, 220]))
	for e in zone.get("exits", []):
		if from != "" and (str(e.get("to")) == from or str(e.get("to")).get_file() == from.get_file()):
			spawn = _v(e.get("at")).lerp(_v(zone.get("spawn", [240, 220])), 0.3)
	player = _actor(str(pack.get("player", "旅人")), spawn)
	player.face = "up" if spawn.y > 200 else "down"
	for n in zone.get("npcs", []):
		var a := _actor(str(n.get("who")), _v(n.get("at")))
		a.face = str(n.get("face", "down"))
		people.append({"node": a, "who": str(n.get("who")), "kind": "mob" if "mob" in (_person(str(n.get("who"))).get("tags", []) as Array) else "npc"})
	_place_souls()
	for p in zone.get("props", []):
		var s := Sprite2D.new(); s.texture = art.texture(p.get("sprite")); s.position = _v(p.get("at")); s.offset = Vector2(0, -20); town_root.add_child(s)
	var cut: Array = zone.get("layers", (art.read_json("scenes/layers.json") as Dictionary).get(scene_file.get_file().get_basename(), []))
	for l in cut:   # a cut-out of the scene in front of its base line: drawn over whoever stands behind it
		var tex: Texture2D = art.texture(l.get("img"))
		if tex == null:
			continue
		var s := Sprite2D.new(); s.texture = tex; s.centered = false; s.scale = VIEW / Vector2(tex.get_size())
		var base := float(l.get("base", 270)); s.position = Vector2(0, base); s.offset = Vector2(0, -base / s.scale.y)
		town_root.add_child(s)
	stage.get_node("deco").queue_redraw()
	_draw_hud()
	_build_names()
	tw = create_tween(); tw.tween_property(fade, "color:a", 0.0, 0.25)


func _set_bg(rel: Variant) -> void:   # any size of scene picture fills the 480×270 stage
	bg.texture = art.texture(rel)
	if bg.texture:
		bg.scale = VIEW / Vector2(bg.texture.get_size())


func _place_souls() -> void:
	var free: Array = zone.get("free", [[260, 210]])
	var i := 0
	for s in state.get("souls", []):
		if not (s is Dictionary):
			continue
		var loc := str(s.get("location", ""))
		var who := _canon(str(s.get("name", "")))
		var follows := _follows(who)
		if not follows and not (loc == zone_id or loc.get_file() == zone_id.get_file()):
			continue
		if _find(who) != null:
			continue
		var at := player.position + Vector2(-22, 6) if follows else _v(free[i % free.size()])
		i += 1
		var a := _actor(who, at)
		people.append({"node": a, "who": who, "kind": "soul", "follow": follows})


func _follows(who: String) -> bool:
	var f: Dictionary = (pack.get("follow", {}) as Dictionary).get(who, {})
	if f.is_empty():
		return false
	var fl: Variant = f.get("flag")
	for v in vars:   # flags may be exposed as variables flag.<key>
		if str(v) == "flag." + str(fl) and bool(vars[v]):
			return true
	return false


func _find(who: String) -> Variant:
	for p in people:
		if p["who"] == who:
			return p
	return null


func _actor(who: String, at: Vector2) -> Actor:
	var a: Actor = Actor.new()
	var p := _person(who)
	var sid := str(p.get("sprite", ""))
	a.setup(who, art.texture("sprites/%s.png" % sid) if sid != "" else null, meta.get(sid, {}), Color(str(p.get("color", "#8aa07a"))))
	a.position = at
	town_root.add_child(a)
	_depth(a)
	return a


func _depth(a: Node2D) -> void:
	var k := clampf(lerpf(0.72, 1.0, (a.position.y - 110.0) / 150.0), 0.68, 1.0)
	a.scale = Vector2(k, k)


func _draw_deco(n: Node2D) -> void:   # doorways glow a little, so you can see where the street goes
	if in_battle or zone.is_empty():
		return
	if bg.texture == null:
		n.draw_rect(Rect2(Vector2.ZERO, VIEW), Color("#1b2230"))
		n.draw_colored_polygon(walk, Color("#2c3a4a"))
	for e in zone.get("exits", []):
		var at := _v(e.get("at"))
		n.draw_circle(at, 9, Color(1, 0.8, 0.45, 0.16))
		n.draw_circle(at, 4, Color(1, 0.85, 0.55, 0.45))


func _build_names() -> void:
	_clear(names)
	for p in people:
		var l := _label(str(p["who"]), 13, Color(0.93, 0.9, 0.82, 0.85)); l.name = "n%d" % (p["node"] as Actor).get_instance_id()
		l.add_theme_constant_override("outline_size", 5); l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
		names.add_child(l)
	for e in zone.get("exits", []):
		var l := _label("› " + str(e.get("label")), 14, Color(1, 0.86, 0.6, 0.9))
		l.add_theme_constant_override("outline_size", 5); l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
		l.set_meta("at", _v(e.get("at"))); names.add_child(l)


func _v(p: Variant) -> Vector2:
	return Vector2(float(p[0]), float(p[1])) if p is Array and (p as Array).size() >= 2 else Vector2(240, 220)


# world ↔ screen (the stage is drawn letterboxed and scaled up with crisp pixels)
func _k() -> float:
	return minf(view.size.x / VIEW.x, view.size.y / VIEW.y)


func to_screen(p: Vector2) -> Vector2:
	return view.position + (view.size - VIEW * _k()) / 2.0 + p * _k()


func to_world(p: Vector2) -> Vector2:
	return (p - (view.size - VIEW * _k()) / 2.0) / _k()


func can_stand(p: Vector2) -> bool:
	if mask != null:
		var x := int(p.x * mask.get_width() / VIEW.x); var y := int(p.y * mask.get_height() / VIEW.y)
		if x < 0 or y < 0 or x >= mask.get_width() or y >= mask.get_height() or mask.get_pixel(x, y).r < 0.5:
			return false
	elif walk.size() >= 3 and not Geometry2D.is_point_in_polygon(p, walk):
		return false
	for b in blocks:
		if p.distance_to(Vector2(b[0], b[1])) < float(b[2]):
			return false
	return true


# ── walking ──────────────────────────────────────────────────────────────────────────────────────────────────────
func _typing() -> bool:
	return input.has_focus() or ring.visible or map_layer.visible or log_layer.visible or ending_layer.visible


func _process(delta: float) -> void:
	if player == null:
		return
	if not in_battle:
		var dir := Vector2.ZERO
		if not _typing():
			dir.x = float(_held(KEY_D) or _held(KEY_RIGHT)) - float(_held(KEY_A) or _held(KEY_LEFT))
			dir.y = float(_held(KEY_S) or _held(KEY_DOWN)) - float(_held(KEY_W) or _held(KEY_UP))
		if dir != Vector2.ZERO:
			move_to = Vector2.INF; pending = {}
		elif move_to != Vector2.INF:
			var d := move_to - player.position
			if d.length() < 2.0:
				move_to = Vector2.INF
			else:
				dir = d
		player.moving = dir != Vector2.ZERO
		if player.moving:
			var step := dir.normalized() * SPEED * delta
			var was := player.position
			for s in [step, Vector2(step.x, 0), Vector2(0, step.y)]:
				if can_stand(player.position + s):
					player.position += s
					break
			# walking to a clicked spot with something in the way: stop instead of treading in place against it
			stuck = stuck + delta if player.position.distance_to(was) < 0.05 else 0.0
			if move_to != Vector2.INF and stuck > 0.3:
				move_to = Vector2.INF; pending = {}; stuck = 0.0; player.moving = false
			if absf(dir.x) > absf(dir.y):
				player.face = "right" if dir.x > 0 else "left"
			else:
				player.face = "down" if dir.y > 0 else "up"
			_depth(player)
		for p in people:   # companions keep a step behind
			if p.get("follow", false):
				var a: Actor = p["node"]
				var gap := player.position - a.position
				a.moving = gap.length() > 24.0
				if a.moving:
					a.position += gap.normalized() * SPEED * 0.95 * delta
					a.face = ("right" if gap.x > 0 else "left") if absf(gap.x) > absf(gap.y) else ("down" if gap.y > 0 else "up")
					_depth(a)
		if not pending.is_empty() and player.position.distance_to(pending["at"]) < REACH:
			var p: Dictionary = pending; pending = {}; move_to = Vector2.INF
			_interact(p)
		_pick_target()
		if mode == "talk" and not talk_with.is_empty() and player.position.distance_to(talk_with["at"]) > 56.0 and not busy:
			_end_talk()
		if mode == "walk" and dlg.visible and not busy and queue.is_empty() and Time.get_ticks_msec() / 1000.0 > cap_until:
			_box_mode("hide")
	_place_labels()


func _box_mode(kind: String) -> void:   # hide · caption (a background beat, no portrait) · talk (someone in front of you)
	dlg.visible = kind != "hide"
	if kind == "hide":
		return
	var talk := kind == "talk"
	dlg_face.visible = talk; opts_box.visible = true; beat_tag.visible = true
	var tw := create_tween(); tw.tween_property(dlg, "offset_top", (-250.0 if in_battle else -290.0) if talk else -176.0, 0.16)


func _pick_target() -> void:
	var best := {}; var bd := REACH
	for p in people:
		var d := player.position.distance_to((p["node"] as Actor).position)
		if d < bd and not p.get("follow", false):
			bd = d; best = {"kind": "npc", "who": p["who"], "at": (p["node"] as Actor).position, "node": p["node"], "mob": p["kind"] == "mob"}
	for s in zone.get("spots", []):
		var d := player.position.distance_to(_v(s.get("at")))
		if d < bd + 6:
			bd = d; best = {"kind": "spot", "label": s.get("label"), "says": s.get("says"), "desc": s.get("desc", ""), "at": _v(s.get("at"))}
	for e in zone.get("exits", []):
		var d := player.position.distance_to(_v(e.get("at")))
		if d < bd:
			bd = d; best = {"kind": "exit", "to": e.get("to"), "label": e.get("label"), "says": e.get("says", ""), "at": _v(e.get("at"))}
	target = best
	if best.is_empty() or busy or _typing() or in_battle:
		prompt.visible = false
		return
	match best["kind"]:
		"npc": prompt_lbl.text = "E · 和%s……" % best["who"]
		"spot": prompt_lbl.text = "E · %s" % best["label"]
		"exit": prompt_lbl.text = "E · 前往 %s" % best["label"]
	prompt.visible = true
	prompt.reset_size()
	prompt.position = to_screen(best["at"]) + Vector2(-prompt.size.x / 2.0, -78 * _k() / 4.0 - 40)


func _place_labels() -> void:
	for l in names.get_children():
		if l.has_meta("at"):
			(l as Label).visible = not in_battle
			l.position = to_screen(l.get_meta("at")) + Vector2(-(l as Label).size.x / 2.0, 8)
			continue
		var a := instance_from_id(int(str(l.name).substr(1))) as Actor
		if a == null or not is_instance_valid(a):
			continue
		(l as Label).visible = not in_battle
		l.position = to_screen(a.position - Vector2(0, a.height() + 4)) - Vector2((l as Label).size.x / 2.0, 18)


func _on_view_input(ev: InputEvent) -> void:
	if not (ev is InputEventMouseButton) or not (ev as InputEventMouseButton).pressed or (ev as InputEventMouseButton).button_index != MOUSE_BUTTON_LEFT:
		return
	if ring.visible:
		_close_ring()
		return
	var w := to_world((ev as InputEventMouseButton).position - view.position)
	if in_battle:
		_battle_ring()
		return
	for p in people:   # clicked someone: walk up to them, then the ring
		var a: Actor = p["node"]
		if Rect2(a.position - Vector2(12, a.height()), Vector2(24, a.height())).has_point(w):
			pending = {"kind": "npc", "who": p["who"], "at": a.position, "node": a, "mob": p["kind"] == "mob"}
			move_to = _nearest_stand(a.position)
			return
	for e in zone.get("exits", []):
		if w.distance_to(_v(e.get("at"))) < 14:
			pending = {"kind": "exit", "to": e.get("to"), "label": e.get("label"), "says": e.get("says", ""), "at": _v(e.get("at"))}
			move_to = _nearest_stand(_v(e.get("at")))
			return
	move_to = _nearest_stand(w)


func _nearest_stand(p: Vector2) -> Vector2:
	if can_stand(p):
		return p
	var best := player.position
	for i in 24:   # walk toward it along the line from where you stand
		var q := p.lerp(player.position, i / 24.0)
		if can_stand(q):
			return q
	return best


const MOVE_KEYS := [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT]


func _input(ev: InputEvent) -> void:   # movement keys, tracked from their own events
	if ev is InputEventKey and (ev as InputEventKey).physical_keycode in MOVE_KEYS:
		var k := (ev as InputEventKey).physical_keycode
		if (ev as InputEventKey).pressed:
			held[k] = Time.get_ticks_msec()
		else:
			held.erase(k)


## A key counts as held while the OS still says so and it has been reported lately: with a Chinese input method on,
## macOS sometimes swallows the key-up, and the character would walk on by itself.
func _held(k: Key) -> bool:
	if not held.has(k):
		return false
	if not Input.is_physical_key_pressed(k) or Time.get_ticks_msec() - int(held[k]) > 1000:
		held.erase(k)
		return false
	return true


func _notification(what: int) -> void:
	if what in [NOTIFICATION_APPLICATION_FOCUS_OUT, NOTIFICATION_WM_WINDOW_FOCUS_OUT]:
		held.clear()


func _unhandled_input(ev: InputEvent) -> void:
	if not (ev is InputEventKey) or not (ev as InputEventKey).pressed or (ev as InputEventKey).echo:
		return
	var k := (ev as InputEventKey).keycode
	if k == KEY_ESCAPE:
		if ring.visible:
			_close_ring()
		elif input.has_focus():
			_hide_input()
		elif map_layer.visible or log_layer.visible:
			map_layer.visible = false; log_layer.visible = false
		elif mode == "talk":
			_end_talk()
		return
	if ending_layer.visible or input.has_focus():
		return
	if ring.visible and k >= KEY_1 and k <= KEY_9:
		for b in ring.get_children():
			if b is Button and b.has_meta("n") and int(b.get_meta("n")) == k - KEY_0:
				(b as Button).emit_signal("pressed")
		return
	match k:
		KEY_E, KEY_SPACE:
			if in_battle:
				_battle_ring()
			elif mode == "talk" and not talk_with.is_empty():
				_open_ring(talk_with)
			elif not target.is_empty():
				_interact(target)
		KEY_M:
			_open_map()
		KEY_H, KEY_L:
			log_layer.visible = not log_layer.visible


func _interact(t: Dictionary) -> void:
	match t["kind"]:
		"exit":   # the traditional part: the scene changes now; the host hears about it as a beat in the background
			var to := str(t["to"])
			var name := str(_zone(to).get("name", t["label"]))
			if not _zone(to).is_empty():
				await _enter_zone(to, zone_id)
			_queue(str(t["says"]) if str(t.get("says", "")) != "" else "我去%s。" % name, "bg", _ix({"kind": "move", "to": to}))
		"spot":
			if str(t.get("desc", "")) != "":
				_caption(str(t["desc"]))
			_queue(str(t["says"]), "bg", _ix({"kind": "examine", "what": str(t.get("label", "")), "says": str(t["says"])}))
		"npc":
			player.face = _face_to(player.position, t["at"])
			_open_ring(t)


func _face_to(a: Vector2, b: Vector2) -> String:
	var d := b - a
	return ("right" if d.x > 0 else "left") if absf(d.x) > absf(d.y) else ("down" if d.y > 0 else "up")


# ── the ring: approaches are suggestions, not commands ────────────────────────────────────────────────────────────
func _open_ring(t: Dictionary) -> void:
	var who := str(t["who"])
	var tags: Array = _person(who).get("tags", [])
	var list := []
	for a in pack.get("approaches", []):
		var when := str(a.get("when", ""))
		if when != "" and not (when in tags):
			continue
		if "mob" in tags and not (str(a.get("id")) in ["talk", "persuade", "fight"]):
			continue
		var e: Dictionary = a.duplicate(); e["who"] = who
		list.append(e)
	_ring(who, to_screen((t["at"] as Vector2) - Vector2(0, 24)), list, t)


func _battle_ring() -> void:
	if busy or not in_battle:
		return
	var list := []
	for c in (pack.get("battle", {}) as Dictionary).get("commands", []):
		var e: Dictionary = (c as Dictionary).duplicate(); e["battle"] = true
		list.append(e)
	var me := battle_root.get_node_or_null("me") as Actor
	_ring("你的行动", to_screen((me.position if me else Vector2(140, 172)) - Vector2(0, 30)), list, {})


func _ring(head_text: String, c: Vector2, list: Array, t: Dictionary) -> void:
	_clear(ring)
	var shade := ColorRect.new(); shade.color = Color(0, 0, 0, 0.35); ring.add_child(_full(shade))
	shade.gui_input.connect(_ring_shade_input)
	c = c.clamp(Vector2(220, 200), size - Vector2(220, 340))
	var r := 150.0
	for i in list.size():
		var a: Dictionary = list[i]
		var ang := -PI / 2.0 + TAU * i / float(list.size())
		var b := Button.new(); b.set_meta("n", i + 1)
		var icon: Texture2D = art.texture(a.get("icon"))
		if icon:
			b.icon = icon; b.expand_icon = true; b.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER; b.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
			b.add_theme_constant_override("icon_max_width", 46)
		b.custom_minimum_size = Vector2(108, 92 if icon else 52)
		b.text = "%d %s" % [i + 1, a.get("label")]; b.add_theme_font_size_override("font_size", 14)
		b.position = c + Vector2(cos(ang), sin(ang)) * r - b.custom_minimum_size / 2.0
		b.pressed.connect(_pick.bind(a, t))
		ring.add_child(b)
	var own := Button.new(); own.text = "自己说……"; own.custom_minimum_size = Vector2(120, 40); own.position = c - Vector2(60, 20)
	own.pressed.connect(_own_words.bind(t)); ring.add_child(own)
	var head := _label(head_text, 20, LAMP, serif); head.position = c + Vector2(-80, -r - 90); head.custom_minimum_size.x = 160
	head.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; ring.add_child(head)
	ring.visible = true
	prompt.visible = false


func _ring_shade_input(e: InputEvent) -> void:
	if e is InputEventMouseButton and (e as InputEventMouseButton).pressed:
		_close_ring()


func _close_ring() -> void:
	ring.visible = false
	_clear(ring)


func _pick(a: Dictionary, t: Dictionary) -> void:
	_close_ring()
	if a.get("battle", false):
		_command(a)
		return
	var who := str(a.get("who", ""))
	var aid := str(a.get("id", "talk"))
	_start_talk(t)
	words_for = {"kind": "talk", "target": who} if aid == "talk" else {"kind": "approach", "approach": aid, "target": who}
	if aid == "fight":
		words_for = {}
		_confirm(str(a.get("confirm", "")), str(a.get("says", "")).format({"who": who}), _ix({"kind": "encounter", "roster": "%s×1" % who}, str(a.get("says", "")).format({"who": who})))
		return
	if str(a.get("prefill", "")) != "":
		_ask_words(str(a["prefill"]).format({"who": who}))
		return
	var line := str(a.get("says", "")).format({"who": who})
	_queue(line, "talk", _ix(words_for, line))


func _start_talk(t: Dictionary) -> void:
	if t.is_empty() or in_battle:
		return
	mode = "talk"; talk_with = t
	_speaker(str(t["who"]))
	_box_mode("talk")


func _end_talk() -> void:
	mode = "walk"; talk_with = {}
	input.text = ""; _hide_input()
	_box_mode("hide")


func _own_words(t: Dictionary) -> void:
	_close_ring()
	_start_talk(t)
	words_for = {"kind": "talk", "target": str(t["who"])} if not t.is_empty() else {}
	_ask_words("")


func _ask_words(text: String) -> void:   # free words: only ever inside an interaction (someone's ring, the battle ring)
	held.clear()
	_box_mode("talk")
	(dlg.find_child("compose", true, false) as Control).visible = true
	input.text = text
	input.grab_focus()
	input.caret_column = text.length()


func _hide_input() -> void:
	input.release_focus()
	(dlg.find_child("compose", true, false) as Control).visible = false


func _prefill(text: String) -> void:
	_close_ring()
	_ask_words(text)


func _confirm(question: String, line: String, wire := "") -> void:
	_box_mode("talk")
	_clear(opts_box)
	opts_box.add_child(_label(question, 14, BAD))
	var yes := Button.new(); yes.text = "›  动手"; yes.pressed.connect(_queue.bind(line, "talk", wire)); opts_box.add_child(yes)
	var no := Button.new(); no.text = "›  算了"; no.pressed.connect(_show_options.bind(last_options)); opts_box.add_child(no)


func _on_submit(t: String) -> void:
	_hide_input()
	if in_battle or words_for.is_empty():
		_queue(t, "talk")   # in a fight the words are the fight's
	else:
		_queue(t, "talk", _ix(words_for, t))


# ── a turn ───────────────────────────────────────────────────────────────────────────────────────────────────────
func _on_turn_started() -> void:
	seg = {}; last_beat = ""; last_board = false


# every interaction is sent as one line the host's interaction node takes (move · examine · talk · approach ·
# encounter); its own graph judges, lands and settles it. Words typed in a fight go to the fight as they are.
func _ix(d: Dictionary, words := "") -> String:
	return "<interaction>%s</interaction>%s" % [JSON.stringify(d), words]


func _say(text: String) -> void:   # an option the host offered: said in whatever you are doing now
	if mode == "talk" and not words_for.is_empty() and not in_battle:
		_queue(text, "talk", _ix(words_for, text))
		return
	_queue(text, "bg" if mode == "walk" and not in_battle else "talk")


func _queue(text: String, kind: String, wire := "") -> void:
	text = text.strip_edges()
	if text == "" or ended:
		return
	queue.append({"text": text, "kind": kind, "wire": wire if wire != "" else text})
	if not busy:
		_run_queue()


func _run_queue() -> void:
	while not queue.is_empty() and not ended:
		var q: Dictionary = queue.pop_front()
		await _turn(str(q["text"]), str(q["kind"]), str(q["wire"]))


func _caption(text: String) -> void:
	if mode == "walk" and not in_battle:
		_clear(dlg_box)
		_box_mode("caption")
	_line_note(text)
	cap_until = Time.get_ticks_msec() / 1000.0 + 6.0


func _turn(text: String, kind: String, wire := "") -> void:
	busy = true; stop_btn.visible = true; prompt.visible = false
	var talk := kind == "talk" or in_battle
	_box_mode("talk" if talk else "caption")
	_clear(opts_box); _clear(dlg_box)
	last_options = []
	_line("你", text, INK, true)
	if talk and not in_battle:
		dlg_face.texture = art.texture(_person(str(talk_with.get("who", ""))).get("portrait")) if not talk_with.is_empty() else null
	var r: Dictionary = await client.send_line(wire if wire != "" else text)
	if not r.get("success", false):
		_line_note("这一句没跑完:%s" % str(r.get("error", "未知错误")))
	elif str(r.get("assistant_message", "")) == "" and seg.is_empty():
		_line_note("世界没有回应 —— 看一下主进程的日志(模型连得上吗?)")
	var opts: Array = r.get("options", []) if r.get("options") is Array and not (r.get("options") as Array).is_empty() else last_options
	if opts.is_empty():
		opts = _options_in(str(r.get("assistant_message", "")))
	seg = {}; stop_btn.visible = false
	await _after_turn()   # the host's word on where you are lands before anything else can be done
	busy = false
	_show_options(opts)
	cap_until = Time.get_ticks_msec() / 1000.0 + 9.0
	if in_battle and queue.is_empty():
		_battle_ring()


func _after_turn() -> void:
	await _refresh()
	var here := str(state.get("player_location", zone_id))
	var fighting := _foe_ids().size() > 0
	if fighting and not in_battle:
		_battle_begin()
	elif in_battle and not fighting:
		await _battle_end()
	elif in_battle:
		_battle_sync()
	# the host has the last word on where you are — once nothing else is on its way
	if not in_battle and queue.is_empty() and here != "" and here != zone_id and here.get_file() != zone_id.get_file():
		_toast("(%s)" % str(_zone(here).get("name", here)), MUTED)
		await _enter_zone(here, zone_id)
	elif not in_battle:
		_place_souls(); _build_names()
	var s: Variant = await client.get_json("/api/v1/play/engine/settlement", {})
	if s is Dictionary and (s as Dictionary).has("exit"):
		_show_ending(s)


func _show_options(opts: Array) -> void:
	_clear(opts_box)
	last_options = opts
	var shown := 0
	for o in opts:
		for part in str(o).split("|"):
			var label := part.strip_edges()
			if label == "" or shown >= 4:
				continue
			shown += 1
			var b := Button.new(); b.text = "›  " + label; b.alignment = HORIZONTAL_ALIGNMENT_LEFT; b.add_theme_font_override("font", serif)
			b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; b.custom_minimum_size.x = 340
			b.pressed.connect(_say.bind(label))
			opts_box.add_child(b)
	var k: Dictionary = kinds.get(last_beat, kinds.get(start, {}))
	var chips: Array = (k.get("chips", []) as Array) + ((k.get("chips_when_board", []) as Array) if last_board else [])
	if not chips.is_empty():
		var flow := HFlowContainer.new(); opts_box.add_child(flow)
		for c in chips:
			var b := Button.new(); b.text = str(c); b.add_theme_color_override("font_color", PLAN if str(c) == "定" else INK)
			b.pressed.connect(_say.bind(str(c))); flow.add_child(b)
	if mode == "talk" and not talk_with.is_empty():   # back to their ring: another approach, or your own words
		var more := Button.new(); more.text = "…… 还想做点别的(E)"; more.alignment = HORIZONTAL_ALIGNMENT_LEFT
		more.add_theme_color_override("font_color", LAMP); more.pressed.connect(_open_ring.bind(talk_with)); opts_box.add_child(more)
	input.placeholder_text = str(k.get("placeholder", "说你想做什么"))


func _options_in(text: String) -> Array:
	var out := []
	for m in RegEx.create_from_string("[①②③④⑤]\\s*([^①②③④⑤\\n]+)").search_all(text):
		out.append(m.get_string(1).strip_edges())
	return out


func _kind(b: String) -> Dictionary:
	return kinds.get(b, {}) if b != "" else {}


func _on_chunk(text: String, who: String, b: String) -> void:
	if seg.is_empty() or seg["who"] != who or seg["beat"] != b:
		if b != "" and last_beat != "" and b != last_beat:
			var div := str((_kind(b).get("divider_from", {}) as Dictionary).get(last_beat, ""))
			if div != "":
				var d := _label("—— %s ——" % div, 12, MUTED); d.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; dlg_box.add_child(d)
		if b != "":
			last_beat = b
			beat_tag.text = str(_kind(b).get("live", _kind(b).get("label", b)))
			beat_tag.add_theme_color_override("font_color", {"plan": PLAN, "res": RES}.get(str(_kind(b).get("tone", "")), MUTED))
		var name := _canon(who) if who != "" else ""
		var col: Color = LAMP if who != "" else {"plan": PLAN, "res": RES}.get(str(_kind(b).get("tone", "")), MUTED)
		seg = _line(name if name != "" else str(_kind(b).get("host", "主持")).split(" · ")[0], "", col)
		seg["who"] = who; seg["beat"] = b; seg["raw"] = ""
		if name != "":
			_speaker(name)
	seg["raw"] += text
	var raw := str(seg["raw"])
	var away := RegEx.create_from_string("(?:^|\\n)// ([^·\\n]+) · ([^@\\n]+?) @ ([^:：\\n]+)[:：]([^\\n]*)\\n")
	for m in away.search_all(raw):   # someone elsewhere had a beat: one muted line, not the prose
		_line_note("✓ %s @ %s:%s" % [m.get_string(2).strip_edges(), m.get_string(3).strip_edges(), m.get_string(4).strip_edges()])
		raw = raw.replace(m.get_string(0), "\n")
	seg["raw"] = raw
	(seg["body"] as Label).text = raw.strip_edges()
	if who == "":   # the host quoting someone — 卡斯:「…」 — lights them up
		var ms := RegEx.create_from_string("(?:^|\\n|。)([^\\n:：「。,,]{1,10})[:：]?「").search_all(raw)
		if not ms.is_empty() and not _person(ms[-1].get_string(1)).is_empty():
			_speaker(_canon(ms[-1].get_string(1)))
	_scroll_dlg()


func _speaker(name: String) -> void:
	var tex: Texture2D = art.texture(_person(name).get("portrait"))
	if tex:
		dlg_face.texture = tex
	var p: Variant = _find(name)
	if p != null and not in_battle:
		(p["node"] as Actor).face = _face_to((p["node"] as Actor).position, player.position)


func _line(who: String, text: String, color: Color, italic := false) -> Dictionary:
	var box := VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if who != "":
		box.add_child(_label(who, 13, color))
	var body := _label(text, 19, Color(0.92, 0.9, 0.85, 0.72) if italic else INK, serif)
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("line_spacing", 6)
	box.add_child(body)
	dlg_box.add_child(box)
	var copy := box.duplicate(); log_box.add_child(copy)   # the record (H) keeps every beat
	_scroll_dlg()
	return {"box": box, "body": body, "copy": copy}


func _line_note(text: String) -> void:
	if text != "":
		_line("", text, MUTED, true)


func _scroll_dlg() -> void:
	if not seg.is_empty() and seg.has("copy") and is_instance_valid(seg["copy"]):
		((seg["copy"] as VBoxContainer).get_child((seg["copy"] as VBoxContainer).get_child_count() - 1) as Label).text = (seg["body"] as Label).text
	await get_tree().process_frame
	dlg_scroll.scroll_vertical = int(dlg_scroll.get_v_scroll_bar().max_value)


func _on_beat(event: String, data: Dictionary) -> void:
	match event:
		"plan.beat":
			last_board = not (data.get("board", {}) as Dictionary).is_empty()
		"resolve.beat":
			if data.get("options") is Array and not (data["options"] as Array).is_empty():
				last_options = data["options"]
		"dice":
			dice_queue.append(data)
			if not dice_running:
				_roll_next()
		"node.enter":
			if str(data.get("node")) == "combat" and not in_battle:
				await _refresh()
				_battle_begin()
		"state.changed":
			for o in data.get("applied", []):
				if o is Dictionary and o.has("var"):
					_changed(str(o["var"]), o.get("from"), o.get("to"))


func _changed(v: String, from: Variant, to: Variant) -> void:
	if not (from is int or from is float) or not (to is int or to is float):
		return
	var d := float(to) - float(from)
	vars[v] = to
	if v.begins_with("foe.") and v.ends_with(".hp"):
		var fid := v.substr(4, v.length() - 7)
		if foes.has(fid):
			_pop(foes[fid]["node"], d)
			foes[fid]["hp"] = to
			_battle_sync()
		return
	if v == "player.hp":
		var who: Variant = battle_root.get_node_or_null("me") if in_battle else player
		_pop(who, d)
		return
	for g in pack.get("goals", []):
		if str(g.get("var")) == v and d > 0:
			_toast("✓ %s" % g.get("label"), MOSS)
	for m in pack.get("meters", []):
		if str(m.get("var")) == v and v != "player.hp":
			_toast("%s %s%d" % [m.get("label"), "+" if d > 0 else "", int(d)], MOSS if d > 0 else BAD)


func _on_ask(id: Variant, question: String, options: Array) -> void:
	_clear(opts_box)
	opts_box.add_child(_label(question, 14, LAMP))
	for o in options:
		var b := Button.new(); b.text = "›  " + str(o); b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.pressed.connect(_answer.bind(id, o))
		opts_box.add_child(b)


func _answer(id: Variant, o: Variant) -> void:
	_clear(opts_box)
	client.answer(id, o)


# ── the fight: narrative turns — the host narrates, the numbers come from the layer's variables ─────────────────
func _foe_ids() -> Array:
	var out := []
	for v in vars:
		var s := str(v)
		if s.begins_with("foe.") and s.ends_with(".hp"):
			out.append(s.substr(4, s.length() - 7))
	return out


func _foe_name(fid: String) -> String:
	var doc := str((specs.get("foe.%s.hp" % fid, {}) as Dictionary).get("doc", ""))
	return doc.split(" hp")[0] if doc != "" else fid


func _battle_begin() -> void:
	in_battle = true
	move_to = Vector2.INF; pending = {}; prompt.visible = false
	town_root.visible = false; battle_root.visible = true
	for c in battle_root.get_children():
		c.queue_free()
	foes.clear()
	var scene: Variant = zone.get("battle", (pack.get("battle", {}) as Dictionary).get("default_scene"))
	_set_bg(scene)
	var me := _battle_actor(str(pack.get("player", "旅人")), Vector2(140, 172), "right"); me.name = "me"
	var row := 0
	for p in people:
		if p["kind"] == "soul":
			_battle_actor(str(p["who"]), Vector2(100, 140 + row * 44), "right"); row += 1
	_battle_sync()
	mode = "battle"; talk_with = {}
	_box_mode("talk")
	_banner("战斗开始")
	get_tree().create_timer(1.2).timeout.connect(_battle_ring)
	stage.get_node("deco").queue_redraw()


func _battle_actor(who: String, at: Vector2, face: String) -> Actor:
	var a: Actor = Actor.new()
	var p := _person(who)
	var sid := str(p.get("sprite", ""))
	a.setup(who, art.texture("sprites/%s.png" % sid) if sid != "" else null, meta.get(sid, {}), Color(str(p.get("color", "#8aa07a"))))
	a.position = at; a.face = face
	battle_root.add_child(a)
	return a


func _battle_sync() -> void:
	var ids := _foe_ids()
	var slots := [Vector2(345, 150), Vector2(405, 172), Vector2(330, 192), Vector2(420, 128), Vector2(385, 205), Vector2(300, 160)]
	for i in ids.size():
		var fid: String = ids[i]
		if not foes.has(fid):
			var name := _foe_name(fid)
			var sid := "bandit"
			for f in (pack.get("battle", {}) as Dictionary).get("foes", []):
				if str(f.get("match")) == "" or name.contains(str(f.get("match"))):
					sid = str(f.get("sprite")); break
			var a: Actor = Actor.new()
			a.setup(name, art.texture("sprites/%s.png" % sid), meta.get(sid, {}), BAD)
			a.position = slots[i % slots.size()]; a.face = "left"
			battle_root.add_child(a)
			foes[fid] = {"node": a, "name": name, "hp": 0, "max": 0}
		var hp := int(_var("foe.%s.hp" % fid, 0))
		var mx: Variant = (specs.get("foe.%s.hp" % fid, {}) as Dictionary).get("max")
		foes[fid]["hp"] = hp; foes[fid]["max"] = int(mx) if mx != null else maxi(hp, int(foes[fid]["max"]))
		(foes[fid]["node"] as Actor).down = hp <= 0
	_draw_bars()


func _draw_bars() -> void:
	_clear(bars)
	if not in_battle:
		return
	for fid in foes:
		var f: Dictionary = foes[fid]
		var a: Actor = f["node"]
		var v := VBoxContainer.new(); v.custom_minimum_size.x = 150
		v.add_child(_label("%s  %d/%d" % [f["name"], int(f["hp"]), int(f["max"])], 13, MUTED if int(f["hp"]) <= 0 else INK))
		var bar := ProgressBar.new(); bar.max_value = maxi(1, int(f["max"])); bar.value = int(f["hp"]); bar.show_percentage = false
		bar.custom_minimum_size = Vector2(150, 8)
		var fill := StyleBoxFlat.new(); fill.bg_color = BAD; bar.add_theme_stylebox_override("fill", fill)
		var back := StyleBoxFlat.new(); back.bg_color = Color(0, 0, 0, 0.6); bar.add_theme_stylebox_override("background", back)
		v.add_child(bar)
		v.position = to_screen(a.position + Vector2(0, 6)) - Vector2(75, 0)
		bars.add_child(v)
	var me := battle_root.get_node_or_null("me") as Actor
	if me:
		var hp := _label("你  生命 %s/%s" % [_n(_var("player.hp", "?")), _n((specs.get("player.hp", {}) as Dictionary).get("max", "?"))], 14, LAMP)
		hp.position = to_screen(me.position + Vector2(0, 6)) - Vector2(60, 0); bars.add_child(hp)


func _command(c: Dictionary) -> void:
	if str(c.get("prefill", "")) != "":
		_ask_words(str(c["prefill"]))
		return
	var line := str(c.get("says", ""))
	if c.get("target", false):
		var alive := []
		for fid in foes:
			if int(foes[fid]["hp"]) > 0:
				alive.append(fid)
		if alive.size() > 1:   # which one: a small ring of the foes still standing
			var list := []
			for fid in alive:
				list.append({"label": str(foes[fid]["name"]), "says": line.format({"target": foes[fid]["name"]}), "battle": true})
			_ring("对谁?", to_screen((foes[alive[0]]["node"] as Actor).position - Vector2(0, 30)), list, {})
			return
		line = line.format({"target": foes[alive[0]]["name"] if not alive.is_empty() else "对方"})
	_queue(line, "talk")


func _battle_end() -> void:
	_banner("战斗结束")
	await get_tree().create_timer(1.3).timeout
	in_battle = false; mode = "walk"
	_close_ring()
	battle_root.visible = false; town_root.visible = true
	_set_bg(zone.get("scene"))
	foes.clear(); _clear(bars)
	stage.get_node("deco").queue_redraw()


func _pop(a: Variant, d: float) -> void:
	if a == null or not is_instance_valid(a) or d == 0:
		return
	var n: Actor = a
	if d < 0:
		n.set("hurt", 0.5)
	var l := _label(("%+d" % int(d)), 30, BAD if d < 0 else MOSS, serif)
	l.add_theme_constant_override("outline_size", 6); l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	l.position = to_screen(n.position - Vector2(0, 50)) - Vector2(20, 0)
	pops.add_child(l)
	var tw := create_tween(); tw.set_parallel(true)
	tw.tween_property(l, "position:y", l.position.y - 60, 0.9).set_ease(Tween.EASE_OUT)
	tw.tween_property(l, "modulate:a", 0.0, 0.9).set_delay(0.4)
	tw.chain().tween_callback(l.queue_free)
	var shake := create_tween()
	for i in 4:
		shake.tween_property(stage, "position", Vector2(randf_range(-3, 3), randf_range(-2, 2)), 0.04)
	shake.tween_property(stage, "position", Vector2.ZERO, 0.04)


func _banner(text: String) -> void:
	banner.text = text
	var tw := create_tween()
	tw.tween_property(banner, "modulate:a", 1.0, 0.2)
	tw.tween_interval(1.0)
	tw.tween_property(banner, "modulate:a", 0.0, 0.4)


# ── dice: the host's own numbers (dice events), rolled on screen ─────────────────────────────────────────────────
func _roll_next() -> void:
	if dice_queue.is_empty():
		dice_running = false; dice_layer.visible = false
		return
	dice_running = true
	var r: Dictionary = dice_queue.pop_front()
	_clear(dice_layer)
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _box(Color("#141821"), Color(0.88, 0.64, 0.35, 0.5), 12, 22))
	p.set_anchors_preset(Control.PRESET_CENTER); p.offset_left = -170; p.offset_right = 170; p.offset_top = -170; p.offset_bottom = 110
	dice_layer.add_child(p)
	var v := VBoxContainer.new(); v.alignment = BoxContainer.ALIGNMENT_CENTER; v.add_theme_constant_override("separation", 8); p.add_child(v)
	var why := str(r.get("reason", r.get("request", "")))
	var t := _label(why, 15, INK, serif); t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; v.add_child(t)
	var die := _label("?", 64, Color("#2a2218"), serif); die.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var face := PanelContainer.new(); face.add_theme_stylebox_override("panel", _box(Color("#e6dbc2"), Color("#c9bc9f"), 14, 8)); face.custom_minimum_size = Vector2(120, 110)
	face.size_flags_horizontal = Control.SIZE_SHRINK_CENTER; face.add_child(die); v.add_child(face)
	var vs: Variant = r.get("vs")
	var aim := _label(("掷出 ≤ %s 成功" % _n(vs)) if vs != null else "", 13, MUTED); aim.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(aim)
	var out := _label("", 22, LAMP, serif); out.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(out)
	dice_layer.visible = true
	var sides := 100 if vs != null and float(vs) > 20 else 20   # a percentile check rolls d100, the combat layer d20
	for i in 14:
		die.text = str(randi() % sides + 1)
		await get_tree().create_timer(0.04 + i * 0.006).timeout
	var total: Variant = r.get("total")
	if total == null and r.get("rolls") is Array and not (r["rolls"] as Array).is_empty():
		total = r["rolls"][0]
	die.text = _n(total) if total != null else "·"
	var passed: Variant = r.get("passed")
	if passed != null:
		out.text = "成功" if bool(passed) else "失败"
		out.add_theme_color_override("font_color", MOSS if bool(passed) else BAD)
	await get_tree().create_timer(1.3).timeout
	_roll_next()


# ── map · toast · ending ─────────────────────────────────────────────────────────────────────────────────────────
func _open_map() -> void:
	_clear(map_layer)
	var m: Dictionary = pack.get("map", {})
	var area := TextureRect.new(); area.texture = art.texture(m.get("picture")); area.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	area.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED; area.set_anchors_preset(Control.PRESET_FULL_RECT)
	area.offset_left = 80; area.offset_right = -80; area.offset_top = 60; area.offset_bottom = -60
	map_layer.add_child(area)
	map_layer.visible = true
	await get_tree().process_frame
	var k := minf(area.size.x / 1280.0, area.size.y / 720.0)
	var origin := area.position + (area.size - Vector2(1280, 720) * k) / 2.0
	for id in (m.get("at", {}) as Dictionary):
		var at: Array = m["at"][id]
		var here := str(id) == zone_id or str(id).get_file() == zone_id.get_file()
		var b := Button.new(); b.text = ("● " if here else "") + str(_zone(str(id)).get("name", id)); b.add_theme_font_override("font", serif)
		if here:
			b.add_theme_stylebox_override("normal", _box(PANEL, LAMP, 6, 8))
		b.position = origin + Vector2(at[0] * 1280.0, at[1] * 720.0) * k - Vector2(40, 16)
		b.pressed.connect(_map_go.bind(str(id)))
		map_layer.add_child(b)
	var close := Button.new(); close.text = "关闭(Esc)"; close.position = Vector2(size.x - 180, 20); close.pressed.connect(func() -> void: map_layer.visible = false)
	map_layer.add_child(close)


func _map_go(id: String) -> void:
	map_layer.visible = false
	if id != zone_id:
		_say("我去%s。" % str(_zone(id).get("name", id)))


func _toast(text: String, color := INK) -> void:
	_clear(toast)
	toast.add_child(_label(text, 15, color))
	toast.visible = true
	toast.reset_size()
	toast.offset_left = -toast.size.x / 2.0; toast.offset_right = toast.size.x / 2.0
	await get_tree().create_timer(2.4).timeout
	toast.visible = false


func _show_ending(s: Dictionary) -> void:
	ended = true
	_clear(ending_layer)
	var id := str((s.get("exit", {}) as Dictionary).get("id", ""))
	var e: Dictionary = (pack.get("endings", {}) as Dictionary).get(id, {})
	var v := VBoxContainer.new(); v.set_anchors_preset(Control.PRESET_CENTER); v.offset_left = -360; v.offset_right = 360; v.offset_top = -200; v.offset_bottom = 200
	v.add_theme_constant_override("separation", 16); ending_layer.add_child(v)
	var h := _label("结局 · %s" % str(e.get("title", id)), 40, LAMP, serif); h.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(h)
	for t in [str(e.get("text", "")), str(s.get("epilogue", ""))]:
		if t != "":
			var l := _label(t, 18, INK, serif); l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(l)
	ending_layer.visible = true


# ── little helpers ───────────────────────────────────────────────────────────────────────────────────────────────
func _box(bgc: Color, border := Color(1, 1, 1, 0.12), radius := 8, pad := 10) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = bgc; b.border_color = border; b.set_border_width_all(1); b.set_corner_radius_all(radius)
	b.content_margin_left = pad + 4; b.content_margin_right = pad + 4; b.content_margin_top = pad; b.content_margin_bottom = pad
	return b


func _label(text: String, size_ := 15, color := INK, font: Font = null) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size_)
	l.add_theme_color_override("font_color", color)
	if font:
		l.add_theme_font_override("font", font)
	return l


func _full(c: Control) -> Control:
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	return c


func _overlay(color: Color) -> Control:
	var o := ColorRect.new(); o.color = color; add_child(_full(o)); return o


func _clear(c: Node) -> void:
	for ch in c.get_children():
		ch.queue_free()
