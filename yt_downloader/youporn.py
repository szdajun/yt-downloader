"""YouPorn 取流 — 走页面 mediaDefinitions 的 HLS (优先) + MP4 (兜底),
绕开 yt-dlp extractor 的 stale filter.

## 为什么不用 yt-dlp 的 YouPornIE

yt-dlp extractor (vendor: .venv/.../yt_dlp/extractor/youporn.py) 的 HLS 提取
条件是 `not isinstance(v['defaultQuality'], bool)`, 期望 defaultQuality 是数字
(代表 master m3u8 的 quality tag). 但 2026-10 起的 YouPorn 页面里
`mediaDefinitions` 数组每条 HLS 记录的 defaultQuality 都是布尔 (true/false 表
"是否默认档"), 这条 filter 把所有 HLS master 全滤掉, 只剩 format=mp4 那条
直插的 dict (而那条 dict 没有 vcodec 字段, yt-dlp 内部格式选择时全部视作
"无视频流", 走到 `raise_no_formats` → `No video formats found`).

升级 yt-dlp 无效 (issue tracker 至今没改这条 filter, 站点先变了).

## 实际可用的通路

页面 HTML 里有 `playervars.mediaDefinitions: [{format, videoUrl, ...}, ...]`,
分两种:

  - `format: "hls"`  → videoUrl 是个 JSON 端点
    (`https://www.youporn.com/media/hls/?s=base64-token`),
    拿到的 JSON 数组每条对应一个 master m3u8 (240/480/720/1080),
    4 档 total. master.m3u8 里有 1 个 variant (`index-v1-a1.m3u8`),
    variant 里有 N 个 TS 分片. **干净流: 无 AES-128 key, 无 fMP4 init**,
    比 Pornhub 简单.

  - `format: "mp4"` → videoUrl 同样是个 JSON 端点
    (`https://www.youporn.com/media/mp4/?s=base64-token`),
    拿到的 JSON 数组每条对应一个 direct mp4 (240/480/720/1080),
    URL 带 `validfrom/validto/rate/burst/hash` 时效 + 限速参数.

**主路走 HLS**, 因为 1080p master + 多档可选 + ffmpeg 流拷贝无重编码.
**MP4 兜底**: HLS 8 轮全失败时试 1 轮, 拿单文件直下.

## 三个坑 (2026-10-13 实测, 顺序即踩坑顺序)

  1. **yt-dlp extractor 已 stale** (见上) —— 别再尝试升级 yt-dlp 或加 cookie.
  2. **curl_cffi + YouPorn CDN TLS handshake 偶发抖动** —— 1/8 ~ 2/8 概率
    出现 `SSLError: invalid library (0)`, 本页 + CDN 都可能. 生产代码需要
    retry loop: 页面取 12 轮、segment 取 30 轮, 都 catch Exception 然后退避.
  3. **CDN 认抓页面那次的 session cookie** —— 与 Pornhub 同坑, 分片请求
    必须带抓页面那次的 cookie, 全新 session 裸取 → `410 Gone`. `video.session`
    跟着直链走, 见 `download_hls`.

## 代理方向

YouPorn 与 Pornhub 同向, 走 `HTTP(S)_PROXY` (本机指向境外节点), 与抖音的
强制直连相反 —— 分流在 `_make_opts(direct=...)` 之外, 这里不设 `proxy=""`.

## 命名

产物只用 numeric id 命名 (`{vid}.mp4` / `.m4a`). 敏感源, 标题一律不进
文件名/命令行/日志 (见 content-filter-1301 约定).

## 与 pornhub.py 的关系

HLS 基础设施 (parse_playlist / segment_jobs / rewrite_local / progress_dict
/ _fetch_media_playlist / _proxies / _new_session / _ffmpeg) 全部 verbatim
复制, 不从 pornhub import. 理由: 避免跨域依赖 (youporn→pornhub 反直觉);
两站结构后续变化时互不影响. 重复约 150 行可接受, 模块自洽.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# 域白名单: 等于或 . 前缀匹配, 避免 notyouporn.com 这类误命中.
# 域内子域 (www./cn./de./...) 都走这条.
YOUPORN_DOMAINS = ("youporn.com",)

# CDN 按并发限流 (沿用 pornhub 经验: 4 并发 + 410/429/403 退避)
_CONCURRENCY = 4
_SEG_TRIES = 30

_FFMPEG_DIR = r"C:\Users\18091\ffmpeg"
_REFERER = {"Referer": "https://www.youporn.com/"}
_DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

# /watch/{vid}/... 抠 id —— 不要求尾斜杠
_WATCH_ID_RE = re.compile(r"/watch/(\d+)")
# 嵌入页 /embed/{vid}/
_EMBED_ID_RE = re.compile(r"/embed/(\d+)")
# URL 之外的纯数字
_BARE_ID_RE = re.compile(r"^\d+$")
# 改写 EXT-X-MAP/EXT-X-KEY 的 URI 字段 (沿用 pornhub 的小工具)
_URI_ATTR_RE = re.compile(r'URI="[^"]+"')


class YoupornUnavailable(RuntimeError):
    """取流环境/网络不可用 (代理不通 / 页面始终取不到 / HLS+MP4 都失败).
    与「页面开了但 HLS/MP4 解析失败」区分不开时都归这里."""


# ---------------- 纯函数层 (可测, 不碰网络) ----------------

@dataclass(frozen=True)
class HlsGear:
    """一个 HLS 档位. quality 是站方给的档位标签 (240/480/720/1080).
    抖音源里 height 可能 None, 这里同理取不到就给 0."""
    quality: int
    width: int
    height: int
    url: str

    @property
    def short_side(self) -> int:
        return min(self.width, self.height) if self.width and self.height else 0


@dataclass(frozen=True)
class HlsPlan:
    """HLS 通路方案. master 是「已下钻到 variant」后的 playlist URL,
    可直接 fetch 分片. variant_short_side 是挑中的档位, 用来打日志."""
    master: str
    variant_short_side: int


@dataclass(frozen=True)
class Mp4Plan:
    """MP4 兜底方案. url 是 direct .mp4 直链 (带 validfrom/validto/rate/hash
    时效参数), short_side 是挑中的档位 (从 URL path 抠 1080/720/480/240)."""
    url: str
    short_side: int


@dataclass
class YoupornVideo:
    """一次取流的结果: 页面 session + 选定的取流方案 + 元信息.

    session 必须随直链一起传给 download_youporn_* —— CDN 认它的 cookie (坑 3).
    plan 判别联合: HlsPlan → 走 download_hls, Mp4Plan → 走 download_mp4_direct."""

    vid: str
    session: object            # curl_cffi.Session
    plan: HlsPlan | Mp4Plan
    duration: int
    quality: int               # 挑中的档位 short_side


@dataclass(frozen=True)
class Playlist:
    """解析后的 m3u8 (与 pornhub 形状一致, 不复用是为了解耦).

    is_master=True 时只填 variant; 否则 segs 是分片 URI (保持原文, 可能是相对
    路径), key_uri / map_uri 是 AES-128 密钥与 fMP4 init 段的**绝对**地址
    (YouPorn 是干净 TS, 通常都为 None).

    base 是解析这份 playlist 时用的地址 —— segs 保持原文没做 urljoin, 拼绝对
    地址要用它 (见 segment_jobs)."""
    is_master: bool
    variant: str | None
    lines: list[str]
    segs: list[str]
    key_uri: str | None
    map_uri: str | None
    base: str = ""


def is_youporn_url(url: str) -> bool:
    """是否 YouPorn 链接 (含子域 / 嵌入页 / 直接 id)."""
    if not url:
        return False
    try:
        host = (urlparse(url.strip()).netloc or "").lower()
    except Exception:
        return False
    host = host.split(":")[0]
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in YOUPORN_DOMAINS)


def video_id(url_or_id: str) -> str | None:
    """抠 numeric id: 支持 /watch/{id}/... / /embed/{id} / 直接给 id. 抠不到返回 None."""
    s = (url_or_id or "").strip()
    if not s:
        return None
    for rx in (_WATCH_ID_RE, _EMBED_ID_RE):
        m = rx.search(s)
        if m:
            return m.group(1)
    return s if _BARE_ID_RE.match(s) else None


def parse_media_definitions(html: str) -> list[dict]:
    """页面 HTML → mediaDefinitions 数组 (list[dict]). 维护页/结构变了 → [].

    用「找 `mediaDefinitions` 后面紧跟的 `[`, 配对扫描到匹配的 `]`」法:
    比正则靠谱 (JSON 嵌套 + 跨行), 也不依赖额外 JSON 解析器外裹.
    """
    if not html:
        return []
    idx = html.find("mediaDefinitions")
    if idx < 0:
        return []
    bracket = html.find("[", idx)
    if bracket < 0:
        return []
    depth, i = 0, bracket
    while i < len(html):
        c = html[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0:
        return []                                 # 没匹配上, 放弃
    try:
        defs = json.loads(html[bracket:i + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    return defs if isinstance(defs, list) else []


def _int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def hls_gears(defs: list[dict]) -> list[HlsGear]:
    """mediaDefinitions → HLS 候选列表. 丢掉非 hls / 空 url.

    注: mediaDefinitions 里的 hls entry 是「JSON endpoint」(quality=None),
    不是「具体档位」. 真档位在 step2 JSON 里 (240/480/720/1080) — 选档逻辑
    在 _resolve_hls_master 里, 本函数只负责把 endpoint 列表送出去.
    quality 字段若有 (罕见) 沿用, 否则给 0 不作为排序依据.
    """
    if not isinstance(defs, list):
        return []
    gears: list[HlsGear] = []
    for d in defs:
        if not isinstance(d, dict) or d.get("format") != "hls":
            continue
        url = d.get("videoUrl")
        if not isinstance(url, str) or not url:
            continue
        gears.append(HlsGear(_int(d.get("quality")),
                             _int(d.get("width")), _int(d.get("height")), url))
    return gears


def mp4_variants(defs: list[dict]) -> list[dict]:
    """mediaDefinitions → MP4 候选 (dict 列表, 后续 _resolve_mp4_url 处理).
    丢掉非 mp4 / 空 videoUrl 的."""
    if not isinstance(defs, list):
        return []
    out: list[dict] = []
    for d in defs:
        if not isinstance(d, dict) or d.get("format") != "mp4":
            continue
        url = d.get("videoUrl")
        if not isinstance(url, str) or not url:
            continue
        out.append(d)
    return out


def pick_best_hls_gear(gears: list[HlsGear]) -> HlsGear | None:
    """最高档 (short_side 最大, 退化用 quality). 空列表返回 None."""
    if not gears:
        return None
    return max(gears, key=lambda g: (g.short_side, g.quality))


def parse_playlist(text: str, base: str) -> Playlist:
    """解析 m3u8. 非 #EXTM3U 开头一律当垃圾 (CDN 会回 'request incorrect' 纯文本)."""
    if not text or not text.lstrip().startswith("#EXTM3U"):
        return Playlist(False, None, [], [], None, None, base)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    variant = None
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            variant = urljoin(base, lines[i + 1])
            break
    if variant is not None:
        return Playlist(True, variant, lines, [], None, None, base)

    segs = [ln for ln in lines if not ln.startswith("#")]

    def uri_attr(prefix: str) -> str | None:
        for ln in lines:
            if ln.startswith(prefix):
                m = re.search(r'URI="([^"]+)"', ln)
                if m:
                    return urljoin(base, m.group(1))
        return None

    return Playlist(False, None, lines, segs,
                    uri_attr("#EXT-X-KEY"), uri_attr("#EXT-X-MAP"), base)


