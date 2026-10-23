# Plays the game against a running host: title → connect → one line → (optionally) screenshots of play / map / clues.
#   WL_HOST=… WL_TOKEN=… [WL_LINE=…] [WL_SHOTS=<dir>] godot --path . -s tests/scene_play.gd    (screenshots need a window)
extends SceneTree
func _initialize() -> void:
	_go()
func _shot(name: String) -> void:
	var dir := OS.get_environment("WL_SHOTS")
	if dir == "" or DisplayServer.get_name() == "headless":
		return
	await process_frame; await process_frame
	root.get_viewport().get_texture().get_image().save_png(dir.path_join(name + ".png"))
func _go() -> void:
	root.size = Vector2i(1440, 900)
	await process_frame
	var s: Control = load("res://main.tscn").instantiate()
	root.add_child(s)
	await create_timer(0.5).timeout
	await _shot("gd1-title")
	await s._connect()
	await create_timer(1.2).timeout
	print("place: ", s.place_lbl.text, " · clock: ", s.clock_lbl.text, " · clues: ", s.clue_btn.text, " · placeholder: ", s.say.placeholder_text)
	await _shot("gd2-play")
	var line := OS.get_environment("WL_LINE") if OS.get_environment("WL_LINE") != "" else "Look around."
	var t0 := Time.get_ticks_msec()
	var shot_dice := false
	s._play(line)
	while s.busy and Time.get_ticks_msec() - t0 < 280000:
		if s.dice_layer.visible and not shot_dice:
			shot_dice = true
			await create_timer(1.0).timeout
			await _shot("gd3-dice")
		await create_timer(0.25).timeout
	await create_timer(2.5).timeout
	print("turn %.1f s · beat: %s · dice seen: %s · choices: %d" % [(Time.get_ticks_msec() - t0) / 1000.0, s.beat_lbl.text, shot_dice, s.choices.get_child_count()])
	await _shot("gd4-after")
	s._open_map(); await create_timer(0.4).timeout; await _shot("gd5-map"); s.map_layer.visible = false
	s.clue_layer.visible = true; await create_timer(0.4).timeout; await _shot("gd6-clues")
	quit(0)
