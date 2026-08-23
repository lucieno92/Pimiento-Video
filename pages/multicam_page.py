from core.sounds import play_done, play_error
from core.lang import LangManager, tr, TLabel, TButton, TGroupBox, TCheckBox
"""
Module 6 : Synchronisation multi-caméra — v3

Fonctionnalités :
- Import dossiers ET/OU fichiers individuels
- Tous les clips sur la timeline (non-syncs = orange)
- Pistes V séparées des pistes A (clips vidéo avec son = deux pistes)
- Sync TC ou waveform (son embarqué des vidéos inclus)
- Zoom horizontal sur la timeline
- Œil = masque dans le viewer (la piste V visible du dessus prend le dessus)
- Visualiseur : play+pause pour afficher une frame sans lire en continu
- Export FCPXML / AAF
"""

import os

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QPolygon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QFrame, QSizePolicy, QMessageBox, QProgressBar, QSplitter, QTextEdit,
    QLineEdit, QScrollArea, QGroupBox, QSlider, QComboBox, QToolButton,
    QAbstractScrollArea, QScrollBar,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.sync_engine import (
    ClipInfo, read_clip_info, tc_to_frames, frames_to_tc,
    HAS_NUMPY
)
from core.aaf_exporter import export_sync_aaf
from core.xmeml_exporter import export_xmeml
from core.ffmpeg_utils import get_ffmpeg_executable_path
from core.settings_store import get_manual_ffmpeg_path


VIDEO_EXT = {
    ".mp4", ".mov", ".mxf", ".avi", ".mkv", ".braw", ".r3d",
    ".mts", ".m2ts", ".m2t", ".dng",
}
AUDIO_EXT = {
    ".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac", ".bwf", ".w64",
}
_IGNORE_DIRS = {
    "THUMBNAIL", "THUMBNAILS", ".SPOTLIGHT-V100", ".TRASHES",
    "SYSTEM VOLUME INFORMATION", "$RECYCLE.BIN",
}

# Couleurs pistes
V_PALETTE = [
    QColor("#4a7fc1"), QColor("#357ab0"), QColor("#2a6099"),
    QColor("#1e4f82"), QColor("#163c6a"),
]
A_PALETTE = [
    QColor("#3aab6b"), QColor("#2d9058"), QColor("#237046"),
    QColor("#1a5535"), QColor("#123d26"),
]
COLOR_UNSYNCED = QColor("#c0392b")

RULER_H = 30
LABEL_W = 150
TRACK_H = 40
EYE_W   = 24


def _detect_fps(tracks):
    from collections import Counter
    vals = [round(c.fps * 100) / 100
            for _, clips, _ in tracks for c in clips if c.fps > 0]
    return Counter(vals).most_common(1)[0][0] if vals else 25.0


def scan_paths(paths: list) -> dict:
    """
    Scanne une liste de chemins (dossiers ou fichiers).
    Retourne {groupe_name: [path_str]} où groupe = nom du dossier ou
    "Individual files" pour les fichiers directement déposés.
    """
    groups = {}
    for path in paths:
        if os.path.isdir(path):
            name = os.path.basename(path)
            found = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d.upper() not in _IGNORE_DIRS]
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in VIDEO_EXT | AUDIO_EXT:
                        found.append(os.path.join(root, f))
            if found:
                groups[name] = groups.get(name, []) + found
        elif os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in VIDEO_EXT | AUDIO_EXT:
                groups.setdefault("Individual files", []).append(path)
    return groups


def build_tracks(raw_groups: dict, clips_by_path: dict) -> list:
    """
    Construit la liste de pistes à partir des groupes scannés.
    Format : [(track_name, [ClipInfo], is_video_track)]
    Chaque groupe donne UNE piste V et/ou UNE piste A.
    Les clips vidéo avec son embarqué apparaissent sur les deux.
    Les pistes V viennent en premier, les pistes A ensuite.
    """
    v_tracks = []
    a_tracks = []
    for group_name, paths in raw_groups.items():
        v_clips, a_clips = [], []
        for path in paths:
            clip = clips_by_path.get(path)
            if clip is None:
                continue
            if clip.is_video:
                # Clip vidéo → piste V
                v_clips.append(clip)
                # Si ce clip a une piste audio embarquée (duration > 0 suffit
                # comme heuristique — on vérifie le has_audio plus bas)
                if getattr(clip, "has_audio", True):
                    a_clip = ClipInfo(
                        path=clip.path,
                        name=clip.name,
                        track_label="A",
                        duration_frames=clip.duration_frames,
                        fps=clip.fps,
                        timecode_start=clip.timecode_start,
                        offset_frames=clip.offset_frames,
                        is_video=False,
                    )
                    a_clip.synced = getattr(clip, "synced", True)
                    a_clips.append(a_clip)
            else:
                a_clips.append(clip)

        if v_clips:
            v_tracks.append((group_name, v_clips, True))
        if a_clips:
            label = f"{group_name} – Audio"
            a_tracks.append((label, a_clips, False))

    return v_tracks + a_tracks


# ─── Workers ──────────────────────────────────────────────────────────────────