def _local_seg_name(index: int, url: str) -> str:
    """分片落盘的本地名. 扩展名按原样保留 (.ts 与 .m4s 不能混).
    只用 path 段, 丢 query (Windows 文件名不支持 ?)."""
    return f"seg_{index:05d}{os.path.splitext(urlparse(url).path)[1] or '.ts'}"


_INIT_NAME = "init.mp4"
_KEY_NAME = "enc.key"


def segment_jobs(pl: Playlist) -> list[tuple[str, str]]:
    """[(本地文件名, 绝对 URL)] — init/key 在前, 分片按序. 与 rewrite_local 同名同序."""
    jobs: list[tuple[str, str]] = []
    if pl.map_uri:
        jobs.append((_INIT_NAME, pl.map_uri))
    if pl.key_uri:
        jobs.append((_KEY_NAME, pl.key_uri))
    jobs += [(_local_seg_name(i, u), urljoin(pl.base, u))
             for i, u in enumerate(pl.segs)]
    return jobs


def rewrite_local(pl: Playlist) -> str:
    """重写成相对路径的本地 playlist — ffmpeg 只读本地文件, 不吃 CDN 那套校验.

    分片换成 seg_NNNNN.ext, EXT-X-MAP 指向 init.mp4, EXT-X-KEY 的 URI 指向
    enc.key (IV 等其余属性原样保留, 解密仍然正确)."""
    out: list[str] = []
    seg_i = 0
    for ln in pl.lines:
        if ln.startswith("#EXT-X-MAP"):
            out.append(_URI_ATTR_RE.sub(f'URI="{_INIT_NAME}"', ln) if pl.map_uri else ln)
            continue
        if ln.startswith("#EXT-X-KEY"):
            out.append(_URI_ATTR_RE.sub(f'URI="{_KEY_NAME}"', ln) if pl.key_uri else ln)
            continue
        if ln.startswith("#"):
            out.append(ln)
            continue
        out.append(_local_seg_name(seg_i, ln))
        seg_i += 1
    return "\n".join(out) + "\n"


