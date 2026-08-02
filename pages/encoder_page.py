from core.sounds import play_done, play_error
from core.lang import LangManager, tr, TLabel, TButton, TGroupBox, TCheckBox
"""
Module 3 : Encodeur (type Shutter Encoder)

Glisser une ou plusieurs vidéos/photos, choisir une catégorie + un format de
sortie (montage, diffusion/broadcast, web, audio seul, suite d'images,
photo/image, ou simple réencapsulation), un conteneur, ajuster résolution et
frame rate (préréglages ou valeurs personnalisées via "Custom..."),
renommer/organiser la sortie (préfixe, suffixe, dossier par vidéo,
suppression des sources), prévisualiser le rush sélectionné, et lancer
l'encodage. Basé directement sur FFmpeg (le même FFmpeg embarqué utilisé
par le module Téléchargement).

Note sur les codecs broadcast pro (XDCAM, AVC-Intra, XAVC) : FFmpeg standard
ne peut pas reproduire ces formats propriétaires à l'identique (encodeurs
dédiés Sony/Panasonic) ; ils sont ici approximés (même débit, même chroma,
même principe tout-intra) et clairement marqués "(approx.)".

Note sur l'aperçu vidéo : la lecture utilise le décodeur multimédia intégré
à Windows (Windows Media Foundation) via Qt Multimedia. Il lit très bien le
MP4/H.264 classique, mais ne saura probablement pas prévisualiser certains
formats caméra pro bruts (BRAW, R3D, certains MXF) — l'encodage, lui, passe
par FFmpeg (un moteur de décodage totalement différent) et fonctionnera
quand même très bien sur ces fichiers même si l'aperçu reste noir.
"""

import os
import re
import subprocess

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QComboBox, QListWidget, QAbstractItemView, QProgressBar, QTextEdit,
    QGroupBox, QFrame, QMessageBox, QLineEdit, QSplitter, QSlider, QCheckBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None

from core.ffmpeg_utils import get_ffmpeg_executable_path
from core.settings_store import get_manual_ffmpeg_path
from pages.mediainfo_page import format_duration


