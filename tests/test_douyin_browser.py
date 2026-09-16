"""douyin_browser.py — 抖音浏览器取流的纯函数层测试.

只测不依赖 Playwright / 网络的纯函数:
- is_douyin_url(url)         域名识别
- parse_douyin_detail(payload)  拦截到的 detail JSON → DouyinVideo
- pick_best_gear(video, fmt)    按 (短边, 码率) 选档, 对齐 format_sort=["res","tbr"]
"""
from __future__ import annotations

import pytest

from yt_downloader.douyin_browser import (
    DouyinVideo,
    Gear,
    is_douyin_url,
    parse_douyin_detail,
    pick_best_gear,
)


# ---- is_douyin_url ----
@pytest.mark.parametrize("url", [
    "https://www.douyin.com/video/7685199522498698100",
    "https://douyin.com/video/123",
    "https://v.douyin.com/iAfjpuwt/",
    "https://www.iesdouyin.com/share/video/123/",
    "https://www.douyin.com/jingxuan?modal_id=7685199522498698100",
])
def test_is_douyin_url_true(url):
    assert is_douyin_url(url) is True


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://example.com/douyin.com/video/1",   # 非同域, 只是路径里出现
    "",
])
def test_is_douyin_url_false(url):
    assert is_douyin_url(url) is False


def test_is_douyin_url_not_fooled_by_lookalike_domain():
    """notdouyin.com 不是抖音域(避免 endswith 误判)."""
    assert is_douyin_url("https://notdouyin.com/video/1") is False


# ---- 测试夹具: 真实结构的 detail 响应 (已裁剪) ----
def _gear(name, kbps, w, h, host="v26-web.douyinvod.com"):
    return {
        "gear_name": name,
        "bit_rate": kbps * 1000,
        "play_addr": {"width": w, "height": h,
                      "url_list": [f"https://{host}/x/{name}.mp4"]},
    }


def _payload(bit_rates=None, desc="来个丝滑小串联#瑜伽流动", duration=82801,
             fallback=(1080, 1920)):
    return {
        "aweme_detail": {
            "aweme_id": "7685199522498698100",
            "desc": desc,
            "duration": duration,
            "video": {
                "play_addr": {"width": fallback[0], "height": fallback[1],
                              "url_list": ["https://v26-web.douyinvod.com/fb.mp4"]},
                "bit_rate": bit_rates if bit_rates is not None else [
                    _gear("normal_1080_0", 2898, 1080, 1920),
                    _gear("1080_1_1", 2175, 1080, 1920),
                    _gear("normal_720_0", 1785, 720, 1280),
                    _gear("normal_540_0", 1630, 576, 1024),
                ],
            },
        },
    }


# ---- parse_douyin_detail ----
def test_parse_extracts_id_title_duration():
    v = parse_douyin_detail(_payload())
    assert isinstance(v, DouyinVideo)
    assert v.vid == "7685199522498698100"
    assert v.title == "来个丝滑小串联#瑜伽流动"
    assert v.duration == pytest.approx(82.801)


def test_parse_duration_converted_from_ms():
    """detail 里 duration 是毫秒, 转成秒."""
    assert parse_douyin_detail(_payload(duration=82801)).duration == pytest.approx(82.801)


def test_parse_gears_carry_geometry_and_bitrate():
    v = parse_douyin_detail(_payload())
    assert len(v.gears) == 4
    top = max(v.gears, key=lambda g: (g.short_side, g.kbps))
    assert top.gear_name == "normal_1080_0"
    assert top.short_side == 1080
    assert top.kbps == 2898
    assert top.url.startswith("https://")


def test_parse_short_side_is_min_of_w_h():
    """竖屏 1080x1920 的短边是 1080 (不是 1920)."""
    v = parse_douyin_detail(_payload())
    g = next(g for g in v.gears if g.width == 1080 and g.height == 1920)
    assert g.short_side == 1080


def test_parse_falls_back_to_play_addr_when_no_bit_rate_ladder():
    """没有 bit_rate 阶梯时, 用 video.play_addr 兜底, 不能返回空. """
    v = parse_douyin_detail(_payload(bit_rates=[]))
    assert v is not None
    assert len(v.gears) == 1
    assert v.gears[0].url == "https://v26-web.douyinvod.com/fb.mp4"
    assert v.gears[0].short_side == 1080


def test_parse_skips_gears_without_url():
    """play_addr.url_list 为空的档位要跳过(下不了)."""
    brs = [_gear("a", 1000, 1080, 1920)]
    brs.append({"gear_name": "empty", "bit_rate": 9_000_000,
                "play_addr": {"width": 1080, "height": 1920, "url_list": []}})
    v = parse_douyin_detail(_payload(bit_rates=brs))
    assert len(v.gears) == 1
    assert v.gears[0].gear_name == "a"


@pytest.mark.parametrize("bad", [
    {},
    {"aweme_detail": None},
    {"aweme_detail": {}},                      # 风控页/空壳: 无 video
    {"status_code": 11110, "status_msg": "encrypt_data_miss"},
])
def test_parse_returns_none_on_unusable_payload(bad):
    """风控/空壳响应必须返回 None, 让调用方报错而不是崩."""
    assert parse_douyin_detail(bad) is None


def test_parse_never_raises_on_garbage():
    """任意垃圾输入都不抛(拦截到的可能是风控 JSON)."""
    for bad in ([], "x", 0, {"aweme_detail": {"video": "notadict"}}):
        assert parse_douyin_detail(bad) is None


def test_parse_falls_back_title_when_desc_empty():
    """desc 为空时用 id 兜底做标题(不能产生空标题文件名)."""
    v = parse_douyin_detail(_payload(desc=""))
    assert v.title
    assert v.vid in v.title


# ---- pick_best_gear ----
def test_pick_best_prefers_shorter_side_then_bitrate():
    """竖屏 1080x1920(短边1080) 优先于横屏 1920x1080(短边1080)同短边时看码率."""
    gears = [
        Gear("h", 1920, 1080, 2000, "u1"),
        Gear("v", 1080, 1920, 2898, "u2"),
        Gear("hi", 1080, 1920, 3500, "u3"),
    ]
    best = pick_best_gear(gears, "最高画质 (mp4)")
    assert best.url == "u3"          # 同短边取码率最高


def test_pick_best_ignores_high_bitrate_low_resolution():
    """码率高但短边低的不该被选中 (对齐 format_sort 先 res 后 tbr)."""
    gears = [
        Gear("low_res_high_br", 720, 1280, 9000, "u1"),
        Gear("high_res_low_br", 1080, 1920, 1000, "u2"),
    ]
    assert pick_best_gear(gears, "最高画质 (mp4)").url == "u2"


def test_pick_best_audio_label_still_returns_video_gear():
    """仅音频预设也取最佳视频档 (音频随后由 ffmpeg 抽取)."""
    gears = [Gear("a", 1080, 1920, 2898, "u1"), Gear("b", 720, 1280, 1000, "u2")]
    assert pick_best_gear(gears, "仅音频 (m4a)").url == "u1"


def test_pick_best_empty_returns_none():
    assert pick_best_gear([], "最高画质 (mp4)") is None


def test_pick_best_single_gear():
    assert pick_best_gear([Gear("only", 720, 1280, 500, "u")], "720p (mp4)").url == "u"
