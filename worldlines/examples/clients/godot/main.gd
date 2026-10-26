# 灰橡宅 · the Godot game: title → play (scene · cast · dialogue · choices) · map · clues · ending.
# What the beats are comes from the host (beat_kinds); what the world looks like comes from its art pack
# (../art/<world>/art.json, shared with the TS example). Nothing here names a particular beat or world.
extends Control

const Client = preload("res://addons/worldlines/client.gd")
const ArtPack = preload("res://game/art.gd")
const DiceRules = preload("res://game/dice.gd")
const Town = preload("res://game/town/town.gd")

const INK := Color("#e9e3d7")
const MUTED := Color("#9ba2ae")
const LAMP := Color("#d9a75f")
const PLAN := Color("#86c9a4")
const RES := Color("#d98a6f")
const BAD := Color("#c25c52")
const PANEL := Color(0.05, 0.063, 0.086, 0.86)
const NIGHT := Color("#0d1016")

var client: Node
var art := ArtPack.new()
var rules := DiceRules.new()
var kinds := {}
var start := ""
var state := {}
var vars := {}
var clock := ""
var found := {}
var busy := false
var speaking := ""
var last_beat := ""
var seg := {}          # the block being written: {box, body, who, beat, raw}
var dice_queue: Array = []
var dice_running := false

var sans: SystemFont
var serif: SystemFont

# nodes
var scene_a: TextureRect
var scene_b: TextureRect
var title: Control
var title_art: TextureRect
var host_in: LineEdit
var token_in: LineEdit
var title_msg: Label
var play: Control
var place_lbl: Label
var clock_lbl: Label
var beat_lbl: Label
var meters: HBoxContainer
var clue_btn: Button
var cast: HBoxContainer
var log_scroll: ScrollContainer
var log_box: VBoxContainer
var choices: VBoxContainer
var say: LineEdit
var send_btn: Button
var stop_btn: Button
var sugg: HBoxContainer
var dice_layer: Control
var toast: PanelContainer
var map_layer: Control
var clue_layer: Control
var ending_layer: Control


func _ready() -> void:
	sans = SystemFont.new(); sans.font_names = PackedStringArray(["Hiragino Sans GB", "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", "Sans-Serif"])   # Hiragino first: PingFang SC can resolve on macOS yet fail to load, leaving every label blank
	serif = SystemFont.new(); serif.font_names = PackedStringArray(["Songti SC", "Noto Serif CJK SC", "SimSun", "Serif"])
	theme = _theme()
	client = Client.new()
	add_child(client)
	client.chunk.connect(_on_chunk)
	client.beat.connect(_on_beat)
	client.ask_user.connect(_on_ask)
	client.turn_started.connect(func() -> void: seg = {}; last_beat = "")
	client.failed.connect(_on_failed)
	client.connection.connect(_on_connection)
	client.beat_kinds_loaded.connect(func(k: Dictionary) -> void:
		kinds = k.get("kinds", {})
		start = str(k.get("start", "")))
	_build()
	_show_title(OS.get_environment("WL_WORLD") if OS.get_environment("WL_WORLD") != "" else "pct-house")


func _on_failed(message: String) -> void:
	if title.visible:
		title_msg.text = message
	else:
		_note(message)


func _on_connection(s: String, detail: String) -> void:
	if s == "retrying" and not title.visible:
		_note("和主进程断开了,正在重连…(%s)" % detail)


# ── look ─────────────────────────────────────────────────────────────────────────────────────────────────────────
func _box(bg: Color, border := Color(1, 1, 1, 0.12), radius := 8, pad := 10) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = bg; b.border_color = border; b.set_border_width_all(1); b.set_corner_radius_all(radius)
	b.content_margin_left = pad + 4; b.content_margin_right = pad + 4; b.content_margin_top = pad; b.content_margin_bottom = pad
	return b


