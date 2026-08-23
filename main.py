"""
Suite Post-Production — point d'entrée principal.
"""

import sys
import os
import traceback

# freeze_support() DOIT être appelé le plus tôt possible (avant les imports
# lourds), sinon sur macOS/Windows packagé, les sous-processus multiprocessing
# (faster-whisper, demucs...) relancent l'application entière.
import multiprocessing
multiprocessing.freeze_support()

from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QFont, QColor, QPalette, QPixmap, QIcon, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QProgressBar,
    QFrame, QSizePolicy, QScrollArea
)

# Chemin absolu du dossier de l'app (compatible .exe PyInstaller)
from core.paths import app_dir as _app_dir
APP_DIR = _app_dir()
LOGO_PATH = os.path.join(APP_DIR, "assets", "logo.png")
# Icône carrée (piment détouré, transparent) pour l'icône de fenêtre/barre
# des tâches : logo.png est au format portrait et s'affiche mal en icône.
ICON_PATH = os.path.join(APP_DIR, "assets", "logo_icon.png")
if not os.path.exists(ICON_PATH):
    ICON_PATH = LOGO_PATH

# Nom de la famille de police custom (rempli au chargement)
TITLE_FONT_FAMILY = None


def load_title_font():
    """Charge la police custom 'boldone' depuis assets/ et retourne le nom
    de sa famille. Essaie .otf puis .ttf. Retourne None si introuvable."""
    global TITLE_FONT_FAMILY
    if TITLE_FONT_FAMILY:
        return TITLE_FONT_FAMILY
    for ext in ("otf", "ttf", "OTF", "TTF"):
        path = os.path.join(APP_DIR, "assets", f"boldone.{ext}")
        if os.path.exists(path):
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    TITLE_FONT_FAMILY = families[0]
                    return TITLE_FONT_FAMILY
    return None

from pages.home_page     import HomePage
from pages.downloader_page  import DownloaderPage
from pages.mediainfo_page   import MediaInfoPage
from pages.encoder_page     import EncoderPage
from pages.transcription_page import TranscriptionPage
from pages.cuesheet_page    import CueSheetPage
from pages.multicam_page    import MulticamPage
from pages.pdf_page         import PdfPage
from pages.audioclean_page  import AudioCleanPage
from pages.settings_page    import SettingsPage
from pages.donation_dialog  import DonationDialog
from pages.update_dialog    import UpdateDialog
from core.donations         import KOFI_URL
from core.updater           import check_for_update, CURRENT_VERSION

# ── Labels traduits ───────────────────────────────────────────────────────────

LABELS = {
    "en": {
        "app_name":   "Pimiento Video",
        "home":       "Home",
        "modules": [
            ("⬇", "Video Downloader"),
            ("📊", "Media Info"),
            ("🎬", "Encoder"),
            ("📝", "Transcript"),
            ("🎵", "Cue Sheet"),
            ("🎥", "Multicam Sync"),
            ("📄", "PDF Tools"),
            ("🎤", "Audio Lab"),
        ],
        "settings":   "Settings",
        "lang_btn":   "FR",
    },
    "fr": {
        "app_name":   "Pimiento Video",
        "home":       "Accueil",
        "modules": [
            ("⬇", "Téléchargeur"),
            ("📊", "Métadonnées"),
            ("🎬", "Encodeur"),
            ("📝", "Transcription"),
            ("🎵", "Droits musicaux"),
            ("🎥", "Synchro multi-cam"),
            ("📄", "Outils PDF"),
            ("🎤", "Nettoyage audio"),
        ],
        "settings":   "Paramètres",
        "lang_btn":   "EN",
    },
}

SIDEBAR_STYLE = """
QWidget#sidebar {
    background-color: #12141e;
    border-right: 1px solid #2a2d3e;
}
QPushButton#navBtn {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: #8892a4;
    font-size: 12px;
    text-align: left;
    padding: 9px 14px 9px 12px;
    border-radius: 0px;
}
QPushButton#navBtn:hover {
    background: #1e2235;
    color: #ffffff;
    border-left: 3px solid #3d4260;
}
QPushButton#navBtn[active=true] {
    background: rgba(232,84,46,0.10);
    color: #e8542e;
    border-left: 3px solid #e8542e;
    font-weight: 600;
}
QPushButton#homeBtn {
    background: transparent;
    border: none;
    color: #5a6380;
    font-size: 11px;
    text-align: left;
    padding: 7px 14px;
}
QPushButton#homeBtn:hover { color: #ffffff; background: #1e2235; }
QPushButton#langBtn {
    background: #1e2235;
    border: 1px solid #2a2d3e;
    color: #8892a4;
    font-size: 11px;
    border-radius: 4px;
    padding: 5px 12px;
}
QPushButton#langBtn:hover { background: #2a2d3e; color: #ffffff; }
"""

