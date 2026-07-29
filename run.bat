@echo off
chcp 65001 >nul
title YT 视频下载器
cd /d "%~dp0"
echo ============================================
echo   YT 视频下载器  (首次启动会自动装依赖)
echo ============================================
echo.
uv run python -m yt_downloader.app
if errorlevel 1 (
    echo.
    echo [启动失败] 见上方错误。首次运行需联网装依赖 (yt-dlp + PySide6)。
    pause
)
