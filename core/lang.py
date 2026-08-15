"""
Système i18n complet pour Pimiento Video.

Classes auto-traductibles : TLabel, TButton, TGroupBox, TCheckBox.
Usage : TLabel("key") → se traduit automatiquement quand la langue change.
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QGroupBox, QCheckBox

# ─── Dictionnaire complet ─────────────────────────────────────────────────────
T = {
    # Commun
    "back":             {"fr": "← Accueil",         "en": "← Home"},
    "browse":           {"fr": "Parcourir...",       "en": "Browse..."},
    "export":           {"fr": "Exporter",           "en": "Export"},
    "cancel":           {"fr": "Annuler",            "en": "Cancel"},
    "stop":             {"fr": "Arrêter",            "en": "Stop"},
    "save":             {"fr": "Enregistrer",        "en": "Save"},
    "no_file":          {"fr": "Aucun fichier chargé.", "en": "No file loaded."},
    "drop_file":        {"fr": "Glisse un fichier ici", "en": "Drop a file here"},
    "journal":          {"fr": "Journal :",          "en": "Log:"},
    "output_folder":    {"fr": "Dossier de sortie :", "en": "Output folder:"},
    "format":           {"fr": "Format :",           "en": "Format:"},
    "language":         {"fr": "Langue :",           "en": "Language:"},
    "model":            {"fr": "Modèle :",           "en": "Model:"},
    "options":          {"fr": "Options de sortie",  "en": "Output options"},
    "settings":         {"fr": "Paramètres",         "en": "Settings"},
    "start":            {"fr": "Démarrer",           "en": "Start"},
    "done":             {"fr": "Terminé",            "en": "Done"},
    "error":            {"fr": "Erreur",             "en": "Error"},
    "preview":          {"fr": "Aperçu :",           "en": "Preview:"},
    "transcript_lbl":   {"fr": "Transcript :",       "en": "Transcript:"},
    "add_files":        {"fr": "Ajouter des fichiers...", "en": "Add files..."},
    "remove_sel":       {"fr": "Retirer la sélection", "en": "Remove selected"},
    "clear_queue":      {"fr": "Vider la file",      "en": "Clear queue"},
    "create_folder":    {"fr": "Créer un dossier par vidéo", "en": "One folder per video"},
    "delete_source":    {"fr": "⚠ Supprimer les fichiers sources après encodage",
                         "en": "⚠ Delete source files after encoding"},
    "prefix":           {"fr": "Préfixe :",          "en": "Prefix:"},
    "suffix":           {"fr": "Suffixe :",          "en": "Suffix:"},
    "dpi":              {"fr": "Résolution (DPI) :", "en": "Resolution (DPI):"},
    "pages_label":      {"fr": "Pages (ex: 1-3,5  ou vide = toutes) :",
                         "en": "Pages (e.g. 1-3,5  or empty = all):"},
    "intensity":        {"fr": "Intensité :",        "en": "Intensity:"},
    "words_per_sub":    {"fr": "Mots par sous-titre :", "en": "Words per subtitle:"},
    "lines_per_sub":    {"fr": "Lignes par sous-titre :", "en": "Lines per subtitle:"},
    "min_dur":          {"fr": "Durée minimum (s) :", "en": "Min. duration (s):"},
    "min_gap":          {"fr": "Espacement minimum (s) :", "en": "Min. gap (s):"},
    "max_cps":          {"fr": "Vitesse lecture max (car/s) :", "en": "Max reading speed (char/s):"},
    "zoom":             {"fr": "Zoom :",             "en": "Zoom:"},
    "sequence":         {"fr": "Séquence :",         "en": "Sequence:"},
    "timecodes":        {"fr": "Timecodes",          "en": "Timecodes"},
    "translate_to":     {"fr": "Vers :",             "en": "To:"},
    "translate_btn":    {"fr": "Traduire",           "en": "Translate"},
    "subtitle_params":  {"fr": "Paramètres des sous-titres", "en": "Subtitle parameters"},
    "rename_section":   {"fr": "Renommage / organisation", "en": "Rename / organise"},
    "export_group":     {"fr": "Export",             "en": "Export"},
    "sync_group":       {"fr": "Synchronisation",   "en": "Synchronisation"},
    "method":           {"fr": "Méthode :",          "en": "Method:"},
    "ref_track":        {"fr": "Piste de référence :", "en": "Reference track:"},
    "loaded_items":     {"fr": "Éléments chargés :", "en": "Loaded items:"},
    "folders_loaded":   {"fr": "Dossiers chargés :", "en": "Loaded folders:"},
    "clear_all":        {"fr": "Tout effacer",       "en": "Clear all"},
    "doc_title":        {"fr": "Titre du document :", "en": "Document title:"},

    # Home
    "home_subtitle":    {"fr": "Sélectionnez un module pour commencer",
                         "en": "Select a module to get started"},
    "home_section":     {"fr": "MODULES",            "en": "MODULES"},

    # Downloader
    "dl_title":         {"fr": "Téléchargeur vidéo", "en": "Video Downloader"},
    "dl_url":           {"fr": "URL de la vidéo :",  "en": "Video URL:"},
    "dl_paste":         {"fr": "Coller l'URL ici...", "en": "Paste URL here..."},
    "dl_quality":       {"fr": "Qualité :",          "en": "Quality:"},
    "dl_btn":           {"fr": "Télécharger",        "en": "Download"},
    "dl_playlist":      {"fr": "Télécharger la playlist complète",
                         "en": "Download full playlist"},
    "dl_drop":          {"fr": "Glisse une URL ou colle-la ci-dessous",
                         "en": "Drop a URL or paste below"},

    # Media Info
    "mi_title":         {"fr": "Métadonnées",        "en": "Media Info"},
    "mi_drop":          {"fr": "Glisse un fichier vidéo ou audio ici",
                         "en": "Drop a video or audio file here"},
    "mi_raw":           {"fr": "Métadonnées brutes", "en": "Raw metadata"},
    "mi_show_raw":      {"fr": "Afficher les métadonnées brutes",
                         "en": "Show raw metadata"},

    # Encoder
    "enc_title":        {"fr": "Encodeur",           "en": "Encoder"},
    "enc_drop":         {"fr": "Glisse une ou plusieurs vidéos/photos ici",
                         "en": "Drop one or more videos/photos here"},
    "enc_category":     {"fr": "Catégorie :",        "en": "Category:"},
    "enc_format":       {"fr": "Codec :",            "en": "Codec:"},
    "enc_container":    {"fr": "Conteneur :",        "en": "Container:"},
    "enc_resolution":   {"fr": "Résolution :",       "en": "Resolution:"},
    "enc_advanced":     {"fr": "Paramètres avancés", "en": "Advanced parameters"},
    "enc_framerate":    {"fr": "Frame rate :",       "en": "Frame rate:"},
    "enc_btn":          {"fr": "Encoder",            "en": "Encode"},

    # Transcription
    "tr_title":         {"fr": "Transcription",      "en": "Transcript"},
    "tr_drop":          {"fr": "Glisse un fichier audio ou vidéo ici",
                         "en": "Drop an audio or video file here"},
    "tr_btn":           {"fr": "Transcrire",         "en": "Transcribe"},
    "tr_translate":     {"fr": "Traduction",         "en": "Translation"},
    "tr_options":       {"fr": "Options de transcription", "en": "Transcription options"},

    # Cue Sheet
    "cs_title":         {"fr": "Droits musicaux (Cue Sheet)", "en": "Cue Sheet"},
    "cs_drop":          {"fr": "Glisse un fichier EDL ici\n(Avid / Premiere Pro / DaVinci Resolve / Final Cut Pro — format CMX3600)",
                         "en": "Drop an EDL file here\n(Avid / Premiere Pro / DaVinci Resolve / Final Cut Pro — CMX3600)"},
    "cs_fps":           {"fr": "Frame rate de la séquence :", "en": "Sequence frame rate:"},
    "cs_tracks":        {"fr": "Pistes audio détectées — coche celles qui contiennent de la musique",
                         "en": "Detected audio tracks — check those containing music"},
    "cs_generate":      {"fr": "Générer le tableau", "en": "Generate table"},
    "cs_export_pdf":    {"fr": "Exporter en PDF",    "en": "Export PDF"},
    "cs_export_word":   {"fr": "Exporter en Word",   "en": "Export Word"},
    "cs_export_txt":    {"fr": "Exporter en TXT",    "en": "Export TXT"},

    # Multicam
    "mc_title":         {"fr": "Synchronisation multi-caméra", "en": "Multicam Sync"},
    "mc_drop":          {"fr": "Glisse ici tous les dossiers de cartes\n(vidéo + audio — tous ensemble d'un coup)",
                         "en": "Drop all card folders here\n(video + audio — all at once)"},
    "mc_add_folder":    {"fr": "Ajouter un dossier...", "en": "Add folder..."},
    "mc_scan":          {"fr": "⬡ Scanner",          "en": "⬡ Scan"},
    "mc_sync_btn":      {"fr": "▶ Synchroniser",     "en": "▶ Synchronise"},
    "mc_timeline":      {"fr": "Timeline (aperçu) :", "en": "Timeline (preview):"},
    "mc_export_xml":    {"fr": "XML  (Premiere / Resolve / FCP)",
                         "en": "XML  (Premiere / Resolve / FCP)"},
    "mc_export_aaf":    {"fr": "AAF  (Avid Media Composer)",
                         "en": "AAF  (Avid Media Composer)"},
    "mc_method_tc":     {"fr": "Timecode (TC embarqué)", "en": "Timecode (embedded TC)"},
    "mc_method_wf":     {"fr": "Forme d'onde — Waveform (expérimental)",
                         "en": "Waveform (experimental)"},
    "mc_add_files":     {"fr": "+ Fichiers",         "en": "+ Files"},

    # PDF
    "pdf_title":        {"fr": "Outils PDF",         "en": "PDF Tools"},
    "pdf_merge_tab":    {"fr": "📎 Assembler",        "en": "📎 Merge"},
    "pdf_split_tab":    {"fr": "✂ Diviser",          "en": "✂ Split"},
    "pdf_img_tab":      {"fr": "🖼 Extraire images",  "en": "🖼 Extract images"},
    "pdf_word_tab":     {"fr": "📝 → Word",           "en": "📝 → Word"},
    "pdf_excel_tab":    {"fr": "📊 → Excel",          "en": "📊 → Excel"},
    "pdf_jpeg_tab":     {"fr": "🖼 → JPEG",           "en": "🖼 → JPEG"},
    "pdf_compress_tab": {"fr": "🗜 Compresser",       "en": "🗜 Compress"},
    "pdf_doc_tab":      {"fr": "📄 Doc → PDF",        "en": "📄 Doc → PDF"},
    "pdf_merge_btn":    {"fr": "Assembler en un seul PDF", "en": "Merge into one PDF"},
    "pdf_split_btn":    {"fr": "Diviser",            "en": "Split"},
    "pdf_extract_btn":  {"fr": "Extraire les images", "en": "Extract images"},
    "pdf_word_btn":     {"fr": "Convertir en Word (.docx)", "en": "Convert to Word (.docx)"},
    "pdf_excel_btn":    {"fr": "Convertir en Excel (.xlsx)", "en": "Convert to Excel (.xlsx)"},
    "pdf_jpeg_btn":     {"fr": "Convertir en JPEG (une image par page)",
                         "en": "Convert to JPEG (one image per page)"},
    "pdf_compress_btn": {"fr": "Compresser",         "en": "Compress"},
    "pdf_doctopdf_btn": {"fr": "Convertir en PDF",   "en": "Convert to PDF"},

    # Audio Cleaner
    "ac_title":         {"fr": "Nettoyage audio",    "en": "Audio Cleaner"},
    "ac_drop":          {"fr": "Glisse un fichier audio ou vidéo ici\n(MP3, WAV, FLAC, MP4, MOV...)",
                         "en": "Drop an audio or video file here\n(MP3, WAV, FLAC, MP4, MOV...)"},
    "ac_denoise_tab":   {"fr": "🎤 Réduction de bruit", "en": "🎤 Noise Reduction"},
    "ac_separate_tab":  {"fr": "🎵 Séparation voix / musique", "en": "🎵 Vocals / Music"},
    "ac_denoise_btn":   {"fr": "Réduire le bruit",   "en": "Reduce noise"},
    "ac_separate_btn":  {"fr": "Séparer voix / instruments", "en": "Separate vocals / music"},
    "ac_denoise_info":  {"fr": "Supprime le bruit de fond constant (souffle, ventilation, salle).\nLes 0,5 premières secondes servent de profil de référence.",
                         "en": "Removes constant background noise (hiss, fan, room).\nThe first 0.5 s of the file are used as the noise profile."},
    "ac_separate_info": {"fr": "Sépare la voix du fond musical en 2 fichiers.\nMoteur : demucs htdemucs (Meta, MIT license).",
                         "en": "Separates vocals from music into 2 files.\nEngine: demucs htdemucs (Meta, MIT license)."},

    # Settings
    "st_title":         {"fr": "Paramètres avancés", "en": "Advanced Settings"},
    "st_ffmpeg_group":  {"fr": "Chemin FFmpeg manuel (dépannage uniquement)",
                         "en": "Manual FFmpeg path (troubleshooting only)"},
    "st_ffmpeg_label":  {"fr": "Chemin :",           "en": "Path:"},
    "st_save":          {"fr": "Enregistrer",        "en": "Save"},
    "st_note":          {"fr": "Dans l'immense majorité des cas, FFmpeg est détecté automatiquement.",
                         "en": "In most cases, FFmpeg is detected automatically."},
}

# ─── Gestionnaire de langue ───────────────────────────────────────────────────

class LangManager(QObject):
    lang_changed = Signal(str)
    _instance = None

    def __init__(self):
        super().__init__()
        self.current = "en"

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set(self, lang: str):
        if lang != self.current:
            self.current = lang
            self.lang_changed.emit(lang)

    def t(self, key: str) -> str:
        entry = T.get(key)
        if entry is None:
            return key
        return entry.get(self.current, entry.get("fr", key))


def tr(key: str) -> str:
    return LangManager.get().t(key)


# ─── Widgets auto-traductibles ────────────────────────────────────────────────

class TLabel(QLabel):
    """QLabel dont le texte se traduit automatiquement."""
    def __init__(self, key: str, *args, **kwargs):
        super().__init__(tr(key), *args, **kwargs)
        self._key = key
        LangManager.get().lang_changed.connect(
            lambda lang: self.setText(tr(self._key)))


class TButton(QPushButton):
    """QPushButton dont le texte se traduit automatiquement."""
    def __init__(self, key: str, *args, **kwargs):
        super().__init__(tr(key), *args, **kwargs)
        self._key = key
        LangManager.get().lang_changed.connect(
            lambda lang: self.setText(tr(self._key)))


class TGroupBox(QGroupBox):
    """QGroupBox dont le titre se traduit automatiquement."""
    def __init__(self, key: str, *args, **kwargs):
        super().__init__(tr(key), *args, **kwargs)
        self._key = key
        LangManager.get().lang_changed.connect(
            lambda lang: self.setTitle(tr(self._key)))


class TCheckBox(QCheckBox):
    """QCheckBox dont le texte se traduit automatiquement."""
    def __init__(self, key: str, *args, **kwargs):
        super().__init__(tr(key), *args, **kwargs)
        self._key = key
        LangManager.get().lang_changed.connect(
            lambda lang: self.setText(tr(self._key)))
