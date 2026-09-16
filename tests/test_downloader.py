"""downloader.py — 纯函数层测试.

只测不依赖 yt_dlp / 网络的纯函数:
- FORMATS / AUDIO_SUFFIXES 常量一致性
- is_audio_format(label)
- _normalize_url(url)
"""
from __future__ import annotations

import os

from yt_downloader import downloader
from yt_downloader.douyin_browser import DouyinBrowserUnavailable, DouyinVideo, Gear
from yt_downloader.downloader import (
    AUDIO_SUFFIXES,
    FORMATS,
    _free_slot,
    _make_opts,
    _normalize_url,
    download,
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


# ---- 代理分流 (抖音直连 / YouTube 走代理) ----
def test_make_opts_direct_forces_no_proxy():
    """抖音路径 direct=True → proxy="" (yt-dlp 翻成 __noproxy__ 强制直连).

    抖音对非中国大陆 IP 地理封锁, 而本机 HTTP(S)_PROXY 指向境外节点.
    """
    opts = _make_opts("/tmp", "最高画质 (mp4)", lambda d: None, direct=True)
    assert opts["proxy"] == ""


def test_make_opts_default_inherits_env_proxy():
    """默认不设 proxy → yt-dlp 继承环境代理 (YouTube 必须走代理)."""
    opts = _make_opts("/tmp", "最高画质 (mp4)", lambda d: None)
    assert "proxy" not in opts


# ---- _free_slot ----
def test_free_slot_returns_candidate_when_free(tmp_path):
    assert _free_slot(str(tmp_path / "a.mp4")) == str(tmp_path / "a.mp4")


def test_free_slot_bumps_until_free(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert _free_slot(str(tmp_path / "a.mp4")) == str(tmp_path / "a(1).mp4")
    (tmp_path / "a(1).mp4").write_bytes(b"x")
    assert _free_slot(str(tmp_path / "a.mp4")) == str(tmp_path / "a(2).mp4")


# ---- download() 抖音分流 ----
def test_download_routes_douyin_to_browser_path(tmp_path, monkeypatch):
    """抖音 URL 不得落到 yt-dlp 通路 (其 DouyinIE 已被签名墙打死)."""
    seen = {}

    def fake_extract(url, **kw):
        seen["url"] = url
        return None                       # 取流失败

    monkeypatch.setattr(downloader, "extract_douyin", fake_extract)
    errs = []
    path, skipped = download("https://www.douyin.com/jingxuan?modal_id=7685199522498698100",
                             str(tmp_path), "最高画质 (mp4)", on_error=errs.append)
    assert seen["url"] == "https://www.douyin.com/video/7685199522498698100"  # 先规范化
    assert path is None and skipped is False
    assert errs and "抖音" in errs[0]


def test_download_douyin_reports_unavailable_browser(tmp_path, monkeypatch):
    """Playwright 没装/无浏览器 → 可读报错, 不抛异常."""
    def boom(url, **kw):
        raise DouyinBrowserUnavailable("没装 Playwright")

    monkeypatch.setattr(downloader, "extract_douyin", boom)
    errs = []
    path, _ = download("https://www.douyin.com/video/123", str(tmp_path),
                       "最高画质 (mp4)", on_error=errs.append)
    assert path is None
    assert errs and "取流不可用" in errs[0]


def _patch_fake_ydl(monkeypatch, *, write=True):
    """把 yt_dlp.YoutubeDL 换成假桩: 真类算文件名, download() 只记录+落盘占位文件.

    真 YoutubeDL 会在构造时**原地**把 opts["outtmpl"] 从字符串改写成
    {'default': ..., 'chapter': ...} 字典, 故读回时要兼容两种形态.
    返回 download() 的调用记录 (urls 列表), 用来断言是否真的下了.
    """
    real_ydl = downloader.yt_dlp.YoutubeDL      # 打桩前抓住真类
    calls: list[list[str]] = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
            self._real = real_ydl(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self._real.__exit__(*a)

        def prepare_filename(self, info):
            return self._real.prepare_filename(info)

        def download(self, urls):
            calls.append(list(urls))
            if write:
                out = self.opts["outtmpl"]
                target = out["default"] if isinstance(out, dict) else out
                # 模拟 FFmpegExtractAudio: 抽出 m4a 并删掉中间 mp4 (yt-dlp 默认行为)
                if any(p.get("key") == "FFmpegExtractAudio"
                       for p in (self.opts.get("postprocessors") or [])):
                    target = os.path.splitext(target)[0] + ".m4a"
                with open(target, "wb") as f:
                    f.write(b"fake")

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    return calls


def test_download_douyin_writes_named_file_and_returns_it(tmp_path, monkeypatch):
    """取流成功 → 产物名沿用 %(title).100B [%(id)s].%(ext)s, 下游按 [id] 可定位."""
    video = DouyinVideo(vid="7685199522498698100", title="瑜伽流动 #自律",
                        duration=82.8,
                        gears=[Gear("normal_1080_0", 1080, 1920, 2898,
                                    "https://v26-web.douyinvod.com/x.mp4")])
    monkeypatch.setattr(downloader, "extract_douyin", lambda url, **kw: video)
    calls = _patch_fake_ydl(monkeypatch)

    path, skipped = download("https://www.douyin.com/video/7685199522498698100",
                             str(tmp_path), "最高画质 (mp4)")
    assert skipped is False
    assert path is not None and os.path.exists(path)
    assert "[7685199522498698100]" in os.path.basename(path)
    assert path.endswith(".mp4")
    assert calls == [["https://v26-web.douyinvod.com/x.mp4"]]   # 下的就是选中档的直链


def test_download_douyin_skips_existing_file(tmp_path, monkeypatch):
    """目标文件已存在 → 增量跳过 (与 YouTube 通路一致), 不触发下载."""
    video = DouyinVideo(vid="123", title="t", duration=40.0,
                        gears=[Gear("g", 720, 1280, 1000, "https://c/x.mp4")])
    monkeypatch.setattr(downloader, "extract_douyin", lambda url, **kw: video)
    existing = tmp_path / "t [123].mp4"
    existing.write_bytes(b"old")
    calls = _patch_fake_ydl(monkeypatch)

    path, skipped = download("https://www.douyin.com/video/123", str(tmp_path),
                             "最高画质 (mp4)")
    assert skipped is True
    assert path == str(existing)
    assert calls == []      # 关键: 一次都没下


def test_download_douyin_audio_uses_m4a_target(tmp_path, monkeypatch):
    """仅音频预设 → 产物落到 .m4a 名 (中间 mp4 由 yt-dlp 抽音频后删掉)."""
    video = DouyinVideo(vid="999", title="t", duration=40.0,
                        gears=[Gear("g", 1080, 1920, 2898, "https://c/x.mp4")])
    monkeypatch.setattr(downloader, "extract_douyin", lambda url, **kw: video)
    _patch_fake_ydl(monkeypatch)

    path, skipped = download("https://www.douyin.com/video/999", str(tmp_path),
                             "仅音频 (m4a)")
    assert skipped is False
    assert path is not None and path.endswith(".m4a")
    assert os.path.exists(path)
