// WorldLines 桌面壳 — docs/WEBUI-UNIFICATION.md §7.5 LP2/LP3。
//
// 唯一的桌面壳(2026-08-10 拍板 Tauri,Electron 候选整目录删除)。
// 薄壳,不含产品逻辑(SoT = neonrp web + 本仓 ui/ 的 LocalShell):
//   1. 起引擎:装机 = 已安装 neonrp;开发机 = uv run neonrp web
//      (cwd = WORLDLINES_ENGINE_REPO 指到的引擎签出)
//   2. 等就绪:轮询 /api/v1/meta 到 200(裸 TCP HTTP,不引 reqwest)
//   3. 窗口从内置 splash 跳到 http://127.0.0.1:<端口>/local;退出时杀引擎
//
// 端口池(10-24):8792–8799 里挑一个空的(上次用的优先,网页的本地设置跟着端口走),
// 全被占就让系统给一个;只认自己拉起的那个进程(别的引擎占着 8792 时不会跳过去)。
// 菜单「重新加载」⌘R /「重启引擎」⇧⌘R;启动失败 / 引擎退出的画面上有「重启引擎」按钮
// (链接 neonrp://restart,壳在 on_navigation 里拦下);引擎中途退出先自动重启一次。
//
// 解析顺序:WORLDLINES_ENGINE_REPO 显式指到引擎签出(开发机)→ 开发引擎
// 优先;否则找已安装 neonrp,并用能力探针把旧引擎(< v0.3.0,`web --help`
// 没有 --no-browser)在 spawn 前拦下 —— 否则旧引擎会因未知选项瞬退,壳空等
// 30s。发行版没人设那个环境变量,实际就是 installed-first。
//
// S1 引导安装(docs/PACKAGING-ENGINE.md S1):没装引擎或引擎过旧时,壳在
// splash 里自己完成安装 —— 镜像 install.sh 的两步:①缺 uv 则
// `curl -LsSf https://astral.sh/uv/install.sh | sh`(Windows 用 astral 的
// install.ps1);②`uv tool install --force worldlines==<壳版本>`(钉版本保证
// 壳↔引擎同版;钉装失败回退不钉,能力探针最终把关)。全程用户态
// (~/.local),不提权;输出逐行流进 splash,不哑等。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU16, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem, Submenu};
use tauri::{Manager, RunEvent};

/// 端口池:先试上次用的,再按顺序试这几个,都被占就让系统给一个
const PORT_POOL: std::ops::RangeInclusive<u16> = 8792..=8799;
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
/// uv tool install 冷缓存可达数分钟 —— 给足,progress 行让等待可读。
const INSTALL_CAP: Duration = Duration::from_secs(600);

/// 引擎进程 + 它的端口 + 第几次启动(重启后旧的监视线程看到代数变了就退出)
#[derive(Default)]
struct Engine {
    child: Mutex<Option<Child>>,
    port: AtomicU16,
    generation: AtomicU64,
    resolved: Mutex<Option<Resolved>>,
    /// 重启进行中(菜单连按 / 自动重启和按钮同时来时只跑一次)
    restarting: AtomicBool,
    /// 上一次自动重启的时间:两分钟里又退出就不再自动重启,给按钮
    last_auto: Mutex<Option<Instant>>,
}

fn port_file(handle: &tauri::AppHandle) -> Option<PathBuf> {
    handle.path().app_data_dir().ok().map(|d| d.join("engine-port"))
}

fn port_free(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// 挑端口:上次用的 → 池里第一个空的 → 系统给的。挑到就记下来。
fn pick_port(handle: &tauri::AppHandle) -> u16 {
    let last = port_file(handle)
        .and_then(|f| std::fs::read_to_string(f).ok())
        .and_then(|s| s.trim().parse::<u16>().ok());
    let port = last
        .into_iter()
        .chain(PORT_POOL)
        .find(|p| port_free(*p))
        .or_else(|| {
            TcpListener::bind(("127.0.0.1", 0))
                .ok()
                .and_then(|l| l.local_addr().ok())
                .map(|a| a.port())
        })
        .unwrap_or(*PORT_POOL.start());
    if let Some(f) = port_file(handle) {
        let _ = std::fs::create_dir_all(f.parent().unwrap_or(&f));
        let _ = std::fs::write(f, port.to_string());
    }
    port
}

// Windows:壳是 GUI 子系统,直接起控制台程序(neonrp / uv / powershell)
// 会给每个子进程弹一个黑窗 —— 一律带 CREATE_NO_WINDOW。
fn cmd<S: AsRef<std::ffi::OsStr>>(program: S) -> Command {
    #[allow(unused_mut)]
    let mut c = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x0800_0000);
    }
    c
}

