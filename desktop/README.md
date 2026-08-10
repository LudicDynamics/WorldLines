# desktop/ — 桌面壳对比(Tauri vs Electron)

**唯一 SoT 是 Web LocalShell**(`neonrp web` + 本仓 `ui/`)。
这里的两个壳是**同构薄皮**,不含任何产品逻辑,只做三件事:

1. 起引擎:装机形态跑已安装的 `neonrp web --port <port>`
2. 等就绪:轮询 `GET /api/v1/meta` 到 200(30s 超时,splash 显示错误)
3. 开窗口:指向 `http://127.0.0.1:<port>/local`;退出时 SIGTERM 杀引擎

端口约定:dev 手跑 = 8787,Electron 壳 = 8791,Tauri 壳 = 8792(互不打架)。

## 引擎从哪来

**引擎源码不在本仓** —— WorldLines 是开源壳(AGPL-3.0),NeonRP 引擎专有、
单独分发。两个壳都是 **installed-first**:找机器上已安装的 `neonrp`
(Tauri 壳找不到时还会在 splash 里引导安装)。

要对着本地引擎签出开发,显式指路:

```bash
export WORLDLINES_ENGINE_REPO=/path/to/NeonRP   # 该目录须有 pyproject.toml
```

设了就走 `uv run neonrp`(cwd = 该签出),否则走已安装引擎。

## 跑法

```bash
# Electron 候选
cd desktop/electron && npm install && npm start
npm run dist          # 打包 .app(dir target)→ dist/mac-arm64/WorldLines.app

# Tauri 候选
cd desktop/tauri && cargo build --release
./target/release/worldlines-desktop        # 或 cargo tauri build 出 .app
```

## 决策状态

对比结论见 `DESKTOP-SHELL-COMPARE.md`(实测数据+暂定倾向,随引擎仓)。
**最终只保留一个**,另一个整目录删除。在决定之前,两个壳都不发布
(local only)—— CI 的 `desktop.yml` 因此只能手动触发,且不签名不发布。

打包成正式发行版前还差的一步(两边同样):引擎 sidecar 化 ——
现在壳假设机器上装了引擎(或有 `uv` + 引擎签出),发行版要把引擎
打成自带二进制(PyInstaller / python-build-standalone)再由壳拉起。
