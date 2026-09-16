# yt-downloader 项目 Claude 环境 Implementation Plan
> ⚠️ **历史文档 — 阈值已变更 (2026-09-17)**  
> 本文写于 2026-07-30, 其中「码率 ≥5Mbps 准入门槛」已于 2026-09-17 下调为
> **≥2Mbps** (为适配抖音源: 抖音 1080p 档天花板实测 ~2.9Mbps, 旧门槛会把抖音源
> 全部拒掉)。当前生效值以 `CLAUDE.md` 与 `yt_downloader/verify.py` 的
> `THRESH_BITRATE` 为准。本文其余内容为当时记录, 原样保留。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `F:\wkspace\yt-downloader` 建立完整的 Claude Code 项目级环境 — CLAUDE.md + 5 条项目 memory + `.claude/settings.json`(白名单/env)+ 4 个 slash commands + `.gitignore` 配套 + git commit。

**Architecture:** 纯配置层,不动 Python 源码。文件分为三类:仓库根的 `CLAUDE.md`(自动加载)、Claude Code 的项目 memory 目录(在仓库外,跨会话召回)、`.claude/` 目录(settings.json 权限/env、commands/ 下的 4 个 slash command 文件)。所有 memory 文件不进 git,所有含 token 的配置 `.gitignore` 排除。

**Tech Stack:** Markdown / JSON / Windows batch(`run.bat` 不动)。无新依赖。

---

## Global Constraints

- 不改 Python 源码、不改 `pyproject.toml` / `uv.lock` / `run.bat` / `yt_downloader/`
- 项目根: `F:\wkspace\yt-downloader`
- 项目 memory 目录: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\`(仓库外,不进 git)
- 配置文件路径用绝对 Windows 路径(`F:\wkspace\yt-downloader\...`)
- 编码: UTF-8,不带 BOM
- 中文 UI 文案 / 中文 commit message / 中文注释(本项目是中文用户产品)
- CLAUDE.md 文件长度: 80-120 行
- memory 每条 30-80 行,带 frontmatter(`name` / `description` / `type`) + **Why:** / **How to apply:** 段
- MEMORY.md 是索引,无 frontmatter,每条 `- [Title](file.md) — hook` 一行
- 含 token 的文件 `.gitignore` 排除:`.claude/glm.json`(已存在)+ `.claude/settings.local.json`
- 提交粒度:每个 Task 单独 commit;commit message 中文,格式 `<scope>: <说明>`,沿用 `@init:` 前缀的现有风格(`@claude-env:`)

---

## Task 1: 写 CLAUDE.md

**Files:**
- Create: `F:\wkspace\yt-downloader\CLAUDE.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入 `F:\wkspace\yt-downloader\CLAUDE.md`,内容如下(整体长度约 100 行):

