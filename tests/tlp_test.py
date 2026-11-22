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


def curves(**named):
    return [{"name": k, "events": [{"pos": x, "value": y} for x, y in pts]} for k, pts in named.items()]


def test_ai_curves():
    t = ai_track(controllers=curves(dynamics=[(0, 64), (480, 127)], s5Expression=[(0, 100)], s5Air=[(0, -50)],
                                    s5Character=[(0, 32)], pitchBend=[(0, 4096)], pitchBendSens=[(0, 12)]))
    a = first_part(convert(project(t))[0])["automations"]
    ok(a["Dynamics"]["values"] == [0, 0.0, 479, 0.0, 480, 63 / 64], "Dynamics scaled", a.get("Dynamics"))
    ok([a[k]["values"][1] for k in ("Expression", "Air", "Gender", "PitchBend", "PitchBendSensitivity")] == [1.0, -0.5, -0.5, 0.5, 12],
       "AI lanes scaled", a)
    ok(all(a[k]["default"] == 0 for k in ("Dynamics", "Expression", "Air", "Gender", "PitchBend"))
       and a["PitchBendSensitivity"]["default"] == 2, "lane defaults", a)


def test_classic_curves():
    t = classic_track(controllers=curves(brightness=[(0, 0)], breathiness=[(0, 64)], clearness=[(0, 64)], growl=[(0, 64)],
                                         air=[(0, 64)], exciter=[(0, 32)], character=[(0, -64)], portamento=[(0, 10)],
                                         xSynth=[(0, 10)]))
    doc, dropped, _ = convert(project(t))
    a = first_part(doc)["automations"]
    got = {k: a[k]["values"][1] for k in ("Brightness", "Breathiness", "Clearness", "Growl", "Air", "Exciter", "Gender")}
    ok(got == {"Brightness": -1.0, "Breathiness": 0.5, "Clearness": 0.5, "Growl": 0.5, "Air": 0.5, "Exciter": 0.5, "Gender": 1.0},
       "classic lanes scaled", got)
    whats = {d["what"] for d in dropped}
    ok({"curve:portamento", "curve:xSynth"} <= whats, "unsupported curves reported", dropped)


def test_style():
    doc, _, _ = convert(project(ai_track(styleName="Soft Style"), ai_track()))
    ok(first_part(doc)["properties"].get("Style") == "Soft Style", "style carried")
    ok("Style" not in first_part(doc, 1)["properties"], "no style key without a style")


def test_ai_note_settings():
    base = {k: 0.5 for k in vpr.AI_EXP_KEYS}
    n1 = note(0, aiExp={**base, "pitchFine": 0.8, "amplitudeEnd": 0.3, "vibratoLeadingDepth": 0.7},
              isAiVibratoEnabled=False, phonemePositions=[{"pos": vpr.AUTO_POS}, {"pos": 120}])
    doc, dropped, _ = convert(project(ai_track([n1]), ai_track([note(0, aiExp=dict(base))])))
    p = first_part(doc)
    ok(p["notes"][0]["properties"].get("Pitch Fine Tune") == 80, "pitchFine -> Pitch Fine Tune 80", p["notes"][0])
    ok(p["properties"].get("Mode(PIT/PIT+/Snap)") == 0, "Mode PIT when pitch settings are used", p["properties"])
    ok("Mode(PIT/PIT+/Snap)" not in first_part(doc, 1)["properties"], "no Mode when all settings are default")
    whats = {d["what"] for d in dropped if d["track"] == 0}
    ok({"ai_exp:amplitude", "ai_exp:vibrato depth", "ai vibrato off", "timing"} <= whats, "AI-only settings reported", dropped)


def test_rate_table():
    hz = tlp.rate_to_hz
    ok(hz(48) == 6.13 and hz(64) == 4.82 and hz(127) == 9.6, "table points", (hz(48), hz(64), hz(127)))
    ok(abs(hz(52) - 6.37) < 0.01, "interpolated inside segment A", hz(52))
    ok(hz(0) == hz(8) == 3.02, "rate 0 treated as 8", hz(0))
    ok(hz(60) == 6.61, "clamped at the end of segment A", hz(60))


