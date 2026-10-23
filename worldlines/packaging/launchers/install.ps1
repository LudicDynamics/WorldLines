# WorldLines / NeonRP bootstrap installer — PowerShell edition
#
# Usage (from PowerShell):
#   irm https://worldlines.gg/install.ps1 | iex
#
# Or via WorldLines.bat which chains into this script.
#
# What it does:
#   1. Ensures `uv` is installed (fetches from astral.sh if missing).
#   2. Installs `worldlines` (pulls the pinned `neonrp` runtime too).
#   3. Prints a next-step hint.
#
# Env hooks (same semantics as install.sh):
#   $env:CHINA_MIRROR = "1"   route uv through Tsinghua PyPI mirror
#   $env:UV_DEFAULT_INDEX     user override — always wins if set

$ErrorActionPreference = "Stop"
# Make native commands (uv, etc.) honor $ErrorActionPreference on PS 7.3+.
# On older PowerShell this is a no-op — we check $LASTEXITCODE explicitly below.
if (Get-Command -Name '$PSNativeCommandUseErrorActionPreference' -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$package = if ($env:WORLDLINES_PACKAGE) { $env:WORLDLINES_PACKAGE } else { "worldlines" }
$forceInstall = ($env:WORLDLINES_FORCE_INSTALL -eq "1" -or $env:WORLDLINES_FORCE_INSTALL -eq "true")

# Double-click vs `irm | iex`: when this script runs as a FILE (double-click,
# or chained from WorldLines.bat), $PSCommandPath is set and the console
# closes the instant the script ends — the user never sees success or the
# error. When piped through `iex`, $PSCommandPath is $null and a pause would
# hang the one-liner. So pause ONLY when run as a file.
$RanAsFile = [bool]$PSCommandPath
function Hold() {
    if ($RanAsFile) {
        Write-Host ""
        try { Read-Host "Press Enter to close this window" | Out-Null } catch { }
    }
}

function Log($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "xx  $msg" -ForegroundColor Red; Hold; exit 1 }

# Any uncaught terminating error (with $ErrorActionPreference=Stop) would
# otherwise slam the window shut before the message is readable.
trap { Write-Host "xx  $($_.Exception.Message)" -ForegroundColor Red; Hold; exit 1 }

# Make uv-tool default bin dirs visible for this PowerShell session, so
# the user can run `worldlines` immediately after `irm | iex` finishes.
# Idempotent — only prepends if the dir exists and isn't already there.
$extra = @("$env:USERPROFILE\.local\bin")
if ($env:CARGO_HOME) { $extra += "$env:CARGO_HOME\bin" }
$extra += "$env:USERPROFILE\.cargo\bin"
$extra = $extra | Where-Object { $_ -and (Test-Path $_) }
foreach ($p in $extra) {
    if (";$env:PATH;" -notlike "*;$p;*") {
        $env:PATH = "$p;$env:PATH"
    }
}

# Step 1 — ensure uv (astral's Python/tool installer).
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Log "uv already installed ($(uv --version))"
} else {
    Log "installing uv from astral.sh"
    try {
        powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    } catch {
        Die "failed to install uv: $_"
    }
    # uv's installer may have just dropped binaries — re-check the same
    # candidate dirs and prepend anything new.
    $extra = @("$env:USERPROFILE\.local\bin")
    if ($env:CARGO_HOME) { $extra += "$env:CARGO_HOME\bin" }
    $extra += "$env:USERPROFILE\.cargo\bin"
    $extra = $extra | Where-Object { $_ -and (Test-Path $_) }
    foreach ($p in $extra) {
        if (";$env:PATH;" -notlike "*;$p;*") {
            $env:PATH = "$p;$env:PATH"
        }
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Die "uv installed but not found on PATH; open a new PowerShell and re-run this script"
    }
}

