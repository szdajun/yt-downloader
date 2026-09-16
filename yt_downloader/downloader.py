"""yt-dlp 下载封装.

选格式 + ffmpeg 合流 + 进度回调 + cookies 认证. 提供:
  - download(url, out_dir, fmt, *, on_progress, on_error, cookies_browser,
    cookies_file): 核心下载 (回调式, 框架无关). GUI (Qt) / 脚本通用.
  - download_sync(url, out_dir, fmt, q, cookies_browser): queue 适配
    (向后兼容批量/旧调用), 内部转调 download().

两条下载通路 (download() 按域名自动分流):
  - YouTube 等: 走 yt-dlp 原生 extractor (需代理, 见 _make_opts 的 direct).
  - 抖音: 走浏览器取流 (_download_douyin) — yt-dlp 的 DouyinIE 已被抖音
    ArgusSecurityPlugin 签名墙打死, 详见 douyin_browser 模块 docstring.

最终文件路径检测: 记录下载前 output_dir 最新 mtime, 下载后取 mtime 更新的
那个媒体文件 (不依赖 yt-dlp 内部命名/合并后改名细节, 最稳).
"""
from __future__ import annotations

import os
import queue
import sys
import time
from collections.abc import Callable

# Windows 控制台默认 GBK: 视频标题含 emoji/特殊字 (✨❤️ 等) 时 yt-dlp 写日志
# → UnicodeEncodeError (gbk can't encode ✨) → 下载中途崩, 只剩 .f###.mp4 片段
# 无合并产物. 强制 stdout/stderr UTF-8 (errors=replace 容错) 一次性根治所有调用方
# (GUI/CLI/脚本). 幂等; 窗口态 stdout=None 时 reconfigure 会抛, try 兜底跳过.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yt_dlp  # noqa: E402  # delayed import — must run after stdout reconfigure above

from .douyin_browser import (  # noqa: E402  # 同上, 必须在 stdout reconfigure 之后
    DouyinBrowserUnavailable,
    extract_douyin,
    is_douyin_url,
    pick_best_gear,
)

# 已知好路径优先 (Winget 版编码 bug); 不存在回退 PATH.
_FFMPEG_DIR = r"C:\Users\18091\ffmpeg"


def _ffmpeg_location() -> str:
    p = os.path.join(_FFMPEG_DIR, "ffmpeg.exe")
    return p if os.path.exists(p) else "ffmpeg"


# ---- 格式预设 ----
# YouTube 高清多为 DASH 分流 (video + audio 分开), 需 ffmpeg 合流.
FORMATS: dict[str, str] = {
    "最高画质 (mp4)": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p (mp4)":    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
    "720p (mp4)":     "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
    "仅音频 (m4a)":   "bestaudio[ext=m4a]/bestaudio/best",
}

AUDIO_SUFFIXES = (".m4a", ".mp3", ".opus", ".webm", ".ogg")
VIDEO_SUFFIXES = (".mp4", ".mkv", ".webm")


def is_audio_format(label: str) -> bool:
    return "音频" in label or "audio" in label.lower()


def _make_opts(output_dir: str, format_label: str, hook,
               cookies_browser: str = "", cookies_file: str = "",
               outtmpl: str | None = None, overwrites: bool | None = None,
               direct: bool = False) -> dict:
    audio = is_audio_format(format_label)
    opts = {
        "format": FORMATS.get(format_label, FORMATS["最高画质 (mp4)"]),
        # 选源策略: 先分辨率后码率. yt-dlp 默认偏好 h265(更高效→更低码率), 但做源素材
        # 要的是码率最高 (要进管线重编码, 压缩痕迹才是大敌, 不在乎编码效率). 抖音同分辨率
        # 常有 393/540/714/1157kbps 多档, 默认会拿 714 h265 而漏掉 1157 h264 — 此项修正.
        "format_sort": ["res", "tbr"],
        # 标题截断 100 字符 + 视频 id, 防重名/超长; ext 由 yt-dlp 按实际格式决定.
        # outtmpl 可被覆盖 (force 模式算 a(N) 空闲名重下时用).
        "outtmpl": outtmpl or os.path.join(output_dir, "%(title).100B [%(id)s].%(ext)s"),
        "ffmpeg_location": _ffmpeg_location(),
        "progress_hooks": [hook],
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "windowsfilenames": True,   # Windows 友好文件名
        "concurrent_fragment_downloads": 4,
    }
    if overwrites is not None:
        opts["overwrites"] = overwrites
    if not audio:
        opts["merge_output_format"] = "mp4"
    else:
        # 音频: 提取为 m4a (ffmpeg)
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "0",   # 最佳
        }]
    if direct:
        # 抖音对非中国大陆 IP 地理封锁 (web API 与 douyinvod CDN 均是), 而本机
        # HTTP(S)_PROXY 指向境外节点 (实测出口大阪). yt-dlp 里 proxy="" 会被翻成
        # __noproxy__ = 强制直连; YouTube 保持继承环境代理 (它反而必须走代理).
        opts["proxy"] = ""
    if cookies_file:             # cookies.txt (Netscape) — 最通用, 绕所有浏览器加密
        opts["cookiefile"] = cookies_file
    elif cookies_browser:        # Firefox 自动读 (chrome/edge 新版 DPAPI/App-Bound 加密读不出)
        opts["cookiesfrombrowser"] = (cookies_browser,)
    # YouTube 2025+ n-challenge 需 JS runtime 解签名 (yt-dlp-ejs 提供 solver script).
    # 检测可用 runtime (deno 推荐 > node > bun); 没有则留空, yt-dlp 会警告 formats 缺失.
    import shutil as _shutil
    for _rt in ("deno", "node", "bun"):
        if _shutil.which(_rt):
            opts["js_runtimes"] = {_rt: {}}
            break
    return opts


