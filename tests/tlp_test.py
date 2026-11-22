"""Unit tests for the VOCALOID6 -> TuneLab (.tlp) conversion. No VOCALOID6, TuneLab or voicebanks needed.

    python tests/tlp_test.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from vocaloid6_mcp import tlp, vpr  # noqa: E402

passed: list[str] = []
BANKS = {"AAA": {"kind": "ai", "language_ids": [0, 1, 4]}, "BBB": {"kind": "classic", "language_ids": [1]},
         "CCC": {"kind": "classic", "language_ids": [0]}}


def ok(cond, label, detail=None):
    if not cond:
        raise AssertionError(f"FAIL: {label}" + (f"\n  {detail}" if detail is not None else ""))
    passed.append(label)
    print(f"  ok  {label}", flush=True)


def note(pos=0, dur=480, number=60, lyric="a", phoneme="a", lang=0, **extra):
    return {"pos": pos, "duration": dur, "number": number, "lyric": lyric, "phoneme": phoneme, "langID": lang,
            "isProtected": False, "velocity": 64, **extra}


def ai_track(notes=(), **part):
    return {"type": 2, "name": "ai", "parts": [{"pos": 0, "duration": 1920, "voice": {"compID": "CCC", "langID": 0},
                                                "aiVoice": {"compID": "AAA", "langIDs": [{"langID": 0}]},
                                                "notes": list(notes), **part}]}


def classic_track(notes=(), comp="BBB", lang=1, **part):
    return {"type": 0, "name": "classic", "parts": [{"pos": 0, "duration": 1920, "voice": {"compID": comp, "langID": lang},
                                                     "notes": list(notes), **part}]}


def project(*tracks):
    seq = vpr.new("t", 120, 4, 4)
    seq["tracks"] = list(tracks)
    return seq


def convert(seq, tracks=None):
    return tlp.convert(seq, tracks, bank_lookup=BANKS.get)


def first_part(doc, track=0):
    return doc["tracks"][track]["parts"][0]


def test_tempo_and_timesig():
    seq = project(ai_track())
    vpr.set_tempo(seq, 90, 3840)
    vpr.set_time_signature(seq, 2, 3, 4)
    doc, _, _ = convert(seq)
    ok(doc["version"] == 1, "version 1")
    ok(doc["tempos"] == [{"pos": 0.0, "bpm": 120.0}, {"pos": 3840.0, "bpm": 90.0}], "tempos", doc["tempos"])
    ok({"barIndex": 2, "numerator": 3, "denominator": 4} in doc["timeSignatures"], "time signature", doc["timeSignatures"])


def test_ai_voice_id():
    doc, _, _ = convert(project(ai_track()))
    ok(first_part(doc)["voice"] == {"type": "VOCALOID6", "id": "0|AAA", "kind": "voice"}, "AI voice id",
       first_part(doc)["voice"])


def test_classic_voice_id():
    doc, _, _ = convert(project(classic_track()))
    ok(first_part(doc)["voice"]["id"] == "C1|BBB", "classic voice id", first_part(doc)["voice"])


def test_notes_part_relative():
    t = ai_track([note(0, lyric="ka"), note(480, number=62, lyric="e")])
    t["parts"][0]["pos"] = 1920
    doc, _, _ = convert(project(t))
    p = first_part(doc)
    ok(p["pos"] == 1920.0 and p["endOffset"] == 1920.0 and p["startOffset"] == 0.0, "part position and length", p)
    ok([(n["pos"], n["dur"], n["pitch"], n["lyric"]) for n in p["notes"]] == [(0.0, 480.0, 60, "ka"), (480.0, 480.0, 62, "e")],
       "notes are part-relative", p["notes"])
    ok(all(n["pronunciation"] == "" for n in p["notes"]), "pronunciation empty")


def test_track_fields():
    t = ai_track()
    t.update({"isMuted": True, "volume": {"events": [{"pos": 0, "value": -60}]}, "panpot": {"events": [{"pos": 0, "value": 32}]}})
    doc, _, _ = convert(project(t))
    tr = doc["tracks"][0]
    ok(tr["gain"] == -6.0 and tr["pan"] == 0.5 and tr["mute"] is True and tr["solo"] is False, "track gain/pan/mute", tr)


def test_languages():
    notes = [note(0, lyric="ka", phoneme="k a", lang=0), note(480, lyric="hel", phoneme="h @ l", lang=1),
             note(960, lyric="ni", phoneme="n i", lang=4), note(1440, lyric="ta", phoneme="t a", lang=0, isProtected=True),
             note(1920, lyric="ru", phoneme="a", lang=1)]
    doc, _, _ = convert(project(ai_track(notes)))
    ns = first_part(doc)["notes"]
    ok([n["properties"].get(tlp.LANG_PROP) for n in ns] == [1, 2, 3, 1, 2], "language property", ns)
    ok(tlp.PHONEME_PROP not in ns[0]["properties"], "Japanese unprotected phoneme not copied")
    ok(ns[1]["properties"].get(tlp.PHONEME_PROP) == "h @ l", "English phoneme copied")
    ok(ns[3]["properties"].get(tlp.PHONEME_PROP) == "t a", "protected Japanese phoneme copied")
    ok(tlp.PHONEME_PROP not in ns[4]["properties"], "placeholder phoneme never copied")


def test_unsupported_ai_language_warns():
    _, _, warnings = convert(project(ai_track([note(0, lang=2), note(480, lang=2)])))
    kor = [w for w in warnings if "VOCALOID6" in w and "track 0" in w.lower()]
    ok(len(kor) == 1, "one Korean warning naming the track and VOCALOID6", warnings)
    doc, _, warnings = convert(project(ai_track([note(0, lang=4), note(480, lang=4)])))
    ok(first_part(doc)["notes"][0]["properties"][tlp.LANG_PROP] == 3, "Chinese language property")
    ok(len([w for w in warnings if "Chinese" in w]) == 1, "one Chinese warning per track", warnings)


def test_audio_track_dropped_empty_part_kept():
    doc, dropped, _ = convert(project({"type": 1, "name": "backing", "parts": [{"pos": 0, "duration": 100}]}, ai_track()))
    ok(len(doc["tracks"]) == 1, "audio track not exported", doc["tracks"])
    ok({"track": 0, "part": None, "what": "audio track", "count": 1} in dropped, "audio track reported", dropped)
    ok(first_part(doc)["notes"] == [], "empty part exported")


def test_missing_bank_warns():
    doc, _, warnings = convert(project(classic_track(comp="ZZZ")))
    ok(first_part(doc)["voice"] == {"type": "", "id": "", "kind": "voice"}, "empty voice for a missing bank")
    ok(any("ZZZ" in w for w in warnings), "warning names the missing compID", warnings)


def test_velocity_dropped():
    _, dropped, _ = convert(project(classic_track([note(0, velocity=100), note(480, velocity=30), note(960)])))
    ok({"track": 0, "part": 0, "what": "velocity", "count": 2} in dropped, "velocity reported", dropped)


def test_tracks_filter():
    doc, _, _ = convert(project(ai_track(), classic_track()), tracks=[1])
    ok(len(doc["tracks"]) == 1 and first_part(doc)["voice"]["id"] == "C1|BBB", "only track 1 exported", doc["tracks"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[{name}]")
            fn()
    print(f"\n{len(passed)} checks passed")
