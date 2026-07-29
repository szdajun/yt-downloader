# 📺 YT 视频下载器

一个桌面 GUI 下载器：粘贴 YouTube / 抖音 链接 → 自动选最高清 → 下载后 **自动验证准入门槛**（短边 ≥720px / 码率 ≥5Mbps / 时长 ≥30s），红绿提示这个视频**能不能直接用作健身主管线/A+C 换脸的源素材**。

底层用 [**yt-dlp**](https://github.com/yt-dlp/yt-dlp)（业界标准下载引擎）+ 已有的 ffmpeg 合流；界面用 [**PySide6 (Qt6)**](https://www.qt.io/)（原生控件、信号槽、QThread 线程模型）。

![流程](https://img.shields.io/badge/引擎-yt--dlp-red) ![GUI](https://img.shields.io/badge/GUI-PySide6-green)

---

## ✨ 功能

- **粘贴即下** — 粘贴 URL，选品质，一键下载最高清 mp4
- **准入门槛验证** — 下载完自动 ffprobe 读规格，对照三道门槛红绿显示：
  - 短边像素 **≥ 720**（低于此主管线 upscale 不补细节）
  - 码率 **≥ 5 Mbps**（低于此运动场景糊成色块）
  - 时长 **≥ 30s**（太短不够完播率）
- **详情面板** — 下载后展示分辨率 / 短边 / 时长 / 码率 / 编码 / 大小 + 准入标记，一目了然
- **▶ 播放** — 一键用系统默认播放器打开当前视频
- **✂ 裁剪 / 去广告** — 两种模式：① 取精华片段 `[起,止]`；② **删掉中间广告/赞助段**，自动拼接头尾。默认 ffmpeg 流拷贝（秒级），可选精确重编码（帧精确）
- **🧘 瑜伽预审** — 下载后抽样 9 帧缩略图 + 衣着人工清单，预筛抖音「衣着暴露」风险。本机有 fitness 仓库时可点窗内「深度体态扫描」跑 YOLO（详见下）
- **批量下载** — 每行一个 URL，依次下载并逐个验证
- **🔑 认证** — 绕 YouTube 机器人验证：Firefox 自动读 cookies，或用扩展导出 cookies.txt 文件（Chrome/Edge 必选）
- **🎵 抖音** — 同样支持抖音链接（`douyin.com/video/...`），用 Firefox 登录后默认下**无水印**干净源
- **设置记忆** — 输出目录 / 品质 / 验证开关 / 认证方式自动存到 `~/.yt-downloader/config.json`，下次打开恢复
- **格式预设** — 最高画质 / 1080p / 720p / 仅音频(m4a)
- **实时进度** — 进度条 + 速度 + 剩余时间 + ffmpeg 合流状态
- **纯本地** — 不上传任何数据，不花钱，不依赖云

---

## 🚀 快速开始

环境需要 [Python ≥3.11](https://www.python.org/)、[Node.js ≥22](https://nodejs.org/)（YouTube 反爬必需，见下）和 [uv](https://docs.astral.sh/uv/)。

### 方式一：双击启动（推荐）

双击 `run.bat`。首次启动 `uv` 会自动创建虚拟环境并安装依赖（约 1–2 分钟，联网一次），之后秒开。

### 方式二：命令行

```bash
cd F:\wkspace\yt-downloader
uv sync                      # 装依赖 (首次)
uv run python -m yt_downloader.app   # 启动 GUI
```

---

## 🛠 为什么需要 Node.js（YouTube 反爬）

YouTube 2025 起对第三方工具（含 yt-dlp）加了 **n-签名挑战**：视频流的 URL 签名必须用 JavaScript 运行时实时计算，否则拿不到任何清晰度（报「No video formats found」）。

- 本工具自动调用 **Node.js / Deno / Bun**（装了任一即可，优先级 deno > node > bun）解签名
- **没装任何 JS 运行时下载会失败**。最简单：装 [Node.js ≥22](https://nodejs.org/)（安装时勾选「Add to PATH」）
- 极少数高清视频还可能要求 **PO token**（另一层验证），日志会提示——按 [bgutil 文档](https://github.com/Brainfood/bgutil-ytdlp-pot-provider) 跑一个本地 server 即可，多数视频用不到

> 这是 YouTube 与开源社区持续对抗的反爬机制，非本工具能完全规避。跟着报错提示装 runtime / 跑 server 即可。

---

## 📖 用法

1. 复制一个 YouTube 视频链接（`https://www.youtube.com/watch?v=...`）
2. 点 **📋 粘贴**（或手动粘贴到 URL 框）
3. 选品质（默认「最高画质 (mp4)」）
4. 确认输出目录（默认 `下载\yt-downloader\`）
5. 点 **⬇ 下载** — 进度条跑完，记录区出现验证结果：

```
[✓ 达标]  30分钟燃脂操.mp4  1920×1080  5.8Mbps  1820s  (412.3MB)
[✗ 不达标] 尊巴片段.mp4  1280×720  3.2Mbps  1800s  (88.1MB)
           → 码率 3.2 < 5 Mbps  (建议换更高清源)
```

不达标的视频仍会保存，只是提示你它不适合作为源素材——换一个更高清/码率的版本。

### 批量

点 **☰ 批量**，弹窗里每行粘一个 URL，点「开始批量下载」，依次下载+验证。

### ♻ 重复下载同一个链接

文件已存在时，默认**跳过**（显示 `[⊘ 已存在, 跳过]`，直接验证现有文件，省流量、不产生重复大文件——与健身主管线「增量跳过」一致）。

需要重新拿一份新副本时，勾上**「强制重新下载」**：每次都重新下载，重名自动改名 `a(1).mp4`、`a(2).mp4`…，**旧文件保留不覆盖**。

### ▶ 播放

下载完成后点详情面板的 **▶ 播放**，用系统默认播放器打开当前视频。

### ✂ 裁剪 / 去广告

下载后点 **✂ 裁剪**，弹窗里输入起止秒数：

- **不勾**「去除中间片段」= **保留** `[起, 止]` 这段（取精华）
- **勾上**「去除中间片段」= **删掉** `[起, 止]`（去中间广告/赞助），自动把头尾拼起来
- 可先点 **▶ 预览原片** 用系统播放器定位广告的起止时间
- 默认**快速流拷贝**（秒级，接缝处关键帧对齐可能偏 ≤1s）；勾「精确模式」改为重编码（帧精确，慢）
- 产物命名：`<原名>_trim_10-20s.mp4`（保留）/ `<原名>_noad_30-40s.mp4`（去广告）

### 🧘 瑜伽预审（搬运前「衣着暴露」风险预筛）

韩系瑜伽搬运到抖音冲量后，常因「衣着暴露」被锁流量。下载后点详情面板 **🧘 瑜伽预审**：

1. **抽帧**（ffmpeg，秒级）— 自动均匀抽 9 帧缩略图弹窗
2. **人工衣着复核**（机器测不了，必须人眼）— 逐帧看 + 关窗后用 ▶ 看动片，勾三项风险：衣着 / 体态 / 镜头
3. **深度体态扫描**（可选，按钮只在**本机检测到 fitness-video-pipeline** 时出现）— 点了调 fitness 的 YOLO pose 自动判 PASS/CAUTION/REJECT（~30s）

> ⚠ **体态 REJECT ≠ 衣着有问题**。深度扫描测的是折叠/劈叉剪影密度（保守误报方向），抖音真正咬人的「衣着暴露」是衣着维度，必须人眼看动片。全绿才发，任意一项红 → 换源，别打码。

**轻量抽帧零新依赖**（下载器仍只靠 yt-dlp + ffmpeg + PySide6）；深度扫描借 fitness 的 venv 跑，不往下载器塞 torch。别的机器没有 fitness 仓库时，深度按钮不出现，只留轻量帧审。

### ⚙ 设置记忆

输出目录、品质、验证开关会**自动保存**（关闭时写入 `~/.yt-downloader/config.json`），下次打开自动恢复——换过一次下载目录就不用再设。

### 🔑 认证（绕过机器人验证）

YouTube 对未登录访问会弹「Sign in to confirm you're not a bot」，下载会被拦。下载器「认证」下拉三选一：

| 选项 | 适用 | 说明 |
|------|------|------|
| **无** | 少量下载、IP 未被标记 | 直接用，被拦了再换 |
| **Firefox（已登录）** | 最省事 | 先在 **Firefox 里登录 YouTube** 一次，选这项自动读取 cookies |
| **cookies.txt 文件** | 最通用最可靠（Chrome/Edge 用户必选） | 见下方 |

> ⚠ **Chrome / Edge** 因新版 cookie 加密（App-Bound / DPAPI），yt-dlp **读不出**，只能走 cookies.txt 文件。

**cookies.txt 怎么拿**（浏览器扩展导出）：

1. 在你登录 YouTube 的浏览器装扩展 **「Get cookies.txt LOCALLY」**（Chrome / Edge / Firefox 通用，免费开源）
2. 打开 `youtube.com`，点扩展图标 → **Export** → 存成 `youtube.com_cookies.txt`
3. 下载器「认证」选 **cookies.txt 文件…** →「浏览…」选刚存的文件 → 下载
4. cookies 会过期，失效后重新导出一次即可

首次下载若仍报 bot，多半是 cookies 过期、或没在该浏览器登录过 YouTube——重新导出 cookies.txt 再试。

---

## 🎵 抖音 (Douyin) 下载

也支持抖音链接，直接粘 `https://www.douyin.com/video/xxxxxxxx` 即可，引擎、认证、准入验证全部复用，**无需任何额外设置**。

**前置（一次性）**：
1. 在 **Firefox 里登录 douyin.com**（登录后能拿到更稳定、更高清的源；未登录也能下，但 cookies 容易过期报「Fresh cookies needed」）
2. 认证下拉选 **Firefox（已登录）**

**默认下无水印源**：抖音有「带水印下载」（`download_addr`）和「无水印播放源」（playback/direct）两种。本工具默认「最高画质」会自动选**无水印播放源**——下下来是干净的，没有 @用户名/抖音 logo 的跳动水印（已逐帧验证）。

**⚠ 抖音源的码率普遍不达标**：
抖音 CDN 压缩极狠，典型 720×1280 视频码率只有 **0.6–1.0 Mbps**，**远低于主管线 5 Mbps 准入门槛**。实测样本「低强度TABATA」：720×1280 hevc，**0.71 Mbps**，准入判 ✗（码率 0.7 < 5）。

所以抖音下载的实际用途是：
- ✅ 拿**无水印干净版**做参考/搬运/截取（不进主管线）
- ✗ 基本不能作为**健身主管线的高清源**（码率天花板就在那）

下载器会**如实按每个视频报达标/不达标**——遇到少数高清上传（1080p 2-3 Mbps）仍可能判 ✗，但至少你下载完立刻知道，不用瞎猜。

---

## 🎯 为什么有「准入门槛」？

健身短视频处理流水线（同作者的 `fitness-video-pipeline` 项目）对源素材有硬要求：

| 维度 | 门槛 | 原因 |
|------|------|------|
| 短边 | ≥ 720 px | 平台最低 720×1280；低于此主管线 upscale 补不出细节 |
| 码率 | ≥ 5 Mbps | 运动场景低于此会有明显压缩色块，传平台就糊 |
| 时长 | ≥ 30s | 太短不够完播率 |

录屏 / 短视频 APP 导出的低质源（典型 458×726、1.6 Mbps、10s）**三项全不达标**，硬上主管线浪费时间。这个下载器把「下载」和「验证能不能用」合在一起，下载完立刻知道。

---

## 📦 打包成单文件 exe（可选）

想分发给别人或脱离 Python 环境，用 PyInstaller 打包：

```bash
uv pip install pyinstaller
uv run pyinstaller --onefile --windowed --name "YT视频下载器" -m yt_downloader.app
# 产物在 dist/YT视频下载器.exe (PyInstaller 自带 PySide6 hook, 无需 --collect-all)
```

---

## ⚖️ 合规说明

本工具仅用于下载**你有权下载**的内容（自有视频、CC 许可、离线个人观看等）。请遵守 YouTube 服务条款与当地版权法。作者不对工具的滥用承担责任。

---

## 🗂️ 项目结构

```
yt-downloader/
├── pyproject.toml          # 依赖: yt-dlp + PySide6
├── run.bat                 # 双击启动
├── README.md
└── yt_downloader/
    ├── app.py              # GUI (PySide6/Qt) — 主窗口: 下载/进度/详情/播放/裁剪
    ├── workers.py          # QThread 后台 worker — 下载/批量/裁剪/瑜伽预审, 信号桥到主线程
    ├── dialogs.py          # 批量下载 / 裁剪 / 瑜伽预审 对话框
    ├── downloader.py       # yt-dlp 封装 — 选格式 + ffmpeg 合流 + 进度回调
    ├── verify.py           # ffprobe 准入门槛验证 (≥720/≥5Mbps/≥30s)
    ├── yoga_check.py       # 瑜伽预审 — ffmpeg 抽帧 + 检测 fitness venv + subprocess 深度扫描
    ├── trim.py             # ffmpeg 裁剪/去广告 (保留片段 或 删中段拼头尾)
    └── config.py           # 设置持久化 (~/.yt-downloader/config.json)
```