```markdown
# CLAUDE.md

Claude Code 项目级配置 — `F:\wkspace\yt-downloader` 自动加载。

## 项目身份

YouTube / 抖音视频下载器 GUI 桌面应用。三类关键依赖:
- **PySide6 (Qt6)** — 主窗口 + QThread 子线程模型
- **yt-dlp** — 下载引擎 + 格式协商
- **Node.js ≥22** — YouTube 2025+ n-challenge 签名求解器(必装,否则「No video formats found」)

业务核心:下载后 ffprobe 验证准入门槛(短边 ≥720px / 码率 ≥5Mbps / 时长 ≥30s)+ 瑜伽源衣着预审。产物是下游健身主管线 `F:\wkspace\fitness-video-pipeline` 的视频源。

## 架构速览

入口 `yt_downloader/app.py:main()`。包结构(9 个模块):

| 模块 | 职责 |
|---|---|
| `app.py` | 主窗口 + 入口(QMainWindow + 信号槽) |
| `downloader.py` | yt-dlp 封装 + 格式映射(FORMATS/AUDIO_SUFFIXES) |
| `verify.py` | ffprobe 准入门槛(ProbeResult + probe()) |
| `workers.py` | QThread 子线程 + Qt Signal(BatchWorker / DownloadWorker / TrimWorker / YogaFrameWorker / DeepCheckWorker) |
| `dialogs.py` | 弹窗(BatchDialog / TrimDialog / YogaReviewDialog) |
| `trim.py` | 视频裁剪(流拷贝 / 精确重编码两种模式) |
| `yoga_check.py` | 瑜伽源缩略图预审(fitness_env) |
| `config.py` | 设置持久化(`~/.yt-downloader/config.json`) |
| `assets/` | 图标等静态资源 |

线程模型:下载/批量/裁剪/预审在 QThread 子线程跑,进度/完成/错误经 Qt Signal 回主线程。**不**轮询 queue,跨线程自动 QueuedConnection。

## 常用命令

| 用途 | 命令 |
|---|---|
| 启动 GUI(双击) | `F:\wkspace\yt-downloader\run.bat` |
| 装依赖(首次) | `cd F:\wkspace\yt-downloader && uv sync` |
| 跑测试 | `uv run pytest -q`(目前没有,以后加) |
| 打包单文件 exe | `uv run pyinstaller --onefile --windowed yt_downloader/app.py` |
| 代码检查 | `uv run ruff check yt_downloader/`(以后加 ruff) |

也可用 slash 命令:`/run` `/test` `/build-exe` `/lint`。

## 必须装的运行时

| 工具 | 用途 | 缺了的症状 |
|---|---|---|
| **uv** | 虚拟环境 + 依赖管理 | `uv 不是内部或外部命令` — 见 run.bat 提示装 |
| **Python ≥3.11** | `requires-python` | 启动失败 |
| **Node.js ≥22** 或 Deno / Bun | YouTube n-challenge 签名求解 | 「No video formats found」 |
| **ffmpeg** | 视频合流 / 裁剪 | 下载失败或合并阶段报错 |
| **ffprobe** | 准入门槛验证 | 验证阶段报 ffprobe not found |

## 本项目踩坑速查

**`chcp 65001 >nul` 与 `uv run` 不兼容。** 切换 UTF-8 码页会干扰 pyenv-win shim 的 stdio 缓冲,导致 `uv run python -m ...` 无输出挂起。run.bat 已经去掉这行,不要再加回来。

**同一 cmd session 调两次 `uv` 会挂。** pyenv-win shim 的已知问题 — 第一个 `uv` 调用 OK,第二个挂死(console handle 没释放)。run.bat / 脚本里 `uv` 只能调一次。

**pyenv-win shim 路径必须把 `D:\Python\pyenv\pyenv-win\bin` 加到 PATH。** 否则 shim 内部 `pyenv exec uv` 找不到 `pyenv` 二进制,会报 `'pyenv' is not recognized`。run.bat 已经做 PATH 自愈,新增 uv 安装位置时改 run.bat 的 candidate 列表。

**YouTube 反爬必须 JS 运行时。** 装 Node.js ≥22 / Deno / Bun 任一即可,优先级 deno > node > bun。
```

- [ ] **Step 2: 校验**

```powershell
Get-Content "F:\wkspace\yt-downloader\CLAUDE.md" | Measure-Object -Line
```
期望:行数在 80-120 之间。中文不丢(`Get-Content` 默认 UTF-8)。

- [ ] **Step 3: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add CLAUDE.md
git commit -m "@claude-env: CLAUDE.md — 项目身份 / 架构 / 命令 / 踩坑速查"
```

---

## Task 2: 写 MEMORY.md(索引)

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\MEMORY.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入 `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\MEMORY.md`,内容如下:

```markdown
- [项目身份与边界](project-scope.md) — YouTube/抖音 GUI,下游是 fitness-video-pipeline,验证阈值是核心业务逻辑
- [run.bat 修复踩坑](run-bat-pitfalls.md) — chcp 65001 兼容、shim hang、pyenv PATH 自愈、JS 运行时依赖
- [用户角色与协作偏好](user-role.md) — 开发者兼使用方,改核心业务逻辑要主动说明
- [代码风格约定](code-style.md) — 中文注释/UI/Commit、Win 路径、注释解释 WHY
- [下游主管线接口契约](downstream-pipeline.md) — 输出目录、准入标记、瑜伽缩略图位置
```

- [ ] **Step 2: 校验**

```powershell
Get-Content "C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\MEMORY.md"
```
期望:5 行 `- [Title](file.md) — hook`,无 frontmatter。

- [ ] **Step 3:** 本任务无 git commit(文件在仓库外)。

---

## Task 3: 写 `project-scope.md`

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\project-scope.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入,内容:

```markdown
---
name: project-scope
description: yt-downloader 项目身份与业务边界 — 下游是 fitness-video-pipeline,准入门槛和瑜伽预审是核心
metadata:
  type: project