# Step 1.5 — optional China PyPI mirror.
if ($env:CHINA_MIRROR -eq "1" -and -not $env:UV_DEFAULT_INDEX) {
    $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
    Log "CHINA_MIRROR=1 -> using Tsinghua PyPI mirror"
}

# Step 2 — install the CLI via uv tool.
# The `worldlines` wheel pins `neonrp[discord]` transitively (since
# 0.1.8), so the Discord bridge wires up out of the box.
$installedExe = $null
try {
    $toolBinProbe = (uv tool dir --bin 2>$null).Trim()
    if ($toolBinProbe) {
        $candidate = Join-Path $toolBinProbe "$package.exe"
        if (Test-Path $candidate) { $installedExe = $candidate }
    }
} catch { }

if ($installedExe -and -not $forceInstall) {
    Log "$package already installed"
} else {
    if ($forceInstall) {
        Log "reinstalling $package"
        uv tool install --force $package
    } else {
        Log "installing $package"
        uv tool install $package
    }
    # $ErrorActionPreference=Stop does NOT catch non-zero exit codes from
    # native commands on PowerShell < 7.3. Check explicitly.
    if ($LASTEXITCODE -ne 0) {
        Die "uv tool install failed (exit code $LASTEXITCODE)"
    }
}

# Step 2.5 — persist PATH for *future* PowerShell windows.
# Unlike Unix dotfiles, Windows user PATH lives in the registry
# (HKCU\Environment), and almost every Windows installer (Node.js, Rust,
# Python, etc.) writes there — it's the platform-native way, not a
# silent dotfile edit. `uv tool update-shell` is idempotent.
try {
    uv tool update-shell | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "uv tool update-shell exited with code $LASTEXITCODE"
    }
    $shellUpdated = $true
} catch {
    $shellUpdated = $false
    Warn "could not auto-update User PATH; see manual instructions below"
}

$toolBin = $null
try { $toolBin = (uv tool dir --bin 2>$null).Trim() } catch { }
# Make the tool bin visible in THIS session too. `uv tool update-shell` only
# writes the registry (HKCU\Environment), which Windows does NOT apply to an
# already-open shell — so without this, `worldlines` is CommandNotFound in the
# very window that just installed it, even though we tell the user "this window
# already has it". Prepend it to the live $env:PATH so the command works now.
if ($toolBin -and (";$env:PATH;" -notlike "*;$toolBin;*")) {
    $env:PATH = "$toolBin;$env:PATH"
}
$pathHintNeeded = -not (Get-Command $package -ErrorAction SilentlyContinue)

# Step 3 — quick-start hint.
Write-Host ""
Write-Host "✓ $package installed" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  $package              # launch the guided world picker"
Write-Host "  neonrp --help         # full engine CLI"
Write-Host "  neonrp self-update    # check for updates"
Write-Host ""

# Transparency: tell the user exactly what we did to their User PATH.
if ($shellUpdated -and $toolBin) {
    Write-Host "  PATH update: $toolBin added to your User PATH (registry)." -ForegroundColor DarkGray
    Write-Host "  This window already has it. New terminals will pick it up automatically." -ForegroundColor DarkGray
    Write-Host ""
}

if ($pathHintNeeded) {
    Warn "$package is installed but not on this shell's PATH."
    if ($toolBin) {
        Write-Host "    Open a NEW PowerShell and try again, or for this session only:"
        Write-Host "      `$env:PATH = `"$toolBin;`$env:PATH`""
        if (-not $shellUpdated) {
            Write-Host ""
            Write-Host "    To persist for new terminals (manual fallback):"
            Write-Host "      [Environment]::SetEnvironmentVariable("
            Write-Host "          'Path',"
            Write-Host "          [Environment]::GetEnvironmentVariable('Path','User') + ';$toolBin',"
            Write-Host "          'User')"
        }
    } else {
        Write-Host "    Open a NEW PowerShell and try ``$package`` again."
    }
    Write-Host ""
}
Write-Host "Docs: https://github.com/LudicDynamics/WorldLines"
Write-Host ""
Hold
