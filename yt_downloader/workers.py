"""PySide6 后台 worker (QThread).

下载 / 批量 / 裁剪 / 瑜伽预审都在子线程跑, 经 Qt Signal 回主线程 (跨线程自动
QueuedConnection, 不碰 GUI 控件). 替代旧 customtkinter 的 queue + after(120ms) 轮询.

  - DownloadWorker: 单任务下载. progress(dict) / error(str) / done(path|None).
  - BatchWorker: 顺序批量. url_started(str) 每个开始 / done(path|None) 每个 / batch_end(int).
  - TrimWorker: ffmpeg 裁剪/去广告. finished(result_path|None, error|None).
  - YogaFrameWorker: ffmpeg 抽帧 (轻量衣着预审). done(frames|None, tmpdir, error|None).
  - DeepCheckWorker: subprocess 调 fitness yoga_source_check (YOLO 体态判定).
    done(verdict|None, summary|None, error|None).
"""
from __future__ import annotations

import tempfile

from PySide6.QtCore import QThread, Signal

from .downloader import download
from .trim import remove_segment, trim
from .yoga_check import extract_frames, run_deep_check


class DownloadWorker(QThread):
    """单任务下载线程."""

    progress = Signal(dict)             # yt-dlp 进度钩子字典
    error = Signal(str)                 # 可读错误消息
    done = Signal(object, bool)         # (最终文件路径 str|None, skipped)

    def __init__(self, url: str, out_dir: str, fmt: str,
                 cookies_browser: str = "", cookies_file: str = "",
                 force: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._out = out_dir
        self._fmt = fmt
        self._cb = cookies_browser
        self._cf = cookies_file
        self._force = force

    def run(self) -> None:  # noqa: D401 (QThread override)
        path, skipped = download(
            self._url, self._out, self._fmt,
            on_progress=lambda d: self.progress.emit(d),
            on_error=lambda m: self.error.emit(m),
            cookies_browser=self._cb, cookies_file=self._cf, force=self._force,
        )
        self.done.emit(path, skipped)


class BatchWorker(QThread):
    """顺序批量下载线程 (一个接一个)."""

    progress = Signal(dict)
    error = Signal(str)
    url_started = Signal(str)           # 每个任务开始前发其 URL
    done = Signal(object, bool)         # (每个任务的最终路径 str|None, skipped)
    batch_end = Signal(int)             # 全部完成 (任务数)

    def __init__(self, urls: list[str], out_dir: str, fmt: str,
                 cookies_browser: str = "", cookies_file: str = "",
                 force: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._urls = urls
        self._out = out_dir
        self._fmt = fmt
        self._cb = cookies_browser
        self._cf = cookies_file
        self._force = force

    def run(self) -> None:
        for u in self._urls:
            self.url_started.emit(u)
            path, skipped = download(
                u, self._out, self._fmt,
                on_progress=lambda d: self.progress.emit(d),
                on_error=lambda m: self.error.emit(m),
                cookies_browser=self._cb, cookies_file=self._cf, force=self._force,
            )
            self.done.emit(path, skipped)
        self.batch_end.emit(len(self._urls))


class TrimWorker(QThread):
    """ffmpeg 裁剪 / 去中间段 线程."""

    finished = Signal(object, object)  # (result_path|None, error|None)

    def __init__(self, src: str, out: str, start: float, end: float,
                 remove_mid: bool, precise: bool, parent=None) -> None:
        super().__init__(parent)
        self._src = src
        self._out = out
        self._start = start
        self._end = end
        self._remove = remove_mid
        self._precise = precise

    def run(self) -> None:
        if self._remove:
            result, err = remove_segment(
                self._src, self._out, self._start, self._end, precise=self._precise)
        else:
            result, err = trim(
                self._src, self._out, self._start, self._end, precise=self._precise)
        self.finished.emit(result, err)


class YogaFrameWorker(QThread):
    """ffmpeg 抽帧 (轻量瑜伽衣着预审). 自管 tempdir, 完成后交主窗口 (对话框关闭时清).

    done(frames, tmpdir, error):
      - frames: [(idx, t_sec, png_path), ...] | None
      - tmpdir: 帧输出目录 (对话框关闭后由主窗口 rmtree)
      - error: 可读错误 | None
    """

    done = Signal(object, object, object)

    def __init__(self, video: str, n: int = 9, parent=None) -> None:
        super().__init__(parent)
        self._video = video
        self._n = n
        self._tmpdir = tempfile.mkdtemp(prefix="yoga_frames_")

    def run(self) -> None:
        frames, err = extract_frames(self._video, self._n, self._tmpdir)
        self.done.emit(frames if not err else None, self._tmpdir, err)


class DeepCheckWorker(QThread):
    """subprocess 调 fitness yoga_source_check.py (YOLO 体态判定, ~10-30s).

    done(verdict, summary, error):
      - verdict: "PASS" / "CAUTION" / "REJECT" | None
      - summary: "REJECT — 高危体态 7/12, 特写 0, 暗光 0" | None
      - error: 可读错误 | None
    """

    done = Signal(object, object, object)

    def __init__(self, python_exe: str, script: str, video: str,
                 work_dir: str, parent=None) -> None:
        super().__init__(parent)
        self._py = python_exe
        self._script = script
        self._video = video
        self._work = work_dir

    def run(self) -> None:
        verdict, summary, err = run_deep_check(
            self._py, self._script, self._video, self._work)
        self.done.emit(verdict, summary, err)