---

yt-downloader 是 YouTube / 抖音视频下载器 GUI 桌面应用。Python 3.11 + PySide6 (Qt6) + yt-dlp + Node.js。

**业务核心:**
- **准入门槛** — 下载完用 ffprobe 读规格,对三道门槛红绿提示:短边 ≥720px / 码率 ≥5Mbps / 时长 ≥30s。这三阈值是**核心业务逻辑**,给健身主管线筛「能不能直接用」的源素材。改前必须跟用户确认影响面。
- **瑜伽预审** — 抽 9 帧缩略图 + 衣着人工清单,预筛抖音「衣着暴露」风险。本机有 fitness 仓库时可点「深度体态扫描」跑 YOLO。
- **下游消费者** — `F:\wkspace\fitness-video-pipeline`。本项目的产物(下载的视频 + 准入标记 + 瑜伽缩略图)被主管线消费做后续 A+C 换脸/裁剪/合流。改输出格式/标记格式/文件命名都要同步主管线那边的解析。

**不在范围:**
- 不是给别人发布的库(不维护 API 兼容、不写 changelog)
- 不是云服务(纯本地)
- 不是 macOS / Linux 应用(用户是 Windows,UI 文案中文)

**Why:** 让任何会话快速明白这项目的边界与「不能拍脑袋改」的地方,避免改了阈值/标记格式导致下游主管线静默失败。
**How to apply:** 改 `yt_downloader/verify.py` 阈值 / `yt_downloader/app.py` 标记格式 / `yt_downloader/yoga_check.py` 输出结构时,先看这条 memory 再决定。
```

- [ ] **Step 2:** 无 git(仓库外)。

---

## Task 4: 写 `run-bat-pitfalls.md`

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\run-bat-pitfalls.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入,内容:

```markdown
---
name: run-bat-pitfalls
description: run.bat 修复发现的踩坑 — chcp/shim hang/pyenv PATH/JS 运行时
metadata:
  type: project
---

run.bat 在 2026-07-30 重写过。这次修复发现的、本项目特有的坑:

**1. `chcp 65001 >nul` 与 `uv run` 不兼容。**
切换 UTF-8 码页会干扰 pyenv-win shim 的 stdio 缓冲,导致 `uv run python -m ...` 跑出 `uv` + `python` 子进程但**无 stdout/stderr 输出**,Qt GUI 起来了但控制台看不到任何东西。run.bat 已经去掉,不要再加回来。如需中文 UI,在 Python 层用 UTF-8 即可,不依赖 cmd 码页。

**2. 同一 cmd session 调两次 `uv` 会挂。**
pyenv-win shim 的已知问题:第一个 `uv` 调用正常,第二个挂死(console handle 没释放,后续 shim 调用阻塞)。验证:`_probe7.bat` 三次连续 `uv run python -c "print(...)"` — 只有第一次有输出。所以 run.bat / 启动脚本里 `uv` 只能调一次。

**3. pyenv-win shim 路径必须把 `D:\Python\pyenv\pyenv-win\bin` 加到 PATH。**
pyenv-win shim 实际是 45 字节的 proxy,内部 `call pyenv exec uv %*`。如果 PATH 里只有 shim 目录(`D:\Python\pyenv\pyenv-win\shims`)而没有 bin 目录(`D:\Python\pyenv\pyenv-win\bin`),会报 `'pyenv' is not recognized as an internal or external command`。run.bat 已经做 PATH 自愈:找到 uv 后把 `%UV_DIR%;D:\Python\pyenv\pyenv-win\bin` 加到 PATH。

