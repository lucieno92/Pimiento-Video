"""
Lecture des métadonnées via ExifTool (modèle caméra + profil LOG).

ExifTool décode les MakerNotes propriétaires de quasiment tous les fabricants
(Sony, Canon, Panasonic, Fujifilm, Nikon, Blackmagic, DJI, GoPro...) là où
MediaInfo est limité. L'exécutable est embarqué dans assets/exiftool/.

Détection "intelligente" : au lieu de chercher une liste fixe de noms de
champs, on scanne TOUS les champs retournés et on repère automatiquement
ceux qui ressemblent à un modèle de caméra ou à un profil log/gamma.
"""

import os
import sys
import json
import re
import subprocess

from core.paths import app_dir


def get_exiftool_path():
    """Chemin de l'exécutable exiftool embarqué, ou 'exiftool' système.

    Robuste : scanne le dossier assets/exiftool/ et prend le premier fichier
    exécutable dont le nom commence par 'exiftool', quel que soit son
    extension exacte (exiftool, exiftool.exe, exiftool.exe.exe...).
    """
    base = app_dir()
    exif_dir = os.path.join(base, "assets", "exiftool")

    # 1) Scanner le dossier assets/exiftool/ pour trouver l'exécutable
    if os.path.isdir(exif_dir):
        entries = []
        try:
            entries = os.listdir(exif_dir)
        except Exception:
            entries = []
        # Chercher un FICHIER (pas dossier) dont le nom commence par exiftool
        for name in entries:
            full = os.path.join(exif_dir, name)
            if not os.path.isfile(full):
                continue
            low = name.lower()
            if low.startswith("exiftool"):
                # Sur Windows on veut un .exe ; sinon on prend tel quel
                if sys.platform == "win32":
                    if low.endswith(".exe"):
                        return full
                else:
                    return full
        # Sur Windows, si rien en .exe mais un fichier "exiftool" nu, le prendre
        if sys.platform == "win32":
            for name in entries:
                full = os.path.join(exif_dir, name)
                if os.path.isfile(full) and name.lower().startswith("exiftool"):
                    return full

    # 2) Candidats classiques directement dans assets/
    extra = [
        os.path.join(base, "assets", "exiftool.exe"),
        os.path.join(base, "assets", "exiftool"),
    ]
    for c in extra:
        if os.path.isfile(c):
            return c

    # 3) Repli : exiftool dans le PATH système
    return "exiftool"


def _win_kwargs():
    """Arguments subprocess spécifiques Windows pour fonctionner depuis une
    application GUI (sans console). stdin=DEVNULL est CRUCIAL : sans console,
    exiftool peut se bloquer ou échouer en attendant une entrée standard."""
    kw = {}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    kw["stdin"] = subprocess.DEVNULL
    return kw


def _run_exiftool(path, _debug=None):
    """Lance exiftool en JSON. Retourne un dict {champ: valeur} ou None.
    Si _debug est une liste, y ajoute des infos de diagnostic."""
    exe = get_exiftool_path()
    try:
        result = subprocess.run(
            [exe, "-j", "-a", "-s", path],
            capture_output=True, text=True, timeout=30,
            **_win_kwargs(),
        )
        if _debug is not None:
            _debug.append(f"rc={result.returncode}")
            if result.stderr:
                _debug.append(f"stderr={result.stderr[:120]}")
        if not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
        if isinstance(data, list) and data:
            return data[0]
    except Exception as e:
        if _debug is not None:
            _debug.append(f"exc={type(e).__name__}:{e}")
        return None
    return None


# Motif de détection d'un profil log/gamma dans une valeur texte
_LOG_RE = re.compile(
    r"(s-?log\d?|v-?log\d?|c-?log\d?|log-?c\d?|n-?log|d-?log|"
    r"f-?log\d?|redlogfilm|arri\s*log|hlg|rec\.?\s*2100|"
    r"z-?log|j-?log|cine-?ei|s-?gamut|v-?gamut|bt\.?2020|"
    r"pq\b|hybrid\s*log)",
    re.IGNORECASE,
)

