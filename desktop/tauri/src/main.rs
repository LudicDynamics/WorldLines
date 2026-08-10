// WorldLines 桌面壳 — docs/WEBUI-UNIFICATION.md §7.5 LP2/LP3。
//
// 唯一的桌面壳(niko 2026-08-10 拍板 Tauri,Electron 候选整目录删除)。
// 薄壳,不含产品逻辑(SoT = neonrp web + 本仓 ui/ 的 LocalShell):
//   1. 起引擎:装机 = 已安装 neonrp;开发机 = uv run neonrp web
//      (cwd = WORLDLINES_ENGINE_REPO 指到的引擎签出)
//   2. 等就绪:轮询 /api/v1/meta 到 200(裸 TCP HTTP,不引 reqwest)
//   3. 窗口从内置 splash 跳到 http://127.0.0.1:8792/local;退出时杀引擎
//
// 解析顺序:WORLDLINES_ENGINE_REPO 显式指到引擎签出(开发机)→ 开发引擎
// 优先;否则找已安装 neonrp,并用能力探针把旧引擎(< v0.3.0,`web --help`
// 没有 --no-browser)在 spawn 前拦下 —— 否则旧引擎会因未知选项瞬退,壳空等
// 30s(niko 实测)。发行版没人设那个环境变量,实际就是 installed-first。
//
// S1 引导安装(docs/PACKAGING-ENGINE.md S1):没装引擎或引擎过旧时,壳在
// splash 里自己完成安装 —— 镜像 install.sh 的两步:①缺 uv 则
// `curl -LsSf https://astral.sh/uv/install.sh | sh`(Windows 用 astral 的
// install.ps1);②`uv tool install --force worldlines==<壳版本>`(钉版本保证
// 壳↔引擎同版;钉装失败回退不钉,能力探针最终把关)。全程用户态
// (~/.local),不提权;输出逐行流进 splash,不哑等。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};

const PORT: u16 = 8792;
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
/// uv tool install 冷缓存可达数分钟 —— 给足,progress 行让等待可读。
const INSTALL_CAP: Duration = Duration::from_secs(600);

struct Engine(Mutex<Option<Child>>);

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

// 引擎源码不在本仓 —— WorldLines 是开源壳,NeonRP 引擎专有、单独分发。
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
    Command::new(bin)
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

fn engine_args(head: &[&str]) -> Vec<String> {
    let mut args: Vec<String> = head.iter().map(|s| s.to_string()).collect();
    for a in [
        "web",
        "--port",
        &PORT.to_string(),
        "--parent-pid",
        &std::process::id().to_string(),
        "--no-browser",
    ] {
        args.push(a.to_string());
    }
    args
}

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

