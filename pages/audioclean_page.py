"""Module 8: Audio Lab — noise reduction, voice enhance, vocal/music separation."""
from core.sounds import play_done, play_error
import os, subprocess, tempfile
from core.paths import default_output_dir as _dod
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QFrame, QComboBox, QProgressBar, QTextEdit, QSlider, QMessageBox, QTabWidget,
    QGroupBox, QInputDialog
)
from core.ffmpeg_utils import get_ffmpeg_executable_path
from core.settings_store import get_manual_ffmpeg_path

EXPORT_FORMATS = {
    "WAV (lossless)":  {"ext": "wav",  "codec": ["-c:a", "pcm_s16le"]},
    "FLAC (lossless)": {"ext": "flac", "codec": ["-c:a", "flac"]},
    "MP3 320 kbps":    {"ext": "mp3",  "codec": ["-c:a", "libmp3lame", "-b:a", "320k"]},
    "MP3 192 kbps":    {"ext": "mp3",  "codec": ["-c:a", "libmp3lame", "-b:a", "192k"]},
    "AAC / M4A":       {"ext": "m4a",  "codec": ["-c:a", "aac", "-b:a", "256k"]},
}

class AudioDropZone(QFrame):
    file_dropped = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(90)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        l = QVBoxLayout(self)
        self.label = QLabel("Drop an audio or video file here\n(MP3, WAV, FLAC, MP4, MOV...)")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("border: none; color: #666666;")
        self.label.setWordWrap(True)
        from PySide6.QtWidgets import QSizePolicy as _SP
        self.label.setSizePolicy(_SP.Ignored, _SP.Preferred)
        l.addWidget(self.label)
    def show_filename(self, path):
        from PySide6.QtGui import QFontMetrics
        name = os.path.basename(path)
        self.label.setStyleSheet("border: none; color: #e8eaf0; font-weight: 600;")
        avail = max(self.width() - 24, 180)
        self.label.setText(QFontMetrics(self.label.font()).elidedText(
            name, Qt.ElideMiddle, avail))
        self.label.setToolTip(name)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        self.setStyleSheet("QFrame { border: 2px solid #ff6b45; border-radius: 8px; background: #252a42; }")
    def dragLeaveEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
    def dropEvent(self, e):
        self.setStyleSheet("QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }")
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.show_filename(path)
            self.file_dropped.emit(path)

