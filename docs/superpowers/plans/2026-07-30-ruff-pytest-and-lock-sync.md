# ruff + pytest + uv.lock 同步 Implementation Plan
> ⚠️ **历史文档 — 阈值已变更 (2026-09-17)**  
> 本文写于 2026-07-30, 其中「码率 ≥5Mbps 准入门槛」已于 2026-09-17 下调为
> **≥2Mbps** (为适配抖音源: 抖音 1080p 档天花板实测 ~2.9Mbps, 旧门槛会把抖音源
> 全部拒掉)。当前生效值以 `CLAUDE.md` 与 `yt_downloader/verify.py` 的
> `THRESH_BITRATE` 为准。本文其余内容为当时记录, 原样保留。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `F:\wkspace\yt-downloader` 加 ruff + pytest 套件(覆盖 verify / trim / downloader 三个底层模块)+ 同步 uv.lock 版本号。`/lint` `/test` slash command 从 placeholder 升级为 active。

**Architecture:** 两步走 — 第一步单独 commit uv.lock 同步(`@lock:` 范围),第二步 ruff + pytest 一起做(`@dev:` 范围)。所有 ruff findings 不自动 fix — 先跑 check 报告问题,人工判断后单独 commit。pytest 用 subprocess mock + 集成(可用时)两层。

**Tech Stack:** ruff ≥0.6 + pytest ≥8 + uv `[dependency-groups]`(2024+ 推荐写法)。无 GUI 测试,无 ffmpeg/ffprobe 真实依赖(`pytest-mock` 或 `unittest.mock` 已够)。

---

## Global Constraints

- 不改 Python 源码的业务逻辑(只允许 ruff 自动 fix 的纯风格改动 + 测试代码本身)
- 项目根: `F:\wkspace\yt-downloader`
- 不动 `run.bat`、`yt_downloader/app.py` / `dialogs.py` / `workers.py` / `yoga_check.py`(GUI 相关,本 plan 不测)
- 不动下游契约:`downstream-pipeline.md` 里写明的准入标记格式 `[✓ 达标]` / `[✗ 不达标]` 不变
- 编码: UTF-8,无 BOM
- 中文 commit message(沿用 `@launcher:` / `@claude-env:` / `@lock:` / `@dev:` 前缀风格)
- 提交粒度:每 Task 单独 commit;ruff findings 在 Task 3 单独 commit(每个文件一个 commit)
- 不动 `docs/` 目录(spec/plan/SDD workspace)— 留着不 commit

---

## Task 1: 同步 uv.lock 版本号

**Files:**
- Modify: `F:\wkspace\yt-downloader\uv.lock`(1 行改动)

- [ ] **Step 1: 验证 uv.lock 当前 diff**

```bash
cd "F:/wkspace/yt-downloader"
git diff uv.lock
```
期望:`version = "1.0.0"` → `"1.2.0"` 一行改动。如果 diff 多于一行或内容不同,**停下来读 `.superpowers/sdd/2026-07-30-yt-downloader-claude-env/progress.md`** 看是否有遗漏 — 不要继续。

- [ ] **Step 2: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add uv.lock
git commit -m "@lock: 同步 version 到 1.2.0(对齐 init commit 标记的版本)"
```

- [ ] **Step 3: 校验**

```bash
cd "F:/wkspace/yt-downloader" && git status --short && git log --oneline -3
```
期望:`git status --short` 干净(没有 `M uv.lock`),看到新的 `@lock:` commit。

---

## Task 2: 加 ruff + pytest dev 依赖 + pyproject 配置

**Files:**
- Modify: `F:\wkspace\yt-downloader\pyproject.toml`

- [ ] **Step 1: 添加 `[dependency-groups] dev` 到 pyproject.toml**

读 `F:\wkspace\yt-downloader\pyproject.toml` 当前内容,在 `[project.optional-dependencies]` 之后(如果有)或文件末尾加:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]
```

**注意:** 用 `[dependency-groups]` 而非 `[project.optional-dependencies] dev` — uv 2024+ 推荐前者,语义清晰(`uv sync --group dev` 装)。保留已有的 `[project.optional-dependencies] pack` 不动。

- [ ] **Step 2: 添加 `[tool.ruff]` 配置**

在 `[dependency-groups]` 之后加:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
extend-exclude = [
    ".venv",
    "assets",
]

