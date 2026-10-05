# CLAUDE.md

Claude Code 项目级配置 — `F:\wkspace\yt-downloader` 自动加载。

## 项目身份

YouTube / 抖音 / Pornhub 视频下载器 GUI 桌面应用。四类关键依赖:
- **PySide6 (Qt6)** — 主窗口 + QThread 子线程模型
- **yt-dlp** — 下载引擎 + 格式协商
- **Node.js ≥22** — YouTube 2025+ n-challenge 签名求解器(必装,否则「No video formats found」)
- **curl_cffi** — Pornhub 分片下载(该 CDN 只放行带 Chrome TLS 指纹的客户端,见下)

业务核心:下载后 ffprobe 验证准入门槛(短边 ≥720px / 码率 ≥2Mbps / 时长 ≥30s)+ 瑜伽源衣着预审。产物是下游健身主管线 `F:\wkspace\fitness-video-pipeline` 的视频源。

## 架构速览

入口 `yt_downloader/app.py:main()`。包结构(11 个模块):

| 模块 | 职责 |
|---|---|
| `app.py` | 主窗口 + 入口(QMainWindow + 信号槽) |
| `downloader.py` | yt-dlp 封装 + 格式映射(FORMATS/AUDIO_SUFFIXES) + 抖音/Pornhub/YouTube 分流 |
| `douyin_browser.py` | 抖音浏览器取流(Playwright 驱动系统 Chrome/Edge, 绕抖音签名墙) |
| `pornhub.py` | Pornhub 取流(页面 flashvars 的 HLS + curl_cffi 分片, 绕 yt-dlp 的 PhantomJS 死路) |
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
| 跑测试 | `uv run pytest -q` |
| 打包单文件 exe | `uv run --extra pack pyinstaller --onefile --windowed yt_downloader/app.py` |
| 代码检查 | `uv run ruff check yt_downloader/` |

也可用 slash 命令:`/start-gui` `/test` `/build-exe` `/lint`。

## 必须装的运行时

| 工具 | 用途 | 缺了的症状 |
|---|---|---|
| **uv** | 虚拟环境 + 依赖管理 | `uv 不是内部或外部命令` — 见 run.bat 提示装 |
| **Python ≥3.11** | `requires-python` | 启动失败 |
| **Node.js ≥22** 或 Deno / Bun | YouTube n-challenge 签名求解 | 「No video formats found」 |
| **Chrome 或 Edge** | 抖音取流(Playwright 驱动, 跑抖音自己的签名 JS) | 「浏览器取流不可用」 |
| **ffmpeg** | 视频合流 / 裁剪 | 下载失败或合并阶段报错 |
| **ffprobe** | 准入门槛验证 | 验证阶段报 ffprobe not found |

## 记忆同步约定

项目记忆有**两份**,活的那份在仓库外:

| 位置 | 角色 |
|---|---|
| `~/.claude/projects/F--wkspace-yt-downloader/memory/` | **活文件** — Claude 读写的就是这里 |
| `<repo>/memory/` | **仓库内快照** — 纳入版本控制, 关机/换机不丢 |

约定(同 `fitness-video-pipeline`, 照抄即可):

- **写完记忆要同步** —— 单向, 活 → 仓库:
  `cp ~/.claude/projects/F--wkspace-yt-downloader/memory/*.md <repo>/memory/`
- 连同代码一起提交, 提交信息用 `@claude-env:` 前缀(与 docs/ 那类同)。
- 两侧**会漂移**: 仓库里那份是快照, 一切以 `~/.claude` 那份为准; 改了记忆不 sync, 仓库里的就是旧的。
- `MEMORY.md` 是索引 —— 每新增一条记忆要在里面加一行 `- [标题](file.md) — 一句话`, 索引本身也在同步范围内。
- 提交前扫一遍凭证:`grep -rniE 'sk-[a-z0-9]{10,}|api[_-]?key|token\s*[:=]|password' memory/`。
  (记忆里出现过 `?token=&lang=zh` 这种**空参数误报**, 属正常, 别当成泄露。)

## 本项目踩坑速查

**`chcp 65001 >nul` 与 `uv run` 不兼容。** 切换 UTF-8 码页会干扰 pyenv-win shim 的 stdio 缓冲,导致 `uv run python -m ...` 无输出挂起。run.bat 已经去掉这行,不要再加回来。

**同一 cmd session 调两次 `uv` 会挂。** pyenv-win shim 的已知问题 — 第一个 `uv` 调用 OK,第二个挂死(console handle 没释放)。run.bat / 脚本里 `uv` 只能调一次。

**pyenv-win shim 路径必须把 `D:\Python\.pyenv\pyenv-win\bin` 加到 PATH。** 否则 shim 内部 `pyenv exec uv` 找不到 `pyenv` 二进制,会报 `'pyenv' is not recognized`。run.bat 已经做 PATH 自愈,新增 uv 安装位置时改 run.bat 的 candidate 列表。

**YouTube 反爬必须 JS 运行时。** 装 Node.js ≥22 / Deno / Bun 任一即可,优先级 deno > node > bun。

