"""Write VOCALOID3 (.vsqx, vsq3) and VOCALOID4 (.vsqx, vsq4) projects from a VPR sequence.

Element names and order follow vsq3.xsd / vsq4.xsd, which Yamaha ships next to the VOCALOID6 editor.
Only classic ("VOCALOID") tracks can be exported; AI tracks and audio tracks are skipped with a warning.
"""

import xml.etree.ElementTree as ET

from .errors import VocaloidError
from .vpr import PLACEHOLDER

NS = {3: "http://www.yamaha.co.jp/vocaloid/schema/vsq3/", 4: "http://www.yamaha.co.jp/vocaloid/schema/vsq4/"}
STYLE_PLUGIN = ("ACA9C502-A04B-42b5-B2EB-5CEA36D16FCE", "VOCALOID2 Compatible Style", "3.0.0.1")
# VPR controller -> (vsq4 cc id, vsq3 mCtrl id). character is stored as GEN with the scale flipped around 64.
CC_IDS = {"dynamics": ("D", "DYN"), "breathiness": ("B", "BRE"), "brightness": ("R", "BRI"),
          "clearness": ("C", "CLE"), "character": ("G", "GEN"), "pitchBend": ("P", "PIT"),
          "pitchBendSens": ("S", "PBS"), "portamento": ("T", "POR"), "xSynth": ("X", "XSY"), "growl": ("W", "GWL")}
# Tag names that differ between the two schemas: logical name -> (vsq3, vsq4)
TAGS = {
    "bs": ("vBS", "bs"), "pc": ("vPC", "pc"), "id": ("compID", "id"), "vname": ("vVoiceName", "name"),
    "vprm": ("vVoiceParam", "vPrm"), "oDev": ("outDev", "oDev"), "rLvl": ("retLevel", "rLvl"),
    "tNo": ("vsTrackNo", "tNo"), "iGin": ("inGain", "iGin"), "sLvl": ("sendLevel", "sLvl"),
    "sEnable": ("sendEnable", "sEnable"), "m": ("mute", "m"), "s": ("solo", "s"),
    "monoUnit": ("seUnit", "monoUnit"), "stUnit": ("karaokeUnit", "stUnit"),
    "monoTrack": ("seTrack", "monoTrack"), "stTrack": ("karaokeTrack", "stTrack"),
    "tsBar": ("posMes", "m"), "nu": ("nume", "nu"), "de": ("denomi", "de"), "tempoT": ("posTick", "t"),
    "tempoV": ("bpm", "v"), "trackName": ("trackName", "name"), "part": ("musicalPart", "vsPart"),
    "t": ("posTick", "t"), "partName": ("partName", "name"), "sPlug": ("stylePlugin", "sPlug"),
    "sPlugId": ("stylePluginID", "id"), "sPlugName": ("stylePluginName", "name"), "pStyle": ("partStyle", "pStyle"),
    "attr": ("attr", "v"), "cc": ("mCtrl", "cc"), "dur": ("durTick", "dur"), "n": ("noteNum", "n"),
    "vel": ("velocity", "v"), "y": ("lyric", "y"), "p": ("phnms", "p"), "nStyle": ("noteStyle", "nStyle"),
    "seq": ("seqAttr", "seq"), "seqcc": ("elem", "cc"), "seqP": ("posNrm", "p"), "seqV": ("elv", "v"),
}


class _W:
    def __init__(self, version: int):
        self.v = version
        self.ns = NS[version]

    def tag(self, logical: str) -> str:
        return TAGS[logical][0 if self.v == 3 else 1] if logical in TAGS else logical

    def el(self, parent, logical: str, text=None, **attrs):
        e = ET.SubElement(parent, f"{{{self.ns}}}{self.tag(logical)}", {k: str(v) for k, v in attrs.items()})
        if text is not None:
            e.text = str(text)
        return e