func _theme() -> Theme:
	var t := Theme.new()
	t.default_font = sans
	t.default_font_size = 15
	t.set_color("font_color", "Label", INK)
	t.set_color("font_color", "Button", INK)
	t.set_color("font_hover_color", "Button", LAMP)
	t.set_stylebox("normal", "Button", _box(Color(0.92, 0.89, 0.84, 0.06), Color(1, 1, 1, 0.14), 6, 7))
	t.set_stylebox("hover", "Button", _box(Color(0.85, 0.65, 0.37, 0.16), Color(0.85, 0.65, 0.37, 0.5), 6, 7))
	t.set_stylebox("pressed", "Button", _box(Color(0.85, 0.65, 0.37, 0.24), LAMP, 6, 7))
	t.set_stylebox("focus", "Button", _box(Color(0, 0, 0, 0), LAMP, 6, 7))
	t.set_stylebox("normal", "LineEdit", _box(Color(0, 0, 0, 0.45), Color(1, 1, 1, 0.14), 6, 8))
	t.set_stylebox("focus", "LineEdit", _box(Color(0, 0, 0, 0.45), LAMP, 6, 8))
	t.set_color("font_color", "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", MUTED)
	t.set_stylebox("panel", "PanelContainer", _box(PANEL))
	return t


func _label(text: String, size := 15, color := INK, font: Font = null) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if font:
		l.add_theme_font_override("font", font)
	return l


func _full(c: Control) -> Control:
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	return c


# ── layout ───────────────────────────────────────────────────────────────────────────────────────────────────────
func _build() -> void:
	var bg := ColorRect.new(); bg.color = NIGHT; add_child(_full(bg))
	scene_a = _scene_rect(); scene_b = _scene_rect(); scene_b.modulate.a = 0
	var shade := TextureRect.new(); shade.texture = _gradient([Color(0, 0, 0, 0), Color(0.03, 0.04, 0.055, 0.82)]); shade.stretch_mode = TextureRect.STRETCH_SCALE
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(shade))

	# title
	title = _full(Control.new()); add_child(title)
	title_art = TextureRect.new(); title_art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; title_art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	title.add_child(_full(title_art))
	var left := TextureRect.new(); left.texture = _gradient([Color(0.03, 0.04, 0.055, 0.9), Color(0.03, 0.04, 0.055, 0)], true); left.stretch_mode = TextureRect.STRETCH_SCALE
	title.add_child(_full(left))
	var card := VBoxContainer.new(); card.position = Vector2(80, 0); card.size = Vector2(460, 0)
	card.set_anchors_preset(Control.PRESET_BOTTOM_LEFT); card.offset_left = 80; card.offset_bottom = -90; card.offset_top = -380; card.offset_right = 560
	card.add_theme_constant_override("separation", 10)
	title.add_child(card)
	card.add_child(_label("", 64, INK, serif)); card.add_child(_label("", 13, LAMP))
	var pitch := _label("", 16, Color(0.91, 0.89, 0.84, 0.82), serif); pitch.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; card.add_child(pitch)
	var row := HBoxContainer.new(); card.add_child(row)
	host_in = LineEdit.new(); host_in.text = OS.get_environment("WL_HOST") if OS.get_environment("WL_HOST") != "" else "http://127.0.0.1:8788"; host_in.custom_minimum_size.x = 190
	token_in = LineEdit.new(); token_in.secret = true; token_in.placeholder_text = "主进程的令牌"; token_in.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	token_in.text = OS.get_environment("WL_TOKEN")
	var go := Button.new(); go.text = "  进入  "; go.add_theme_color_override("font_color", Color("#1b1408"))
	go.add_theme_stylebox_override("normal", _box(LAMP, LAMP, 6, 7)); go.pressed.connect(_connect)
	token_in.text_submitted.connect(func(_t: String) -> void: _connect())
	row.add_child(host_in); row.add_child(token_in); row.add_child(go)
	title_msg = _label("", 13, MUTED); card.add_child(title_msg)

	# play
	play = _full(Control.new()); play.visible = false; add_child(play)
	cast = HBoxContainer.new(); cast.set_anchors_preset(Control.PRESET_BOTTOM_LEFT); cast.offset_left = 40; cast.offset_top = -640; cast.offset_right = 640; cast.offset_bottom = 0
	cast.alignment = BoxContainer.ALIGNMENT_BEGIN; cast.mouse_filter = Control.MOUSE_FILTER_IGNORE; play.add_child(cast)
	var hud := HBoxContainer.new(); hud.set_anchors_preset(Control.PRESET_TOP_WIDE); hud.offset_left = 22; hud.offset_right = -22; hud.offset_top = 14
	hud.add_theme_constant_override("separation", 14); play.add_child(hud)
	place_lbl = _label("", 18, INK, serif); clock_lbl = _label("", 13, MUTED); beat_lbl = _label("", 12, MUTED)
	hud.add_child(place_lbl); hud.add_child(clock_lbl); hud.add_child(beat_lbl)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hud.add_child(spacer)
	meters = HBoxContainer.new(); meters.add_theme_constant_override("separation", 14); hud.add_child(meters)
	clue_btn = Button.new(); clue_btn.text = "线索 0"; clue_btn.pressed.connect(func() -> void: clue_layer.visible = true); hud.add_child(clue_btn)
	var map_btn := Button.new(); map_btn.text = "地图"; map_btn.pressed.connect(_open_map); hud.add_child(map_btn)

	var panel := VBoxContainer.new(); panel.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	panel.offset_left = -760; panel.offset_right = -40; panel.offset_top = -560; panel.offset_bottom = -28
	panel.add_theme_constant_override("separation", 8); play.add_child(panel)
	var log_panel := PanelContainer.new(); log_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL; panel.add_child(log_panel)
	log_scroll = ScrollContainer.new(); log_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; log_panel.add_child(log_scroll)
	log_box = VBoxContainer.new(); log_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; log_box.add_theme_constant_override("separation", 14); log_scroll.add_child(log_box)
	choices = VBoxContainer.new(); panel.add_child(choices)
	var compose := HBoxContainer.new(); panel.add_child(compose)
	say = LineEdit.new(); say.size_flags_horizontal = Control.SIZE_EXPAND_FILL; say.placeholder_text = "说你想做什么"
	say.text_submitted.connect(func(t: String) -> void: _play(t))
	send_btn = Button.new(); send_btn.text = " 说 "; send_btn.add_theme_color_override("font_color", Color("#1b1408")); send_btn.add_theme_stylebox_override("normal", _box(LAMP, LAMP, 6, 7))
	send_btn.pressed.connect(func() -> void: _play(say.text))
	stop_btn = Button.new(); stop_btn.text = "■ 停"; stop_btn.visible = false; stop_btn.add_theme_color_override("font_color", BAD); stop_btn.pressed.connect(func() -> void: client.cancel())
	compose.add_child(say); compose.add_child(send_btn); compose.add_child(stop_btn)
	sugg = HBoxContainer.new(); panel.add_child(sugg)

	dice_layer = _overlay(Color(0.02, 0.025, 0.035, 0.55)); dice_layer.visible = false
	toast = PanelContainer.new(); toast.add_theme_stylebox_override("panel", _box(PANEL, Color(0.85, 0.65, 0.37, 0.5)))
	toast.set_anchors_preset(Control.PRESET_CENTER_TOP); toast.offset_top = 70; toast.visible = false; add_child(toast)
	map_layer = _overlay(Color(0.02, 0.025, 0.035, 0.8)); map_layer.visible = false
	clue_layer = _overlay(Color(0.02, 0.025, 0.035, 0.8)); clue_layer.visible = false
	ending_layer = _overlay(Color(0.02, 0.025, 0.035, 1)); ending_layer.visible = false


