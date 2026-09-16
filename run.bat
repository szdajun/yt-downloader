@echo off
title YT Video Downloader
cd /d "%~dp0"

rem --- Self-locate uv (avoids PATH-stripped launch contexts) ---
rem Check each candidate with the common Windows executable extensions (PATHEXT).
set "UV="
for %%E in (exe bat cmd) do (
    for %%P in (
        "%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.%%E"
        "%USERPROFILE%\.local\bin\uv.%%E"
        "%USERPROFILE%\.cargo\bin\uv.%%E"
        "D:\Python\.pyenv\pyenv-win\shims\uv.%%E"
        "C:\Python\pyenv-win\shims\uv.%%E"
        "C:\Users\pyenv\shims\uv.%%E"
        "D:\Python\.pyenv\pyenv-win\shims\uv"
        "C:\Python\pyenv-win\shims\uv"
    ) do (
        if exist "%%~P" (
            set "UV=%%~P"
            goto :uv_found
        )
    )
)
where uv >nul 2>&1
if not errorlevel 1 (
    set "UV=uv"
    goto :uv_found
)

echo [ERROR] 'uv' not found on PATH and not in known install locations.
echo Install one of:
echo   1) winget install astral-sh.uv
echo   2) pip install uv   (then put uv.exe on PATH)
echo   3) pyenv install via pyenv-win
echo See README.md - Quick Start for details.
pause
exit /b 1

:uv_found
rem Make sure the directory holding uv (and its pyenv dispatch) is on PATH for
rem this child process — otherwise the pyenv-win shim cannot find pyenv.
for %%D in ("%UV%") do set "UV_DIR=%%~dpD"
set "PATH=%UV_DIR%;D:\Python\.pyenv\pyenv-win\bin;%PATH%"

echo Using uv:  %UV%
echo Starting GUI (first run installs dependencies, ~1-2 min)...
echo.

"%UV%" run python -m yt_downloader.app
set "RC=%errorlevel%"

rem NOTE: keep this error text OUT of an if (...) block. cmd treats an unescaped
rem ")" inside an echo as the block terminator: the block is truncated there and
rem the leftover lines fall through to top level, running unconditionally.
rem Early-exit + flat layout avoids that whole class of bug.
if "%RC%"=="0" exit /b 0

echo.
echo [ERROR] GUI exited with code %RC%.
echo Common causes:
echo   - Missing Node.js / Deno / Bun (YouTube sign-in challenge needs a JS runtime)
echo   - PySide6 platform plugin failed (e.g. no display in a service session)
echo Re-run from a regular desktop session for the GUI window.
pause
exit /b %RC%