def _newest_mtime(output_dir: str) -> float:
    """output_dir 下媒体文件的最大 mtime (无文件返回 0)."""
    mx = 0.0
    for root, _, files in os.walk(output_dir):
        for fn in files:
            if fn.lower().endswith(VIDEO_SUFFIXES + AUDIO_SUFFIXES):
                try:
                    mx = max(mx, os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
    return mx


def _find_final(output_dir: str, before: float) -> str | None:
    """下载后找 mtime > before 的最新媒体文件."""
    best = None
    best_mt = before
    for root, _, files in os.walk(output_dir):
        for fn in files:
            if fn.lower().endswith(VIDEO_SUFFIXES + AUDIO_SUFFIXES):
                p = os.path.join(root, fn)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                if mt > best_mt:
                    best, best_mt = p, mt
    return best


def _noop(_d: dict) -> None:
    pass


def _find_by_id(output_dir: str, vid: str) -> str | None:
    """找 output_dir 顶层文件名含 [<vid>] 的媒体文件 (outtmpl = ... [%(id)s].ext).

    YouTube (DASH 合流) 与抖音 (渐进式) 都把 [id] 嵌进文件名, 故按 id 定位已存在文件最稳.
    多个匹配取最新 mtime.
    """
    best, best_mt = None, -1.0
    try:
        names = os.listdir(output_dir)
    except OSError:
        return None
    for fn in names:
        if f"[{vid}]" in fn and fn.lower().endswith(VIDEO_SUFFIXES + AUDIO_SUFFIXES):
            p = os.path.join(output_dir, fn)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if mt > best_mt:
                best, best_mt = p, mt
    return best


def _find_existing_by_url(url: str, output_dir: str, format_label: str,
                          cookies_browser: str, cookies_file: str) -> str | None:
    """没写新文件时 (多半是 yt-dlp 因文件已存在跳过): extract_info 拿 id, 按 id 找现有文件."""
    opts = _make_opts(output_dir, format_label, _noop, cookies_browser, cookies_file)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None
    vid = (info or {}).get("id")
    return _find_by_id(output_dir, vid) if vid else None


def _unique_force_outtmpl(url: str, output_dir: str, format_label: str,
                          cookies_browser: str, cookies_file: str) -> str | None:
    """force 模式: 用 yt-dlp prepare_filename 算出默认文件名 (与正常下载完全一致, 含
    %(title).100B 字节截断 + windowsfilenames), 再找空闲 a(N) 槽位. 返回字面 outtmpl.

    ext 强制成 mp4(视频, 合流产物)/m4a(音频) — 与默认下载实际产物对齐, 保证 base 名一致
    → 重名检测准确. extract 失败返回 None (调用方回退到默认 outtmpl + overwrites).
    """
    opts = _make_opts(output_dir, format_label, _noop, cookies_browser, cookies_file)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            default_path = ydl.prepare_filename(info)
    except Exception:
        return None
    if not default_path:
        return None
    base, _ext = os.path.splitext(default_path)
    ext = ".m4a" if is_audio_format(format_label) else ".mp4"
    return _free_slot(base + ext)   # 字面路径, yt-dlp 原样用作 outtmpl (无 %() 字段)


def _normalize_url(url: str) -> str:
    """规范化用户粘贴的 URL (透明修正常见误粘, 防直接报 Unsupported URL).

    抖音: 从搜索页 / 用户主页点开视频弹窗后复制地址栏, 拿到的是 /search/{关键词}
    或 /user/{uid} 这种页面 URL, 带 modal_id=<视频id>; yt-dlp 抖音 extractor 只认
    /video/{id}, 否则 Unsupported URL. 提取 modal_id(优先)/item_id/id(纯数字)
    → 重写成 https://www.douyin.com/video/{id}. v.douyin.com 短链 yt-dlp 自带跟随
    不动; 已是 /video/{id} 不动; 非 douyin 域不动; 提取不到数字 id 原样返回
    (交给 yt-dlp 如实报错). 同理 iesdouyin.com.
    """
    from urllib.parse import parse_qs, urlparse
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url
    host = (parsed.netloc or "").lower()
    if not (host.endswith("douyin.com") or host.endswith("iesdouyin.com")):
        return url
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "video" and parts[1].isdigit():
        return url   # 已是规范视频页
    qs = parse_qs(parsed.query)
    for key in ("modal_id", "item_id", "id"):
        vals = qs.get(key)
        if vals and vals[0].isdigit():
            return f"https://www.douyin.com/video/{vals[0]}"
    return url


def _free_slot(candidate: str) -> str:
    """candidate 已占用时返回 base(1).ext / base(2).ext … 第一个空闲名."""
    base, ext = os.path.splitext(candidate)
    n = 0
    while os.path.exists(candidate):
        n += 1
        candidate = f"{base}({n}){ext}"
    return candidate


# ---- 抖音 (浏览器取流) ----
# 2026-09 起抖音给 web detail API 加了 ArgusSecurityPlugin 签名墙 (要 Uifid 请求头
# + a_bogus 签名). yt-dlp 的 DouyinIE 两样都没实现 → 恒定 403, 且 master 依然如此,
# 升级 yt-dlp 无效. 详见 douyin_browser 模块 docstring.
# 这里只负责把浏览器取到的直链交给 yt-dlp 下载 (直连 + Referer 绕 CDN 防盗链).
_DOUYIN_REFERER = "https://www.douyin.com/"


def _douyin_base_name(video, output_dir: str) -> str:
    """算抖音产物文件名主干 (不含扩展名).

    借 yt-dlp 的 prepare_filename 套用项目统一的 `%(title).100B [%(id)s].%(ext)s` —
    100 字节截断与 windowsfilenames 净化都由 yt-dlp 做, 保证与 YouTube 路径命名一致,
    下游 _find_by_id 照样能按 [id] 定位到文件.
    """
    opts = _make_opts(output_dir, "最高画质 (mp4)", _noop, direct=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        name = ydl.prepare_filename(
            {"title": video.title, "id": video.vid, "ext": "mp4"})
    return os.path.splitext(name)[0]


def _download_douyin(url: str, output_dir: str, format_label: str, *,
                     on_progress, on_error, force: bool) -> tuple[str | None, bool]:
    """抖音下载: 浏览器取直链 → yt-dlp 直连 CDN 下载.

    返回约定与 download() 一致: (final_path | None, skipped).
    """
    hook = on_progress or _noop
    before = _newest_mtime(output_dir)
    hook({"status": "douyin_extracting"})   # 浏览器冷启动约 10s, 给 UI 一个反馈

    try:
        video = extract_douyin(url)
    except DouyinBrowserUnavailable as e:
        if on_error:
            on_error(f"{url}\n    [抖音] 浏览器取流不可用: {e}")
        return None, False
    except Exception as e:
        if on_error:
            on_error(f"{url}\n    [抖音] 取流失败: {type(e).__name__}: {e}")
        return None, False

    if not video:
        if on_error:
            on_error(f"{url}\n    [抖音] 未返回可用视频数据 — 风控拦截 / 作品不存在 / "
                     "该作品仅登录可见. 稍后重试或先在浏览器里打开一次该视频.")
        return None, False

    gear = pick_best_gear(video.gears, format_label)
    if not gear:
        if on_error:
            on_error(f"{url}\n    [抖音] 所有档位都没有可下载地址")
        return None, False

    audio = is_audio_format(format_label)
    final = _douyin_base_name(video, output_dir) + (".m4a" if audio else ".mp4")
    if force:
        final = _free_slot(final)          # 不覆盖旧文件: 顺延成 a(1)/a(2)
    elif os.path.exists(final):
        return final, True                 # 增量跳过 (与 YouTube 路径一致)

    # 音频预设: 先下视频档, 再由 FFmpegExtractAudio 抽成 m4a (yt-dlp 会删掉中间 mp4)
    dl_target = os.path.splitext(final)[0] + ".mp4"
    opts = _make_opts(output_dir, format_label, hook, direct=True, outtmpl=dl_target)
    opts["http_headers"] = {"Referer": _DOUYIN_REFERER}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([gear.url])
    except Exception as e:
        if on_error:
            # 直链带时效 token, 取流与下载间隔过久会 403 — 重试即可.
            on_error(f"{url}\n    [抖音] 直链下载失败: {e}\n"
                     "      (取流与下载间隔过久会使 token 过期, 重试一次即可)")
        return None, False

    if os.path.exists(final):
        return final, False
    time.sleep(0.5)                        # ffmpeg 抽音频可能延迟落盘
    found = _find_final(output_dir, before)
    return found, (found is None)


def download(url: str, output_dir: str, format_label: str, *,
             on_progress: Callable[[dict], None] | None = None,
             on_error: Callable[[str], None] | None = None,
             cookies_browser: str = "", cookies_file: str = "",
             force: bool = False) -> tuple[str | None, bool]:
    """核心下载 (回调式, 框架无关). GUI/脚本通用.

    - on_progress(dict): yt-dlp 进度钩子 (status downloading/finished, 字节/速度/eta).
    - on_error(str): 下载异常的可读消息.
    - force: True 时即使文件已存在也重下, 自动改名 a(1)/a(2) 不覆盖旧文件.
    返回 (final_path | None, skipped). skipped=True 表示文件已存在被跳过 (增量跳过,
    与 fitness 主管线一致), 仍返回已存在文件路径供验证/展示; force=True 时 skipped 恒 False.
    """
    os.makedirs(output_dir, exist_ok=True)
    url = _normalize_url(url)   # 搜索页 modal_id → /video/{id} 等 (抖音误粘修正)
    if is_douyin_url(url):
        # 抖音走浏览器取流 — yt-dlp 的 DouyinIE 已被抖音签名墙打死 (见 _download_douyin)
        return _download_douyin(url, output_dir, format_label,
                                on_progress=on_progress, on_error=on_error,
                                force=force)
    before = _newest_mtime(output_dir)
    hook = on_progress or _noop
    outtmpl = None
    overwrites = None
    if force:
        outtmpl = _unique_force_outtmpl(url, output_dir, format_label,
                                        cookies_browser, cookies_file)
        overwrites = True   # 确保不触发 yt-dlp 自己的 skip (目标名已空闲, 一般也不会 skip)
    opts = _make_opts(output_dir, format_label, hook, cookies_browser, cookies_file,
                      outtmpl=outtmpl, overwrites=overwrites)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:  # DownloadError / 网络等
        if on_error:
            msg = f"{url}\n    {e}"
            es = str(e).lower()
            # YouTube 反爬没返回视频流时, yt-dlp 内部对空格式列表取下标 → 泄漏 IndexError
            # ("list index out of range") 或 "no formats"/"only images". 给可读提示而非裸异常.
            anti_bot = (isinstance(e, IndexError)
                        or "no video formats" in es or "no formats" in es
                        or "only images" in es)
            if anti_bot:
                msg += ("\n    [可能原因] YouTube 反爬没返回视频流 (空格式).\n"
                        "      • 装了 Node.js ≥22 且在 PATH 吗? (解 n-签名挑战; https://nodejs.org)\n"
                        "      • 极少数视频要 PO token → 起 bgutil 本地 server (:4416): "
                        "https://github.com/Brainfood/bgutil-ytdlp-pot-provider\n"
                        "      • 或换条视频 / 用 cookies.txt 登录态再试")
            on_error(msg)
        return None, False
    # ffmpeg 合流/提取可能延迟写盘, 给一点宽限
    time.sleep(0.5)
    found = _find_final(output_dir, before)
    if found:
        return found, False
    if force:
        return None, False   # force 模式没写出新文件 = 真失败
    # 没写新文件 → 多半是文件已存在被 yt-dlp 跳过 (YouTube 跳过不触发 finished hook,
    # 抖音触发但给最终名). 统一按 video id 找现有文件 (增量跳过).
    existing = _find_existing_by_url(url, output_dir, format_label, cookies_browser, cookies_file)
    return (existing, True) if existing else (None, False)


def download_sync(url: str, output_dir: str, format_label: str,
                  q: queue.Queue, cookies_browser: str = "",
                  cookies_file: str = "", force: bool = False) -> str | None:
    """queue 适配 (向后兼容批量/旧调用). 内部转调回调式 download(). 返回路径 (忽略 skipped)."""
    path, _skipped = download(
        url, output_dir, format_label,
        on_progress=lambda d: q.put(("progress", d)),
        on_error=lambda m: q.put(("error", m)),
        cookies_browser=cookies_browser, cookies_file=cookies_file, force=force,
    )
    return path