func _scene_rect() -> TextureRect:
	var t := TextureRect.new(); t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(_full(t)); return t


func _overlay(color: Color) -> Control:
	var o := ColorRect.new(); o.color = color; add_child(_full(o)); return o


func _gradient(stops: Array, horizontal := false) -> GradientTexture2D:
	var g := Gradient.new(); g.set_color(0, stops[0]); g.set_color(1, stops[1])
	var t := GradientTexture2D.new(); t.gradient = g; t.width = 8; t.height = 8
	t.fill_from = Vector2(0, 0); t.fill_to = Vector2(1, 0) if horizontal else Vector2(0, 1)
	return t


# ── title · connect ──────────────────────────────────────────────────────────────────────────────────────────────
func _show_title(world: String) -> void:
	art.load_world(world)
	var p := art.pack
	title_art.texture = art.texture(p.get("title_art"))
	var card := title.get_child(2) as VBoxContainer
	(card.get_child(0) as Label).text = str(p.get("title", "WorldLines"))
	(card.get_child(1) as Label).text = str(p.get("subtitle", ""))
	(card.get_child(2) as Label).text = str(p.get("pitch", ""))


func _connect() -> void:
	title_msg.text = "连接中……"
	if not await client.connect_to_host(host_in.text, token_in.text):
		return
	var tpl: Variant = await client.get_json("/api/v1/play/engine/template", {})
	var world := str(((tpl if tpl is Dictionary else {}) as Dictionary).get("template", {}).get("id", "")) if tpl is Dictionary and tpl.get("template") is Dictionary else ""
	if world != "" and world != str(art.pack.get("world", "")):
		_show_title(world)
	title.visible = false
	if str(art.pack.get("game", "")) == "town":   # a walkable town (石津镇): its own screen on the same client node
		_hand_off_to_town()
		return
	play.visible = true
	await _refresh()
	_hints()
	_note(str(art.pack.get("pitch", "")))
	say.grab_focus()