// GUI 进程的 PATH 不含 homebrew/.local(双击启动时)— 显式找 uv
fn find_uv() -> Option<PathBuf> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_default();
    let exe = if cfg!(windows) { "uv.exe" } else { "uv" };
    for cand in [
        format!("{home}/.local/bin/{exe}"),
        format!("/opt/homebrew/bin/{exe}"),
        format!("/usr/local/bin/{exe}"),
    ] {
        let p = PathBuf::from(&cand);
        if p.exists() {
            return Some(p);
        }
    }
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path)
        .map(|d| d.join(exe))
        .find(|p| p.exists())
}

// 发行版形态:找用户已安装的引擎(install.sh/ps1 落点的 neonrp 可执行文件)。
// GUI 双击启动时 PATH 极简,按安装脚本的固定落点显式探测,最后信一次 PATH。
fn find_installed_engine() -> Option<PathBuf> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_default();
    let exe = if cfg!(windows) { "neonrp.exe" } else { "neonrp" };
    // 最优先:worldlines uv-tool venv 内部的 neonrp —— 不看 PATH,不会被
    // 残留的旧版 shim(pip 装的 0.2.x neonrp.exe 等)遮蔽。用户机器上
    // 「worldlines 已是新版但壳仍探到旧 neonrp」的根因就是 shim 遮蔽。
    let tool_bin = if cfg!(windows) { "Scripts" } else { "bin" };
    let mut cands: Vec<String> = Vec::new();
    if cfg!(windows) {
        if let Ok(appdata) = std::env::var("APPDATA") {
            cands.push(format!("{appdata}/uv/tools/worldlines/{tool_bin}/{exe}"));
        }
    }
    cands.push(format!(
        "{home}/.local/share/uv/tools/worldlines/{tool_bin}/{exe}"
    ));
    cands.push(format!("{home}/.local/bin/{exe}"));
    cands.push(format!("/opt/homebrew/bin/{exe}"));
    cands.push(format!("/usr/local/bin/{exe}"));
    for cand in cands {
        let p = PathBuf::from(&cand);
        if p.exists() {
            return Some(p);
        }
    }
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path)
        .map(|d| d.join(exe))
        .find(|p| p.exists())
}

/// worldlines uv-tool venv 根目录候选(Windows 在 %APPDATA%\uv,其余 ~/.local/share/uv)
fn worldlines_tool_dirs() -> Vec<PathBuf> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_default();
    let mut dirs = Vec::new();
    if cfg!(windows) {
        if let Ok(appdata) = std::env::var("APPDATA") {
            dirs.push(PathBuf::from(format!("{appdata}/uv/tools/worldlines")));
        }
    }
    dirs.push(PathBuf::from(format!(
        "{home}/.local/share/uv/tools/worldlines"
    )));
    dirs
}

/// 已装引擎的实际版本:扫 venv 的 site-packages 里 worldlines-<ver>.dist-info。
/// 拿不到就 None(按"未知"处理,不触发重装)。
fn installed_engine_version() -> Option<String> {
    for root in worldlines_tool_dirs() {
        let sp_candidates = if cfg!(windows) {
            vec![root.join("Lib/site-packages")]
        } else {
            match std::fs::read_dir(root.join("lib")) {
                Ok(rd) => rd
                    .filter_map(|e| e.ok())
                    .map(|e| e.path().join("site-packages"))
                    .collect(),
                Err(_) => vec![],
            }
        };
        for sp in sp_candidates {
            let Ok(rd) = std::fs::read_dir(&sp) else { continue };
            for e in rd.filter_map(|e| e.ok()) {
                let name = e.file_name().to_string_lossy().to_string();
                if let Some(rest) = name.strip_prefix("worldlines-") {
                    if let Some(ver) = rest.strip_suffix(".dist-info") {
                        return Some(ver.to_string());
                    }
                }
            }
        }
    }
    None
}

