"""抖音浏览器取流 — 让真实浏览器跑抖音自己的签名 JS, 我们只拦响应.

## 为什么需要这个模块 (2026-09 起)

抖音给 `www.douyin.com/aweme/v1/web/aweme/detail/` 前置了 ArgusSecurityPlugin
风控. 实测两道关卡, 缺一不可:

  1. 缺 `Uifid` 请求头 → `403 Blocked by ArgusSecurityPlugin Uifid Not Found`
  2. 补上 Uifid 但缺 a_bogus 签名 → `403 ... Signature Not Found`

**与登录态无关**: 带上完整登录 cookie (含 sessionid / s_v_web_id / UIFID / ttwid,
共 51 个) 依然 403. 所以 yt-dlp 那句 "Fresh cookies (not necessarily logged in) are
needed" 是误导 —— 缺的是请求签名, 不是 cookie.

yt-dlp 的 DouyinIE (含 master 最新) 两样都没实现, 源码里只有一句
`# TODO: Run verification challenge code to generate signature cookies`,
故**升级 yt-dlp 无效**.

a_bogus 依赖 WebAssembly / Canvas / AudioContext / WebGL 设备指纹, 纯 Python 复刻
不现实; 且抖音约 2-4 个月换一次签名参数 (s4 字母表 / ua_code / 版本号), 逆向方案
会周期性失效. 因此改用真实浏览器: 签名逻辑永远跟随抖音官方实现, 本模块零维护.

## 为什么强制直连

抖音对非中国大陆 IP 地理封锁 (web detail API 与 douyinvod CDN 均是). 本机
`HTTP(S)_PROXY` 指向境外节点 (实测出口大阪 JP), 所以浏览器和 CDN 下载都必须绕开
代理: Chrome 用 `--no-proxy-server`, yt-dlp 用 `proxy=""`.

## 播放地址时效

`play_addr.url_list` 里的直链带过期 token (路径中含十六进制时间戳), **必须取到后
立即下载**, 不能缓存复用.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# 抖音域名(含 iesdouyin 分享域). 用「等于 或 . 前缀」判定, 避免 notdouyin.com 误命中.
DOUYIN_DOMAINS = ("douyin.com", "iesdouyin.com")

# 桌面 Chrome UA — 移动端 UA 会被导到验证码中间页.
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)

# 优先系统 Chrome, 回退 Edge — 两者 Windows 都自带, 免去下载 ~300MB Chromium.
_BROWSER_CHANNELS = ("chrome", "msedge")

# 拦截目标: 抖音前端拿到 detail JSON 的那个请求.
_DETAIL_URL_MARK = "aweme/detail"

_LAUNCH_ARGS = [
    "--no-proxy-server",                            # 强制直连, 绕开境外代理
    "--disable-blink-features=AutomationControlled",  # 去掉 webdriver 指纹
    "--mute-audio",
]


class DouyinBrowserUnavailable(RuntimeError):
    """浏览器取流不可用 (Playwright 没装 / 本机无 Chrome 与 Edge)."""


@dataclass(frozen=True)
class Gear:
    """一个码率档位. width/height 为像素, kbps 为千比特每秒."""

    gear_name: str
    width: int
    height: int
    kbps: int
    url: str

    @property
    def short_side(self) -> int:
        """短边像素 — 准入门槛看的就是这个 (竖屏 1080x1920 的短边是 1080)."""
        return min(self.width, self.height) if self.width and self.height else 0


@dataclass
class DouyinVideo:
    """一次取流的结果: 元信息 + 全部候选档位."""

    vid: str
    title: str
    duration: float          # 秒 (detail 原始字段是毫秒, 已换算)
    gears: list[Gear] = field(default_factory=list)


def is_douyin_url(url: str) -> bool:
    """是否抖音链接 (含 www / v 短链 / iesdouyin 分享域)."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse
        host = (urlparse(url.strip()).netloc or "").lower()
    except Exception:
        return False
    host = host.split(":")[0]          # 去端口
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in DOUYIN_DOMAINS)


def _int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _gear_from_play_addr(pa: object, gear_name: str, bit_rate: object) -> Gear | None:
    """把一条 play_addr 变成 Gear; 没有可用 url 则返回 None (下不了的档位直接丢)."""
    if not isinstance(pa, dict):
        return None
    url = next((u for u in (pa.get("url_list") or [])
                if isinstance(u, str) and u), None)
    if not url:
        return None
    return Gear(
        gear_name=str(gear_name or ""),
        width=_int(pa.get("width")),
        height=_int(pa.get("height")),
        kbps=_int(bit_rate) // 1000,
        url=url,
    )


