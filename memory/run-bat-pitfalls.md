---
name: run-bat-pitfalls
description: run.bat 修复发现的踩坑 — chcp/shim hang/pyenv PATH/JS 运行时/CRLF/块内括号
metadata: 
  node_type: memory
  type: project
  originSessionId: 7ac65baf-4fef-4d86-a03a-3e2c6cb4e369
  modified: 2026-09-16T18:00:54.153Z
---

run.bat 在 2026-07-30 重写过。这次修复发现的、本项目特有的坑:

**1. `chcp 65001 >nul` 与 `uv run` 不兼容。**
切换 UTF-8 码页会干扰 pyenv-win shim 的 stdio 缓冲,导致 `uv run python -m ...` 跑出 `uv` + `python` 子进程但**无 stdout/stderr 输出**,Qt GUI 起来了但控制台看不到任何东西。run.bat 已经去掉,不要再加回来。如需中文 UI,在 Python 层用 UTF-8 即可,不依赖 cmd 码页。

**2. 同一 cmd session 调两次 `uv` 会挂。**
pyenv-win shim 的已知问题:第一个 `uv` 调用正常,第二个挂死(console handle 没释放,后续 shim 调用阻塞)。验证:`_probe7.bat` 三次连续 `uv run python -c "print(...)"` — 只有第一次有输出。所以 run.bat / 启动脚本里 `uv` 只能调一次。

**3. pyenv-win shim 路径必须把 `D:\Python\.pyenv\pyenv-win\bin` 加到 PATH。**
pyenv-win shim 实际是 45 字节的 proxy,内部 `call pyenv exec uv %*`。如果 PATH 里只有 shim 目录(`D:\Python\.pyenv\pyenv-win\shims`)而没有 bin 目录(`D:\Python\.pyenv\pyenv-win\bin`),会报 `'pyenv' is not recognized as an internal or external command`。run.bat 已经做 PATH 自愈:找到 uv 后把 `%UV_DIR%;D:\Python\.pyenv\pyenv-win\bin` 加到 PATH。

**4. YouTube 反爬必须 Node.js / Deno / Bun。**
YouTube 2025+ 对第三方工具加了 n-challenge 签名,没有 JS 运行时解签名 → 「No video formats found」。README 已写明,用户必须装 ≥22。

**5. pyenv-win shim 文件名是裸 `uv`,不是 `uv.exe`。**
`D:\Python\.pyenv\pyenv-win\shims\uv`(45 字节)+ `uv.bat`(53 字节)。`if exist ...uv.exe` 会判 false,probe 列表里既要 `uv.exe` 也要裸 `uv`。

**6. ffmpeg/ffprobe 必须装。**
ffmpeg 做合流 + 裁剪,ffprobe 做准入验证。缺一个都会让某一步失败。WinGet 装 `Gyan.FFmpeg` 是最方便的方式。

**7. `.bat` 必须 CRLF 行尾(2026-09-17 发现)。**
cmd.exe 按**字节偏移**回读批处理文件。LF-only 的 run.bat 配上它自己的 `goto` 标签 + 括号块,cmd 会算错偏移、回头把前面几行的开头字符吃掉重执行。实测症状:启动时报 7 个 `'tle' is not recognized` / `'/d' is not recognized` / `'em'` / `'m'` 等,后果是 `cd /d "%~dp0"` **静默失效**(能跑只因调用方 cwd 恰好是项目目录)。对照实验:同一份内容 LF 版 7 个错误、CRLF 版 0 个。已加 `.gitattributes` 锁 `*.bat text eol=crlf`。
注意:**Python 读写 .bat 要用 `read_bytes().decode()` 而不是 `read_text()`** —— `read_text()` 默认做换行归一,会把 CRLF 悄悄变成 LF,测试脚本自己就踩回这个坑(表现为 errorlevel 莫名 9009)。

**8. 括号块内 `echo` 里的 `)` 是块结束符(2026-09-17 发现)。**
`if ... ( ... echo X (foo) ... )` —— cmd 把那个 `)` 当成 `if` 块的结束符,**开头的 `(` 不提供嵌套保护**。后果:块被截断在那一行,剩余行掉到顶层**无条件执行**。实测最小复现:`if not "0"=="0" ( echo A / echo B (paren) / echo C )` 输出 `C`(A、B 被跳过,但 C 泄漏执行了)。旧 run.bat 的错误提示块因此会把后 3 行无条件打印,还会吞掉 Node.js 那行的右括号。修法:**错误提示不要包在 `if (...)` 里**,用 `if "%RC%"=="0" exit /b 0` 提前退出 + 平铺结构。

**Why:** 下次任何人改 run.bat / 加新启动脚本 / 调试启动问题,会重新踩这些坑。
**How to apply:** 改 run.bat 时不要加 `chcp`;新增启动入口时确保 `uv` 只调一次 + PATH 自愈;排查「uv 不是内部或外部命令」先看 PATH 里有没有 `D:\Python\.pyenv\pyenv-win\bin`。改完 .bat 先确认行尾是 CRLF(`git ls-files --eol run.bat` 看 `w/crlf`);写带括号的提示文案时别放进 `if (...)` 块。
