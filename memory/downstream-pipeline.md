---
name: downstream-pipeline
description: 下游主管线 fitness-video-pipeline 怎么消费本项目的产物 — 接口契约
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7ac65baf-4fef-4d86-a03a-3e2c6cb4e369
  modified: 2026-07-30T02:53:23.572Z
---

下游主管线: `F:\wkspace\fitness-video-pipeline`(单独的 Claude Code 会话跑过)。

**接口契约:**

**输出目录:** 默认 `C:\Users\18091\Downloads\yt-downloader\`,可在 GUI 设置里改(写到 `~/.yt-downloader/config.json` 的 `output_dir`)。主管线扫这个目录(默认路径)找新下载的视频。

**文件命名:** yt-dlp 自动命名 — `<title>.mp4` / `<title>.<ext>`,非法字符被 yt-dlp 转义。主管线按文件扩展名识别,不依赖具体命名。

**准入标记格式:**
- 通过:`[✓ 达标]  <文件名>  <分辨率>  <码率>  <时长>  (<大小>)`
- 不通过:`[✗ 不达标]  <文件名>  <分辨率>  <码率>  <时长>  (<大小>)` + `→ <不达标原因>`
- 这些标记写在 GUI 日志区(`QTextEdit`),主管线目前是**手工读日志**判准入,不是机器解析

**瑜伽预审缩略图:** 当前不是持久化接口。`YogaFrameWorker` 在系统临时目录创建 `yoga_frames_*` 目录，`extract_frames()` 输出 `frame_%03d.png`（通常 9 帧）供人工复核窗口显示；窗口关闭后 `_on_yoga_frames()` 会递归删除整个临时目录。下游不能消费这些临时图片；若未来需要对接，必须另行设计持久化输出契约。

**ffprobe 验证输出:** GUI 显示用,不导出文件。主管线要重新跑 ffprobe 自己读。

**修改红线:**
- 改 `[✓ 达标]` / `[✗ 不达标]` 标记格式 → 主管线那边的人工审核流程可能误判
- 改输出目录默认值 → 主管线那边白跑
- 改 `config.json` schema(`output_dir` 字段名) → 用户 GUI 设置失效

**Why:** 让 Claude 知道这项目跟主管线怎么衔接,改一处要看另一处,避免主管线静默失败(主管线跑完才报错,定位难)。
**How to apply:** 改 `app.py` 日志格式 / `config.py` 默认值 / `config.py` schema 前,先看这条 memory 再决定;若要让主管线消费瑜伽缩略图，先设计并实现持久化输出契约。
