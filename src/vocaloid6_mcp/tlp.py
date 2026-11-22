"""VOCALOID6 project (.vpr sequence dict) -> TuneLab project (.tlp JSON dict). Pure: no file or UI access.

One-way: for tuning a VOCALOID6 draft in TuneLab, which needs a VOCALOID6 voice extension for TuneLab (installed
separately) to sing it. Everything that cannot be carried over is reported in `dropped` or `warnings`.
"""

from collections.abc import Callable

from . import voicebanks, vpr
from .vpr import AUTO_POS, PLACEHOLDER

LANG_PROP = "Language(0:Default/1:JPN/2:ENG/3:CHN)"
PHONEME_PROP = "Phoneme"
ENGINE = "VOCALOID6"
LANG_TO_PROP = {0: 1, 1: 2, 4: 3}  # VOCALOID language id -> TuneLab engine Language property
EXPORT_CONFIG = {"exportPath": "", "fileName": "", "format": "wav", "sampleRate": 44100, "bitDepth": 16,
                 "bitrate": 320, "masterExportEnabled": True, "masterExportChannels": 2}


MODE_PROP = "Mode(PIT/PIT+/Snap)"
STYLE_PROP = "Style"
# vpr curve -> (TuneLab lane, controller value -> lane value, lane default). Lanes are [-1, 1] (or [0, 1]) like the
# TuneLab engine's, PitchBendSensitivity stays in semitones.
_SHARED = {
    "dynamics": ("Dynamics", lambda v: (v - 64) / 64, 0),
    "pitchBend": ("PitchBend", lambda v: v / 8192, 0),
    "pitchBendSens": ("PitchBendSensitivity", lambda v: v, 2),
}
AI_CURVES_TLP = {**_SHARED,
                 "s5Character": ("Gender", lambda v: v / -64, 0),
                 "s5Expression": ("Expression", lambda v: (v - 50) / 50, 0),
                 "s5Air": ("Air", lambda v: v / 100, 0)}
CLASSIC_CURVES_TLP = {**_SHARED,
                      "character": ("Gender", lambda v: v / -64, 0),
                      "brightness": ("Brightness", lambda v: (v - 64) / 64, 0),
                      "breathiness": ("Breathiness", lambda v: v / 128, 0),
                      "clearness": ("Clearness", lambda v: v / 128, 0),
                      "growl": ("Growl", lambda v: v / 128, 0),
                      "air": ("Air", lambda v: v / 128, 0),
                      "exciter": ("Exciter", lambda v: v / 64, 0)}
AI_EXP_TO_PROP = {"pitchTransitionStart": "Pitch Leading Transition", "pitchFine": "Pitch Fine Tune",
                  "pitchTransitionEnd": "Pitch Following Transition", "pitchDriftStart": "Pitch Leading Drift",
                  "pitchDriftEnd": "Pitch Following Drift", "pitchScalingCenter": "Pitch Scaling Center",
                  "pitchScalingOrigin": "Pitch Scaling Origin"}


# VOCALOID:AI manual vibrato, measured in VOCALOID6 6.13 (pitch tracked on renders): rate -> Hz is two parallel
# segments with a drop at 64; amplitude is depth / 123 semitones.
_RATE_A = [(8, 3.02), (24, 4.27), (32, 4.82), (40, 5.37), (48, 6.13), (56, 6.61)]
_RATE_B = [(64, 4.82), (72, 5.54), (80, 6.12), (96, 7.49), (104, 8.20), (112, 8.6), (120, 9.00), (127, 9.6)]
VIBRATO_ATTACK = 0.12  # seconds (TuneLab vibrato attack/release are seconds)
VIBRATO_RELEASE = 0.02  # not 0: TuneLab divides by it at the vibrato's last sample


def rate_to_hz(rate: int) -> float:
    table = _RATE_B if rate >= 64 else _RATE_A
    rate = max(table[0][0], min(table[-1][0], rate))
    for (r0, h0), (r1, h1) in zip(table, table[1:]):
        if r0 <= rate <= r1:
            return round(h0 + (h1 - h0) * (rate - r0) / (r1 - r0), 4)
    return table[0][1]


def depth_to_semitones(depth: int) -> float:
    return depth / 123


def _vibrato(n: dict) -> dict | None:
    vib = n.get("vibrato") or {}
    dur = min(int(vib.get("duration") or 0), int(n["duration"]))
    depth = (vib.get("depths") or [{"value": 0}])[0]["value"]
    if dur <= 0 or depth <= 0:
        return None
    rate = (vib.get("rates") or [{"value": 64}])[0]["value"]
    return {"pos": float(n["pos"] + n["duration"] - dur), "dur": float(dur), "frequency": rate_to_hz(rate),
            "amplitude": depth_to_semitones(depth), "phase": 0.0, "attack": VIBRATO_ATTACK, "release": VIBRATO_RELEASE}


