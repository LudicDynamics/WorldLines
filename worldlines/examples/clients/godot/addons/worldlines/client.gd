# WorldLines client for Godot 4 — the whole protocol in one node (copy addons/worldlines into your project).
#
# A WorldLines host (`neonrp serve`) runs the world; this node sends lines and listens:
#   POST /rpc         JSON-RPC 2.0: session.hello · turn.send · turn.cancel · reply
#   GET  /rpc/events  server-sent events, one JSON-RPC message each:
#                       {"method": "bus.message", "params": {"topic", "seq", "payload"}}
#                       {"id": …, "method": "ask_user", "params": {"question", "options"}}  → answer(id, value)
#   GET  /api/v1/play/engine/beat-kinds   how this run's beats are shown (declared by the play pack; empty = one plain turn)
# Auth: "Authorization: Bearer <token>" (printed by `neonrp serve`).
#
# It knows no particular beat: names, tones and hints come from beat_kinds — the same scene shows every kind of game.
class_name WorldLinesClient
extends Node

const PROTOCOL := "worldlines.net/1"
const ERR_UNAUTHORIZED := -32001
const ERR_BUSY := -32002
const ERR_VERSION := -32003
const ERR_NO_SESSION := -32004

## handshake done: {protocol, world, agent_id}
signal connected(hello: Dictionary)
## {start?, kinds: {node: {label, tone, live, host, narr, you, placeholder, chips, divider_from, …}}}
signal beat_kinds_loaded(kinds: Dictionary)
## a piece of prose as it is written: who = a character's name ("" = the host), beat = the node it belongs to ("" before the first)
signal chunk(text: String, who: String, beat: String)
## a landed beat event: node.enter · node.leave · <node>.beat · dice · tool · state.changed · run.settled · away …
signal beat(event: String, data: Dictionary)
signal turn_started
signal turn_finished(ok: bool, error: String)
## the world asks the player; reply with answer(id, value)
signal ask_user(id: Variant, question: String, options: Array)
## "open" / "retrying"
signal connection(state: String, detail: String)
## a readable sentence for something the player can fix (bad token, no host, a turn still running)
signal failed(message: String)

var base_url := ""
var token := ""
var client_id := ""
var _seq := -1
var _sse_buf := PackedByteArray()
var _sse_state := "idle"   # idle · connecting · requesting · streaming · waiting
var _retry_at := 0.0
var _closing := false


func _ready() -> void:
	client_id = "%08x" % (randi() & 0x7fffffff)


## Handshake, read beat_kinds, start listening. Emits connected / beat_kinds_loaded, or failed.
func connect_to_host(url: String, host_token: String) -> bool:
	base_url = url.strip_edges().trim_suffix("/")
	if not base_url.begins_with("http://") and not base_url.begins_with("https://"):
		base_url = "http://" + base_url
	token = host_token.strip_edges()
	_closing = false
	var hello: Variant = await call_rpc("session.hello", {"protocol": PROTOCOL})
	if hello == null:
		return false
	connected.emit(hello)
	beat_kinds_loaded.emit(await get_json("/api/v1/play/engine/beat-kinds", {"kinds": {}}))
	_open_stream()
	return true


## Play one line; returns the turn result ({success, error, assistant_message, …}) when the turn is over.
func send_line(text: String) -> Dictionary:
	var r: Variant = await call_rpc("turn.send", {"text": text, "client": client_id})
	return r if r is Dictionary else {"success": false}


func cancel() -> void:
	await call_rpc("turn.cancel", {})


func answer(id: Variant, value: Variant) -> void:
	await call_rpc("reply", {"id": id, "result": value})


func close() -> void:
	_closing = true
	if _tcp:
		_tcp.disconnect_from_host()
	_sse_state = "idle"