func _hand_off_to_town() -> void:
	for sig in [[client.chunk, _on_chunk], [client.beat, _on_beat], [client.ask_user, _on_ask]]:
		if (sig[0] as Signal).is_connected(sig[1]):
			(sig[0] as Signal).disconnect(sig[1])
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_size(Vector2i(1600, 900))
	var t: Control = Town.new()
	t.setup(client, art, kinds, start, sans, serif)
	t.theme = theme
	add_child(t)


# ── the world on screen ──────────────────────────────────────────────────────────────────────────────────────────
func _refresh() -> void:
	var s: Variant = await client.get_json("/state", {})
	if s is Dictionary and not (s as Dictionary).is_empty():
		state = s
	var sc: Variant = await client.get_json("/api/v1/play/schema", {})
	vars = {}
	if sc is Dictionary:
		for v in sc.get("variables", []):
			vars[str(v.get("name"))] = v.get("value")
	var here := str(state.get("player_location", ""))
	place_lbl.text = str((state.get("places", {}) as Dictionary).get(here, here))
	clock_lbl.text = clock if clock != "" else str(vars.get("time.clock", ""))
	_set_scene(here)
	_draw_cast(here)
	_draw_meters()
	_draw_clues()
	var ending: Variant = await client.get_json("/api/v1/play/engine/settlement", {})
	if ending is Dictionary and ending.has("exit"):
		_show_ending(ending)


var _scene_key := ""
func _set_scene(place: String) -> void:
	var own := art.scene(place)
	var tex := own if own else art.texture(art.pack.get("fallback_scene", art.pack.get("title_art")))
	var key := place + str(tex)
	if key == _scene_key:
		return
	_scene_key = key
	var show := scene_b if scene_a.modulate.a > 0.5 else scene_a
	var hide := scene_a if show == scene_b else scene_b
	show.texture = tex
	show.self_modulate = Color(1, 1, 1) if own else Color(0.42, 0.44, 0.5)   # a stand-in (the key art) is dimmed
	var tw := create_tween().set_parallel()
	tw.tween_property(show, "modulate:a", 1.0, 1.0)
	tw.tween_property(hide, "modulate:a", 0.0, 1.0)


func _draw_cast(place: String) -> void:
	for c in cast.get_children():
		c.queue_free()
	var names := art.npcs_at(place)
	for so in state.get("souls", []):
		if str(so.get("location", "")) == place and not names.has(str(so.get("name"))):
			names.append(str(so.get("name")))
	for n in names:
		var fig := VBoxContainer.new(); fig.name = "actor_" + str(n).md5_text().substr(0, 8); fig.set_meta("who", n)
		fig.alignment = BoxContainer.ALIGNMENT_END; fig.size_flags_vertical = Control.SIZE_FILL
		var tex := art.portrait_of(n)
		if tex:
			var r := TextureRect.new(); r.texture = tex; r.expand_mode = TextureRect.EXPAND_FIT_WIDTH_PROPORTIONAL; r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
			r.custom_minimum_size = Vector2(0, 600); fig.add_child(r)
		else:
			var sil := ColorRect.new(); sil.color = Color(0.92, 0.89, 0.84, 0.07); sil.custom_minimum_size = Vector2(170, 460); fig.add_child(sil)
		var cap := _label(n, 13, MUTED, serif); cap.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; fig.add_child(cap)
		cast.add_child(fig)
	_highlight(speaking)


func _highlight(who: String) -> void:
	speaking = who
	for f in cast.get_children():
		var on: bool = who != "" and str(f.get_meta("who", "")) == who
		create_tween().tween_property(f, "modulate", Color(1, 1, 1) if on else Color(0.55, 0.55, 0.6), 0.35)


