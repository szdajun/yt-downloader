"""youporn.py — 取流的纯函数层测试.

只测不依赖网络/curl_cffi 的纯函数 (与 test_pornhub.py 同构):
- is_youporn_url / video_id     域名与 id 识别
- parse_media_definitions / hls_gears / mp4_variants   页面 → 候选档位
- pick_best_hls_gear            选档
- parse_playlist / segment_jobs / rewrite_local   m3u8 → 本地抓取计划与本地 playlist
- progress_dict                 分片进度 → yt-dlp 风格进度字典 (GUI 直接吃)
"""
from __future__ import annotations

import pytest

from yt_downloader.youporn import (
    HlsGear,
    HlsPlan,
    Mp4Plan,
    YoupornUnavailable,
    YoupornVideo,
    hls_gears,
    is_youporn_url,
    mp4_variants,
    parse_media_definitions,
    parse_playlist,
    pick_best_hls_gear,
    progress_dict,
    rewrite_local,
    segment_jobs,
    video_id,
)

# 现实数据参考 (.tmp_youporn_spike.py 实测)
REAL_MEDIA_DEFS = [
    {"format": "hls", "quality": "720", "videoUrl":
     "https://www.youporn.com/media/hls/?s=hls-token", "remote": True},
    {"format": "mp4", "quality": "1080", "videoUrl":
     "https://www.youporn.com/media/mp4/?s=mp4-token", "remote": True},
]

# HLS step2 返回的 4 master (spike 实测)
HLS_STEP2_BODY = json_dumps_hls = (
    '[{"defaultQuality":true,"format":"hls","height":404,"width":720,'
    '"videoUrl":"https://ev-h-ph.ypncdn.com/hls/v/720P/master.m3u8?validfrom=1",'
    '"quality":"720"},'
    '{"defaultQuality":false,"format":"hls","height":404,"width":720,'
    '"videoUrl":"https://ev-h-ph.ypncdn.com/hls/v/480P/master.m3u8?validfrom=1",'
    '"quality":"480"},'
    '{"defaultQuality":false,"format":"hls","height":404,"width":720,'
    '"videoUrl":"https://ev-h-ph.ypncdn.com/hls/v/240P/master.m3u8?validfrom=1",'
    '"quality":"240"},'
    '{"defaultQuality":false,"format":"hls","height":720,"width":1280,'
    '"videoUrl":"https://ev-h-ph.ypncdn.com/hls/v/1080P/master.m3u8?validfrom=1",'
    '"quality":"1080"}]'
)


# ---- is_youporn_url ----
@pytest.mark.parametrize("url", [
    "https://www.youporn.com/watch/103059821/",
    "https://www.youporn.com/watch/103059821",
    "https://youporn.com/watch/12345/some-slug/",
    "https://www.youporn.com/embed/103059821/",
])
def test_is_youporn_url_true(url):
    assert is_youporn_url(url) is True


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.douyin.com/video/123",
    "https://www.pornhub.com/view_video.php?viewkey=abc",
    "https://example.com/youporn.com/watch/123",  # 非同域, 只是路径里出现
    "",
])
def test_is_youporn_url_false(url):
    assert is_youporn_url(url) is False


def test_is_youporn_url_not_fooled_by_lookalike():
    """notyouporn.com 不是 youporn 域 (避免 endswith 误判)."""
    assert is_youporn_url("https://notyouporn.com/watch/123") is False


# ---- video_id ----
def test_video_id_from_watch_url():
    assert video_id("https://www.youporn.com/watch/103059821/") == "103059821"


def test_video_id_handles_no_trailing_slash():
    """URL 没尾斜杠也应匹配 (正则不强制)."""
    assert video_id("https://www.youporn.com/watch/12345") == "12345"


def test_video_id_from_watch_with_slug():
    """URL 末尾带 slug 也不影响 (/watch/{id}/{slug}/)."""
    assert video_id("https://www.youporn.com/watch/103059821/some-title/") == "103059821"


def test_video_id_from_embed_url():
    assert video_id("https://www.youporn.com/embed/103059821/") == "103059821"


def test_video_id_from_bare_id():
    assert video_id("103059821") == "103059821"


@pytest.mark.parametrize("bad", [
    "", "   ", "https://www.youporn.com/",
    "https://www.youporn.com/watch/", "https://example.com/x",
    "not-a-number",
])
def test_video_id_none_when_unparseable(bad):
    assert video_id(bad) is None


# ---- parse_media_definitions ----
def test_parse_media_defs_extracts_list():
    """HTML 嵌 JSON, 配对扫描要能正确抠出 mediaDefinitions 数组."""
    html = ('... var playervars = {"mediaDefinitions":'
            + __import__("json").dumps(REAL_MEDIA_DEFS)
            + ', "duration": 660}; ...')
    defs = parse_media_definitions(html)
    assert len(defs) == 2
    assert defs[0]["format"] == "hls"
    assert defs[1]["format"] == "mp4"


