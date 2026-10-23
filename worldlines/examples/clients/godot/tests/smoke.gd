# Plays one line against a running host, headless — the same client node the scene uses.
#   WL_HOST=http://127.0.0.1:8788 WL_TOKEN=<token> godot --headless --path . -s tests/smoke.gd
extends SceneTree

const Client = preload("res://addons/worldlines/client.gd")

var prose := ""
var who_now := "?"
var events: Array[String] = []
var problems: Array[String] = []
var kinds := {}


func _initialize() -> void:
	var c: Node = Client.new()
	root.add_child(c)
	c.chunk.connect(func(text: String, who: String, b: String) -> void:
		if who != who_now:
			who_now = who
			prose += "\n[%s%s] " % [who if who != "" else "host", (" · " + b) if b != "" else ""]
		prose += text)
	c.beat.connect(func(ev: String, _d: Dictionary) -> void: events.append(ev))
	c.failed.connect(func(m: String) -> void: problems.append(m))
	c.ask_user.connect(func(id: Variant, _q: String, options: Array) -> void: c.answer(id, options[0] if options.size() > 0 else null))
	_run(c)


func _run(c: Node) -> void:
	await process_frame   # the client node must be inside the tree before its HTTPRequests can run
	var host := OS.get_environment("WL_HOST") if OS.get_environment("WL_HOST") != "" else "http://127.0.0.1:8788"
	var line := OS.get_environment("WL_LINE") if OS.get_environment("WL_LINE") != "" else "Look around."
	c.beat_kinds_loaded.connect(func(k: Dictionary) -> void: kinds = k)   # a member: GDScript lambdas capture locals by value
	if not await c.connect_to_host(host, OS.get_environment("WL_TOKEN")):
		print("could not connect: ", "; ".join(problems))
		quit(2)
		return
	await create_timer(0.5).timeout
	print("connected · beats: ", ", ".join((kinds.get("kinds", {}) as Dictionary).keys()) if not (kinds.get("kinds", {}) as Dictionary).is_empty() else "(one plain turn)")
	var t0 := Time.get_ticks_msec()
	var r: Dictionary = await c.send_line(line)
	await create_timer(0.5).timeout
	print("turn %.1f s · success %s%s" % [(Time.get_ticks_msec() - t0) / 1000.0, r.get("success"), (" · " + "; ".join(problems)) if problems.size() > 0 else ""])
	print("beat events: ", " → ".join(events) if events.size() > 0 else "(none)")
	print("streamed %d chars:%s" % [prose.strip_edges().length(), prose.substr(0, 400)])
	c.close()
	quit(0 if r.get("success", false) and prose.strip_edges() != "" else 1)
