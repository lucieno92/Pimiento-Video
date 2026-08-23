"""
Moteur de synchronisation multi-caméra.

Deux méthodes :
1. Timecode  : lit le TC embarqué dans les métadonnées (détection exhaustive
               de tous les champs connus selon le conteneur et la caméra).
2. Waveform  : cross-corrélation audio via numpy/FFmpeg (expérimental).
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from pymediainfo import MediaInfo
    HAS_PYMEDIAINFO = True
except ImportError:
    HAS_PYMEDIAINFO = False


@dataclass
class ClipInfo:
    path:             str
    name:             str
    track_label:      str   = "?"
    duration_frames:  int   = 0
    fps:              float = 25.0
    timecode_start:   str   = "00:00:00:00"
    offset_frames:    int   = 0
    is_video:         bool  = True


# ── Helpers TC ────────────────────────────────────────────────────────────────

_TC_RE = re.compile(r"^(\d{1,2})[:;](\d{2})[:;](\d{2})[:;](\d{2})$")

def _is_valid_tc(value: str) -> bool:
    """Vérifie qu'une valeur ressemble à un vrai timecode HH:MM:SS:FF."""
    if not value or not isinstance(value, str):
        return False
    m = _TC_RE.match(value.strip())
    if not m:
        return False
    h, mi, s, f = (int(x) for x in m.groups())
    # Rejeter 00:00:00:00 seulement si on cherche "mieux", mais on l'accepte
    # ici car c'est un TC valide (tournage commencé à minuit).
    return mi < 60 and s < 60 and f < 120

def _normalize_tc(tc: str) -> str:
    return _TC_RE.sub(lambda m: ":".join(m.groups()), tc.strip().replace(";", ":"))


def tc_to_frames(tc: str, fps: float) -> int:
    tc = tc.strip().replace(";", ":")
    parts = tc.split(":")
    if len(parts) != 4:
        return 0
    try:
        h, m, s, f = (int(p) for p in parts)
        nfps = max(round(fps), 1)
        return (h * 3600 + m * 60 + s) * nfps + f
    except (ValueError, TypeError):
        return 0


def frames_to_tc(frame_count: int, fps: float) -> str:
    nfps = max(round(fps), 1)
    total_s, f = divmod(max(int(frame_count), 0), nfps)
    h, rem  = divmod(total_s, 3600)
    m, s    = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


# Tous les noms d'attributs pymediainfo connus pour le timecode, triés par
# priorité (les plus fiables en premier). La liste est longue exprès :
# Sony MXF, Canon MOV/MP4, ARRI MXF, RED, Blackmagic, GoPro, etc. ont
# chacun leurs propres balises.
_TC_ATTRS = [
    # Champs standard pymediainfo
    "time_code_of_first_frame",
    "timecode",
    "time_code_source",
    "timecode_start",
    # Apple/QuickTime MOV
    "comapplequicktimetimecode",
    "comapplequicktimecreationdate",
    # Sony MXF / XDCAM
    "time_code",
    "startTimecode",
    "start_time_code",
    # Blackmagic BRAW / DaVinci
    "startTimeCode",
    "blackmagic_timecode",
    # GoPro
    "gopro_timecode",
    # Générique
    "recorded_date",
    "tagged_date",
    "mastered_date",
]


def _extract_tc_from_track(track) -> Optional[str]:
    """Cherche un TC valide dans une piste pymediainfo."""
    data = track.to_data() if hasattr(track, "to_data") else {}
    # 1. Essayer les attributs connus
    for attr in _TC_ATTRS:
        val = getattr(track, attr, None) or data.get(attr)
        if val and isinstance(val, str) and _is_valid_tc(val.strip()):
            return _normalize_tc(val.strip())
    # 2. Scan de tous les attributs de la piste (cas exotiques)
    for key, val in data.items():
        if not isinstance(val, str):
            continue
        if "time" in key.lower() or "tc" in key.lower() or "timecode" in key.lower():
            if _is_valid_tc(val.strip()):
                return _normalize_tc(val.strip())
    return None