def test_parse_media_defs_none_when_absent():
    """维护页 / 改版可能没 mediaDefinitions."""
    assert parse_media_definitions("<html>... no media defs ...</html>") == []
    assert parse_media_definitions("") == []


def test_parse_media_defs_survives_truncated_json():
    """JSON 截断 / 未配对闭合 → [] (不抛)."""
    html = '... "mediaDefinitions": [{"format":"hls", ... no closing ...'
    assert parse_media_definitions(html) == []


def test_parse_media_defs_survives_garbage():
    """非 JSON 也不抛."""
    html = '... "mediaDefinitions": [this is not json] ...'
    assert parse_media_definitions(html) == []


# ---- hls_gears ----
def test_hls_gears_keeps_hls_with_url():
    defs = REAL_MEDIA_DEFS
    gears = hls_gears(defs)
    assert len(gears) == 1
    assert gears[0].quality == 720
    assert gears[0].url == "https://www.youporn.com/media/hls/?s=hls-token"


def test_hls_gears_drops_mp4_format():
    """format=mp4 那条不进 HLS 档列表."""
    defs = [
        {"format": "hls", "quality": "720", "videoUrl": "h"},
        {"format": "mp4", "quality": "1080", "videoUrl": "m"},
    ]
    assert len(hls_gears(defs)) == 1


def test_hls_gears_drops_empty_url():
    defs = [
        {"format": "hls", "videoUrl": ""},                       # 空 url
        {"format": "hls", "videoUrl": "x"},
    ]
    gears = hls_gears(defs)
    assert [g.url for g in gears] == ["x"]


def test_hls_gears_accepts_endpoint_without_quality():
    """mediaDefinitions 里的 hls entry 是 JSON endpoint, quality=None 是合法的
    (档位 quality 在 step2 JSON 里)."""
    defs = [
        {"format": "hls", "videoUrl": "https://www.youporn.com/media/hls/?s=...",
         "remote": True, "segmentFormats": {"video": "fmp4", "audio": "aac"}},
    ]
    gears = hls_gears(defs)
    assert len(gears) == 1
    assert gears[0].quality == 0          # 缺省, 不作为排序依据
    assert gears[0].url.startswith("https://www.youporn.com/media/hls/")


def test_hls_gears_survives_garbage():
    assert hls_gears("not a list") == []
    assert hls_gears([{"format": "hls"}]) == []                # 无 url


# ---- mp4_variants ----
def test_mp4_variants_returns_mp4_entries():
    defs = REAL_MEDIA_DEFS
    out = mp4_variants(defs)
    assert len(out) == 1
    assert out[0]["quality"] == "1080"


def test_mp4_variants_drops_hls_format():
    defs = [
        {"format": "hls", "quality": "720", "videoUrl": "h"},
        {"format": "mp4", "quality": "1080", "videoUrl": "m"},
    ]
    out = mp4_variants(defs)
    assert len(out) == 1 and out[0]["format"] == "mp4"


def test_mp4_variants_survives_garbage():
    assert mp4_variants("not a list") == []
    assert mp4_variants([{"format": "hls", "videoUrl": "h"}]) == []


# ---- pick_best_hls_gear ----
def test_pick_best_hls_gear_prefers_highest_short_side():
    gears = [
        HlsGear(240, 320, 240, "u240"),
        HlsGear(1080, 1920, 1080, "u1080"),
        HlsGear(720, 1280, 720, "u720"),
        HlsGear(480, 854, 480, "u480"),
    ]
    assert pick_best_hls_gear(gears).url == "u1080"


def test_pick_best_hls_gear_falls_back_to_quality():
    """height/width 都缺时退化用 quality 比较."""
    gears = [
        HlsGear(240, 0, 0, "u240"),
        HlsGear(1080, 0, 0, "u1080"),
    ]
    assert pick_best_hls_gear(gears).url == "u1080"


def test_pick_best_hls_gear_empty_returns_none():
    assert pick_best_hls_gear([]) is None


# ---- parse_playlist / segment_jobs / rewrite_local ----
def test_parse_playlist_media_no_aes_no_map():
    """YouPorn variant 是干净 TS: 无 #EXT-X-KEY, 无 #EXT-X-MAP, 仅 #EXTINF + seg URI."""
    # 截断到 3 个分片示意
    base = ("https://ev-h-ph.ypncdn.com/hls/v/720P_4000K_442136961.mp4/"
            "index-v1-a1.m3u8?validfrom=1")
    text = (
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:10.0,\nseg0.ts\n"
        "#EXTINF:10.0,\nseg1.ts\n#EXTINF:10.0,\nseg2.ts\n#EXT-X-ENDLIST\n"
    )
    pl = parse_playlist(text, base)
    assert pl.is_master is False
    assert pl.key_uri is None
    assert pl.map_uri is None
    assert len(pl.segs) == 3
    assert pl.segs[0] == "seg0.ts"