**抖音 2026-09 起了签名墙, yt-dlp 升级无效。** `www.douyin.com/aweme/v1/web/aweme/detail/` 前置了 ArgusSecurityPlugin, 两道关卡: 缺 `Uifid` 请求头 → `Uifid Not Found`; 补上后缺 `a_bogus` 签名 → `Signature Not Found`。**带完整登录 cookie 也照样 403**, 所以 yt-dlp 那句 "Fresh cookies are needed" 是误导。yt-dlp 的 DouyinIE(含 master)两样都没实现, 故走 `douyin_browser.py` 用真实浏览器跑抖音自己的 JS。排查时别再花时间查 cookie / 升 yt-dlp。

**抖音必须直连(不能走代理)。** 抖音对非中国大陆 IP 地理封锁(web API 与 douyinvod CDN 均是)。本机 `HTTP(S)_PROXY` 指向境外节点, 故抖音路径一律 `proxy=""`, 浏览器加 `--no-proxy-server`。YouTube 反之必须走代理 —— 分流在 `_make_opts(direct=...)`。

**抖音源到不了旧的 5Mbps 门槛 → 2026-09-17 已下调到 2Mbps。** 抖音码率天花板就在那: 实测 1080p 档 2119~2898 kbps(容器实测 2.90 Mbps)、720p 档最高 1785。2.0 落在 **1785~2119 这个天然断层**里, 放行 1080p、挡住 720p —— 720p 的短边恰好是 720 能过分辨率门槛, 只能靠码率挡, 所以这个数直接决定下游拿到哪个档。⚠ 下游 `fitness-video-pipeline`(`CLAUDE.md` + `.claude/skills/coach-video-process/SKILL.md`)有同值硬门槛且「不达标直接放弃不硬上」, **两边必须同步改**, 否则这边判达标、下游丢掉, 下载白费。

**`.bat` 必须 CRLF 行尾。** cmd.exe 按字节偏移回读批处理文件,LF-only 的 run.bat 配上 `goto` 标签 + 括号块会让 cmd 算错偏移、回头把前面几行吃掉开头字符重执行(实测 7 个 `'tle' is not recognized` / `'/d' is not recognized`),后果是 `cd /d "%~dp0"` **静默失效**。已加 `.gitattributes` 锁 `*.bat text eol=crlf`。另注意:用 Python 读写 .bat 要 `read_bytes().decode()`,**别用 `read_text()`** —— 它默认换行归一,会把 CRLF 悄悄变回 LF。

**括号块内 `echo` 里的 `)` 是块结束符。** `if ... ( ... echo X (foo) ... )` 里那个 `)` 会被 cmd 当成 `if` 块的结束符,**开头的 `(` 不提供嵌套保护**:块被截断在该行,剩余行掉到顶层**无条件执行**。所以错误提示文案别放进 `if (...)` 块 —— 用 `if "%RC%"=="0" exit /b 0` 提前退出 + 平铺结构(与 uv-not-found 那段一致)。

**Pornhub 的 yt-dlp 提取器死在 PhantomJS, 别再查 cookie / 升 yt-dlp。** `PornHubIE` 依赖已停更的 PhantomJS 去重放一个反爬 JS 挑战(页面里的 `<body onload="go()">` + `document.cookie=...`), 本机没有也装不动 → 直接 `ERROR: [PornHub] PhantomJS not found`。`pornhub.py` 另起一条路: 抓页面里 `var flashvars_<n> = {...}` 的 `mediaDefinitions`, 取 `format: "hls"` 那条的 `master.m3u8`, 再经 ffmpeg 本地 remux。**`format: "mp4"` + `remote: true` 那条(`cn.pornhub.com/video/get_media`)是死路, 403, 直接丢。**

**Pornhub 四个实测坑(缺一个就 410/412):**
1. **CDN 认页面 session 的 cookie。** 分片请求必须带抓页面那次的 session cookie, 拿全新 session 去取同一个 m3u8 → `410 Gone`。
2. **页面 token 会失效。** 有些页面加载出的 HLS URL 是无 token 的(`validfrom=validto=0`), 取回来是 `412 request incorrect`。所以要**逐档位降级重试 + 失败就重抓页面换新 token**(`extract_pornhub` 里的 12 轮)。
3. **CDN 有每 IP 并发上限。** 8 路并发分片会随机 410, 3 路串行全 200 —— 用 4 并发 + 410/429/403 退避。`_CONCURRENCY = 4` 别往上调。
4. **ffmpeg 自己的 HTTP 栈过不了 CDN 检查** —— 同一个 URL curl_cffi 200、ffmpeg 410。所以**分片用 curl_cffi 落到本地文件**, 再把 playlist 改写成指向本地文件(`rewrite_local`), ffmpeg 只做 `-c copy` remux。curl_cffi 的 `impersonate="chrome"`(TLS 指纹)是唯一能过 CDN 的客户端。

**Pornhub 必须走代理(与抖音正好相反)。** 抖音 `proxy=""` 直连;Pornhub 走 `HTTP(S)_PROXY`。分流同样在 `_make_opts(direct=...)` 之外单开 `_download_pornhub`, 别把两者的代理设定搞混。

**Pornhub 产物只用 viewkey 命名(`{viewkey}.mp4` / `.m4a`)。** 敏感源, 标题一律不进文件名、不进对话、不进命令 —— 见 `content-filter-1301-handling` 约定。