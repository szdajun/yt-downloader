"""共享 fixtures.

`ffmpeg_available` / `ffprobe_available` 自动检测本机是否有 ffmpeg/ffprobe,
集成测试在可用时才跑,缺失时自动 skip(不 fail)。
"""
from __future__ import annotations

import os
import shutil

import pytest

# ffmpeg 目录约定同 yt_downloader.verify / trim / yoga_check:
# env YT_FFMPEG_DIR 可覆盖; 默认 ~/ffmpeg (可移植, 别写死用户名/盘符); 都没有则回退 PATH。
_FFMPEG_DIR = os.environ.get("YT_FFMPEG_DIR") or os.path.expanduser(r"~\ffmpeg")


def _have(name: str) -> bool:
    return shutil.which(name) is not None or os.path.exists(
        os.path.join(_FFMPEG_DIR, f"{name}.exe")
    )


@pytest.fixture
def ffmpeg_available() -> bool:
    return _have("ffmpeg")


@pytest.fixture
def ffprobe_available() -> bool:
    return _have("ffprobe")


@pytest.fixture
def skip_if_no_ffmpeg(ffmpeg_available: bool) -> None:
    if not ffmpeg_available:
        pytest.skip(f"ffmpeg not available on PATH or at {_FFMPEG_DIR}")


@pytest.fixture
def skip_if_no_ffprobe(ffprobe_available: bool) -> None:
    if not ffprobe_available:
        pytest.skip(f"ffprobe not available on PATH or at {_FFMPEG_DIR}")