def test_parse_playlist_garbage_returns_empty():
    pl = parse_playlist("not m3u8", "https://x")
    assert pl.is_master is False
    assert pl.segs == []
    assert pl.variant is None


def test_parse_playlist_master_has_variant():
    base = "https://x/master.m3u8"
    text = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\n"
        "720p/index.m3u8\n"
    )
    pl = parse_playlist(text, base)
    assert pl.is_master is True
    assert pl.variant == "https://x/720p/index.m3u8"


def test_segment_jobs_no_init_no_key():
    """YouPorn 干净流: 不到 init / key, jobs 只有 seg_NNNNN.ts."""
    base = "https://x/v.m3u8?token=1"
    text = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXTINF:5.0,\nseg_a.ts?h=1\n#EXTINF:5.0,\nseg_b.ts?h=1\n"
        "#EXT-X-ENDLIST\n"
    )
    pl = parse_playlist(text, base)
    jobs = segment_jobs(pl)
    assert len(jobs) == 2
    # 扩展名按 path 段取, 丢 query
    assert jobs[0][0] == "seg_00000.ts"
    assert jobs[1][0] == "seg_00001.ts"
    assert jobs[0][1].startswith("https://x/seg_a.ts?")


def test_rewrite_local_no_init_no_key():
    base = "https://x/v.m3u8?token=1"
    text = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXTINF:5.0,\nseg_a.ts?h=1\n#EXTINF:5.0,\nseg_b.ts?h=1\n"
        "#EXT-X-ENDLIST\n"
    )
    pl = parse_playlist(text, base)
    out = rewrite_local(pl)
    assert "EXT-X-MAP" not in out
    assert "EXT-X-KEY" not in out
    assert "seg_00000.ts" in out
    assert "seg_00001.ts" in out
    assert "seg_a.ts" not in out                          # 原 URI 已被替换


# ---- progress_dict ----
def test_progress_dict_shape_matches_ytdlp_contract():
    d = progress_dict(1, 10, 5_000_000, 1.0)
    assert set(d.keys()) == {
        "status", "downloaded_bytes", "total_bytes_estimate", "speed", "eta"}
    assert d["status"] == "downloading"


def test_progress_dict_estimates_total_from_segment_ratio():
    """10/90 完成, 已下 50MB → 估算总 ≈ 450MB."""
    d = progress_dict(10, 90, 50_000_000, 1.0)
    assert d["total_bytes_estimate"] == 450_000_000


def test_progress_dict_eta_counts_remaining():
    d = progress_dict(5, 10, 5_000_000, 1.0)
    assert d["speed"] == 5_000_000
    # 5/10 done, 5MB got → est = 5M * 10 / 5 = 10M, remaining 5M, eta = 5M/5MBps = 1s
    assert d["total_bytes_estimate"] == 10_000_000
    assert d["eta"] == 1


def test_progress_dict_never_divides_by_zero():
    d = progress_dict(0, 10, 0, 0.0)
    assert d["speed"] == 0.0
    assert d["eta"] == 0
    assert d["total_bytes_estimate"] == 0


def test_progress_dict_caps_estimate_when_all_segments_done():
    d = progress_dict(10, 10, 95_000_000, 10.0)
    # 下完就收敛成实际值, 不会因为浮点误差 > bytes_got
    assert d["total_bytes_estimate"] == 95_000_000
    assert d["eta"] == 0


# ---- 类型 sanity (不联网, 测 dataclass 字段) ----
def test_youporn_video_dataclass_holds_plan():
    sess = object()
    v = YoupornVideo("103059821", sess, HlsPlan("https://x/m.m3u8", 1080), 660, 1080)
    assert v.vid == "103059821"
    assert v.session is sess
    assert isinstance(v.plan, HlsPlan)
    assert v.quality == 1080
    assert v.duration == 660


def test_youporn_video_supports_mp4_plan():
    sess = object()
    v = YoupornVideo("103059821", sess,
                     Mp4Plan("https://x/1080.mp4", 1080), 660, 1080)
    assert isinstance(v.plan, Mp4Plan)
    assert v.plan.url.endswith("1080.mp4")


# ---- exception ----
def test_youporn_unavailable_is_runtime_error():
    """异常类继承 RuntimeError, 让外层 except Exception 能捕到."""
    with pytest.raises(YoupornUnavailable):
        raise YoupornUnavailable("test")
    assert issubclass(YoupornUnavailable, RuntimeError)
