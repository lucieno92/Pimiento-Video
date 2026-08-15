from core.lang import LangManager, tr, TLabel, TButton, TGroupBox, TCheckBox
"""
Module 2 : Métadonnées (type MediaInfo)

Affiche les métadonnées techniques d'un rush vidéo : nom de fichier, caméra,
nombre d'images, codec, résolution, frame rate, profil LOG, profondeur de
couleur, sous-échantillonnage chroma, pistes audio, sous-titres, et un
résumé condensé des métadonnées de tournage (ISO, shutter, zoom, focus...).

Une section "métadonnées brutes" expose en plus absolument tous les champs
renvoyés par MediaInfo, sans aucun filtre ni déduplication (utile pour
vérifier le nom exact d'un champ si quelque chose manque ailleurs).

Basé sur pymediainfo (wrapper de la bibliothèque MediaInfo).
"""

import os
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QScrollArea, QGroupBox, QFormLayout, QFrame, QTextEdit
)

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None


def format_file_size(num_bytes):
    """Convertit une taille en octets vers une unité lisible (Mo/Go)."""
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return str(num_bytes)
    if num_bytes >= 1_000_000_000:
        return f"{num_bytes / 1_000_000_000:.2f} Go"
    return f"{num_bytes / 1_000_000:.1f} Mo"


def format_bit_rate(bps):
    """Convertit un débit en bits/s vers Mb/s (convention standard pour un débit)."""
    try:
        bps = float(bps)
    except (TypeError, ValueError):
        return str(bps)
    return f"{bps / 1_000_000:.2f} Mb/s"


def format_duration(ms):
    """Convertit une durée en millisecondes vers un format lisible (h/min/s/ms)."""
    try:
        ms = float(ms)
    except (TypeError, ValueError):
        return str(ms)
    total_seconds = ms / 1000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    millis = int(ms % 1000)

    parts = []
    if hours:
        parts.append(f"{hours} h")
    if hours or minutes:
        parts.append(f"{minutes} min")
    parts.append(f"{seconds} s")
    parts.append(f"{millis} ms")
    return " ".join(parts)


# Motifs reconnus de profils LOG (S-Log/S-Log2/S-Log3, V-Log, C-Log,
# Log-C/ARRI, RedLogFilm...). Recherché dans toutes les valeurs textuelles
# de toutes les pistes, pas seulement le champ "transfer_characteristics"
# officiel, car certaines caméras (notamment Sony) ne le déclarent pas
# toujours dans ce champ standard.
_LOG_PATTERN = re.compile(
    r"(s-?log\d?|v-?log|c-?log\d?|log-?c|redlogfilm|canon\s*log\d?)",
    re.IGNORECASE,
)

# Champs candidats pour retrouver le modèle de caméra, par mots-clés (et non
# nom exact) car pymediainfo convertit les majuscules en underscores de façon
# pas toujours prévisible (ex: "FirstFrame" -> "first_frame" et pas
# "firstframe"). "camera" + "attribute" est confirmé sur Sony FX30.
CAMERA_MODEL_KEYWORD_GROUPS = [
    ["camera", "attribute"],
    ["device", "model"],
    ["camera", "model"],
    ["model", "name"],
    ["performer"],
    ["comapplequicktimemodel"],
    ["device", "manufacturer"],
]