def _to_wav(src, dst, ffmpeg):
    cmd = [ffmpeg, "-y", "-i", src, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", dst]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0).returncode

def _convert(src, dst, codec, ffmpeg):
    subprocess.run([ffmpeg, "-y", "-i", src] + codec + [dst],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)

class DenoiseWorker(QThread):
    log_message = Signal(str)
    progress_value = Signal(int)
    finished = Signal(bool, str)
    def __init__(self, input_path, output_path, fmt_key, sensitivity, ffmpeg_exe, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.fmt_key = fmt_key
        self.sensitivity = sensitivity
        self.ffmpeg_exe = ffmpeg_exe
    def run(self):
        try:
            import numpy as np, soundfile as sf, noisereduce as nr
        except ImportError as e:
            self.log_message.emit(f"ERROR: {e}\nRun: pip install noisereduce soundfile numpy")
            self.finished.emit(False, ""); return
        with tempfile.TemporaryDirectory() as tmp:
            tmp_in = os.path.join(tmp, "input.wav")
            tmp_out = os.path.join(tmp, "cleaned.wav")
            self.log_message.emit("Converting to WAV...")
            self.progress_value.emit(10)
            if _to_wav(self.input_path, tmp_in, self.ffmpeg_exe) != 0:
                self.log_message.emit("ERROR: FFmpeg conversion failed.")
                self.finished.emit(False, ""); return
            self.log_message.emit("Analysing noise profile and reducing...")
            self.progress_value.emit(25)
            data, rate = sf.read(tmp_in)
            if data.ndim == 1: data = data.reshape(-1, 1)
            cleaned = []
            for ch in range(data.shape[1]):
                c = data[:, ch]
                cleaned.append(nr.reduce_noise(y=c, sr=rate, y_noise=c[:int(rate*0.5)],
                    prop_decrease=min(1.0, self.sensitivity), stationary=False))
                self.progress_value.emit(25 + ch*35)
            sf.write(tmp_out, np.stack(cleaned, axis=1), rate)
            self.log_message.emit("Exporting...")
            self.progress_value.emit(85)
            _convert(tmp_out, self.output_path, EXPORT_FORMATS[self.fmt_key]["codec"], self.ffmpeg_exe)
        self.log_message.emit(f"✔ File saved: {self.output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True, self.output_path)

class EnhanceWorker(QThread):
    """Amélioration de voix : transforme un enregistrement médiocre (portable,
    micro d'ordi...) en une voix claire type podcast, via une chaîne de
    traitement pro (filtre passe-haut, dé-bruitage léger, EQ vocal,
    compression, de-esser, limiteur)."""
    log_message = Signal(str)
    progress_value = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, input_path, output_path, fmt_key, intensity, ffmpeg_exe, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.fmt_key = fmt_key
        self.intensity = intensity   # "light" | "medium" | "strong"
        self.ffmpeg_exe = ffmpeg_exe

    def run(self):
        try:
            import numpy as np, soundfile as sf
            from pedalboard import (Pedalboard, NoiseGate, Compressor,
                                    LowShelfFilter, HighShelfFilter,
                                    HighpassFilter, PeakFilter, Gain, Limiter)
        except ImportError as e:
            self.log_message.emit(
                f"ERROR: {e}\nRun: pip install pedalboard soundfile numpy")
            self.finished.emit(False, ""); return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_in = os.path.join(tmp, "input.wav")
            tmp_out = os.path.join(tmp, "enhanced.wav")

            self.log_message.emit("Converting to WAV...")
            self.progress_value.emit(10)
            if _to_wav(self.input_path, tmp_in, self.ffmpeg_exe) != 0:
                self.log_message.emit("ERROR: FFmpeg conversion failed.")
                self.finished.emit(False, ""); return

            self.log_message.emit("Loading audio...")
            self.progress_value.emit(25)
            data, rate = sf.read(tmp_in)
            if data.ndim > 1:
                # Voix = mono : on moyenne les canaux pour un traitement propre
                data = data.mean(axis=1)
            data = data.astype("float32")

            # Réglages selon l'intensité choisie
            presets = {
                "light":  dict(gate=-50, low=-1, mud=-1, pres=2, air=2, comp_ratio=2, comp_thr=-18, gain=3),
                "medium": dict(gate=-42, low=-2, mud=-2, pres=3, air=3, comp_ratio=3, comp_thr=-20, gain=4),
                "strong": dict(gate=-38, low=-3, mud=-3, pres=4, air=4, comp_ratio=4, comp_thr=-22, gain=5),
            }
            p = presets.get(self.intensity, presets["medium"])

            self.log_message.emit(f"Enhancing voice ({self.intensity})...")
            self.progress_value.emit(45)

            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=80),           # anti pop/rumble
                NoiseGate(threshold_db=p["gate"], ratio=2, release_ms=250),
                LowShelfFilter(cutoff_frequency_hz=200, gain_db=p["low"]),   # dégraisse le bas
                PeakFilter(cutoff_frequency_hz=350, gain_db=p["mud"], q=1.0),# enlève le "boueux"
                PeakFilter(cutoff_frequency_hz=4000, gain_db=p["pres"], q=1.5), # présence
                HighShelfFilter(cutoff_frequency_hz=8000, gain_db=p["air"]),  # air/clarté
                # De-esser approximatif : léger creux dans les sifflantes
                PeakFilter(cutoff_frequency_hz=6500, gain_db=-2, q=2.0),
                Compressor(threshold_db=p["comp_thr"], ratio=p["comp_ratio"],
                           attack_ms=5, release_ms=120),          # densité "radio"
                Gain(gain_db=p["gain"]),
                Limiter(threshold_db=-1.0),                       # sécurité
            ])

            self.progress_value.emit(65)
            enhanced = board(data, rate)

            # Normalisation finale à ~ -1 dBFS
            peak = float(abs(enhanced).max()) if len(enhanced) else 0.0
            if peak > 0:
                enhanced = enhanced * (0.89 / peak)   # ~ -1 dBFS

            self.progress_value.emit(80)
            sf.write(tmp_out, enhanced, rate)

            self.log_message.emit("Exporting...")
            self.progress_value.emit(90)
            _convert(tmp_out, self.output_path,
                     EXPORT_FORMATS[self.fmt_key]["codec"], self.ffmpeg_exe)

        self.log_message.emit(f"✔ File saved: {self.output_path}")
        self.progress_value.emit(100)
        self.finished.emit(True, self.output_path)