def _automations(part: dict, ttype: int, drop) -> dict:
    table = AI_CURVES_TLP if ttype == 2 else CLASSIC_CURVES_TLP
    out = {}
    for c in part.get("controllers", []):
        events = sorted(c.get("events") or [], key=lambda e: e["pos"])
        if not events:
            continue
        if c.get("name") not in table:
            drop(f"curve:{c.get('name')}")
            continue
        lane, scale, default = table[c["name"]]
        values, prev = [], None
        for e in events:
            if prev is not None and e["pos"] > prev["pos"] + 1:  # VOCALOID holds a value until the next point; TuneLab ramps
                values += [e["pos"] - 1, scale(prev["value"])]
            values += [e["pos"], scale(e["value"])]
            prev = e
        out[lane] = {"default": default, "values": values}
    return out


def _ai_settings(n: dict, props: dict, drop) -> bool:
    """Copy VOCALOID:AI pitch settings to note properties; report the rest. True if a pitch setting was set."""
    exp = n.get("aiExp") or {}
    for key, prop in AI_EXP_TO_PROP.items():
        if exp.get(key, 0.5) != 0.5:
            props[prop] = round(exp[key] * 100)
    if any(exp.get(k, 0.5) != 0.5 for k in ("amplitudeWhole", "amplitudeStart", "amplitudeEnd")):
        drop("ai_exp:amplitude")
    if any(exp.get(k, 0.5) != 0.5 for k in ("vibratoLeadingDepth", "vibratoFollowingDepth")):
        drop("ai_exp:vibrato depth")
    if n.get("isAiVibratoEnabled") is False:
        drop("ai vibrato off")
    if any(x.get("pos") != AUTO_POS for x in n.get("phonemePositions") or []):
        drop("timing")
    return any(p in props for p in AI_EXP_TO_PROP.values())


def _default_bank_lookup(comp_id: str) -> dict | None:
    return next((b for b in voicebanks.list_voicebanks() if b["comp_id"] == comp_id), None)


def _first_event(container: dict | None, default: float) -> float:
    events = (container or {}).get("events") or []
    return float(events[0]["value"]) if events else default


def _voice(part: dict, ttype: int, bank_lookup, warnings: list[str], ti: int) -> dict:
    voice = (part.get("aiVoice") if ttype == 2 else None) or part.get("voice") or {}
    comp = voice.get("compID", "")
    bank = bank_lookup(comp) if comp else None
    if not bank:
        warnings.append(f"Track {ti}: voicebank {comp or '(none)'} is not installed here; the part has no voice in TuneLab. "
                        f"/ トラック {ti}: 音源 {comp or '(なし)'} がこの PC にないため、TuneLab では歌手なしになります")
        return {"type": "", "id": "", "kind": "voice"}
    langs = bank.get("language_ids") or [0]
    if ttype == 2:
        return {"type": ENGINE, "id": f"{langs[0]}|{comp}", "kind": "voice"}
    return {"type": ENGINE, "id": f"C{part.get('voice', {}).get('langID', langs[0])}|{comp}", "kind": "voice"}


def _note(n: dict, ttype: int) -> dict:
    props = {}
    lang = n.get("langID", 0)
    if ttype == 2 and lang in LANG_TO_PROP:
        props[LANG_PROP] = LANG_TO_PROP[lang]
    phoneme = n.get("phoneme") or ""
    placeholder = phoneme == PLACEHOLDER and (lang != 0 or n.get("lyric") not in ("a", "あ", "ア"))
    if phoneme and not placeholder and (lang != 0 or n.get("isProtected")):
        props[PHONEME_PROP] = phoneme  # non-Japanese: keep VOCALOID6's pronunciation; Japanese: only user-locked
    return {"pos": float(n["pos"]), "dur": float(n["duration"]), "pitch": int(n["number"]), "lyric": n.get("lyric", ""),
            "pronunciation": "", "properties": props}