def progress_dict(done_segs: int, total_segs: int, bytes_got: int,
                  elapsed: float) -> dict:
    """分片进度 → yt-dlp 风格进度字典 (GUI `_on_progress` 直接吃, 不自创字段).

    分片大小事前未知, 总量按「已完成比例」外推 —— 与 yt-dlp 的
    total_bytes_estimate 同义, 所以复用这个 key 而不是新增."""
    speed = bytes_got / elapsed if elapsed > 0 else 0.0
    if done_segs > 0 and total_segs > 0:
        est = int(bytes_got * total_segs / done_segs)
    else:
        est = bytes_got
    est = max(est, bytes_got)                      # 外推值不能小于已下
    if done_segs >= total_segs > 0:
        est = bytes_got                            # 下完就收敛成实际值
    remaining = max(est - bytes_got, 0)
    eta = int(remaining / speed) if speed > 0 else 0
    return {
        "status": "downloading",
        "downloaded_bytes": bytes_got,
        "total_bytes_estimate": est,
        "speed": speed,
        "eta": eta,
    }


# ---------------- 有副作用层 (网络 / 进程) ----------------

def _ffmpeg() -> str:
    p = os.path.join(_FFMPEG_DIR, "ffmpeg.exe")
    return p if os.path.exists(p) else "ffmpeg"