class ScanWorker(QThread):
    log_message    = Signal(str)
    progress_value = Signal(int)
    # result : {group_name: [path]}, {path: ClipInfo}
    finished_scan  = Signal(bool, dict, dict)

    def __init__(self, paths: list, parent=None):
        super().__init__(parent)
        self.paths = paths   # dossiers ET fichiers mélangés

    def run(self):
        groups = scan_paths(self.paths)
        if not groups:
            self.log_message.emit("⚠ No video or audio file found.")
            self.finished_scan.emit(False, {}, {})
            return

        total_files = sum(len(v) for v in groups.values())
        self.log_message.emit(
            f"{len(groups)} group(s) detected — {total_files} file(s) to analyse..."
        )

        clips_by_path = {}
        done = 0
        for group_name, paths in groups.items():
            self.log_message.emit(f"\n📁 {group_name} ({len(paths)} fichiers)")
            for path in paths:
                clip = read_clip_info(path, "?", 25.0)
                clip.is_video = os.path.splitext(path)[1].lower() in VIDEO_EXT
                clip.synced   = False   # not yet synced
                clips_by_path[path] = clip
                done += 1
                self.progress_value.emit(int(done / total_files * 100))

            tc_ok = sum(
                1 for p in paths
                if clips_by_path[p].timecode_start != "00:00:00:00"
            )
            self.log_message.emit(
                f"  → TC lisible : {tc_ok}/{len(paths)} fichiers"
            )
            if tc_ok < len(paths):
                self.log_message.emit(
                    f"  ⚠ {len(paths)-tc_ok} fichier(s) sans TC lisible "
                    "(will be placed at 00:00:00:00 in TC mode)"
                )

        self.log_message.emit(f"\n✔ Scan complete — {total_files} clip(s).")
        self.finished_scan.emit(True, groups, clips_by_path)


class SyncWorker(QThread):
    log_message    = Signal(str)
    progress_value = Signal(int)
    finished_sync  = Signal(bool, list, int, int)  # ok, tracks, earliest, total

    def __init__(self, tracks, method, ref_track_name, fps,
                 ffmpeg_exe, parent=None):
        super().__init__(parent)
        self.tracks         = tracks
        self.method         = method   # "tc" | "waveform"
        self.ref_track_name = ref_track_name
        self.fps            = fps
        self.ffmpeg_exe     = ffmpeg_exe
        self._stop          = False

    def stop(self): self._stop = True

    def run(self):
        fps = self.fps
        all_clips = [c for _, clips, _ in self.tracks for c in clips]

        if self.method == "tc":
            self.log_message.emit("Sync par timecode...")
            valid = [c for c in all_clips if c.timecode_start != "00:00:00:00"]

            if not valid:
                self.log_message.emit(
                    "⚠ No readable timecode found. "
                    "Clips will be placed at start of timeline."
                )
                for clip in all_clips:
                    clip.offset_frames = 0
                    clip.synced = False
            else:
                earliest = min(tc_to_frames(c.timecode_start, fps) for c in valid)
                for clip in all_clips:
                    start = tc_to_frames(clip.timecode_start, fps)
                    clip.offset_frames = start - earliest
                    clip.synced = clip.timecode_start != "00:00:00:00"
                    if not clip.synced:
                        self.log_message.emit(
                            f"  ⚠ {clip.name}: no TC → placed at 00:00:00:00"
                        )

        elif self.method == "waveform":
            if not HAS_NUMPY:
                self.log_message.emit("ERREUR : numpy non disponible.")
                self.finished_sync.emit(False, self.tracks, 0, 0)
                return

            from core.sync_engine import extract_audio_mono, compute_waveform_offset_frames
            import numpy as np
            SR = 8000

            # Piste de référence : préférer la piste demandée,
            # sinon la première piste qui a de l'audio extractible
            ref_clips = next(
                (clips for n, clips, _ in self.tracks if n == self.ref_track_name),
                None
            )
            if ref_clips is None:
                ref_clips = next(
                    (clips for _, clips, _ in self.tracks), []
                )

            self.log_message.emit(f"Extracting reference audio...")
            ref_parts = []
            for clip in ref_clips[:3]:   # max 3 clips de ref pour la vitesse
                a = extract_audio_mono(clip.path, self.ffmpeg_exe, SR)
                if a is not None and len(a) > 0:
                    ref_parts.append(a)
            if not ref_parts:
                self.log_message.emit("ERREUR : impossible d'extraire l'reference audio.")
                self.finished_sync.emit(False, self.tracks, 0, 0)
                return
            ref_audio = np.concatenate(ref_parts)

            # Offsets TC comme point de départ (meilleure précision initiale)
            valid_tc = [c for c in all_clips if c.timecode_start != "00:00:00:00"]
            if valid_tc:
                base_earliest = min(tc_to_frames(c.timecode_start, fps) for c in valid_tc)
            else:
                base_earliest = 0
            for clip in all_clips:
                clip.offset_frames = max(0, tc_to_frames(clip.timecode_start, fps) - base_earliest)

            total_tracks = len(self.tracks)
            for ti, (name, clips, _) in enumerate(self.tracks):
                if self._stop:
                    self.log_message.emit("Cancelled.")
                    self.finished_sync.emit(False, self.tracks, 0, 0)
                    return
                self.progress_value.emit(int(ti / total_tracks * 100))
                if clips is ref_clips:
                    for c in clips: c.synced = True
                    continue

                t_parts = []
                for clip in clips[:3]:
                    a = extract_audio_mono(clip.path, self.ffmpeg_exe, SR)
                    if a is not None and len(a) > 0:
                        t_parts.append(a)
                if not t_parts:
                    self.log_message.emit(f"[{name}] ⚠ pas d'audio → not synced.")
                    for c in clips: c.synced = False
                    continue

                target = np.concatenate(t_parts)
                self.log_message.emit(f"[{name}] cross-correlation...")
                wf = compute_waveform_offset_frames(ref_audio, target, SR, fps)
                for clip in clips:
                    clip.offset_frames = max(0, clip.offset_frames + wf)
                    clip.synced = True
                self.log_message.emit(
                    f"[{name}] offset = {wf:+d} fr ({wf/fps:+.3f} s)"
                )

        # Calcul earliest / total
        if all_clips:
            earliest = min(c.offset_frames for c in all_clips)
            for c in all_clips:
                c.offset_frames -= earliest
            total = max(c.offset_frames + c.duration_frames for c in all_clips)
        else:
            earliest, total = 0, 0

        self.progress_value.emit(100)
        self.log_message.emit("✔ Synchronisation complete.")
        self.finished_sync.emit(True, self.tracks, 0, total)


