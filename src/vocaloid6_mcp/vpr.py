"""Read, edit and write VOCALOID5/6 projects (.vpr = zip with Project/sequence.json).

Learned from files VOCALOID6 itself saved (no decompiling). Facts this code relies on:
- Track type 0 = VOCALOID (classic V3/V4/V5 banks), 1 = audio, 2 = VOCALOID:AI.
- Part "pos" is absolute (ticks); note "pos" is relative to its part. 480 ticks per quarter note.
- Tempo values are BPM x 100; time signature events use 0-based bars.
- A note needs a non-empty "phoneme" or VOCALOID6 drops it on load. Unprotected notes get their phonemes
  recomputed from the lyric when VOCALOID6 loads the file, so new notes carry a placeholder phoneme.
- Part curves are "controllers": [{"name", "events": [{"pos", "value"}]}], pos relative to the part.
Unknown fields are kept as they are, so files VOCALOID6 wrote survive a round trip.
"""

import copy
import json
import os
import shutil
import tempfile
import zipfile

from . import music
from .errors import VocaloidError
from .lyrics import LANG_NAMES, lang_id

SEQ = "Project/sequence.json"
PLACEHOLDER = "a"  # replaced by VOCALOID6's own pronunciation when it loads the file
TYPE_NAMES = {0: "VOCALOID", 1: "audio", 2: "VOCALOID:AI"}
# name -> (min, max, default). Ranges of the classic VOCALOID parameters; the AI-only ones (air, exciter) are
# assumed to share the 0..127 range of the classic sliders.
CURVES = {
    "dynamics": (0, 127, 64), "pitchBend": (-8192, 8191, 0), "pitchBendSens": (0, 24, 2),
    "breathiness": (0, 127, 0), "brightness": (0, 127, 64), "clearness": (0, 127, 0),
    "portamento": (0, 127, 64), "growl": (0, 127, 0), "xSynth": (0, 127, 0),
    "character": (-64, 63, 0), "air": (0, 127, 0), "exciter": (0, 127, 0),
}
CURVE_ALIASES = {"dyn": "dynamics", "pit": "pitchBend", "pb": "pitchBend", "pbs": "pitchBendSens",
                 "bre": "breathiness", "bri": "brightness", "cle": "clearness", "por": "portamento",
                 "gwl": "growl", "xsy": "xSynth", "gen": "character", "cha": "character", "air": "air",
                 "exc": "exciter"}


# ----------------------------------------------------------------------------- file io