def export(seq: dict, version: int = 4, pre_measure: int = 1) -> tuple[bytes, list[str]]:
    """Returns (xml bytes, warnings). Positions shift by pre_measure bars, as VOCALOID3/4 count them."""
    if version not in (3, 4):
        raise VocaloidError("VSQX version must be 3 or 4", "VSQX のバージョンは 3 か 4 です")
    w = _W(version)
    warnings: list[str] = []
    ET.register_namespace("", w.ns)
    root = ET.Element(f"{{{w.ns}}}vsq{version}")
    w.el(root, "vender", "Yamaha corporation")
    w.el(root, "version", "3.0.0.11" if version == 3 else "4.0.0.3")

    sigs = seq.get("masterTrack", {}).get("timeSig", {}).get("events") or [{"bar": 0, "numer": 4, "denom": 4}]
    first = sigs[0]
    offset = pre_measure * 1920 * first["numer"] // first["denom"]

    tracks = []
    for ti, t in enumerate(seq.get("tracks", [])):
        if t.get("type", 0) != 0:
            warnings.append(f"Track {ti} ({t.get('name')}) is not a classic VOCALOID track and was skipped / "
                            f"トラック {ti}（{t.get('name')}）は VOCALOID トラックではないため省きました")
            continue
        tracks.append(t)
    if not tracks:
        raise VocaloidError("No classic VOCALOID tracks to export (VSQX cannot hold VOCALOID:AI tracks)",
                            "書き出せる VOCALOID トラックがありません（VSQX は VOCALOID:AI トラックを保存できません）")
    if len(tracks) > 16:
        raise VocaloidError("VSQX holds at most 16 voice tracks", "VSQX のボイストラックは最大 16 です")

    # voice table: one entry per (comp ID, language); pc counts up within each bank select (language)
    voice_keys: list[tuple[str, int]] = []
    for t in tracks:
        for p in t.get("parts", []):
            v = p.get("voice", {})
            key = (v.get("compID", ""), v.get("langID", 0))
            if key not in voice_keys and key[0]:
                voice_keys.append(key)
    names = {v.get("compID"): v.get("name") for v in seq.get("voices", [])}
    program: dict[tuple[str, int], tuple[int, int]] = {}
    table = w.el(root, "vVoiceTable")
    for cid, lid in voice_keys:
        pc = sum(1 for k in program if k[1] == lid)
        program[(cid, lid)] = (lid, pc)
        vv = w.el(table, "vVoice")
        w.el(vv, "bs", lid)
        w.el(vv, "pc", pc)
        w.el(vv, "id", cid)
        w.el(vv, "vname", names.get(cid) or cid)
        prm = w.el(vv, "vprm")
        for k in ("bre", "bri", "cle", "gen", "ope"):
            w.el(prm, k, 0)
    if not voice_keys:
        raise VocaloidError("The classic tracks have no parts with a singer", "VOCALOID トラックに歌手付きのパートがありません")

    mixer = w.el(root, "mixer")
    mu = w.el(mixer, "masterUnit")
    w.el(mu, "oDev", 0)
    w.el(mu, "rLvl", 0)
    w.el(mu, "vol", 0)
    for i, t in enumerate(tracks):
        vu = w.el(mixer, "vsUnit")
        w.el(vu, "tNo", i)
        w.el(vu, "iGin", 0)
        w.el(vu, "sLvl", -898)
        w.el(vu, "sEnable", 0)
        w.el(vu, "m", int(t.get("isMuted", False)))
        w.el(vu, "s", int(t.get("isSoloMode", False)))
        pan = (t.get("panpot", {}).get("events") or [{"value": 0}])[0]["value"]
        w.el(vu, "pan", max(0, min(128, 64 + pan)))
        w.el(vu, "vol", (t.get("volume", {}).get("events") or [{"value": 0}])[0]["value"])
    mono = w.el(mixer, "monoUnit")
    for k, val in (("iGin", 0), ("sLvl", -898), ("sEnable", 0), ("m", 0), ("s", 0), ("pan", 64), ("vol", 0)):
        w.el(mono, k, val)
    st = w.el(mixer, "stUnit")
    for k, val in (("iGin", 0), ("m", 0), ("s", 0), ("vol", -129)):
        w.el(st, k, val)

    mt = w.el(root, "masterTrack")
    w.el(mt, "seqName", seq.get("title") or "Untitled")
    w.el(mt, "comment", "")
    w.el(mt, "resolution", 480)
    w.el(mt, "preMeasure", pre_measure)
    for i, s in enumerate(sigs):
        ts = w.el(mt, "timeSig")
        w.el(ts, "tsBar", 0 if i == 0 else s["bar"] + pre_measure)
        w.el(ts, "nu", s["numer"])
        w.el(ts, "de", s["denom"])
    for i, e in enumerate(seq.get("masterTrack", {}).get("tempo", {}).get("events") or [{"pos": 0, "value": 12000}]):
        te = w.el(mt, "tempo")
        w.el(te, "tempoT", 0 if i == 0 else e["pos"] + offset)
        w.el(te, "tempoV", e["value"])

    uncomputed = 0
    for i, t in enumerate(tracks):
        vt = w.el(root, "vsTrack")
        w.el(vt, "tNo", i)
        w.el(vt, "trackName", t.get("name", f"Track {i}"))
        w.el(vt, "comment", "")
        for p in sorted(t.get("parts", []), key=lambda x: x.get("pos", 0)):
            vp = w.el(vt, "part")
            w.el(vp, "t", p.get("pos", 0) + offset)
            w.el(vp, "playTime", p.get("duration", 1920))
            w.el(vp, "partName", p.get("name", "Part"))
            w.el(vp, "comment", "")
            sp = w.el(vp, "sPlug")
            w.el(sp, "sPlugId", STYLE_PLUGIN[0])
            w.el(sp, "sPlugName", STYLE_PLUGIN[1])
            w.el(sp, "version", STYLE_PLUGIN[2])
            ps = w.el(vp, "pStyle")
            for k, val in (("accent", 50), ("bendDep", 8), ("bendLen", 0), ("decay", 50), ("fallPort", 0),
                           ("opening", 127), ("risePort", 0)):
                w.el(ps, "attr", val, id=k)
            v = p.get("voice", {})
            bs, pc = program.get((v.get("compID", ""), v.get("langID", 0)), (0, 0))
            sg = w.el(vp, "singer")
            w.el(sg, "t", 0)
            w.el(sg, "bs", bs)
            w.el(sg, "pc", pc)
            events = []
            for c in p.get("controllers", []):
                if c.get("name") not in CC_IDS:
                    continue
                cid = CC_IDS[c["name"]][0 if version == 4 else 1]
                for e in c.get("events", []):
                    val = 63 - e["value"] if c["name"] == "character" else e["value"]
                    events.append((e["pos"], cid, val))
            for pos, cid, val in sorted(events):
                cc = w.el(vp, "cc")
                w.el(cc, "t", pos)
                w.el(cc, "attr", val, id=cid)
            for n in sorted(p.get("notes", []), key=lambda x: x["pos"]):
                ph = n.get("phoneme") or PLACEHOLDER
                if ph == PLACEHOLDER and n.get("lyric") not in ("a", "あ", "ア"):
                    uncomputed += 1
                ne = w.el(vp, "note")
                w.el(ne, "t", n["pos"])
                w.el(ne, "dur", n["duration"])
                w.el(ne, "n", n["number"])
                w.el(ne, "vel", n.get("velocity", 64))
                w.el(ne, "y", n.get("lyric", "a")[:32])
                w.el(ne, "p", ph[:32], lock=int(bool(n.get("isProtected"))))
                exp = n.get("exp", {})
                vib = n.get("vibrato") or {}
                ns = w.el(ne, "nStyle")
                for k, val in (("accent", exp.get("accent", 50)), ("bendDep", exp.get("bendDepth", 8)),
                               ("bendLen", exp.get("bendLength", 0)), ("decay", exp.get("decay", 50)),
                               ("fallPort", 0), ("opening", exp.get("opening", 127)), ("risePort", 0),
                               ("vibLen", round(100 * vib.get("duration", 0) / max(1, n["duration"]))),
                               ("vibType", vib.get("type", 0))):
                    w.el(ns, "attr", val, id=k)
                for sid, key in (("vibDep", "depths"), ("vibRate", "rates")):
                    pts = vib.get(key)
                    if vib.get("type") and pts:
                        sq = w.el(ns, "seq", id=sid)
                        span = max(1, vib.get("duration", 1))
                        for pt in pts:
                            c = w.el(sq, "seqcc")
                            w.el(c, "seqP", min(65535, round(pt["pos"] * 65535 / span)))
                            w.el(c, "seqV", pt["value"])
            if version == 4:
                w.el(vp, "plane", 0)
    w.el(root, "monoTrack")
    w.el(root, "stTrack")
    if uncomputed:
        warnings.append(
            f"{uncomputed} notes have no pronunciation yet (placeholder 'a'): open and save the .vpr in VOCALOID6 "
            f"first so it fills in the phonemes / {uncomputed} 個の音符にまだ発音記号がありません（仮の 'a'）。"
            f"先に VOCALOID6 で .vpr を開いて保存すると発音記号が入ります")
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(root, encoding="utf-8"), warnings