func _draw_meters() -> void:
	for c in meters.get_children():
		c.queue_free()
	var defs: Dictionary = art.pack.get("meters", {"player.hp": {"label": "HP", "max": 10}})
	for key in defs:
		var val: Variant = vars.get(key)
		if val == null:
			continue
		var maxv := float(defs[key].get("max", 100))
		if key == "player.hp" and state.get("player_hp") is Dictionary:
			maxv = float(state["player_hp"].get("max", maxv))
		var row := HBoxContainer.new()
		row.add_child(_label(str(defs[key].get("label", key)), 12, MUTED))
		var bar := ProgressBar.new(); bar.min_value = 0; bar.max_value = maxv; bar.value = float(val); bar.show_percentage = false
		bar.custom_minimum_size = Vector2(86, 6); bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar.add_theme_stylebox_override("background", _box(Color(1, 1, 1, 0.12), Color(0, 0, 0, 0), 3, 0))
		bar.add_theme_stylebox_override("fill", _box(LAMP, Color(0, 0, 0, 0), 3, 0))
		row.add_child(bar); row.add_child(_label(str(int(round(float(val)))), 13))
		meters.add_child(row)


func _draw_clues() -> void:
	var clues: Array = art.pack.get("clues", [])
	clue_btn.visible = not clues.is_empty()
	for c in clues:
		var w: Dictionary = c.get("when", {})
		if float(vars.get(str(w.get("var", "")), -1)) >= float(w.get("gte", 0)) and not found.has(c["id"]):
			found[c["id"]] = true
			_toast("获得线索", str(c.get("title", "")))
	clue_btn.text = "线索 %d" % found.size()
	for ch in clue_layer.get_children():
		ch.queue_free()
	var sheet := _sheet(clue_layer, "线索")
	var grid := GridContainer.new(); grid.columns = 3; grid.add_theme_constant_override("h_separation", 14); grid.add_theme_constant_override("v_separation", 14); sheet.add_child(grid)
	for c in clues:
		var got := found.has(c["id"])
		var card := VBoxContainer.new(); card.custom_minimum_size = Vector2(240, 0)
		var tex := art.texture(c.get("art")) if got else null
		if tex:
			var r := TextureRect.new(); r.texture = tex; r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED; r.custom_minimum_size = Vector2(240, 272); card.add_child(r)
		else:
			var ph := PanelContainer.new(); ph.custom_minimum_size = Vector2(240, 272); var q := _label("🔍" if got else "？", 34, MUTED); q.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; q.vertical_alignment = VERTICAL_ALIGNMENT_CENTER; ph.add_child(q); card.add_child(ph)
		card.add_child(_label(str(c.get("title", "")) if got else "还没找到", 15, INK if got else MUTED, serif))
		if got:
			var t := _label(str(c.get("text", "")), 13, MUTED, serif); t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; t.custom_minimum_size.x = 240; card.add_child(t)
		grid.add_child(card)


func _sheet(layer: Control, heading: String) -> VBoxContainer:
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _box(Color("#12161e"), Color(1, 1, 1, 0.12), 12, 22))
	p.set_anchors_preset(Control.PRESET_CENTER); p.offset_left = -480; p.offset_right = 480; p.offset_top = -300; p.offset_bottom = 300
	layer.add_child(p)
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 14); p.add_child(v)
	var top := HBoxContainer.new(); v.add_child(top)
	var h := _label(heading, 20, INK, serif); h.size_flags_horizontal = Control.SIZE_EXPAND_FILL; top.add_child(h)
	var x := Button.new(); x.text = "×"; x.pressed.connect(func() -> void: layer.visible = false); top.add_child(x)
	return v


func _toast(kind: String, text: String) -> void:
	for c in toast.get_children():
		c.queue_free()
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12)
	row.add_child(_label(kind, 12, LAMP)); row.add_child(_label(text, 16, INK, serif))
	toast.add_child(row)
	toast.visible = true
	await get_tree().create_timer(2.6).timeout
	toast.visible = false


# ── the dialogue ─────────────────────────────────────────────────────────────────────────────────────────────────
func _kind(b: String) -> Dictionary:
	return kinds.get(b, {}) if b != "" else {}


func _block(color: Color, who: String, text := "", italic := false) -> Dictionary:
	var box := VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(_label(who, 12, color))
	var body := _label(text, 16, Color(0.91, 0.89, 0.84, 0.7) if italic else INK, serif)
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("line_spacing", 6)
	box.add_child(body)
	log_box.add_child(box)
	_scroll()
	return {"box": box, "body": body}


func _note(text: String) -> void:
	if text != "":
		_block(MUTED, "", text)


func _scroll() -> void:
	await get_tree().process_frame
	log_scroll.scroll_vertical = int(log_scroll.get_v_scroll_bar().max_value)


