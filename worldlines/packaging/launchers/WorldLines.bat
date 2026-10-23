@echo off
REM WorldLines - Windows double-clickable launcher.
REM
REM Double-click opens a cmd window; this script delegates to PowerShell
REM (because the real install flow needs Invoke-RestMethod and env-aware
REM PATH tweaks that are a pain in pure .bat). PowerShell pipes through
REM install.ps1 from worldlines.gg, then execs `worldlines`.
REM
REM IMPORTANT: this file is named WorldLines.bat — the SAME name as the
REM `worldlines` command. On Windows, `where worldlines` and a bare
REM `worldlines` both resolve the CURRENT DIRECTORY first, so if the real
REM CLI is not on PATH they resolve to THIS .bat and the launcher calls
REM itself forever. Therefore we NEVER use bare `worldlines`: we resolve
REM the real installed worldlines.exe by full path (via uv's tool bin dir)
REM and invoke that explicitly.
REM
REM Updates are handled inside the Python launcher at startup. This .bat file
REM must not call uv tool upgrade itself; doing so can loop before the real
REM application gets control.
REM
REM Companion scripts: WorldLines.command (macOS), WorldLines.sh (Linux).

setlocal EnableDelayedExpansion
title WorldLines
cls

echo.
echo   WorldLines launcher
echo.

REM --- resolve the real worldlines.exe by FULL PATH (never bare name) ----
set "WLEXE="
for /f "delims=" %%D in ('uv tool dir --bin 2^>nul') do set "WLBIN=%%D"
if defined WLBIN if exist "!WLBIN!\worldlines.exe" set "WLEXE=!WLBIN!\worldlines.exe"
if not defined WLEXE if exist "%USERPROFILE%\.local\bin\worldlines.exe" set "WLEXE=%USERPROFILE%\.local\bin\worldlines.exe"

if defined WLEXE (
    goto :launch
)

echo   worldlines not installed yet -- running first-time setup
echo.

powershell -ExecutionPolicy ByPass -NoProfile -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$sources = @(" ^
    "  'https://worldlines.gg/install.ps1'," ^
    "  'https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.ps1'," ^
    "  'https://raw.githubusercontent.com/LudicDynamics/WorldLines/main/install.ps1'" ^
    ");" ^
    "$ok = $false;" ^
    "foreach ($u in $sources) {" ^
    "  try {" ^
    "    Write-Host ('Installing from ' + $u + ' ...') -ForegroundColor Cyan;" ^
    "    irm $u | iex;" ^
    "    if ($LASTEXITCODE -ne 0) { throw ('exit code ' + $LASTEXITCODE) }" ^
    "    $ok = $true; break" ^
    "  } catch {" ^
    "    Write-Host ('  failed: ' + $u + ' (' + $_.Exception.Message + ')') -ForegroundColor Yellow" ^
    "  }" ^
    "}" ^
    "if (-not $ok) {" ^
    "  Write-Host '';" ^
    "  Write-Host 'All install sources failed. Tried:' -ForegroundColor Red;" ^
    "  foreach ($u in $sources) { Write-Host ('  - ' + $u) -ForegroundColor Red };" ^
    "  Write-Host 'Please check your internet connection and try again.' -ForegroundColor Red;" ^
    "  exit 1" ^
    "}"

if %ERRORLEVEL% neq 0 (
    echo.
    echo   install failed. Check the output above.
    pause
    exit /b 1
)

REM Re-resolve the full path after install (uv drops it in its tool bin).
REM If uv was JUST installed by the PowerShell step, it may only exist in
REM %USERPROFILE%\.local\bin — add it to PATH so `uv tool dir --bin` works.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
for /f "delims=" %%D in ('uv tool dir --bin 2^>nul') do set "WLBIN=%%D"
if defined WLBIN if exist "!WLBIN!\worldlines.exe" set "WLEXE=!WLBIN!\worldlines.exe"
if not defined WLEXE if exist "%USERPROFILE%\.local\bin\worldlines.exe" set "WLEXE=%USERPROFILE%\.local\bin\worldlines.exe"

if not defined WLEXE (
    echo.
    echo   setup finished but worldlines.exe was not found.
    echo   Open a new cmd or PowerShell and run: worldlines
    pause
    exit /b 1
)

:launch
echo.
REM Make uv's bin dir visible to the app we're about to launch, so the
REM in-app auto-updater (which shells out to `uv tool upgrade`) can find uv
REM even when this double-clicked cmd window started with a minimal PATH.
REM Without this, the updater silently fell back to a no-op and the user
REM "pressed y but stayed on the old version".
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
REM Recursion guard: never exec this very script.
if /i "%WLEXE%"=="%~f0" (
    echo   internal error: resolved launcher to itself; aborting to avoid a loop.
    pause
    exit /b 1
)
REM Bare `worldlines` now boots the engine and opens the Web LocalShell in
REM the browser (the TUI moved to `worldlines tui`) — this console is the
REM engine's log window and must stay open. Windows Terminal is still
REM preferred when available: nicer console, and if a user runs
REM `worldlines tui` here the textual TUI renders correctly (Git Bash /
REM MinTTY would garble it). Skip if we're already inside Windows Terminal
REM (WT_SESSION), fall back to in-place when wt.exe isn't installed.
if defined WT_SESSION goto :run_inplace
where wt.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" wt.exe "%WLEXE%"
    exit /b 0
)
:run_inplace
"%WLEXE%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo   worldlines exited with code %RC%.
    pause
)
endlocal
