---
name: code-style
description: 代码风格约定 — 中文注释/UI/Commit、Win 路径、注释解释 WHY
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7ac65baf-4fef-4d86-a03a-3e2c6cb4e369
  modified: 2026-07-30T01:38:11.233Z
---

本项目代码风格约定:

**语言:**
- 中文注释(`# 用 ffprobe 读规格,验证三道门槛`)
- 中文 UI 文案(`APP_TITLE = "YT 视频下载器"`)
- 中文 commit message(参考 `@init: yt-downloader v1.2.0 — 高清下载 + 准入验证 + 瑜伽预审`)
- 中文错误消息
- 标识符(变量名/函数名)用英文(`probe_result`,不是 `chaxunjieguo`)

**路径:**
- 绝对 Windows 路径优先(`F:\wkspace\yt-downloader`),不要 POSIX 路径(`/f/wkspace/...`)
- 仓库根用 `F:\wkspace\yt-downloader`,代码里要用相对路径(`Path(__file__).parent`)

**缩进:**
- Python: 4 空格(看现有文件,pyproject.toml 没强制 ruff 配置)
- batch: 不用缩进语法,顺序执行

**注释哲学:**
- 解释 **WHY**,不解释 WHAT
- 非显然的设计决策要写(`# Windows 任务栏自定义图标: 不显式设 AppUserModelID, 任务栏会回退显示 python.exe`)
- 业务规则的来源要写(`# 短边 ≥720px: 低于此主管线 upscale 不补细节`)
- 已有代码的注释不动,除非改的是注释本身

**import 顺序:**
- 标准库 → 第三方 → 本项目(`from . import config`)
- 现有文件遵循这个顺序

**测试:**
- 目前项目没有测试代码(grep `tests/` 是空的)
- 加测试时用 pytest,放 `tests/` 镜像包结构
- 不要为还没加测试的项目"假装"写测试

**Why:** 风格一致减少每次确认;不解释 WHAT 节省 token;中文 UI 是产品用户需要。
**How to apply:** 写新文件前先 `Read` 同目录的现有文件对齐风格;改现有文件时保留原作者注释风格。
