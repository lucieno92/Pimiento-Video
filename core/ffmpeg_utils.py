"""
Détection de FFmpeg, partagée par tous les modules de l'application.

Ordre de priorité :
1. FFmpeg embarqué automatiquement via le paquet 'imageio-ffmpeg'
   (cas normal : l'utilisateur final n'a rien à installer)
2. Un chemin indiqué manuellement (paramètres avancés, pour dépannage)
3. Un dossier 'ffmpeg/bin' placé à côté de l'application
4. FFmpeg déjà présent dans le PATH système
"""

import os
import shutil

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


def _project_root():
    # core/ se trouve juste sous la racine du projet (là où se trouve main.py)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_bundled_ffmpeg_path():
    """FFmpeg embarqué via imageio-ffmpeg. Retourne None si le paquet est absent."""
    if imageio_ffmpeg is None:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _ffmpeg_exe_name():
    """Nom de l'exécutable ffmpeg selon le système."""
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def find_ffmpeg_bin_dir():
    """Cherche un dossier ffmpeg/bin à côté de l'app, ou dans les emplacements
    habituels du système. Utilisé seulement si le ffmpeg embarqué est
    indisponible. Fonctionne sur Windows comme sur macOS/Linux."""
    project_dir = _project_root()
    exe = _ffmpeg_exe_name()

    candidate = os.path.join(project_dir, "ffmpeg", "bin")
    if os.path.isfile(os.path.join(candidate, exe)):
        return candidate

    candidate_flat = os.path.join(project_dir, "ffmpeg")
    if os.path.isfile(os.path.join(candidate_flat, exe)):
        return candidate_flat

    if os.name == "nt":
        common_paths = [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
        ]
    else:
        # macOS (Homebrew Intel + Apple Silicon) et Linux
        common_paths = [
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/usr/bin",
        ]

    for path in common_paths:
        if os.path.isfile(os.path.join(path, exe)):
            return path

    return None


def is_ffmpeg_on_system_path():
    return shutil.which("ffmpeg") is not None


def _assets_ffmpeg_dir():
    """Dossier assets/ffmpeg/ embarqué dans l'app, s'il contient ffmpeg.
    Ce dossier a l'avantage de contenir aussi ffprobe (côte à côte),
    ce que imageio-ffmpeg ne fournit pas.
    Utilise app_dir() pour fonctionner aussi en mode packagé (sys._MEIPASS)."""
    try:
        from core.paths import app_dir
        base = app_dir()
    except Exception:
        base = _project_root()
    exe = _ffmpeg_exe_name()
    cand = os.path.join(base, "assets", "ffmpeg")
    if os.path.isfile(os.path.join(cand, exe)):
        return cand
    return None


def resolve_ffmpeg_location(manual_path=None):
    """Retourne le chemin à transmettre à yt-dlp / aux post-traitements,
    selon l'ordre de priorité décrit en haut de ce fichier.
    Retourne None si rien n'est trouvé (on retombera alors sur le PATH système)."""
    # 1) assets/ffmpeg/ en priorite : contient ffmpeg ET ffprobe ensemble
    assets_dir = _assets_ffmpeg_dir()
    if assets_dir:
        return assets_dir
    # 2) ffmpeg embarque via imageio-ffmpeg (ffmpeg seul, sans ffprobe)
    bundled = get_bundled_ffmpeg_path()
    if bundled:
        return bundled
    if manual_path and os.path.isdir(manual_path):
        return manual_path
    return find_ffmpeg_bin_dir()


def get_ffmpeg_executable_path(manual_path=None):
    """Retourne le chemin complet vers l'exécutable ffmpeg lui-même (et non
    juste son dossier), pour les modules qui appellent ffmpeg directement
    en ligne de commande (ex: l'encodeur), via subprocess."""
    location = resolve_ffmpeg_location(manual_path)
    if not location:
        return "ffmpeg"  # dernier recours : on espère qu'il est dans le PATH
    if os.path.isfile(location):
        return location
    if os.path.isdir(location):
        exe_name = _ffmpeg_exe_name()
        candidate = os.path.join(location, exe_name)
        if os.path.isfile(candidate):
            return candidate
    return "ffmpeg"