## One JSON-RPC call. Returns the result, or null after emitting `failed` with a readable message.
func call_rpc(method: String, params: Dictionary) -> Variant:
	var req := HTTPRequest.new()
	req.timeout = 0.0 if method == "turn.send" else 15.0   # only a turn may take long
	add_child(req)
	var body := JSON.stringify({"jsonrpc": "2.0", "id": randi(), "method": method, "params": params})
	var err := req.request(base_url + "/rpc", _headers(), HTTPClient.METHOD_POST, body)
	if err != OK:
		req.queue_free()
		failed.emit("Cannot send to %s (%s)." % [base_url, error_string(err)])
		return null
	var res: Array = await req.request_completed
	req.queue_free()
	if res[0] != HTTPRequest.RESULT_SUCCESS:
		failed.emit("Cannot reach the host at %s — is `neonrp serve` running?" % base_url)
		return null
	var msg: Variant = JSON.parse_string((res[3] as PackedByteArray).get_string_from_utf8())
	if not (msg is Dictionary):
		failed.emit("The host answered HTTP %d with something that is not JSON-RPC." % res[1])
		return null
	if msg.has("error"):
		failed.emit(explain(int(msg["error"].get("code", 0)), str(msg["error"].get("message", ""))))
		return null
	return msg.get("result")


static func explain(code: int, message: String) -> String:
	match code:
		ERR_UNAUTHORIZED: return "The token is wrong — use the one `neonrp serve` printed."
		ERR_BUSY: return "A turn is still running — wait for it to finish."
		ERR_VERSION: return "This host speaks another protocol version (%s)." % message
		ERR_NO_SESSION: return "The host has no world open yet."
	return message


func _headers() -> PackedStringArray:
	return PackedStringArray(["Content-Type: application/json", "Authorization: Bearer " + token])


## A plain HTTP read the host answers (/state · /api/v1/play/schema · /api/v1/play/engine/settlement …).
func get_json(path: String, fallback: Variant = null) -> Variant:
	var req := HTTPRequest.new()
	req.timeout = 15.0
	add_child(req)
	if req.request(base_url + path, _headers()) != OK:
		req.queue_free()
		return fallback
	var res: Array = await req.request_completed
	req.queue_free()
	if res[0] != HTTPRequest.RESULT_SUCCESS or res[1] != 200:
		return fallback
	var d: Variant = JSON.parse_string((res[3] as PackedByteArray).get_string_from_utf8())
	return d if d != null else fallback


# ── the event stream ─────────────────────────────────────────────────────────────────────────────────────────────
# Read over a raw TCP (+ TLS) stream rather than HTTPClient: the host answers the stream as HTTP/1.0 with no length,
# which HTTPClient takes for "no body". Reconnects and asks for what it missed (since).
var _tcp: StreamPeerTCP
var _peer: StreamPeer
var _host := ""
var _port := 80
var _tls := false
var _headers_done := false


func _open_stream() -> void:
	var u := base_url.trim_prefix("http://").trim_prefix("https://")
	_tls = base_url.begins_with("https://")
	_host = u.get_slice("/", 0)
	_port = 443 if _tls else 80
	if ":" in _host:
		_port = int(_host.get_slice(":", 1))
		_host = _host.get_slice(":", 0)
	_tcp = StreamPeerTCP.new()
	_peer = _tcp
	_sse_buf = PackedByteArray()
	_headers_done = false
	if _tcp.connect_to_host(_host if _host != "localhost" else "127.0.0.1", _port) != OK:
		_retry("cannot open the stream")
		return
	_sse_state = "connecting"


func _retry(detail: String) -> void:
	if _closing:
		return
	connection.emit("retrying", detail)
	_sse_state = "waiting"
	_retry_at = Time.get_ticks_msec() / 1000.0 + 1.0