/// a < b(数字点分版本;段缺省当 0;解析失败当相等,不触发重装)
fn version_lt(a: &str, b: &str) -> bool {
    let parse = |v: &str| -> Vec<u64> {
        v.split('.')
            .map(|s| s.chars().take_while(|c| c.is_ascii_digit()).collect::<String>())
            .map(|s| s.parse::<u64>().unwrap_or(0))
            .collect()
    };
    let (pa, pb) = (parse(a), parse(b));
    for i in 0..pa.len().max(pb.len()) {
        let (x, y) = (
            pa.get(i).copied().unwrap_or(0),
            pb.get(i).copied().unwrap_or(0),
        );
        if x != y {
            return x < y;
        }
    }
    false
}

// 引擎源码在同一个仓库的 neonrp/(Apache-2.0);桌面壳默认用装好的 neonrp 包。
// 开发机想跑本地引擎签出,显式指路:
//   WORLDLINES_ENGINE_REPO=/path/to/NeonRP
// 未设、路径不存在、或该目录没有 pyproject.toml → None,走发行版形态
// (installed-first)。此前这里是 CARGO_MANIFEST_DIR/../..(= 引擎仓根),
// 拆仓后那个路径指向壳仓自己,永远探不到引擎。
fn engine_repo() -> Option<PathBuf> {
    let root = PathBuf::from(std::env::var_os("WORLDLINES_ENGINE_REPO")?)
        .canonicalize()
        .ok()?;
    if root.join("pyproject.toml").exists() {
        Some(root)
    } else {
        None
    }
}

// 能力探针:桌面模式需要 launcher 化的 `neonrp web`(≥ v0.3.0)。CLI 没有
// --version 选项(新旧皆无),所以直接探我们依赖的能力本身:`web --help`
// 里有没有 --no-browser。旧引擎(≤0.2.x)没有 → 会因未知选项瞬退。
fn engine_capable(bin: &PathBuf) -> bool {
    cmd(bin)
        .args(["web", "--help"])
        // Windows 管道下 Python stdio 默认本地代码页,帮助文案里的非 ASCII
        // 字符会崩掉命令,探针误判引擎太旧 —— 强制 UTF-8(老引擎也吃这个)。
        .env("PYTHONUTF8", "1")
        .output()
        .map(|out| {
            let text = format!(
                "{}{}",
                String::from_utf8_lossy(&out.stdout),
                String::from_utf8_lossy(&out.stderr)
            );
            text.contains("--no-browser")
        })
        .unwrap_or(false)
}

fn engine_args(head: &[&str], port: u16) -> Vec<String> {
    let mut args: Vec<String> = head.iter().map(|s| s.to_string()).collect();
    for a in [
        "web",
        "--port",
        &port.to_string(),
        "--parent-pid",
        &std::process::id().to_string(),
        "--no-browser",
    ] {
        args.push(a.to_string());
    }
    args
}

#[derive(Clone)]
enum Resolved {
    /// 开发机:仓库根 + uv run
    Dev(PathBuf),
    /// 装机:已安装且能力达标的 neonrp
    Installed(PathBuf),
}

enum ResolveFail {
    NotInstalled,
    TooOld,
}

fn resolve_engine() -> Result<Resolved, ResolveFail> {
    if let Some(root) = engine_repo() {
        return Ok(Resolved::Dev(root));
    }
    match find_installed_engine() {
        Some(bin) => {
            if !engine_capable(&bin) {
                return Err(ResolveFail::TooOld);
            }
            // 能力探针只保证"有 web 模式",保证不了修没修过已知致命 bug
            // (0.3.2 引擎的看门狗在 Windows 上启动 2 秒自杀)。引擎实际
            // 版本低于壳 → 走引导钉装升级,壳↔引擎同版。
            if let Some(ver) = installed_engine_version() {
                if version_lt(&ver, APP_VERSION) {
                    return Err(ResolveFail::TooOld);
                }
            }
            Ok(Resolved::Installed(bin))
        }
        None => Err(ResolveFail::NotInstalled),
    }
}

