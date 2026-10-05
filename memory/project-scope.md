---
name: project-scope
description: "yt-downloader 项目身份与业务边界 — 下游是 fitness-video-pipeline,准入门槛和瑜伽预审是核心"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7ac65baf-4fef-4d86-a03a-3e2c6cb4e369
  modified: 2026-09-16T18:44:13.161Z
---

yt-downloader 是 YouTube / 抖音视频下载器 GUI 桌面应用。Python 3.11 + PySide6 (Qt6) + yt-dlp + Node.js。

**业务核心:**
- **准入门槛** — 下载完用 ffprobe 读规格,对三道门槛红绿提示:短边 ≥720px / 码率 ≥2Mbps / 时长 ≥30s。这三阈值是**核心业务逻辑**,给健身主管线筛「能不能直接用」的源素材。改前必须跟用户确认影响面。(码率 2026-09-17 由 5Mbps 下调以适配抖音源; 现行值以 `verify.py` 的 `THRESH_BITRATE` 为准 —— 别抄这里的数字, 详见 [[douyin-2mbps-gate-pending-visual-check]])
- **瑜伽预审** — 抽 9 帧缩略图 + 衣着人工清单,预筛抖音「衣着暴露」风险。本机有 fitness 仓库时可点「深度体态扫描」跑 YOLO。
- **下游消费者** — `F:\wkspace\fitness-video-pipeline`。本项目下载的视频供主管线做后续处理；准入结果和瑜伽预审目前仅在 GUI 中供人工查看，不导出持久化标记或缩略图。

**不在范围:**
- 不是给别人发布的库(不维护 API 兼容、不写 changelog)
- 不是云服务(纯本地)
- 不是 macOS / Linux 应用(用户是 Windows,UI 文案中文)

**Why:** 让任何会话快速明白这项目的边界与「不能拍脑袋改」的地方,避免改了阈值/标记格式导致下游主管线静默失败。
**How to apply:** 改 `yt_downloader/verify.py` 阈值 / `yt_downloader/app.py` 标记格式 / `yt_downloader/yoga_check.py` 输出结构时,先看这条 memory 再决定。