def convert(seq: dict, tracks: list[int] | None = None,
            bank_lookup: Callable[[str], dict | None] | None = None) -> tuple[dict, list[dict], list[str]]:
    """Return (tlp document, dropped, warnings). dropped: [{track, part, what, count}] merged per track/part/what."""
    bank_lookup = bank_lookup or _default_bank_lookup
    counts: dict[tuple, int] = {}
    warnings: list[str] = []

    def drop(ti, pi, what, n=1):
        if n:
            counts[(ti, pi, what)] = counts.get((ti, pi, what), 0) + n

    for i in tracks or []:
        vpr._track(seq, i)  # a wrong index is an error, not an empty file
    mt = seq.get("masterTrack", {})
    # VOCALOID6 6.13 plays the tempo events and ignores tempo.global, even with isEnabled true (checked by ear)
    doc = {
        "version": 1,
        "tempos": [{"pos": float(e["pos"]), "bpm": e["value"] / 100} for e in mt.get("tempo", {}).get("events", [])],
        "timeSignatures": [{"barIndex": e["bar"], "numerator": e["numer"], "denominator": e["denom"]}
                           for e in mt.get("timeSig", {}).get("events", [])],
        "tracks": [],
        "exportConfig": dict(EXPORT_CONFIG),
    }
    for ti, t in enumerate(seq.get("tracks", [])):
        if tracks is not None and ti not in tracks:
            continue
        ttype = t.get("type", 0)
        if ttype == 1:
            drop(ti, None, "audio track")
            continue
        drop(ti, None, "track volume/pan automation",
             sum(max(0, len((t.get(k) or {}).get("events") or []) - 1) for k in ("volume", "panpot")))
        out_parts = []
        langs_seen: set[int] = set()
        for pi, p in enumerate(t.get("parts", [])):
            notes = p.get("notes", [])
            drop(ti, pi, "velocity", sum(1 for n in notes if n.get("velocity", 64) != 64))
            langs_seen.update(n.get("langID", 0) for n in notes)

            def part_drop(what, ti=ti, pi=pi):
                drop(ti, pi, what)

            out_notes, vibratos, uses_pitch_settings = [], [], False
            for n in notes:
                tn = _note(n, ttype)
                if ttype == 2:
                    uses_pitch_settings |= _ai_settings(n, tn["properties"], part_drop)
                    v = _vibrato(n)
                    if v:
                        vibratos.append(v)
                elif _vibrato(n):
                    part_drop("classic vibrato")  # VOCALOID6 renders it flat, so there is nothing to match
                out_notes.append(tn)
            props = {}
            if ttype == 2 and p.get("styleName"):
                props[STYLE_PROP] = p["styleName"]
            if uses_pitch_settings:
                props[MODE_PROP] = 0  # the engine reads the per-note pitch settings only outside Snap mode
            out_parts.append({
                "name": p.get("name", ""), "pos": float(p.get("pos", 0)), "startOffset": 0.0,
                "endOffset": float(p.get("duration", 0)), "type": "midi", "gain": 0.0,
                "voice": _voice(p, ttype, bank_lookup, warnings, ti), "properties": props,
                "notes": out_notes, "automations": _automations(p, ttype, part_drop), "pitch": [], "vibratos": vibratos,
            })
        if ttype == 2 and langs_seen & {2, 3}:
            warnings.append(f"Track {ti}: Korean/Spanish lyrics on a VOCALOID:AI voice cannot be sung through TuneLab; "
                            f"keep this track in VOCALOID6. / トラック {ti}: AI 音源の韓国語・スペイン語は TuneLab で歌えません。"
                            "このトラックは VOCALOID6 で仕上げてください")
        if ttype == 2 and 4 in langs_seen:
            warnings.append(f"Track {ti}: Chinese on VOCALOID:AI voices may not render in TuneLab for some voices; check the "
                            f"render, else keep this track in VOCALOID6. / トラック {ti}: AI 音源の中国語は TuneLab で"
                            "レンダリングできない音源があります。確認し、だめなら VOCALOID6 で仕上げてください")
        if ttype != 2 and langs_seen & {2, 3}:
            warnings.append(f"Track {ti}: Korean/Spanish on classic voices is untested in TuneLab; check the render. "
                            f"/ トラック {ti}: 旧世代音源の韓国語・スペイン語は TuneLab で未検証です。確認してください")
        doc["tracks"].append({
            "name": t.get("name", ""), "gain": _first_event(t.get("volume"), 0) / 10,
            "pan": _first_event(t.get("panpot"), 0) / 64, "mute": bool(t.get("isMuted", False)),
            "solo": bool(t.get("isSoloMode", False)), "color": "", "asRefer": True, "exportEnabled": False,
            "exportChannels": 1, "parts": out_parts,
        })
    dropped = [{"track": ti, "part": pi, "what": what, "count": n} for (ti, pi, what), n in counts.items()]
    return doc, dropped, list(dict.fromkeys(warnings))  # a missing voicebank is reported per part: keep one per track