**4. YouTube 反爬必须 Node.js / Deno / Bun。**
YouTube 2025+ 对第三方工具加了 n-challenge 签名,没有 JS 运行时解签名 → 「No video formats found」。README 已写明,用户必须装 ≥22。

**5. pyenv-win shim 文件名是裸 `uv`,不是 `uv.exe`。**
`D:\Python\pyenv\pyenv-win\shims\uv`(45 字节)+ `uv.bat`(53 字节)。`if exist ...uv.exe` 会判 false,probe 列表里既要 `uv.exe` 也要裸 `uv`。

**6. ffmpeg/ffprobe 必须装。**
ffmpeg 做合流 + 裁剪,ffprobe 做准入验证。缺一个都会让某一步失败。WinGet 装 `Gyan.FFmpeg` 是最方便的方式。

**Why:** 下次任何人改 run.bat / 加新启动脚本 / 调试启动问题,会重新踩这些坑。
**How to apply:** 改 run.bat 时不要加 `chcp`;新增启动入口时确保 `uv` 只调一次 + PATH 自愈;排查「uv 不是内部或外部命令」先看 PATH 里有没有 `D:\Python\pyenv\pyenv-win\bin`。
```

- [ ] **Step 2:** 无 git。

---

## Task 5: 写 `user-role.md`

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\user-role.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入,内容:

```markdown
---
name: user-role
description: 用户是开发者兼使用方 — 改核心业务逻辑要主动说
metadata:
  type: user
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

**Why:** 让 Claude 调整与用户的协作语气 — 别废话,别动核心逻辑不打招呼,别只给 traceback。
**How to apply:** 改 `yt_downloader/verify.py` / `app.py` / `yoga_check.py` / `config.py` 这四个文件前,先在响应里说"建议改 X,因为会影响 Y,行不行?"。
```

- [ ] **Step 2:** 无 git。

---

## Task 6: 写 `code-style.md`

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\code-style.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入,内容:

```markdown
---
name: code-style
description: 代码风格约定 — 中文注释/UI/Commit、Win 路径、注释解释 WHY
metadata:
  type: feedback
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
```

- [ ] **Step 2:** 无 git。

---

## Task 7: 写 `downstream-pipeline.md`

**Files:**
- Create: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\downstream-pipeline.md`

- [ ] **Step 1: 创建文件**

用 Write 工具写入,内容:

```markdown
---
name: downstream-pipeline
description: 下游主管线 fitness-video-pipeline 怎么消费本项目的产物 — 接口契约
metadata:
  type: reference
---

下游主管线: `F:\wkspace\fitness-video-pipeline`(单独的 Claude Code 会话跑过)。

**接口契约:**

**输出目录:** 默认 `C:\Users\18091\Downloads\yt-downloader\`,可在 GUI 设置里改(写到 `~/.yt-downloader/config.json` 的 `output_dir`)。主管线扫这个目录(默认路径)找新下载的视频。

**文件命名:** yt-dlp 自动命名 — `<title>.mp4` / `<title>.<ext>`,非法字符被 yt-dlp 转义。主管线按文件扩展名识别,不依赖具体命名。

**准入标记格式:**
- 通过:`[✓ 达标]  <文件名>  <分辨率>  <码率>  <时长>  (<大小>)`
- 不通过:`[✗ 不达标]  <文件名>  <分辨率>  <码率>  <时长>  (<大小>)` + `→ <不达标原因>`
- 这些标记写在 GUI 日志区(`QTextEdit`),主管线目前是**手工读日志**判准入,不是机器解析

**瑜伽预审缩略图位置:** `<output>/<video_title>.frames/frame_NN.jpg`(N 从 1 到 9)。主管线后续会读这 9 张图做衣着暴露检测。

**ffprobe 验证输出:** GUI 显示用,不导出文件。主管线要重新跑 ffprobe 自己读。

**修改红线:**
- 改 `[✓ 达标]` / `[✗ 不达标]` 标记格式 → 主管线那边的人工审核流程可能误判
- 改瑜伽缩略图命名(`frame_NN.jpg` → `thumb_NN.jpg`)→ 主管线那边的脚本读不到
- 改输出目录默认值 → 主管线那边白跑
- 改 `config.json` schema(`output_dir` 字段名) → 用户 GUI 设置失效

**Why:** 让 Claude 知道这项目跟主管线怎么衔接,改一处要看另一处,避免主管线静默失败(主管线跑完才报错,定位难)。
**How to apply:** 改 `app.py` 日志格式 / `yoga_check.py` 缩略图命名 / `config.py` 默认值 / `config.py` schema 前,先看这条 memory 再决定;改完跟用户同步「主管线那边要不要跟改」。
```

