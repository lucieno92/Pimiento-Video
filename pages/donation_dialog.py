"""
Fenêtre de don, affichée à la fermeture de l'application.
"""

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)

from core.donations import KOFI_URL

from core.paths import app_dir as _app_dir
_LOGO = os.path.join(_app_dir(), "assets", "logo.png")


class DonationDialog(QDialog):
    """Fenêtre affichée quand l'utilisateur ferme l'app.
    Retourne accept() dans tous les cas (l'app se ferme ensuite)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Support Pimiento Video")
        self.setFixedSize(440, 380)
        self.setStyleSheet("background:#141622;")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        # Logo
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background:transparent;")
        pix = QPixmap(_LOGO)
        if not pix.isNull():
            logo.setPixmap(
                pix.scaled(88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("🌶")
            logo.setStyleSheet("font-size:52px; background:transparent;")
        layout.addWidget(logo, alignment=Qt.AlignCenter)
        layout.addSpacing(14)

        # Titre
        title = QLabel("Enjoying Pimiento Video?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color:#ffffff; font-size:20px; font-weight:700;"
            "font-family:'Segoe UI',Arial; background:transparent;")
        layout.addWidget(title)
        layout.addSpacing(10)

        # Message
        msg = QLabel(
            "Pimiento Video is completely free.\n\n"
            "If this tool is useful to you, you can support its development "
            "and server costs with a small donation. Every bit helps and is "
            "hugely appreciated \u2764"
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(
            "color:#8892a4; font-size:12px; background:transparent;"
            "font-family:'Segoe UI',Arial;")
        layout.addWidget(msg)
        layout.addSpacing(20)

        # Bouton principal : Ko-fi
        donate_btn = QPushButton("\u2615   Support on Ko-fi")
        donate_btn.setFixedHeight(44)
        donate_btn.setCursor(Qt.PointingHandCursor)
        donate_btn.setStyleSheet(
            "QPushButton { background:#e8542e; color:#ffffff; border:none;"
            "border-radius:8px; font-size:14px; font-weight:600; }"
            "QPushButton:hover { background:#ff6b45; }")
        donate_btn.clicked.connect(self._open_kofi)
        layout.addWidget(donate_btn)
        layout.addSpacing(8)

        # Bouton secondaire : plus tard
        later_btn = QPushButton("Maybe later")
        later_btn.setFixedHeight(38)
        later_btn.setCursor(Qt.PointingHandCursor)
        later_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#8892a4; border:none;"
            "font-size:12px; }"
            "QPushButton:hover { color:#ffffff; }")
        later_btn.clicked.connect(self.accept)
        layout.addWidget(later_btn)

    def _open_kofi(self):
        QDesktopServices.openUrl(QUrl(KOFI_URL))
        self.accept()   # ferme la fenêtre de don après ouverture de Ko-fi
