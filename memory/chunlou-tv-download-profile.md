---
name: chunlou-tv-download-profile
description: chunlou.tv 取流档案 — CDN 仅查 UA、HLS AES-128、Supabase 元数据、付费墙结构与画质准入相关性
metadata: 
  node_type: memory
  type: reference
  originSessionId: f674692e-d309-4715-be19-28fa66155c07
  modified: 2026-09-24T14:40:50.930Z
---

chunlou.tv(AI 短剧站,RTA 成人分级)2026-09-24 实测取流档案:

- **架构**:Vue SPA + Supabase(数据)+ 自建 HLS CDN `hls.chunlou.tv`(媒体)。初始 HTML 空壳,yt-dlp generic extractor 不认(Unsupported URL)。
- **CDN 鉴权只查 User-Agent**:无 UA → 403,任意浏览器 UA → 200;Referer 无关。无签名墙、无 IP 封锁。
- **取流公式**:`https://hls.chunlou.tv/hls/{episode-uuid}/master.m3u8?token=&lang=zh` + 浏览器 UA,yt-dlp 直吃(`format: b`,变体是音视频混合单流;AES-128 密钥自动处理)。实测 1080p 一集 79MB / 1 分钟。
- **集 UUID 就是页面 `?ep=` 参数**,同时也是 HLS 路径段、同时也是 Supabase `episodes` 表主键(注意表名是复数 `episodes`)。
- **付费墙**:episodes 表 `coin_price > 0` 即付费;匿名 playlist 被服务端截断到 `preview_sec` 秒(有预览集),`preview_sec = 0` 的付费集直接 401。付费墙不绕过;合法路径 = 浏览器登录拿 entitled token(未实现,思路同 [[douyin_browser]])。
- **元数据入口**:anon key 明文在 `/assets/config-*.js`,Supabase REST 直接查。URL `https://grzjuztzhrexhvmetnvd-all.supabase.co/rest/v1/`。
- **签名时效**:变体/密钥/分片 URL 的 `e=` 参数数小时过期,取到立即下载(同抖音 play_addr)。
- **画质因剧差异大,直接关系准入门槛**:实测有的剧 1080x1920 @ 3.89 Mbps(过 [[douyin-2mbps-gate]]),有的剧最高 720p @ 1.50 Mbps(过不了)。挑源先查该剧 `episodes` + 实测码率。
- **GUI 未集成**:2026-09-24 时贴 chunlou 链接会失败;若要支持,参照 douyin_browser.py 加 chunlou 分流(提取 = 查 Supabase 拿集信息 + 拼 master.m3u8 + 注 UA,比抖音简单得多,不需要浏览器)。
