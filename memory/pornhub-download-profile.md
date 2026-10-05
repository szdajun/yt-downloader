---
name: pornhub-download-profile
description: Pornhub 取流档案 — yt-dlp extractor 死在 PhantomJS; 可用通路是 flashvars 的 HLS + 页面 session cookie; 四个已踩坑; 已集成进 yt_downloader/pornhub.py
metadata:
  node_type: memory
  type: reference
  originSessionId: 81b16e5f-5e95-41b9-8a73-985efa02ee3b
  modified: 2026-10-05T08:23:07.048Z
---

Pornhub 取流 (2026-10-05 实测)。**已进主产品线** —— 不是一次性脚本:
`yt_downloader/pornhub.py`(纯函数层 + 取流层, 仿 `douyin_browser.py`) +
`downloader.py:_download_pornhub()` 作为 `download()` 的第三条分流 +
`app.py:_on_progress` 的 `pornhub_extracting` 状态分支; 纯函数测试在
`tests/test_pornhub.py`, 分流测试在 `tests/test_downloader.py`。

- **yt-dlp 的 PornHubIE 是死路**: 它请求 `platform=pc` 页面, 命中反爬后返回
  `<body onload="go()">` + `document.cookie=` 的 JS 挑战, extractor 靠 **PhantomJS**
  重放 —— PhantomJS 已停维护、本机没装 → 恒定 `ERROR: PhantomJS not found`.
  带 Firefox 完整登录 cookie 照旧触发 (不是登录态问题), 升级 yt-dlp 无效.
- **可用通路**: 页面 HTML 里 `var flashvars_<n> = {...}` 自带 `mediaDefinitions`,
  其中 `format:"hls"` 条目是真实可下的 master.m3u8 (240/480/720/1080).
  `format:"mp4"` + `remote:true` 那条指向 `cn.pornhub.com/video/get_media`, 该 API
  被反爬挡死 (403 maintenance), **不要走**.
- **坑 1 — CDN 只认页面 session 的 cookie**: 同一 m3u8 用取 flashvars 的那个 session
  请求 200, 换新 session 请求 410/412. 直链必须复用页面 session.
- **坑 2 — 页面偶尔下发不带 token 的直链** (validfrom=validto=0) → `412 request
  incorrect`. 要遍历档位试 master, 不通就重新取页面换 token.
- **坑 3 — CDN 按并发限流**: 8 并发时随机 410 Gone (串行复测 3/3 全 200).
  4 并发 + 遇 410/429 退避重试即稳.
- **坑 4 — ffmpeg 的 HTTP 栈过不了该 CDN**: 同一 URL curl_cffi 200 / ffmpeg 410.
  所以分片用 curl_cffi 拉到本地, 重写成相对路径的本地 m3u8, 再让 ffmpeg 做本地拼接
  (顺带天然支持 AES-128 与 fMP4).
- **反爬会零星返回 403 维护页**, 换新 session 重试即可绕过 (实测成功率不低, 需重试循环).
- 代理: 走 `HTTP(S)_PROXY` (与抖音相反, 抖音必须 `proxy=""` 直连).
- 命名/文本约定同 [[content-filter-1301-handling]]: 文件名只用 viewkey, 不复述标题.
- **集成契约**: 进度只发 yt-dlp 既有的 key (`status/downloaded_bytes/total_bytes_estimate/
  speed/eta`), 所以 GUI 只多了一个 label 分支, 没动 `_on_progress` 的解析;
  产物 `{viewkey}.mp4` / 仅音频 `.m4a`; `force` 时走 `_free_slot()` 顺延不覆盖。
- 实测两条独立 1080p 源, 均过 [[douyin-2mbps-gate-pending-visual-check]] 的准入门槛:
  ① 700 MB / 27 min / 3.63 Mbps  ② 1.26 GB / 48.1 min / 3.76 Mbps (h264)。
  第二条是**经 GUI 走完整流程**跑通的(状态栏出 pornhub_extracting → 分片 → remux
  → ffprobe 判定), 说明这条通路在真界面上可复现, 不是脚本一次性产物。
- 文档已同步: `CLAUDE.md` 模块表(11 个)+ 踩坑速查新增 Pornhub 段; `README.md` 新增
  「🔞 Pornhub 下载」一节。
