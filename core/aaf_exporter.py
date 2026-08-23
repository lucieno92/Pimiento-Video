"""
Exporteur AAF minimal pour Avid Media Composer.
Utilise pyaaf2. Installe avec : pip install pyaaf2
"""

import os, fractions, urllib.request


def _url(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"): p = "/" + p
    return "file://localhost" + p


def export_sync_aaf(output_path, clips, fps=25.0, sequence_name="Sync Sequence"):
    try:
        import aaf2
    except ImportError:
        return False, "pyaaf2 non installé. Lance : pip install pyaaf2"

    if not clips:
        return False, "Aucun clip."

    try:
        rate = fractions.Fraction(round(fps), 1)
        total = max(c.offset_frames + c.duration_frames for c in clips)

        with aaf2.open(output_path, "w") as f:
            comp = f.create.CompositionMob()
            comp.name = sequence_name
            f.content.mobs.append(comp)

            for slot_id, clip in enumerate(clips, 1):
                kind = "picture" if clip.is_video else "sound"
                dur  = max(clip.duration_frames, 1)

                # SourceMob
                src = f.create.SourceMob()
                src.name = clip.name
                f.content.mobs.append(src)

                if clip.is_video:
                    desc = f.create.CDCIDescriptor()
                    desc["SampleRate"].value  = rate
                    desc["Length"].value      = dur
                    desc["StoredWidth"].value  = 1920
                    desc["StoredHeight"].value = 1080
                    desc["HorizontalSubsampling"].value = 2
                    desc["FrameLayout"].value  = "FullFrame"
                else:
                    desc = f.create.PCMDescriptor()
                    desc["SampleRate"].value       = rate
                    desc["Length"].value           = dur
                    desc["Channels"].value         = 2
                    desc["QuantizationBits"].value = 24
                    desc["AverageBPS"].value       = 288000

                src["EssenceDescription"].value = desc
                loc = f.create.NetworkLocator()
                loc["URLString"].value = _url(clip.path)
                desc["Locator"].append(loc)

                src_slot = f.create.TimelineMobSlot()
                src_slot["SlotID"].value = 1
                src_slot["EditRate"].value = rate
                src_slot["PhysicalTrackNumber"].value = 1
                src_filler = f.create.Filler(media_kind=kind, length=dur)
                src_slot["Segment"].value = src_filler
                src["Slots"].value.append(src_slot)

                # MasterMob
                master = f.create.MasterMob()
                master.name = clip.name
                f.content.mobs.append(master)

                master_slot = f.create.TimelineMobSlot()
                master_slot["SlotID"].value = 1
                master_slot["EditRate"].value = rate
                master_slot["PhysicalTrackNumber"].value = 1
                mc = f.create.SourceClip(media_kind=kind, length=dur)
                mc["SourceID"].value = src.id
                master_slot["Segment"].value = mc
                master["Slots"].value.append(master_slot)

                # Slot dans la composition
                segs = []
                if clip.offset_frames > 0:
                    segs.append(f.create.Filler(media_kind=kind,
                                                length=clip.offset_frames))
                sc = f.create.SourceClip(media_kind=kind, length=dur)
                sc["SourceID"].value = master.id
                segs.append(sc)
                trail = total - clip.offset_frames - dur
                if trail > 0:
                    segs.append(f.create.Filler(media_kind=kind, length=trail))

                seq = f.create.Sequence(media_kind=kind, segments=segs)
                cslot = f.create.TimelineMobSlot()
                cslot["SlotID"].value = slot_id
                cslot["EditRate"].value = rate
                cslot["PhysicalTrackNumber"].value = slot_id
                cslot["Segment"].value = seq
                comp["Slots"].value.append(cslot)

        return True, ""
    except Exception as e:
        import traceback
        return False, f"{e}\n\n{traceback.format_exc()}"