func _on_chunk(text: String, who: String, b: String) -> void:
	if seg.is_empty() or seg["who"] != who or seg["beat"] != b:
		var div := ""
		if b != "" and last_beat != "" and b != last_beat:
			div = str((_kind(b).get("divider_from", {}) as Dictionary).get(last_beat, ""))
		if div != "":
			var d := _label("—— %s ——" % div, 12, MUTED); d.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; log_box.add_child(d)
		if b != "":
			last_beat = b
			beat_lbl.text = str(_kind(b).get("label", b))
			beat_lbl.add_theme_color_override("font_color", {"plan": PLAN, "res": RES}.get(str(_kind(b).get("tone", "")), MUTED))
		var tone := str(_kind(b).get("tone", ""))
		var col: Color = LAMP if who != "" else {"plan": PLAN, "res": RES}.get(tone, MUTED)
		var head := who if who != "" else str(_kind(b).get("live", ("主持 · " + str(_kind(b).get("label", b))) if b != "" else "主持"))
		seg = _block(col, head)
		seg["who"] = who; seg["beat"] = b; seg["raw"] = ""
		_highlight(who)
	seg["raw"] += text
	seg["raw"] = _lift_away(seg["raw"], seg["box"], false)
	var lifted: Dictionary = rules.lift(seg["raw"])
	if not (lifted["rolls"] as Array).is_empty():
		seg["raw"] = lifted["rest"]
		for r in lifted["rolls"]:
			_chip(seg["box"], "%s %s %d/%d · %s" % [r["who"], r["skill"], r["roll"], r["target"], r["outcome"]], LAMP if r["good"] else BAD)
		dice_queue.append_array(lifted["rolls"])
		if not dice_running:
			_roll_next()
	(seg["body"] as Label).text = str(seg["raw"]).lstrip("\n")
	if who == "":
		var m := RegEx.create_from_string("(?:^|\\n)([^\\n:：「]{1,8})[:：]「[^」]*$").search(str(seg["raw"]))
		if m and (art.pack.get("speakers", {}) as Dictionary).has(m.get_string(1)):
			_highlight(m.get_string(1))
	_scroll()


# "// 异地 · 温妮 @ 门厅:…" — a character's turn somewhere else — folded under the block
func _lift_away(raw: String, at: Control, final: bool) -> String:
	var re := RegEx.create_from_string("(?:^|\\n)// ([^·\\n]+) · ([^@\\n]+?) @ ([^:：\\n]+)[:：]([^\\n]*)(?=\\n|$)")
	var out := raw
	for m in re.search_all(raw):
		if not final and m.get_end() >= raw.length():
			continue   # the line may still be arriving
		var who := m.get_string(2).strip_edges(); var where := m.get_string(3).strip_edges(); var said := m.get_string(4).strip_edges()
		var b := Button.new(); b.flat = true; b.alignment = HORIZONTAL_ALIGNMENT_LEFT; b.text = "✓ %s  @ %s" % [who, where]; b.add_theme_color_override("font_color", MUTED)
		var p := _label(said, 14, Color(0.91, 0.89, 0.84, 0.75), serif); p.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; p.visible = false
		b.pressed.connect(func() -> void: p.visible = not p.visible)
		at.add_child(b); at.add_child(p)
		out = out.replace(m.get_string(0), "")
	return out


func _chip(at: Control, text: String, color := MUTED) -> void:
	var flow: HFlowContainer = at.get_node_or_null("chips")
	if flow == null:
		flow = HFlowContainer.new(); flow.name = "chips"; at.add_child(flow)
	flow.add_child(_label(" %s " % text, 12, color))


func _on_beat(event: String, data: Dictionary) -> void:
	if seg.is_empty():
		return
	if event == "state.changed":
		for o in data.get("applied", []):
			if not (o is Dictionary) or not o.has("var"):
				continue
			if o["var"] == "time.clock":
				clock = str(o.get("to", ""))
				continue
			var m: Variant = (art.pack.get("meters", {}) as Dictionary).get(o["var"])
			if m == null:
				continue   # only what the player can read; plot stages show as clues
			var delta := float(o.get("to", 0)) - float(o.get("from", 0))
			_chip(seg["box"], "%s %s%d" % [m.get("label", ""), "+" if delta > 0 else "", int(delta)], BAD if delta < 0 else PLAN)


