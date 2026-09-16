"""verify.py — 准入门槛阈值 + ProbeResult 性质 + probe() 调用.

两层:
- 纯函数层(无 subprocess):阈值边界、ProbeResult.*_ok、failures
- 集成层(real ffprobe):`probe()` 真实调用(自动 skip if ffprobe 不在)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from yt_downloader.verify import (
    THRESH_BITRATE,
    THRESH_DURATION,
    THRESH_SHORT_SIDE,
    ProbeResult,
    probe,
)


# ---- 阈值常量钉死 ----
def test_thresholds_constants():
    assert THRESH_SHORT_SIDE == 720
    assert THRESH_BITRATE == 2_000_000
    assert THRESH_DURATION == 30.0


# ---- ProbeResult 几何/性质 ----
def _r(width=1920, height=1080, duration=120.0, bit_rate=6_000_000, codec="h264"):
    return ProbeResult(width=width, height=height, duration=duration,
                       bit_rate=bit_rate, codec=codec, path="x.mp4")


def test_short_side_landscape():
    assert _r(1920, 1080).short_side == 1080


def test_short_side_portrait():
    assert _r(1080, 1920).short_side == 1080


def test_short_side_zero_when_no_video():
    assert _r(0, 0).short_side == 0


def test_short_side_ok_above_threshold():
    # 1080 > 720
    assert _r(1920, 1080).short_side_ok is True


def test_short_side_ok_below_threshold():
    # 720 = 720 边界:达标(>=)
    assert _r(1280, 720).short_side_ok is True
    # 704 < 720 不达标
    assert _r(1280, 704).short_side_ok is False


def test_bitrate_ok_at_threshold():
    assert _r(bit_rate=2_000_000).bitrate_ok is True
    assert _r(bit_rate=1_999_999).bitrate_ok is False


def test_bitrate_threshold_sits_in_douyin_natural_gap():
    """2.0 Mbps 不是拍脑袋: 它落在抖音实测的天然断层 1785~2119 kbps 之间.

    2026-09-17 实测抖音码率阶梯(样本 7685199522498698100, 1080x1920):
      1080p 档 2119 / 2175 / 2834 / 2898 kbps  (容器实测 2.90 Mbps)
       720p 档  618 ~ 1785 kbps
    门槛落断层里 → 放行 1080p、挡住 720p。720p 的短边恰好是 720 能过分辨率
    门槛, 只能靠码率挡 —— 所以这个数直接决定下游拿到 1080p 还是 720p。
    """
    douyin_1080p = (2_119_000, 2_175_000, 2_834_000, 2_898_000)
    douyin_720p = (618_000, 1_650_000, 1_785_000)
    for br in douyin_1080p:
        assert _r(bit_rate=br).bitrate_ok is True, f"1080p {br} 应放行"
    for br in douyin_720p:
        assert _r(bit_rate=br).bitrate_ok is False, f"720p {br} 应挡住"


def test_failures_bitrate_message_follows_threshold():
    """报错文案必须跟着常量走 —— 这里硬编码过一次, 改门槛最容易漏."""
    msg = next(f for f in _r(bit_rate=1_000_000).failures if "码率" in f)
    assert f"< {THRESH_BITRATE / 1e6:g} Mbps" in msg
    assert "5 Mbps" not in msg


def test_duration_ok_at_threshold():
    assert _r(duration=30.0).duration_ok is True
    assert _r(duration=29.9).duration_ok is False


def test_ok_all_passing():
    r = _r()
    assert r.ok is True
    assert r.failures == []


def test_ok_no_video():
    r = _r(width=0, height=0)
    assert r.ok is False
    assert r.failures == ["无视频流 (纯音频?)"]


def test_failures_lists_each_failing_criterion():
    # 短边 < 720, 码率 < 2Mbps, 时长 < 30s — 三项都不达标
    r = _r(width=640, height=360, duration=10.0, bit_rate=1_000_000)
    assert r.ok is False
    assert len(r.failures) == 3
    assert any("短边" in f for f in r.failures)
    assert any("码率" in f for f in r.failures)
    assert any("时长" in f for f in r.failures)


# ---- probe() subprocess mock 层 ----
def test_probe_returns_none_when_file_not_found():
    """probe() 对不存在的路径返回 None,不抛."""
    with patch("yt_downloader.verify.subprocess.run",
               side_effect=FileNotFoundError):
        assert probe("Z:/nonexistent.mp4") is None


def test_probe_returns_none_when_timeout():
    with patch("yt_downloader.verify.subprocess.run",
               side_effect=__import__("subprocess").TimeoutExpired(cmd="x", timeout=30)):
        assert probe("any.mp4") is None


def test_probe_parses_valid_ffprobe_json():
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps({
        "streams": [{"width": 1920, "height": 1080, "codec_name": "h264"}],
        "format": {"duration": "120.5", "bit_rate": "6000000"},
    })
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        r = probe("any.mp4")
    assert r is not None
    assert r.width == 1920 and r.height == 1080
    assert r.duration == 120.5
    assert r.bit_rate == 6_000_000
    assert r.codec == "h264"
    assert r.ok is True


def test_probe_returns_none_on_nonzero_returncode():
    fake = MagicMock()
    fake.returncode = 1
    fake.stdout = ""
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        assert probe("any.mp4") is None


def test_probe_returns_none_on_invalid_json():
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "not json"
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        assert probe("any.mp4") is None


def test_probe_handles_missing_fields_gracefully():
    """ffprobe 输出里字段缺失时,probe() 仍返回 ProbeResult(不全 None)."""
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps({"streams": [{}], "format": {}})
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        r = probe("any.mp4")
    assert r is not None
    assert r.width == 0
    assert r.height == 0
    assert r.bit_rate == 0
    assert r.has_video is False
    assert r.ok is False


# ---- 集成层(real ffprobe)— 自动 skip if not available ----
def test_probe_integration_real_video(skip_if_no_ffprobe, tmp_path):
    """真实 ffprobe 调用 — 跳过 if ffprobe 不在."""
    # 找一个本机真实视频文件测(用户 Downloads 目录或 yt_downloader assets/)
    from pathlib import Path
    candidates = [
        Path.home() / "Downloads",
        Path(r"F:\wkspace\yt-downloader\yt_downloader\assets"),
    ]
    video = None
    for d in candidates:
        if not d.exists():
            continue
        for ext in ("*.mp4", "*.mkv", "*.webm"):
            matches = list(d.glob(ext))
            if matches:
                video = matches[0]
                break
        if video:
            break
    if video is None:
        pytest.skip("no test video found in standard locations")

    r = probe(str(video))
    if r is None:
        pytest.skip("ffprobe could not parse the test video")
    assert r.has_video
    assert r.width > 0 and r.height > 0