def _proxies() -> dict | None:
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    return {"http": p, "https": p} if p else None


def _new_session(impersonate: str = "chrome"):
    from curl_cffi import requests as cr  # 延迟导入: 纯函数层不依赖 curl_cffi
    return cr.Session(impersonate=impersonate)


def _page_url(vid: str) -> str:
    return f"https://www.youporn.com/watch/{vid}/"


def _open_page(vid: str, proxies, on_status=None) -> tuple[object, str]:
    """取视频页 HTML. 反爬/TLS 抖动都会失败 —— 换新会话重试绕开.

    返回 (session, html_text); 全部尝试失败抛 YoupornUnavailable.
    与 pornhub 同样的「换 session 重试」策略, 区别是 YouPorn TLS 抖动更明显
    (curl_cffi + YouPorn CDN 不如 Pornhub 稳), 12 轮留足 margin.
    """
    last = ""
    for i in range(12):
        try:
            s = _new_session()
            s.headers.update({"User-Agent": _DESKTOP_UA,
                              "Referer": "https://www.youporn.com/",
                              "Accept": "text/html,application/xhtml+xml,*/*"})
            r = s.get(_page_url(vid), proxies=proxies, timeout=45)
            if r.status_code == 200 and len(r.text) > 5000:
                return s, r.text
            last = f"status={r.status_code} len={len(r.text)}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:80]}"
        if on_status:
            on_status(i + 1, last)
        time.sleep(min(2 + i, 8))
    raise YoupornUnavailable(
        f"页面取不到 ({last}) — 检查代理是否可用 (HTTP(S)_PROXY)")


