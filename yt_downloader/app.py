"""YT 视频下载器 GUI (PySide6 / Qt).

功能: 单/批量下载 YouTube / 抖音 → 自动 ffprobe 验证准入门槛 → 详情面板展示规格
→ 可播放 / 裁剪 / 去广告 / 瑜伽预审. 设置 (输出目录/品质/验证/认证方式) 持久化到
~/.yt-downloader/config.json.

线程模型: 下载/批量/裁剪/预审在 QThread 子线程跑, 进度/完成/错误经 Qt Signal 回主线程
(跨线程自动 QueuedConnection, 不碰 GUI 控件). 替代旧 customtkinter 的 queue+after 轮询.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import config
from .dialogs import BatchDialog, TrimDialog, YogaReviewDialog
from .downloader import FORMATS, AUDIO_SUFFIXES, is_audio_format
from .verify import THRESH_BITRATE, THRESH_DURATION, THRESH_SHORT_SIDE, ProbeResult, probe
from .yoga_check import fitness_env
from .workers import BatchWorker, DeepCheckWorker, DownloadWorker, TrimWorker, YogaFrameWorker

APP_TITLE = "YT 视频下载器"
APP_VERSION = "1.2.0"

# 认证: 绕 YouTube "Sign in to confirm you're not a bot". Chrome/Edge 新版加密读不出,
# 仅 Firefox 可自动读 (需在 Firefox 登录过 YouTube); cookies.txt 文件最通用 (扩展导出).
AUTH_OPTIONS = ["无", "Firefox (已登录)", "cookies.txt 文件…"]

# 日志颜色
LOG_OK = "#4ade80"
LOG_BAD = "#f87171"
LOG_INFO = "#93c5fd"
LOG_DIM = "#9ca3af"
LOG_ERR = "#fbbf24"


def _fmt_bytes(n: float) -> str:
    return f"{n / 1e6:.1f} MB" if n < 1e9 else f"{n / 1e9:.2f} GB"


def _startfile(path: str) -> None:
    """用系统默认程序打开 (Windows). 失败静默."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        pass