- [ ] **Step 2:** 无 git。

---

## Task 8: 写 `.claude/settings.json`

**Files:**
- Create: `F:\wkspace\yt-downloader\.claude\settings.json`

- [ ] **Step 1: 创建文件**

用 Write 工具写入:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(uv *)",
      "Bash(git *)",
      "Bash(ffmpeg *)",
      "Bash(ffprobe *)",
      "Bash(node *)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(git push --force *)",
      "Bash(uv pip install --break-system-packages *)"
    ]
  },
  "env": {
    "PYTHONIOENCODING": "utf-8",
    "UV_LINK_MODE": "copy",
    "QT_AUTO_SCREEN_SCALE_FACTOR": "1"
  }
}
```

**注:** `UV_LINK_MODE=copy` 是因为 `F:` 盘与 uv cache 跨盘符,hardlink 失败;`QT_AUTO_SCREEN_SCALE_FACTOR=1` 让 PySide6 在高分屏上正确缩放。

- [ ] **Step 2: 校验 JSON 合法**

```powershell
Get-Content "F:\wkspace\yt-downloader\.claude\settings.json" -Raw | ConvertFrom-Json
```
期望:无错误,输出对象。

- [ ] **Step 3: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add .claude/settings.json
git commit -m "@claude-env: settings.json — Bash 白名单/拒名单 + Qt/uv/PythonIO env"
```

---

## Task 9: 写 4 个 slash commands

**Files:**
- Create: `F:\wkspace\yt-downloader\.claude\commands\run.md`
- Create: `F:\wkspace\yt-downloader\.claude\commands\test.md`
- Create: `F:\wkspace\yt-downloader\.claude\commands\build-exe.md`
- Create: `F:\wkspace\yt-downloader\.claude\commands\lint.md`

- [ ] **Step 1: 写 `run.md`**

```markdown
---
description: 启动 GUI(等同 run.bat)
---

cd F:\wkspace\yt-downloader && .\run.bat
```

- [ ] **Step 2: 写 `test.md`**

```markdown
---
description: 跑测试(以后加了测试用)
---

cd F:\wkspace\yt-downloader && uv run pytest -q
```

- [ ] **Step 3: 写 `build-exe.md`**

```markdown
---
description: 打成单文件 exe
---

cd F:\wkspace\yt-downloader && uv run pyinstaller --onefile --windowed yt_downloader/app.py
```

- [ ] **Step 4: 写 `lint.md`**

```markdown
---
description: ruff 检查(以后加 ruff 后用)
---

cd F:\wkspace\yt-downloader && uv run ruff check yt_downloader/
```

- [ ] **Step 5: 校验 4 个文件都存在**

```powershell
Test-Path F:\wkspace\yt-downloader\.claude\commands\run.md
Test-Path F:\wkspace\yt-downloader\.claude\commands\test.md
Test-Path F:\wkspace\yt-downloader\.claude\commands\build-exe.md
Test-Path F:\wkspace\yt-downloader\.claude\commands\lint.md
```
期望:4 个都是 `True`。