fn spawn_resolved(r: &Resolved, port: u16) -> std::io::Result<Child> {
    match r {
        Resolved::Dev(root) => cmd(find_uv().unwrap_or_else(|| PathBuf::from("uv")))
            .args(engine_args(&["run", "neonrp"], port))
            .current_dir(root)
            .env("PYTHONUTF8", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn(),
        Resolved::Installed(bin) => cmd(bin)
            .args(engine_args(&[], port))
            .env("PYTHONUTF8", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn(),
    }
}

// 等 /api/v1/meta 200(裸 HTTP/1.1,避免为一个健康检查拖依赖)
fn probe_ready(port: u16) -> bool {
    if let Ok(mut s) = TcpStream::connect(("127.0.0.1", port)) {
        let req = format!(
            "GET /api/v1/meta HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
        );
        if s.write_all(req.as_bytes()).is_ok() {
            let mut buf = [0u8; 64];
            if let Ok(n) = s.read(&mut buf) {
                if String::from_utf8_lossy(&buf[..n]).contains(" 200 ") {
                    return true;
                }
            }
        }
    }
    false
}

// 注入 JS 字符串字面量的手工转义(Cargo 不引 serde_json,保持零依赖)
fn js_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "")
}

fn show_msg_text(win: &tauri::WebviewWindow, text: &str) {
    let _ = win.eval(&format!(
        "var m=document.querySelector('.msg'); if(m){{m.style.whiteSpace='pre-wrap'; m.style.textAlign='left'; m.textContent='{}';}}",
        js_escape(text)
    ));
}

fn show_msg_html(win: &tauri::WebviewWindow, html: &str) {
    let _ = win.eval(&format!(
        "var m=document.querySelector('.msg'); if(m){{m.innerHTML='{}';}}",
        js_escape(html)
    ));
}

/// 滚动进度:header + 最后 8 行子进程输出,流式刷到 splash。
struct Progress {
    win: tauri::WebviewWindow,
    header: String,
    lines: Arc<Mutex<Vec<String>>>,
}

impl Progress {
    fn new(win: tauri::WebviewWindow, header: &str) -> Self {
        let p = Progress {
            win,
            header: header.to_string(),
            lines: Arc::new(Mutex::new(Vec::new())),
        };
        p.render();
        p
    }
    fn sink(&self) -> Arc<Mutex<Vec<String>>> {
        Arc::clone(&self.lines)
    }
    fn set_header(&mut self, header: &str) {
        self.header = header.to_string();
        self.render();
    }
    fn render(&self) {
        let lines = self.lines.lock().unwrap();
        let tail: Vec<&str> = lines
            .iter()
            .rev()
            .take(8)
            .map(|s| s.as_str())
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        show_msg_text(&self.win, &format!("{}\n\n{}", self.header, tail.join("\n")));
    }
}

fn pipe_lines<R: std::io::Read + Send + 'static>(reader: R, sink: Arc<Mutex<Vec<String>>>) {
    std::thread::spawn(move || {
        let br = BufReader::new(reader);
        for line in br.lines().map_while(Result::ok) {
            let mut buf = sink.lock().unwrap();
            if buf.len() > 400 {
                buf.drain(..200);
            }
            buf.push(line);
        }
    });
}

/// 跑一个安装类子进程:stdout/stderr 逐行流进 progress,带总超时。
fn run_streaming(cmd: &mut Command, progress: &Progress, cap: Duration) -> Result<(), String> {
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("无法启动安装进程:{e}"))?;
    if let Some(out) = child.stdout.take() {
        pipe_lines(out, progress.sink());
    }
    if let Some(err) = child.stderr.take() {
        pipe_lines(err, progress.sink());
    }
    let t0 = Instant::now();
    loop {
        progress.render();
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(status)) => return Err(format!("安装进程退出:{status}")),
            Ok(None) => {
                if t0.elapsed() > cap {
                    let _ = child.kill();
                    return Err("安装超时(10 分钟)".into());
                }
                std::thread::sleep(Duration::from_millis(300));
            }
            Err(e) => return Err(format!("等待安装进程失败:{e}")),
        }
    }
}

