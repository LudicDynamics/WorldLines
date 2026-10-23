# A world's art pack (examples/clients/art/<world>/art.json, shared with the TS example): which picture goes with which
# place, person, ending, clue. Pictures not drawn yet come back null — the scene draws a stand-in.
extends RefCounted

var pack := {}
var _dir := ""
var _cache := {}


## The pack for a world, from ../art/<world>/ next to this project (override with WL_ART_DIR).
func load_world(world: String) -> bool:
	var base := OS.get_environment("WL_ART_DIR")
	if base == "":
		base = ProjectSettings.globalize_path("res://").path_join("../art")
	_dir = base.path_join(world)
	var f := FileAccess.open(_dir.path_join("art.json"), FileAccess.READ)
	if f == null:
		pack = {"world": world}
		return false
	var d: Variant = JSON.parse_string(f.get_as_text())
	pack = d if d is Dictionary else {"world": world}
	return true


func texture(rel: Variant) -> Texture2D:
	if rel == null or str(rel) == "":
		return null
	var path := _dir.path_join(str(rel))
	if _cache.has(path):
		return _cache[path]
	var tex: Texture2D = null
	if FileAccess.file_exists(path):
		var img := Image.load_from_file(path)
		if img:
			tex = ImageTexture.create_from_image(img)
	_cache[path] = tex
	return tex


func scene(place: String) -> Texture2D:
	return texture((pack.get("scenes", {}) as Dictionary).get(place))


func portrait_of(name: String) -> Texture2D:
	var id: Variant = (pack.get("speakers", {}) as Dictionary).get(name)
	if id == null:
		return null
	return texture(((pack.get("portraits", {}) as Dictionary).get(id, {}) as Dictionary).get("base"))


func npcs_at(place: String) -> Array:
	var out := []
	for id in (pack.get("npcs_by_place", {}) as Dictionary).get(place, []):
		out.append(str(((pack.get("portraits", {}) as Dictionary).get(id, {}) as Dictionary).get("name", id)))
	return out


## Any JSON file inside the pack (e.g. sprites/index.json written by pull_town.py); {} when missing.
func read_json(rel: String) -> Dictionary:
	var f := FileAccess.open(_dir.path_join(rel), FileAccess.READ)
	if f == null:
		return {}
	var d: Variant = JSON.parse_string(f.get_as_text())
	return d if d is Dictionary else {}
