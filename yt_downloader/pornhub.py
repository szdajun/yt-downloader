"""Pornhub 取流 — 走页面 flashvars 的 HLS, 绕开 yt-dlp extractor 的 PhantomJS 死路.

## 为什么不用 yt-dlp 的 PornHubIE

它请求 `platform=pc` 页面, 命中反爬后返回 `<body onload="go()">` +
`document.cookie=` 的 JS 挑战, extractor 的应对是调 **PhantomJS** 重放. PhantomJS
早已停止维护、本机也没有, 于是恒定:

    ERROR: [PornHub] <id>: PhantomJS not found

带 Firefox 完整登录 cookie 照旧触发 —— 不是登录态问题. **升级 yt-dlp 无效**.

## 实际可用的通路

页面 HTML 里 `var flashvars_<n> = {...};` 直接带 `mediaDefinitions`:
  - `format: "hls"` → 真实可下的 master.m3u8 (240/480/720/1080 档), **走这条**;
  - `format: "mp4"` + `remote: true` → 指向 `cn.pornhub.com/video/get_media`,
    该 API 被反爬挡死 (403 maintenance), 不要走.

## 四个坑 (2026-10-05 实测, 顺序即踩坑顺序)

  1. **CDN 只认取 flashvars 那个 session 的 cookie**: 同一 m3u8 用它请求 200,
     换个新 session 请求 410/412. 所以 cookie 必须跟着直链一起传下去.
  2. **页面偶尔下发不带 token 的直链** (validfrom=validto=0) → `412 request
     incorrect`. 故要遍历档位试 master, 不通就重新取页面换 token.
  3. **CDN 按并发限流**: 8 并发时随机 410 Gone (串行复测 3/3 全 200).
    4 并发 + 遇 410/429 退避重试即稳.
  4. **ffmpeg 的 HTTP 栈过不了该 CDN** (同一 URL curl_cffi 200 / ffmpeg 410),
     所以不用 ffmpeg 拉流. 分片由 curl_cffi 拉到本地, 重写成相对路径的本地
     playlist, 再让 ffmpeg 做**本地**拼接 —— 顺带天然支持 AES-128 与 fMP4.

反爬还会零星返回 403 维护页, 换新 session 重试即可绕开 (需重试循环, 单次不够).

## 代理方向与抖音相反

Pornhub 必须走代理 (本机直连不通), 与 douyin_browser 的强制直连相反 —— 这里
不设 `proxy=""`, 直接继承 `HTTP(S)_PROXY`.

## 命名

产物只用 viewkey 命名, 标题不进文件名/命令行/日志 (见 content-filter-1301 约定).
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

# 域名判定用「等于 或 . 前缀」, 避免 notpornhub.com 这类误命中.
PORNHUB_DOMAINS = ("pornhub.com", "pornhub.org", "pornhub.net", "pornhubpremium.com")

# CDN 按并发限流 (坑 3): 再高会随机 410 Gone.
_CONCURRENCY = 4
_SEG_TRIES = 30

_FFMPEG_DIR = r"C:\Users\18091\ffmpeg"
_REFERER = {"Referer": "https://www.pornhub.com/"}
_DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

_VIEWKEY_RE = re.compile(r"viewkey=([0-9a-zA-Z]+)")
_EMBED_RE = re.compile(r"/embed/([0-9a-zA-Z]+)")
_BARE_ID_RE = re.compile(r"^[0-9a-zA-Z]+$")
_FLASHVARS_RE = re.compile(r"var\s+flashvars_\d+\s*=\s*(\{.+?\});", re.S)
_URI_ATTR_RE = re.compile(r'URI="[^"]+"')


class PornhubUnavailable(RuntimeError):
    """取流环境/网络不可用 (代理不通 / 页面始终取不到). 与「页面开了但没数据」区分."""


# ---------------- 纯函数层 (可测, 不碰网络) ----------------

@dataclass(frozen=True)
class HlsGear:
    """一个 HLS 档位。quality 是站方给的码率档标签 (240/480/720/1080)."""

    quality: int
    width: int
    height: int
    url: str

    @property
    def short_side(self) -> int:
        return min(self.width, self.height) if self.width and self.height else 0


@dataclass(frozen=True)
class Playlist:
    """解析后的 m3u8。

    is_master 为 True 时只填 variant; 否则 segs 是分片 URI (保持原文, 可能是相对
    路径), key_uri / map_uri 是 AES-128 密钥与 fMP4 init 段的**绝对**地址.

    base 是解析这份 playlist 时用的地址 —— segs 保持原文没做 urljoin, 拼绝对地址
    要用它 (见 segment_jobs). 尾字段带默认值, 便于测试里 6 参直接构造.
    """

    is_master: bool
    variant: str | None
    lines: list[str]
    segs: list[str]
    key_uri: str | None
    map_uri: str | None
    base: str = ""


def is_pornhub_url(url: str) -> bool:
    """是否 Pornhub 链接 (含地区子域 / premium)."""
    if not url:
        return False
    try:
        host = (urlparse(url.strip()).netloc or "").lower()
    except Exception:
        return False
    host = host.split(":")[0]
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in PORNHUB_DOMAINS)


def viewkey(url_or_key: str) -> str | None:
    """抠 viewkey: 支持 `?viewkey=` / `/embed/<id>` / 直接给 id. 抠不到返回 None."""
    s = (url_or_key or "").strip()
    if not s:
        return None
    for rx in (_VIEWKEY_RE, _EMBED_RE):
        m = rx.search(s)
        if m:
            return m.group(1)
    return s if _BARE_ID_RE.match(s) else None


def parse_flashvars(html: str) -> dict | None:
    """页面 → flashvars dict. 维护页/结构变了/JSON 坏 → None (调用方据此重试)."""
    if not html:
        return None
    m = _FLASHVARS_RE.search(html)
    if not m:
        return None
    try:
        fv = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    return fv if isinstance(fv, dict) else None


def _int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def hls_gears(flashvars: dict) -> list[HlsGear]:
    """flashvars → HLS 档位列表. 丢掉非 hls / 空 url / 非法 quality (坑: get_media 那条)."""
    defs = flashvars.get("mediaDefinitions") if isinstance(flashvars, dict) else None
    if not isinstance(defs, list):
        return []
    gears: list[HlsGear] = []
    for d in defs:
        if not isinstance(d, dict) or d.get("format") != "hls":
            continue
        url = d.get("videoUrl")
        if not isinstance(url, str) or not url:
            continue
        q = _int(d.get("quality"))
        if q <= 0:                      # quality 是空串/缺失 → 无法比较档位, 丢
            continue
        gears.append(HlsGear(q, _int(d.get("width")), _int(d.get("height")), url))
    return gears


def pick_best_gear(gears: list[HlsGear]) -> HlsGear | None:
    """最高档 (quality 最大). 空列表返回 None."""
    return max(gears, key=lambda g: g.quality) if gears else None


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
    """分片落盘的本地名. 扩展名按原样保留 (.ts 与 .m4s 不能混)."""
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

    分片换成 seg_NNNNN.ext, EXT-X-MAP 指向 init.mp4, EXT-X-KEY 的 URI 指向 enc.key
    (IV 等其余属性原样保留, 解密仍然正确).
    """
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
    total_bytes_estimate 同义, 所以复用这个 key 而不是新增.
    """
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

@dataclass
class PornhubVideo:
    """一次取流的结果: 页面 session + 可用 master.m3u8 + 元信息.

    session 必须随直链一起传给 download_hls —— CDN 认它的 cookie (坑 1).
    """

    viewkey: str
    session: object            # curl_cffi.Session
    master: str
    duration: int
    quality: int


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
    return f"https://cn.pornhub.com/view_video.php?viewkey={vid}"


def _open_page(vid: str, proxies, on_status=None) -> tuple[object, dict]:
    """取视频页 flashvars. 反爬会零星回 403 维护页 —— 换新会话重试绕开.

    返回 (session, flashvars); 全部尝试失败抛 PornhubUnavailable.
    """
    last = ""
    for i in range(25):
        try:
            s = _new_session()
            r = s.get(_page_url(vid), proxies=proxies, timeout=45)
            fv = parse_flashvars(r.text)
            if fv is not None:
                return s, fv
            last = str(r.status_code)
        except Exception as e:
            last = type(e).__name__
        if on_status:
            on_status(i + 1, last)
        time.sleep(min(2 + i, 8))
    raise PornhubUnavailable(
        f"页面取不到 ({last}) — 检查代理是否可用 (HTTP(S)_PROXY)")


def extract_pornhub(url_or_key: str, *, on_status=None) -> PornhubVideo:
    """取页面 → 选最高档 HLS → 验 master 可用 (不通就重取页面换 token, 坑 2).

    on_status(round_no, detail) 每轮回调一次, 供 UI 显示「解析中」而非像卡死.
    """
    vid = viewkey(url_or_key)
    if not vid:
        raise PornhubUnavailable(f"从 {url_or_key!r} 抠不出 viewkey")
    proxies = _proxies()

    for round_ in range(12):
        s, fv = _open_page(vid, proxies, on_status)
        gears = hls_gears(fv)
        dur = _int(fv.get("video_duration"))
        for gear in sorted(gears, key=lambda g: -g.quality):
            try:
                r = s.get(gear.url, proxies=proxies, timeout=45, headers=_REFERER)
            except Exception:
                continue
            if r.status_code == 200 and r.text.lstrip().startswith("#EXTM3U"):
                return PornhubVideo(vid, s, gear.url, dur, gear.quality)
        if on_status:
            on_status(round_ + 1, "no-valid-master")
        time.sleep(1.5)
    raise PornhubUnavailable("所有档位都拿不到可用 master.m3u8 (token 一直失效)")


def _fetch_media_playlist(s, video: PornhubVideo, proxies) -> Playlist:
    """master 常是 variant playlist, 下钻到真正带分片的 media playlist."""
    r = s.get(video.master, proxies=proxies, timeout=45, headers=_REFERER)
    pl = parse_playlist(r.text, video.master)
    if not pl.is_master:
        return pl
    r2 = s.get(pl.variant, proxies=proxies, timeout=45, headers=_REFERER)
    return parse_playlist(r2.text, pl.variant)


def download_hls(video: PornhubVideo, dest: str, *, audio_only: bool = False,
                 on_progress=None, workdir: str | None = None) -> str:
    """抓分片到本地 → 本地 playlist → ffmpeg 拼接为 dest. 返回 dest.

    audio_only=True 时从同一份本地 playlist 直接抽音频成 m4a (不走中间 mp4,
    省一遍全量重写) —— 与抖音路径的「仅音频」预设语义一致.

    进度经 on_progress 发 yt-dlp 风格字典 (见 progress_dict), 收尾发 finished.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    hook = on_progress or (lambda _d: None)
    proxies = _proxies()
    pl = _fetch_media_playlist(video.session, video, proxies)
    if not pl.segs:
        raise PornhubUnavailable("media playlist 里没有分片 (CDN 可能回了错误页)")

    own_workdir = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix=f"pornhub_{video.viewkey}_")
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
            raise PornhubUnavailable(f"{name} 重试 {_SEG_TRIES} 次仍失败 ({last})")

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

        hook({"status": "finished"})        # 复用 GUI 已有的「合并音频视频 (ffmpeg)…」
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "warning",
               "-i", local_pl, "-c", "copy"]
        if audio_only:
            cmd += ["-vn"]
        # aac_adtstoasc 只对 TS 里的 ADTS AAC 有效; fMP4 输入加了反而报错
        if not all(n.endswith(".m4s") for n, _ in jobs if n.startswith("seg_")):
            cmd += ["-bsf:a", "aac_adtstoasc"]
        cmd += ["-movflags", "+faststart", "-y", dest]
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0 or not os.path.exists(dest) or os.path.getsize(dest) < 1_000_000:
            tail = "\n".join((p.stderr or "").strip().splitlines()[-4:])
            raise PornhubUnavailable(f"ffmpeg 拼接失败 rc={p.returncode}\n{tail}")
        return dest
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
