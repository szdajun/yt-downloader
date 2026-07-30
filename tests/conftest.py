"""共享 fixtures.

`ffmpeg_available` / `ffprobe_available` 自动检测本机是否有 ffmpeg/ffprobe,
集成测试在可用时才跑,缺失时自动 skip(不 fail)。
"""
from __future__ import annotations

import shutil

import pytest


@pytest.fixture
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None or shutil.which(
        r"C:\Users\18091\ffmpeg\ffmpeg.exe"
    ) is not None


@pytest.fixture
def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None or shutil.which(
        r"C:\Users\18091\ffmpeg\ffprobe.exe"
    ) is not None


@pytest.fixture
def skip_if_no_ffmpeg(ffmpeg_available: bool) -> None:
    if not ffmpeg_available:
        pytest.skip("ffmpeg not available on PATH or at C:\\Users\\18091\\ffmpeg")


@pytest.fixture
def skip_if_no_ffprobe(ffprobe_available: bool) -> None:
    if not ffprobe_available:
        pytest.skip("ffprobe not available on PATH or at C:\\Users\\18091\\ffmpeg")