class DropZone(QFrame):
    """Zone où on peut glisser-déposer un fichier vidéo."""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(110)
        self.setStyleSheet(
            "QFrame { border: 2px solid #e8542e; border-radius: 8px; background: #1e2235; }"
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Drop a video or audio file here\n(or click \"Browse\" below)")
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
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.file_dropped.emit(path)


class MediaInfoPage(QWidget):
    back_requested = Signal()

    # (attribut, libellé, formateur_optionnel) - pour Vidéo / Audio / Texte.
    # Le General est construit à la main (ordre précis demandé : nom du
    # fichier, conteneur, taille, durée, nombre d'images, débit, date, caméra).
    VIDEO_FIELDS = [
        ("format", "Video codec", None),
        ("format_profile", "Profil", None),
        ("width", "Largeur (px)", None),
        ("height", "Hauteur (px)", None),
        ("display_aspect_ratio", "Ratio d'image", None),
        ("frame_rate", "Frame rate", None),
        ("scan_type", "Type de scan", None),
        ("bit_depth", "Profondeur de couleur (bits)", None),
        ("chroma_subsampling", "Chroma subsampling", None),
        ("color_space", "Colour space", None),
        ("color_primaries", "Colour primaries", None),
        ("transfer_characteristics", "Transfert (gamma)", None),
        ("bit_rate", "Video bitrate", format_bit_rate),
        ("codec_id", "Codec ID", None),
    ]
    AUDIO_FIELDS = [
        ("format", "Codec audio", None),
        ("channel_s", "Nombre de canaux", None),
        ("sampling_rate", "Sample rate", None),
        ("bit_depth", "Profondeur (bits)", None),
        ("bit_rate", "Audio bitrate", format_bit_rate),
        ("language", "Langue", None),
    ]
    TEXT_FIELDS = [
        ("format", "Format", None),
        ("language", "Langue", None),
        ("title", "Titre", None),
    ]

    # Vue condensée des métadonnées de tournage, basée sur la liste de champs
    # confirmée sur un vrai rush Sony FX30. Recherche par MOTS-CLÉS (et non
    # par nom exact) car l'orthographe précise des champs Sony est incertaine
    # (underscores, casse...) ; chaque groupe = (libellé, [mots-clés qui
    # doivent TOUS apparaître dans le nom du champ, peu importe la casse ou
    # les underscores]). Un seul champ affiché par groupe.
    CAMERA_FIELD_GROUPS = [
        ("Mode d'exposition auto", ["autoexposure", "mode"]),
        ("Autofocus settings", ["autofocus", "settings"]),
        ("Mode balance des blancs auto", ["autowhitebalance", "mode"]),
        ("Codec ID (piste additionnelle)", ["codec", "id"]),
        ("Colour primaries (tournage)", ["colorprimaries"]),
        ("Nom commercial", ["commercial", "name"]),
        ("Position de focus", ["focus", "position"]),
        ("ISO", ["iso"]),
        ("Angle d'obturation (shutter angle)", ["shutter", "angle"]),
        ("Vitesse d'obturation (temps)", ["shutter", "time"]),
        ("Balance des blancs", ["whitebalance"]),
    ]

    # Champs qu'on exclut explicitement de cette section car déjà affichés
    # ailleurs (caméra et nombre d'images sont dans "General").
    _CAMERA_SECTION_EXCLUDED_SUBSTRINGS = ["camera_attribute", "framecount", "frame_count"]

    _SKIP_KEYS = {
        "track_type", "track_id", "kind_of_stream", "stream_identifier",
        "streamorder", "id", "other_id",
    }

    @staticmethod
    def _key_matches(key, keywords):
        """Vrai si tous les mots-clés apparaissent dans le nom du champ,
        en ignorant la casse et les underscores."""
        normalized = key.lower().replace("_", "")
        return all(kw.lower().replace("_", "") in normalized for kw in keywords)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_filename = ""
        self._camera_model = None
        self._log_profile = None
        self._exif_camera = None
        self._exif_log = None
        self._frame_count_value = None
        self._frame_count_is_computed = False
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

        title = self._t_title = QLabel(tr("mi_title")); _ = self._t_title
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._load_file)
        layout.addWidget(self.drop_zone)

        browse_layout = QHBoxLayout()
        browse_btn = TButton("browse")
        browse_btn.clicked.connect(self._browse_file)
        browse_layout.addWidget(browse_btn)
        self.file_label = TLabel("no_file")
        self.file_label.setStyleSheet("color: #555555;")
        browse_layout.addWidget(self.file_label)
        browse_layout.addStretch()
        layout.addLayout(browse_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        scroll.setWidget(self.results_container)
        layout.addWidget(scroll)

        self.raw_toggle = QPushButton("Show all raw metadata ▸")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.clicked.connect(self._toggle_raw)
        layout.addWidget(self.raw_toggle)

        self.raw_output = QTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setVisible(False)
        self.raw_output.setFixedHeight(180)
        layout.addWidget(self.raw_output)

    def _toggle_raw(self, checked):
        self.raw_output.setVisible(checked)
        self.raw_toggle.setText(
            "Show all raw metadata ▾" if checked
            else "Show all raw metadata ▸"
        )

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a video file", "",
            "Video files (*.mp4 *.mov *.mxf *.avi *.mkv *.braw *.r3d *.wav);;"
            "Tous les fichiers (*.*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        if not os.path.isfile(path):
            return
        self._current_filename = os.path.basename(path)
        self.file_label.setText(self._current_filename)
        self._clear_results()
        self._camera_model = None
        self._log_profile = None
        self._frame_count_value = None
        self._frame_count_is_computed = False

        # ── ExifTool : lecture prioritaire du modèle caméra + profil LOG ──
        # (décode les MakerNotes propriétaires que MediaInfo ne lit pas)
        self._exif_camera = None
        self._exif_log = None
        try:
            from core.exiftool_reader import read_camera_and_log
            self._exif_camera, self._exif_log = read_camera_and_log(path)
        except Exception:
            pass  # si ExifTool absent/échoue, on retombe sur MediaInfo

        if MediaInfo is None:
            # pymediainfo indisponible (ex: macOS) : on lit via ffprobe/ffmpeg,
            # déjà embarqué dans l'application. Même information à l'écran.
            self._load_file_via_ffprobe(path)
            return

        try:
            media_info = MediaInfo.parse(path)
        except Exception as e:
            # MediaInfo présent mais échoue : dernier recours ffprobe.
            if self._load_file_via_ffprobe(path):
                return
            self._add_section_text("Error", f"Impossible d'analyser ce fichier :\n{e}")
            return

        self._camera_model = self._find_camera_model(media_info.tracks)
        self._log_profile = self._detect_log_profile(media_info.tracks)
        self._frame_count_value, self._frame_count_is_computed = self._find_frame_count(media_info.tracks)
        other_data = self._merge_other_tracks_data(media_info.tracks)

        for track in media_info.tracks:
            if track.track_type == "General":
                self._add_general_section(track)
            elif track.track_type in ("Video", "Audio", "Text"):
                self._add_track_section(track)

        # Une seule section condensée pour les métadonnées de tournage,
        # même si la caméra répétait les mêmes infos sur plusieurs pistes.
        if other_data:
            self._add_camera_section(other_data)

        self.raw_output.setPlainText(self._format_raw(media_info))

    def _load_file_via_ffprobe(self, path):
        """Affiche les métadonnées via ffprobe/ffmpeg (source de secours
        quand pymediainfo est absent). Retourne True si des infos ont pu
        être affichées, False sinon."""
        try:
            from core.ffprobe_reader import read_metadata
            meta = read_metadata(path)
        except Exception:
            meta = None

        if not meta:
            self._add_section_text(
                "Error",
                "Impossible d'analyser ce fichier.\n"
                "Verifiez que FFmpeg est bien disponible."
            )
            return False

        # ── Section General ──
        g = meta.get("general", {})
        box = QGroupBox("General")
        form = QFormLayout(box)
        if self._current_filename:
            form.addRow("Nom du fichier :", QLabel(self._current_filename))
        if g.get("format"):
            form.addRow("Conteneur :", QLabel(str(g["format"])))
        if g.get("size_bytes"):
            form.addRow("Taille du fichier :", QLabel(format_file_size(g["size_bytes"])))
        if g.get("duration_s") is not None:
            form.addRow("Duration:", QLabel(format_duration(g["duration_s"] * 1000)))
        # Nombre d'images : depuis la vidéo si dispo, sinon calculé
        vids = meta.get("video", [])
        nb = None
        if vids:
            nb = vids[0].get("nb_frames")
            if not nb and vids[0].get("frame_rate") and g.get("duration_s"):
                nb = int(round(vids[0]["frame_rate"] * g["duration_s"]))
                self._frame_count_is_computed = True
        if nb:
            lbl = "Frame count (calculated)" if self._frame_count_is_computed else "Nombre d'images"
            form.addRow(f"{lbl} :", QLabel(str(nb)))
        if g.get("bit_rate"):
            form.addRow("Bitrate:", QLabel(format_bit_rate(g["bit_rate"])))
        # Date d'encodage depuis les tags si présente
        tags = g.get("tags", {}) or {}
        enc_date = tags.get("creation_time") or tags.get("date")
        if enc_date:
            form.addRow("Date d'encodage :", QLabel(str(enc_date)))
        # Caméra : ExifTool prioritaire, sinon tag
        cam = self._exif_camera or tags.get("com.apple.quicktime.make") or tags.get("make")
        if cam:
            form.addRow("Camera:", QLabel(str(cam)))
        self.results_layout.addWidget(box)

        # ── Sections Vidéo ──
        for v in vids:
            box = QGroupBox("Video track")
            form = QFormLayout(box)
            if v.get("codec"):
                form.addRow("Codec :", QLabel(str(v["codec"])))
            if v.get("width") and v.get("height"):
                form.addRow("Resolution:", QLabel(f"{v['width']} x {v['height']}"))
            if v.get("frame_rate"):
                form.addRow("Frame rate :", QLabel(f"{v['frame_rate']} fps"))
            if v.get("bit_rate"):
                form.addRow("Bitrate:", QLabel(format_bit_rate(v["bit_rate"])))
            if v.get("pix_fmt"):
                form.addRow("Pixel format :", QLabel(str(v["pix_fmt"])))
            if v.get("color_space"):
                form.addRow("Color space :", QLabel(str(v["color_space"])))
            if v.get("color_transfer"):
                form.addRow("Transfer :", QLabel(str(v["color_transfer"])))
            if v.get("profile"):
                form.addRow("Profil :", QLabel(str(v["profile"])))
            # Profil LOG : ExifTool prioritaire
            log_text = self._exif_log if self._exif_log else "Not detected"
            form.addRow("Profil LOG :", QLabel(log_text))
            self.results_layout.addWidget(box)

        # ── Sections Audio ──
        for a in meta.get("audio", []):
            box = QGroupBox("Piste audio")
            form = QFormLayout(box)
            if a.get("codec"):
                form.addRow("Codec :", QLabel(str(a["codec"])))
            if a.get("sample_rate"):
                form.addRow("Sample rate :", QLabel(f"{a['sample_rate']} Hz"))
            if a.get("channels"):
                form.addRow("Channels :", QLabel(str(a["channels"])))
            if a.get("channel_layout"):
                form.addRow("Layout :", QLabel(str(a["channel_layout"])))
            if a.get("bit_rate"):
                form.addRow("Bitrate:", QLabel(format_bit_rate(a["bit_rate"])))
            self.results_layout.addWidget(box)

        # ── Sections Texte / Sous-titres ──
        for t in meta.get("text", []):
            box = QGroupBox("Sous-titres / Texte")
            form = QFormLayout(box)
            if t.get("codec"):
                form.addRow("Codec :", QLabel(str(t["codec"])))
            self.results_layout.addWidget(box)

        return True

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_section_text(self, title, text):
        box = QGroupBox(title)
        v = QVBoxLayout(box)
        label = QLabel(text)
        label.setWordWrap(True)
        v.addWidget(label)
        self.results_layout.addWidget(box)

    def _add_general_section(self, track):
        """Construit la section General dans un ordre précis et fixe :
        nom du fichier, conteneur, taille, durée, nombre d'images, débit
        global, date d'encodage, caméra."""
        box = QGroupBox("General")
        form = QFormLayout(box)
        any_value = False

        if self._current_filename:
            form.addRow("Nom du fichier :", QLabel(self._current_filename))
            any_value = True

        value = getattr(track, "format", None)
        if value not in (None, ""):
            form.addRow("Conteneur :", QLabel(str(value)))
            any_value = True

        value = getattr(track, "file_size", None)
        if value not in (None, ""):
            form.addRow("Taille du fichier :", QLabel(format_file_size(value)))
            any_value = True

        value = getattr(track, "duration", None)
        if value not in (None, ""):
            form.addRow("Duration:", QLabel(format_duration(value)))
            any_value = True

        if self._frame_count_value:
            label = "Frame count (calculated)" if self._frame_count_is_computed else "Nombre d'images"
            form.addRow(f"{label} :", QLabel(self._frame_count_value))
            any_value = True

        value = getattr(track, "overall_bit_rate", None)
        if value not in (None, ""):
            form.addRow("Bitrate:", QLabel(format_bit_rate(value)))
            any_value = True

        value = getattr(track, "encoded_date", None)
        if value not in (None, ""):
            form.addRow("Date d'encodage :", QLabel(str(value)))
            any_value = True

        if self._camera_model:
            form.addRow("Camera:", QLabel(self._camera_model))
            any_value = True

        if any_value:
            self.results_layout.addWidget(box)
        else:
            box.deleteLater()

    def _add_track_section(self, track):
        track_type = track.track_type
        titles = {
            "Video": "Video track",
            "Audio": "Piste audio",
            "Text": "Sous-titres / Texte",
        }
        field_map = {
            "Video": self.VIDEO_FIELDS,
            "Audio": self.AUDIO_FIELDS,
            "Text": self.TEXT_FIELDS,
        }
        fields = field_map[track_type]

        box = QGroupBox(titles.get(track_type, track_type))
        form = QFormLayout(box)
        any_value = False

        for attr, label, formatter in fields:
            value = getattr(track, attr, None)
            if value not in (None, ""):
                display_value = formatter(value) if formatter else str(value)
                form.addRow(f"{label} :", QLabel(display_value))
                any_value = True

        if track_type == "Video":
            log_text = self._log_profile if self._log_profile else "Not detected"
            form.addRow("Profil LOG :", QLabel(log_text))
            any_value = True

        if any_value:
            self.results_layout.addWidget(box)
        else:
            box.deleteLater()

    def _add_camera_section(self, data):
        """Vue condensée et déduplicée : un seul champ par concept, retrouvé
        par mots-clés (robuste aux variations d'orthographe exacte des
        champs Sony). Les champs déjà affichés ailleurs (caméra, nombre
        d'images) sont exclus pour ne jamais les dupliquer."""
        filtered_data = {
            key: value for key, value in data.items()
            if not any(
                excl in key.lower()
                for excl in self._CAMERA_SECTION_EXCLUDED_SUBSTRINGS
            )
        }

        box = QGroupBox("Camera / Shoot Metadata")
        form = QFormLayout(box)
        any_value = False
        used_keys = set()

        for label, keywords in self.CAMERA_FIELD_GROUPS:
            for key, value in filtered_data.items():
                if key in used_keys:
                    continue
                if self._key_matches(key, keywords):
                    form.addRow(f"{label} :", QLabel(str(value)))
                    any_value = True
                    used_keys.add(key)
                    break  # un seul champ affiché par concept

        if any_value:
            self.results_layout.addWidget(box)
        else:
            box.deleteLater()

    def _find_camera_model(self, tracks):
        # 1) ExifTool en priorité (décode les MakerNotes de tous fabricants)
        if self._exif_camera:
            return self._exif_camera
        # 2) Repli sur MediaInfo (comportement d'origine)
        for keywords in CAMERA_MODEL_KEYWORD_GROUPS:
            for track in tracks:
                data = track.to_data()
                for key, value in data.items():
                    if value not in (None, "") and self._key_matches(key, keywords):
                        return str(value)
        return None

    def _detect_log_profile(self, tracks):
        # 1) ExifTool en priorité
        if self._exif_log:
            return self._exif_log
        # 2) Repli sur MediaInfo (comportement d'origine)
        for track in tracks:
            data = track.to_data()
            for value in data.values():
                if isinstance(value, str) and _LOG_PATTERN.search(value):
                    return value
        return None

    def _find_frame_count(self, tracks):
        """Retourne (valeur, est_calculé). Cherche d'abord un champ
        FrameCount déjà fourni par MediaInfo (Vidéo puis General) ; si
        absent, le calcule à partir de la durée et du frame rate."""
        for track_type in ("Video", "General"):
            for track in tracks:
                if track.track_type == track_type:
                    value = getattr(track, "frame_count", None)
                    if value not in (None, ""):
                        return str(value), False

        for track in tracks:
            if track.track_type == "Video":
                try:
                    duration = float(getattr(track, "duration", None))
                    frame_rate = float(getattr(track, "frame_rate", None))
                    computed = round(duration / 1000 * frame_rate)
                    return str(computed), True
                except (TypeError, ValueError):
                    continue
        return None, False

    def _merge_other_tracks_data(self, tracks):
        """Fusionne les pistes non standard (souvent les métadonnées caméra)
        en gardant la première valeur trouvée pour chaque champ, afin
        d'éliminer les doublons quand plusieurs pistes répètent les mêmes
        informations (cas fréquent sur certaines caméras)."""
        merged = {}
        for track in tracks:
            if track.track_type in ("General", "Video", "Audio", "Text"):
                continue
            data = track.to_data()
            for key, value in data.items():
                if key in self._SKIP_KEYS or value in (None, ""):
                    continue
                if key not in merged:
                    merged[key] = value
        return merged

    def _format_raw(self, media_info):
        lines = []
        for track in media_info.tracks:
            lines.append(f"--- {track.track_type} ---")
            data = track.to_data()
            for key, value in sorted(data.items()):
                if value not in (None, ""):
                    lines.append(f"{key}: {value}")
            lines.append("")
        return "\n".join(lines)

    def set_lang(self, lang):
        from core.lang import tr, LangManager
        LangManager.get().current = lang
        if hasattr(self, '_t_title'):  self._t_title.setText(tr("mi_title"))
        if hasattr(self, '_t_back'):   self._t_back.setText(tr("back"))

