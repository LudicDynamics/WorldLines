# Plays the 石津镇 town on a real host: connect through the title screen, then a few lines through the town screen.
#   WL_HOST=… WL_TOKEN=… [WL_SHOTS=dir] godot --path . -s tests/town_play.gd [-- "line" "line" …]
extends SceneTree

var shots := OS.get_environment("WL_SHOTS")


func _initialize() -> void:
	_go()


func _shot(name: String) -> void:
	if shots != "":
		await process_frame
		root.get_texture().get_image().save_png(shots.path_join("play-%s.png" % name))


func _go() -> void:
	await process_frame
	var lines := OS.get_cmdline_user_args()
	if lines.is_empty():
		lines = PackedStringArray(["开始游戏", "我进镇,去冒险者公会问问有没有能出北门的委托"])
	var m: Control = load("res://main.tscn").instantiate()
	root.add_child(m)
	await process_frame
	m._connect()
	var t: Control = null
	for i in 100:
		await create_timer(0.1).timeout
		for c in m.get_children():
			if c.get_script() == preload("res://game/town/town.gd"):
				t = c
		if t != null and t.player != null:
			break
	if t == null:
		print("no town screen: ", m.title_msg.text)
		quit(1)
		return
	# a scripted run: whatever is typed in another app while this window has focus must not play the game
	t.set_process_unhandled_input(false); t.view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	await create_timer(0.6).timeout
	print("town: ", t.zone_id, " · ", t.hud_place.text, " · ", t.hud_time.text, " · people ", t.people.map(func(p: Dictionary) -> String: return p["who"]))
	await _shot("0-start")
	var n := 0
	for line in lines:
		n += 1
		var t0 := Time.get_ticks_msec()
		if line.begins_with("@"):   # @T001/main_street — walk out through the doorway to it (the traditional way)
			for e in t.zone.get("exits", []):
				if str(e.get("to")) == line.substr(1):
					t._interact({"kind": "exit", "to": e.get("to"), "label": e.get("label"), "says": e.get("says", ""), "at": t._v(e.get("at"))})
			await create_timer(0.6).timeout
			print("   moved at once: ", t.zone_id, " · host still busy: ", t.busy)
		elif line.begins_with("!"):   # !卡斯/persuade/我想说服你…… — as if picked in their ring (approach "talk" = 交谈)
			var parts := line.substr(1).split("/", true, 2)
			var who := parts[0]; var aid := parts[1] if parts.size() > 1 else "talk"; var words := parts[2] if parts.size() > 2 else ""
			t._start_talk({"kind": "npc", "who": who, "at": t.player.position})
			var d := {"kind": "talk", "target": who} if aid == "talk" else {"kind": "approach", "approach": aid, "target": who}
			t._queue(words if words != "" else "(%s)" % aid, "talk", t._ix(d, words))
		else:
			t._queue(line, "bg")
		await create_timer(0.3).timeout
		while t.busy or not t.queue.is_empty():
			await create_timer(0.3).timeout
		await create_timer(0.8).timeout
		var text := ""
		for b in t.dlg_box.get_children():
			for c in b.get_children():
				if c is Label:
					text += (c as Label).text + "\n"
		print("── %s  (%.1f s) → %s · %s · options %d" % [line, (Time.get_ticks_msec() - t0) / 1000.0, t.zone_id, t.hud_time.text, t.last_options.size()])
		print(text.strip_edges().substr(0, 400))
		await _shot("%d" % n)
	quit(0)
