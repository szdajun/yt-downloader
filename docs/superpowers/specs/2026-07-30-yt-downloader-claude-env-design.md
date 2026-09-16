# yt-downloader 项目 Claude 环境 — 设计文档
> ⚠️ **历史文档 — 阈值已变更 (2026-09-17)**  
> 本文写于 2026-07-30, 其中「码率 ≥5Mbps 准入门槛」已于 2026-09-17 下调为
> **≥2Mbps** (为适配抖音源: 抖音 1080p 档天花板实测 ~2.9Mbps, 旧门槛会把抖音源
> 全部拒掉)。当前生效值以 `CLAUDE.md` 与 `yt_downloader/verify.py` 的
> `THRESH_BITRATE` 为准。本文其余内容为当时记录, 原样保留。

**日期:** 2026-07-30
**状态:** 已批准,待实施
**范围:** 仅配置层 — 不改任何 Python 源码、pyproject、依赖锁。

---

## Context

`F:\wkspace\yt-downloader` 是一个 git 仓库(`main` 分支,目前一个 init commit),Python 3.11 + PySide6 的 YouTube/抖音 GUI 下载器。本次想给项目建立独立的 Claude Code 会话环境,这样任何新会话打开这个目录都会自动加载项目知识,而不是从零开始摸。

修复 run.bat 时已经发现这个项目有几条很有用的"踩坑知识"(chcp 65001 与 shim 冲突、back-to-back uv hang、pyenv-win PATH 自愈),不沉淀下来下次又会重蹈覆辙。

用户明确要"全做" — 项目级 CLAUDE.md + 项目 memory + `.claude/` 目录(permissions/env/slash commands)。

---

## 设计总览

四个交付物:

1. **`CLAUDE.md`** (项目根) — 项目身份、架构、常用命令、运行时依赖、本项目踩坑速查
2. **5 条项目 memory** + `MEMORY.md` 索引 — 结构化的事实/偏好记忆,写到 Claude Code 的项目 memory 目录
3. **`.claude/settings.json`** — Bash 白名单/拒名单 + 环境变量预设
4. **4 个 slash commands** — `/run`、`/test`、`/build-exe`、`/lint`

---

## 1. CLAUDE.md

路径: `F:\wkspace\yt-downloader\CLAUDE.md`
长度: 80-120 行
5 个一级章节:

### 1.1 项目身份(3-5 行)
一句话定位 + 三个关键依赖(PySide6 GUI、yt-dlp 引擎、Node.js ≥22 解 YouTube n-challenge)。

### 1.2 架构速览(15-20 行)
- 包结构:`yt_downloader/` 下 9 个模块,入口 `app.py:main()`
- 关键模块职责一行注解:
  - `app.py` — 主窗口 + 入口
  - `downloader.py` — yt-dlp 封装 + 格式映射
  - `verify.py` — ffprobe 准入门槛(720p / 5Mbps / 30s)
  - `workers.py` — QThread 子线程 + Qt Signal
  - `yoga_check.py` — 瑜伽源缩略图预审
  - 其他:`dialogs.py` `trim.py` `config.py` `assets/`
- 线程模型一句话:下载/批量/裁剪/预审在 QThread 子线程跑,信号回主线程。

### 1.3 常用命令(10-15 行)
- 启动 GUI:`run.bat` (双击或 `.\run.bat`)
- 装依赖:`uv sync`
- 跑测试:`uv run pytest -q` (目前没有,以后加)
- 打包 exe:`uv run pyinstaller --onefile --windowed yt_downloader/app.py`

### 1.4 必须装的运行时(8-10 行)
表格列出 Node.js ≥22 / ffmpeg / ffprobe / uv 各自的用途与安装提示,以及各自的失败症状(YouTube 「No video formats found」/ 合流失败 / 准入验证报错 / 「uv 不是内部或外部命令」)。

### 1.5 本项目踩坑速查(20-30 行,每条 2-4 行)
- `chcp 65001` 与 `uv run` 不兼容 — 会让 shim stdio 缓冲挂起
- 同一 cmd session 调两次 `uv run` 会挂 — pyenv-win shim 的已知问题,bat/脚本里 uv 只调一次
- pyenv-win shim 路径(`D:\Python\pyenv\pyenv-win\shims\uv.exe`)必须把 `D:\Python\pyenv\pyenv-win\bin` 加到 PATH,否则 `pyenv exec` 找不到
- YouTube 反爬必须用 Node.js / Deno / Bun 解 n-challenge 签名 — 没装会「No video formats found」

---

## 2. 项目 memory(5 条 + 索引)