func _process(_delta: float) -> void:
	if _sse_state == "waiting":
		if Time.get_ticks_msec() / 1000.0 >= _retry_at:
			_open_stream()
		return
	if _sse_state == "idle" or _tcp == null:
		return
	_tcp.poll()
	var st := _tcp.get_status()
	if st == StreamPeerTCP.STATUS_ERROR or (st == StreamPeerTCP.STATUS_NONE and _sse_state != "connecting"):
		_retry("the host closed the stream")
		return
	match _sse_state:
		"connecting":
			if st != StreamPeerTCP.STATUS_CONNECTED:
				return
			if _tls:
				var t := StreamPeerTLS.new()
				if t.connect_to_stream(_tcp, _host) != OK:
					_retry("TLS failed")
					return
				_peer = t
				_sse_state = "handshaking"
				return
			_send_stream_request()
		"handshaking":
			var t: StreamPeerTLS = _peer
			t.poll()
			if t.get_status() == StreamPeerTLS.STATUS_CONNECTED:
				_send_stream_request()
			elif t.get_status() != StreamPeerTLS.STATUS_HANDSHAKING:
				_retry("TLS failed")
		"streaming":
			if _tls:
				(_peer as StreamPeerTLS).poll()
			var n := _peer.get_available_bytes()
			if n <= 0:
				return
			var got: Array = _peer.get_partial_data(n)
			if got[0] != OK:
				_retry("read failed")
				return
			_sse_buf.append_array(got[1])
			if not _headers_done and not _read_headers():
				return
			_drain()


func _send_stream_request() -> void:
	var path := "/rpc/events?client=%s" % client_id + ("" if _seq < 0 else "&since=%d" % _seq)
	var req := "GET %s HTTP/1.1\r\nHost: %s:%d\r\nAuthorization: Bearer %s\r\nAccept: text/event-stream\r\nConnection: close\r\n\r\n" % [path, _host, _port, token]
	_peer.put_data(req.to_utf8_buffer())
	_sse_state = "streaming"


func _read_headers() -> bool:
	# the status line + headers end with a blank line; what follows is the event stream
	for i in range(_sse_buf.size() - 3):
		if _sse_buf[i] == 13 and _sse_buf[i + 1] == 10 and _sse_buf[i + 2] == 13 and _sse_buf[i + 3] == 10:
			var head := _sse_buf.slice(0, i).get_string_from_utf8()
			_sse_buf = _sse_buf.slice(i + 4)
			var code := int(head.get_slice(" ", 1))
			if code != 200:
				failed.emit(explain(ERR_UNAUTHORIZED, "") if code == 401 else "The stream answered HTTP %d." % code)
				close()
				return false
			_headers_done = true
			connection.emit("open", "")
			return true
	return false


func _drain() -> void:
	# frames end with a blank line; decode only whole frames (a multi-byte character may be split across reads)
	while true:
		var cut := -1
		for i in range(_sse_buf.size() - 1):
			if _sse_buf[i] == 10 and _sse_buf[i + 1] == 10:
				cut = i
				break
		if cut < 0:
			return
		var frame := _sse_buf.slice(0, cut).get_string_from_utf8()
		_sse_buf = _sse_buf.slice(cut + 2)
		for line in frame.split("\n"):
			if line.begins_with("data: "):
				var msg: Variant = JSON.parse_string(line.substr(6))
				if msg is Dictionary:
					_dispatch(msg)


func _dispatch(msg: Dictionary) -> void:
	var p: Dictionary = msg.get("params", {})
	if msg.get("method") == "ask_user" and msg.has("id"):
		ask_user.emit(msg["id"], str(p.get("question", "")), p.get("options", []))
		return
	if msg.get("method") != "bus.message":
		return
	_seq = int(p.get("seq", _seq))
	var topic := str(p.get("topic", ""))
	var pl: Dictionary = p.get("payload", {})
	var kind := str(pl.get("kind", ""))
	if topic == "engine/stream" and kind == "chunk":
		var raw := str(pl.get("text", ""))
		var who := ""
		var re := RegEx.create_from_string("^\\[\\[subagent:([^\\]]+)\\]\\]")
		var m := re.search(raw)
		if m:
			who = m.get_string(1)
		chunk.emit(RegEx.create_from_string("\\[\\[subagent:[^\\]]+\\]\\]").sub(raw, "", true), who, str(pl.get("beat", "")))
	elif topic == "engine/beat":
		beat.emit(kind, pl)
	elif topic == "engine/event" and kind == "turn_started":
		turn_started.emit()
	elif topic == "engine/event" and kind == "turn_finished":
		turn_finished.emit(bool(pl.get("success", false)), str(pl.get("error", "") if pl.get("error") != null else ""))
