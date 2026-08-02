from core.sounds import play_done, play_error
from core.lang import LangManager, tr, TLabel, TButton, TGroupBox, TCheckBox
"""
Module 1 : Téléchargeur vidéo multi-plateformes
Basé sur yt-dlp (YouTube, TikTok, Facebook, Instagram, Vimeo, etc.)
"""

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QComboBox,
    QPushButton, QFileDialog, QProgressBar, QCheckBox, QLineEdit,
    QGroupBox, QMessageBox
)

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from core.ffmpeg_utils import resolve_ffmpeg_location, is_ffmpeg_on_system_path
from core.settings_store import get_manual_ffmpeg_path


VIDEO_CONTAINERS = ["mp4", "mkv", "mov"]
AUDIO_FORMATS = ["mp3", "wav", "m4a"]
RESOLUTIONS = {
    "Best available": None,
    "4K (2160p)": 2160,
    "1440p (QHD)": 1440,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
}


class DownloadWorker(QThread):
    """Exécute les téléchargements yt-dlp dans un thread séparé pour ne pas geler l'UI."""

    log_message = Signal(str)
    progress_value = Signal(int)
    item_started = Signal(str, int, int)  # url, index, total
    finished_all = Signal(bool)  # True si tout s'est bien passé

    def __init__(self, urls, output_dir, mode, container, resolution_height,
                 is_playlist, parent=None):
        super().__init__(parent)
        self.urls = urls
        self.output_dir = output_dir
        self.mode = mode  # "video" ou "audio"
        self.container = container
        self.resolution_height = resolution_height  # int ou None
        self.is_playlist = is_playlist
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def _progress_hook(self, d):
        if self._stop_requested:
            raise yt_dlp.utils.DownloadError("Download cancelled by user.")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                self.progress_value.emit(int(downloaded / total * 100))
        elif status == "finished":
            self.progress_value.emit(100)
            self.log_message.emit("  -> Fusion / post-traitement en cours...")

    def _build_format_string(self):
        if self.mode == "audio":
            return "bestaudio/best"
        if self.resolution_height:
            h = self.resolution_height
            # Fallback élargi : certains sites (Instagram, TikTok) ne fournissent
            # qu'un flux combiné, d'où les alternatives après les /
            return (f"bestvideo[height<={h}]+bestaudio/"
                    f"best[height<={h}]/best")
        return "bestvideo+bestaudio/best/best"

    def _build_postprocessors(self):
        if self.mode == "audio":
            quality_map = {"mp3": "192", "wav": "0", "m4a": "192"}
            return [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.container,
                "preferredquality": quality_map.get(self.container, "192"),
            }]
        return [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": self.container,
        }]

    def run(self):
        if yt_dlp is None:
            self.log_message.emit(
                "ERREUR : yt-dlp n'est pas installé. "
                "Lance : pip install -r requirements.txt"
            )
            self.finished_all.emit(False)
            return

        os.makedirs(self.output_dir, exist_ok=True)

        manual_path = get_manual_ffmpeg_path()
        ffmpeg_location = resolve_ffmpeg_location(manual_path)
        if ffmpeg_location:
            self.log_message.emit("FFmpeg ready.")
        elif is_ffmpeg_on_system_path():
            self.log_message.emit("FFmpeg found in system PATH.")
        else:
            self.log_message.emit(
                "⚠ WARNING: FFmpeg not found. Open Advanced Settings "
                "from the home page (⚙ icon) to set its location."
            )

        ydl_opts = {
            "outtmpl": os.path.join(self.output_dir, "%(title)s.%(ext)s"),
            "format": self._build_format_string(),
            "postprocessors": self._build_postprocessors(),
            "noplaylist": not self.is_playlist,
            "progress_hooks": [self._progress_hook],
            "ignoreerrors": False,
            "merge_output_format": self.container if self.mode == "video" else None,
            "quiet": True,
            "no_warnings": True,
            # En-têtes navigateur : améliore la compatibilité avec Instagram,
            # TikTok, Facebook qui bloquent les requêtes "non-navigateur"
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        }
        if ffmpeg_location:
            ydl_opts["ffmpeg_location"] = ffmpeg_location

        total = len(self.urls)
        success = True

        for index, url in enumerate(self.urls, start=1):
            if self._stop_requested:
                self.log_message.emit("Cancelled.")
                break

            self.item_started.emit(url, index, total)
            self.progress_value.emit(0)
            self.log_message.emit(f"[{index}/{total}] Starting: {url}")

            # ── Générer un template de sortie unique pour éviter les doublons ──
            # yt-dlp skippe un fichier déjà présent. On récupère d'abord le
            # titre pour construire un nom libre (_1, _2, ... si nécessaire).
            per_url_opts = dict(ydl_opts)
            try:
                unique_tmpl = self._build_unique_outtmpl(url, ydl_opts)
                if unique_tmpl:
                    per_url_opts["outtmpl"] = unique_tmpl
            except Exception:
                pass  # en cas d'échec, on garde le template par défaut

            downloaded_ok = False
            try:
                with yt_dlp.YoutubeDL(per_url_opts) as ydl:
                    ydl.download([url])
                self.log_message.emit(f"[{index}/{total}] Done.")
                downloaded_ok = True
            except Exception as e:
                err_text = str(e).lower()
                # Erreurs typiques de blocage (Instagram, Facebook, contenus
                # qui exigent d'être connecté)
                blocked = any(k in err_text for k in [
                    "cookies", "empty media response", "login required",
                    "log in", "private", "rate-limit", "sign in",
                    "not available", "unable to extract"
                ])
                is_instagram = "instagram.com" in url.lower()
                if blocked and is_instagram and not self._stop_requested:
                    self.log_message.emit(
                        f"  Instagram blocked the direct download. "
                        f"Trying alternative methods…")
                    if self._instagram_cascade(url, per_url_opts, index, total):
                        downloaded_ok = True
                    else:
                        success = False
                elif blocked and not self._stop_requested:
                    # Autres sites bloqués : tenter les cookies navigateur
                    self.log_message.emit(
                        f"  This content may require login. "
                        f"Trying with your browser's cookies…")
                    if self._try_with_cookies(url, per_url_opts, index, total):
                        downloaded_ok = True
                    else:
                        success = False
                else:
                    success = False
                    self.log_message.emit(f"[{index}/{total}] ERROR: {e}")

        self.finished_all.emit(success)

    # ── Cascade Instagram : embed yt-dlp → scraping embed → cookies ─────────
    def _instagram_cascade(self, url, base_opts, index, total):
        """Essaie plusieurs méthodes alternatives pour Instagram, dans l'ordre.
        Retourne True dès qu'une méthode réussit."""
        import re

        # Extraire le shortcode du reel/post
        m = re.search(r"instagram\.com/(?:reels?|p|tv)/([A-Za-z0-9_-]+)", url)
        shortcode = m.group(1) if m else None

        # ── Méthode 1 : yt-dlp sur l'URL embed (souvent moins verrouillée) ──
        if shortcode:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            self.log_message.emit("  Method 1/3: trying Instagram embed page…")
            try:
                import yt_dlp
                opts = dict(base_opts)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([embed_url])
                self.log_message.emit(f"[{index}/{total}] Done (via embed page).")
                return True
            except Exception:
                pass

        # ── Méthode 2 : scraping direct de la page embed ────────────────────
        if shortcode:
            self.log_message.emit("  Method 2/3: extracting video from embed HTML…")
            try:
                video_url = self._scrape_instagram_embed(shortcode)
                if video_url:
                    out_path = self._direct_download(video_url, shortcode)
                    if out_path:
                        self.log_message.emit(
                            f"[{index}/{total}] Done (direct extraction): "
                            f"{os.path.basename(out_path)}")
                        return True
            except Exception as e:
                self.log_message.emit(f"    (extraction failed: {e})")

        # ── Méthode 3 : cookies du navigateur ───────────────────────────────
        self.log_message.emit("  Method 3/3: trying your browser's cookies…")
        if self._try_with_cookies(url, base_opts, index, total, quiet=True):
            return True

        self.log_message.emit(
            f"[{index}/{total}] ERROR: All methods failed. Instagram is "
            f"actively blocking downloads for this content. This can be "
            f"temporary — try again later, or make sure you are logged in "
            f"to Instagram in your browser (and close it during download).")
        return False

    def _scrape_instagram_embed(self, shortcode):
        """Récupère la page embed d'Instagram et en extrait l'URL vidéo.
        Retourne l'URL du MP4 ou None."""
        import urllib.request
        import re
        import json as _json

        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        req = urllib.request.Request(embed_url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Piste A : "video_url":"https:\/\/..."
        m = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
        if m:
            video_url = m.group(1)
            # Décoder les échappements JSON (\/ → /, \u0026 → &)
            video_url = video_url.encode().decode("unicode_escape")
            video_url = video_url.replace("\\/", "/")
            return video_url

        # Piste B : contentUrl dans le JSON-LD
        m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', html)
        if m:
            video_url = m.group(1).encode().decode("unicode_escape")
            return video_url.replace("\\/", "/")

        # Piste C : balise <video src="...">
        m = re.search(r'<video[^>]+src="([^"]+)"', html)
        if m:
            import html as _html
            return _html.unescape(m.group(1))

        return None

    def _direct_download(self, video_url, shortcode):
        """Télécharge directement un MP4 depuis son URL CDN.
        Retourne le chemin du fichier ou None."""
        import urllib.request

        ext = self.container if self.mode == "video" else "mp4"
        if ext not in ("mp4", "mov", "mkv"):
            ext = "mp4"
        base_name = f"instagram_{shortcode}"
        out_path = os.path.join(self.output_dir, f"{base_name}.{ext}")
        n = 1
        while os.path.exists(out_path):
            out_path = os.path.join(self.output_dir, f"{base_name}_{n}.{ext}")
            n += 1

        req = urllib.request.Request(video_url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Referer": "https://www.instagram.com/",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(out_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        self.progress_value.emit(
                            int(downloaded / total_size * 100))
        if os.path.getsize(out_path) > 10000:  # au moins 10 Ko = vraie vidéo
            self.progress_value.emit(100)
            return out_path
        os.remove(out_path)
        return None

    def _try_with_cookies(self, url, base_opts, index, total, quiet=False):
        """Réessaie le téléchargement en utilisant les cookies du navigateur.
        Teste plusieurs navigateurs jusqu'à ce que l'un fonctionne.
        Retourne True si le téléchargement réussit."""
        import yt_dlp
        # Navigateurs à essayer, dans l'ordre de popularité
        browsers = ["chrome", "edge", "firefox", "brave", "opera", "chromium"]
        for browser in browsers:
            if self._stop_requested:
                return False
            opts = dict(base_opts)
            opts["cookiesfrombrowser"] = (browser, None, None, None)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                self.log_message.emit(
                    f"[{index}/{total}] Done (using {browser.capitalize()} cookies).")
                return True
            except Exception:
                continue
        if not quiet:
            self.log_message.emit(
                f"[{index}/{total}] ERROR: Could not download even with browser "
                f"cookies. Make sure you are logged in in Chrome, Edge or "
                f"Firefox, and that the browser is closed during download.")
        return False

    def _build_unique_outtmpl(self, url, base_opts):
        """Retourne un template de sortie avec un nom de fichier libre.
        Si 'Ma Video.mp4' existe déjà, renvoie un template menant à
        'Ma Video_1.mp4', puis 'Ma Video_2.mp4', etc."""
        import yt_dlp
        # Récupérer les métadonnées sans télécharger, pour connaître le titre
        probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                      "noplaylist": not self.is_playlist,
                      "http_headers": {
                          "User-Agent": (
                              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
                          ),
                      }}
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            return None
        # yt-dlp nettoie le titre pour le nom de fichier.
        # Instagram/TikTok ont souvent des titres vides ou très longs.
        title = info.get("title") or info.get("id") or "video"
        # Limiter la longueur (Instagram met parfois toute la description)
        title = title[:80]
        # Nettoyage basique des caractères interdits sous Windows
        safe = "".join(c for c in title if c not in '<>:"/\\|?*').strip()
        if not safe:
            safe = "video"

        # Déterminer l'extension finale attendue
        if self.mode == "video":
            ext = self.container or "mp4"
        else:
            ext = self.container or "mp3"

        # Chercher un nom libre
        candidate = os.path.join(self.output_dir, f"{safe}.{ext}")
        if not os.path.exists(candidate):
            base = safe
        else:
            n = 1
            while os.path.exists(os.path.join(self.output_dir, f"{safe}_{n}.{ext}")):
                n += 1
            base = f"{safe}_{n}"
            self.log_message.emit(
                f"  File already exists → saving as \"{base}.{ext}\"")

        return os.path.join(self.output_dir, f"{base}.%(ext)s")


class DownloaderPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)

        top_bar = QHBoxLayout()
        self._t_back = QPushButton(tr("back")); back_btn = self._t_back
        back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        title = self._t_title = QLabel(tr("dl_title")); _ = self._t_title
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        url_label = QLabel("URLs to download (one per line):")
        url_label.setStyleSheet("border: none; color: #666666;")
        layout.addWidget(url_label)
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "Paste one or more video URLs here, one per line\n\n"
            "https://www.youtube.com/watch?v=...\n"
            "https://www.tiktok.com/@user/video/...\n"
            "https://www.facebook.com/.../videos/..."
        )
        self.url_input.setFixedHeight(120)
        self.url_input.setStyleSheet(
            "QTextEdit {"
            "  background: #1e2235;"
            "  border: 2px solid #e8542e;"
            "  border-radius: 8px;"
            "  padding: 10px;"
            "  color: #666666;"
            "}"
            "QTextEdit:focus { border: 2px solid #ff6b45; }"
        )
        layout.addWidget(self.url_input)

        self.playlist_checkbox = QCheckBox("Download full playlist (if playlist URL)")
        layout.addWidget(self.playlist_checkbox)

        options_group = QGroupBox("Options de sortie")
        options_layout = QHBoxLayout(options_group)

        mode_box = QVBoxLayout()
        mode_box.addWidget(QLabel("Type :"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Video", "Audio only"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_box.addWidget(self.mode_combo)
        options_layout.addLayout(mode_box)

        format_box = QVBoxLayout()
        format_box.addWidget(TLabel("format"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(VIDEO_CONTAINERS)
        format_box.addWidget(self.format_combo)
        options_layout.addLayout(format_box)

        res_box = QVBoxLayout()
        res_box.addWidget(QLabel("Resolution:"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(list(RESOLUTIONS.keys()))
        res_box.addWidget(self.res_combo)
        options_layout.addLayout(res_box)

        layout.addWidget(options_group)

        out_layout = QHBoxLayout()
        out_layout.addWidget(TLabel("output_folder"))
        self.output_path = QLineEdit(os.path.join(os.path.expanduser("~"), "Downloads"))
        out_layout.addWidget(self.output_path)
        browse_btn = TButton("browse")
        browse_btn.clicked.connect(self._choose_output_dir)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)

        action_layout = QHBoxLayout()
        self.download_btn = TButton("dl_btn")
        self.download_btn.setMinimumHeight(36)
        self.download_btn.clicked.connect(self._start_download)
        action_layout.addWidget(self.download_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_download)
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

    def _on_mode_changed(self, mode_text):
        self.format_combo.clear()
        if mode_text == "Video":
            self.format_combo.addItems(VIDEO_CONTAINERS)
            self.res_combo.setEnabled(True)
        else:
            self.format_combo.addItems(AUDIO_FORMATS)
            self.res_combo.setEnabled(False)

    def _choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_path.setText(folder)

    def _start_download(self):
        urls = [u.strip() for u in self.url_input.toPlainText().splitlines() if u.strip()]
        if not urls:
            QMessageBox.warning(self, "Aucune URL", "Merci de coller au moins une URL.")
            return

        output_dir = self.output_path.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Missing folder", "Please select an output folder.")
            return

        mode = "video" if self.mode_combo.currentText() == "Video" else "audio"
        container = self.format_combo.currentText()
        resolution_height = RESOLUTIONS[self.res_combo.currentText()] if mode == "video" else None
        is_playlist = self.playlist_checkbox.isChecked()

        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        self.worker = DownloadWorker(
            urls=urls,
            output_dir=output_dir,
            mode=mode,
            container=container,
            resolution_height=resolution_height,
            is_playlist=is_playlist,
        )
        self.worker.log_message.connect(self._append_log)
        self.worker.progress_value.connect(self.progress_bar.setValue)
        self.worker.item_started.connect(self._on_item_started)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_item_started(self, url, index, total):
        self.current_item_label.setText(f"[{index}/{total}] {url}")

    def _cancel_download(self):
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
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.current_item_label.setText("")
        if success:
            self._append_log("✔ All downloads complete.")
        else:
            self._append_log("⚠ Completed with at least one error (see log above).")

    def set_lang(self, lang):
        from core.lang import tr, LangManager
        LangManager.get().current = lang
        if hasattr(self, '_t_title'):   self._t_title.setText(tr("dl_title"))
        if hasattr(self, '_t_dl_btn'):  self._t_dl_btn.setText(tr("dl_btn"))
        if hasattr(self, '_t_back'):    self._t_back.setText(tr("back"))