# ── Splash screen ─────────────────────────────────────────────────────────────

class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(520, 360)
        self.setStyleSheet("background:#0d0f1a;")
        self._build_ui()
        self._center_on_screen()
        self._step = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(0)
        layout.addStretch()

        # Logo PNG centré
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(150, 150)
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("background:transparent;")
        pix = QPixmap(LOGO_PATH)
        if not pix.isNull():
            logo_lbl.setPixmap(
                pix.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo_lbl.setText("🌶")
            logo_lbl.setStyleSheet("font-size:70px; background:transparent;")
        layout.addWidget(logo_lbl, alignment=Qt.AlignCenter)
        layout.addSpacing(16)

        title = QLabel("Pimiento Video")
        title.setAlignment(Qt.AlignCenter)
        _fam = TITLE_FONT_FAMILY or "Segoe UI"
        title.setStyleSheet(
            f"color:#ffffff; font-size:34px; font-weight:700;"
            f"font-family:'{_fam}','Segoe UI',Arial; background:transparent;"
            f"letter-spacing:1px;"
        )
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = QLabel("Professional Post-Production Toolkit")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            "color:#4a5270; font-size:12px;"
            "font-family:'Segoe UI',Arial; background:transparent;"
        )
        layout.addWidget(sub)
        layout.addStretch()

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #1e2235;
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background: #e8542e;
                border-radius: 1px;
            }
        """)
        layout.addWidget(self._progress)
        layout.addSpacing(12)

        version = QLabel(f"v{CURRENT_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(
            "color:#ffffff; font-size:12px; font-weight:600; "
            "letter-spacing:1px; background:transparent;")
        layout.addWidget(version)
        layout.addSpacing(4)

        author = QLabel("Created by Lucien Oudin")
        author.setAlignment(Qt.AlignCenter)
        author.setStyleSheet(
            "color:#e8542e; font-size:10px; background:transparent;"
            "font-family:'Segoe UI',Arial;")
        layout.addWidget(author)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    def show_and_run(self, callback):
        self._callback = callback
        self.show()
        self._timer.start()

    def _tick(self):
        self._step += 1
        pct = min(100, int(self._step / 100 * 100))
        self._progress.setValue(pct)
        if self._step >= 100:
            self._timer.stop()
            QTimer.singleShot(200, self._finish)

    def _finish(self):
        self.close()
        self._callback()


# ── Sidebar ────────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    def __init__(self, lang="en", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(198)
        self.setStyleSheet(SIDEBAR_STYLE)
        self.lang = lang
        self._nav_buttons = []
        self._callbacks = {}
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # En-tête sidebar — vide et épuré (le logo est dans le header de droite)
        logo_area = QWidget()
        logo_area.setFixedHeight(24)
        logo_area.setStyleSheet("background:#0a0c14;")
        self._layout.addWidget(logo_area)

        # Home button
        self._home_btn = QPushButton("  🏠  Home")
        self._home_btn.setObjectName("homeBtn")
        self._home_btn.setFixedHeight(34)
        self._home_btn.clicked.connect(lambda: self._callbacks.get("home", lambda: None)())
        self._layout.addWidget(self._home_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#1e2235; margin: 0 12px;")
        self._layout.addWidget(sep)
        self._layout.addSpacing(4)

        # Module buttons (will be populated)
        self._modules_widget = QWidget()
        self._modules_layout = QVBoxLayout(self._modules_widget)
        self._modules_layout.setContentsMargins(0, 0, 0, 0)
        self._modules_layout.setSpacing(1)
        self._layout.addWidget(self._modules_widget)

        self._layout.addStretch()

        # Bottom: settings + language
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#1e2235; margin: 0 12px;")
        bottom_layout.addWidget(sep2)

        # Bouton Support / Don (Ko-fi)
        self._support_btn = QPushButton("  \u2615   Support")
        self._support_btn.setObjectName("navBtn")
        self._support_btn.setFixedHeight(38)
        self._support_btn.setStyleSheet(
            "QPushButton#navBtn { color:#e8542e; }"
            "QPushButton#navBtn:hover { background:#1e2235; color:#ff6b45; }")
        self._support_btn.clicked.connect(
            lambda: self._callbacks.get("support", lambda: None)())
        bottom_layout.addWidget(self._support_btn)

        version_lbl = QLabel(f"Pimiento Video · v{CURRENT_VERSION}")
        version_lbl.setStyleSheet(
            "color:#2a2d3e; font-size:9px; font-family:'Segoe UI',Arial;"
            "background:transparent; padding: 2px 14px;"
        )
        bottom_layout.addWidget(version_lbl)

        self._settings_btn = QPushButton("  ⚙   Settings")
        self._settings_btn.setObjectName("navBtn")
        self._settings_btn.setFixedHeight(38)
        self._settings_btn.clicked.connect(
            lambda: self._callbacks.get("settings", lambda: None)())
        bottom_layout.addWidget(self._settings_btn)
        bottom_layout.addSpacing(8)

        self._layout.addWidget(bottom)
        self._populate_modules()

    def _populate_modules(self):
        for btn in self._nav_buttons:
            btn.deleteLater()
        self._nav_buttons.clear()
        while self._modules_layout.count():
            item = self._modules_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, (icon, name) in enumerate(LABELS["en"]["modules"]):
            btn = QPushButton(f"  {icon}  {name}")
            btn.setObjectName("navBtn")
            btn.setFixedHeight(40)
            btn.setProperty("active", False)
            btn.clicked.connect(
                lambda _, i=idx: self._callbacks.get("module", lambda x: None)(i))
            self._nav_buttons.append(btn)
            self._modules_layout.addWidget(btn)

        self._home_btn.setText("  🏠  Home")
        self._settings_btn.setText("  ⚙   Settings")

    def set_active_module(self, idx):
        for i, btn in enumerate(self._nav_buttons):
            active = (i == idx)
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_active_none(self):
        for btn in self._nav_buttons:
            btn.setProperty("active", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def on(self, event, callback):
        self._callbacks[event] = callback


# ── Fenêtre principale ─────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pimiento Video")
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(1200, 780)
        self.resize(1440, 900)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────
        self.sidebar = Sidebar()
        self.sidebar.on("home",         self._go_home)
        self.sidebar.on("module",       self._go_module)
        self.sidebar.on("settings",     self._go_settings)
        self.sidebar.on("support",      self._open_donation)
        self.sidebar.on("lang_changed", self._on_lang_changed)
        root.addWidget(self.sidebar)

        # ── Contenu ──────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:#141622;")
        root.addWidget(self.stack)

        # Pages
        self.home_page         = HomePage()
        self.downloader_page   = DownloaderPage()
        self.mediainfo_page    = MediaInfoPage()
        self.encoder_page      = EncoderPage()
        self.transcription_page = TranscriptionPage()
        self.cuesheet_page     = CueSheetPage()
        self.multicam_page     = MulticamPage()
        self.pdf_page          = PdfPage()
        self.audioclean_page   = AudioCleanPage()
        self.settings_page     = SettingsPage()

        self.stack.addWidget(self.home_page)          # 0
        self.stack.addWidget(self.downloader_page)    # 1
        self.stack.addWidget(self.mediainfo_page)     # 2
        self.stack.addWidget(self.encoder_page)       # 3
        self.stack.addWidget(self.transcription_page) # 4
        self.stack.addWidget(self.cuesheet_page)      # 5
        self.stack.addWidget(self.multicam_page)      # 6
        self.stack.addWidget(self.pdf_page)           # 7
        self.stack.addWidget(self.audioclean_page)    # 8
        self.stack.addWidget(self.settings_page)      # 9

        # Connexions home_page → modules
        for i, signal in enumerate([
            self.home_page.open_downloader,
            self.home_page.open_mediainfo,
            self.home_page.open_encoder,
            self.home_page.open_transcription,
            self.home_page.open_cuesheet,
            self.home_page.open_multicam,
            self.home_page.open_pdf,
            self.home_page.open_audioclean,
        ], start=0):
            signal.connect(lambda idx=i: self._go_module(idx))

        # Connexions boutons "Accueil" sur chaque page
        for page in [
            self.downloader_page, self.mediainfo_page, self.encoder_page,
            self.transcription_page, self.cuesheet_page, self.multicam_page,
            self.pdf_page, self.audioclean_page, self.settings_page,
        ]:
            page.back_requested.connect(self._go_home)

    def _go_home(self):
        self.stack.setCurrentIndex(0)
        self.sidebar.set_active_none()

    def _go_module(self, idx):
        self.stack.setCurrentIndex(idx + 1)
        self.sidebar.set_active_module(idx)

    def _go_settings(self):
        self.stack.setCurrentIndex(9)
        self.sidebar.set_active_none()

    def _on_lang_changed(self, lang):
        """Propage le changement de langue à toutes les pages."""
        from core.lang import LangManager
        LangManager.get().set(lang)
        for page in [
            self.home_page, self.downloader_page, self.mediainfo_page,
            self.encoder_page, self.transcription_page, self.cuesheet_page,
            self.multicam_page, self.pdf_page, self.audioclean_page,
            self.settings_page,
        ]:
            if hasattr(page, "set_lang"):
                page.set_lang(lang)

    def _open_donation(self):
        """Ouvre directement la page Ko-fi (bouton sidebar)."""
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(KOFI_URL))

    def closeEvent(self, event):
        """À la fermeture : proposer un don (sauf si déjà donné), puis
        arrêter proprement le thread de vérification des mises à jour.
        Sans cet arrêt propre, macOS signale un crash à chaque fermeture."""
        dlg = DonationDialog(self)
        dlg.exec()

        # Arrêter le thread de mise à jour s'il tourne encore.
        thread = getattr(self, "_update_thread", None)
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(3000)  # attendre max 3 s qu'il se termine
            except RuntimeError:
                pass  # thread déjà supprimé, rien à faire

        event.accept()


# ── Entrée ────────────────────────────────────────────────────────────────────

def _check_updates_async(window):
    """Vérifie les mises à jour sans bloquer le démarrage, et affiche le
    pop-up sur le thread principal. Le dialogue DOIT être créé sur le thread
    principal (celui de l'interface), sinon Qt plante (segfault / fond blanc).
    """
    from PySide6.QtCore import QThread, Signal, QObject, Qt as _Qt

    # Ce récepteur VIT sur le thread principal (il est créé ici, dans main()).
    # Son slot _on_found sera donc exécuté sur le thread principal grâce à la
    # connexion Queued, ce qui rend la création du dialogue sûre.
    class _UpdateReceiver(QObject):
        def _on_found(self, info):
            try:
                dlg = UpdateDialog(CURRENT_VERSION, info, window)
                dlg.exec()
            except Exception:
                pass

    class _UpdateWorker(QObject):
        found = Signal(dict)

        def run(self):
            info = check_for_update()
            if info:
                self.found.emit(info)

    receiver = _UpdateReceiver()          # vit sur le thread principal
    thread = QThread()
    worker = _UpdateWorker()
    worker.moveToThread(thread)           # le worker vit sur le thread secondaire

    # Connexion Queued : le slot du receiver (thread principal) est appelé
    # sur le thread principal même si le signal part du thread secondaire.
    worker.found.connect(receiver._on_found, _Qt.QueuedConnection)
    thread.started.connect(worker.run)
    worker.found.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()

    # Garder les références pour éviter le garbage collection
    window._update_thread = thread
    window._update_worker = worker
    window._update_receiver = receiver


def main():
    app = QApplication(sys.argv)
    if os.path.exists(LOGO_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    app.setApplicationName("Pimiento Video")
    app.setStyle("Fusion")

    # Charger la police custom pour les titres
    load_title_font()

    # Palette sombre globale
    palette = QPalette()
    palette.setColor(QPalette.Window,        QColor("#141622"))
    palette.setColor(QPalette.WindowText,    QColor("#e8eaf0"))
    palette.setColor(QPalette.Base,          QColor("#1a1d2e"))
    palette.setColor(QPalette.AlternateBase, QColor("#1e2235"))
    palette.setColor(QPalette.Text,          QColor("#e8eaf0"))
    palette.setColor(QPalette.Button,        QColor("#1e2235"))
    palette.setColor(QPalette.ButtonText,    QColor("#e8eaf0"))
    palette.setColor(QPalette.Highlight,     QColor("#e8542e"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Link,          QColor("#e8542e"))
    app.setPalette(palette)

    splash = SplashScreen()
    window = None

    def launch():
        nonlocal window
        window = MainWindow()
        window.show()
        # Vérifier les mises à jour en arrière-plan (ne bloque pas le démarrage)
        _check_updates_async(window)

    splash.show_and_run(launch)

    try:
        sys.exit(app.exec())
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    # IMPORTANT (macOS surtout) : quand l'app est packagée, les bibliothèques
    # qui utilisent le multiprocessing (faster-whisper, demucs, torch...)
    # relancent l'exécutable pour créer leurs sous-processus. Sans cet appel,
    # chaque sous-processus rouvre TOUTE l'application (fenêtres en double).
    # freeze_support() intercepte ce cas et exécute seulement le worker.
    import multiprocessing
    multiprocessing.freeze_support()
    main()
