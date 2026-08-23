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
    'Téléchargements' de l'utilisateur (Downloads), aussi bien sur Windows
    que sur macOS et Linux. Si Downloads n'existe pas, on retombe sur le
    dossier personnel."""
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    if os.path.isdir(downloads):
        return downloads
    return home