def _resolve_hls_master(s, gear: HlsGear, proxies) -> HlsPlan | None:
    """GET gear.url (JSON endpoint) → 选 highest → GET master.m3u8 → 拿 variant.

    任一步失败返回 None (调用方继续试下一档 / 下一轮).
    """
    try:
        r = s.get(gear.url, proxies=proxies, timeout=30, headers=_REFERER)
        if r.status_code != 200 or not r.text.lstrip().startswith("["):
            return None
        meta = r.json()  # list[{format, height, videoUrl, ...}]
    except Exception:
        return None
    candidates = [m for m in meta
                  if isinstance(m, dict) and m.get("format") == "hls"
                  and isinstance(m.get("videoUrl"), str) and m["videoUrl"]]
    if not candidates:
        return None
    # 选 highest short_side (HLS JSON 里 height 字段可能为 None, 退化 quality)
    best = max(candidates,
               key=lambda m: (int(m.get("height") or 0), int(m.get("quality") or 0)))
    master_url = best["videoUrl"].replace("\\/", "/")
    try:
        rm = s.get(master_url, proxies=proxies, timeout=30, headers=_REFERER)
        if rm.status_code != 200 or not rm.text.lstrip().startswith("#EXTM3U"):
            return None
    except Exception:
        return None
    pl = parse_playlist(rm.text, master_url)
    # master 一定有 variant; 兜底用 master_url (单一档罕见但 master 也可直接当 media)
    variant = pl.variant or master_url
    short_side = int(best.get("height") or 0) or gear.short_side or gear.quality
    return HlsPlan(master=variant, variant_short_side=short_side)


def _resolve_mp4_url(s, defs: list[dict], proxies) -> Mp4Plan | None:
    """HLS 兜底: 从 mediaDefinitions 选 highest format=mp4, 拿直链.

    同一 page session 拿 JSON (与 HLS 共用页面 cookie, 坑 3)."""
    candidates = mp4_variants(defs)
    if not candidates:
        return None
    best = max(candidates,
               key=lambda d: (int(d.get("quality") or 0)))
    try:
        r = s.get(best["videoUrl"], proxies=proxies, timeout=30, headers=_REFERER)
        if r.status_code != 200 or not r.text.lstrip().startswith("["):
            return None
        meta = r.json()
    except Exception:
        return None
    mp4s = [m for m in meta
            if isinstance(m, dict) and m.get("format") == "mp4"
            and isinstance(m.get("videoUrl"), str) and m["videoUrl"]]
    if not mp4s:
        return None
    # 选 highest quality; 退化顺序: quality > height
    def key(m):
        return (int(m.get("quality") or 0), int(m.get("height") or 0))
    top = max(mp4s, key=key)
    url = top["videoUrl"].replace("\\/", "/")
    # 兜底 short_side: 从 URL path 抠 "1080P_4000K_xxx" 这种标签
    short_side = int(top.get("quality") or 0)
    if not short_side:
        m = re.search(r"(\d{3,4})[pP]_\d+[kK]_\d+", url)
        short_side = int(m.group(1)) if m else 0
    return Mp4Plan(url=url, short_side=short_side)