目录: `C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\`

### 2.1 `MEMORY.md`(索引,4-6 行)
每行一条 `- [Title](file.md) — hook`,作为 Claude Code 启动时的召回索引。

### 2.2 `project-scope.md`(type: project)
**Why:** 让任何会话快速明白这项目的边界与「不能拍脑袋改」的地方。
**内容要点:**
- 一句话定位:YouTube/抖音 GUI 下载器,主管线入口是 PySide6
- 准入门槛三阈值是核心业务逻辑(720p/5Mbps/30s),改前必须说
- 瑜伽预审是给健身主管线筛「衣着暴露」风险的,跟下载器主流程独立但耦合
- 下游消费者是 `F:\wkspace\fitness-video-pipeline`,产物要兼容它那边的解析

### 2.3 `run-bat-pitfalls.md`(type: project)
**Why:** 这次修复踩过的坑,沉淀给下次。
**内容要点:**
- `chcp 65001 >nul` 与 `uv run` 不兼容(会让 shim stdio 缓冲挂起)
- 同一 cmd session 调两次 `uv run` 会挂(只调一次)
- pyenv-win shim 必须把 `D:\Python\pyenv\pyenv-win\bin` 加 PATH(否则 `pyenv exec` 找不到)
- YouTube 反爬必须 Node.js / Deno / Bun
- run.bat 已自定位 uv 路径 + PATH 自愈,新增沙箱安装位置时改 run.bat 的 candidate 列表

### 2.4 `user-role.md`(type: user)
**Why:** 让 Claude 调整与用户的协作语气。
**内容要点:**
- 你是开发者兼使用方,代码是给健身主管线下游用的,不是给别人发布的库
- 改了核心业务逻辑(下载/验证/瑜伽阈值)要主动说明影响面
- 你不喜欢冗长解释,偏好"诊断 → 根因 → 修复 → 验证"四段式

### 2.5 `code-style.md`(type: feedback)
**Why:** 风格一致,减少每次重复确认。
**内容要点:**
- 中文注释 + 中文 UI 文案(产品是中文用户)
- 中文 commit message(参考 `@init: yt-downloader v1.2.0 — 高清下载 + 准入验证 + 瑜伽预审`)
- Windows 路径优先(`F:\wkspace\...`)
- 缩进遵循现有文件风格
- 注释解释 WHY 而非 WHAT

### 2.6 `downstream-pipeline.md`(type: reference)
**Why:** 让 Claude 知道这个项目跟主管线怎么衔接,改一处要看另一处。
**内容要点:**
- 下游:`F:\wkspace\fitness-video-pipeline`(`fitness-video-pipeline` 会话跑过)
- 接口契约:输出目录约定(默认 `~/Downloads/yt-downloader/`,可在设置里改)+ 文件命名约定 + 准入标记格式 `[✓ 达标]` / `[✗ 不达标]`
- 瑜伽预审缩略图位置:`<output>/<title>.frames/frame_NN.jpg`
- 改输出/标记格式前要同步更新主管线那边的解析

---

## 3. `.claude/settings.json`

路径: `F:\wkspace\yt-downloader\.claude\settings.json`

### 3.1 内容
```jsonc
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

### 3.2 关键决策
- `UV_LINK_MODE=copy`:`F:` 盘与 uv cache 跨盘符,hardlink 失败会每次都全拷,显式用 copy 更稳定
- `QT_AUTO_SCREEN_SCALE_FACTOR=1`:高分屏自动缩放避免 Qt 控件过小/过大
- 不放 `Write`/`Edit`/`Agent` 到 allow — Claude Code 自己的权限 UI 已足够
- deny 只挡最危险的几个,白名单之外的命令走默认交互

---

## 4. Slash commands(4 个)

目录: `F:\wkspace\yt-downloader\.claude\commands\`

每个文件 frontmatter `description:` 一行,正文用 Bash 工具调一条命令。

### 4.1 `run.md`
```
description: 启动 GUI(等同 run.bat)
```
内容:`cd F:\wkspace\yt-downloader && .\run.bat`

### 4.2 `test.md`
```
description: 跑测试(以后加了测试用)
```
内容:`cd F:\wkspace\yt-downloader && uv run pytest -q`

### 4.3 `build-exe.md`
```
description: 打成单文件 exe
```
内容:`cd F:\wkspace\yt-downloader && uv run pyinstaller --onefile --windowed yt_downloader/app.py`

### 4.4 `lint.md`
```
description: ruff 检查
```
内容:`cd F:\wkspace\yt-downloader && uv run ruff check yt_downloader/`

---

## 5. `.gitignore` 追加

路径: `F:\wkspace\yt-downloader\.gitignore`

追加一行:
```
.claude/settings.local.json
```

---

## 实施顺序(4 步)

1. 写 `CLAUDE.md`(先写最大的,后续 memory/settings 引用其术语)
2. 写 5 条 memory + `MEMORY.md` 索引
3. 写 `.claude/settings.json` + 4 个 slash commands
4. `.gitignore` 追加 + `git add` + `git commit -m "@claude-env: CLAUDE.md + .claude/ 配置 + 项目 memory"`

注意:memory 文件(`C:\Users\18091\.claude\projects\F--wkspace-yt-downloader\memory\`)在仓库目录之外,**不**进 git。

---

## 验证

| 验证项 | 怎么测 | 期望 |
|---|---|---|
| CLAUDE.md 自动加载 | 退出会话,新开会话,问"这项目是干什么的" | Claude 答出 YouTube/抖音 GUI 下载器 + 三个关键依赖 |
| Memory 召回 | 新会话问"run.bat 有什么坑" | 引用 `run-bat-pitfalls.md` 的要点(chcp / back-to-back / pyenv PATH) |
| Slash 命令 | 新会话输 `/run` | 触发 `run.bat`,GUI 弹出 |
| Bash 白名单 | 新会话跑 `uv --version` | 不弹权限确认,直接执行 |
| 危险命令拦截 | 跑 `rm -rf F:\test` | 被拒(deny 命中) |
| Git 提交 | `git status` | 新增 `CLAUDE.md` + `.claude/` 在版本内;memory 不在 git 里 |

---

## 不在范围

- 不改 Python 源码、pyproject、依赖锁、run.bat
- 不加 subagent / hooks / pre-commit 钩子(过度工程,本项目是单 GUI 应用)
- 不在 CLAUDE.md 里塞全部细节(只放指针,详情 → memory / 外部文档)