# Mots-clés indiquant qu'un CHAMP concerne le gamma/profil (même si la valeur
# ne matche pas le motif log — ex: "Gamma: HLG", "Picture Profile: PP8")
_GAMMA_FIELD_HINTS = [
    "gamma", "captgamma", "picture profile", "pictureprofile",
    "log", "gammacapture", "capturegamma", "transfercharacteristics",
    "colorprofile", "tonecurve",
]

# Mots-clés pour repérer un champ "modèle de caméra"
_MODEL_FIELD_HINTS = ["model", "cameramodelname", "camera model"]
_MAKE_FIELD_HINTS = ["make", "manufacturer", "cameramanufacturer"]

# Valeurs à ignorer (trop génériques ou non pertinentes)
_MODEL_IGNORE = {"", "unknown", "n/a", "digital camera", "camera"}


def read_camera_and_log(path):
    """Retourne (camera_model, log_profile). Chaque valeur peut être None.
    Ne lève jamais d'exception."""
    data = _run_exiftool(path)
    if not data:
        return None, None

    # ══ MODÈLE DE CAMÉRA ══
    make = None
    model = None
    for key, val in data.items():
        if val is None or str(val).strip() == "":
            continue
        v = str(val).strip()
        kl = key.lower()
        # Modèle : champ contenant "model" (mais pas "lensmodel")
        if model is None and any(h in kl for h in _MODEL_FIELD_HINTS):
            if "lens" not in kl and v.lower() not in _MODEL_IGNORE:
                model = v
        # Marque : champ contenant "make"/"manufacturer"
        if make is None and any(h in kl for h in _MAKE_FIELD_HINTS):
            if "lens" not in kl and v.lower() not in _MODEL_IGNORE:
                make = v

    camera = None
    if model and make and make.lower() not in model.lower():
        camera = f"{make} {model}"
    elif model:
        camera = model
    elif make:
        camera = make

    # ══ PROFIL LOG / GAMMA ══
    log_profile = None

    # Priorité 1 : un champ dont le NOM évoque le gamma/profil ET dont la
    # valeur ressemble à un log → le plus fiable
    for key, val in data.items():
        if val is None:
            continue
        v = str(val).strip()
        if not v:
            continue
        kl = key.lower()
        if any(h in kl for h in _GAMMA_FIELD_HINTS):
            if _LOG_RE.search(v):
                log_profile = v
                break

    # Priorité 2 : un champ "gamma/profil" avec une valeur courte et parlante
    # (ex: Picture Profile = "PP8", Gamma = "HLG2") même sans match strict
    if not log_profile:
        for key, val in data.items():
            if val is None:
                continue
            v = str(val).strip()
            if not v or v.lower() in ("off", "none", "standard", "0", "auto"):
                continue
            kl = key.lower()
            if any(h in kl for h in _GAMMA_FIELD_HINTS) and len(v) < 40:
                log_profile = v
                break

    # Priorité 3 : n'importe quelle valeur texte qui matche le motif log
    if not log_profile:
        for key, val in data.items():
            if isinstance(val, str) and _LOG_RE.search(val) and len(val) < 60:
                log_profile = val.strip()
                break

    return camera, log_profile


def dump_all_fields(path):
    """Debug : retourne le dict complet des champs ExifTool (ou {})."""
    data = _run_exiftool(path)
    return data or {}


def is_available(_debug=None):
    exe = get_exiftool_path()
    try:
        result = subprocess.run(
            [exe, "-ver"], capture_output=True, text=True, timeout=10,
            **_win_kwargs(),
        )
        if _debug is not None:
            _debug.append(f"ver_rc={result.returncode}")
            _debug.append(f"ver_out={result.stdout.strip()[:20]}")
            if result.stderr:
                _debug.append(f"ver_err={result.stderr[:120]}")
        return result.returncode == 0
    except Exception as e:
        if _debug is not None:
            _debug.append(f"ver_exc={type(e).__name__}:{e}")
        return False