# ─── Timeline ─────────────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    clip_clicked   = Signal(object)
    playhead_moved = Signal(int)      # frame absolu (relatif au début)
    eye_toggled    = Signal(str, bool)  # track_name, visible

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks: list        = []   # [(name, [ClipInfo], is_video)]
        self.total_frames: int   = 1
        self.fps: float          = 25.0
        self.hidden: set         = set()
        self.selected_clip       = None
        self.playhead_frame: int = 0
        self.zoom: float         = 1.0   # 1.0 = tout visible, >1 = zoom avant
        self.scroll_px: int      = 0
        self._dragging           = False
        self._eye_btns: list     = []

        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#1a1a1a;")
        self.setMouseTracking(True)

    # ── API ─────────────────────────────────────────────────────────────

    def set_tracks(self, tracks, total_frames, fps):
        self.tracks       = tracks
        self.total_frames = max(total_frames, 1)
        self.fps          = fps
        self.playhead_frame = 0
        self.hidden.clear()
        self._rebuild_eyes()
        self.setMinimumHeight(RULER_H + max(len(tracks), 1) * TRACK_H + 4)
        self.update()

    scroll_changed = Signal(int, int)   # scroll_px, max_scroll_px

    def set_zoom(self, zoom: float):
        old_zoom = self.zoom
        self.zoom = max(0.1, zoom)
        # Centrer le zoom sur la tête de lecture
        W = self.width()
        canvas_old = (W - LABEL_W) * old_zoom
        canvas_new = (W - LABEL_W) * self.zoom
        if self.total_frames > 0:
            ph_ratio = self.playhead_frame / self.total_frames
            center    = (W - LABEL_W) / 2
            self.scroll_px = max(0, int(canvas_new * ph_ratio - center))
        max_scroll = max(0, int(canvas_new - (W - LABEL_W)))
        self.scroll_changed.emit(self.scroll_px, max_scroll)
        self.update()

    def set_scroll(self, px: int):
        self.scroll_px = px
        self.update()

    # ── Boutons œil ──────────────────────────────────────────────────────

    def _rebuild_eyes(self):
        for btn, _ in self._eye_btns:
            btn.deleteLater()
        self._eye_btns = []
        for i, (name, _, _) in enumerate(self.tracks):
            btn = QToolButton(self)
            btn.setText("👁")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedSize(EYE_W, EYE_W)
            btn.setToolTip(f"Masquer / afficher : {name}")
            btn.setStyleSheet(
                "QToolButton{border:none;background:transparent;font-size:12px;}"
                "QToolButton:!checked{color:#333;}"
            )
            btn.toggled.connect(
                lambda checked, n=name: self._on_eye(n, checked))
            self._eye_btns.append((btn, i))
        self._place_eyes()

    def _place_eyes(self):
        for btn, idx in self._eye_btns:
            y = RULER_H + idx * TRACK_H + (TRACK_H - EYE_W) // 2
            btn.move(2, y)
            btn.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_eyes()

    def _on_eye(self, name, checked):
        if checked:
            self.hidden.discard(name)
        else:
            self.hidden.add(name)
        self.eye_toggled.emit(name, checked)
        self.update()

    # ── Conversion frame ↔ pixel ─────────────────────────────────────────

    def _x_of_frame(self, frame: int) -> int:
        W = self.width()
        canvas_w = (W - LABEL_W) * self.zoom
        return LABEL_W + int(canvas_w * frame / self.total_frames) - self.scroll_px

    def _frame_of_x(self, x: int) -> int:
        W = self.width()
        canvas_w = max((W - LABEL_W) * self.zoom, 1)
        ratio = max(0.0, min(1.0, (x - LABEL_W + self.scroll_px) / canvas_w))
        return int(ratio * self.total_frames)

    # ── Dessin ───────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor("#1a1a1a"))

        if not self.tracks:
            painter.setPen(QColor("#555"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Scan folders or files, then synchronise.")
            return

        # Ruler
        painter.setPen(QPen(QColor("#444"), 1))
        painter.drawLine(LABEL_W, RULER_H, W, RULER_H)
        for i in range(11):
            f  = int(self.total_frames * i / 10)
            x  = self._x_of_frame(f)
            if LABEL_W <= x <= W:
                painter.setPen(QPen(QColor("#333"), 1))
                painter.drawLine(x, 0, x, H)
                painter.setPen(QColor("#aaa"))
                painter.setFont(QFont("Courier", 7))
                painter.drawText(x + 2, RULER_H - 4, frames_to_tc(f, self.fps))

        # Séparateur V / A
        n_video = sum(1 for _, _, iv in self.tracks if iv)
        if n_video and n_video < len(self.tracks):
            sep_y = RULER_H + n_video * TRACK_H
            painter.setPen(QPen(QColor("#555"), 2, Qt.DashLine))
            painter.drawLine(0, sep_y, W, sep_y)

        # Pistes
        for idx, (name, clips, is_video) in enumerate(self.tracks):
            palette = V_PALETTE if is_video else A_PALETTE
            color   = palette[idx % len(palette)]
            hidden  = name in self.hidden
            y0      = RULER_H + idx * TRACK_H

            bg = QColor(30, 30, 30) if hidden else QColor(
                color.red(), color.green(), color.blue(), 18)
            painter.fillRect(LABEL_W, y0, W - LABEL_W, TRACK_H, bg)
            painter.setPen(QPen(QColor("#2a2a2a"), 1))
            painter.drawLine(0, y0 + TRACK_H, W, y0 + TRACK_H)

            lc = QColor("#333") if hidden else color
            painter.setPen(lc)
            painter.setFont(QFont("Arial", 7, QFont.Bold))
            painter.drawText(EYE_W + 4, y0, LABEL_W - EYE_W - 6, TRACK_H,
                             Qt.AlignVCenter | Qt.TextSingleLine, name)

            if hidden:
                continue

            for clip in clips:
                synced = getattr(clip, "synced", True)
                x0 = self._x_of_frame(clip.offset_frames)
                cw = max(2, self._x_of_frame(clip.offset_frames + clip.duration_frames) - x0)
                ch = TRACK_H - 6

                # Couleur : synced → couleur piste, non-synced → rouge/orange
                fill = color if synced else COLOR_UNSYNCED
                if clip is self.selected_clip:
                    fill = fill.lighter(150)

                painter.fillRect(x0, y0 + 3, cw, ch, fill)
                painter.setPen(QPen(fill.darker(140), 1))
                painter.drawRect(x0, y0 + 3, cw, ch)
                if cw > 20:
                    painter.setPen(Qt.white)
                    painter.setFont(QFont("Arial", 7))
                    painter.drawText(x0 + 2, y0 + 3, cw - 4, ch,
                                     Qt.AlignVCenter | Qt.TextSingleLine, clip.name)
                    if not synced and cw > 50:
                        painter.setPen(QColor("#ffcc00"))
                        painter.setFont(QFont("Arial", 6))
                        painter.drawText(x0 + 2, y0 + 3 + ch // 2,
                                         cw - 4, ch // 2,
                                         Qt.AlignVCenter | Qt.TextSingleLine,
                                         "⚠ not synced")

        # Tête de lecture
        xph = self._x_of_frame(self.playhead_frame)
        if LABEL_W <= xph <= W:
            painter.setPen(QPen(QColor("#ff3333"), 2))
            painter.drawLine(xph, 0, xph, H)
            painter.setBrush(QColor("#ff3333"))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygon([
                QPoint(xph - 7, 0), QPoint(xph + 7, 0), QPoint(xph, 12)
            ]))

        painter.end()

    # ── Souris ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self.tracks or event.pos().x() < LABEL_W:
            return
        self._dragging = True
        self.playhead_frame = self._frame_of_x(event.pos().x())
        self.playhead_moved.emit(self.playhead_frame)
        lane = (event.pos().y() - RULER_H) // TRACK_H
        if 0 <= lane < len(self.tracks):
            _, clips, _ = self.tracks[lane]
            for clip in clips:
                x0 = self._x_of_frame(clip.offset_frames)
                x1 = self._x_of_frame(clip.offset_frames + clip.duration_frames)
                if x0 <= event.pos().x() <= x1:
                    self.selected_clip = clip
                    self.clip_clicked.emit(clip)
                    break
        self.update()

    def mouseMoveEvent(self, event):
        if self._dragging and event.pos().x() >= LABEL_W:
            self.playhead_frame = self._frame_of_x(event.pos().x())
            self.playhead_moved.emit(self.playhead_frame)
            self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False


# ─── Zone de drop mixte ───────────────────────────────────────────────────────

class DropZone(QFrame):
    """Accepte des dossiers ET des fichiers."""
    items_dropped = Signal(list)   # liste de chemins (dossiers ou fichiers)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        l = QVBoxLayout(self)
        lbl = QLabel(
            "Drop memory card folders here\n"
            "and/or video/audio files directly"
        )
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("border: none; color: #666666;")
        l.addWidget(lbl)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        self.setStyleSheet("QFrame { border: 2px solid #ff6b45; border-radius: 8px; background: #252a42; }")
    def dragLeaveEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")

    def dropEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        paths = [u.toLocalFile() for u in e.mimeData().urls()
                 if u.toLocalFile()]
        if paths:
            self.items_dropped.emit(paths)


# ─── Page principale ──────────────────────────────────────────────────────────

class MulticamPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_paths: list       = []   # dossiers + fichiers déposés
        self.raw_groups: dict      = {}   # {group_name: [path]}
        self.clips_by_path: dict   = {}   # {path: ClipInfo}
        self.tracks: list          = []   # [(name, [ClipInfo], is_video)]
        self.total_frames: int     = 0
        self.fps: float            = 25.0
        self.scan_worker           = None
        self.sync_worker_obj       = None
        self._pending_seek_ms      = None
        self._is_playing           = False
        self._current_v_clip       = None
        self._last_frame           = 0
        self._pending_frame        = 0
        self._build_ui()

    # ── Construction de l'UI ─────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)

        top = QHBoxLayout()
        back = self._t_back = QPushButton(tr("back")); _ = self._t_back
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch()
        root.addLayout(top)

        self._t_title = QLabel(tr("mc_title"))
        self._t_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(self._t_title)

        h = QSplitter(Qt.Horizontal)

        # Gauche
        left = QWidget()
        left.setMaximumWidth(290)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        self._build_left(ll)
        h.addWidget(left)

        # Droite : viewer haut + timeline bas
        v = QSplitter(Qt.Vertical)
        v.addWidget(self._build_viewer())
        v.addWidget(self._build_timeline_panel())
        v.setStretchFactor(0, 1)
        v.setStretchFactor(1, 1)
        h.addWidget(v)

        h.setStretchFactor(0, 1)
        h.setStretchFactor(1, 3)
        root.addWidget(h)

    def _build_left(self, ll):
        self.drop_zone = DropZone()
        self.drop_zone.items_dropped.connect(self._add_paths)
        ll.addWidget(self.drop_zone)

        row = QHBoxLayout()
        b_folder = QPushButton("+ Dossier")
        b_folder.clicked.connect(self._browse_folder)
        row.addWidget(b_folder)
        b_files = TButton("mc_add_files")
        b_files.clicked.connect(self._browse_files)
        row.addWidget(b_files)
        ll.addLayout(row)

        ll.addWidget(QLabel("Loaded items:"))
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        self._items_container = QWidget()
        self._items_layout    = QVBoxLayout(self._items_container)
        self._items_layout.setAlignment(Qt.AlignTop)
        sc.setWidget(self._items_container)
        sc.setFixedHeight(80)
        ll.addWidget(sc)

        row2 = QHBoxLayout()
        clear_btn = TButton("clear_all")
        clear_btn.clicked.connect(self._clear_all)
        row2.addWidget(clear_btn)
        self.scan_btn = TButton("mc_scan")
        self.scan_btn.setMinimumHeight(34)
        self.scan_btn.clicked.connect(self._start_scan)
        row2.addWidget(self.scan_btn)
        ll.addLayout(row2)

        self.progress_bar = QProgressBar()
        ll.addWidget(self.progress_bar)

        sg = TGroupBox("sync_group")
        sgl = QVBoxLayout(sg)
        mr = QHBoxLayout()
        mr.addWidget(TLabel("method"))
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Timecode (embedded TC)",
            "Waveform (experimental)",
        ])
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        mr.addWidget(self.method_combo)
        sgl.addLayout(mr)
        self.ref_label = TLabel("ref_track")
        self.ref_combo  = QComboBox()
        self.ref_label.setVisible(False)
        self.ref_combo.setVisible(False)
        sgl.addWidget(self.ref_label)
        sgl.addWidget(self.ref_combo)
        ar = QHBoxLayout()
        self.sync_btn = TButton("mc_sync_btn")
        self.sync_btn.setMinimumHeight(34)
        self.sync_btn.setEnabled(False)
        self.sync_btn.clicked.connect(self._start_sync)
        ar.addWidget(self.sync_btn)
        self.cancel_btn = TButton("cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_sync)
        ar.addWidget(self.cancel_btn)
        sgl.addLayout(ar)
        ll.addWidget(sg)

        ll.addWidget(TLabel("journal"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        ll.addWidget(self.log_output)

        eg = QGroupBox("Export")
        egl = QVBoxLayout(eg)
        nr = QHBoxLayout()
        nr.addWidget(TLabel("sequence"))
        self.seq_name_input = QLineEdit("Sync Sequence")
        nr.addWidget(self.seq_name_input)
        egl.addLayout(nr)
        for label, fmt in [
            ("XML — Premiere Pro / DaVinci Resolve", "xmeml"),
            ("AAF — Avid Media Composer", "aaf"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, f=fmt: self._export(f))
            egl.addWidget(btn)
        ll.addWidget(eg)

    def _build_viewer(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        self.clip_info_label = QLabel("Click a clip or drag the playhead.")
        self.clip_info_label.setStyleSheet("color:#888;font-size:11px;")
        l.addWidget(self.clip_info_label)
        self.tc_label = QLabel("--:--:--:--")
        self.tc_label.setAlignment(Qt.AlignCenter)
        self.tc_label.setStyleSheet(
            "color:#ffffff;font-size:22px;font-family:Courier;font-weight:bold;"
            "background:#111;padding:4px;border-radius:4px;"
        )
        l.addWidget(self.tc_label)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(160)
        self.video_widget.setStyleSheet("background:black;")
        l.addWidget(self.video_widget, stretch=1)

        ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(32)
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.play_btn)
        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedWidth(32)
        self.stop_btn.clicked.connect(self._stop_all)
        ctrl.addWidget(self.stop_btn)
        # Slider en FRAMES (pas en ms) — jamais connecté à player.positionChanged
        # ou player.durationChanged → Qt ne peut pas le remettre à 0
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderMoved.connect(self._on_seek_slider_moved)
        ctrl.addWidget(self.seek_slider)
        vol_label = QLabel("Vol:")
        vol_label.setStyleSheet("font-size:10px;")
        ctrl.addWidget(vol_label)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(70)
        self.vol_slider.valueChanged.connect(self._update_volumes)
        ctrl.addWidget(self.vol_slider)
        l.addLayout(ctrl)

        # Player vidéo — on NE connecte PAS durationChanged ni positionChanged
        # au slider : Qt émet durationChanged(0) lors de setSource() ce qui
        # forçait setRange(0,0) → valeur à 0. Le slider est géré manuellement.
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.audio_out.setVolume(0.0)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.playbackStateChanged.connect(
            lambda s: self.play_btn.setText(
                "⏸" if s == QMediaPlayer.PlaybackState.PlayingState else "▶"))
        self.player.mediaStatusChanged.connect(self._on_video_media_status)
        self._pending_seek_ms = None

        # Players audio (un par piste audio, max 6) — jouent tous simultanément
        MAX_AUDIO = 6
        self._audio_players  = []   # [(QMediaPlayer, QAudioOutput, track_name)]
        for _ in range(MAX_AUDIO):
            ao  = QAudioOutput(self)
            ao.setVolume(0.8)
            ap  = QMediaPlayer(self)
            ap.setAudioOutput(ao)
            self._audio_players.append([ap, ao, None])   # track_name = None tant qu'on n'a pas assigné

        return w

    def _build_timeline_panel(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        # Contrôles zoom
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(TLabel("zoom"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)   # 0.1x à 5x (×10)
        self.zoom_slider.setValue(10)         # 1.0x au départ
        self.zoom_slider.setFixedWidth(160)
        self.zoom_slider.valueChanged.connect(
            lambda v: self.timeline.set_zoom(v / 10.0))
        zoom_row.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("×1.0")
        self.zoom_slider.valueChanged.connect(
            lambda v: self.zoom_label.setText(f"×{v/10:.1f}"))
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addStretch()
        l.addLayout(zoom_row)

        self.timeline = TimelineWidget()
        self.timeline.clip_clicked.connect(self._on_clip_clicked)
        self.timeline.playhead_moved.connect(self._on_playhead_moved)
        self.timeline.eye_toggled.connect(self._on_eye_toggled)
        self.timeline.scroll_changed.connect(self._on_scroll_changed)
        l.addWidget(self.timeline)

        # Scrollbar horizontale pour le zoom
        self.h_scroll = QScrollBar(Qt.Horizontal)
        self.h_scroll.setRange(0, 0)
        self.h_scroll.valueChanged.connect(self.timeline.set_scroll)
        l.addWidget(self.h_scroll)
        return w

    def _on_scroll_changed(self, scroll_px: int, max_scroll: int):
        """Met à jour la scrollbar quand le zoom change."""
        # Bloquer les signaux pour éviter la boucle scroll→timeline→scroll
        self.h_scroll.blockSignals(True)
        self.h_scroll.setRange(0, max_scroll)
        self.h_scroll.setValue(scroll_px)
        self.h_scroll.blockSignals(False)

    # ── Import ───────────────────────────────────────────────────────────

    def _add_paths(self, paths: list):
        for path in paths:
            if path not in self.raw_paths:
                self.raw_paths.append(path)
                name = os.path.basename(path)
                icon = "📁" if os.path.isdir(path) else "🎬"
                row = QHBoxLayout()
                lbl = QLabel(f"{icon} {name}")
                lbl.setToolTip(path)
                row.addWidget(lbl)
                rm = QPushButton("✕")
                rm.setFixedWidth(22)
                rm.clicked.connect(lambda _, p=path: self._remove_path(p))
                row.addWidget(rm)
                ctn = QWidget()
                ctn.setLayout(row)
                ctn.setProperty("path", path)
                self._items_layout.addWidget(ctn)

    def _remove_path(self, path):
        if path in self.raw_paths:
            self.raw_paths.remove(path)
        for i in range(self._items_layout.count()):
            item = self._items_layout.itemAt(i)
            if item and item.widget() and item.widget().property("path") == path:
                item.widget().deleteLater()
                break

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir un dossier de carte")
        if folder:
            self._add_paths([folder])

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select video/audio files", "",
            "Video and audio (*.mp4 *.mov *.mxf *.avi *.mkv *.wav *.mp3 "
            "*.m4a *.aif *.braw *.r3d);;Tous (*.*)"
        )
        if paths:
            self._add_paths(paths)

    def _clear_all(self):
        self.raw_paths.clear()
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.tracks = []
        self.timeline.set_tracks([], 1, 25.0)
        self.log_output.clear()

    # ── Scan ─────────────────────────────────────────────────────────────

    def _start_scan(self):
        if not self.raw_paths:
            QMessageBox.warning(self, "Nothing to scan",
                                "Ajoute des dossiers ou des fichiers.")
            return
        self.scan_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        self.scan_worker = ScanWorker(paths=list(self.raw_paths))
        self.scan_worker.log_message.connect(self.log_output.append)
        self.scan_worker.progress_value.connect(self.progress_bar.setValue)
        self.scan_worker.finished_scan.connect(self._on_scan_finished)
        self.scan_worker.start()

    def _on_scan_finished(self, success, raw_groups, clips_by_path):
        self.scan_btn.setEnabled(True)
        if not success:
            return
        self.raw_groups    = raw_groups
        self.clips_by_path = clips_by_path
        self.fps = _detect_fps(
            [("all", list(clips_by_path.values()), True)])

        # Peupler combo référence waveform
        self.ref_combo.clear()
        for name in raw_groups:
            self.ref_combo.addItem(name)

        total = sum(len(v) for v in raw_groups.values())
        self.log_output.append(
            f"\n{total} clips — FPS : {self.fps}\n"
            "Choose sync method and click ▶ Synchronise."
        )
        self.sync_btn.setEnabled(True)

    # ── Synchronisation ───────────────────────────────────────────────────

    def _on_method_changed(self, text):
        wf = "forme" in text.lower()
        self.ref_label.setVisible(wf)
        self.ref_combo.setVisible(wf)

    def _start_sync(self):
        if not self.raw_groups:
            return
        # Construire les pistes V/A
        self.tracks = build_tracks(self.raw_groups, self.clips_by_path)
        method = "waveform" if "forme" in self.method_combo.currentText().lower() else "tc"
        ref    = self.ref_combo.currentText()
        ffmpeg = get_ffmpeg_executable_path(get_manual_ffmpeg_path())

        self.sync_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_output.append(f"\n▶ Synchronisation ({method})...")

        self.sync_worker_obj = SyncWorker(
            tracks=self.tracks,
            method=method,
            ref_track_name=ref,
            fps=self.fps,
            ffmpeg_exe=ffmpeg,
        )
        self.sync_worker_obj.log_message.connect(self.log_output.append)
        self.sync_worker_obj.progress_value.connect(self.progress_bar.setValue)
        self.sync_worker_obj.finished_sync.connect(self._on_sync_finished)
        self.sync_worker_obj.start()

    def _cancel_sync(self):
        if self.sync_worker_obj:
            self.sync_worker_obj.stop()
        self.sync_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_sync_finished(self, success, tracks, earliest, total):
        if success:
            play_done()
        else:
            play_error()
        self.sync_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if not success:
            return
        self.tracks       = tracks
        self.total_frames = total
        # Ajuster la scrollbar en fonction du zoom
        self.h_scroll.setRange(0, max(0, int(total * 10)))
        self.timeline.set_tracks(tracks, total, self.fps)
        self.seek_slider.setRange(0, total)   # slider en frames

        n_ok  = sum(getattr(c, "synced", True)
                    for _, clips, _ in tracks for c in clips)
        n_all = sum(len(clips) for _, clips, _ in tracks)
        self.log_output.append(
            f"Timeline: {n_ok}/{n_all} clips synchronised  "
            f"| Duration: {frames_to_tc(total, self.fps)}"
        )
        if n_ok < n_all:
            self.log_output.append(
                f"⚠ {n_all - n_ok} clip(s) not synchronised "
                "apparaissent en rouge sur la timeline."
            )
        # Charger et afficher la première frame dès que la synchro est faite
        self._current_v_clip = None
        self._seek_to_frame(0)

    # ── Visualiseur ───────────────────────────────────────────────────────
    # Architecture :
    #   self._is_playing        : True si en cours de lecture
    #   self._current_v_clip    : ClipInfo actuellement chargé dans self.player
    #   _seek_to_frame(frame)   : positionne tous les players à cette frame
    #                              (sans changer l'état play/pause)
    # Règles :
    #   - Jamais setSource() pendant _is_playing (évite reset + écran noir)
    #   - _on_eye_toggled pendant lecture = mute/unmute audio seulement
    #   - _on_eye_toggled hors lecture = _seek_to_frame pour switcher la vidéo

    def _find_video_clip_at(self, frame: int):
        """Clip vidéo de la piste visible la plus haute à cette frame."""
        for name, clips, is_video in self.tracks:
            if not is_video or name in self.timeline.hidden:
                continue
            for clip in clips:
                if clip.offset_frames <= frame < clip.offset_frames + clip.duration_frames:
                    return clip
        return None

    def _find_audio_clips_at(self, frame: int):
        """Un clip par piste audio à cette frame (dans l'ordre des pistes)."""
        result = []
        for name, clips, is_video in self.tracks:
            if is_video:
                continue
            for clip in clips:
                if clip.offset_frames <= frame < clip.offset_frames + clip.duration_frames:
                    result.append((name, clip))
                    break
        return result

    def _seek_to_frame(self, frame: int):
        """Positionne tous les players à frame — sans changer l'état play/pause."""
        self._pending_frame = frame   # mémoriser la frame cible pour restauration

        # ── Vidéo ──────────────────────────────────────────────────────
        v_clip = self._find_video_clip_at(frame)
        if v_clip:
            ms = int((frame - v_clip.offset_frames) / max(self.fps, 1) * 1000)
            src = QUrl.fromLocalFile(v_clip.path)
            if self.player.source() == src:
                self.player.setPosition(ms)
                if not self._is_playing:
                    self.player.play()
                    QTimer.singleShot(100, self._restore_after_preview)
            else:
                self._current_v_clip    = v_clip
                self._pending_seek_ms   = ms
                self.player.setSource(src)
            self.clip_info_label.setText(
                f"{v_clip.name}  |  {frames_to_tc(frame, self.fps)}")

        # ── Audio ──────────────────────────────────────────────────────
        a_clips = self._find_audio_clips_at(frame)
        for slot, (ap, ao, _) in enumerate(self._audio_players):
            if slot < len(a_clips):
                name, clip = a_clips[slot]
                self._audio_players[slot][2] = name
                vol = 0.0 if name in self.timeline.hidden else self.vol_slider.value() / 100
                ao.setVolume(vol)
                a_ms = int((frame - clip.offset_frames) / max(self.fps, 1) * 1000)
                ap.setSource(QUrl.fromLocalFile(clip.path))
                ap.setPosition(a_ms)
            else:
                self._audio_players[slot][2] = None
                ao.setVolume(0.0)

    def _restore_position_indicators(self):
        """Force tous les indicateurs visuels à _last_frame — appelé après
        chaque opération Qt pour neutraliser tout positionChanged(0) parasite."""
        f = self._last_frame
        if self.timeline.playhead_frame != f:
            self.timeline.playhead_frame = f
            self.timeline.update()
        self.tc_label.setText(frames_to_tc(f, self.fps))
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(f)

    def _restore_after_preview(self):
        print(f"[DEBUG restore_preview] _last_frame={self._last_frame}, playhead={self.timeline.playhead_frame}")
        self.player.pause()
        self._restore_position_indicators()
        print(f"[DEBUG restore_preview AFTER] playhead={self.timeline.playhead_frame}")

    def _on_video_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pending_seek_ms is not None:
            ms   = self._pending_seek_ms
            self._pending_seek_ms = None
            # Forcer le range du slider (en frames) et sa valeur correcte
            frame = getattr(self, "_pending_frame", self._last_frame)
            self.seek_slider.setValue(frame)
            self.player.setPosition(ms)
            if self._is_playing:
                self.player.play()
                for ap, ao, _ in self._audio_players:
                    if ao.volume() > 0:
                        ap.play()
            else:
                self.player.play()
                QTimer.singleShot(100, self._restore_after_preview)

    def _on_player_position_changed(self, ms: int):
        if not self._is_playing:
            if ms < 1000:  # log seulement les valeurs suspectes proches de 0
                print(f"[DEBUG posChanged] ms={ms} IGNORÉ (_is_playing=False, _last_frame={self._last_frame})")
            return
        if self._current_v_clip:
            frame = self._current_v_clip.offset_frames + int(ms / 1000 * self.fps)
            self._last_frame = frame
            self.timeline.playhead_frame = frame
            self.timeline.update()
            self.tc_label.setText(frames_to_tc(frame, self.fps))
            if not self.seek_slider.isSliderDown():
                self.seek_slider.setValue(frame)

    def _on_clip_clicked(self, clip):
        self.clip_info_label.setText(
            f"{clip.name}  |  TC : {clip.timecode_start}  |  "
            f"{'Video' if clip.is_video else 'Audio'}"
        )
        self._seek_to_frame(clip.offset_frames)

    def _on_playhead_moved(self, frame: int):
        """Déplacement manuel — met à jour _last_frame."""
        self._last_frame = frame
        was_playing = self._is_playing
        if was_playing:
            self._is_playing = False
            self.player.pause()
            for ap, ao, _ in self._audio_players:
                ap.pause()
        self._seek_to_frame(frame)
        if was_playing:
            QTimer.singleShot(120, self._resume_playback)

    def _resume_playback(self):
        self._is_playing = True
        self.player.play()
        for ap, ao, _ in self._audio_players:
            if ao.volume() > 0:
                ap.play()

    def _on_eye_toggled(self, name: str, visible: bool):
        for item in self._audio_players:
            if item[2] == name:
                item[1].setVolume(0.0 if not visible else self.vol_slider.value() / 100)
        if not self._is_playing:
            for track_name, clips, is_video in self.tracks:
                if track_name == name and is_video:
                    print(f"[DEBUG eye_toggled] name={name}, _last_frame={self._last_frame}, playhead={self.timeline.playhead_frame}")
                    self.timeline.playhead_frame = self._last_frame
                    self.timeline.update()
                    self.tc_label.setText(frames_to_tc(self._last_frame, self.fps))
                    self._seek_to_frame(self._last_frame)
                    print(f"[DEBUG eye_toggled AFTER seek] _last_frame={self._last_frame}, playhead={self.timeline.playhead_frame}")
                    return

    def _toggle_play(self):
        if self._is_playing:
            self._is_playing = False
            self.player.pause()
            for ap, ao, _ in self._audio_players:
                ap.pause()
            print(f"[DEBUG pause] _last_frame={self._last_frame}")
        else:
            if not self.player.source().isValid() or self.player.source().isEmpty():
                self._pending_seek_ms = 0
                self._current_v_clip  = self._find_video_clip_at(self.timeline.playhead_frame)
                if self._current_v_clip:
                    self._seek_to_frame(self.timeline.playhead_frame)
                self._is_playing = True
                return
            self._is_playing = True
            self.player.play()
            for ap, ao, _ in self._audio_players:
                if ao.volume() > 0:
                    ap.play()

    def _stop_all(self):
        print(f"[DEBUG stop] _last_frame={self._last_frame}, _is_playing={self._is_playing}")
        self._is_playing = False
        self.player.pause()
        for ap, ao, _ in self._audio_players:
            ap.pause()
        print(f"[DEBUG stop AFTER pause] _last_frame={self._last_frame}")

    def _on_seek_slider_moved(self, frame: int):
        """Déplacement du slider par l'utilisateur (en frames)."""
        self._last_frame = frame
        self.timeline.playhead_frame = frame
        self.timeline.update()
        self.tc_label.setText(frames_to_tc(frame, self.fps))
        was_playing = self._is_playing
        if was_playing:
            self._is_playing = False
            self.player.pause()
            for ap, ao, _ in self._audio_players:
                ap.pause()
        self._seek_to_frame(frame)
        if was_playing:
            QTimer.singleShot(120, self._resume_playback)

    def _update_volumes(self, value: int):
        vol = value / 100
        for ap, ao, name in self._audio_players:
            if name and name not in self.timeline.hidden:
                ao.setVolume(vol)

    # ── Export ────────────────────────────────────────────────────────────

    def _export(self, fmt):
        if not self.tracks or self.total_frames == 0:
            QMessageBox.warning(self, "Nothing to export",
                                "Lance d'abord le scan et la synchronisation.")
            return
        seq = self.seq_name_input.text().strip() or "Sync Sequence"
        if fmt == "xmeml":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exporter en XML (Premiere / Resolve)", seq,
                "Final Cut Pro XML (*.xml)"
            )
            if not path: return
            tracks_data = [(n, clips) for n, clips, _ in self.tracks]
            ok, err = export_xmeml(
                output_path=path, tracks_data=tracks_data,
                fps=self.fps, sequence_name=seq)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Exporter en AAF (Avid)", seq, "AAF (*.aaf)")
            if not path: return
            all_clips = [c for _, clips, _ in self.tracks for c in clips]
            ok, err = export_sync_aaf(
                output_path=path, clips=all_clips,
                fps=self.fps, sequence_name=seq)
            if not ok and "pyaaf2" in err:
                QMessageBox.critical(
                    self, "pyaaf2 not installed",
                    "Lance dans ton terminal :\n    pip install pyaaf2\n\n"
                    "Puis relance et retente l'export."
                )
                return
        if ok:
            QMessageBox.information(self, "Export successful",
                                    f"File saved:\n{path}")
        else:
            QMessageBox.critical(self, "Erreur d'export", err)

    def set_lang(self, lang):
        from core.lang import tr, LangManager
        LangManager.get().current = lang
        if hasattr(self, '_t_title'):     self._t_title.setText(tr("mc_title"))
        if hasattr(self, '_t_back'):      self._t_back.setText(tr("back"))
        if hasattr(self, 'scan_btn'):     self.scan_btn.setText(tr("mc_scan"))
        if hasattr(self, 'sync_btn'):     self.sync_btn.setText(tr("mc_sync_btn"))
        if hasattr(self, 'cancel_btn'):   self.cancel_btn.setText(tr("cancel"))

