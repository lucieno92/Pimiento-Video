"""
Stockage persistant des préférences de l'application (via QSettings :
registre Windows, plist sur Mac, fichier ini sur Linux — géré automatiquement
par Qt, rien à coder côté fichiers).
"""

from PySide6.QtCore import QSettings

ORG_NAME = "PostProdSuiteProto"
APP_NAME = "PostProdSuite"


def _settings():
    return QSettings(ORG_NAME, APP_NAME)


def get_manual_ffmpeg_path():
    return _settings().value("ffmpeg/manual_path", "", type=str)


def set_manual_ffmpeg_path(path):
    _settings().setValue("ffmpeg/manual_path", path or "")
