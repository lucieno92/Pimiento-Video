from core.lang import LangManager, tr, TLabel, TButton, TGroupBox, TCheckBox
"""
Page d'accueil : grille des 8 modules avec design pro.
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QSizePolicy
)

_TITLE_FONT_FAMILY = None

def _load_title_font_family():
    """Charge la police custom 'boldone' depuis assets/ (une seule fois)."""
    global _TITLE_FONT_FAMILY
    if _TITLE_FONT_FAMILY is not None:
        return _TITLE_FONT_FAMILY
    from core.paths import app_dir as _app_dir
    base = _app_dir()
    for ext in ("otf", "ttf", "OTF", "TTF"):
        path = os.path.join(base, "assets", f"boldone.{ext}")
        if os.path.exists(path):
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id != -1:
                fams = QFontDatabase.applicationFontFamilies(font_id)
                if fams:
                    _TITLE_FONT_FAMILY = fams[0]
                    return _TITLE_FONT_FAMILY
    _TITLE_FONT_FAMILY = "Segoe UI"
    return _TITLE_FONT_FAMILY

MODULES = [
    ("⬇",  "Video Downloader", "Download videos & audio from YouTube, Vimeo, TikTok and more."),
    ("📊", "Media Info",       "Inspect any video or audio file — codec, frame rate, timecode, camera profile."),
    ("🎬", "Encoder",          "Convert and export to ProRes, DNxHD, H.264, XDCAM, and more."),
    ("📝", "Transcript",       "Transcribe audio/video with Whisper, export to SRT, VTT, Word or PDF."),
    ("🎵", "Cue Sheet",        "Import an EDL and auto-generate music rights reports in PDF or Word."),
    ("🎥", "Multicam Sync",    "Drop your card folders — timecode or waveform sync, export XML or AAF."),
    ("📄", "PDF Tools",        "Merge, split, compress, convert PDFs to Word, Excel or JPEG."),
    ("🎤", "Audio Lab",        "Clean noise, enhance voice, separate vocals/music, or generate AI voice-overs."),
]

CARD_STYLE = """
QFrame#moduleCard {
    background: #22263a;
    border: 1px solid #313650;
    border-left: 3px solid #313650;
    border-radius: 10px;
}
QFrame#moduleCard:hover {
    background: #2a2f47;
    border: 1px solid #e8542e;
    border-left: 3px solid #e8542e;
}
"""

class ModuleCard(QFrame):
    clicked = Signal()

    def __init__(self, icon, title, description, parent=None):
        super().__init__(parent)
        self.setObjectName("moduleCard")
        self.setStyleSheet(CARD_STYLE)
        self.setFixedHeight(130)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size:22px; background:transparent;")
        icon_lbl.setFixedWidth(34)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color:#e8eaf0; font-size:14px; font-weight:600;"
            "font-family:'Segoe UI',Arial; background:transparent;"
        )
        top.addWidget(icon_lbl)
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            "color:#5a6380; font-size:11px;"
            "font-family:'Segoe UI',Arial; background:transparent;"
        )
        layout.addWidget(desc_lbl)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


SIGNALS = [
    "open_downloader", "open_mediainfo", "open_encoder",
    "open_transcription", "open_cuesheet", "open_multicam",
    "open_pdf", "open_audioclean",
]


class HomePage(QWidget):
    open_downloader   = Signal()
    open_mediainfo    = Signal()
    open_encoder      = Signal()
    open_transcription = Signal()
    open_cuesheet     = Signal()
    open_multicam     = Signal()
    open_pdf          = Signal()
    open_audioclean   = Signal()
    # Compatibilité avec l'ancien code (settings géré via sidebar)
    back_requested    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(148)
        header.setStyleSheet("background:#0d0f1a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(36, 16, 40, 16)
        header_layout.setSpacing(12)

        # Logo PNG dans le header
        import os
        from PySide6.QtGui import QPixmap
        from core.paths import app_dir as _app_dir
        logo_path = os.path.join(_app_dir(), "assets", "logo.png")
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(120, 120)
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("background:transparent;")
        pix = QPixmap(logo_path)
        if not pix.isNull():
            logo_lbl.setPixmap(
                pix.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo_lbl.setText("🌶")
            logo_lbl.setStyleSheet("font-size:72px; background:transparent;")
        header_layout.addWidget(logo_lbl)

        text_block = QVBoxLayout()
        text_block.setSpacing(3)
        text_block.addStretch()
        title = QLabel("Pimiento Video")
        _fam = _load_title_font_family()
        title.setStyleSheet(
            f"color:#e8542e; font-size:30px; font-weight:700;"
            f"font-family:'{_fam}','Segoe UI',Arial; letter-spacing:0.5px;"
        )
        subtitle = QLabel("Post-Production Suite")
        subtitle.setStyleSheet(
            "color:#5a6380; font-size:13px; font-family:'Segoe UI',Arial;"
            "letter-spacing:0.5px;"
        )
        text_block.addWidget(title)
        text_block.addWidget(subtitle)
        text_block.addStretch()
        header_layout.addLayout(text_block)
        header_layout.addStretch()
        root.addWidget(header)

        # ── Grille de modules ─────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none; background:#141622;}")

        content = QWidget()
        content.setStyleSheet("background:#141622;")
        grid_layout = QVBoxLayout(content)
        grid_layout.setContentsMargins(32, 32, 32, 32)
        grid_layout.setSpacing(0)

        label_section = TLabel("home_section")
        label_section.setStyleSheet(
            "color:#2a2d3e; font-size:10px; font-weight:700;"
            "letter-spacing:3px; font-family:'Segoe UI',Arial;"
        )
        grid_layout.addWidget(label_section)
        grid_layout.addSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(14)
        signals = [
            self.open_downloader, self.open_mediainfo,
            self.open_encoder, self.open_transcription,
            self.open_cuesheet, self.open_multicam,
            self.open_pdf, self.open_audioclean,
        ]
        for i, (icon, title_txt, desc) in enumerate(MODULES):
            card = ModuleCard(icon, title_txt, desc)
            card.clicked.connect(signals[i].emit)
            row, col = divmod(i, 2)
            grid.addWidget(card, row, col)

        grid_layout.addLayout(grid)
        grid_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)