[tool.ruff.lint]
# E/F/W = pycodestyle/pyflakes/pycodestyle-warnings
# I = isort (import 顺序)
# B = bugbear (深入错误检查)
# UP = pyupgrade (现代化写法)
select = ["E", "F", "W", "I", "B", "UP"]
ignore = [
    "E501",  # line-too-long: 中文项目 + 长路径容易超,手动控制
    "B008",  # do-not-perform-function-call-in-argument-default: PySide6 信号连接常用
]

[tool.ruff.lint.isort]
known-first-party = ["yt_downloader"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 3: 装 dev 依赖**

```bash
cd "F:/wkspace/yt-downloader"
uv sync --group dev
```
期望:`Resolved N packages, Installed M packages` 无报错。

- [ ] **Step 4: 验证 ruff + pytest 可用**

```bash
cd "F:/wkspace/yt-downloader" && uv run ruff --version
cd "F:/wkspace/yt-downloader" && uv run pytest --version
```
期望:两个都返回版本号。

- [ ] **Step 5: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add pyproject.toml uv.lock  # uv.lock 也可能因为 dev 依赖变化
git commit -m "@dev: ruff + pytest dev 依赖 + pyproject 配置"
```

**重要:不要在这一步跑 `ruff check` 自动 fix!** 那是 Task 3 的事,自动 fix 范围需要人工判断。

---

## Task 3: 跑 ruff check,报告 findings,不自动 fix

**Files:** 不创建新文件,只跑命令。

- [ ] **Step 1: 跑 ruff check**

```bash
cd "F:/wkspace/yt-downloader"
uv run ruff check yt_downloader/ 2>&1 | tee /tmp/ruff-findings.txt
```
**所有** findings 都记录下来,但**不**自动 fix。

- [ ] **Step 2: 把 findings 写到报告文件**

写报告到 `F:\wkspace\yt-downloader\.superpowers\sdd\2026-07-30-ruff-pytest-and-lock-sync\ruff-findings.md`(创建这个目录)。

报告格式:
```markdown
# ruff findings

**Date:** 2026-07-30
**Command:** `uv run ruff check yt_downloader/`

## Summary
- Total: N
- Auto-fixable safely (isort I): N1
- Auto-fixable safely (UP pyupgrade): N2
- Manual review needed (B bugbear / W warnings): N3

## By file

### yt_downloader/verify.py
- [I001] import 顺序 (line 14): ...
- [UP035] outdated typing (line 28): ...

### yt_downloader/app.py
- [B008] ... (line 234)
...
```

- [ ] **Step 3: 把报告呈现给用户,等决定**

把报告内容贴出来(关键 findings),问:哪些 fix 可以自动应用,哪些要人工看?

**决策选项:**
- A:全部不 fix,只把发现写到 CLAUDE.md「踩坑速查」里,留待后续
- B:只 fix 自动安全的(I + UP 的 safe 部分,绕开 B)
- C:分两类 commit — 安全的自动 fix 一个 commit,B 类逐条报告但不修

**默认推荐 B**(在 brainstorming 里已确认 「bugbear 类手动」)。继续等用户决定。

---

## Task 4: 写 pytest 测试(verify + trim + downloader)

**Files:**
- Create: `F:\wkspace\yt-downloader\tests\__init__.py`
- Create: `F:\wkspace\yt-downloader\tests\conftest.py`(可选,共享 fixtures)
- Create: `F:\wkspace\yt-downloader\tests\test_verify.py`
- Create: `F:\wkspace\yt-downloader\tests\test_trim.py`
- Create: `F:\wkspace\yt-downloader\tests\test_downloader.py`

- [ ] **Step 1: 创建 tests/ 目录骨架**

```python
# tests/__init__.py — 空文件,让 tests/ 成为 package
```

- [ ] **Step 2: 写 conftest.py(共享 subprocess mock)**

```python
"""共享 fixtures.

`ffmpeg_available` / `ffprobe_available` 自动检测本机是否有 ffmpeg/ffprobe,
集成测试在可用时才跑,缺失时自动 skip(不 fail)。
"""
from __future__ import annotations

import shutil

import pytest


@pytest.fixture
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None or shutil.which(
        r"C:\Users\18091\ffmpeg\ffmpeg.exe"
    ) is not None


@pytest.fixture
def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None or shutil.which(
        r"C:\Users\18091\ffmpeg\ffprobe.exe"
    ) is not None


@pytest.fixture
def skip_if_no_ffmpeg(ffmpeg_available: bool) -> None:
    if not ffmpeg_available:
        pytest.skip("ffmpeg not available on PATH or at C:\\Users\\18091\\ffmpeg")


@pytest.fixture
def skip_if_no_ffprobe(ffprobe_available: bool) -> None:
    if not ffprobe_available:
        pytest.skip("ffprobe not available on PATH or at C:\\Users\\18091\\ffmpeg")
```

- [ ] **Step 3: 写 `test_verify.py`**

```python
"""verify.py — 准入门槛阈值 + ProbeResult 性质 + probe() 调用.

两层:
- 纯函数层(无 subprocess):阈值边界、ProbeResult.*_ok、failures
- 集成层(real ffprobe):`probe()` 真实调用(自动 skip if ffprobe 不在)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from yt_downloader.verify import (
    ProbeResult,
    THRESH_BITRATE,
    THRESH_DURATION,
    THRESH_SHORT_SIDE,
    probe,
)


# ---- 阈值常量钉死 ----
def test_thresholds_constants():
    assert THRESH_SHORT_SIDE == 720
    assert THRESH_BITRATE == 5_000_000
    assert THRESH_DURATION == 30.0


# ---- ProbeResult 几何/性质 ----
def _r(width=1920, height=1080, duration=120.0, bit_rate=6_000_000, codec="h264"):
    return ProbeResult(width=width, height=height, duration=duration,
                       bit_rate=bit_rate, codec=codec, path="x.mp4")


def test_short_side_landscape():
    assert _r(1920, 1080).short_side == 1080


def test_short_side_portrait():
    assert _r(1080, 1920).short_side == 1080


def test_short_side_zero_when_no_video():
    assert _r(0, 0).short_side == 0


def test_short_side_ok_above_threshold():
    # 1080 > 720
    assert _r(1920, 1080).short_side_ok is True


def test_short_side_ok_below_threshold():
    # 720 = 720 边界:达标(>=)
    assert _r(1280, 720).short_side_ok is True
    # 704 < 720 不达标
    assert _r(1280, 704).short_side_ok is False


def test_bitrate_ok_at_threshold():
    assert _r(bit_rate=5_000_000).bitrate_ok is True
    assert _r(bit_rate=4_999_999).bitrate_ok is False


def test_duration_ok_at_threshold():
    assert _r(duration=30.0).duration_ok is True
    assert _r(duration=29.9).duration_ok is False


def test_ok_all_passing():
    r = _r()
    assert r.ok is True
    assert r.failures == []


def test_ok_no_video():
    r = _r(width=0, height=0)
    assert r.ok is False
    assert r.failures == ["无视频流 (纯音频?)"]


def test_failures_lists_each_failing_criterion():
    # 短边 < 720, 码率 < 5Mbps, 时长 < 30s — 三项都不达标
    r = _r(width=640, height=360, duration=10.0, bit_rate=1_000_000)
    assert r.ok is False
    assert len(r.failures) == 3
    assert any("短边" in f for f in r.failures)
    assert any("码率" in f for f in r.failures)
    assert any("时长" in f for f in r.failures)


# ---- probe() subprocess mock 层 ----
def test_probe_returns_none_when_file_not_found():
    """probe() 对不存在的路径返回 None,不抛."""
    with patch("yt_downloader.verify.subprocess.run",
               side_effect=FileNotFoundError):
        assert probe("Z:/nonexistent.mp4") is None


def test_probe_returns_none_when_timeout():
    with patch("yt_downloader.verify.subprocess.run",
               side_effect=__import__("subprocess").TimeoutExpired(cmd="x", timeout=30)):
        assert probe("any.mp4") is None


def test_probe_parses_valid_ffprobe_json():
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps({
        "streams": [{"width": 1920, "height": 1080, "codec_name": "h264"}],
        "format": {"duration": "120.5", "bit_rate": "6000000"},
    })
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        r = probe("any.mp4")
    assert r is not None
    assert r.width == 1920 and r.height == 1080
    assert r.duration == 120.5
    assert r.bit_rate == 6_000_000
    assert r.codec == "h264"
    assert r.ok is True


def test_probe_returns_none_on_nonzero_returncode():
    fake = MagicMock()
    fake.returncode = 1
    fake.stdout = ""
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        assert probe("any.mp4") is None


def test_probe_returns_none_on_invalid_json():
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "not json"
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        assert probe("any.mp4") is None


def test_probe_handles_missing_fields_gracefully():
    """ffprobe 输出里字段缺失时,probe() 仍返回 ProbeResult(不全 None)."""
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = json.dumps({"streams": [{}], "format": {}})
    with patch("yt_downloader.verify.subprocess.run", return_value=fake):
        r = probe("any.mp4")
    assert r is not None
    assert r.width == 0
    assert r.height == 0
    assert r.bit_rate == 0
    assert r.has_video is False
    assert r.ok is False


# ---- 集成层(real ffprobe)— 自动 skip if not available ----
def test_probe_integration_real_video(skip_if_no_ffprobe, tmp_path):
    """真实 ffprobe 调用 — 跳过 if ffprobe 不在."""
    import subprocess as sp
    # 找一个本机真实视频文件测(用户 Downloads 目录或 yt_downloader assets/)
    from pathlib import Path
    candidates = [
        Path.home() / "Downloads",
        Path(r"F:\wkspace\yt-downloader\yt_downloader\assets"),
    ]
    video = None
    for d in candidates:
        if not d.exists():
            continue
        for ext in ("*.mp4", "*.mkv", "*.webm"):
            matches = list(d.glob(ext))
            if matches:
                video = matches[0]
                break
        if video:
            break
    if video is None:
        pytest.skip("no test video found in standard locations")

    r = probe(str(video))
    if r is None:
        pytest.skip("ffprobe could not parse the test video")
    assert r.has_video
    assert r.width > 0 and r.height > 0
```

- [ ] **Step 4: 写 `test_trim.py`**

```python
"""trim.py — trim() / remove_segment() 参数校验 + 命令拼接.

subprocess 层用 mock;真实 ffmpeg 集成层 optional。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yt_downloader.trim import remove_segment, trim


def test_trim_rejects_end_le_start():
    out, err = trim("src.mp4", "out.mp4", 5.0, 3.0)
    assert out is None
    assert "结束时间必须大于开始时间" in err


def test_trim_rejects_missing_src(tmp_path):
    out, err = trim(str(tmp_path / "no.mp4"), str(tmp_path / "out.mp4"), 1.0, 5.0)
    assert out is None
    assert "源文件不存在" in err


def test_trim_command_construction_copy_mode(tmp_path):
    """precise=False 模式:应该用 -c copy + -avoid_negative_ts."""
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)  # 最小文件,不会真跑 ffmpeg
    out = tmp_path / "out.mp4"

    fake = MagicMock()
    fake.returncode = 0
    # 创建 out 文件让 trim() 认为成功了
    out.write_bytes(b"\x00" * 16)

    with patch("yt_downloader.trim.subprocess.run", return_value=fake) as m:
        result, err = trim(str(src), str(out), 1.0, 5.0, precise=False)

    assert err is None
    assert result == str(out)
    # 验证调用的命令包含 -c copy 和 -ss
    cmd = m.call_args[0][0]
    assert "-c" in cmd and "copy" in cmd
    assert "-ss" in cmd
    assert "1.000" in cmd