def _fps_from_track(track, fps_default: float) -> float:
    """Extrait le frame rate depuis une piste pymediainfo."""
    for attr in ("frame_rate", "framerate", "r_frame_rate"):
        val = getattr(track, attr, None)
        if val:
            try:
                return float(str(val).split("/")[0]) / float(str(val).split("/")[1]) \
                    if "/" in str(val) else float(val)
            except (ValueError, ZeroDivisionError):
                pass
    return fps_default


def read_clip_info(path: str, track_label: str, fps_hint: float = 25.0) -> ClipInfo:
    """Lit les métadonnées d'un clip : durée, TC de départ, FPS réel."""
    name  = os.path.splitext(os.path.basename(path))[0]
    clip  = ClipInfo(path=path, name=name, track_label=track_label, fps=fps_hint)

    if not HAS_PYMEDIAINFO:
        return clip

    try:
        info = MediaInfo.parse(path)
    except Exception:
        return clip

    tc_found  = None
    fps_found = fps_hint

    for track in info.tracks:
        t = track.track_type

        # Durée & FPS depuis la piste vidéo ou générale
        if t in ("General", "Video"):
            dur = getattr(track, "duration", None)
            if dur not in (None, ""):
                try:
                    fps_for_dur = fps_found if fps_found > 0 else 25.0
                    clip.duration_frames = round(float(dur) / 1000 * fps_for_dur)
                except ValueError:
                    pass
            if t == "Video":
                fps_found = _fps_from_track(track, fps_found)

        # TC dans n'importe quelle piste (General, Video, Other, Menu...)
        if tc_found is None:
            tc_found = _extract_tc_from_track(track)

    clip.fps = fps_found
    if tc_found:
        clip.timecode_start = tc_found

    # Recalcul de la durée avec le bon fps maintenant qu'on le connaît
    if clip.duration_frames == 0 or fps_found != fps_hint:
        for track in info.tracks:
            if track.track_type in ("General", "Video"):
                dur = getattr(track, "duration", None)
                if dur not in (None, ""):
                    try:
                        clip.duration_frames = round(float(dur) / 1000 * fps_found)
                        break
                    except ValueError:
                        pass

    return clip


def compute_timecode_offsets(clips: list) -> list:
    if not clips:
        return clips
    starts = [tc_to_frames(c.timecode_start, c.fps) for c in clips]
    earliest = min(starts)
    for clip, start in zip(clips, starts):
        clip.offset_frames = start - earliest
    return clips


def extract_audio_mono(path: str, ffmpeg_exe: str,
                       sample_rate: int = 8000) -> Optional["np.ndarray"]:
    if not HAS_NUMPY:
        return None
    try:
        cmd = [
            ffmpeg_exe, "-i", path,
            "-ac", "1", "-ar", str(sample_rate),
            "-f", "f32le", "-loglevel", "quiet", "pipe:1",
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if not result.stdout:
            return None
        return np.frombuffer(result.stdout, dtype=np.float32).copy()
    except Exception:
        return None


def compute_waveform_offset_frames(ref: "np.ndarray", target: "np.ndarray",
                                   sample_rate: int, fps: float) -> int:
    if not HAS_NUMPY or ref is None or target is None:
        return 0
    if len(ref) == 0 or len(target) == 0:
        return 0
    ref    = ref    / (np.max(np.abs(ref))    + 1e-10)
    target = target / (np.max(np.abs(target)) + 1e-10)
    n = len(ref) + len(target) - 1
    np2 = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(
        np.fft.rfft(ref, n=np2) * np.conj(np.fft.rfft(target, n=np2)),
        n=np2
    )
    idx = int(np.argmax(corr))
    lag = idx if idx <= np2 // 2 else idx - np2
    return round(lag / sample_rate * fps)