def extract_youporn(url_or_id: str, *, on_status=None) -> YoupornVideo:
    """主路 HLS 优先 8 轮, 全失败再 1 轮 MP4 兜底.

    on_status(round_no, detail) 每轮回调, 供 UI 显示「解析中」而非像卡死.
    """
    vid = video_id(url_or_id)
    if not vid:
        raise YoupornUnavailable(f"从 {url_or_id!r} 抠不出 numeric id")
    proxies = _proxies()

    # 8 轮 HLS: 每轮都重新抓 page, 用最新 session 试所有档位
    for round_ in range(8):
        try:
            sess, html = _open_page(vid, proxies, on_status)
        except YoupornUnavailable:
            if on_status:
                on_status(round_ + 1, "page-failed")
            time.sleep(1.5)
            continue
        defs = parse_media_definitions(html)
        gears = hls_gears(defs)
        dur = 0  # YouPorn JSON 里没 duration 顶层字段, 由 verify() 重读
        for gear in sorted(gears, key=lambda g: -(g.short_side or g.quality)):
            plan = _resolve_hls_master(sess, gear, proxies)
            if plan is not None:
                return YoupornVideo(vid, sess, plan, dur, plan.variant_short_side)
        if on_status:
            on_status(round_ + 1, "no-valid-master")
        time.sleep(1.5)

    # 1 轮 MP4 兜底: 重抓 page, 拿 format=mp4
    try:
        sess, html = _open_page(vid, proxies, on_status)
    except YoupornUnavailable as e:
        raise YoupornUnavailable(f"HLS 8 轮全失败, MP4 兜底也无法取页: {e}") from e
    defs = parse_media_definitions(html)
    plan = _resolve_mp4_url(sess, defs, proxies)
    if plan is None:
        raise YoupornUnavailable("HLS 8 轮 + MP4 兜底都拿不到可用直链")
    return YoupornVideo(vid, sess, plan, 0, plan.short_side)


def _fetch_media_playlist(s, video: YoupornVideo, proxies) -> Playlist:
    """对 HlsPlan: 直接 GET 已下钻的 variant (plan.master 就是 variant URL).
    沿用 pornhub 同名函数签名, 内部按 plan 类型分发."""
    if not isinstance(video.plan, HlsPlan):
        raise YoupornUnavailable("内部错误: 非 HLS plan 调到了 _fetch_media_playlist")
    r = s.get(video.plan.master, proxies=proxies, timeout=45, headers=_REFERER)
    pl = parse_playlist(r.text, video.plan.master)
    if not pl.is_master:
        return pl
    # master 还有 variant? 二次下钻
    r2 = s.get(pl.variant, proxies=proxies, timeout=45, headers=_REFERER)
    return parse_playlist(r2.text, pl.variant)


