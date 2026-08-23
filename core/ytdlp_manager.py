"""
Gestion du binaire yt-dlp externe, auto-mis à jour.

Pourquoi ce module :
YouTube (et les autres sites) changent souvent leur code, ce qui casse les
anciennes versions de yt-dlp. Si yt-dlp est figé dans l'app packagée, les
utilisateurs devraient réinstaller l'app à chaque fois — ingérable.

Solution : l'app utilise le BINAIRE OFFICIEL yt-dlp, stocké dans un dossier
utilisateur (hors de l'app). Ce binaire :
  - est téléchargé au premier besoin depuis GitHub,
  - se met à jour tout seul (petites mises à jour régulières),
sans jamais toucher à l'app elle-même. Les utilisateurs ne réinstallent rien.

Le binaire officiel est dans le domaine public (Unlicense) : usage commercial
autorisé.
"""

import os
import sys
import stat
import time
import json
import urllib.request

# ── Emplacement du binaire dans le dossier utilisateur ────────────────────────

def _user_data_dir() -> str:
    """Dossier où stocker le binaire yt-dlp, propre à chaque OS."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/PimientoVideo")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                            "PimientoVideo")
    else:
        base = os.path.expanduser("~/.local/share/PimientoVideo")
    os.makedirs(base, exist_ok=True)
    return base


def _binary_name() -> str:
    """Nom du binaire yt-dlp selon la plateforme."""
    if os.name == "nt":
        return "yt-dlp.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux"


def _download_url() -> str:
    """URL du binaire officiel le plus récent (redirige vers la dernière
    version stable publiée sur GitHub)."""
    return ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
            + _binary_name())


def binary_path() -> str:
    """Chemin complet du binaire yt-dlp dans le dossier utilisateur."""
    return os.path.join(_user_data_dir(), _binary_name())


# ── Téléchargement / mise à jour ──────────────────────────────────────────────

# Fichier marqueur pour ne pas vérifier la mise à jour à CHAQUE téléchargement
# (une fois par 24 h suffit largement).
_STAMP_NAME = ".ytdlp_last_check"


def _last_check_time() -> float:
    stamp = os.path.join(_user_data_dir(), _STAMP_NAME)
    try:
        return os.path.getmtime(stamp)
    except OSError:
        return 0.0


def _touch_stamp():
    stamp = os.path.join(_user_data_dir(), _STAMP_NAME)
    try:
        with open(stamp, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _download_binary(dest: str, log=None) -> bool:
    """Télécharge le binaire officiel vers dest. Retourne True si réussi."""
    url = _download_url()
    if log:
        log("Downloading the latest yt-dlp engine (first time only)…")
    try:
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers={"User-Agent": "PimientoVideo"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(tmp, dest)
        # Rendre exécutable (Mac/Linux)
        if os.name != "nt":
            st = os.stat(dest)
            os.chmod(dest, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        if log:
            log("yt-dlp engine ready.")
        return True
    except Exception as e:
        if log:
            log(f"Could not download yt-dlp engine: {e}")
        try:
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
        except OSError:
            pass
        return False


def ensure_ytdlp(log=None, force_check=False) -> str | None:
    """S'assure qu'un binaire yt-dlp à jour est disponible, et renvoie son
    chemin (ou None si indisponible).

    - S'il n'existe pas : le télécharge.
    - S'il existe : le met à jour au plus une fois par 24 h (sauf force_check),
      via la commande native `-U` du binaire (rapide, incrémentale).
    Ne bloque jamais le téléchargement : en cas d'échec réseau, on renvoie le
    binaire existant s'il y en a un.
    """
    path = binary_path()

    # 1) Pas encore présent → télécharger
    if not os.path.exists(path):
        if _download_binary(path, log):
            _touch_stamp()
            return path
        return None  # échec et rien en place

    # 2) Présent → mise à jour throttlée (1×/24 h)
    day = 24 * 3600
    if force_check or (time.time() - _last_check_time() > day):
        _self_update(path, log)
        _touch_stamp()

    return path


def _self_update(path: str, log=None):
    """Met à jour le binaire via sa commande native `-U`. Silencieux et non
    bloquant : toute erreur est ignorée (on garde la version en place)."""
    import subprocess
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW : pas de fenêtre noire
        subprocess.run(
            [path, "-U"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            creationflags=creationflags,
        )
        if log:
            log("yt-dlp engine checked for updates.")
    except Exception:
        pass  # pas de réseau, pas de droits : on garde la version actuelle