class SeparateWorker(QThread):
    log_message = Signal(str)
    progress_value = Signal(int)
    finished = Signal(bool, dict)
    def __init__(self, input_path, output_dir, fmt_key, ffmpeg_exe, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_dir = output_dir
        self.fmt_key = fmt_key
        self.ffmpeg_exe = ffmpeg_exe
    def run(self):
        try:
            import torch, soundfile as sf, numpy as np
        except ImportError as e:
            self.log_message.emit(f"ERROR: {e}\nRun: pip install torch soundfile numpy")
            self.finished.emit(False, {}); return
        try:
            from demucs.pretrained import get_model
            from demucs.apply import apply_model
        except ImportError as e:
            self.log_message.emit(f"ERROR: {e}\nRun: pip install demucs")
            self.finished.emit(False, {}); return
        base = os.path.splitext(os.path.basename(self.input_path))[0]
        fmt = EXPORT_FORMATS[self.fmt_key]
        os.makedirs(self.output_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_wav = os.path.join(tmp, "input.wav")
            self.log_message.emit("Step 1/3: Converting to WAV via FFmpeg...")
            self.progress_value.emit(5)
            if _to_wav(self.input_path, tmp_wav, self.ffmpeg_exe) != 0:
                self.log_message.emit("ERROR: FFmpeg conversion failed.")
                self.finished.emit(False, {}); return
            self.log_message.emit("Step 2/3: Loading demucs model + separating...\n(first run = downloading model ~80 MB)")
            self.progress_value.emit(20)
            try:
                data, sr = sf.read(tmp_wav, dtype="float32", always_2d=True)
                waveform = torch.from_numpy(data.T).unsqueeze(0).float()
                ref = waveform.mean(0); std = ref.std() + 1e-8
                waveform = (waveform - ref.mean()) / std
                self.log_message.emit(f"Audio: {data.shape[0]} samples, {sr} Hz, {data.shape[1]} channel(s)")
                self.progress_value.emit(30)
                model = get_model("htdemucs"); model.eval()
                self.log_message.emit("Model loaded. Separating (may take several minutes on CPU)...")
                self.progress_value.emit(40)
                with torch.no_grad():
                    sources = apply_model(model, waveform, device="cpu", progress=False, shifts=1, split=True, overlap=0.25)
                sources = sources * std + ref.mean()
                self.log_message.emit("Separation complete.")
                self.progress_value.emit(85)
                sd = {name: sources[0, i] for i, name in enumerate(model.sources)}
                stems = {"vocals": sd["vocals"], "no_vocals": sum(v for k, v in sd.items() if k != "vocals")}
            except Exception as e:
                import traceback
                self.log_message.emit(f"ERROR: {e}\n{traceback.format_exc()}")
                self.finished.emit(False, {}); return
            self.log_message.emit("Step 3/3: Exporting stems...")
            labels = {"vocals": "vocals", "no_vocals": "instruments"}
            result = {}
            stems_dir = os.path.join(tmp, "stems")
            os.makedirs(stems_dir, exist_ok=True)
            for key, tensor in stems.items():
                label = labels[key]
                audio_np = tensor.numpy().T
                tmp_stem = os.path.join(stems_dir, f"{key}.wav")
                sf.write(tmp_stem, audio_np, sr)
                out_name = f"{base}_{label}.{fmt['ext']}"
                out_path = os.path.join(self.output_dir, out_name)
                _convert(tmp_stem, out_path, fmt["codec"], self.ffmpeg_exe)
                result[label] = out_path
                self.log_message.emit(f"✔ {out_name}")
        self.progress_value.emit(100)
        self.log_message.emit(f"\n✔ Stems saved to: {self.output_dir}")
        self.finished.emit(True, result)


class AudioCleanPage(QWidget):
    back_requested = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_path = ""
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        top = QHBoxLayout()
        back = QPushButton("← Home"); back.clicked.connect(self.back_requested.emit)
        top.addWidget(back); top.addStretch(); layout.addLayout(top)
        title = QLabel("Audio Lab"); title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)
        # Plus de drop zone commune : chaque onglet qui traite un fichier a la
        # sienne (Noise/Enhance/Separate). Voice Over & Clone n'en ont pas besoin.
        self.audio_path = ""
        tabs = QTabWidget()
        tabs.addTab(self._tab_denoise(),   "🎤 Noise Reduction")
        tabs.addTab(self._tab_enhance(),   "✨ Voice Enhance")
        tabs.addTab(self._tab_separate(), "🎵 Vocals / Music")
        tabs.setStyleSheet("""
            QTabBar::tab {
                background: #1c2030;
                color: #8892a4;
                padding: 9px 18px;
                margin-right: 3px;
                border: 1px solid #2a2f42;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                font-size: 13px;
            }
            QTabBar::tab:hover {
                background: #262b3e;
                color: #e8eaf0;
            }
            QTabBar::tab:selected {
                background: #e8542e;
                color: #ffffff;
                font-weight: 600;
                border: 1px solid #e8542e;
            }
            QTabWidget::pane {
                border: 1px solid #2a2f42;
                border-radius: 6px;
                top: -1px;
            }
        """)
        layout.addWidget(tabs)
        layout.addWidget(QLabel("Log:"))
        self.log_output = QTextEdit(); self.log_output.setReadOnly(True); self.log_output.setFixedHeight(110)
        layout.addWidget(self.log_output)
        self.progress_bar = QProgressBar(); layout.addWidget(self.progress_bar)

    def _make_drop_zone(self):
        """Retourne un widget (drop zone + Browse + label) autonome, à placer
        dans les onglets qui traitent un fichier audio. Toutes les zones
        partagent le même self.audio_path via _load_file."""
        box = QVBoxLayout()
        dz = AudioDropZone()
        dz.file_dropped.connect(self._load_file)
        box.addWidget(dz)
        row = QHBoxLayout()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lbl = QLabel("No file loaded.")
        lbl.setStyleSheet("color:#555;")
        row.addWidget(lbl); row.addStretch()
        box.addLayout(row)
        # Mémoriser les zones ET les labels pour les tenir à jour ensemble
        if not hasattr(self, "_file_labels"):
            self._file_labels = []
        if not hasattr(self, "_drop_zones"):
            self._drop_zones = []
        self._file_labels.append(lbl)
        self._drop_zones.append(dz)
        return box

    def _tab_denoise(self):
        w = QWidget(); l = QVBoxLayout(w)
        info = QLabel("Removes constant background noise (hiss, fan, room noise).\nThe first 0.5 s of the file is used as the noise profile — make sure it contains only noise, no voice.")
        info.setWordWrap(True); info.setStyleSheet("color:#555;font-size:11px;"); l.addWidget(info)
        l.addLayout(self._make_drop_zone())
        row = QHBoxLayout(); row.addWidget(QLabel("Intensity:"))
        self._slider = QSlider(Qt.Horizontal); self._slider.setRange(1, 20); self._slider.setValue(10); self._slider.setFixedWidth(160)
        self._slider_lbl = QLabel("1.0")
        self._slider.valueChanged.connect(lambda v: self._slider_lbl.setText(f"{v/10:.1f}"))
        row.addWidget(self._slider); row.addWidget(self._slider_lbl); row.addStretch(); l.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Output format:"))
        self._denoise_fmt = QComboBox(); self._denoise_fmt.addItems(list(EXPORT_FORMATS.keys()))
        row2.addWidget(self._denoise_fmt); row2.addStretch(); l.addLayout(row2)
        l.addWidget(QLabel("Requires: pip install noisereduce soundfile numpy", styleSheet="color:#888;font-size:11px;"))
        btn = QPushButton("Reduce Noise"); btn.setMinimumHeight(36); btn.clicked.connect(self._run_denoise); l.addWidget(btn)
        l.addStretch(); return w

    def _tab_enhance(self):
        w = QWidget(); l = QVBoxLayout(w)
        info = QLabel("Turns a poor recording (phone, laptop mic) into a clear, "
                      "podcast-style voice.\nApplies a pro chain: high-pass, light "
                      "de-noise, vocal EQ, compression, de-esser and limiter.")
        info.setWordWrap(True); info.setStyleSheet("color:#555;font-size:11px;"); l.addWidget(info)
        l.addLayout(self._make_drop_zone())
        row = QHBoxLayout(); row.addWidget(QLabel("Strength:"))
        self._enhance_intensity = QComboBox()
        self._enhance_intensity.addItems(["Light", "Medium", "Strong"])
        self._enhance_intensity.setCurrentText("Medium")
        row.addWidget(self._enhance_intensity); row.addStretch(); l.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Output format:"))
        self._enhance_fmt = QComboBox(); self._enhance_fmt.addItems(list(EXPORT_FORMATS.keys()))
        row2.addWidget(self._enhance_fmt); row2.addStretch(); l.addLayout(row2)
        l.addWidget(QLabel("Requires: pip install pedalboard soundfile numpy",
                           styleSheet="color:#888;font-size:11px;"))
        btn = QPushButton("Enhance Voice"); btn.setMinimumHeight(36)
        btn.clicked.connect(self._run_enhance); l.addWidget(btn)
        l.addStretch(); return w

    def _tab_separate(self):
        w = QWidget(); l = QVBoxLayout(w)
        info = QLabel("Separates vocals/speech from music into 2 files:\n  • vocals: voice/speech only\n  • instruments: everything else\n\nEngine: demucs htdemucs (Meta, MIT license).\nFirst run: downloads model ~80 MB.")
        info.setWordWrap(True); info.setStyleSheet("color:#555;font-size:11px;"); l.addWidget(info)
        l.addLayout(self._make_drop_zone())
        row = QHBoxLayout(); row.addWidget(QLabel("Output format:"))
        self._sep_fmt = QComboBox(); self._sep_fmt.addItems(list(EXPORT_FORMATS.keys()))
        row.addWidget(self._sep_fmt); row.addStretch(); l.addLayout(row)
        l.addWidget(QLabel("Requires: pip install demucs", styleSheet="color:#888;font-size:11px;"))
        btn = QPushButton("Separate Vocals / Music"); btn.setMinimumHeight(36); btn.clicked.connect(self._run_separate); l.addWidget(btn)
        l.addStretch(); return w

    def _load_file(self, path):
        if os.path.isfile(path):
            self.audio_path = path
            # Afficher le nom DANS chaque zone de dépôt (en blanc)
            for dz in getattr(self, "_drop_zones", []):
                dz.show_filename(path)
            # Vider les labels du dessous (le nom est déjà dans la zone)
            for lbl in getattr(self, "_file_labels", []):
                lbl.setText("")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select audio or video file", "",
            "Audio/Video (*.mp3 *.wav *.flac *.m4a *.mp4 *.mov *.aif);;All (*.*)")
        if path: self._load_file(path)

    def _run_denoise(self):
        if not self.audio_path: QMessageBox.warning(self, "No file", "Load a file first."); return
        fmt_key = self._denoise_fmt.currentText()
        ext = EXPORT_FORMATS[fmt_key]["ext"]
        base = os.path.splitext(self.audio_path)[0]
        out, _ = QFileDialog.getSaveFileName(self, "Save cleaned file", os.path.join(_dod(), f"{base}_cleaned.{ext}"), f"Audio (*.{ext})")
        if not out: return
        ffmpeg = get_ffmpeg_executable_path(get_manual_ffmpeg_path())
        self._start(DenoiseWorker(self.audio_path, out, fmt_key, self._slider.value()/10, ffmpeg))

    def _run_separate(self):
        if not self.audio_path: QMessageBox.warning(self, "No file", "Load a file first."); return
        out_dir = QFileDialog.getExistingDirectory(self, "Output folder for stems", os.path.dirname(self.audio_path))
        if not out_dir: return
        ffmpeg = get_ffmpeg_executable_path(get_manual_ffmpeg_path())
        self._start(SeparateWorker(self.audio_path, out_dir, self._sep_fmt.currentText(), ffmpeg))

    def _run_enhance(self):
        if not self.audio_path: QMessageBox.warning(self, "No file", "Load a file first."); return
        fmt_key = self._enhance_fmt.currentText()
        ext = EXPORT_FORMATS[fmt_key]["ext"]
        base = os.path.splitext(self.audio_path)[0]
        out, _ = QFileDialog.getSaveFileName(self, "Save enhanced file", os.path.join(_dod(), f"{base}_enhanced.{ext}"), f"Audio (*.{ext})")
        if not out: return
        intensity = self._enhance_intensity.currentText().lower()  # light/medium/strong
        ffmpeg = get_ffmpeg_executable_path(get_manual_ffmpeg_path())
        self._start(EnhanceWorker(self.audio_path, out, fmt_key, intensity, ffmpeg))

    def _start(self, worker):
        self.log_output.clear(); self.progress_bar.setValue(0)
        self.worker = worker
        self.worker.log_message.connect(self.log_output.append)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.finished.connect(lambda ok, *_: (play_done() if ok else play_error(),
            QMessageBox.information(self, "Done", "Operation successful!") if ok
            else QMessageBox.warning(self, "Error", "See the log for details.")))
        self.worker.start()

    def set_lang(self, lang): pass