fn spawn_resolved(r: &Resolved) -> std::io::Result<Child> {
    match r {
        Resolved::Dev(root) => Command::new(find_uv().unwrap_or_else(|| PathBuf::from("uv")))
            .args(engine_args(&["run", "neonrp"]))
            .current_dir(root)
            .env("PYTHONUTF8", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn(),
        Resolved::Installed(bin) => Command::new(bin)
            .args(engine_args(&[]))
            .env("PYTHONUTF8", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn(),
    }
}

// 等 /api/v1/meta 200(裸 HTTP/1.1,避免为一个健康检查拖依赖)
fn probe_ready() -> bool {
    if let Ok(mut s) = TcpStream::connect(("127.0.0.1", PORT)) {
        let req = format!(
            "GET /api/v1/meta HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\n\r\n"
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
                    Command::new("powershell").args([
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
                    Command::new("sh").args([
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
        "首次启动:正在安装 WorldLines 引擎 v{APP_VERSION}(约 1-3 分钟,需要联网)…"
    ));
    let pinned = format!("worldlines=={APP_VERSION}");
    let pinned_result = run_streaming(
        Command::new(&uv).args(["tool", "install", "--force", &pinned]),
        progress,
        INSTALL_CAP,
    );
    if pinned_result.is_err() {
        progress.set_header("钉版安装失败,改装最新版 WorldLines 引擎…");
        run_streaming(
            Command::new(&uv).args(["tool", "install", "--force", "worldlines"]),
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

/// spawn + 就绪监控:stderr 收集,进程死亡快速失败,超时展示原因。
fn run_engine(win: tauri::WebviewWindow, handle: tauri::AppHandle, resolved: Resolved) {
    let mut child = match spawn_resolved(&resolved) {
        Ok(c) => c,
        Err(e) => {
            show_msg_text(&win, &format!("引擎启动失败:{e}"));
            return;
        }
    };
    let err_buf: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    if let Some(stderr) = child.stderr.take() {
        pipe_lines(stderr, Arc::clone(&err_buf));
    }
    *handle.state::<Engine>().0.lock().unwrap() = Some(child);

    let t0 = Instant::now();
    let timeout = Duration::from_secs(30);
    loop {
        if probe_ready() {
            let _ = win.eval(&format!(
                "window.location.replace('http://127.0.0.1:{PORT}/local')"
            ));
            watch_engine_after_ready(win, handle, err_buf);
            return;
        }
        // 进程已死就立刻失败,别陪跑满 30s。
        let exited = {
            let state = handle.state::<Engine>();
            let mut guard = state.0.lock().unwrap();
            match guard.as_mut().map(|c| c.try_wait()) {
                Some(Ok(Some(status))) => Some(format!("{status}")),
                _ => None,
            }
        };
        let fail = |reason: String| {
            let tail = err_buf.lock().unwrap().join("\n");
            show_msg_text(&win, &format!("引擎启动失败:{reason}\n{}", tail.trim()));
        };
        if let Some(status) = exited {
            fail(format!("进程已退出({status})"));
            return;
        }
        if t0.elapsed() >= timeout {
            fail("30s 未就绪".into());
            return;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

/// 跳转进产品页之后继续盯引擎进程:此前引擎死了页面只是静默变砖
/// (所有 fetch 失败、面板卡"读取中"),用户以为"没自动开引擎"。
/// 死了就往当前页面注入全屏浮层,把退出码 + stderr 尾巴给出来。
fn watch_engine_after_ready(
    win: tauri::WebviewWindow,
    handle: tauri::AppHandle,
    err_buf: Arc<Mutex<Vec<String>>>,
) {
    loop {
        std::thread::sleep(Duration::from_secs(1));
        let exited = {
            let state = handle.state::<Engine>();
            let mut guard = state.0.lock().unwrap();
            match guard.as_mut().map(|c| c.try_wait()) {
                Some(Ok(Some(status))) => Some(format!("{status}")),
                None => return, // 已被关窗清理,正常退出
                _ => None,
            }
        };
        if let Some(status) = exited {
            let tail: String = {
                let buf = err_buf.lock().unwrap();
                buf.iter()
                    .rev()
                    .take(12)
                    .cloned()
                    .collect::<Vec<_>>()
                    .into_iter()
                    .rev()
                    .collect::<Vec<_>>()
                    .join("\n")
            };
            let msg = format!(
                "引擎进程已退出({status})\n\n{}\n\n请关闭本窗口重开;反复出现请在终端跑 worldlines 看完整日志。",
                tail
            );
            let _ = win.eval(&format!(
                "(function(){{var d=document.createElement('div');d.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(10,10,12,.96);color:#FFB4C4;font:13px/1.7 ui-monospace,monospace;padding:44px;white-space:pre-wrap;overflow:auto';d.textContent='{}';document.body.appendChild(d);}})()",
                js_escape(&msg)
            ));
            return;
        }
    }
}

/// 完整启动流:解析 → (必要时 S1 引导安装) → spawn+监控。全程后台线程。
fn boot(win: tauri::WebviewWindow, handle: tauri::AppHandle) {
    match resolve_engine() {
        Ok(resolved) => run_engine(win, handle, resolved),
        Err(fail) => {
            let mut progress = Progress::new(
                win.clone(),
                match fail {
                    ResolveFail::TooOld => "检测到旧版引擎,正在升级 WorldLines 引擎…",
                    ResolveFail::NotInstalled => "首次启动:正在安装 WorldLines 引擎…",
                },
            );
            match bootstrap_install(&mut progress) {
                Ok(bin) => {
                    progress.set_header("引擎就绪,正在启动…");
                    run_engine(win, handle, Resolved::Installed(bin));
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
                            "{}<br><br>可手动安装后重开本应用:<br><code style=\"color:#34E879\">{}</code>",
                            e.replace('<', "&lt;"),
                            manual
                        ),
                    );
                }
            }
        }
    }
}

fn main() {
    tauri::Builder::default()
        .manage(Engine(Mutex::new(None)))
        .setup(|app| {
            let win = app.get_webview_window("main").expect("main window");
            let handle = app.handle().clone();
            std::thread::spawn(move || boot(win, handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building tauri app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Engine>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