def test_depth():
    ok(tlp.depth_to_semitones(123) == 1.0, "depth 123 = 1 semitone")
    ok(abs(tlp.depth_to_semitones(64) - 0.52) < 0.005, "depth 64 ~ 0.52 semitone", tlp.depth_to_semitones(64))


def vib(duration=960, depth=64, rate=48, type_=0):
    return {"type": type_, "duration": duration, "depths": [{"pos": 0, "value": depth}], "rates": [{"pos": 0, "value": rate}]}


def test_ai_vibrato_object():
    doc, _, _ = convert(project(ai_track([note(960, 1920, vibrato=vib())])))
    v = first_part(doc)["vibratos"]
    ok(len(v) == 1, "one vibrato", v)
    v = v[0]
    ok(v["pos"] == 1920.0 and v["dur"] == 960.0 and v["frequency"] == 6.13 and abs(v["amplitude"] - 0.52) < 0.005
       and v["phase"] == 0.0, "vibrato placement and shape", v)
    ok(v["attack"] == 0.12 and v["release"] == 0.02, "attack/release in seconds", v)


def test_no_vibrato_when_zero():
    doc, _, _ = convert(project(ai_track([note(0, 1920, vibrato=vib(duration=0)), note(1920, 1920, vibrato=vib(depth=0))])))
    ok(first_part(doc)["vibratos"] == [], "no vibrato for zero duration or depth")


def test_classic_vibrato_dropped():
    doc, dropped, _ = convert(project(classic_track([note(0, 1920, vibrato=vib(type_=1))])))
    ok(first_part(doc)["vibratos"] == [], "classic vibrato not converted")
    ok(any(d["what"] == "classic vibrato" for d in dropped), "classic vibrato reported", dropped)


def fake_cli(tmp, name, body):
    path = os.path.join(tmp, name + ".cmd")
    with open(path, "w", encoding="ascii") as f:
        f.write("@echo off\r\n" + body + "\r\n")
    return path


def with_cli(path, fn):
    old = os.environ.get("TUNELAB_CLI")
    os.environ["TUNELAB_CLI"] = path
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("TUNELAB_CLI")
        else:
            os.environ["TUNELAB_CLI"] = old


def test_find_cli_env_override():
    import tempfile
    from vocaloid6_mcp import tunelab
    tmp = tempfile.mkdtemp()
    ok(with_cli(os.path.join(tmp, "missing.exe"), tunelab.find_cli) is None, "override to a missing file means not installed")
    real = fake_cli(tmp, "cli", "exit /b 0")
    ok(with_cli(real, tunelab.find_cli) == real, "override to an existing file is used")


def test_status_not_installed():
    from vocaloid6_mcp import tunelab
    ok(with_cli(r"C:\nonexistent\TuneLab.Cli.exe", tunelab.status) == {"installed": False, "cli": None}, "status without TuneLab")


def test_probe_timeout_reports_error():
    import tempfile
    import time
    from vocaloid6_mcp import tunelab
    slow = fake_cli(tempfile.mkdtemp(), "slow", f'"{sys.executable}" -c "import time; time.sleep(20)"')
    t0 = time.time()
    r = with_cli(slow, lambda: tunelab.engines(timeout=1))
    ok(time.time() - t0 < 5 and r["installed"] is True and "error" in r, "a hung TuneLab is cut off and reported", r)


def test_engines_without_extension():
    import tempfile
    from vocaloid6_mcp import tunelab
    cli = fake_cli(tempfile.mkdtemp(), "noext", 'echo no engine with type id "VOCALOID6".& exit /b 1')
    r = with_cli(cli, tunelab.engines)
    ok(r["installed"] is True and r["vocaloid6_engine"] is False and r["voices"] == 0 and "hint" in r, "no voice extension", r)


def test_engines_with_extension():
    import tempfile
    from vocaloid6_mcp import tunelab
    cli = fake_cli(tempfile.mkdtemp(), "ext", 'echo {"mode": "sources", "engine": "VOCALOID6", "loaded": true, "total": 3, "sources": []}')
    r = with_cli(cli, tunelab.engines)
    ok(r == {"installed": True, "vocaloid6_engine": True, "voices": 3}, "engine and voice count", r)


