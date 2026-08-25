"""
Résolution des chemins de ressources, compatible développement ET .exe PyInstaller.

En développement : les fichiers sont à côté du code.
Dans un .exe PyInstaller : les fichiers sont extraits dans un dossier temporaire
(sys._MEIPASS). Cette fonction gère les deux cas.
"""

import os
import sys


def resource_path(relative_path: str) -> str:
    """Retourne le chemin absolu vers une ressource (assets/, etc.),
    que l'app tourne en Python ou en .exe PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        # Mode .exe : PyInstaller extrait les fichiers ici
        base = sys._MEIPASS
    else:
        # Mode développement : racine du projet (dossier parent de core/)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def app_dir() -> str:
    """Dossier racine de l'application (où trouver assets/)."""
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_output_dir() -> str:
    """Dossier de sortie par défaut pour tous les modules : le dossier
    'Téléchargements' (Downloads) de l'utilisateur, sur Windows, macOS et Linux.

    Robuste en app packagée : sur Windows, os.path.expanduser('~') peut être
    peu fiable, donc on utilise en priorité les variables d'environnement du
    profil utilisateur, puis le registre pour le vrai dossier Downloads.
    """
    import os as _os

    # 1) Déterminer le dossier personnel de l'utilisateur de façon fiable
    home = None
    if _os.name == "nt":
        # USERPROFILE = C:\Users\<nom> (fiable même en app packagée)
        home = _os.environ.get("USERPROFILE")
        if not home:
            drive = _os.environ.get("HOMEDRIVE", "")
            path = _os.environ.get("HOMEPATH", "")
            if drive or path:
                home = drive + path
    if not home:
        home = _os.path.expanduser("~")

    # 2) Sur Windows, lire le vrai dossier Downloads dans le registre
    #    (l'utilisateur a pu le déplacer ailleurs).
    if _os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            # Étendre les variables comme %USERPROFILE%
            val = _os.path.expandvars(val)
            if val and _os.path.isdir(val):
                return val
        except Exception:
            pass

    # 3) Dossier Downloads standard
    downloads = _os.path.join(home, "Downloads")
    if _os.path.isdir(downloads):
        return downloads

    # 4) Dernier recours : le dossier personnel
    return home