def _apply_theme(app: QApplication, mode: str) -> None:
    """Fusion + 暗色调色板 (dark 默认); light 走 Fusion 默认."""
    app.setStyle("Fusion")
    if mode == "light":
        return
    p = QPalette()
    bg = QColor("#242424")
    base = QColor("#2b2b2b")
    text = QColor("#e5e5e5")
    btn = QColor("#3a3a3a")
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, QColor("#333333"))
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, btn)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.ToolTipBase, base)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Highlight, QColor("#2563eb"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#888888"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#888888"))
    app.setPalette(p)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = config.load()
        _apply_theme(QApplication.instance(), self.settings.appearance)  # type: ignore[arg-type]

        self.setWindowTitle(f"{APP_TITLE}  v{APP_VERSION}")
        self.resize(860, 940)
        self.setMinimumSize(760, 800)

        os.makedirs(self.settings.output_dir, exist_ok=True)
        self.busy = False
        self._batch_mode = False
        self._current_file: str | None = None
        self._current_probe: ProbeResult | None = None
        self._dl_worker = None      # DownloadWorker | BatchWorker | None
        self._trim_worker = None    # TrimWorker | None
        self._yoga_frame_worker = None  # YogaFrameWorker | None
        self._deep_worker = None    # DeepCheckWorker | None
        self._yoga_dlg = None       # YogaReviewDialog | None (模态期间持有)
        self._yoga_tmpdir: str | None = None  # 抽帧 tempdir (对话框关闭时清)

        central = QWidget()
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(16, 12, 16, 12)
        self._root.setSpacing(8)

        self._build_header()
        self._build_url_row()
        self._build_options()
        self._build_buttons()
        self._build_progress()
        self._build_detail()
        self._build_log()
        self._build_footer()

    # ---------------- UI 构建 ----------------
    def _build_header(self) -> None:
        title = QLabel("📺  YT 视频下载器")
        f = QFont(); f.setPointSize(18); f.setBold(True)
        title.setFont(f)
        sub = QLabel("高清下载 (YouTube / 抖音) + 验证准入 + 播放 / 裁剪 / 去广告")
        sub.setStyleSheet("color:#9ca3af;")
        self._root.addWidget(title)
        self._root.addWidget(sub)

    def _build_url_row(self) -> None:
        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴 YouTube / 抖音 链接 (https://...)")
        self.url_edit.setMinimumHeight(36)
        paste = QPushButton("📋 粘贴")
        paste.setFixedWidth(86)
        paste.clicked.connect(self._paste)
        row.addWidget(self.url_edit, 1)
        row.addWidget(paste)
        self._root.addLayout(row)

    def _build_options(self) -> None:
        box = QWidget()
        box.setObjectName("OptBox")
        g = QGridLayout(box)
        g.setContentsMargins(12, 10, 12, 10)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(8)

        g.addWidget(QLabel("品质"), 0, 0)
        self.fmt_box = QComboBox()
        self.fmt_box.addItems(list(FORMATS.keys()))
        cur = self.settings.format_label if self.settings.format_label in FORMATS else "最高画质 (mp4)"
        self.fmt_box.setCurrentText(cur)
        self.fmt_box.setFixedWidth(240)
        g.addWidget(self.fmt_box, 0, 1)

        self.verify_cb = QCheckBox("下载后验证准入")
        self.verify_cb.setChecked(self.settings.verify)
        g.addWidget(self.verify_cb, 0, 2, 1, 2)
        self.force_cb = QCheckBox("强制重新下载 (已存在时改名 a(1) 重下, 不覆盖)")
        self.force_cb.setChecked(self.settings.force)
        self.force_cb.setToolTip("默认: 文件已存在→跳过 (省流量)。勾上: 总是重新下载, "
                                 "重名自动加序号 a(1)/a(2), 旧文件保留。")
        g.addWidget(self.force_cb, 1, 0, 1, 2)
        hint = QLabel(f"(≥{THRESH_SHORT_SIDE}px / ≥{int(THRESH_BITRATE / 1e6)}Mbps / ≥{int(THRESH_DURATION)}s)")
        hint.setStyleSheet("color:#9ca3af; font-size:11px;")
        g.addWidget(hint, 1, 2, 1, 2)

        g.addWidget(QLabel("输出到"), 2, 0)
        self.dir_edit = QLineEdit(self.settings.output_dir)
        g.addWidget(self.dir_edit, 2, 1, 1, 2)
        browse = QPushButton("浏览…")
        browse.setFixedWidth(82)
        browse.clicked.connect(self._browse)
        g.addWidget(browse, 2, 3)

        g.addWidget(QLabel("认证"), 3, 0)
        self.auth_box = QComboBox()
        self.auth_box.addItems(AUTH_OPTIONS)
        self.auth_box.setFixedWidth(180)
        self.auth_box.currentTextChanged.connect(self._on_auth_change)
        g.addWidget(self.auth_box, 3, 1)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("cookies.txt 文件路径…")
        g.addWidget(self.cookie_edit, 3, 2)
        browse_ck = QPushButton("浏览…")
        browse_ck.setFixedWidth(82)
        browse_ck.clicked.connect(self._browse_cookiefile)
        g.addWidget(browse_ck, 3, 3)

        # 按保存的设置恢复认证
        if self.settings.cookies_file:
            self.auth_box.setCurrentText("cookies.txt 文件…")
            self.cookie_edit.setText(self.settings.cookies_file)
        elif self.settings.cookies_browser == "firefox":
            self.auth_box.setCurrentText("Firefox (已登录)")

        g.setColumnStretch(2, 1)
        self._root.addWidget(box)

    def _build_buttons(self) -> None:
        row = QHBoxLayout()
        self.dl_btn = QPushButton("⬇  下载")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        self.dl_btn.setFont(f)
        self.dl_btn.setMinimumHeight(42)
        self.dl_btn.clicked.connect(self._on_download)
        self.batch_btn = QPushButton("☰ 批量")
        self.batch_btn.setMinimumHeight(42)
        self.batch_btn.setFixedWidth(120)
        self.batch_btn.clicked.connect(self._open_batch)
        row.addWidget(self.dl_btn, 1)
        row.addWidget(self.batch_btn)
        self._root.addLayout(row)

    def _build_progress(self) -> None:
        self.status_lbl = QLabel("就绪 — 粘贴链接开始下载")
        self.status_lbl.setStyleSheet("font-size:13px;")
        self.progress = QProgressBar()
        self.progress.setFixedHeight(16)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.speed_lbl = QLabel("")
        self.speed_lbl.setStyleSheet("color:#9ca3af;")
        self._root.addWidget(self.status_lbl)
        self._root.addWidget(self.progress)
        self._root.addWidget(self.speed_lbl)

    def _build_detail(self) -> None:
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(12, 10, 12, 10)
        g.setHorizontalSpacing(8)

        self.detail_mark = QLabel("—")
        fm = QFont(); fm.setPointSize(16); fm.setBold(True)
        self.detail_mark.setFont(fm)
        self.detail_name = QLabel("下载后显示详情")
        self.detail_name.setStyleSheet("color:#9ca3af;")
        g.addWidget(self.detail_mark, 0, 0)
        g.addWidget(self.detail_name, 0, 1, 1, 3)

        self.spec_labels: dict[str, QLabel] = {}
        specs = [("分辨率", "resolution"), ("短边", "short"), ("时长", "duration"),
                 ("码率", "bitrate"), ("编码", "codec"), ("大小", "size")]
        for i, (label, key) in enumerate(specs):
            r, c = divmod(i, 3)
            lab = QLabel(label)
            lab.setStyleSheet("color:#9ca3af; font-size:11px;")
            val = QLabel("—")
            val.setStyleSheet("font-size:13px;")
            g.addWidget(lab, 1 + r, c * 2)
            g.addWidget(val, 1 + r, c * 2 + 1)
            self.spec_labels[key] = val

        op = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_current)
        self.trim_btn = QPushButton("✂ 裁剪 / 去广告")
        self.trim_btn.setEnabled(False)
        self.trim_btn.clicked.connect(self._open_trim)
        self.yoga_btn = QPushButton("🧘 瑜伽预审")
        self.yoga_btn.setEnabled(False)
        self.yoga_btn.setToolTip("抽样帧 + 衣着人工复核 (抖音\"衣着暴露\"风险预筛).\n"
                                 "本机有 fitness venv 时可点窗内「深度体态扫描」跑 YOLO.")
        self.yoga_btn.clicked.connect(self._open_yoga_check)
        self.open_btn = QPushButton("📂 打开目录")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_dir)
        op.addWidget(self.play_btn)
        op.addWidget(self.trim_btn)
        op.addWidget(self.yoga_btn)
        op.addWidget(self.open_btn)
        op.addStretch(1)
        g.addLayout(op, 3, 0, 1, 6)
        g.setColumnStretch(1, 1)
        self._root.addWidget(box)

    def _build_log(self) -> None:
        head = QLabel("下载记录")
        self._root.addWidget(head)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setStyleSheet("font-size:12px;")
        self._root.addWidget(self.log, 1)

    def _build_footer(self) -> None:
        foot = QLabel("⚠ 仅下载你有权下载的内容, 尊重版权与平台条款.")
        foot.setStyleSheet("color:#7c7c7c; font-size:11px;")
        self._root.addWidget(foot)

    # ---------------- 认证 (cookies) ----------------
    def _cookie_settings(self) -> tuple[str, str]:
        sel = self.auth_box.currentText()
        if sel == "cookies.txt 文件…":
            return "", self.cookie_edit.text().strip()
        if sel == "Firefox (已登录)":
            return "firefox", ""
        return "", ""

    def _on_auth_change(self, text: str) -> None:
        if text == "cookies.txt 文件…" and not self.cookie_edit.text().strip():
            self._browse_cookiefile()

    def _browse_cookiefile(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "选择 cookies.txt", "", "cookies.txt (*.txt);;所有文件 (*.*)")
        if p:
            self.cookie_edit.setText(p)
            self.auth_box.setCurrentText("cookies.txt 文件…")

    # ---------------- 小回调 ----------------
    def _paste(self) -> None:
        txt = QApplication.clipboard().text()
        if txt:
            self.url_edit.setText(txt.strip().splitlines()[0])

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                             self.dir_edit.text() or self.settings.output_dir)
        if d:
            self.dir_edit.setText(d)

    def _open_dir(self) -> None:
        d = self.dir_edit.text() or self.settings.output_dir
        os.makedirs(d, exist_ok=True)
        _startfile(d)

    def _play_current(self) -> None:
        if self._current_file and os.path.exists(self._current_file):
            _startfile(self._current_file)

    def _log(self, text: str, color: str = LOG_DIM) -> None:
        c = QTextCursor(self.log.document())
        c.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        c.setCharFormat(fmt)
        c.insertText(text + "\n")
        self.log.setTextCursor(c)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.dl_btn.setEnabled(not busy)
        self.batch_btn.setEnabled(not busy)

    # ---------------- 详情 ----------------
    def _reset_detail(self) -> None:
        """新下载开始时清空上一次的详情面板残留 (mark/规格/按钮), 避免误导。"""
        self._current_file = None
        self._current_probe = None
        self.detail_mark.setText("…")
        self.detail_mark.setStyleSheet("color:#9ca3af;")
        self.detail_name.setText("下载中…")
        for v in self.spec_labels.values():
            v.setText("—")
        for b in (self.play_btn, self.trim_btn, self.yoga_btn, self.open_btn):
            b.setEnabled(False)

    def _show_detail(self, path: str, result: ProbeResult | None = None) -> None:
        self._current_file = path
        if result is None:
            result = probe(path)
        self._current_probe = result
        name = os.path.basename(path)
        size = _fmt_bytes(os.path.getsize(path)) if os.path.exists(path) else "—"

        if result and result.has_video:
            self.spec_labels["resolution"].setText(f"{result.width} × {result.height}")
            self.spec_labels["short"].setText(f"{result.short_side} px")
            self.spec_labels["duration"].setText(f"{result.duration:.0f} s")
            self.spec_labels["bitrate"].setText(f"{result.bit_rate / 1e6:.1f} Mbps")
            self.spec_labels["codec"].setText(result.codec)
            self.spec_labels["size"].setText(size)
            if result.ok:
                self.detail_mark.setText("✓ 达标")
                self.detail_mark.setStyleSheet("color:#4ade80;")
            else:
                self.detail_mark.setText("✗ 不达标")
                self.detail_mark.setStyleSheet("color:#f87171;")
        else:
            for k in self.spec_labels:
                self.spec_labels[k].setText("—")
            self.spec_labels["size"].setText(size)
            self.detail_mark.setText("♪")  # 音频/无视频流
            self.detail_mark.setStyleSheet("color:#93c5fd;")
        self.detail_name.setText(name)
        for b in (self.play_btn, self.trim_btn, self.yoga_btn, self.open_btn):
            b.setEnabled(True)

    # ---------------- 下载 ----------------
    def _on_download(self) -> None:
        if self.busy:
            self._log("[!] 正在下载中, 请等待当前任务完成", LOG_ERR)
            return
        url = self.url_edit.text().strip()
        if not url:
            self._log("[!] 请先粘贴 URL", LOG_ERR)
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            self._log("[!] URL 必须以 http(s):// 开头", LOG_ERR)
            return
        out = self.dir_edit.text().strip() or self.settings.output_dir
        os.makedirs(out, exist_ok=True)
        self._set_busy(True)
        self._batch_mode = False
        self._reset_detail()
        self.status_lbl.setText("下载中…")
        self.progress.setValue(0)
        self.speed_lbl.setText("")
        self._log(f"[↓] 开始  {url}", LOG_INFO)
        cb, cf = self._cookie_settings()
        self._dl_worker = DownloadWorker(url, out, self.fmt_box.currentText(), cb, cf,
                                         force=self.force_cb.isChecked())
        self._dl_worker.progress.connect(self._on_progress)
        self._dl_worker.error.connect(self._on_error)
        self._dl_worker.done.connect(self._on_done)
        self._dl_worker.start()

    def _open_batch(self) -> None:
        if self.busy:
            self._log("[!] 正在下载中", LOG_ERR)
            return
        dlg = BatchDialog(self)
        if dlg.exec() != BatchDialog.Accepted:
            return
        urls = dlg.urls()
        if urls:
            self._start_batch(urls)

    def _start_batch(self, urls: list[str]) -> None:
        out = self.dir_edit.text().strip() or self.settings.output_dir
        fmt = self.fmt_box.currentText()
        cb, cf = self._cookie_settings()
        self._set_busy(True)
        self._batch_mode = True
        self._reset_detail()
        self.progress.setValue(0)
        self._log(f"[☰] 批量: {len(urls)} 个任务, 品质 {fmt}", LOG_INFO)
        self._dl_worker = BatchWorker(urls, out, fmt, cb, cf,
                                      force=self.force_cb.isChecked())
        self._dl_worker.progress.connect(self._on_progress)
        self._dl_worker.error.connect(self._on_error)
        self._dl_worker.url_started.connect(
            lambda u: (self._log(f"[→] {u}", LOG_INFO),
                       self.progress.setValue(0), self.speed_lbl.setText("")))
        self._dl_worker.done.connect(self._on_done)
        self._dl_worker.batch_end.connect(self._on_batch_end)
        self._dl_worker.start()

    # ---------------- 裁剪 / 去广告 ----------------
    def _open_trim(self) -> None:
        if not self._current_file or not os.path.exists(self._current_file):
            return
        dur = self._current_probe.duration if self._current_probe else 0.0
        dlg = TrimDialog(self._current_file, dur, self)
        dlg.trimRequested.connect(self._run_trim)
        dlg.exec()

    def _run_trim(self, out: str, start: float, end: float, remove_mid: bool, precise: bool) -> None:
        if not self._current_file:
            return
        self._log(f"[✂] {'去广告' if remove_mid else '裁剪'}中… (ffmpeg)", LOG_INFO)
        self._trim_worker = TrimWorker(self._current_file, out, start, end, remove_mid, precise)
        self._trim_worker.finished.connect(self._on_trimmed)
        self._trim_worker.start()

    # ---------------- 瑜伽预审 ----------------
    def _open_yoga_check(self) -> None:
        if not self._current_file or not os.path.exists(self._current_file):
            return
        self.yoga_btn.setEnabled(False)
        self.status_lbl.setText("瑜伽预审: 抽帧中… (ffmpeg)")
        self._log(f"[🧘] 预审 {os.path.basename(self._current_file)} — 抽帧…", LOG_INFO)
        self._yoga_frame_worker = YogaFrameWorker(self._current_file, n=9)
        self._yoga_frame_worker.done.connect(self._on_yoga_frames)
        self._yoga_frame_worker.start()

    def _on_yoga_frames(self, frames: object, tmpdir: object, err: object) -> None:
        self.yoga_btn.setEnabled(True)
        self._yoga_tmpdir = tmpdir if isinstance(tmpdir, str) else None
        frame_list = frames if isinstance(frames, list) else None
        if err or not frame_list:
            self._log(f"[✗] 抽帧失败: {(err or '无帧')[-300:]}", LOG_BAD)
            self.status_lbl.setText("瑜伽预审: 抽帧失败")
            return
        self._log(f"[🧘] 抽到 {len(frame_list)} 帧 — 打开人工复核窗口", LOG_INFO)
        self.status_lbl.setText("瑜伽预审 — 人工复核窗口已打开")
        deep_avail = fitness_env() is not None
        self._yoga_dlg = YogaReviewDialog(frame_list, deep_avail, self)
        self._yoga_dlg.deepRequested.connect(self._run_deep_check)
        self._yoga_dlg.exec()   # 模态: 期间 DeepCheckWorker 信号仍能回填 (模态事件循环活)
        # 对话框关闭 → 清临时帧目录 (含深度扫描的 <stem>/ 子目录)
        if isinstance(tmpdir, str):
            shutil.rmtree(tmpdir, ignore_errors=True)
        self._yoga_dlg = None
        self._yoga_tmpdir = None

    def _run_deep_check(self) -> None:
        env = fitness_env()
        if not env or not self._current_file:
            return
        py, script = env
        # work_dir 复用帧 tempdir (深度扫描在其下建 <stem>/, 不与抽帧 frame_%03d.png 冲突)
        work = self._yoga_tmpdir or os.path.dirname(self._current_file)
        self._deep_worker = DeepCheckWorker(py, script, self._current_file, work)
        self._deep_worker.done.connect(self._on_deep_check)
        self._deep_worker.start()

    def _on_deep_check(self, verdict: object, summary: object, err: object) -> None:
        if self._yoga_dlg:
            self._yoga_dlg.set_deep_result(verdict, summary, err)
        if err:
            self._log(f"[✗] 深度扫描失败: {str(err)[-300:]}", LOG_BAD)
        elif summary:
            self._log(f"[🧘] 深度体态: {summary}", LOG_INFO)

    # ---------------- worker 槽 ----------------
    def _on_progress(self, d: dict) -> None:
        st = d.get("status")
        if st == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            pct = (100 * got / tot) if tot else 0
            self.progress.setValue(int(pct) if tot else 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            parts = [f"{got / 1e6:.1f} MB" if not tot else f"{got / 1e6:.1f} / {tot / 1e6:.1f} MB"]
            if speed:
                parts.append(f"{speed / 1e6:.2f} MB/s")
            if eta:
                parts.append(f"剩余 {eta}s")
            self.status_lbl.setText(f"下载中… {pct:.0f}%")
            self.speed_lbl.setText("   ".join(parts))
        elif st == "finished":
            self.status_lbl.setText("合并音频视频 (ffmpeg)…")
            self.speed_lbl.setText("")
            self.progress.setValue(100)

    def _on_done(self, final_path: object, skipped: bool) -> None:
        path = final_path if isinstance(final_path, str) else None
        if not path or not os.path.exists(path):
            if not self._batch_mode:
                self.status_lbl.setText("未输出文件 (见错误记录)")
                self._set_busy(False)
            return
        name = os.path.basename(path)
        sz = os.path.getsize(path) / 1e6
        audio = is_audio_format(self.fmt_box.currentText()) or path.lower().endswith(AUDIO_SUFFIXES)
        r = None
        if self.verify_cb.isChecked() and not audio:
            r = probe(path)
        tag = "  [⊘ 已存在, 跳过]" if skipped else ""
        if r and r.has_video:
            if r.ok:
                self._log(f"[✓ 达标]{tag}  {name}  {r.width}×{r.height}  "
                          f"{r.bit_rate / 1e6:.1f}Mbps  {r.duration:.0f}s  ({sz:.1f}MB)", LOG_OK)
                self.status_lbl.setText(("⊘ 已存在 — " if skipped else "✓ 达标 — ") + name)
            else:
                self._log(f"[✗ 不达标]{tag} {name}  {r.width}×{r.height}  "
                          f"{r.bit_rate / 1e6:.1f}Mbps  {r.duration:.0f}s  ({sz:.1f}MB)", LOG_BAD)
                self._log("           → " + ", ".join(r.failures) + "  (建议换更高清源)", LOG_BAD)
                self.status_lbl.setText(("⊘ 已存在 — " if skipped else "✗ 不达标 — ") + name)
        else:
            self._log(f"[✓]{tag} {name}  ({sz:.1f}MB)" + ("  [音频]" if audio else ""), LOG_OK)
            self.status_lbl.setText(("⊘ 已存在 " if skipped else "完成") + ("[音频]" if audio else ""))
        self._show_detail(path, r)
        self.progress.setValue(100)
        self.speed_lbl.setText("")
        if not self._batch_mode:
            self._set_busy(False)

    def _on_batch_end(self, count: int) -> None:
        self._log(f"[✓] 批量完成 ({count} 个)", LOG_OK)
        self.status_lbl.setText(f"批量完成 ({count} 个)")
        self._set_busy(False)

    def _on_trimmed(self, result: object, err: object) -> None:
        path = result if isinstance(result, str) else None
        if path and os.path.exists(path):
            self._log(f"[✂] 完成 → {os.path.basename(path)}", LOG_OK)
            self._show_detail(path)
            self.status_lbl.setText(f"完成 — {os.path.basename(path)}")
        else:
            self._log(f"[✗] 失败: {(err or '')[-200:]}", LOG_ERR)

    def _on_error(self, msg: str) -> None:
        self._log(f"[✗ 错误] {msg}", LOG_ERR)
        if "not a bot" in msg or "Sign in" in msg:
            self._log("    💡 在「认证」选 Firefox (需先在 Firefox 登录) 或用扩展导出 cookies.txt", LOG_INFO)

    # ---------------- 关闭 ----------------
    def _gather_settings(self) -> config.Settings:
        cb, cf = self._cookie_settings()
        return config.Settings(
            output_dir=self.dir_edit.text().strip() or config.default_output_dir(),
            format_label=self.fmt_box.currentText(),
            verify=bool(self.verify_cb.isChecked()),
            appearance=self.settings.appearance,
            cookies_browser=cb,
            cookies_file=cf,
            force=bool(self.force_cb.isChecked()),
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        try:
            config.save(self._gather_settings())
        except Exception:
            pass
        super().closeEvent(event)


def _app_icon_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "app.ico"


def main() -> None:
    # Windows 任务栏自定义图标: 不显式设 AppUserModelID, 任务栏会回退显示 python.exe
    # 默认图标而非本程序 logo. 设唯一 id 让任务栏/窗口正确分组并显示自定义图标.
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "niuma.ytdownloader.1")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    icon = QIcon(str(_app_icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)          # 标题栏 + 任务栏 + Alt-Tab 全局图标
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
