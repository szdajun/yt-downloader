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