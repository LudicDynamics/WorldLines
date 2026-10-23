# Builds the 石津镇 town screen from the art pack with a made-up host state (no host needed): a street, walking,
# the ring of approaches, a line of prose, a fight. WL_SHOTS=<dir> (with a window) saves a screenshot of each.
extends SceneTree

const ArtPack = preload("res://game/art.gd")
const Town = preload("res://game/town/town.gd")

var shots := OS.get_environment("WL_SHOTS")


func _initialize() -> void:
	_go()


func _shot(t: Control, name: String) -> void:
	if shots == "":
		return
	await process_frame
	await process_frame
	root.get_texture().get_image().save_png(shots.path_join("town-%s.png" % name))


func _go() -> void:
	await process_frame
	if shots != "":
		DisplayServer.window_set_size(Vector2i(1600, 900))
	var art := ArtPack.new()
	var ok := art.load_world("stoneford-town")
	var sans := SystemFont.new(); sans.font_names = PackedStringArray(["PingFang SC", "Noto Sans CJK SC", "Sans-Serif"])
	var serif := SystemFont.new(); serif.font_names = PackedStringArray(["Songti SC", "Noto Serif CJK SC", "Serif"])
	var t: Control = Town.new()
	t.setup(null, art, {"resolve": {"label": "清算拍", "tone": "res", "host": "主持 · 清算拍"}}, "resolve", sans, serif)
	root.add_child(t)
	await process_frame
	t.state = {"player_location": "T001/main_street", "souls": [{"name": "艾琳娜", "location": "T001/main_street"}], "places": {}}
	t.vars = {"time.day": 5, "time.clock": "22:20", "P20.pass": 1, "P20.route": 0, "P20.road": 0, "player.hp": 12, "player.silver": 8}
	t.specs = {"player.hp": {"max": 12}}
	await t._enter_zone("T001/main_street", "T001/guild")
	await create_timer(0.4).timeout
	var built: bool = t.player != null and t.people.size() == 1 and t.bg.texture != null
	print("pack: ", ok, " · street built: ", built, " · scene: ", t.bg.texture != null, " · people: ", t.people.map(func(p: Dictionary) -> String: return p["who"]))
	print("spawned by the guild door: ", t.player.position.distance_to(Vector2(126, 170)) < 60, " · fog: ", t.hud_fog.text, " · goals: ", t.goals_box.get_child_count())
	await _shot(t, "street")

	t.move_to = Vector2(300, 200)   # walk
	await create_timer(2.6).timeout
	print("walked: ", t.player.position.distance_to(Vector2(300, 200)) < 6, " · stays on the street: ", t.can_stand(t.player.position), " · fountain blocked: ", not t.can_stand(Vector2(226, 155)))

	await t._enter_zone("T001/gate_north", "T001/main_street")
	await create_timer(0.4).timeout
	t.player.position = Vector2(318, 168)
	await create_timer(0.15).timeout
	print("by 卡斯: ", t.target.get("who", ""), " · prompt: ", t.prompt_lbl.text)
	t._open_ring(t.target)
	print("no free-text box while walking: ", not (t.dlg.find_child("compose", true, false) as Control).visible)
	var labels := []
	for c in t.ring.get_children():
		if c is Button and c.has_meta("n"):
			labels.append((c as Button).text)
	print("ring: ", labels)
	await _shot(t, "ring")
	t._start_talk(t.target)
	t._close_ring()

	t._on_chunk("卡斯把长矛横过来,头盔歪到一边。\n卡斯:「没公会委托,往北一步都不行。」", "", "resolve")
	t._show_options(["问他雾退以后北路通到哪", "塞给他两枚银币", "回镇上去"])
	t._own_words(t.talk_with)
	await _shot(t, "dialogue")
	print("dialogue: ", t.dlg_box.get_child_count() > 0, " · options: ", t.opts_box.get_child_count(), " · portrait: ", t.dlg_face.texture != null, " · own words open in the talk: ", t.input.text)
	t._hide_input(); t._end_talk()

	await t._enter_zone("T001/road_camp", "T001/gate_north")
	t.vars["foe.bandit1.hp"] = 6; t.vars["foe.tiger1.hp"] = 22
	t.specs["foe.bandit1.hp"] = {"doc": "山贼甲 hp → 0 = down", "max": 8}; t.specs["foe.tiger1.hp"] = {"doc": "独眼虎 hp → 0 = down", "max": 22}
	t._battle_begin()
	await create_timer(0.3).timeout
	t._changed("foe.bandit1.hp", 6, 2)
	await create_timer(0.2).timeout
	await create_timer(1.4).timeout
	print("battle: ", t.in_battle, " · foes: ", t.foes.keys(), " · battle ring: ", t.ring.visible, " · bars: ", t.bars.get_child_count())
	await _shot(t, "battle")
	quit(0 if ok and built and t.in_battle else 1)
