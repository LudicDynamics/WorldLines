# Loads the game scene headless and checks it built (no host needed).
extends SceneTree
func _initialize() -> void:
	_go()
func _go() -> void:
	await process_frame
	var s: Control = load("res://main.tscn").instantiate()
	root.add_child(s)
	await process_frame
	var ok: bool = s.say != null and s.token_in.secret and s.title.visible and not s.play.visible
	print("scene built: ", ok, " · title: ", (s.title.get_child(2).get_child(0) as Label).text, " · title art: ", s.title_art.texture != null)
	s._on_chunk("门厅里只点着一盏油灯。\n[调查员 侦查(看灯): 16 ≤ 60] → 成功\n", "", "")
	s._on_chunk("「舅舅三天前进去的。」", "温妮", "")
	var text := ""
	for b in s.log_box.get_children():
		for c in b.get_children():
			if c is Label: text += (c as Label).text
	print("dice lifted: ", not text.contains("16 ≤ 60"), " · log ok: ", text.contains("油灯") and text.contains("温妮"))
	quit(0 if ok else 1)
