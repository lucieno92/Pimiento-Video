"""
Lecture des métadonnées d'un fichier média via ffprobe/ffmpeg.

Sert de source d'information quand 'pymediainfo' n'est pas disponible
(typiquement sur macOS, où la bibliothèque système libmediainfo n'est
pas embarquée dans l'application).

ffprobe est fourni avec FFmpeg. S'il n'est pas trouvé, on se rabat sur
'ffmpeg -i' dont la sortie texte contient les mêmes informations
essentielles.
"""

import os
import re
import json
import subprocess

from core.ffmpeg_utils import get_ffmpeg_executable_path, _ffmpeg_exe_name


def _ffprobe_path():
    """Cherche ffprobe à côté de ffmpeg (même dossier)."""
    ffmpeg = get_ffmpeg_executable_path()
    if ffmpeg and os.path.isfile(ffmpeg):
        d = os.path.dirname(ffmpeg)
        name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        cand = os.path.join(d, name)
        if os.path.isfile(cand):
            return cand
    # Repli : ffprobe dans le PATH système
    return "ffprobe"


def _subprocess_kwargs():
    """Empêche une fenêtre console d'apparaître sous Windows."""
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


def is_available():
    """Vrai si ffprobe OU ffmpeg est utilisable pour lire des métadonnées."""
    for exe in (_ffprobe_path(), get_ffmpeg_executable_path()):
        try:
            subprocess.run([exe, "-version"], **_subprocess_kwargs())
            return True
        except Exception:
            continue
    return False


def read_metadata(path):
    """
    Retourne un dictionnaire de métadonnées structuré :
      {
        "general": {...},
        "video":   [ {...}, ... ],
        "audio":   [ {...}, ... ],
        "text":    [ {...}, ... ],
      }
    Retourne None si l'analyse échoue complètement.
    """
    data = _read_with_ffprobe(path)
    if data is not None:
        return data
    # Repli sur 'ffmpeg -i' si ffprobe indisponible
    return _read_with_ffmpeg(path)


# ----------------------------------------------------------------------
#  Méthode 1 : ffprobe en JSON (précise et structurée)
# ----------------------------------------------------------------------
def _read_with_ffprobe(path):
    exe = _ffprobe_path()
    cmd = [
        exe, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path,
    ]
    try:
        proc = subprocess.run(cmd, **_subprocess_kwargs())
        if proc.returncode != 0:
            return None
        raw = proc.stdout.decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except Exception:
        return None

    result = {"general": {}, "video": [], "audio": [], "text": []}

    fmt = parsed.get("format", {})
    result["general"] = {
        "file_name": os.path.basename(path),
        "format": fmt.get("format_long_name") or fmt.get("format_name", ""),
        "duration_s": _to_float(fmt.get("duration")),
        "size_bytes": _to_int(fmt.get("size")),
        "bit_rate": _to_int(fmt.get("bit_rate")),
        "tags": fmt.get("tags", {}) or {},
    }

    for stream in parsed.get("streams", []):
        codec_type = stream.get("codec_type", "")
        if codec_type == "video":
            result["video"].append({
                "codec": stream.get("codec_long_name") or stream.get("codec_name", ""),
                "codec_short": stream.get("codec_name", ""),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "frame_rate": _parse_fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
                "bit_rate": _to_int(stream.get("bit_rate")),
                "pix_fmt": stream.get("pix_fmt", ""),
                "color_space": stream.get("color_space", ""),
                "color_transfer": stream.get("color_transfer", ""),
                "color_primaries": stream.get("color_primaries", ""),
                "nb_frames": _to_int(stream.get("nb_frames")),
                "profile": stream.get("profile", ""),
                "tags": stream.get("tags", {}) or {},
            })
        elif codec_type == "audio":
            result["audio"].append({
                "codec": stream.get("codec_long_name") or stream.get("codec_name", ""),
                "codec_short": stream.get("codec_name", ""),
                "sample_rate": _to_int(stream.get("sample_rate")),
                "channels": stream.get("channels"),
                "channel_layout": stream.get("channel_layout", ""),
                "bit_rate": _to_int(stream.get("bit_rate")),
                "tags": stream.get("tags", {}) or {},
            })
        elif codec_type == "subtitle":
            result["text"].append({
                "codec": stream.get("codec_long_name") or stream.get("codec_name", ""),
                "tags": stream.get("tags", {}) or {},
            })

    return result


# ----------------------------------------------------------------------
#  Méthode 2 : 'ffmpeg -i' (repli, analyse de la sortie texte)
# ----------------------------------------------------------------------
def _read_with_ffmpeg(path):
    exe = get_ffmpeg_executable_path()
    try:
        proc = subprocess.run([exe, "-i", path], **_subprocess_kwargs())
        # ffmpeg écrit les infos sur stderr, et sort en erreur (pas de sortie) : normal
        text = proc.stderr.decode("utf-8", errors="replace")
    except Exception:
        return None

    if not text:
        return None

    result = {"general": {}, "video": [], "audio": [], "text": []}
    result["general"]["file_name"] = os.path.basename(path)
    try:
        result["general"]["size_bytes"] = os.path.getsize(path)
    except Exception:
        pass

    # Durée : "Duration: 00:01:23.45"
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
    if m:
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        result["general"]["duration_s"] = h * 3600 + mn * 60 + s

    # Bitrate global : "bitrate: 1234 kb/s"
    m = re.search(r"bitrate:\s*(\d+)\s*kb/s", text)
    if m:
        result["general"]["bit_rate"] = int(m.group(1)) * 1000

    # Flux vidéo : "Stream #0:0: Video: h264 (High), yuv420p, 1920x1080, 25 fps"
    for vm in re.finditer(r"Stream #\d+:\d+.*?:\s*Video:\s*([^\n]+)", text):
        line = vm.group(1)
        v = {"codec_short": line.split(",")[0].split("(")[0].strip()}
        rm = re.search(r"(\d{2,5})x(\d{2,5})", line)
        if rm:
            v["width"], v["height"] = int(rm.group(1)), int(rm.group(2))
        fm = re.search(r"([\d.]+)\s*fps", line)
        if fm:
            v["frame_rate"] = float(fm.group(1))
        pm = re.search(r"yuv\w+|rgb\w+|gbr\w+", line)
        if pm:
            v["pix_fmt"] = pm.group(0)
        v["codec"] = v.get("codec_short", "")
        result["video"].append(v)

    # Flux audio : "Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp, 128 kb/s"
    for am in re.finditer(r"Stream #\d+:\d+.*?:\s*Audio:\s*([^\n]+)", text):
        line = am.group(1)
        a = {"codec_short": line.split(",")[0].split("(")[0].strip()}
        sm = re.search(r"(\d+)\s*Hz", line)
        if sm:
            a["sample_rate"] = int(sm.group(1))
        if "stereo" in line:
            a["channels"] = 2
        elif "mono" in line:
            a["channels"] = 1
        a["channel_layout"] = (
            "stereo" if "stereo" in line else "mono" if "mono" in line else ""
        )
        a["codec"] = a.get("codec_short", "")
        result["audio"].append(a)

    return result


# ----------------------------------------------------------------------
#  Utilitaires
# ----------------------------------------------------------------------
def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_fraction(frac):
    """Convertit '25/1' ou '30000/1001' en nombre décimal (fps)."""
    if not frac or frac == "0/0":
        return None
    try:
        if "/" in frac:
            num, den = frac.split("/")
            den = float(den)
            if den == 0:
                return None
            return round(float(num) / den, 3)
        return float(frac)
    except (ValueError, ZeroDivisionError):
        return None
