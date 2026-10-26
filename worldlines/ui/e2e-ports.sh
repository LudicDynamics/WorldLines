# e2e 启动脚本共用(source 进来):端口防护(10-18 —— 端口被别人占着时,引擎会自己退到下一个端口,用例却还打原端口 = 在别人那一局上开局 / 说话)
#   wl_ports_free 8906 8612 …            起之前:任何一个端口上已经有服务就退出(返回 3),不跑
#   export NEONRP_STRICT_PORT=1          引擎只绑要的那个端口,被占就报错退出(commands/web.py _bind_server),不再悄悄换端口
#   wl_wait_engine <端口> <进程> <日志> [秒]   等自己的引擎起来:日志里有绑到这个端口的那一行 + 页面能打开;引擎退了 / 报 was busy / 超时 → 返回 3
#   wl_wait_server <地址> <进程> <日志> [秒]   别的服务(假模型 · 静态站):进程还活着 + 地址能打开
wl_ports_free() {
  local p
  for p in "$@"; do
    [ -n "$p" ] || continue
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 || curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$p/"; then
      echo "e2e: port $p is already in use (someone else's server) — pick another port; not running against it" >&2
      return 3
    fi
  done
}

wl_wait_engine() {
  local port=$1 pid=$2 log=$3 n=${4:-120} i
  for i in $(seq 1 "$n"); do
    if grep -q "was busy" "$log" 2>/dev/null; then echo "e2e: the engine could not get port $port — not running against someone else's" >&2; return 3; fi
    if ! kill -0 "$pid" 2>/dev/null; then echo "e2e: the engine exited (port $port taken?) — $log:" >&2; tail -20 "$log" >&2; return 3; fi
    # 自己的引擎:日志里是绑在这个端口上的那一行(neonrp web 打「→ http://127.0.0.1:<端口>/…」),再能打开
    if grep -q "http://127.0.0.1:$port" "$log" 2>/dev/null && curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/"; then return 0; fi
    sleep 1
  done
  echo "e2e: the engine on port $port never came up — $log" >&2
  return 3
}

wl_wait_server() {
  local url=$1 pid=$2 log=$3 n=${4:-60} i
  for i in $(seq 1 "$n"); do
    if ! kill -0 "$pid" 2>/dev/null; then echo "e2e: $url — the server exited (port taken?) — $log:" >&2; tail -20 "$log" >&2; return 3; fi
    curl -sf -o /dev/null --max-time 2 "$url" && return 0
    sleep 1
  done
  echo "e2e: $url never came up — $log" >&2
  return 3
}
