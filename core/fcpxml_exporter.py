"""
Exporteur FCPXML v1.8 — compatible Premiere Pro, DaVinci Resolve, Final Cut Pro.

Structure :
  resources/
    format   (paramètres de la séquence)
    asset    (un par fichier source, avec NetworkLocator file://)
  library/event/project/sequence/spine
    clip     (un par clip, positionné avec offset= et lane= pour les pistes)
"""

import os
import math
from fractions import Fraction
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


def _rational(frames: int, fps: float) -> str:
    """Convertit N frames en fraction de secondes pour FCPXML."""
    if frames == 0:
        return "0s"
    num, denom = _fps_rational(fps)
    # frames / fps  =  frames * denom / num  secondes
    total_num   = frames * denom
    total_denom = num
    from math import gcd
    g = gcd(total_num, total_denom)
    n, d = total_num // g, total_denom // g
    return f"{n}/{d}s" if d != 1 else f"{n}s"


def _fps_rational(fps: float):
    """Retourne (num, denom) entiers pour un fps."""
    f = Fraction(fps).limit_denominator(1001)
    return f.numerator, f.denominator


def _file_url(path: str) -> str:
    """Convertit un chemin absolu en URL file:// (Windows + Mac)."""
    abs_path = os.path.abspath(path).replace("\\", "/")
    if not abs_path.startswith("/"):
        abs_path = "/" + abs_path
    return f"file://{abs_path}"


def export_fcpxml(output_path: str, tracks_data: list,
                  fps: float, earliest_frame: int,
                  sequence_name: str = "Sync Sequence") -> tuple:
    """
    tracks_data : list of (track_name, [ClipInfo])
    Retourne (True, "") ou (False, message_erreur).
    """
    try:
        num, denom = _fps_rational(fps)
        frame_dur   = f"{denom}/{num}s"

        # Durée totale de la séquence
        total_frames = 0
        for _, clips in tracks_data:
            for clip in clips:
                end = clip.offset_frames + clip.duration_frames
                if end > total_frames:
                    total_frames = end
        total_frames = max(total_frames, 1)

        # ── Racine ───────────────────────────────────────────────────
        root = Element("fcpxml", version="1.8")

        # ── Resources ────────────────────────────────────────────────
        resources = SubElement(root, "resources")

        # Format de la séquence
        fmt = SubElement(resources, "format",
            id="r0",
            name=f"FFVideoFormat{round(fps)}",
            frameDuration=frame_dur,
            width="1920",
            height="1080",
        )

        # Un asset par chemin de fichier unique
        asset_map = {}   # path → asset_id
        asset_idx = 1
        for _, clips in tracks_data:
            for clip in clips:
                if clip.path in asset_map:
                    continue
                aid = f"r{asset_idx}"
                asset_idx += 1
                asset_map[clip.path] = aid

                has_video = "1" if clip.is_video else "0"
                has_audio = "1"  # on suppose toujours de l'audio
                asset = SubElement(resources, "asset",
                    id=aid,
                    name=clip.name,
                    start="0s",
                    duration=_rational(clip.duration_frames, fps),
                    hasVideo=has_video,
                    hasAudio=has_audio,
                    format="r0",
                )
                SubElement(asset, "media-rep",
                    kind="original-media",
                    src=_file_url(clip.path),
                )

        # ── Library / Event / Project ────────────────────────────────
        library  = SubElement(root, "library")
        event    = SubElement(library, "event", name=sequence_name)
        project  = SubElement(event, "project", name=sequence_name)
        sequence = SubElement(project, "sequence",
            duration=_rational(total_frames, fps),
            format="r0",
            tcStart=_rational(earliest_frame, fps),
            tcFormat="NDF",
            audioLayout="stereo",
            audioRate="48k",
        )
        spine = SubElement(sequence, "spine")

        # ── Clips dans la spine ──────────────────────────────────────
        # FCPXML v1.8 : le clip principal (lane 0) est dans la spine,
        # les clips sur d'autres pistes utilisent lane="N" (négatif ou positif).
        # Premiere Pro et Resolve importent les lanes comme pistes séparées.
        for lane_idx, (track_name, clips) in enumerate(tracks_data):
            # lane 0 = piste principale (dans la spine directement)
            # lane -1, -2... = pistes connectées (au-dessus ou en dessous)
            lane = str(-lane_idx) if lane_idx > 0 else "0"
            for clip in clips:
                aid = asset_map[clip.path]
                attrs = dict(
                    name=clip.name,
                    ref=aid,
                    offset=_rational(clip.offset_frames, fps),
                    duration=_rational(max(clip.duration_frames, 1), fps),
                    start="0s",
                )
                if lane != "0":
                    attrs["lane"] = lane
                clip_el = SubElement(spine, "clip", **attrs)
                # Métadonnée : nom de la piste d'origine
                note = SubElement(clip_el, "note")
                note.text = track_name

        # ── Écriture du fichier (tout en texte, pas de mélange bytes) ─
        tree = ElementTree(root)
        try:
            indent(tree, space="  ")   # Python 3.9+
        except TypeError:
            pass   # Python 3.8 : pas de indentation automatique, ok

        with open(output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<!DOCTYPE fcpxml>\n')
            tree.write(f, encoding="unicode", xml_declaration=False)

        return True, ""

    except Exception as e:
        import traceback
        return False, f"{e}\n{traceback.format_exc()}"