def load(path: str) -> dict:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise VocaloidError(f"File not found: {path}", f"ファイルが見つかりません: {path}")
    try:
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read(SEQ).decode("utf-8-sig"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise VocaloidError(f"Not a VOCALOID5/6 project (.vpr): {path} ({e})",
                            f"VOCALOID5/6 のプロジェクト (.vpr) ではありません: {path}（{e}）") from e


def save(path: str, seq: dict) -> str:
    """Write seq into path, keeping every other zip entry (audio, etc.). Atomic: temp file then replace."""
    path = os.path.abspath(path)
    if not path.lower().endswith(".vpr"):
        raise VocaloidError(f"Project path must end with .vpr: {path}", f"プロジェクトのパスは .vpr で終わる必要があります: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".vpr", dir=os.path.dirname(path))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            if os.path.isfile(path):
                with zipfile.ZipFile(path) as old:
                    for item in old.infolist():
                        if item.filename != SEQ:
                            out.writestr(item, old.read(item.filename))
            out.writestr(SEQ, json.dumps(seq, ensure_ascii=False, indent=2))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def new(title: str = "Untitled", bpm: float = 120, numer: int = 4, denom: int = 4) -> dict:
    seq = {
        "version": {"major": 5, "minor": 0, "revision": 0},  # loads in VOCALOID5 and 6
        "vender": "Yamaha Corporation",
        "title": title,
        "masterTrack": {
            "samplingRate": 44100,
            "tempo": {"isFolded": False, "height": 0.0, "global": {"isEnabled": False, "value": 12000},
                      "events": [{"pos": 0, "value": 12000}]},
            "timeSig": {"isFolded": False, "events": [{"bar": 0, "numer": 4, "denom": 4}]},
        },
        "voices": [],
        "tracks": [],
    }
    set_tempo(seq, bpm, 0)
    set_time_signature(seq, 0, numer, denom)
    return seq


# ----------------------------------------------------------------------------- master track

def _tempo_events(seq):
    return seq.setdefault("masterTrack", {}).setdefault("tempo", {}).setdefault("events", [])


def set_tempo(seq: dict, bpm: float, position: int = 0) -> None:
    if not 20 <= float(bpm) <= 300:
        raise VocaloidError(f"Tempo {bpm} is outside 20..300 BPM", f"テンポ {bpm} が 20〜300 BPM の範囲外です")
    events = [e for e in _tempo_events(seq) if e["pos"] != int(position)]
    events.append({"pos": int(position), "value": round(float(bpm) * 100)})
    seq["masterTrack"]["tempo"]["events"] = sorted(events, key=lambda e: e["pos"])
    if int(position) == 0:
        seq["masterTrack"]["tempo"].setdefault("global", {})["value"] = round(float(bpm) * 100)


def remove_tempo(seq: dict, position: int) -> None:
    if int(position) == 0:
        raise VocaloidError("The tempo at tick 0 cannot be removed", "ティック 0 のテンポは削除できません")
    seq["masterTrack"]["tempo"]["events"] = [e for e in _tempo_events(seq) if e["pos"] != int(position)]


def _timesigs(seq):
    return seq.setdefault("masterTrack", {}).setdefault("timeSig", {}).setdefault("events", [])


def set_time_signature(seq: dict, bar: int, numer: int, denom: int) -> None:
    if denom not in (1, 2, 4, 8, 16, 32) or not 1 <= numer <= 32 or bar < 0:
        raise VocaloidError(f"Invalid time signature {numer}/{denom} at bar {bar}",
                            f"無効な拍子 {numer}/{denom}（小節 {bar}）")
    events = [e for e in _timesigs(seq) if e["bar"] != int(bar)]
    events.append({"bar": int(bar), "numer": int(numer), "denom": int(denom)})
    seq["masterTrack"]["timeSig"]["events"] = sorted(events, key=lambda e: e["bar"])


def bar_to_tick(seq: dict, bar: int) -> int:
    """Tick where 0-based bar starts, following time signature changes."""
    sigs = sorted(_timesigs(seq) or [{"bar": 0, "numer": 4, "denom": 4}], key=lambda e: e["bar"])
    tick, cur = 0, sigs[0]
    for b in range(int(bar)):
        cur = next((s for s in reversed(sigs) if s["bar"] <= b), sigs[0])
        tick += music.TICKS_PER_BEAT * 4 * cur["numer"] // cur["denom"]
    return tick


def tick_to_bar(seq: dict, tick: int, ceil: bool = False) -> int:
    bar = 0
    while bar_to_tick(seq, bar + 1) <= tick:
        bar += 1
    if ceil and bar_to_tick(seq, bar) < tick:
        bar += 1
    return bar


# ----------------------------------------------------------------------------- lookups

def _track(seq: dict, track: int) -> dict:
    tracks = seq.get("tracks", [])
    if not 0 <= int(track) < len(tracks):
        raise VocaloidError(f"Track {track} does not exist (the project has {len(tracks)} tracks, numbered from 0)",
                            f"トラック {track} はありません（トラック数 {len(tracks)}、0 から数えます）")
    return tracks[int(track)]


def _part(seq: dict, track: int, part: int) -> dict:
    parts = _track(seq, track).get("parts", [])
    if not 0 <= int(part) < len(parts):
        raise VocaloidError(f"Part {part} does not exist on track {track} ({len(parts)} parts, numbered from 0)",
                            f"トラック {track} にパート {part} はありません（パート数 {len(parts)}、0 から数えます）")
    return parts[int(part)]


def _notes(p: dict) -> list:
    p.setdefault("notes", []).sort(key=lambda n: (n["pos"], n.get("number", 0)))
    return p["notes"]


def _note(p: dict, index: int) -> dict:
    notes = _notes(p)
    if not 0 <= int(index) < len(notes):
        raise VocaloidError(f"Note {index} does not exist ({len(notes)} notes, numbered from 0)",
                            f"音符 {index} はありません（音符数 {len(notes)}、0 から数えます）")
    return notes[int(index)]


def _voice_of(p: dict, ttype: int = 0) -> dict:
    """The singer that actually sings: VOCALOID6 stores a default AI voice on classic parts too."""
    return (p.get("aiVoice") if ttype == 2 else None) or p.get("voice") or {}


def _voice_name(seq: dict, comp_id: str) -> str | None:
    return next((v.get("name") for v in seq.get("voices", []) if v.get("compID") == comp_id), None)


def _part_languages(p: dict, ttype: int) -> list[int]:
    if ttype == 2 and p.get("aiVoice"):
        return [x["langID"] for x in p["aiVoice"].get("langIDs", [])] or [0]
    return [p.get("voice", {}).get("langID", 0)]


# ----------------------------------------------------------------------------- summaries

def note_info(i: int, n: dict) -> dict:
    vib = n.get("vibrato") or {}
    out = {
        "index": i, "position": n["pos"], "duration": n["duration"], "tone": n["number"],
        "note": music.to_name(n["number"]), "lyric": n.get("lyric", ""), "phoneme": n.get("phoneme", ""),
        "language": LANG_NAMES.get(n.get("langID", 0), n.get("langID")), "protected": n.get("isProtected", False),
        "velocity": n.get("velocity", 64),
    }
    if vib.get("type"):
        out["vibrato"] = {"type": vib["type"], "duration": vib.get("duration", 0)}
    if n.get("phoneme") == PLACEHOLDER and n.get("lyric") not in ("a", "あ", "ア", "-"):
        out["phoneme"] = None  # not computed yet: VOCALOID6 fills it in when it loads the file
    return out


def summary(seq: dict) -> dict:
    tracks = []
    for ti, t in enumerate(seq.get("tracks", [])):
        ttype = t.get("type", 0)
        parts = []
        for pi, p in enumerate(t.get("parts", [])):
            v = _voice_of(p, ttype)
            parts.append({
                "index": pi, "name": p.get("name", ""), "position": p.get("pos", 0), "duration": p.get("duration", 0),
                "end": p.get("pos", 0) + p.get("duration", 0), "voice": _voice_name(seq, v.get("compID")) or v.get("compID"),
                "comp_id": v.get("compID"), "languages": [LANG_NAMES.get(x, x) for x in _part_languages(p, ttype)],
                "style": p.get("styleName"), "note_count": len(p.get("notes", [])),
                "curves": sorted({c["name"] for c in p.get("controllers", []) if c.get("events")}),
            })
        tracks.append({"index": ti, "name": t.get("name", ""), "type": TYPE_NAMES.get(ttype, ttype),
                       "muted": t.get("isMuted", False), "solo": t.get("isSoloMode", False), "parts": parts})
    mt = seq.get("masterTrack", {})
    return {
        "title": seq.get("title"),
        "file_version": "{major}.{minor}.{revision}".format(**seq.get("version", {"major": 0, "minor": 0, "revision": 0})),
        "tempo": [{"position": e["pos"], "bpm": e["value"] / 100} for e in mt.get("tempo", {}).get("events", [])],
        "time_signatures": [{"bar": e["bar"], "numer": e["numer"], "denom": e["denom"]}
                            for e in mt.get("timeSig", {}).get("events", [])],
        "tracks": tracks,
    }


# ----------------------------------------------------------------------------- tracks & parts

def _register_voice(seq: dict, bank: dict) -> None:
    voices = seq.setdefault("voices", [])
    if not any(v.get("compID") == bank["comp_id"] for v in voices):
        voices.append({"compID": bank["comp_id"], "name": bank["name"]})


def _voice_fields(bank: dict, language: str | None) -> dict:
    """Part fields that select a singer. AI parts carry both "voice" and "aiVoice" (as VOCALOID6 writes them)."""
    langs = bank["language_ids"] or [0]
    lid = lang_id(language) if language else langs[0]
    if lid not in langs and bank["kind"] == "classic" and bank["language_source"] == "registry":
        raise VocaloidError(f"{bank['name']} does not sing {LANG_NAMES[lid]}", f"{bank['name']} は {LANG_NAMES[lid]} を歌えません")
    if bank["kind"] == "ai":
        if lid not in langs:
            raise VocaloidError(f"{bank['name']} sings {bank['languages']}, not {LANG_NAMES[lid]}",
                                f"{bank['name']} が歌える言語は {bank['languages']} です（{LANG_NAMES[lid]} は不可）")
        # VOCALOID6 fills "voice" of AI parts with a classic bank; reuse one so it shows no "replaced" dialog
        classic = classic_fallback(bank, lid)
        return {"voice": {"compID": classic, "langID": lid},
                "aiVoice": {"compID": bank["comp_id"], "langIDs": [{"langID": x} for x in langs]}}
    return {"voice": {"compID": bank["comp_id"], "langID": lid}}


def classic_fallback(bank: dict, lid: int) -> str:
    """An installed classic bank that sings language lid (VOCALOID6's default first), else the AI bank itself."""
    from . import voicebanks
    try:
        default = voicebanks.default_voice("classic")
        same = [b for b in voicebanks.list_voicebanks("classic") if lid in b["language_ids"]]
    except Exception:  # noqa: BLE001 - registry trouble must not block writing a file
        default, same = None, []
    if default and lid in default["language_ids"]:
        return default["comp_id"]
    return same[0]["comp_id"] if same else bank["comp_id"]


def add_track(seq: dict, bank: dict, name: str | None = None, language: str | None = None,
              part_position: int = 0, part_duration: int = 1920) -> int:
    """New track with one empty part (VOCALOID stores the singer on parts, so a track needs one)."""
    fields = _voice_fields(bank, language)
    _register_voice(seq, bank)
    track = {"type": 2 if bank["kind"] == "ai" else 0, "name": name or bank["name"],
             "color": 3 if bank["kind"] == "ai" else 0, "busNo": 0, "isFolded": False, "height": 0.0,
             "isMuted": False, "isSoloMode": False, "parts": []}
    seq.setdefault("tracks", []).append(track)
    if int(part_duration) <= 0 or int(part_position) < 0:
        raise VocaloidError("Part position must be >= 0 and duration > 0", "パートの位置は 0 以上、長さは正の値にしてください")
    track["parts"].append({"name": track["name"], "pos": int(part_position), "duration": int(part_duration),
                           **fields, "notes": []})
    return len(seq["tracks"]) - 1


def set_track(seq: dict, track: int, name: str | None = None, mute: bool | None = None,
              solo: bool | None = None, volume: int | None = None, pan: int | None = None) -> dict:
    t = _track(seq, track)
    if name is not None:
        t["name"] = name
    if mute is not None:
        t["isMuted"] = bool(mute)
    if solo is not None:
        t["isSoloMode"] = bool(solo)
    if volume is not None:  # dB x 10 at tick 0, as the mixer stores it
        t.setdefault("volume", {"isFolded": False, "height": 0.0})["events"] = [{"pos": 0, "value": int(volume)}]
    if pan is not None:
        if not -64 <= int(pan) <= 64:
            raise VocaloidError("Pan must be -64..64", "パンは -64〜64 で指定してください")
        t.setdefault("panpot", {"isFolded": False, "height": 0.0})["events"] = [{"pos": 0, "value": int(pan)}]
    return t


def remove_track(seq: dict, track: int) -> None:
    _track(seq, track)
    del seq["tracks"][int(track)]


def set_voice(seq: dict, track: int, bank: dict, language: str | None = None) -> None:
    """Change the singer of every part on a track. Classic and AI tracks cannot swap kinds."""
    t = _track(seq, track)
    want = 2 if bank["kind"] == "ai" else 0
    if t.get("type", 0) != want:
        raise VocaloidError(
            f"Track {track} is a {TYPE_NAMES.get(t.get('type'))} track; {bank['name']} needs a {TYPE_NAMES[want]} track",
            f"トラック {track} は {TYPE_NAMES.get(t.get('type'))} トラックです。{bank['name']} には {TYPE_NAMES[want]} トラックが必要です")
    _register_voice(seq, bank)
    fields = _voice_fields(bank, language)
    for p in t.get("parts", []):
        p.pop("aiVoice", None)
        p.update(copy.deepcopy(fields))
        if language:
            for n in p.get("notes", []):
                n["langID"] = fields["voice"]["langID"]
                if not n.get("isProtected"):
                    n["phoneme"] = PLACEHOLDER


def add_part(seq: dict, track: int, position: int, duration: int = 1920, name: str | None = None,
             bank: dict | None = None, language: str | None = None) -> int:
    t = _track(seq, track)
    if t.get("type", 0) == 1:
        raise VocaloidError("Audio tracks cannot hold voice parts", "オーディオトラックにはボイスパートを置けません")
    if bank is None:  # reuse the singer of the track's first part
        if not t.get("parts"):
            raise VocaloidError("Give a voice for the first part of this track", "このトラックの最初のパートには voice を指定してください")
        ref = t["parts"][0]
        fields = {k: copy.deepcopy(ref[k]) for k in ("voice", "aiVoice") if k in ref}
    else:
        _register_voice(seq, bank)
        fields = _voice_fields(bank, language)
    if int(duration) <= 0 or int(position) < 0:
        raise VocaloidError("Part position must be >= 0 and duration > 0", "パートの位置は 0 以上、長さは正の値にしてください")
    part = {"name": name or t.get("name", "Part"), "pos": int(position), "duration": int(duration), **fields, "notes": []}
    t.setdefault("parts", []).append(part)
    t["parts"].sort(key=lambda p: p.get("pos", 0))
    return t["parts"].index(part)


def edit_part(seq: dict, track: int, part: int, position: int | None = None, duration: int | None = None,
              name: str | None = None) -> dict:
    p = _part(seq, track, part)
    if position is not None:
        p["pos"] = max(0, int(position))
    if duration is not None:
        if int(duration) <= 0:
            raise VocaloidError("Duration must be positive", "長さは正の値にしてください")
        p["duration"] = int(duration)
    if name is not None:
        p["name"] = name
    _track(seq, track)["parts"].sort(key=lambda x: x.get("pos", 0))
    return p


def remove_part(seq: dict, track: int, part: int) -> None:
    _part(seq, track, part)
    del _track(seq, track)["parts"][int(part)]


def fit_part(seq: dict, track: int, part: int) -> dict:
    """Grow or shrink a part so it ends on the first bar line at or after its last note."""
    p = _part(seq, track, part)
    end = p["pos"] + max((n["pos"] + n["duration"] for n in p.get("notes", [])), default=0)
    bar = max(tick_to_bar(seq, end, ceil=True), tick_to_bar(seq, p["pos"]) + 1)
    p["duration"] = bar_to_tick(seq, bar) - p["pos"]
    return {"position": p["pos"], "duration": p["duration"]}


def _grow(seq: dict, p: dict) -> None:
    end = max((n["pos"] + n["duration"] for n in p.get("notes", [])), default=0)
    if end > p.get("duration", 0):
        p["duration"] = bar_to_tick(seq, tick_to_bar(seq, p["pos"] + end, ceil=True)) - p["pos"]


# ----------------------------------------------------------------------------- notes

def _new_note(pos: int, dur: int, tone, lyric: str, lid: int, phoneme: str | None, velocity: int) -> dict:
    if int(dur) <= 0 or int(pos) < 0:
        raise VocaloidError("Note position must be >= 0 and duration > 0", "音符の位置は 0 以上、長さは正の値にしてください")
    return {"lyric": lyric, "phoneme": phoneme or PLACEHOLDER, "langID": lid, "isProtected": bool(phoneme),
            "pos": int(pos), "duration": int(dur), "number": music.to_midi(tone), "velocity": int(velocity)}


def _lang_for(seq: dict, track: int, p: dict, language: str | None) -> int:
    ttype = _track(seq, track).get("type", 0)
    langs = _part_languages(p, ttype)
    if not language or ttype != 2:  # default: the part's chosen language; a classic bank sings only its own
        return p.get("voice", {}).get("langID", langs[0]) if ttype == 2 else langs[0]
    lid = lang_id(language)
    if lid not in langs:
        raise VocaloidError(f"This AI voice sings {[LANG_NAMES[x] for x in langs]}, not {language}",
                            f"この AI 音源が歌える言語は {[LANG_NAMES[x] for x in langs]} です（{language} は不可）")
    return lid


def add_notes(seq: dict, track: int, part: int, notes: list[dict], language: str | None = None) -> list[int]:
    """notes: [{position, duration, tone, lyric?, phoneme?, velocity?, language?}] (positions relative to the part)."""
    p = _part(seq, track, part)
    added = []
    for n in notes:
        lid = _lang_for(seq, track, p, n.get("language") or language)
        note = _new_note(n["position"], n["duration"], n["tone"], n.get("lyric") or "a", lid,
                         n.get("phoneme"), n.get("velocity", 64))
        _notes(p).append(note)
        added.append(note)
    _grow(seq, p)
    order = _notes(p)
    return [next(i for i, x in enumerate(order) if x is n) for n in added]


def list_notes(seq: dict, track: int, part: int, start: int = 0, count: int | None = None) -> list[dict]:
    notes = _notes(_part(seq, track, part))
    end = len(notes) if count is None else start + count
    return [note_info(i, notes[i]) for i in range(max(0, start), min(end, len(notes)))]


def edit_notes(seq: dict, track: int, part: int, edits: list[dict]) -> None:
    p = _part(seq, track, part)
    targets = [(_note(p, e["index"]), e) for e in edits]  # resolve every index before changing order
    for n, e in targets:
        if e.get("position") is not None:
            n["pos"] = max(0, int(e["position"]))
        if e.get("duration") is not None:
            if int(e["duration"]) <= 0:
                raise VocaloidError("Duration must be positive", "長さは正の値にしてください")
            n["duration"] = int(e["duration"])
        if e.get("tone") is not None:
            n["number"] = music.to_midi(e["tone"])
        if e.get("velocity") is not None:
            n["velocity"] = max(0, min(127, int(e["velocity"])))
        if e.get("language"):
            n["langID"] = _lang_for(seq, track, p, e["language"])
            if not n.get("isProtected"):
                n["phoneme"] = PLACEHOLDER
        if e.get("lyric") is not None:
            n["lyric"] = e["lyric"]
            n["phoneme"], n["isProtected"] = PLACEHOLDER, False
        if e.get("phoneme") is not None:
            if e["phoneme"]:
                n["phoneme"], n["isProtected"] = e["phoneme"], True
            else:  # empty string: let VOCALOID6 pronounce the lyric again
                n["phoneme"], n["isProtected"] = PLACEHOLDER, False
        if e.get("vibrato") is not None:
            v = e["vibrato"]
            vib = n.setdefault("vibrato", {"type": 0, "duration": 0})
            if v.get("type") is not None:
                vib["type"] = int(v["type"])
            if v.get("duration") is not None:
                vib["duration"] = max(0, min(int(v["duration"]), n["duration"]))
            if v.get("depth") is not None:
                vib["depths"] = [{"pos": 0, "value": int(v["depth"])}]
            if v.get("rate") is not None:
                vib["rates"] = [{"pos": 0, "value": int(v["rate"])}]
    _notes(p)
    _grow(seq, p)


def delete_notes(seq: dict, track: int, part: int, indexes: list[int]) -> int:
    p = _part(seq, track, part)
    doomed = {id(_note(p, i)) for i in indexes}
    p["notes"] = [n for n in _notes(p) if id(n) not in doomed]
    return len(doomed)


def assign_lyrics(seq: dict, track: int, part: int, lyrics: list[str], start: int = 0,
                  language: str | None = None) -> int:
    """Put one lyric per note from note index start on. Returns how many notes changed."""
    p = _part(seq, track, part)
    notes = _notes(p)
    if start + len(lyrics) > len(notes):
        raise VocaloidError(f"{len(lyrics)} lyrics but only {len(notes) - start} notes from index {start}",
                            f"歌詞 {len(lyrics)} 個に対し、音符 {start} 番以降は {len(notes) - start} 個しかありません")
    lid = _lang_for(seq, track, p, language) if language else None
    for n, y in zip(notes[start:], lyrics):
        n["lyric"], n["phoneme"], n["isProtected"] = y, PLACEHOLDER, False
        if lid is not None:
            n["langID"] = lid
    return len(lyrics)


def add_melody(seq: dict, track: int, part: int, melody: str, lyrics: list[str] | None,
               start: int | None = None, language: str | None = None) -> list[int]:
    p = _part(seq, track, part)
    if start is None:
        start = max((n["pos"] + n["duration"] for n in p.get("notes", [])), default=0)
    notes = music.melody_notes(melody, lyrics, start)
    return add_notes(seq, track, part, notes, language)


# ----------------------------------------------------------------------------- curves

def curve_name(name: str) -> str:
    if name in CURVES:
        return name
    key = CURVE_ALIASES.get(name.lower()) or next((k for k in CURVES if k.lower() == name.lower()), None)
    if not key:
        raise VocaloidError(f"Unknown curve {name!r}; use one of {list(CURVES)}",
                            f"不明なカーブ {name!r}: {list(CURVES)} のいずれかを指定してください")
    return key


def _controller(p: dict, name: str, create: bool) -> dict | None:
    for c in p.setdefault("controllers", []):
        if c.get("name") == name:
            return c
    if not create:
        return None
    c = {"name": name, "events": []}
    p["controllers"].append(c)
    return c


def set_curve(seq: dict, track: int, part: int, name: str, points: list[tuple[int, int]]) -> int:
    """Replace the curve between the first and last point with these points (positions relative to the part)."""
    name = curve_name(name)
    lo, hi, _ = CURVES[name]
    pts = sorted((int(x), int(y)) for x, y in points)
    if not pts:
        raise VocaloidError("No points given", "点が指定されていません")
    bad = [y for _, y in pts if not lo <= y <= hi]
    if bad:
        raise VocaloidError(f"{name} values must be {lo}..{hi}: {bad}", f"{name} の値は {lo}〜{hi} です: {bad}")
    c = _controller(_part(seq, track, part), name, True)
    keep = [e for e in c["events"] if not pts[0][0] <= e["pos"] <= pts[-1][0]]
    c["events"] = sorted(keep + [{"pos": x, "value": y} for x, y in pts], key=lambda e: e["pos"])
    return len(pts)


def get_curve(seq: dict, track: int, part: int, name: str) -> dict:
    name = curve_name(name)
    c = _controller(_part(seq, track, part), name, False)
    lo, hi, default = CURVES[name]
    return {"name": name, "range": [lo, hi], "default": default,
            "points": [[e["pos"], e["value"]] for e in (c or {}).get("events", [])]}


def clear_curve(seq: dict, track: int, part: int, name: str, start: int | None = None, end: int | None = None) -> int:
    name = curve_name(name)
    c = _controller(_part(seq, track, part), name, False)
    if not c:
        return 0
    before = len(c["events"])
    if start is None and end is None:
        c["events"] = []
    else:
        lo, hi = start if start is not None else -1, end if end is not None else 1 << 40
        c["events"] = [e for e in c["events"] if not lo <= e["pos"] <= hi]
    return before - len(c["events"])


def copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.copyfile(src, dst)