# Chaque préréglage : ext (extension par défaut, peut être remplacée par le
# conteneur choisi dans l'UI pour les catégories qui le permettent), vcodec
# (liste d'arguments ffmpeg, ou None si pas de vidéo en sortie), acodec
# (idem, ou None si pas d'audio), image_sequence (True si l'export produit
# une suite d'images numérotées).
PRESETS = {
    "Editing codecs": {
        "Apple ProRes 422 Proxy": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "0"], "acodec": ["-c:a", "pcm_s16le"]},
        "Apple ProRes 422 LT": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "1"], "acodec": ["-c:a", "pcm_s16le"]},
        "Apple ProRes 422": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "2"], "acodec": ["-c:a", "pcm_s16le"]},
        "Apple ProRes 422 HQ": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "3"], "acodec": ["-c:a", "pcm_s16le"]},
        "Apple ProRes 4444": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "4"], "acodec": ["-c:a", "pcm_s16le"]},
        "Apple ProRes 4444 XQ": {"ext": "mov", "vcodec": ["-c:v", "prores_ks", "-profile:v", "5"], "acodec": ["-c:a", "pcm_s16le"]},
        "DNxHD 36 (1080p, fixed)": {"ext": "mov", "vcodec": ["-c:v", "dnxhd", "-b:v", "36M"], "acodec": ["-c:a", "pcm_s16le"]},
        "DNxHR LB (low bandwidth)": {"ext": "mov", "vcodec": ["-c:v", "dnxhd", "-profile:v", "dnxhr_lb"], "acodec": ["-c:a", "pcm_s16le"]},
        "DNxHR SQ (standard)": {"ext": "mov", "vcodec": ["-c:v", "dnxhd", "-profile:v", "dnxhr_sq"], "acodec": ["-c:a", "pcm_s16le"]},
        "DNxHR HQ (high quality)": {"ext": "mov", "vcodec": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq"], "acodec": ["-c:a", "pcm_s16le"]},
        "DNxHR HQX (10-bit)": {"ext": "mov", "vcodec": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le"], "acodec": ["-c:a", "pcm_s16le"]},
        "GoPro CineForm": {"ext": "mov", "vcodec": ["-c:v", "cfhd"], "acodec": ["-c:a", "pcm_s16le"]},
        "QuickTime Animation (RLE)": {"ext": "mov", "vcodec": ["-c:v", "qtrle"], "acodec": ["-c:a", "pcm_s16le"]},
        "Uncompressed 10-bit (v210)": {"ext": "mov", "vcodec": ["-c:v", "v210"], "acodec": ["-c:a", "pcm_s16le"]},
    },
    "Output codecs": {
        "H.264 (MP4)": {"ext": "mp4", "vcodec": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"], "acodec": ["-c:a", "aac", "-b:a", "192k"]},
        "H.265 / HEVC (MP4)": {"ext": "mp4", "vcodec": ["-c:v", "libx265", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"], "acodec": ["-c:a", "aac", "-b:a", "192k"]},
        "H.266 / VVC (MP4)": {"ext": "mp4", "vcodec": ["-c:v", "libvvenc", "-q", "32"], "acodec": ["-c:a", "aac", "-b:a", "192k"], "may_be_unavailable": True},
        "VP8 (WebM)": {"ext": "webm", "vcodec": ["-c:v", "libvpx", "-crf", "10", "-b:v", "1M"], "acodec": ["-c:a", "libvorbis"]},
        "VP9 (WebM)": {"ext": "webm", "vcodec": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0"], "acodec": ["-c:a", "libopus"]},
        "AV1 (MP4)": {"ext": "mp4", "vcodec": ["-c:v", "libaom-av1", "-crf", "30", "-b:v", "0"], "acodec": ["-c:a", "aac", "-b:a", "192k"]},
    },
    "Broadcast codecs": {
        "XDCAM HD422 50 Mb/s": {"ext": "mxf", "vcodec": ["-c:v", "mpeg2video", "-pix_fmt", "yuv422p", "-b:v", "50M"], "acodec": ["-c:a", "pcm_s16le"]},
        "XDCAM HD 35 Mb/s": {"ext": "mxf", "vcodec": ["-c:v", "mpeg2video", "-pix_fmt", "yuv420p", "-b:v", "35M"], "acodec": ["-c:a", "pcm_s16le"]},
        "AVC-Intra 100": {"ext": "mxf", "vcodec": ["-c:v", "libx264", "-x264-params", "keyint=1", "-pix_fmt", "yuv422p10le", "-b:v", "100M"], "acodec": ["-c:a", "pcm_s16le"]},
        "XAVC-Intra": {"ext": "mxf", "vcodec": ["-c:v", "libx264", "-x264-params", "keyint=1", "-pix_fmt", "yuv422p10le", "-b:v", "100M"], "acodec": ["-c:a", "pcm_s16le"]},
        "HAP": {"ext": "mov", "vcodec": ["-c:v", "hap"], "acodec": ["-c:a", "pcm_s16le"]},
    },
    "Legacy codecs": {
        "MPEG-2": {"ext": "mpg", "vcodec": ["-c:v", "mpeg2video", "-b:v", "8M"], "acodec": ["-c:a", "mp2", "-b:a", "192k"]},
        "MPEG-1": {"ext": "mpg", "vcodec": ["-c:v", "mpeg1video", "-b:v", "4M"], "acodec": ["-c:a", "mp2", "-b:a", "192k"]},
        "MJPEG": {"ext": "avi", "vcodec": ["-c:v", "mjpeg", "-q:v", "3"], "acodec": ["-c:a", "pcm_s16le"]},
        "Xvid": {"ext": "avi", "vcodec": ["-c:v", "libxvid", "-q:v", "4"], "acodec": ["-c:a", "libmp3lame", "-b:a", "192k"]},
        "DV": {"ext": "dv", "vcodec": ["-c:v", "dvvideo", "-pix_fmt", "yuv411p"], "acodec": ["-c:a", "pcm_s16le"]},
        "WMV": {"ext": "wmv", "vcodec": ["-c:v", "wmv2", "-b:v", "4M"], "acodec": ["-c:a", "wmav2", "-b:a", "192k"]},
        "Theora (OGV)": {"ext": "ogv", "vcodec": ["-c:v", "libtheora", "-q:v", "7"], "acodec": ["-c:a", "libvorbis"]},
    },
    "Audio conversion": {
        "WAV": {"ext": "wav", "vcodec": None, "acodec": ["-c:a", "pcm_s16le"]},
        "AIFF": {"ext": "aiff", "vcodec": None, "acodec": ["-c:a", "pcm_s16be"]},
        "FLAC": {"ext": "flac", "vcodec": None, "acodec": ["-c:a", "flac"]},
        "ALAC (Apple Lossless)": {"ext": "m4a", "vcodec": None, "acodec": ["-c:a", "alac"]},
        "MP3": {"ext": "mp3", "vcodec": None, "acodec": ["-c:a", "libmp3lame", "-b:a", "192k"]},
        "AAC / M4A": {"ext": "m4a", "vcodec": None, "acodec": ["-c:a", "aac", "-b:a", "192k"]},
        "AC3 (Dolby Digital)": {"ext": "ac3", "vcodec": None, "acodec": ["-c:a", "ac3", "-b:a", "448k"]},
        "Opus": {"ext": "opus", "vcodec": None, "acodec": ["-c:a", "libopus", "-b:a", "192k"]},
        "Vorbis (OGG)": {"ext": "ogg", "vcodec": None, "acodec": ["-c:a", "libvorbis", "-q:a", "6"]},
    },
    "Image / sequence": {
        "JPEG": {"ext": "jpg", "vcodec": ["-c:v", "mjpeg", "-q:v", "2"], "acodec": None},
        "PNG": {"ext": "png", "vcodec": ["-c:v", "png"], "acodec": None},
        "TIFF": {"ext": "tiff", "vcodec": ["-c:v", "tiff"], "acodec": None},
        "WebP": {"ext": "webp", "vcodec": ["-c:v", "libwebp"], "acodec": None},
        "PNG sequence": {"ext": "png", "image_sequence": True, "vcodec": ["-c:v", "png"]},
        "JPEG sequence": {"ext": "jpg", "image_sequence": True, "vcodec": ["-c:v", "mjpeg", "-q:v", "2"]},
        "TIFF sequence": {"ext": "tiff", "image_sequence": True, "vcodec": ["-c:v", "tiff"]},
    },
    "Archival": {
        "FFV1 (lossless)": {"ext": "mkv", "vcodec": ["-c:v", "ffv1", "-level", "3"], "acodec": ["-c:a", "flac"]},
    },
}

# Ordre d'affichage des catégories dans le menu déroulant unique
CATEGORY_ORDER = [
    "Editing codecs",
    "Output codecs",
    "Broadcast codecs",
    "Legacy codecs",
    "Audio conversion",
    "Image / sequence",
    "Archival",
]

RESOLUTIONS = {
    "Keep original resolution": None,
    "3840×2160 (4K UHD)": 2160,
    "2560×1440 (1440p)": 1440,
    "1920×1080 (Full HD)": 1080,
    "1280×720 (HD)": 720,
    "854×480": 480,
    "Custom...": None,
}

FRAME_RATES = [
    "Keep original frame rate",
    "23.976", "24", "25", "29.97", "30", "50", "60",
    "Custom...",
]

# Conteneurs réellement compatibles avec chaque format, vérifié avec FFmpeg.
# (ProRes/DNxHR/CineForm/HAP/DV/FFV1 ne peuvent PAS être mis dans du MP4 ;
#  VP8/VP9 ne vont pas en MOV ; le MXF est réservé aux codecs broadcast.)
CONTAINER_OPTIONS = ["mov", "mp4", "mkv", "mxf", "avi", "webm", "mpg", "wmv", "ogv"]

FORMAT_CONTAINERS = {
    # ── Editing codecs ──
    "Apple ProRes 422 Proxy":     ["mov", "mxf", "mkv", "avi"],
    "Apple ProRes 422 LT":        ["mov", "mxf", "mkv", "avi"],
    "Apple ProRes 422":           ["mov", "mxf", "mkv", "avi"],
    "Apple ProRes 422 HQ":        ["mov", "mxf", "mkv", "avi"],
    "Apple ProRes 4444":          ["mov", "mxf", "mkv", "avi"],
    "Apple ProRes 4444 XQ":       ["mov", "mxf", "mkv", "avi"],
    "DNxHD 36 (1080p, fixed)":    ["mov", "mxf", "mkv", "avi"],
    "DNxHR LB (low bandwidth)":   ["mov", "mxf", "mkv", "avi"],
    "DNxHR SQ (standard)":        ["mov", "mxf", "mkv", "avi"],
    "DNxHR HQ (high quality)":    ["mov", "mxf", "mkv", "avi"],
    "DNxHR HQX (10-bit)":         ["mov", "mxf", "mkv", "avi"],
    "GoPro CineForm":             ["mov", "mkv", "avi"],
    "QuickTime Animation (RLE)":  ["mov", "mkv", "avi"],
    "Uncompressed 10-bit (v210)": ["mov", "mkv", "avi"],
    # ── Output codecs ──
    "H.264 (MP4)":                ["mp4", "mov", "mkv", "avi"],
    "H.265 / HEVC (MP4)":         ["mp4", "mov", "mkv", "avi"],
    "H.266 / VVC (MP4)":          ["mp4", "mkv"],
    "VP8 (WebM)":                 ["webm", "mkv"],
    "VP9 (WebM)":                 ["webm", "mkv", "mp4"],
    "AV1 (MP4)":                  ["mp4", "mkv", "webm"],
    # ── Broadcast codecs ──
    "XDCAM HD422 50 Mb/s":        ["mxf", "mov", "mp4", "mkv"],
    "XDCAM HD 35 Mb/s":           ["mxf", "mov", "mp4", "mkv"],
    "AVC-Intra 100":              ["mxf", "mov", "mp4", "mkv"],
    "XAVC-Intra":                 ["mxf", "mov", "mp4", "mkv"],
    "HAP":                        ["mov", "mkv", "avi"],
    # ── Legacy codecs ──
    "MPEG-2":                     ["mpg", "mov", "mp4", "mkv", "avi"],
    "MPEG-1":                     ["mpg", "mkv", "avi"],
    "MJPEG":                      ["avi", "mov", "mp4", "mkv"],
    "Xvid":                       ["avi", "mp4", "mov", "mkv", "mpg"],
    "DV":                         ["mov", "avi", "mkv"],
    "WMV":                        ["wmv", "mkv", "avi", "mov"],
    "Theora (OGV)":               ["ogv", "mkv", "mov", "avi"],
    # ── Archival ──
    "FFV1 (lossless)":            ["mkv", "avi"],
}

# Catégories où la résolution / le frame rate ne s'appliquent pas.
CATEGORIES_NO_RESOLUTION = {"Audio conversion"}
CATEGORIES_NO_FRAMERATE = {"Audio conversion", "Image / sequence"}

# Catégories où le conteneur de sortie peut être choisi librement.
CATEGORIES_WITH_CONTAINER_CHOICE = {
    "Editing codecs", "Output codecs", "Broadcast codecs",
    "Legacy codecs", "Archival"
}

_TIME_PATTERN = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def _get_duration_seconds(path):
    """Durée du fichier en secondes, via pymediainfo. None si indisponible
    (normal pour une simple photo, par exemple)."""
    if MediaInfo is None:
        return None
    try:
        info = MediaInfo.parse(path)
        for track in info.tracks:
            if track.track_type == "General":
                duration_ms = getattr(track, "duration", None)
                if duration_ms not in (None, ""):
                    return float(duration_ms) / 1000
    except Exception:
        pass
    return None


class MultiDropZone(QFrame):
    """Zone de glisser-déposer acceptant plusieurs fichiers à la fois."""
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(100)
        self.setStyleSheet(
            "QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }"
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Drop one or more videos/photos here\n(or click \"Add files\" below)")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("border: none; color: #666666;")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        self.setStyleSheet("QFrame { border: 2px solid #ff6b45; border-radius: 8px; background: #252a42; }")
    def dragLeaveEvent(self, event):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")

    def dropEvent(self, event):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class PreviewPanel(QWidget):
    """Panneau de prévisualisation : lecture vidéo + infos (durée,
    résolution, frame rate). Reste masqué jusqu'au premier fichier ajouté."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(0.8)

        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(480, 320)
        self.video_widget.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_widget, stretch=1)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(36)
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedWidth(36)
        self.stop_btn.clicked.connect(self._stop)
        controls.addWidget(self.stop_btn)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.sliderMoved.connect(self._on_seek)
        controls.addWidget(self.seek_slider)
        layout.addLayout(controls)

        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel("Volume :"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_row.addWidget(self.volume_slider)
        volume_row.addStretch()
        layout.addLayout(volume_row)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #555555;")
        layout.addWidget(self.info_label)

    def load_file(self, path):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.play_btn.setText("▶")
        self._update_info(path)

    def _update_info(self, path):
        duration_txt = resolution_txt = frame_rate_txt = "—"
        if MediaInfo is not None:
            try:
                info = MediaInfo.parse(path)
                for track in info.tracks:
                    if track.track_type == "General":
                        d = getattr(track, "duration", None)
                        if d not in (None, ""):
                            duration_txt = format_duration(d)
                    if track.track_type == "Video":
                        w = getattr(track, "width", None)
                        h = getattr(track, "height", None)
                        if w and h:
                            resolution_txt = f"{w}×{h}"
                        fr = getattr(track, "frame_rate", None)
                        if fr not in (None, ""):
                            frame_rate_txt = f"{fr} fps"
            except Exception:
                pass
        self.info_label.setText(
            f"Duration: {duration_txt}    Resolution: {resolution_txt}    Frame rate: {frame_rate_txt}"
        )

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop(self):
        self.player.stop()

    def _on_state_changed(self, state):
        self.play_btn.setText(
            "⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶"
        )

    def _on_duration_changed(self, duration_ms):
        self.seek_slider.setRange(0, duration_ms)

    def _on_position_changed(self, position_ms):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position_ms)

    def _on_seek(self, position_ms):
        self.player.setPosition(position_ms)

    def _on_volume_changed(self, value):
        self.audio_output.setVolume(value / 100)


class EncodeWorker(QThread):
    """Lance ffmpeg pour chaque fichier de la file, dans un thread séparé."""

    log_message = Signal(str)
    progress_value = Signal(int)
    item_started = Signal(str, int, int)  # nom du fichier, index, total
    finished_all = Signal(bool)

    def __init__(self, files, output_dir, category, preset_name,
                 resolution, frame_rate, container_override=None,
                 prefix="", suffix="", folder_per_video=False,
                 delete_source=False, parent=None):
        super().__init__(parent)
        self.files = files
        self.output_dir = output_dir
        self.category = category
        self.preset_name = preset_name
        self.resolution = resolution  # int (hauteur), tuple (largeur,hauteur), ou None
        self.frame_rate = frame_rate  # str ou None
        self.container_override = container_override  # str (ext) ou None
        self.prefix = prefix
        self.suffix = suffix
        self.folder_per_video = folder_per_video
        self.delete_source = delete_source
        self._stop_requested = False
        self._current_process = None

    def stop(self):
        self._stop_requested = True
        if self._current_process is not None:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    def _is_stream_copy(self, preset):
        vcodec = preset.get("vcodec")
        return bool(vcodec) and vcodec[:2] == ["-c:v", "copy"]

    def _build_args(self, input_path, output_path, preset):
        args = ["-y", "-i", input_path]

        apply_filters = not self._is_stream_copy(preset)
        vf_parts = []
        if apply_filters and self.resolution:
            if isinstance(self.resolution, tuple):
                w, h = self.resolution
                vf_parts.append(f"scale={w}:{h}")
            else:
                vf_parts.append(f"scale=-2:{self.resolution}")
        if vf_parts:
            args += ["-vf", ",".join(vf_parts)]

        if preset.get("vcodec") is None:
            args += ["-vn"]
        else:
            args += preset["vcodec"]

        if self.frame_rate and (apply_filters or preset.get("image_sequence")):
            args += ["-r", str(self.frame_rate)]

        if preset.get("image_sequence"):
            args += ["-an"]
        elif preset.get("acodec") is None:
            args += ["-an"]
        else:
            out_ext = os.path.splitext(output_path)[1].lower().lstrip(".")
            acodec = list(preset["acodec"])
            # Certains conteneurs n'acceptent pas n'importe quel codec audio :
            # on substitue un codec valide quand c'est nécessaire.
            if "copy" not in acodec:
                if out_ext == "webm":
                    # WebM n'accepte que Opus ou Vorbis
                    acodec = ["-c:a", "libopus", "-b:a", "192k"]
                elif out_ext in ("mpg", "mpeg"):
                    # MPEG-PS n'accepte pas le PCM : MP2 par défaut
                    if "pcm" in " ".join(acodec):
                        acodec = ["-c:a", "mp2", "-b:a", "192k"]
                elif out_ext == "ogv":
                    acodec = ["-c:a", "libvorbis"]
                elif out_ext == "wmv":
                    acodec = ["-c:a", "wmav2", "-b:a", "192k"]
            args += acodec
            # Le conteneur MXF n'accepte QUE de l'audio 48 kHz, sinon FFmpeg
            # échoue avec "only 48khz is implemented".
            if out_ext == "mxf" and "copy" not in acodec:
                args += ["-ar", "48000"]

        args.append(output_path)
        return args

    def _build_output_path(self, input_path, preset):
        basename = os.path.splitext(os.path.basename(input_path))[0]
        new_name = f"{self.prefix}{basename}{self.suffix}"
        ext = self.container_override or preset.get("ext") or "mp4"

        if preset.get("image_sequence"):
            sequence_dir = os.path.join(self.output_dir, new_name)
            os.makedirs(sequence_dir, exist_ok=True)
            return os.path.join(sequence_dir, f"{new_name}_%04d.{ext}")

        target_dir = self.output_dir
        if self.folder_per_video:
            target_dir = os.path.join(self.output_dir, new_name)
            os.makedirs(target_dir, exist_ok=True)

        return os.path.join(target_dir, f"{new_name}.{ext}")

    def run(self):
        ffmpeg_exe = get_ffmpeg_executable_path(get_manual_ffmpeg_path())
        os.makedirs(self.output_dir, exist_ok=True)

        preset = PRESETS[self.category][self.preset_name]
        total = len(self.files)
        success = True

        for index, input_path in enumerate(self.files, start=1):
            if self._stop_requested:
                self.log_message.emit("Cancelled.")
                break

            filename = os.path.basename(input_path)
            self.item_started.emit(filename, index, total)
            self.progress_value.emit(0)
            self.log_message.emit(f"[{index}/{total}] Starting: {filename}")

            output_path = self._build_output_path(input_path, preset)
            args = self._build_args(input_path, output_path, preset)
            duration = _get_duration_seconds(input_path)
            if duration is None:
                self.log_message.emit(
                    "  (unknown duration, progress estimate may be inaccurate)"
                )

            try:
                self._current_process = subprocess.Popen(
                    [ffmpeg_exe] + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                for line in self._current_process.stdout:
                    if self._stop_requested:
                        break
                    match = _TIME_PATTERN.search(line)
                    if match and duration:
                        h, m, s = match.groups()
                        elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                        pct = max(0, min(100, int(elapsed / duration * 100)))
                        self.progress_value.emit(pct)

                self._current_process.wait()
                return_code = self._current_process.returncode
                self._current_process = None

                if self._stop_requested:
                    self.log_message.emit(f"[{index}/{total}] Cancelled.")
                    break
                elif return_code == 0:
                    self.progress_value.emit(100)
                    self.log_message.emit(f"[{index}/{total}] Done: {os.path.basename(output_path)}")
                    if self.delete_source:
                        try:
                            os.remove(input_path)
                            self.log_message.emit(f"  🗑 Source file deleted: {filename}")
                        except Exception as e:
                            self.log_message.emit(f"  ⚠ Impossible de supprimer la source : {e}")
                else:
                    success = False
                    self.log_message.emit(
                        f"[{index}/{total}] ERROR: ffmpeg returned code {return_code}."
                    )
            except FileNotFoundError:
                success = False
                self.log_message.emit(
                    "ERROR: ffmpeg not found. Check Advanced Settings (⚙ "
                    "depuis l'accueil)."
                )
                break
            except Exception as e:
                success = False
                self.log_message.emit(f"[{index}/{total}] ERREUR : {e}")

        self.finished_all.emit(success)


class EncoderPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.queued_files = []
        self._preview_shown = False
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 16)

        top_bar = QHBoxLayout()
        self._t_back = QPushButton(tr("back")); back_btn = self._t_back
        back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        outer.addLayout(top_bar)

        self._t_title = QLabel(tr("enc_title")); title = self._t_title
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        outer.addWidget(title)

        self.splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_widget.setMinimumWidth(300)
        layout = QVBoxLayout(left_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.drop_zone = MultiDropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        layout.addWidget(self.drop_zone)

        queue_row = QHBoxLayout()
        add_btn = TButton("add_files")
        add_btn.clicked.connect(self._browse_files)
        queue_row.addWidget(add_btn)
        remove_btn = TButton("remove_sel")
        remove_btn.clicked.connect(self._remove_selected)
        queue_row.addWidget(remove_btn)
        clear_btn = TButton("clear_queue")
        clear_btn.clicked.connect(self._clear_queue)
        queue_row.addWidget(clear_btn)
        queue_row.addStretch()
        layout.addLayout(queue_row)

        self.queue_list = QListWidget()
        self.queue_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue_list.setFixedHeight(90)
        self.queue_list.currentRowChanged.connect(self._on_queue_selection_changed)
        layout.addWidget(self.queue_list)

        options_group = TGroupBox("options")
        options_layout = QHBoxLayout(options_group)

        # ── Un SEUL menu déroulant : catégories en séparateurs + formats ──
        # (comme Shutter Encoder : tous les formats visibles d'un coup, les
        #  titres de catégorie ne sont pas sélectionnables)
        fmt_box = QVBoxLayout()
        fmt_box.addWidget(TLabel("enc_format"))
        self.format_combo = QComboBox()
        self._build_format_combo()
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_box.addWidget(self.format_combo)
        options_layout.addLayout(fmt_box)

        container_box = QVBoxLayout()
        container_box.addWidget(TLabel("enc_container"))
        self.container_combo = QComboBox()
        self.container_combo.addItems(CONTAINER_OPTIONS)
        container_box.addWidget(self.container_combo)
        options_layout.addLayout(container_box)

        res_box = QVBoxLayout()
        res_box.addWidget(TLabel("enc_resolution"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(list(RESOLUTIONS.keys()))
        self.res_combo.setEditable(True)
        self.res_combo.activated.connect(self._on_res_combo_activated)
        res_box.addWidget(self.res_combo)
        options_layout.addLayout(res_box)

        fps_box = QVBoxLayout()
        fps_box.addWidget(TLabel("enc_framerate"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(FRAME_RATES)
        self.fps_combo.setEditable(True)
        self.fps_combo.activated.connect(self._on_fps_combo_activated)
        fps_box.addWidget(self.fps_combo)
        options_layout.addLayout(fps_box)

        layout.addWidget(options_group)
        self._on_format_changed()

        rename_group = TGroupBox("rename_section")
        rename_layout = QHBoxLayout(rename_group)

        prefix_box = QVBoxLayout()
        prefix_box.addWidget(TLabel("prefix"))
        self.prefix_input = QLineEdit()
        self.prefix_input.setPlaceholderText("ex: EXPORT_")
        prefix_box.addWidget(self.prefix_input)
        rename_layout.addLayout(prefix_box)

        suffix_box = QVBoxLayout()
        suffix_box.addWidget(TLabel("suffix"))
        self.suffix_input = QLineEdit()
        self.suffix_input.setPlaceholderText("ex: _v1")
        suffix_box.addWidget(self.suffix_input)
        rename_layout.addLayout(suffix_box)

        checks_box = QVBoxLayout()
        self.folder_per_video_check = TCheckBox("create_folder")
        checks_box.addWidget(self.folder_per_video_check)
        self.delete_source_check = TCheckBox("delete_source")
        checks_box.addWidget(self.delete_source_check)
        rename_layout.addLayout(checks_box)

        layout.addWidget(rename_group)

        out_layout = QHBoxLayout()
        out_layout.addWidget(TLabel("output_folder"))
        self.output_path = QLineEdit(os.path.join(os.path.expanduser("~"), "Documents"))
        out_layout.addWidget(self.output_path)
        browse_out_btn = TButton("browse")
        browse_out_btn.clicked.connect(self._choose_output_dir)
        out_layout.addWidget(browse_out_btn)
        layout.addLayout(out_layout)

        action_layout = QHBoxLayout()
        self.encode_btn = TButton("enc_btn")
        self.encode_btn.setMinimumHeight(36)
        self.encode_btn.clicked.connect(self._start_encode)
        action_layout.addWidget(self.encode_btn)

        self.cancel_btn = TButton("cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_encode)
        action_layout.addWidget(self.cancel_btn)
        layout.addLayout(action_layout)

        self.current_item_label = QLabel("")
        layout.addWidget(self.current_item_label)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        layout.addWidget(TLabel("journal"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        self.splitter.addWidget(left_widget)

        self.preview_panel = PreviewPanel()
        self.preview_panel.setVisible(False)
        self.splitter.addWidget(self.preview_panel)

        # Le visualiseur doit dominer l'espace (3/4) une fois affiché,
        # les contrôles d'encodage restant compacts (1/4).
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        outer.addWidget(self.splitter)

    def _build_format_combo(self):
        """Remplit le combo unique : chaque catégorie devient un séparateur
        (titre non-sélectionnable, en gras) suivi de ses formats."""
        from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont, QBrush, QColor
        from PySide6.QtCore import Qt as _Qt
        model = QStandardItemModel()
        for category in CATEGORY_ORDER:
            if category not in PRESETS:
                continue
            # Titre de catégorie : non-sélectionnable, gras, fond rouge léger
            header = QStandardItem(f"— {category} —")
            header.setFlags(_Qt.NoItemFlags)   # ni cliquable ni sélectionnable
            f = QFont(); f.setBold(True)
            header.setData(f, _Qt.FontRole)
            # Fond legerement plus clair que la base, texte clair
            header.setData(QBrush(QColor("#2a2d3e")), _Qt.BackgroundRole)
            header.setData(QBrush(QColor("#cdd2e0")), _Qt.ForegroundRole)
            header.setData(category, _Qt.UserRole + 1)   # marqueur "header"
            model.appendRow(header)
            # Formats de la catégorie
            for fmt_name in PRESETS[category].keys():
                item = QStandardItem(f"    {fmt_name}")
                item.setData(category, _Qt.UserRole + 2)   # catégorie associée
                item.setData(fmt_name, _Qt.UserRole + 3)   # nom réel du format
                model.appendRow(item)
        self.format_combo.setModel(model)
        # Sous Windows, le popup natif ignore parfois les couleurs de fond :
        # une feuille de style sur la vue force Qt à dessiner lui-même.
        self.format_combo.view().setStyleSheet(
            "QListView { outline: none; }"
            "QListView::item { padding: 3px 6px; }"
        )
        # Sélectionner le premier vrai format (pas le premier header)
        for i in range(self.format_combo.count()):
            if self._format_at(i) is not None:
                self.format_combo.setCurrentIndex(i)
                break

    def _format_at(self, index):
        """Retourne (category, format_name) pour l'item d'index donné, ou None
        si c'est un séparateur de catégorie."""
        from PySide6.QtCore import Qt as _Qt
        model = self.format_combo.model()
        item = model.item(index)
        if item is None:
            return None
        cat = item.data(_Qt.UserRole + 2)
        fmt = item.data(_Qt.UserRole + 3)
        if cat is None or fmt is None:
            return None
        return (cat, fmt)

    def _current_category_and_format(self):
        """Catégorie et format actuellement sélectionnés dans le combo unique."""
        return self._format_at(self.format_combo.currentIndex())

    def _on_format_changed(self, *args):
        sel = self._current_category_and_format()
        if sel is None:
            # Si on tombe sur un header, avancer au format suivant
            idx = self.format_combo.currentIndex()
            for i in range(idx + 1, self.format_combo.count()):
                if self._format_at(i) is not None:
                    self.format_combo.setCurrentIndex(i)
                    return
            for i in range(idx - 1, -1, -1):
                if self._format_at(i) is not None:
                    self.format_combo.setCurrentIndex(i)
                    return
            return
        category, _ = sel
        self.res_combo.setEnabled(category not in CATEGORIES_NO_RESOLUTION)
        self.fps_combo.setEnabled(category not in CATEGORIES_NO_FRAMERATE)
        self._sync_container_default()

    def _sync_container_default(self):
        """Ne propose que les conteneurs RÉELLEMENT compatibles avec le format
        choisi (table FORMAT_CONTAINERS vérifiée avec FFmpeg)."""
        sel = self._current_category_and_format()
        if sel is None:
            return
        category, preset_name = sel
        enabled = category in CATEGORIES_WITH_CONTAINER_CHOICE
        self.container_combo.setEnabled(enabled)
        if not enabled:
            self.container_combo.clear()
            return

        preset = PRESETS[category].get(preset_name, {})
        default_ext = preset.get("ext", "mp4")
        # Conteneurs compatibles pour ce format précis
        allowed = FORMAT_CONTAINERS.get(preset_name)
        if not allowed:
            allowed = [default_ext]
        # Le conteneur par défaut du preset doit toujours figurer en tête
        if default_ext in allowed:
            allowed = [default_ext] + [c for c in allowed if c != default_ext]

        self.container_combo.blockSignals(True)
        self.container_combo.clear()
        self.container_combo.addItems(allowed)
        self.container_combo.setCurrentIndex(0)
        self.container_combo.blockSignals(False)

    def _on_res_combo_activated(self, index):
        if self.res_combo.itemText(index) == "Custom...":
            self.res_combo.setEditText("")
            self.res_combo.lineEdit().setPlaceholderText("e.g. 1000  or  1920x1080")
            self.res_combo.setFocus()

    def _on_fps_combo_activated(self, index):
        if self.fps_combo.itemText(index) == "Custom...":
            self.fps_combo.setEditText("")
            self.fps_combo.lineEdit().setPlaceholderText("ex: 48")
            self.fps_combo.setFocus()

    def _add_files(self, paths):
        was_empty = not self.queued_files
        added_any = False
        for path in paths:
            if os.path.isfile(path) and path not in self.queued_files:
                self.queued_files.append(path)
                self.queue_list.addItem(os.path.basename(path))
                added_any = True
        if added_any and was_empty:
            self.queue_list.setCurrentRow(0)
            self._show_preview_panel()

    def _show_preview_panel(self):
        self.preview_panel.setVisible(True)
        if not self._preview_shown:
            self._preview_shown = True
            window = self.window()
            if window is not None:
                window.resize(window.width() + 500, window.height())
        total = max(self.splitter.width(), 1000)
        self.splitter.setSizes([int(total * 0.25), int(total * 0.75)])

    def _on_queue_selection_changed(self, row):
        if 0 <= row < len(self.queued_files):
            self.preview_panel.load_file(self.queued_files[row])

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select one or more videos/photos", "",
            "Video and image files (*.mp4 *.mov *.mxf *.avi *.mkv *.braw *.r3d "
            "*.jpg *.jpeg *.png *.tiff *.bmp *.webp);;Tous les fichiers (*.*)"
        )
        if paths:
            self._add_files(paths)

    def _remove_selected(self):
        for item in self.queue_list.selectedItems():
            row = self.queue_list.row(item)
            self.queue_list.takeItem(row)
            del self.queued_files[row]
        if not self.queued_files:
            self.preview_panel.player.stop()

    def _clear_queue(self):
        self.queue_list.clear()
        self.queued_files = []
        self.preview_panel.player.stop()

    def _choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_path.setText(folder)

    def _parse_resolution(self, text):
        """Accepte un préréglage, une hauteur seule ('1000'), ou une
        résolution exacte 'LARGEURxHAUTEUR' (ex: '1920x1037')."""
        text = text.strip()
        if text in RESOLUTIONS:
            return RESOLUTIONS[text]
        cleaned = text.lower().replace(" ", "")
        if "x" in cleaned:
            parts = cleaned.split("x")
            if len(parts) == 2 and all(p.isdigit() and int(p) > 0 for p in parts):
                return (int(parts[0]), int(parts[1]))
        elif cleaned.isdigit() and int(cleaned) > 0:
            return int(cleaned)
        return None

    def _parse_frame_rate(self, text):
        text = text.strip()
        if text in ("Keep original frame rate", "Custom...", ""):
            return None
        try:
            value = float(text.replace(",", "."))
            if value > 0:
                return text.replace(",", ".")
        except ValueError:
            pass
        return None

    def _start_encode(self):
        if not self.queued_files:
            QMessageBox.warning(self, "File vide", "Add at least one file to encode.")
            return

        output_dir = self.output_path.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Missing folder", "Please select an output folder.")
            return

        if self.delete_source_check.isChecked():
            confirm = QMessageBox.question(
                self, "Confirmation requise",
                f"{len(self.queued_files)} source file(s) will be deleted "
                "after encoding completes."
                "This is irreversible.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

        sel = self._current_category_and_format()
        if sel is None:
            QMessageBox.warning(self, "No format", "Please select an output format.")
            self.encode_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return
        category, preset_name = sel
        resolution = (
            self._parse_resolution(self.res_combo.currentText())
            if self.res_combo.isEnabled() else None
        )
        frame_rate = (
            self._parse_frame_rate(self.fps_combo.currentText())
            if self.fps_combo.isEnabled() else None
        )
        container_override = (
            self.container_combo.currentText() if self.container_combo.isEnabled() else None
        )

        self.encode_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        self.worker = EncodeWorker(
            files=list(self.queued_files),
            output_dir=output_dir,
            category=category,
            preset_name=preset_name,
            resolution=resolution,
            frame_rate=frame_rate,
            container_override=container_override,
            prefix=self.prefix_input.text(),
            suffix=self.suffix_input.text(),
            folder_per_video=self.folder_per_video_check.isChecked(),
            delete_source=self.delete_source_check.isChecked(),
        )
        self.worker.log_message.connect(self._append_log)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.item_started.connect(self._on_item_started)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_item_started(self, filename, index, total):
        self.current_item_label.setText(f"[{index}/{total}] {filename}")

    def _cancel_encode(self):
        if self.worker:
            self.worker.stop()
            self._append_log("Cancellation requested...")

    def _append_log(self, text):
        self.log_output.append(text)

    def _on_finished(self, success):
        if success:
            play_done()
        else:
            play_error()
        self.encode_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.current_item_label.setText("")
        if success:
            self._append_log("✔ All encodings complete.")
        else:
            self._append_log("⚠ Completed with at least one error (see log above).")

    def set_lang(self, lang):
        from core.lang import tr, LangManager
        LangManager.get().current = lang
        if hasattr(self, '_t_title'):     self._t_title.setText(tr("enc_title"))
        if hasattr(self, '_t_back'):      self._t_back.setText(tr("back"))
        if hasattr(self, '_t_enc_btn'):   self._t_enc_btn.setText(tr("enc_btn"))
        if hasattr(self, '_t_cancel_btn'):self._t_cancel_btn.setText(tr("cancel"))