func _roll_next() -> void:
	if dice_queue.is_empty():
		dice_running = false
		dice_layer.visible = false
		return
	dice_running = true
	var r: Dictionary = dice_queue.pop_front()
	for c in dice_layer.get_children():
		c.queue_free()
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _box(Color("#161a23"), Color(0.85, 0.65, 0.37, 0.4), 12, 24))
	p.set_anchors_preset(Control.PRESET_CENTER); p.offset_left = -160; p.offset_right = 160; p.offset_top = -150; p.offset_bottom = 150
	dice_layer.add_child(p)
	var v := VBoxContainer.new(); v.alignment = BoxContainer.ALIGNMENT_CENTER; v.add_theme_constant_override("separation", 8); p.add_child(v)
	var t := _label("%s · %s" % [r["who"], r["skill"]], 16, INK, serif); t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(t)
	var why := _label(str(r["why"]), 12, MUTED); why.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(why)
	var pair := HBoxContainer.new(); pair.alignment = BoxContainer.ALIGNMENT_CENTER; pair.add_theme_constant_override("separation", 12); v.add_child(pair)
	var tens := _die(pair); var units := _die(pair)
	var total := _label("", 48, INK, serif); total.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(total)
	var target := _label("目标 %s %d" % [r["op"], r["target"]], 13, MUTED); target.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(target)
	var out := _label("", 22, LAMP if r["good"] else BAD, serif); out.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(out)
	dice_layer.visible = true
	for i in 14:
		tens.text = "%02d" % (randi() % 10 * 10); units.text = str(randi() % 10)
		await get_tree().create_timer(0.045 + i * 0.006).timeout
	var roll := int(r["roll"])
	tens.text = "00" if roll == 100 else "%02d" % (roll / 10 * 10); units.text = str(roll % 10)
	total.text = str(roll); out.text = str(r["outcome"])
	await get_tree().create_timer(1.5).timeout
	_roll_next()


func _die(parent: Control) -> Label:
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _box(Color("#e3d8c0"), Color("#c9bc9f"), 10, 6)); p.custom_minimum_size = Vector2(74, 74)
	var l := _label("0", 32, Color("#2a2218"), serif); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	p.add_child(l); parent.add_child(p)
	return l


func _on_ask(id: Variant, question: String, options: Array) -> void:
	_clear(choices)
	choices.add_child(_label(question, 14, LAMP))
	for o in options:
		var b := Button.new(); b.text = "›  " + str(o); b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.pressed.connect(func() -> void: _clear(choices); client.answer(id, o))
		choices.add_child(b)


func _clear(c: Node) -> void:
	for ch in c.get_children():
		ch.queue_free()


func _hints() -> void:
	say.placeholder_text = str(_kind(start).get("placeholder", "说你想做什么"))
	_clear(sugg)
	for c in _kind(start).get("chips", []):
		var b := Button.new(); b.text = str(c); b.add_theme_font_size_override("font_size", 12); b.pressed.connect(func() -> void: _play(str(c)))
		sugg.add_child(b)


func _options_in(text: String) -> Array:
	var out := []
	for m in RegEx.create_from_string("[①②③④⑤]\\s*([^①②③④⑤\\n]+)").search_all(text):
		out.append(m.get_string(1).strip_edges())
	if out.is_empty():
		for m in RegEx.create_from_string("(?:^|\\n)\\s*\\d+[.、]\\s*([^\\n]+)").search_all(text):
			out.append(m.get_string(1).strip_edges())
		if out.size() < 2:
			out = []
	return out


func _play(text: String) -> void:
	text = text.strip_edges()
	if text == "" or busy:
		return
	busy = true; say.text = ""; say.editable = false; send_btn.visible = false; stop_btn.visible = true
	_clear(choices)
	var you := str(_kind(start).get("you", ""))
	_block(INK, "你 · " + you if you != "" else "你", text, true)
	var r: Dictionary = await client.send_line(text)
	if not r.get("success", false):
		_note("这一句没跑完:%s" % str(r.get("error", "未知错误")))
	elif str(r.get("assistant_message", "")) == "" and seg.is_empty():
		_note("世界没有回应 —— 看一下主进程的日志(模型连得上吗?)")
	for line in log_box.get_children():   # the turn is over: fold what was still open
		if line is VBoxContainer and line.get_child_count() > 1 and line.get_child(1) is Label:
			var body := line.get_child(1) as Label
			body.text = _lift_away(body.text, line, true).rstrip("\n")
	var opts: Array = r.get("options", []) if r.get("options") is Array and not (r.get("options") as Array).is_empty() else _options_in(str(r.get("assistant_message", "")))
	for o in opts.slice(0, 4):
		for part in str(o).split("|"):
			var label := part.strip_edges()
			if label == "":
				continue
			var b := Button.new(); b.text = "›  " + label; b.alignment = HORIZONTAL_ALIGNMENT_LEFT; b.add_theme_font_override("font", serif)
			b.pressed.connect(func() -> void: _play(label))
			choices.add_child(b)
	seg = {}; busy = false; say.editable = true; send_btn.visible = true; stop_btn.visible = false
	_highlight("")
	await _refresh()
	_hints()
	say.grab_focus()


