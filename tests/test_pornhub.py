"""pornhub.py — 取流的纯函数层测试.

只测不依赖网络/curl_cffi 的纯函数 (与 test_douyin_browser.py 同构):
- is_pornhub_url / viewkey      域名与 id 识别
- parse_flashvars / hls_gears   页面 flashvars → 候选档位
- pick_best_gear                选档
- parse_playlist / segment_jobs / rewrite_local   m3u8 → 本地抓取计划与本地 playlist
- progress_dict                 分片进度 → yt-dlp 风格进度字典 (GUI 直接吃)
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from yt_downloader.pornhub import (
    HlsGear,
    Playlist,
    hls_gears,
    is_pornhub_url,
    parse_flashvars,
    parse_playlist,
    pick_best_gear,
    progress_dict,
    rewrite_local,
    segment_jobs,
    viewkey,
)

BASE = "https://hv-h.phncdn.com/hls/c6251/videos/202601/30/37831245/1080P_4000K_37831245.mp4/master.m3u8"


# ---- is_pornhub_url ----
@pytest.mark.parametrize("url", [
    "https://cn.pornhub.com/view_video.php?viewkey=697c4901ab738",
    "https://www.pornhub.com/view_video.php?viewkey=abc",
    "https://pornhub.com/embed/697c4901ab738",
    "https://rt.pornhub.org/view_video.php?viewkey=abc",
    "https://www.pornhubpremium.com/view_video.php?viewkey=abc",
])
def test_is_pornhub_url_true(url):
    assert is_pornhub_url(url) is True


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.douyin.com/video/123",
    "https://example.com/pornhub.com/view_video.php",   # 非同域, 只是路径里出现
    "",
])
def test_is_pornhub_url_false(url):
    assert is_pornhub_url(url) is False


def test_is_pornhub_url_not_fooled_by_lookalike_domain():
    """notpornhub.com 不是 pornhub 域 (避免 endswith 误判)."""
    assert is_pornhub_url("https://notpornhub.com/view_video.php?viewkey=a") is False


# ---- viewkey ----
def test_viewkey_from_query():
    assert viewkey("https://cn.pornhub.com/view_video.php?viewkey=697c4901ab738") == "697c4901ab738"


def test_viewkey_from_embed_path():
    assert viewkey("https://www.pornhub.com/embed/697c4901ab738") == "697c4901ab738"


def test_viewkey_from_bare_id():
    assert viewkey("697c4901ab738") == "697c4901ab738"


def test_viewkey_with_extra_query_params():
    assert viewkey("https://cn.pornhub.com/view_video.php?viewkey=abc123&t=9") == "abc123"


@pytest.mark.parametrize("bad", ["", "   ", "https://cn.pornhub.com/", "https://example.com/x"])
def test_viewkey_none_when_absent(bad):
    assert viewkey(bad) is None


# ---- 测试夹具: 真实结构的 flashvars (已裁剪) ----
def _hls(q, w, h, host="hv-h.phncdn.com"):
    return {"format": "hls", "quality": str(q), "width": w, "height": h,
            "videoUrl": f"https://{host}/hls/x/{q}P_4000K_x.mp4/master.m3u8?h=abc&e=1"}


def _flashvars(defs):
    return {"video_duration": "1614", "mediaDefinitions": defs}


def _html(fv=None, raw=None):
    body = raw if raw is not None else json.dumps(fv)
    return f"<html><script>var flashvars_99999 = {body};</script></html>"


# ---- parse_flashvars ----
def test_parse_flashvars_extracts_dict():
    fv = _flashvars([_hls(1080, 1920, 1080)])
    assert parse_flashvars(_html(fv)) == fv


def test_parse_flashvars_none_when_absent():
    """反爬维护页 / 无 flashvars 的页面 → None (调用方据此重试)."""
    assert parse_flashvars("<html><body>Down for Maintenance 403</body></html>") is None


def test_parse_flashvars_none_on_malformed_json():
    assert parse_flashvars(_html(raw="{not json}")) is None
    assert parse_flashvars("") is None


# ---- hls_gears ----
def test_hls_gears_keeps_only_hls_with_url():
    """mp4+remote 那条(get_media, 被反爬挡死)与空 url 的都要丢掉."""
    fv = _flashvars([
        _hls(1080, 1920, 1080),
        {"format": "hls", "quality": "720", "width": 1280, "height": 720, "videoUrl": ""},
        {"format": "mp4", "quality": [], "remote": True,
         "videoUrl": "https://cn.pornhub.com/video/get_media"},
    ])
    gears = hls_gears(fv)
    assert [g.quality for g in gears] == [1080]
    assert gears[0].width == 1920 and gears[0].height == 1080
    assert gears[0].short_side == 1080


def test_hls_gears_survives_garbage():
    """任意垃圾输入都不抛 (页面结构随时可能变)."""
    for bad in ({}, {"mediaDefinitions": None}, {"mediaDefinitions": ["x", 3]},
                {"mediaDefinitions": [{"format": "hls"}]}):
        assert hls_gears(bad) == []


def test_hls_gears_skips_non_numeric_quality():
    fv = _flashvars([
        {"format": "hls", "quality": "", "width": 1, "height": 1, "videoUrl": "https://x/y.m3u8"},
        _hls(480, 854, 480),
    ])
    assert [g.quality for g in hls_gears(fv)] == [480]


# ---- pick_best_gear ----
def test_pick_best_gear_highest_quality():
    gears = [HlsGear(240, 426, 240, "u1"), HlsGear(1080, 1920, 1080, "u3"),
             HlsGear(720, 1280, 720, "u2")]
    assert pick_best_gear(gears).url == "u3"


def test_pick_best_gear_empty_returns_none():
    assert pick_best_gear([]) is None


# ---- parse_playlist: master (variant) ----
MASTER = "\n".join([
    "#EXTM3U",
    "#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=4000000,RESOLUTION=1920x1080",
    "1080P_4000K_37831245.mp4/index.m3u8?h=abc&e=1",
])


def test_parse_playlist_master_detected_and_variant_resolved_absolute():
    pl = parse_playlist(MASTER, BASE)
    assert pl.is_master is True
    assert pl.variant == ("https://hv-h.phncdn.com/hls/c6251/videos/202601/30/"
                          "37831245/1080P_4000K_37831245.mp4/"
                          "1080P_4000K_37831245.mp4/index.m3u8?h=abc&e=1")


# ---- parse_playlist: media ----
MEDIA_TS = "\n".join([
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    "#EXT-X-TARGETDURATION:18",
    "#EXTINF:18.000,",
    "seg-1.ts?h=abc",
    "#EXTINF:18.000,",
    "seg-2.ts?h=abc",
    "#EXT-X-ENDLIST",
])

MEDIA_FMP4 = "\n".join([
    "#EXTM3U",
    '#EXT-X-MAP:URI="init-v1-a1.mp4?h=k&e=1"',
    "#EXTINF:18.000,",
    "seg-1-v1-a1.m4s",
    "#EXTINF:18.000,",
    "seg-2-v1-a1.m4s",
    "#EXT-X-ENDLIST",
])

MEDIA_AES = "\n".join([
    "#EXTM3U",
    '#EXT-X-KEY:METHOD=AES-128,URI="https://cdn/enc.key?h=z",IV=0x1234',
    "#EXTINF:18.000,",
    "seg-1.ts",
    "#EXT-X-ENDLIST",
])


def test_parse_playlist_media_segments_and_absolute_urls():
    pl = parse_playlist(MEDIA_TS, BASE)
    assert pl.is_master is False
    assert pl.segs == ["seg-1.ts?h=abc", "seg-2.ts?h=abc"]
    assert pl.key_uri is None and pl.map_uri is None


def test_parse_playlist_reads_ext_x_map():
    pl = parse_playlist(MEDIA_FMP4, BASE)
    assert pl.map_uri == ("https://hv-h.phncdn.com/hls/c6251/videos/202601/30/"
                          "37831245/1080P_4000K_37831245.mp4/init-v1-a1.mp4?h=k&e=1")
    assert pl.segs == ["seg-1-v1-a1.m4s", "seg-2-v1-a1.m4s"]


def test_parse_playlist_reads_aes_key():
    pl = parse_playlist(MEDIA_AES, BASE)
    assert pl.key_uri == "https://cdn/enc.key?h=z"
    assert pl.segs == ["seg-1.ts"]


def test_parse_playlist_empty_or_garbage():
    for bad in ("", "request incorrect", "#EXTM3U"):
        pl = parse_playlist(bad, BASE)
        assert pl.segs == []
        assert pl.is_master is False


# ---- segment_jobs / rewrite_local: 两者必须同序同名 ----
def test_segment_jobs_names_align_with_rewrite():
    pl = parse_playlist(MEDIA_TS, BASE)
    jobs = segment_jobs(pl)
    assert [n for n, _ in jobs] == ["seg_00000.ts", "seg_00001.ts"]
    assert jobs[0][1] == ("https://hv-h.phncdn.com/hls/c6251/videos/202601/30/"
                          "37831245/1080P_4000K_37831245.mp4/seg-1.ts?h=abc")
    txt = rewrite_local(pl)
    assert "seg_00000.ts" in txt and "seg_00001.ts" in txt
    assert "seg-1.ts" not in txt          # 远端 URI 必须已被替换
    assert txt.startswith("#EXTM3U") and txt.endswith("\n")


def test_segment_jobs_puts_init_and_key_first():
    jobs = segment_jobs(parse_playlist(MEDIA_FMP4, BASE))
    assert [n for n, _ in jobs] == ["init.mp4", "seg_00000.m4s", "seg_00001.m4s"]
    txt = rewrite_local(parse_playlist(MEDIA_FMP4, BASE))
    assert '#EXT-X-MAP:URI="init.mp4"' in txt


def test_rewrite_local_relinks_aes_key_but_keeps_iv():
    txt = rewrite_local(parse_playlist(MEDIA_AES, BASE))
    assert '#EXT-X-KEY:METHOD=AES-128,URI="enc.key",IV=0x1234' in txt


def test_rewrite_local_keeps_ext_per_segment():
    """分片扩展名要按原样保留 (.ts 与 .m4s 不能混)."""
    pl = parse_playlist("\n".join(["#EXTM3U", "a.ts?t=1", "b.m4s?t=1"]), BASE)
    assert [n for n, _ in segment_jobs(pl)] == ["seg_00000.ts", "seg_00001.m4s"]


# ---- progress_dict ----
def test_progress_dict_shape_matches_ytdlp_contract():
    """GUI (_on_progress) 只认这些 key, 不能自创字段."""
    d = progress_dict(done_segs=10, total_segs=90, bytes_got=50_000_000, elapsed=5.0)
    assert d["status"] == "downloading"
    assert set(d) == {"status", "downloaded_bytes", "total_bytes_estimate", "speed", "eta"}
    assert d["downloaded_bytes"] == 50_000_000
    assert d["speed"] == pytest.approx(10_000_000, rel=0.01)


def test_progress_dict_estimates_total_from_segment_ratio():
    """分片大小未知 → 用完成比例外推总量 (10/90 下了 50MB ⇒ 总量约 450MB)."""
    d = progress_dict(done_segs=10, total_segs=90, bytes_got=50_000_000, elapsed=5.0)
    assert d["total_bytes_estimate"] == 450_000_000


def test_progress_dict_eta_counts_remaining_segments():
    d = progress_dict(done_segs=10, total_segs=90, bytes_got=50_000_000, elapsed=5.0)
    assert d["eta"] > 0


def test_progress_dict_never_divides_by_zero():
    d = progress_dict(done_segs=0, total_segs=0, bytes_got=0, elapsed=0.0)
    assert d["status"] == "downloading"
    assert d["total_bytes_estimate"] == 0
    assert d["speed"] == 0
    assert d["eta"] == 0


def test_progress_dict_caps_estimate_when_all_segments_done():
    d = progress_dict(done_segs=90, total_segs=90, bytes_got=450_000_000, elapsed=10.0)
    assert d["total_bytes_estimate"] == 450_000_000
    assert d["eta"] == 0


# ---- Playlist dataclass 契约 ----
def test_playlist_is_frozen():
    pl = Playlist(False, None, ["#EXTM3U"], ["a.ts"], None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pl.segs = []
