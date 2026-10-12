---
name: youporn-download-profile
description: YouPorn 取流档案 — yt-dlp extractor 有 stale filter (defaultQuality 全 bool); 可用通路是 mediaDefinitions HLS 优先 + MP4 兜底; 三个已踩坑; 已集成进 yt_downloader/youporn.py
metadata:
  node_type: memory
  type: reference
  modified: 2026-10-12T16:49:40.305Z
  originSessionId: 2dcbbd3f-acde-49cc-9aa4-71e561f0ea83
---

YouPorn 取流 (2026-10-13 实测)。**已进主产品线** —— 不是一次性脚本:
`yt_downloader/youporn.py`(纯函数层 + 取流层, 仿 [[pornhub-download-profile]] 的
结构, HLS 基础设施 parse_playlist/segment_jobs/rewrite_local/progress_dict 是
verbatim 复制而非 import, 避免跨域反向依赖)+
`downloader.py:_download_youporn()` 作为 `download()` 的第四条分流 +
`app.py:_on_progress` 的 `youporn_extracting` 状态分支; 纯函数测试在
`tests/test_youporn.py`, 分流测试在 `tests/test_downloader.py`。

- **yt-dlp YouPornIE 是死路(另一种)**: 它的 `_real_extract` 里有
  `not isinstance(v['defaultQuality'], bool)` 这条过滤器, 而**现在所有 `mediaDefinitions`
  条目的 `defaultQuality` 都是 bool**, 导致 HLS 全部被滤掉; 剩下的 mp4 dict 是
  `vcodec=None` 形态, formats 数组空, 下载报「No video formats found」。
  不是登录/cookie 问题, 升级 yt-dlp 无效。
- **可用通路**: 页面 HTML 里 `mediaDefinitions` 是数组, 两条 entry:
  - `format: "hls"` + `quality: None` (注意!) — 这条指向 `https://www.youporn.com/media/hls/?s=...`
    **是个 JSON endpoint**, 不是真实 m3u8。GET 它拿到的 step2 JSON 才是 4 档 master
    (240/480/720/1080, 各自含 `defaultQuality`/`width`/`height`/`videoUrl`)。
    再 GET 选中的 master 拿 variant `index-v1-a1.m3u8` (165 个 TS 分片, 无 AES-128
    / 无 fMP4 init, 比 Pornhub 还干净) → ffmpeg `-c copy` 拼通。
  - `format: "mp4"` + `remote: true` — 拿到的 4 个 direct mp4 URL 带
    `validfrom/validto/rate/burst/hash` 时效/限速参数, 实战被 `rate=50000k`
    限速, 仅作 HLS 失败兜底 (1 轮)。
- **坑 1 — CDN 认抓页面那次的 session cookie** (同 [[pornhub-download-profile]] 坑 1):
  yt-dlp 用它自己的 HTTP 客户端 GET `mediaDefinitions[*].videoUrl` 的 JSON 时丢
  page session, 反爬挡。`youporn.py` 整个生命周期共用一个 curl_cffi session,
  page → JSON → segments 串到底。
- **坑 2 — curl_cffi 与 ypncdn TLS 握手偶发抖动**: 1/8 ~ 2/8 概率
  `SSLError invalid library (0)`。`_open_page` 12 轮 retry + 分片层 except Exception
  覆盖, 实测重试 1~2 次就过。
- **坑 3 — `hls_gears()` 不能按 `quality <= 0` 过滤**: 页面 `mediaDefinitions` 的
  hls entry 是「JSON endpoint」不是「具体档位」, `quality=None` 是合法形态。真档位
  在 step2 JSON 里。**第一次实现踩这个坑** — 写了 `if q <= 0: continue`,
  结果 `hls_gears()` 返回空, extract 8 轮 HLS 全失败, 跌穿到 MP4 兜底但仍能下,
  让人误以为「HLS 永远失败」, 排查了半天才发现。修法: `hls_gears()` 接受
  `quality=None` entry, 真正的档位在后续 `_resolve_hls_master()` GET JSON 时解析。
- 4 并发 + 30 重试 (同 [[pornhub-download-profile]] 的 `_CONCURRENCY = 4`、
  `_SEG_TRIES = 30`)。
- 代理: 走 `HTTP(S)_PROXY` (与 [[pornhub-download-profile]] 同, 与抖音相反)。
- 命名/文本约定同 [[content-filter-1301-handling]]: 文件名只用 numeric id
  (如 `103059821.mp4`), 不复述标题/敏感词。
- **集成契约**: 进度只发 yt-dlp 既有的 key (`status/downloaded_bytes/total_bytes_estimate/
  speed/eta`), GUI 只多了一个 `youporn_extracting` label 分支; 产物 `{vid}.mp4` /
  仅音频 `.m4a`; `force` 时走 `_free_slot()` 顺延不覆盖。
- 实测 spike URL `/watch/103059821/`: HLS 走通, 191.8MB / 11 min / 2.32 Mbps
  (h264, 1920×1080), 全部过 [[douyin-2mbps-gate-pending-visual-check]] 的三道
  门槛 (短边 1080 ≥720 / 码率 2.32 ≥2 / 时长 660 ≥30)。
- **与 [[pornhub-download-profile]] 的对比**: HLS 路径几乎同构 (连
  parse_playlist/segment_jobs/rewrite_local 都 verbatim 复制), 但
  (a) 无 AES-128 加密, 无 fMP4 init (更干净);
  (b) 失败模式不是「token 过期」, 而是「TLS 抖动 + stale filter」;
  (c) HLS 优先 + MP4 兜底, Pornhub 是纯 HLS (mp4 那条是死路, 不做兜底)。
- 文档已同步: `CLAUDE.md` 模块表(11→12)+ 踩坑速查新增 YouPorn 3 坑段;
  `README.md` 新增「🔞 YouPorn 下载」一节 + 功能 bullet + 项目结构。
