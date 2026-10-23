# One person on the pixel stage: a turnaround sheet (front · side · back, 64 px frames) drawn at its feet, a shadow,
# a little bob while walking. No sheet yet → a coloured stand-in of the same size.
extends Node2D

var who := ""
var sheet: Texture2D
var frame := 64
var foot := 60
var top := 6
var color := Color("#8aa07a")
var face := "down"          # down · up · left · right
var moving := false
var hurt := 0.0             # seconds of red flash left
var down := false           # out of the fight: drawn lying low and grey
var _t := randf() * 3.0


func setup(name_: String, tex: Texture2D, meta: Dictionary, tint: Color) -> void:
	who = name_
	sheet = tex
	color = tint
	if not meta.is_empty():
		frame = int(meta.get("frame", 64)); foot = int(meta.get("foot", 60)); top = int(meta.get("top", 6))
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST


func height() -> float:
	return float(foot - top) * scale.y


func _process(delta: float) -> void:
	_t += delta
	hurt = maxf(0.0, hurt - delta)
	queue_redraw()


func _draw() -> void:
	draw_set_transform(Vector2.ZERO)
	_ellipse(Vector2(0, 0), Vector2(11, 3.5), Color(0, 0, 0, 0.35))
	var bob := -absf(sin(_t * 11.0)) * 1.5 if moving else sin(_t * 1.8) * 0.4
	var tint := Color(1, 0.45, 0.4) if hurt > 0.0 and int(hurt * 20) % 2 == 0 else (Color(0.55, 0.55, 0.6, 0.7) if down else Color.WHITE)
	if sheet:
		var col := {"down": 0, "right": 1, "left": 1, "up": 2}.get(face, 0) as int
		var src := Rect2(col * frame, 0, frame, frame)
		var flip := face == "left"
		if down:
			draw_set_transform(Vector2(0, -4), PI / 2.0 * (-1.0 if flip else 1.0), Vector2(-1 if flip else 1, 1))
			draw_texture_rect_region(sheet, Rect2(-frame / 2.0, -foot, frame, frame), src, tint)
			return
		draw_set_transform(Vector2(0, bob), 0.0, Vector2(-1 if flip else 1, 1))
		draw_texture_rect_region(sheet, Rect2(-frame / 2.0, -foot, frame, frame), src, tint)
	else:
		var h := 40.0 if not down else 14.0
		draw_set_transform(Vector2(0, bob))
		draw_rect(Rect2(-8, -h + 10, 16, h - 10), color * tint)
		draw_circle(Vector2(0, -h + 6), 7, (color.lightened(0.25)) * tint)
		var f := ThemeDB.fallback_font
		draw_string(f, Vector2(-6, -h + 10), who.substr(0, 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color(0.1, 0.1, 0.12))


func _ellipse(c: Vector2, r: Vector2, col: Color) -> void:
	var pts := PackedVector2Array()
	for i in 20:
		var a := TAU * i / 20.0
		pts.append(c + Vector2(cos(a) * r.x, sin(a) * r.y))
	draw_colored_polygon(pts, col)