/// S1:壳内引导安装。镜像 install.sh 两步(uv → uv tool install),
/// 钉壳版本;钉装失败回退不钉。返回可用引擎路径。
fn bootstrap_install(progress: &mut Progress) -> Result<PathBuf, String> {
    // 步骤 1 — 确保 uv(镜像 install.sh:astral.sh 官方脚本,落 ~/.local/bin)
    let uv = match find_uv() {
        Some(uv) => uv,
        None => {
            progress.set_header("首次启动:正在安装 uv(约 30 秒,需要联网)…");
            if cfg!(windows) {
                run_streaming(
                    cmd("powershell").args([
                        "-ExecutionPolicy",
                        "ByPass",
                        "-NoProfile",
                        "-Command",
                        "irm https://astral.sh/uv/install.ps1 | iex",
                    ]),
                    progress,
                    INSTALL_CAP,
                )
            } else {
                run_streaming(
                    cmd("sh").args([
                        "-c",
                        "curl -LsSf https://astral.sh/uv/install.sh | sh",
                    ]),
                    progress,
                    INSTALL_CAP,
                )
            }
            .map_err(|e| format!("uv 安装失败(安装需要联网):{e}"))?;
            find_uv().ok_or_else(|| "uv 安装完成但未找到可执行文件".to_string())?
        }
    };

    // 步骤 2 — uv tool install --force worldlines==<壳版本>(壳↔引擎同版)。
    // 钉装失败(如该版本尚未上 PyPI)回退不钉;能力探针最终把关。
    progress.set_header(&format!(
        "首次启动:正在安装 NeonRP 引擎 v{APP_VERSION}(约 1-3 分钟,需要联网)…"
    ));
    let pinned = format!("worldlines=={APP_VERSION}");
    let pinned_result = run_streaming(
        cmd(&uv).args(["tool", "install", "--force", &pinned]),
        progress,
        INSTALL_CAP,
    );
    if pinned_result.is_err() {
        progress.set_header("钉版安装失败,改装最新版 NeonRP 引擎…");
        run_streaming(
            cmd(&uv).args(["tool", "install", "--force", "worldlines"]),
            progress,
            INSTALL_CAP,
        )
        .map_err(|e| format!("引擎安装失败(安装需要联网):{e}"))?;
    }

    let bin = find_installed_engine().ok_or_else(|| "安装完成但未找到 neonrp".to_string())?;
    if !engine_capable(&bin) {
        return Err("安装后的引擎仍不支持桌面模式(需 ≥ v0.3.0)".into());
    }
    Ok(bin)
}

/// 引擎画面上的浮层(启动失败 / 退出 / 重启中):盖住当前页,带「重启引擎」「重新加载」两个按钮
/// (链接 neonrp://…,壳在 on_navigation 里拦下)。buttons = false 只显示文字(重启进行中)。
fn overlay(win: &tauri::WebviewWindow, text: &str, buttons: bool) {
    let btns = if buttons {
        "<div style=\"margin-top:22px;display:flex;gap:10px;font:600 13px -apple-system,sans-serif\">\
<a href=\"neonrp://restart\" style=\"padding:9px 16px;border-radius:9px;background:#34E879;color:#0A0A0A;text-decoration:none\">重启引擎</a>\
<a href=\"neonrp://reload\" style=\"padding:9px 16px;border-radius:9px;border:1px solid #3A3A40;color:#F5F5F7;text-decoration:none\">重新加载</a></div>"
    } else {
        ""
    };
    let _ = win.eval(&format!(
        "(function(){{var d=document.getElementById('nrp-ov');if(!d){{d=document.createElement('div');d.id='nrp-ov';\
d.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(10,10,12,.96);color:#FFB4C4;font:13px/1.7 ui-monospace,monospace;padding:44px;overflow:auto';\
document.body.appendChild(d);}}var t=document.createElement('div');t.style.whiteSpace='pre-wrap';t.textContent='{}';d.replaceChildren(t);d.insertAdjacentHTML('beforeend','{}');}})()",
        js_escape(text),
        js_escape(btns)
    ));
}

fn err_tail(err_buf: &Arc<Mutex<Vec<String>>>, n: usize) -> String {
    let buf = err_buf.lock().unwrap();
    let start = buf.len().saturating_sub(n);
    buf[start..].join("\n")
}

/// 自己拉起的那个引擎退出了没有(Some = 已退出;None 且没有进程 = 已被关窗 / 重启收走)
fn child_exit(handle: &tauri::AppHandle) -> Option<Option<String>> {
    let state = handle.state::<Engine>();
    let mut guard = state.child.lock().unwrap();
    match guard.as_mut().map(|c| c.try_wait()) {
        Some(Ok(Some(status))) => Some(Some(format!("{status}"))),
        None => Some(None),
        _ => None,
    }
}

