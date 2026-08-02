"""
Gestion des sons de l'application.

Utilise QSoundEffect avec des références persistantes pour éviter que
les objets soient garbage-collectés avant la fin de la lecture.
Fallback sur QMediaPlayer si QSoundEffect échoue.
"""

import os
from PySide6.QtCore import QUrl

from core.paths import app_dir as _app_dir
_SOUNDS_DIR = os.path.join(_app_dir(), "assets", "sounds")

_enabled = True
_players = []   # références persistantes (évite le garbage collection)


def set_enabled(enabled: bool):
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    return _enabled


def _play_file(filename: str):
    """Joue un fichier son. Essaie QSoundEffect, puis QMediaPlayer en secours."""
    if not _enabled:
        return
    path = os.path.join(_SOUNDS_DIR, filename)
    if not os.path.exists(path):
        return

    url = QUrl.fromLocalFile(path)

    # ── Méthode 1 : QSoundEffect (idéal pour les sons courts) ──
    try:
        from PySide6.QtMultimedia import QSoundEffect
        effect = QSoundEffect()
        effect.setSource(url)
        effect.setVolume(0.6)
        effect.play()
        _players.append(effect)
        # Limiter la taille du cache de références
        if len(_players) > 10:
            _players.pop(0)
        return
    except Exception:
        pass

    # ── Méthode 2 : QMediaPlayer (secours) ──
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        player = QMediaPlayer()
        audio_out = QAudioOutput()
        audio_out.setVolume(0.6)
        player.setAudioOutput(audio_out)
        player.setSource(url)
        player.play()
        _players.append(player)
        _players.append(audio_out)   # garder aussi la sortie audio
        if len(_players) > 20:
            _players.pop(0)
            _players.pop(0)
    except Exception:
        pass


def play_done():
    """Son de validation (action terminée avec succès)."""
    _play_file("done.wav")


def play_error():
    """Son d'erreur (action échouée)."""
    _play_file("false.wav")


def play(name: str):
    _play_file(name)