def test_curves_hold_until_next_point():
    t = ai_track(controllers=curves(dynamics=[(0, 0), (480, 127), (481, 64)]))
    v = first_part(convert(project(t))[0])["automations"]["Dynamics"]["values"]
    ok(v == [0, -1.0, 479, -1.0, 480, 63 / 64, 481, 0.0], "VOCALOID curves are steps: value held until the next point", v)


def test_volume_pan_automation_dropped():
    t = ai_track()
    t.update({"volume": {"events": [{"pos": 0, "value": 0}, {"pos": 960, "value": -30}]},
              "panpot": {"events": [{"pos": 0, "value": 0}, {"pos": 960, "value": 10}]}})
    _, dropped, _ = convert(project(t))
    ok({"track": 0, "part": None, "what": "track volume/pan automation", "count": 2} in dropped,
       "later volume/pan events reported", dropped)


def test_path_fallback_finds_the_cli_not_the_editor():
    import shutil
    import tempfile
    from vocaloid6_mcp import tunelab
    d = tempfile.mkdtemp()
    for name in ("TuneLab.exe", "TuneLab.Cli.exe", "tunelab.cmd"):
        open(os.path.join(d, name), "w").close()
    saved = {k: os.environ.get(k) for k in ("TUNELAB_CLI", "LOCALAPPDATA", "PATH")}
    try:
        os.environ.pop("TUNELAB_CLI", None)
        os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
        os.environ["PATH"] = d
        found = tunelab.find_cli()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ok(found and os.path.basename(found).lower() == "tunelab.cli.exe", "PATH lookup returns TuneLab.Cli.exe", found)
    shutil.rmtree(d, ignore_errors=True)


def test_engines_reports_other_failures_as_errors():
    import tempfile
    from vocaloid6_mcp import tunelab
    cli = fake_cli(tempfile.mkdtemp(), "bad", "echo unknown option --json& exit /b 2")
    r = with_cli(cli, tunelab.engines)
    ok("error" in r and "vocaloid6_engine" not in r, "a failing CLI is an error, not 'no extension'", r)


def test_bad_track_index_rejected():
    from vocaloid6_mcp.errors import VocaloidError
    try:
        convert(project(ai_track(), classic_track()), tracks=[9])
        raised = False
    except VocaloidError:
        raised = True
    ok(raised, "tracks=[9] on a two-track project is an error, not an empty file")


def test_missing_bank_warns_once_per_track():
    t = classic_track(comp="ZZZ")
    t["parts"].append(dict(t["parts"][0], pos=1920))
    _, _, warnings = convert(project(t))
    ok(len([w for w in warnings if "ZZZ" in w]) == 1, "one missing-voicebank warning per track and voicebank", warnings)


def test_english_placeholder_never_copied():
    doc, _, _ = convert(project(ai_track([note(0, lyric="a", phoneme="a", lang=1)])))
    ok(tlp.PHONEME_PROP not in first_part(doc)["notes"][0]["properties"], "English lyric 'a' with placeholder phoneme")


def test_global_tempo_ignored_like_vocaloid6():
    seq = project(ai_track())
    vpr.set_tempo(seq, 90, 3840)
    seq["masterTrack"]["tempo"]["global"] = {"isEnabled": True, "value": 14000}
    doc, _, _ = convert(seq)
    ok(doc["tempos"] == [{"pos": 0.0, "bpm": 120.0}, {"pos": 3840.0, "bpm": 90.0}],
       "tempo events are used even with tempo.global enabled, as VOCALOID6 plays them", doc["tempos"])


def test_stderr_kept_out_of_json():
    import tempfile
    from vocaloid6_mcp import tunelab
    cli = fake_cli(tempfile.mkdtemp(), "noisy", 'echo log {x} 1>&2& echo {"loaded": true, "total": 2, "sources": []}')
    r = with_cli(cli, tunelab.engines)
    ok(r == {"installed": True, "vocaloid6_engine": True, "voices": 2}, "a brace in a stderr log line does not break parsing", r)


def test_probe_default_timeout_is_short():
    import inspect
    from vocaloid6_mcp import tunelab
    ok(inspect.signature(tunelab.engines).parameters["timeout"].default <= 30, "self_check probe fits a 60 s client timeout")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[{name}]")
            fn()
    print(f"\n{len(passed)} checks passed")