# ── map · ending ─────────────────────────────────────────────────────────────────────────────────────────────────
func _open_map() -> void:
	_clear(map_layer)
	var sheet := _sheet(map_layer, str(art.pack.get("title", "地图")))
	var m: Dictionary = art.pack.get("map", {})
	var area := Control.new(); area.custom_minimum_size = Vector2(900, 506); sheet.add_child(area)
	var tex := art.texture(m.get("art"))
	if tex:
		var r := TextureRect.new(); r.texture = tex; r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED; area.add_child(_full(r))
	else:
		var grid := ColorRect.new(); grid.color = Color("#171c26"); area.add_child(_full(grid))
		var rooms: Dictionary = m.get("rooms", {})
		area.draw.connect(func() -> void:
			for l in m.get("links", []):
				var a: Dictionary = rooms.get(l[0], {}); var b: Dictionary = rooms.get(l[1], {})
				if not a.is_empty() and not b.is_empty():
					area.draw_dashed_line(Vector2(a["x"], a["y"]) * area.size / 100.0, Vector2(b["x"], b["y"]) * area.size / 100.0, Color(0.85, 0.65, 0.37, 0.4), 2.0, 8.0))
		grid.show_behind_parent = true
	var here := str(state.get("player_location", ""))
	for id in (m.get("rooms", {}) as Dictionary):
		var room: Dictionary = m["rooms"][id]
		var b := Button.new(); b.text = str(room.get("label", id)) + ("\n你在这里" if id == here else "")
		b.add_theme_font_override("font", serif)
		if id == here:
			b.add_theme_stylebox_override("normal", _box(PANEL, LAMP, 6, 10))
		area.add_child(b)
		var at := Vector2(room["x"], room["y"]) * Vector2(900, 506) / 100.0
		b.resized.connect(func() -> void: b.position = at - b.size / 2.0)   # centred on its spot once its size is known
		b.position = at
		var go := str(room.get("go", ""))
		b.pressed.connect(func() -> void:
			map_layer.visible = false
			if go != "" and id != here:
				_play(go))
	map_layer.visible = true
	area.queue_redraw()


func _show_ending(s: Dictionary) -> void:
	_clear(ending_layer)
	var id := str((s.get("exit", {}) as Dictionary).get("id", ""))
	var tex := art.texture((art.pack.get("endings", {}) as Dictionary).get(id))
	if tex:
		var r := TextureRect.new(); r.texture = tex; r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED; ending_layer.add_child(_full(r))
	var shade := TextureRect.new(); shade.texture = _gradient([Color(0, 0, 0, 0), Color(0.02, 0.025, 0.035, 0.95)]); shade.stretch_mode = TextureRect.STRETCH_SCALE; ending_layer.add_child(_full(shade))
	var v := VBoxContainer.new(); v.set_anchors_preset(Control.PRESET_CENTER_BOTTOM); v.offset_left = -330; v.offset_right = 330; v.offset_top = -300; v.offset_bottom = -60
	v.add_theme_constant_override("separation", 12); ending_layer.add_child(v)
	var kind := str((s.get("exit", {}) as Dictionary).get("kind", ""))
	var h := _label("结局 " + id if kind == "ending" else ("你倒下了" if kind == "death" else "理智崩溃"), 34, LAMP, serif); h.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(h)
	for t in [str(s.get("epilogue", "")), str((s.get("truth_reveal", {}) as Dictionary).get("text", "")) if s.get("truth_reveal") is Dictionary else ""]:
		if t != "":
			var l := _label(t, 16, INK, serif); l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; v.add_child(l)
	var back := Button.new(); back.text = "回到标题"; back.pressed.connect(func() -> void: ending_layer.visible = false; play.visible = false; title.visible = true); v.add_child(back)
	ending_layer.visible = true