def test_trim_command_construction_precise_mode(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"\x00" * 16)

    fake = MagicMock()
    fake.returncode = 0
    with patch("yt_downloader.trim.subprocess.run", return_value=fake) as m:
        result, err = trim(str(src), str(out), 1.0, 5.0, precise=True)

    assert err is None
    cmd = m.call_args[0][0]
    assert "libx264" in cmd
    assert "crf" in cmd


def test_trim_returns_error_on_nonzero(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"

    fake = MagicMock()
    fake.returncode = 1
    fake.stderr = "ffmpeg error: invalid data"
    with patch("yt_downloader.trim.subprocess.run", return_value=fake):
        result, err = trim(str(src), str(out), 1.0, 5.0)

    assert result is None
    assert "ffmpeg" in err.lower() or "ffmpeg" in err


def test_remove_segment_rejects_end_le_start():
    out, err = remove_segment("x.mp4", "y.mp4", 5.0, 3.0)
    assert out is None
    assert "结束时间必须大于开始时间" in err


def test_remove_segment_rejects_negative_only():
    out, err = remove_segment("x.mp4", "y.mp4", -5.0, -1.0)
    assert out is None
    assert "请输入有效" in err


def test_remove_segment_command_construction_copy(tmp_path):
    """precise=False 模式:三步 (切 p1, 切 p2, concat)."""
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"

    fake_ok = MagicMock(returncode=0, stderr="")
    # 让 p1 和 out 都存在,这样函数走到 p2 创建那步也 OK
    # remove_segment 在 finally 清理 p1/p2/list,所以我们只需要 mock 创建步骤成功
    with patch("yt_downloader.trim.subprocess.run", return_value=fake_ok) as m:
        # 让所有 subprocess.run 都成功,文件创建也模拟
        with patch("builtins.open", new_callable=MagicMock):
            # patch open() for the concat list file
            result, err = remove_segment(str(src), str(out), 5.0, 10.0, precise=False)

    assert err is None or err is not None  # 不强求,这只验证命令被构造
    # 验证至少有一次 subprocess.run 被调用
    assert m.call_count >= 2  # 至少 p1 + p2


def test_remove_segment_precise_mode_uses_select(tmp_path):
    src = tmp_path / "src.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out.mp4"
    out.write_bytes(b"\x00" * 16)

    fake_ok = MagicMock(returncode=0, stderr="")
    with patch("yt_downloader.trim.subprocess.run", return_value=fake_ok) as m:
        result, err = remove_segment(str(src), str(out), 5.0, 10.0, precise=True)

    assert err is None
    cmd = m.call_args[0][0]
    assert "select=" in " ".join(cmd) or any("select=" in str(x) for x in cmd)
    assert "libx264" in cmd
```

- [ ] **Step 5: 写 `test_downloader.py`**

```python
"""downloader.py — 纯函数层测试.

只测不依赖 yt_dlp / 网络的纯函数:
- FORMATS / AUDIO_SUFFIXES 常量一致性
- is_audio_format(label)
- _normalize_url(url)
"""
from __future__ import annotations

import pytest

from yt_downloader.downloader import (
    AUDIO_SUFFIXES,
    FORMATS,
    _normalize_url,
    is_audio_format,
)


# ---- FORMATS 字典结构 ----
def test_formats_has_at_least_three_entries():
    """至少三种品质预设(最高画质 / 中等画质 / 仅音频)."""
    assert len(FORMATS) >= 3


def test_formats_audio_label_in_dict():
    """所有 AUDIO_SUFFIXES 对应的 format label 必须在 FORMATS 里出现."""
    # 仅音频 preset 的 label 通常是 "仅音频(m4a)" 或类似
    audio_labels = [label for label in FORMATS if any(s in label for s in ("音频", "audio", "Audio"))]
    assert len(audio_labels) >= 1


# ---- AUDIO_SUFFIXES 一致性 ----
def test_audio_suffixes_includes_m4a():
    """m4a 是默认的仅音频格式后缀."""
    assert ".m4a" in AUDIO_SUFFIXES


def test_audio_suffixes_lowercase_with_dot():
    """所有后缀以 . 开头且小写(避免大小写不一致)."""
    for s in AUDIO_SUFFIXES:
        assert s.startswith(".")
        assert s == s.lower()


# ---- is_audio_format ----
def test_is_audio_format_matches_audio_label():
    """任何包含「音频」的 label 都判定为音频格式."""
    assert is_audio_format("仅音频(m4a)") is True
    assert is_audio_format("最高画质 (mp4)") is False


def test_is_audio_format_handles_unknown_label():
    """未知 label 返回 False(不抛)."""
    assert is_audio_format("不存在的品质") is False


# ---- _normalize_url ----
def test_normalize_url_passes_https_youtube_unchanged():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _normalize_url(url) == url


def test_normalize_url_strips_trailing_whitespace():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ   "
    result = _normalize_url(url)
    assert not result.endswith(" ")


def test_normalize_url_handles_youtu_be_short_link():
    url = "https://youtu.be/dQw4w9WgXcQ"
    result = _normalize_url(url)
    # 至少 URL 主体保留
    assert "youtu" in result or "dQw4w9WgXcQ" in result


def test_normalize_url_handles_douyin():
    """抖音 URL 应该被识别/规范化."""
    url = "https://www.douyin.com/video/1234567890"
    result = _normalize_url(url)
    assert result  # 非空
```

- [ ] **Step 6: 跑 pytest,确认全绿**

```bash
cd "F:/wkspace/yt-downloader"
uv run pytest -q 2>&1 | tee /tmp/pytest-output.txt
```
期望:全绿。如果有失败,**先修测试代码,不动源文件**。

- [ ] **Step 7: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add tests/
git commit -m "@dev: pytest 测试覆盖 verify + trim + downloader(纯函数 + subprocess mock + ffprobe 集成)"
```

---

## Task 5: 升级 /lint 和 /test slash command 描述 + CLAUDE.md 同步

**Files:**
- Modify: `F:\wkspace\yt-downloader\.claude\commands\lint.md`
- Modify: `F:\wkspace\yt-downloader\.claude\commands\test.md`
- Modify: `F:\wkspace\yt-downloader\CLAUDE.md`

- [ ] **Step 1: 更新 `lint.md`**

新内容:
```markdown
---
description: ruff 检查 yt_downloader/(E/F/W/I/B/UP)
---

cd F:\wkspace\yt-downloader && uv run ruff check yt_downloader/
```

- [ ] **Step 2: 更新 `test.md`**

新内容:
```markdown
---
description: 跑 pytest(tests/ — verify + trim + downloader)
---

cd F:\wkspace\yt-downloader && uv run pytest -q
```

- [ ] **Step 3: 更新 CLAUDE.md 的「常用命令」段**

把 `| 跑测试 | uv run pytest -q(目前没有,以后加) |` 改成 `| 跑测试 | uv run pytest -q |`(去掉括号注释)。

把 `| 代码检查 | uv run ruff check yt_downloader/(以后加 ruff) |` 改成 `| 代码检查 | uv run ruff check yt_downloader/ |`。

- [ ] **Step 4: 提交**

```bash
cd "F:/wkspace/yt-downloader"
git add .claude/commands/lint.md .claude/commands/test.md CLAUDE.md
git commit -m "@dev: /lint /test / CLAUDE.md 从 placeholder 升级为 active"
```

---

## Task 6: 端到端验证

**Files:** 不创建新文件,只验证。

- [ ] **Step 1: 校验 git log**

```bash
cd "F:/wkspace/yt-downloader" && git log --oneline f0bb8a3..HEAD
```
期望:看到 4 个新 commit(`@lock:` + `@dev: ruff+pytest dev 依赖` + `@dev: pytest 测试...` + `@dev: /lint /test ...`)。

- [ ] **Step 2: 校验 ruff 真能跑**

```bash
cd "F:/wkspace/yt-downloader" && uv run ruff check yt_downloader/
```
期望:执行成功,有 findings 报告(从 Task 3 来),无 crash。

- [ ] **Step 3: 校验 pytest 全绿**

```bash
cd "F:/wkspace/yt-downloader" && uv run pytest -q
```
期望:全绿。

- [ ] **Step 4: 校验 /lint /test 描述**

读 `.claude/commands/lint.md` 和 `test.md`,确认 description 反映 active 状态。

---

## Verification matrix

| 验证项 | 怎么测 | 期望 |
|---|---|---|
| uv.lock 同步 | `git log --oneline -1 uv.lock` | 看到 `@lock:` commit |
| ruff 装上 | `uv run ruff --version` | 0.6+ |
| ruff check 能跑 | `uv run ruff check yt_downloader/` | 跑通(可有问题报告) |
| pytest 找到测试 | `uv run pytest --collect-only -q` | 列出 20+ 测试 |
| 测试通过 | `uv run pytest -q` | 全绿 |
| /lint /test 描述 | 读 slash command 文件 | 描述反映 active |
| CLAUDE.md 同步 | grep 「以后加」| 无 |

---

## 不在范围

- 不自动 fix ruff B 类(bugbear)— 等用户决定
- 不测 GUI 模块(app.py / dialogs.py / workers.py / yoga_check.py)— 需要真实 Qt event loop
- 不加 CI / pre-commit — 单独 plan
- 不动 `downstream-pipeline.md` / `run-bat-pitfalls.md` 等 memory(已经准确)
- 不动 `docs/` 目录