def _parse_gears(video: dict) -> list[Gear]:
    """抽取候选档位. 优先 bit_rate 阶梯; 阶梯缺失时退回 video.play_addr 单档."""
    gears: list[Gear] = []
    for entry in (video.get("bit_rate") or []):
        if not isinstance(entry, dict):
            continue
        g = _gear_from_play_addr(entry.get("play_addr"),
                                 entry.get("gear_name") or "",
                                 entry.get("bit_rate"))
        if g:
            gears.append(g)
    if not gears:
        g = _gear_from_play_addr(video.get("play_addr"), "default", 0)
        if g:
            gears.append(g)
    return gears


def parse_douyin_detail(payload: object) -> DouyinVideo | None:
    """拦截到的 detail 响应 → DouyinVideo. 不可用时返回 None (绝不抛).

    风控页 / 空壳响应 (`video_layout: null`, `encrypt_data_miss` 等) 都会走到 None,
    由调用方给出可读报错. 这里不抛异常是因为拦截到的 body 不保证是合法 JSON.
    """
    if not isinstance(payload, dict):
        return None
    detail = payload.get("aweme_detail")
    if not isinstance(detail, dict):
        return None
    video = detail.get("video")
    if not isinstance(video, dict):
        return None
    gears = _parse_gears(video)
    if not gears:
        return None

    vid = str(detail.get("aweme_id") or "")
    desc = str(detail.get("desc") or "").strip()
    # desc 可能为空 — 用 id 兜底, 避免产出空标题文件名.
    title = desc or f"douyin_{vid or 'video'}"
    return DouyinVideo(vid=vid, title=title,
                       duration=float(_int(detail.get("duration"))) / 1000.0,
                       gears=gears)


def pick_best_gear(gears: list[Gear], format_label: str) -> Gear | None:
    """按 (短边, 码率) 取最佳档, 对齐 downloader 的 format_sort=["res", "tbr"].

    先分辨率后码率: 做源素材要的是细节, 高码率低分辨率不如低码率高分辨率. 仅音频
    预设同样取最佳视频档 —— 音频随后由 ffmpeg 从该档抽取.
    """
    if not gears:
        return None
    return max(gears, key=lambda g: (g.short_side, g.kbps))


def _loads(text: object) -> object:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _launch_browser(playwright):
    """起 headless 系统浏览器. Chrome 优先, 失败回退 Edge."""
    errors = []
    for channel in _BROWSER_CHANNELS:
        try:
            return playwright.chromium.launch(channel=channel, headless=True,
                                              args=_LAUNCH_ARGS)
        except Exception as e:
            errors.append(f"{channel}: {type(e).__name__}")
    raise DouyinBrowserUnavailable(
        "起不了浏览器 (试过 " + ", ".join(_BROWSER_CHANNELS) + "): "
        + "; ".join(errors)
        + " — 需要本机装有 Chrome 或 Edge")


def extract_douyin(url: str, *, timeout_ms: int = 60_000,
                   settle_ms: int = 9_000) -> DouyinVideo | None:
    """浏览器打开视频页, 拦截 detail 响应取直链.

    抖音自己的 JS 会算出 a_bogus 并带上请求, 我们只做被动拦截 —— 不逆向、不签名.
    页面加载后给 `settle_ms` 让前端把 detail 请求发出去.

    返回 None 表示页面开了但没拿到可用 detail (风控/视频不存在);
    `DouyinBrowserUnavailable` 表示环境缺依赖, 两者调用方要分开处理.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:      # 延迟导入: 没装 playwright 时给清晰提示而非崩在 import
        raise DouyinBrowserUnavailable(
            "没装 Playwright — 装法: uv pip install playwright (无需 playwright install, "
            "直接驱动系统 Chrome/Edge)") from e

    bodies: list[str] = []

    def _on_response(resp) -> None:
        try:
            if _DETAIL_URL_MARK in resp.url and resp.status == 200:
                bodies.append(resp.text())
        except Exception:
            pass      # 响应体读取失败/页面已关: 忽略, 下一帧可能还有

    with sync_playwright() as p:
        browser = _launch_browser(p)
        try:
            ctx = browser.new_context(locale="zh-CN", user_agent=_DESKTOP_UA,
                                      viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.on("response", _on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(settle_ms)
        finally:
            browser.close()

    for body in bodies:
        video = parse_douyin_detail(_loads(body))
        if video:
            return video
    return None


_VIDEO_ID_RE = re.compile(r"/video/(\d+)")


def video_id(url: str) -> str | None:
    """从 URL 抠视频 id (短链 / 分享页可能抠不到, 交给 detail 响应里的 aweme_id)."""
    m = _VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None
