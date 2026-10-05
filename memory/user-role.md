---
name: user-role
description: 用户是开发者兼使用方 — 改核心业务逻辑要主动说
metadata: 
  node_type: memory
  type: user
  originSessionId: 7ac65baf-4fef-4d86-a03a-3e2c6cb4e369
  modified: 2026-09-16T17:27:49.849Z
---

用户在这项目里的角色:**开发者兼使用方**。

**背景:**
- 项目代码是给健身主管线下游用的(`F:\wkspace\fitness-video-pipeline`),不是给别人发布的库
- 用户自己跑这个 GUI 下载视频做健身主管线的源素材,所以既写代码也用产品
- 主管线那边跑过 Claude 会话,跟本项目有接口契约(见 `downstream-pipeline`)

**协作偏好:**
- **四段式沟通** — 诊断 → 根因 → 修复 → 验证。用户不喜欢冗长解释,喜欢直奔结论
- **改核心业务逻辑要主动说** — `verify.py` 阈值、`app.py` 准入标记格式、`yoga_check.py` 输出结构、`config.py` 设置 schema,这些改一处会影响下游主管线静默失败,改前要跟用户打招呼
- **不解释显而易见的** — 像 `print(x)` 这种代码不需要解释 WHY,只解释非显然的设计决策
- **报错要带诊断数据** — 失败时除了说"哪里坏了",还要说"为什么坏 + 怎么验证修了",不要只贴 traceback
- **架构级改动先 spike 验证**(2026-09-17 确认) — 引入重依赖或改架构前,先用一次性脚本实测方案可行性,把结果拿给用户看,再决定要不要集成。用户明确选了"先 spike,验证通过再决定是否集成",理由是"避免先改架构结果发现也过不了风控"。别自作主张直接上架构

**Why:** 让 Claude 调整与用户的协作语气 — 别废话,别动核心逻辑不打招呼,别只给 traceback。
**How to apply:** 改 `yt_downloader/verify.py` / `app.py` / `yoga_check.py` / `config.py` 这四个文件前,先在响应里说"建议改 X,因为会影响 Y,行不行?"。