- [ ] **Step 6: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add .claude/commands/
git commit -m "@claude-env: 4 个 slash commands — /run /test /build-exe /lint"
```

---

## Task 10: 确认 `.gitignore` 已包含 `.claude/glm.json` 和 `.claude/settings.local.json`

**Files:**
- Read: `F:\wkspace\yt-downloader\.gitignore`

- [ ] **Step 1: 校验 .gitignore 已包含必要条目**

读 `.gitignore`,确认最后几行包含:
```
# Claude Code local config (API tokens, machine-specific overrides)
.claude/glm.json
.claude/settings.local.json
```
(在上一轮已加;如果 git status 显示 `.claude/glm.json` 是 untracked,说明漏了,需要再追加。)

- [ ] **Step 2: 验证 git status 正确**

```bash
cd "F:/wkspace/yt-downloader" && git status --short
```
期望:
- `.claude/settings.json` 是 modified/added(刚 commit 过 → 无)
- `.claude/commands/*` 是 added(刚 commit 过 → 无)
- `.claude/glm.json` **不在** untracked 列表里
- `.claude/settings.local.json` **不在** untracked 列表里(此文件不存在,但 .gitignore 排除规则仍生效)

如果 `.claude/glm.json` 出现在 untracked,回到 Step 1 修 .gitignore。

---

## Task 11: 端到端验证

**Files:** 不创建新文件,只验证。

- [ ] **Step 1: 校验最终目录结构**

```powershell
Get-ChildItem F:\wkspace\yt-downloader -Force | Select-Object Name, Mode
```
期望:有 `CLAUDE.md`、`.claude/`、`docs/`、`yt_downloader/`、`run.bat` 等。

```powershell
Get-ChildItem F:\wkspace\yt-downloader\.claude -Force | Select-Object Name, Mode
```
期望:`glm.json`(已在)、`settings.json`、`commands/` 子目录。

```powershell
Get-ChildItem C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory | Select-Object Name
```
期望:`MEMORY.md` + 5 个 .md 文件(`project-scope.md`、`run-bat-pitfalls.md`、`user-role.md`、`code-style.md`、`downstream-pipeline.md`)。

- [ ] **Step 2: 校验 git 历史**

```bash
cd "F:/wkspace/yt-downloader" && git log --oneline -5
```
期望:看到本次新增的 `@claude-env:` commits(CLAUDE.md / settings.json / commands/)。`glm.json` **不**在 git 里。

- [ ] **Step 3: 校验 CLAUDE.md 大小合理**

```powershell
(Get-Content F:\wkspace\yt-downloader\CLAUDE.md | Measure-Object -Line).Lines
```
期望:80-120 行。

- [ ] **Step 4: 提交最终状态(如还有未提交的文件)**

如果有未提交的文件(比如发现 .gitignore 漏改):
```bash
cd "F:/wkspace/yt-downloader"
git status --short
git add .gitignore  # 视情况
git commit -m "@claude-env: .gitignore 排除 glm.json 与 settings.local.json"
```

---

## Verification matrix

| 验证项 | 怎么测 | 期望 |
|---|---|---|
| CLAUDE.md 自动加载 | 退出会话,新开会话,问"这项目是干什么的" | Claude 答出 YouTube/抖音 GUI 下载器 + 三个关键依赖 |
| Memory 召回 | 新会话问"run.bat 有什么坑" | 引用 `run-bat-pitfalls.md` 的要点(chcp / back-to-back / pyenv PATH) |
| Slash 命令 | 新会话输 `/run` | 触发 `run.bat`,GUI 弹出 |
| Bash 白名单 | 新会话跑 `uv --version` | 不弹权限确认,直接执行 |
| 危险命令拦截 | 跑 `rm -rf F:\test` | 被拒(deny 命中) |
| Git 提交 | `git status` | 新增 `CLAUDE.md` + `.claude/settings.json` + `.claude/commands/` 在版本内;memory + glm.json 不在 git 里 |

---

## 不在范围

- 不改 Python 源码、pyproject、依赖锁、run.bat
- 不加 subagent / hooks / pre-commit 钩子(过度工程,本项目是单 GUI 应用)
- 不在 CLAUDE.md 里塞全部细节(只放指针,详情 → memory / 外部文档)
- 不动 `.claude/glm.json`(已存在,且已 .gitignore)