/// 挑端口 → spawn → 等就绪 → 跳到 back(重启时回到原来那一页;None = /local)→ 接着盯进程。
/// 就绪 = 自己拉起的进程还活着,且它的端口上 /api/v1/meta 是 200(端口是空的才挑,别人的引擎接不进来)。
fn run_engine(win: tauri::WebviewWindow, handle: tauri::AppHandle, resolved: Resolved, back: Option<String>) {
    let state = handle.state::<Engine>();
    *state.resolved.lock().unwrap() = Some(resolved.clone());
    let port = pick_port(&handle);
    state.port.store(port, Ordering::SeqCst);
    let mut child = match spawn_resolved(&resolved, port) {
        Ok(c) => c,
        Err(e) => {
            overlay(&win, &format!("引擎启动失败:{e}"), true);
            return;
        }
    };
    let err_buf: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    if let Some(stderr) = child.stderr.take() {
        pipe_lines(stderr, Arc::clone(&err_buf));
    }
    *state.child.lock().unwrap() = Some(child);
    let gen = state.generation.fetch_add(1, Ordering::SeqCst) + 1;

    let t0 = Instant::now();
    let timeout = Duration::from_secs(30);
    loop {
        let exited = child_exit(&handle);
        if let Some(status) = exited {
            let status = status.unwrap_or_else(|| "已停止".into());
            overlay(&win, &format!("引擎启动失败:进程已退出({status})\n{}", err_tail(&err_buf, 12).trim()), true);
            return;
        }
        if probe_ready(port) {
            let path = back.clone().unwrap_or_else(|| "/local".into());
            let _ = win.eval(&format!(
                "window.location.replace('http://127.0.0.1:{port}{}')",
                js_escape(&path)
            ));
            watch_engine_after_ready(win, handle, err_buf, gen);
            return;
        }
        if t0.elapsed() >= timeout {
            overlay(&win, &format!("引擎启动失败:30 秒没有就绪(端口 {port})\n{}", err_tail(&err_buf, 12).trim()), true);
            return;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

/// 跳转进产品页之后继续盯引擎进程:此前引擎死了页面只是静默变砖
/// (所有 fetch 失败、面板卡"读取中"),用户以为"没自动开引擎"。
/// 退出了先自动重启一次(两分钟里又退出就不再自动重启),再退就给浮层 + 「重启引擎」按钮。
fn watch_engine_after_ready(
    win: tauri::WebviewWindow,
    handle: tauri::AppHandle,
    err_buf: Arc<Mutex<Vec<String>>>,
    gen: u64,
) {
    loop {
        std::thread::sleep(Duration::from_secs(1));
        if handle.state::<Engine>().generation.load(Ordering::SeqCst) != gen {
            return; // 已经重启过,新的那一代自己有人盯
        }
        let status = match child_exit(&handle) {
            None => continue,
            Some(None) => return, // 已被关窗清理,正常退出
            Some(Some(status)) => status,
        };
        let auto = {
            let state = handle.state::<Engine>();
            let mut last = state.last_auto.lock().unwrap();
            let ok = last.map_or(true, |t| t.elapsed() > Duration::from_secs(120));
            if ok {
                *last = Some(Instant::now());
            }
            ok
        };
        if auto {
            restart(win, handle, &format!("引擎意外退出({status}),正在自动重启…"));
            return;
        }
        let msg = format!(
            "引擎进程已退出({status})\n\n{}\n\n点「重启引擎」再试一次;反复出现请在终端跑 worldlines 看完整日志。",
            err_tail(&err_buf, 12)
        );
        overlay(&win, &msg, true);
        return;
    }
}

/// 重启引擎:收走旧进程,重新挑端口拉起,回到原来那一页(只认 127.0.0.1 上的页面;splash 上就去 /local)。
/// 引擎还没解析过(首次安装失败)就整套重来。
fn restart(win: tauri::WebviewWindow, handle: tauri::AppHandle, note: &str) {
    let state = handle.state::<Engine>();
    if state.restarting.swap(true, Ordering::SeqCst) {
        return;
    }
    overlay(&win, note, false);
    state.generation.fetch_add(1, Ordering::SeqCst);
    if let Some(mut child) = state.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    let back = win.url().ok().and_then(|u| {
        (u.host_str() == Some("127.0.0.1")).then(|| {
            let mut s = u.path().to_string();
            if let Some(q) = u.query() {
                s.push('?');
                s.push_str(q);
            }
            if let Some(f) = u.fragment() {
                s.push('#');
                s.push_str(f);
            }
            s
        })
    });
    let resolved = state.resolved.lock().unwrap().clone();
    state.restarting.store(false, Ordering::SeqCst);
    match resolved {
        Some(r) => run_engine(win, handle, r, back),
        None => boot(win, handle),
    }
}

/// 重新加载:引擎还活着就刷新当前页;已经退出就等于重启引擎
fn reload(win: tauri::WebviewWindow, handle: tauri::AppHandle) {
    match child_exit(&handle) {
        None => {
            let _ = win.eval("window.location.reload()");
        }
        Some(_) => restart(win, handle, "引擎没有在运行,正在重启…"),
    }
}

/// 完整启动流:解析 → (必要时 S1 引导安装) → spawn+监控。全程后台线程。
fn boot(win: tauri::WebviewWindow, handle: tauri::AppHandle) {
    match resolve_engine() {
        Ok(resolved) => run_engine(win, handle, resolved, None),
        Err(fail) => {
            let mut progress = Progress::new(
                win.clone(),
                match fail {
                    ResolveFail::TooOld => "检测到旧版引擎,正在升级 NeonRP 引擎…",
                    ResolveFail::NotInstalled => "首次启动:正在安装 NeonRP 引擎…",
                },
            );
            match bootstrap_install(&mut progress) {
                Ok(bin) => {
                    progress.set_header("引擎就绪,正在启动…");
                    run_engine(win, handle, Resolved::Installed(bin), None);
                }
                Err(e) => {
                    let manual = if cfg!(windows) {
                        "irm https://worldlines.gg/install.ps1 | iex"
                    } else {
                        "curl -LsSf https://worldlines.gg/install.sh | sh"
                    };
                    show_msg_html(
                        &win,
                        &format!(
                            "{}<br><br>可手动安装后点重试:<br><code style=\"color:#34E879\">{}</code><br><br><a href=\"neonrp://restart\" style=\"color:#34E879\">重试</a>",
                            e.replace('<', "&lt;"),
                            manual
                        ),
                    );
                }
            }
        }
    }
}

/// 在后台线程里对主窗口做 f(菜单 / 按钮都从 UI 线程来,不能在那里等引擎)
fn on_main(handle: &tauri::AppHandle, f: fn(tauri::WebviewWindow, tauri::AppHandle)) {
    if let Some(win) = handle.get_webview_window("main") {
        let h = handle.clone();
        std::thread::spawn(move || f(win, h));
    }
}

fn do_restart(win: tauri::WebviewWindow, handle: tauri::AppHandle) {
    restart(win, handle, "正在重启引擎…");
}

fn main() {
    tauri::Builder::default()
        .manage(Engine::default())
        .setup(|app| {
            // 默认菜单(编辑 / 窗口……,复制粘贴靠它)后面加一栏「引擎」
            let menu = Menu::default(app.handle())?;
            let reload_item = MenuItem::with_id(app, "reload", "重新加载", true, Some("CmdOrCtrl+R"))?;
            let restart_item = MenuItem::with_id(app, "restart", "重启引擎", true, Some("CmdOrCtrl+Shift+R"))?;
            menu.append(&Submenu::with_items(app, "引擎", true, &[&reload_item, &restart_item])?)?;
            app.set_menu(menu)?;
            app.on_menu_event(|app, event| match event.id().as_ref() {
                "reload" => on_main(app, reload),
                "restart" => on_main(app, do_restart),
                _ => {}
            });

            // 主窗口在这里建(tauri.conf.json 里 create: false),好挂 on_navigation:neonrp://… 是壳的按钮
            let cfg = app
                .config()
                .app
                .windows
                .iter()
                .find(|w| w.label == "main")
                .expect("main window config")
                .clone();
            let nav = app.handle().clone();
            let win = tauri::WebviewWindowBuilder::from_config(app.handle(), &cfg)?
                .on_navigation(move |url| {
                    if url.scheme() != "neonrp" {
                        return true;
                    }
                    match url.host_str() {
                        Some("restart") => on_main(&nav, do_restart),
                        Some("reload") => on_main(&nav, reload),
                        _ => {}
                    }
                    false
                })
                .build()?;
            let handle = app.handle().clone();
            std::thread::spawn(move || boot(win, handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Engine>().child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
