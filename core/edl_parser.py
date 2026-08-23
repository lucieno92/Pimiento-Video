"""
Parseur EDL (format CMX3600) pour la feuille de droits musicaux.

L'EDL est un format texte simple et universel, exporté nativement par
Avid Media Composer, Premiere Pro, DaVinci Resolve et Final Cut Pro
(contrairement au XMEML, qui n'est pas supporté par Avid).

Limitation connue : un fichier EDL ne contient pas le frame rate numérique
exact (seulement une mention optionnelle "DROP FRAME" / "NON-DROP FRAME").
Le frame rate doit donc être choisi manuellement dans l'interface pour que
les durées soient calculées correctement ; les timecodes IN/OUT eux-mêmes
sont affichés tels quels depuis le fichier, sans reconversion.
"""

import re


class EdlParseError(Exception):
    pass


_TC_PATTERN = r"\d{2}[:;]\d{2}[:;]\d{2}[:;]\d{2}"

_EVENT_LINE_RE = re.compile(
    r"^(?P<event>\d+)\s+(?P<reel>\S+)\s+(?P<channel>\S+)\s+(?P<edit>\S+)"
    r"(?:\s+\S+)*\s+"
    r"(?P<src_in>" + _TC_PATTERN + r")\s+"
    r"(?P<src_out>" + _TC_PATTERN + r")\s+"
    r"(?P<rec_in>" + _TC_PATTERN + r")\s+"
    r"(?P<rec_out>" + _TC_PATTERN + r")\s*$"
)

_TITLE_RE = re.compile(r"^TITLE:\s*(.+)$", re.IGNORECASE)
_FCM_RE = re.compile(r"^FCM:\s*(DROP FRAME|NON-DROP FRAME)", re.IGNORECASE)

# Lignes de commentaire donnant le vrai nom de fichier/clip (le champ "reel"
# d'un événement EDL classique est souvent tronqué à 8 caractères).
_NAME_COMMENT_RE = re.compile(
    r"^\*\s*(?:FROM CLIP NAME|SOURCE FILE|CLIP NAME)\s*:\s*(.+)$", re.IGNORECASE
)
_GENERIC_COMMENT_RE = re.compile(r"^\*\s*(.+)$")


def _normalize_tc(tc):
    return tc.replace(";", ":")


def timecode_to_frames(tc, fps, drop_frame=False):
    """Convertit un timecode HH:MM:SS:FF en nombre de frames absolu."""
    h, m, s, f = (int(x) for x in _normalize_tc(tc).split(":"))
    nominal_fps = round(fps)
    total_minutes = h * 60 + m
    frame_number = (h * 3600 + m * 60 + s) * nominal_fps + f
    if drop_frame:
        drop_per_min = round(fps * 0.066666)
        frame_number -= drop_per_min * (total_minutes - total_minutes // 10)
    return frame_number


def frames_to_timecode(frame_count, fps):
    """Convertit un nombre de frames en timecode HH:MM:SS:FF (non drop-frame,
    utilisé ici uniquement pour afficher des DURÉES, pas des positions
    absolues, où l'imprécision du drop-frame est négligeable)."""
    nominal_fps = max(round(fps), 1)
    total_seconds, frames = divmod(int(frame_count), nominal_fps)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def _is_audio_channel(channel):
    """Un événement est considéré 'audio' si son champ piste contient la
    lettre A (couvre A, A2, A3, AA, A2/V, AA/V2, etc.)."""
    return "A" in channel.upper()


def parse_edl(path):
    """Analyse un fichier EDL et retourne :
    {
        "title": str,
        "drop_frame_hint": bool,   # déduit du FCM, simple indication
        "events": [
            {"event_num": str, "reel": str, "channel": str, "name": str,
             "rec_in": str, "rec_out": str},
            ...
        ]  # uniquement les événements audio (channel contient 'A')
    }
    Lève EdlParseError si aucun événement audio exploitable n'est trouvé.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        raise EdlParseError(f"Impossible de lire le fichier : {e}")

    title = "Cue Sheet"
    drop_frame_hint = False
    events = []
    current_event = None
    pending_name = None
    pending_name_is_specific = False

    def flush_current_event():
        nonlocal current_event, pending_name, pending_name_is_specific
        if current_event is not None:
            current_event["name"] = pending_name or current_event["reel"]
            events.append(current_event)
        current_event = None
        pending_name = None
        pending_name_is_specific = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        title_match = _TITLE_RE.match(line)
        if title_match:
            title = title_match.group(1).strip()
            continue

        fcm_match = _FCM_RE.match(line)
        if fcm_match:
            if fcm_match.group(1).upper() == "DROP FRAME":
                drop_frame_hint = True
            continue

        event_match = _EVENT_LINE_RE.match(line)
        if event_match:
            flush_current_event()
            channel = event_match.group("channel")
            if _is_audio_channel(channel):
                current_event = {
                    "event_num": event_match.group("event"),
                    "reel": event_match.group("reel"),
                    "channel": channel,
                    "rec_in": event_match.group("rec_in"),
                    "rec_out": event_match.group("rec_out"),
                }
            continue

        if line.startswith("*") and current_event is not None:
            name_match = _NAME_COMMENT_RE.match(line)
            if name_match:
                pending_name = name_match.group(1).strip()
                pending_name_is_specific = True
                continue
            if not pending_name_is_specific:
                generic_match = _GENERIC_COMMENT_RE.match(line)
                if generic_match:
                    pending_name = generic_match.group(1).strip()

    flush_current_event()

    if not events:
        raise EdlParseError(
            "Aucun événement audio exploitable n'a été trouvé dans ce "
            "fichier EDL. Vérifie qu'il s'agit bien d'un export EDL "
            "(format CMX3600) contenant des pistes audio."
        )

    return {"title": title, "drop_frame_hint": drop_frame_hint, "events": events}
