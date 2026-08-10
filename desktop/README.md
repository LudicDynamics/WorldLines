# desktop/ — 桌面壳(Tauri)

**唯一 SoT 是 Web LocalShell**(`neonrp web` + 本仓 `ui/`)。
这个壳是**薄皮**,不含任何产品逻辑,只做三件事:

1. 起引擎:装机形态跑已安装的 `neonrp web --port 8792`
2. 等就绪:轮询 `GET /api/v1/meta` 到 200(30s 超时,splash 显示错误)
3. 开窗口:指向 `http://127.0.0.1:8792/local`;退出时杀引擎

端口约定:dev 手跑引擎 = 8787,桌面壳 = 8792(互不打架)。

> 曾经有一个同构的 Electron 候选并行对比。**2026-08-10 niko 拍板用
> Tauri**,Electron 整目录已删除。要翻旧实现去 git 历史里找
> (`desktop/electron/`,删除前最后存在于 commit `9d0ef43`)。

## 引擎从哪来

**引擎源码不在本仓** —— WorldLines 是开源壳(AGPL-3.0),NeonRP 引擎专有、
单独分发。壳是 **installed-first**:找机器上已安装的 `neonrp`,找不到时
在 splash 里引导安装(镜像 install.sh 的两步:装 uv → `uv tool install`
钉壳版本,全程用户态不提权)。

要对着本地引擎签出开发,显式指路:

```bash
export WORLDLINES_ENGINE_REPO=/path/to/NeonRP   # 该目录须有 pyproject.toml
```

设了就走 `uv run neonrp`(cwd = 该签出),否则走已安装引擎。这个变量是
拆仓后加的:壳原本按 `<壳目录>/../..` 推断引擎仓根,在引擎仓里那正好是
NeonRP 根,搬进壳仓后那个路径指向壳仓自己,永远探不到引擎。

引擎太旧也会被拦下:能力探针跑 `neonrp web --help` 看有没有 `--no-browser`
(< v0.3.0 没有),旧引擎会因未知选项瞬退、壳空等 30s。

## 跑法

```bash
cd desktop/tauri
cargo build --release
./target/release/worldlines-desktop        # 或 cargo tauri build 出 .app
```

## 发布前还缺什么

- **签名**:mac 要 Apple Developer ID + 公证,Windows 要 Authenticode。
  在此之前 CI 的 `desktop.yml` 只能手动触发,且刻意不签名、不发布、
  不上传产物 —— 一个「看着像已发布」的未签名包比没有更糟。
- **引擎 sidecar 化**:现在壳假设机器上装了引擎(或有 `uv` + 引擎签出),
  正式发行版要把引擎打成自带二进制(PyInstaller / python-build-standalone)
  再由壳拉起。
