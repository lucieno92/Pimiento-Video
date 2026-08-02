"""Settings page — FFmpeg path configuration."""
import os
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox
)
from core.ffmpeg_utils import (
    get_bundled_ffmpeg_path, find_ffmpeg_bin_dir, is_ffmpeg_on_system_path
)
from core.settings_store import get_manual_ffmpeg_path, set_manual_ffmpeg_path

class SettingsPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)

        top = QHBoxLayout()
        back = QPushButton("← Home")
        back.clicked.connect(self.back_requested.emit)
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)

        title = QLabel("Advanced Settings")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        grp = QGroupBox("FFmpeg Path (troubleshooting only)")
        gl = QVBoxLayout(grp)
        info = QLabel(
            "FFmpeg is bundled automatically with the application.\n"
            "Only use this field if you encounter a persistent FFmpeg error."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;")
        gl.addWidget(info)

        self.status_label = QLabel("")
        gl.addWidget(self.status_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("FFmpeg bin folder:"))
        self.path_input = QLineEdit(get_manual_ffmpeg_path())
        self.path_input.setPlaceholderText(r"e.g. C:\ffmpeg\bin")
        self.path_input.textChanged.connect(self._on_path_changed)
        row.addWidget(self.path_input)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._choose_dir)
        row.addWidget(browse)
        gl.addLayout(row)

        save = QPushButton("Save")
        save.clicked.connect(lambda: set_manual_ffmpeg_path(self.path_input.text().strip()))
        gl.addWidget(save)
        layout.addWidget(grp)
        layout.addStretch()
        self._refresh_status()

    def _choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select FFmpeg bin folder")
        if folder:
            self.path_input.setText(folder)

    def _on_path_changed(self, text):
        set_manual_ffmpeg_path(text.strip())
        self._refresh_status()

    def _refresh_status(self):
        manual = self.path_input.text().strip()
        _exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        if manual and os.path.isfile(os.path.join(manual, _exe)):
            self.status_label.setText(f"✅ FFmpeg found (manual path): {manual}")
            return
        if get_bundled_ffmpeg_path():
            self.status_label.setText("✅ Ready — bundled FFmpeg detected.")
            return
        auto = find_ffmpeg_bin_dir()
        if auto:
            self.status_label.setText(f"✅ FFmpeg detected automatically: {auto}")
        elif is_ffmpeg_on_system_path():
            self.status_label.setText("✅ FFmpeg found in system PATH.")
        else:
            self.status_label.setText("⚠ FFmpeg not found. Set the path above.")

    def set_lang(self, lang):
        pass