def download_hls(video: YoupornVideo, dest: str, *, audio_only: bool = False,
                 on_progress=None, workdir: str | None = None) -> str:
    """抓分片到本地 → 本地 playlist → ffmpeg 拼接为 dest. 返回 dest.

    audio_only=True 时从同一份本地 playlist 直接抽音频成 m4a (不走中间 mp4).
    进度经 on_progress 发 yt-dlp 风格字典 (见 progress_dict), 收尾发 finished.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    hook = on_progress or (lambda _d: None)
    proxies = _proxies()
    pl = _fetch_media_playlist(video.session, video, proxies)
    if not pl.segs:
        raise YoupornUnavailable("media playlist 里没有分片 (CDN 可能回了错误页)")

    own_workdir = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix=f"youporn_{video.vid}_")
    os.makedirs(workdir, exist_ok=True)
    try:
        jobs = segment_jobs(pl)
        # 每线程复用一个 session (复用连接, 少一次 TLS 握手 = 少一次抖动)
        cookies = dict(video.session.cookies)
        tl = threading.local()

        def sess():
            s = getattr(tl, "s", None)
            if s is None:
                s = _new_session()
                for k, v in cookies.items():
                    try:
                        s.cookies.set(k, v)
                    except Exception:
                        pass
                tl.s = s
            return s

        def fetch(job: tuple[str, str]) -> int:
            name, url = job
            path = os.path.join(workdir, name)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return os.path.getsize(path)          # 断点续跑
            last = ""
            for attempt in range(_SEG_TRIES):
                try:
                    r = sess().get(url, proxies=proxies, timeout=90, headers=_REFERER)
                    if r.status_code == 200 and r.content:
                        with open(path, "wb") as f:
                            f.write(r.content)
                        return len(r.content)
                    last = f"HTTP {r.status_code}"
                    if r.status_code in (410, 429, 403):   # 坑 3: 并发限流, 退避让位
                        time.sleep(3 + attempt * 0.5)
                        continue
                except Exception as e:
                    last = type(e).__name__
                time.sleep(min(1 + attempt, 6))
            raise YoupornUnavailable(f"{name} 重试 {_SEG_TRIES} 次仍失败 ({last})")

        total = len(jobs)
        done, got = 0, 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=_CONCURRENCY) as ex:
            futs = {ex.submit(fetch, j): j[0] for j in jobs}
            for fu in as_completed(futs):
                got += fu.result()
                done += 1
                hook(progress_dict(done, total, got, time.time() - t0))

        local_pl = os.path.join(workdir, "local.m3u8")
        with open(local_pl, "w", encoding="utf-8") as f:
            f.write(rewrite_local(pl))

        hook({"status": "finished"})
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "warning",
               "-i", local_pl, "-c", "copy"]
        if audio_only:
            cmd += ["-vn"]
        # YouPorn 是干净 TS, 分片是 .ts; 加 aac_adtstoasc (Pornhub 同款: fMP4 加了反而报错)
        if not all(n.endswith(".m4s") for n, _ in jobs if n.startswith("seg_")):
            cmd += ["-bsf:a", "aac_adtstoasc"]
        cmd += ["-movflags", "+faststart", "-y", dest]
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 1_000_000:
            tail = "\n".join((p.stderr or "").strip().splitlines()[-4:])
            raise YoupornUnavailable(f"ffmpeg 拼接失败 rc={p.returncode}\n{tail}")
        return dest
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def download_mp4_direct(video: YoupornVideo, dest: str, *, audio_only: bool = False,
                        on_progress=None) -> str:
    """MP4 兜底: 直链是单 .mp4 文件, stream 落盘. 无分片, 无并发.

    进度报告简单: started (0 bytes) → finished (实际大小). URL 带 validfrom/
    validto (~2h) + rate/burst 限速 + hash 签名, 必须用 page session cookie.
    audio_only=True 时抽音为 m4a (ffmpeg -vn -c copy, 无重编码).
    """
    if not isinstance(video.plan, Mp4Plan):
        raise YoupornUnavailable("内部错误: 非 MP4 plan 调到了 download_mp4_direct")
    proxies = _proxies()
    sess = video.session
    last = ""
    for attempt in range(_SEG_TRIES):
        try:
            hook = on_progress or (lambda _d: None)
            hook({"status": "downloading", "downloaded_bytes": 0,
                  "total_bytes_estimate": 0, "speed": 0, "eta": 0})
            # 流式写: 避免一次性吃 1GB 内存
            tmp = dest + ".part"
            r = sess.get(video.plan.url, proxies=proxies, timeout=600,
                         headers=_REFERER, stream=True)
            if r.status_code == 200:
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MiB
                        f.write(chunk)
                os.replace(tmp, dest)
            else:
                last = f"HTTP {r.status_code}"
                if r.status_code in (410, 429, 403):
                    time.sleep(3 + attempt * 0.5)
                    continue
                break
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(min(2 + attempt, 8))
            continue
        # 落盘成功, ffmpeg 抽音 (如有) + 准入门槛检查
        if not os.path.exists(dest) or os.path.getsize(dest) < 1_000_000:
            raise YoupornUnavailable(
                f"MP4 落盘失败: {dest} 不存在或 < 1MB ({last})")
        if audio_only:
            tmp = dest + ".m4a"
            cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "warning",
                   "-i", dest, "-vn", "-c", "copy", "-y", tmp]
            p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
            if p.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 100_000:
                tail = "\n".join((p.stderr or "").strip().splitlines()[-3:])
                raise YoupornUnavailable(f"ffmpeg 抽音失败 rc={p.returncode}\n{tail}")
            os.replace(tmp, dest)
        hook({"status": "finished"})
        return dest
    raise YoupornUnavailable(
        f"MP4 直链重试 {_SEG_TRIES} 次仍失败 ({last})")
