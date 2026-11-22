"""VOCALOID6 project (.vpr sequence dict) -> TuneLab project (.tlp JSON dict). Pure: no file or UI access.

One-way: for tuning a VOCALOID6 draft in TuneLab, which needs a VOCALOID6 voice extension for TuneLab (installed
separately) to sing it. Everything that cannot be carried over is reported in `dropped` or `warnings`.
"""

from collections.abc import Callable

from . import voicebanks

LANG_PROP = "Language(0:Default/1:JPN/2:ENG/3:CHN)"
PHONEME_PROP = "Phoneme"
ENGINE = "VOCALOID6"
PLACEHOLDER = "a"  # vpr.PLACEHOLDER: phoneme VOCALOID6 has not computed yet
LANG_TO_PROP = {0: 1, 1: 2, 4: 3}  # VOCALOID language id -> TuneLab engine Language property
EXPORT_CONFIG = {"exportPath": "", "fileName": "", "format": "wav", "sampleRate": 44100, "bitDepth": 16,
                 "bitrate": 320, "masterExportEnabled": True, "masterExportChannels": 2}


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
    placeholder = phoneme == PLACEHOLDER and n.get("lyric") not in ("a", "あ", "ア")
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

    mt = seq.get("masterTrack", {})
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
        out_parts = []
        langs_seen: set[int] = set()
        for pi, p in enumerate(t.get("parts", [])):
            notes = p.get("notes", [])
            drop(ti, pi, "velocity", sum(1 for n in notes if n.get("velocity", 64) != 64))
            langs_seen.update(n.get("langID", 0) for n in notes)
            out_parts.append({
                "name": p.get("name", ""), "pos": float(p.get("pos", 0)), "startOffset": 0.0,
                "endOffset": float(p.get("duration", 0)), "type": "midi", "gain": 0.0,
                "voice": _voice(p, ttype, bank_lookup, warnings, ti), "properties": {},
                "notes": [_note(n, ttype) for n in notes], "automations": {}, "pitch": [], "vibratos": [],
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
    return doc, dropped, warnings
