"""
Pop-up affiché au démarrage quand une nouvelle version est disponible.
"""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)


class UpdateDialog(QDialog):
    def __init__(self, current_version, update_info, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setWindowTitle("Update available")
        self.setFixedSize(420, 300)
        self.setStyleSheet("background:#141622;")
        self._build_ui(current_version, update_info)

    def _build_ui(self, current, info):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("\U0001F53A")   # petit triangle rouge
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:40px; background:transparent;")
        layout.addWidget(icon)
        layout.addSpacing(10)

        title = QLabel("A new version is available")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color:#ffffff; font-size:19px; font-weight:700;"
            "font-family:'Segoe UI',Arial; background:transparent;")
        layout.addWidget(title)
        layout.addSpacing(6)

        version_line = QLabel(
            f"You have v{current} \u2014 latest is v{info['latest']}")
        version_line.setAlignment(Qt.AlignCenter)
        version_line.setStyleSheet(
            "color:#e8542e; font-size:13px; font-weight:600;"
            "background:transparent;")
        layout.addWidget(version_line)
        layout.addSpacing(12)

        if info.get("notes"):
            notes = QLabel(info["notes"])
            notes.setWordWrap(True)
            notes.setAlignment(Qt.AlignCenter)
            notes.setStyleSheet(
                "color:#8892a4; font-size:12px; background:transparent;"
                "font-family:'Segoe UI',Arial;")
            layout.addWidget(notes)
            layout.addSpacing(16)
        else:
            layout.addSpacing(8)

        # Bouton principal : télécharger
        download_btn = QPushButton("Download the new version")
        download_btn.setFixedHeight(42)
        download_btn.setCursor(Qt.PointingHandCursor)
        download_btn.setStyleSheet(
            "QPushButton { background:#e8542e; color:#ffffff; border:none;"
            "border-radius:8px; font-size:13px; font-weight:600; }"
            "QPushButton:hover { background:#ff6b45; }")
        download_btn.clicked.connect(self._download)
        layout.addWidget(download_btn)
        layout.addSpacing(6)

        # Bouton secondaire : plus tard
        later_btn = QPushButton("Later")
        later_btn.setFixedHeight(34)
        later_btn.setCursor(Qt.PointingHandCursor)
        later_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#8892a4; border:none;"
            "font-size:12px; }"
            "QPushButton:hover { color:#ffffff; }")
        later_btn.clicked.connect(self.accept)
        layout.addWidget(later_btn)

    def _download(self):
        url = self.update_info.get("url", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()
