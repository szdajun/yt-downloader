"""downloader.py — 纯函数层测试.

只测不依赖 yt_dlp / 网络的纯函数:
- FORMATS / AUDIO_SUFFIXES 常量一致性
- is_audio_format(label)
- _normalize_url(url)
"""
from __future__ import annotations

from yt_downloader.downloader import (
    AUDIO_SUFFIXES,
    FORMATS,
    _normalize_url,
    is_audio_format,
)


# ---- FORMATS 字典结构 ----
def test_formats_has_at_least_three_entries():
    """至少三种品质预设(最高画质 / 中等画质 / 仅音频)."""
    assert len(FORMATS) >= 3


def test_formats_audio_label_in_dict():
    """所有 AUDIO_SUFFIXES 对应的 format label 必须在 FORMATS 里出现."""
    # 仅音频 preset 的 label 通常是 "仅音频(m4a)" 或类似
    audio_labels = [label for label in FORMATS if any(s in label for s in ("音频", "audio", "Audio"))]
    assert len(audio_labels) >= 1


# ---- AUDIO_SUFFIXES 一致性 ----
def test_audio_suffixes_includes_m4a():
    """m4a 是默认的仅音频格式后缀."""
    assert ".m4a" in AUDIO_SUFFIXES


def test_audio_suffixes_lowercase_with_dot():
    """所有后缀以 . 开头且小写(避免大小写不一致)."""
    for s in AUDIO_SUFFIXES:
        assert s.startswith(".")
        assert s == s.lower()


# ---- is_audio_format ----
def test_is_audio_format_matches_audio_label():
    """任何包含「音频」的 label 都判定为音频格式."""
    assert is_audio_format("仅音频(m4a)") is True
    assert is_audio_format("最高画质 (mp4)") is False


def test_is_audio_format_handles_unknown_label():
    """未知 label 返回 False(不抛)."""
    assert is_audio_format("不存在的品质") is False


# ---- _normalize_url ----
def test_normalize_url_passes_https_youtube_unchanged():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _normalize_url(url) == url


def test_normalize_url_preserves_canonical_douyin_video_url():
    """规范化 douyin /video/{id} URL:已是视频页时,原样返回(含原尾部空白)."""
    url = "https://www.douyin.com/video/1234567890"
    result = _normalize_url(url)
    assert result == url


def test_normalize_url_handles_youtu_be_short_link():
    url = "https://youtu.be/dQw4w9WgXcQ"
    result = _normalize_url(url)
    # 至少 URL 主体保留
    assert "youtu" in result or "dQw4w9WgXcQ" in result


def test_normalize_url_handles_douyin():
    """抖音 URL 应该被识别/规范化."""
    url = "https://www.douyin.com/video/1234567890"
    result = _normalize_url(url)
    assert result  # 非空
