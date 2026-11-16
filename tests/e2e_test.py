"""End-to-end test: starts the MCP server over stdio as a real MCP client.

    python tests/e2e_test.py           # file / voicebank / utility tools (VOCALOID6 may be closed)
    python tests/e2e_test.py --live    # also drives the running VOCALOID6 (opens a temporary project)

The live part opens its own project with force=false, so it stops if VOCALOID6 has unsaved changes.
The live part keeps its temp folder (VOCALOID6 still has the project open); set VOCALOID6_MCP_KEEP=1 to keep it
after file tests too.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XSD_DIR = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "VOCALOID6", "Editor")
passed: list[str] = []


def ok(cond, label, detail=None):
    if not cond:
        raise AssertionError(f"FAIL: {label}" + (f"\n  {detail}" if detail is not None else ""))
    passed.append(label)
    print(f"  ok  {label}", flush=True)


class Client:
    def __init__(self, session: ClientSession):
        self.s = session

    async def __call__(self, _tool, **args):
        res = await self.s.call_tool(_tool, args)
        text = "".join(c.text for c in res.content if getattr(c, "text", None))
        if res.isError:
            raise RuntimeError(f"{_tool} failed: {text}")
        if res.structuredContent is not None and set(res.structuredContent) == {"result"}:
            return res.structuredContent["result"]
        texts = [c.text for c in res.content if getattr(c, "text", None) is not None]
        try:
            return [json.loads(t) for t in texts] if len(texts) > 1 else json.loads(text)
        except ValueError:
            return text

    async def error(self, name, **args) -> str:
        res = await self.s.call_tool(name, args)
        ok(res.isError, f"{name} returns an error")
        return "".join(c.text for c in res.content if getattr(c, "text", None))


def validate_vsqx(path: str, version: int):
    """(valid, errors) against Yamaha's shipped schema, or None if lxml / the schema is missing."""
    xsd = os.path.join(XSD_DIR, f"vsq{version}.xsd")
    try:
        from lxml import etree
    except ImportError:
        return None
    if not os.path.isfile(xsd):
        return None
    schema = etree.XMLSchema(etree.parse(xsd))
    return schema.validate(etree.parse(path)), str(schema.error_log)


async def file_tests(c: Client, tmp: str) -> dict:
    print("[utilities]")
    ok(await c("note_to_midi", note="C4") == 60, "C4 = 60")
    ok(await c("note_to_midi", note="Bb3") == 58 and await c("note_to_midi", note="A#3") == 58, "A#3 = Bb3 = 58")
    ok(await c("midi_to_note", midi=61) == "C#4", "61 = C#4")
    ok(await c("beats_to_ticks", beats=1.5) == 720, "1.5 beats = 720 ticks")
    r = await c("split_lyrics", text="きゃりーぱみゅぱみゅ、ちゃっと")
    ok(r["lyrics"] == ["きゃ", "り", "-", "ぱ", "みゅ", "ぱ", "みゅ", "ちゃ", "っ", "と"], "Japanese mora split", r)
    r = await c("split_lyrics", text="Hel-lo, beau-ti-ful world!")
    ok(r["lyrics"] == ["hel-", "lo", "beau-", "ti-", "ful", "world"], "English syllable split (VOCALOID style)", r)
    r = await c("split_lyrics", text="hello love world")
    ok(r["lyrics"] == ["hello", "love", "world"] and "hello" in r["warnings"][0] and "love" not in r["warnings"][0],
       "un-hyphenated multi-syllable word is flagged", r)
    r = await c("split_lyrics", text="我爱你")
    ok(r["lyrics"] == ["我", "爱", "你"] and r["language"] == "zh", "Chinese split", r)
    r = await c("split_lyrics", text="사랑해")
    ok(r["lyrics"] == ["사", "랑", "해"] and r["language"] == "ko", "Korean split", r)
    err = await c.error("note_to_midi", note="H9")
    ok("/" in err and any("぀" <= ch <= "ヿ" for ch in err), "error message is bilingual", err)

    print("[voicebanks]")
    banks = await c("list_voicebanks")
    ok(len(banks) > 0, "at least one VOCALOID3-6 voicebank installed (the tests need one)", banks)
    ais = [b for b in banks if b["kind"] == "ai"]
    ai = ais[-1] if ais else None  # not the first: VOCALOID6 falls back to its default AI voice, which hides swaps
    classic = next((b for b in banks if b["kind"] == "classic" and b["languages"] == ["ja"]), None) or \
        next((b for b in banks if b["kind"] == "classic"), None)
    english = next((b for b in banks if b["kind"] == "classic" and "en" in b["languages"]), None)
    ok(all(b["track_type"] == ("VOCALOID:AI" if b["kind"] == "ai" else "VOCALOID") for b in banks), "track types per kind")
    ok(all(b["era"] in (3, 4, 5, 6) for b in banks), "eras are VOCALOID3-6")
    one = await c("get_voicebank", voice=banks[0]["comp_id"])
    ok(one["name"] == banks[0]["name"], "get_voicebank by comp ID")
    styles = await c("list_styles")
    ok(isinstance(styles, list), f"list_styles ({len(styles)} presets)")

    print("[project file]")
    path = os.path.join(tmp, "test_song.vpr")
    r = await c("new_project", path=path, bpm=128)
    ok(r["summary"]["tempo"][0]["bpm"] == 128, "new_project at 128 BPM")
    ok(r["summary"]["file_version"] == "5.0.0", "a new project is VOCALOID5-compatible", r["summary"])
    err = await c.error("new_project", path=path)
    ok("overwrite" in err, "new_project refuses to overwrite")
    tracks = {}
    if ai:
        r = await c("add_track", voice=ai["name"], language="ja", path=path)
        tracks["ai"] = r["result"]["track"]
        missing = next((x for x in ("ko", "es", "en", "zh", "ja") if x not in ai["languages"]), None)
        if missing:
            err = await c.error("add_track", voice=ai["name"], language=missing, path=path)
            ok(missing in err, f"AI voice refuses a language it does not sing ({missing})", err)
    if classic:
        r = await c("add_track", voice=classic["name"], path=path)
        tracks["classic"] = r["result"]["track"]
    if english and english is not classic:
        r = await c("add_track", voice=english["name"], path=path)
        tracks["english"] = r["result"]["track"]
    proj = await c("get_project", path=path)
    ok(len(proj["tracks"]) == len(tracks), f"{len(tracks)} tracks added", proj)
    if ai:
        ok(proj["file_version"] == "6.5.1", "a project with an AI track declares VOCALOID6 6.5.1", proj["file_version"])
    for key, ti in tracks.items():
        want = "VOCALOID:AI" if key == "ai" else "VOCALOID"
        ok(proj["tracks"][ti]["type"] == want, f"{key} track is {want}")

    t = tracks.get("ai", tracks.get("classic"))
    r = await c("add_melody", track=t, part=0, melody="C4:1 D4:1 E4:2 r:1 G4:1", lyrics="さくらー", path=path)
    ok(r["result"]["lyrics"] == ["さ", "く", "ら", "-"], "add_melody splits lyrics", r)
    notes = await c("list_notes", track=t, part=0, path=path)
    ok([n["note"] for n in notes] == ["C4", "D4", "E4", "G4"], "melody pitches", notes)
    ok([n["position"] for n in notes] == [0, 480, 960, 2400], "rest leaves a gap", notes)
    ok(all(n["phoneme"] is None for n in notes[:3]), "phonemes wait for VOCALOID6", notes)
    proj = await c("get_project", path=path)
    ok(proj["tracks"][t]["parts"][0]["duration"] == 3840, "part grew to two bars", proj["tracks"][t]["parts"][0])
    err = await c.error("add_melody", track=t, part=0, melody="C4 D4", lyrics="さくら", path=path)
    ok("3" in err and "2" in err, "melody/lyric count mismatch is explained", err)

    await c("assign_lyrics", track=t, part=0, text="はなび", path=path)
    notes = await c("list_notes", track=t, part=0, path=path)
    ok([n["lyric"] for n in notes[:3]] == ["は", "な", "び"], "assign_lyrics", notes)
    vib = ({"ai_vibrato": False, "ai_exp": {"vibratoFollowingDepth": 0.8}, "vibrato": {"duration": 400, "depth": 200, "rate": 60}}
           if "ai" in tracks else {"vibrato": {"type": 1, "duration": 400, "depth": 70, "rate": 60}})
    await c("edit_notes", track=t, part=0, path=path, edits=[
        {"index": 0, "tone": "C#4", "duration": 240},
        {"index": 1, "phoneme": "n a"},
        {"index": 2, **vib}])
    notes = await c("list_notes", track=t, part=0, path=path)
    ok(notes[0]["note"] == "C#4" and notes[0]["duration"] == 240, "edit_notes pitch and length")
    ok(notes[1]["phoneme"] == "n a" and notes[1]["protected"], "phoneme override is protected")
    if "ai" in tracks:
        ok(notes[2]["ai_vibrato"] is False and notes[2]["ai_exp"] == {"vibratoFollowingDepth": 0.8}, "AI vibrato", notes[2])
        ok(notes[2]["vibrato"] == {"type": 0, "duration": 400, "depth": 127, "rate": 60},
           "AI manual vibrato (depth clamped to 127)", notes[2])
        err = await c.error("edit_notes", track=t, part=0, path=path, edits=[{"index": 2, "vibrato": {"type": 1}}])
        ok("type" in err, "vibrato type refused on an AI track", err)
        err = await c.error("edit_notes", track=t, part=0, path=path, edits=[{"index": 2, "ai_exp": {"wobble": 0.5}}])
        ok("vibratoLeadingDepth" in err, "unknown ai_exp key lists the valid ones", err)
        await c("edit_notes", track=t, part=0, path=path, edits=[{"index": 1, "timing": [None, 40, 400, None]}])
        notes = await c("list_notes", track=t, part=0, path=path)
        ok(notes[1].get("timing") == [None, 40, 400], "timing (trailing automatic entries dropped)", notes[1])
        await c("edit_notes", track=t, part=0, path=path, edits=[{"index": 1, "phoneme": "n a"}])
        notes = await c("list_notes", track=t, part=0, path=path)
        ok("timing" not in notes[1], "timing cleared when the phonemes change", notes[1])
        await c("edit_notes", track=t, part=0, path=path, edits=[{"index": 1, "timing": [-41]}])
        await c("edit_notes", track=t, part=0, path=path, edits=[{"index": 1, "timing": []}])
        notes = await c("list_notes", track=t, part=0, path=path)
        ok("timing" not in notes[1], "timing [] = all automatic", notes[1])
        err = await c.error("edit_notes", track=t, part=0, path=path, edits=[{"index": 1, "timing": [9999]}])
        ok("timing" in err, "timing out of range refused", err)
    else:
        err = await c.error("edit_notes", track=t, part=0, path=path, edits=[{"index": 2, "timing": [0]}])
        ok("VOCALOID:AI" in err, "timing refused on a VOCALOID track", err)
        ok(notes[2]["vibrato"] == {"type": 1, "duration": 400, "depth": 70, "rate": 60}, "vibrato", notes[2])
    r = await c("add_notes", track=t, part=0, path=path, notes=[{"position": 2880, "duration": 480, "tone": "A4", "lyric": "た"}])
    ok(r["result"]["indexes"] == [4], "add_notes returns sorted index", r)
    await c("delete_notes", track=t, part=0, indexes=[4], path=path)
    ok(len(await c("list_notes", track=t, part=0, path=path)) == 4, "delete_notes")
    err = await c.error("list_notes", track=t, part=7, path=path)
    ok("0" in err, "bad part index is explained", err)

    print("[curves, tempo, parts]")
    await c("set_curve", track=t, part=0, curve="DYN", points=[[0, 100], [960, 40]], path=path)
    await c("set_curve", track=t, part=0, curve="pitchBend", points=[[480, -2000], [720, 0]], path=path)
    cv = await c("get_curve", track=t, part=0, curve="dynamics", path=path)
    ok(cv["points"] == [[0, 100], [960, 40]] and cv["range"] == [0, 127], "set/get dynamics curve", cv)
    err = await c.error("set_curve", track=t, part=0, curve="dynamics", points=[[0, 300]], path=path)
    ok("0..127" in err, "curve range is checked", err)
    err = await c.error("set_curve", track=t, part=0, curve="wobble", points=[[0, 1]], path=path)
    ok("dynamics" in err, "unknown curve lists the valid ones", err)
    r = await c("clear_curve", track=t, part=0, curve="PIT", path=path)
    ok(r["result"]["removed"] == 2, "clear_curve", r)
    if "ai" in tracks:
        await c("set_curve", track=t, part=0, curve="expression", points=[[0, 80]], path=path)
        cv = await c("get_curve", track=t, part=0, curve="EXP", path=path)
        ok(cv["name"] == "s5Expression" and cv["range"] == [0, 100] and cv["points"] == [[0, 80]], "AI expression lane", cv)
        await c("set_curve", track=t, part=0, curve="air", points=[[0, -50]], path=path)
        cv = await c("get_curve", track=t, part=0, curve="air", path=path)
        ok(cv["name"] == "s5Air" and cv["points"] == [[0, -50]], "air on an AI track writes the AI lane", cv)
        err = await c.error("set_curve", track=t, part=0, curve="brightness", points=[[0, 1]], path=path)
        ok("no effect" in err, "classic-only lane refused on an AI track", err)
    await c("set_tempo", bpm=96, position=7680, path=path)
    await c("set_time_signature", numer=3, denom=4, bar=4, path=path)
    proj = await c("get_project", path=path)
    ok(proj["tempo"][-1] == {"position": 7680, "bpm": 96.0}, "tempo change", proj["tempo"])
    ok(proj["time_signatures"][-1] == {"bar": 4, "numer": 3, "denom": 4}, "time signature change")
    r = await c("add_part", track=t, position=7680, duration=1440, path=path)
    ok(r["result"]["part"] == 1, "add_part on the track's singer")
    await c("add_melody", track=t, part=1, melody="E4:1 D4:1 C4:1 C4:1", lyrics="あいうえ", path=path)
    r = await c("fit_part", track=t, part=1, path=path)
    ok(r["result"] == {"position": 7680, "duration": 2880}, "fit_part follows the 3/4 bars", r)
    await c("edit_track", track=t, name="Lead", pan=-20, path=path)
    proj = await c("get_project", path=path)
    ok(proj["tracks"][t]["name"] == "Lead", "edit_track renames")

    if "english" in tracks:
        await c("add_melody", track=tracks["english"], part=0, melody="C4:1 D4:1 E4:2", lyrics="hel-lo world", path=path)
        notes = await c("list_notes", track=tracks["english"], part=0, path=path)
        ok([n["lyric"] for n in notes] == ["hel-", "lo", "world"] and notes[0]["language"] == "en", "English melody")
    if "classic" in tracks:
        if not (await c("get_project", path=path))["tracks"][tracks["classic"]]["parts"][0]["note_count"]:
            await c("add_melody", track=tracks["classic"], part=0, melody="G4:1 A4:1", lyrics="はる", path=path)
        await c("set_curve", track=tracks["classic"], part=0, curve="character", points=[[0, -10]], path=path)
        err = await c.error("set_curve", track=tracks["classic"], part=0, curve="expression", points=[[0, 1]], path=path)
        ok("no effect" in err, "AI-only lane refused on a VOCALOID track", err)

    print("[vsqx]")
    if "classic" in tracks or "english" in tracks:
        for ver in (3, 4):
            out = os.path.join(tmp, f"test_v{ver}.vsqx")
            r = await c("export_vsqx", output=out, version=ver, path=path)
            ok(os.path.getsize(out) > 500, f"export_vsqx v{ver}")
            ok(any("skipped" in w for w in r["warnings"]) == ("ai" in tracks), f"v{ver}: AI tracks are skipped with a warning", r)
            check = validate_vsqx(out, ver)
            if check is None:
                print(f"  --  vsq{ver}.xsd or lxml missing: schema check skipped")
            else:
                ok(check[0], f"v{ver} matches Yamaha's vsq{ver}.xsd", check[1])
    else:
        print("  --  no classic voicebank: VSQX export skipped")
    return {"path": path, "tracks": tracks, "ai": ai, "classic": classic, "english": english}


def write_midi(path: str) -> bool:
    try:
        import mido
    except ImportError:
        return False
    m = mido.MidiFile(ticks_per_beat=480)
    meta, song = mido.MidiTrack(), mido.MidiTrack()
    m.tracks += [meta, song]
    meta.append(mido.MetaMessage("set_tempo", tempo=500000))
    song.append(mido.MetaMessage("track_name", name="Imported"))
    for n, y in ((60, "la"), (62, "la")):
        song.append(mido.MetaMessage("lyrics", text=y))
        song.append(mido.Message("note_on", note=n, velocity=100))
        song.append(mido.Message("note_off", note=n, time=480))
    m.save(path)
    return True


async def live_tests(c: Client, tmp: str, ctx: dict):
    print("[live: app]")
    st = await c("vocaloid_status")
    if not st["running"]:
        st = await c("launch_vocaloid")
    ok(st["running"], "VOCALOID6 is running", st)
    path = ctx["path"]
    r = await c("open_project", path=path)  # force=false: stops here if VOCALOID6 has unsaved changes
    ok(r["opened"].lower() == path.lower(), "open_project", r)
    chk = await c("self_check")
    ok(chk["ok"], "self_check: every selector matches this VOCALOID6", chk)

    print("[live: VOCALOID6 fills in phonemes]")
    proj = await c("get_project")
    ok(proj["path"].lower() == path.lower(), "live get_project knows the file", proj["path"])
    ok(len(proj["tracks"]) == len(ctx["tracks"]), "all tracks survived loading", proj)
    for key, bank in (("ai", ctx["ai"]), ("classic", ctx["classic"]), ("english", ctx["english"])):
        if key in ctx["tracks"]:
            voice = proj["tracks"][ctx["tracks"][key]]["parts"][0]["voice"]
            ok(voice == bank["name"], f"VOCALOID6 keeps the {key} singer {bank['name']}", voice)
    t = ctx["tracks"].get("ai", ctx["tracks"].get("classic"))
    notes = await c("list_notes", track=t, part=0)
    ok(all(n["phoneme"] for n in notes), "every note has a phoneme after loading", notes)
    ok(notes[1]["phoneme"] == "n a" and notes[1]["protected"], "protected phoneme kept", notes[1])
    ok(notes[2]["vibrato"]["type"] == 1, "vibrato kept", notes[2])
    ok(notes[3]["lyric"] == "-", f"continuation note sings {notes[3]['phoneme']!r}", notes[3])
    cv = await c("get_curve", track=t, part=0, curve="dynamics")
    ok(cv["points"] == [[0, 100], [960, 40]], "curve kept", cv)
    if "english" in ctx["tracks"]:
        en = await c("list_notes", track=ctx["tracks"]["english"], part=0)
        ok([n["phoneme"] for n in en] == ["h e", "l @U", "w @r l d"], "English hel- lo world pronounced", en)
    if ctx["ai"] and "en" in ctx["ai"]["languages"]:
        await c("add_track", voice=ctx["ai"]["name"], language="en", part_position=0)
        ti = len((await c("get_project"))["tracks"]) - 1
        await c("add_melody", track=ti, part=0, melody="C4:1 D4:1 E4:2", lyrics="hel-lo world")
        en = await c("list_notes", track=ti, part=0)
        ok([n["phoneme"] for n in en] == ["h e", "l @U", "w @r l d"], "AI voice sings English", en)
        await c("undo")
        await c("undo")

    print("[live: edit, undo, redo]")
    before = len(await c("list_notes", track=t, part=0))
    r = await c("add_notes", track=t, part=0, notes=[{"position": 2880, "duration": 480, "tone": "A4", "lyric": "た"}])
    ok(r["mode"] == "live", "live add_notes", r)
    notes = await c("list_notes", track=t, part=0)
    ok(len(notes) == before + 1 and notes[-1]["phoneme"], "live note added and pronounced", notes[-1])
    await c("undo")
    ok(len(await c("list_notes", track=t, part=0)) == before, "undo")
    await c("redo")
    ok(len(await c("list_notes", track=t, part=0)) == before + 1, "redo")
    await c("undo")

    print("[live: transport & export]")
    await c("play")
    await asyncio.sleep(1.5)
    await c("stop")
    ok(True, "play / stop")
    mid = os.path.join(tmp, "export.mid")
    r = await c("export_midi", output=mid)
    ok(r["bytes"] > 50, "export_midi", r)
    wav = os.path.join(tmp, "export.wav")
    r = await c("export_wav", output=wav)
    ok(r["bytes"] > 10000, f"export_wav ({r['seconds']} s)", r)
    muted = [x["muted"] for x in (await c("get_project"))["tracks"]]
    stem = os.path.join(tmp, "stem.wav")
    r = await c("export_wav", output=stem, tracks=[t])
    ok(r["bytes"] > 10000 and r["tracks"] == [t], "export_wav of one track (stem)", r)
    ok([x["muted"] for x in (await c("get_project"))["tracks"]] == muted, "stem export restores mute states")
    src = os.path.join(tmp, "import.mid")
    if write_midi(src):
        n = len((await c("get_project"))["tracks"])
        await c("import_midi", midi_path=src, track_type="ai" if ctx["ai"] else "classic")
        await c("save_project")
        ok(len((await c("get_project"))["tracks"]) == n + 1, "import_midi adds a track")
    for ver in (3, 4):
        vs = os.path.join(tmp, f"test_v{ver}.vsqx")
        if os.path.exists(vs):
            await c("open_project", path=vs, force=True)
            saved = os.path.join(tmp, f"from_v{ver}.vpr")
            await c("save_project", path=saved)
            p = await c("get_project", path=saved)
            ok(p["tracks"] and all(t["parts"] for t in p["tracks"]), f"VOCALOID6 opens our v{ver} .vsqx", p)
            cur = [x for t in p["tracks"] for x in t["parts"] if "character" in x["curves"]]
            ok(bool(cur), f"v{ver} curves survive", p)
    await c("open_project", path=path, force=True)


def unit_tests():
    print("[stem helpers]")
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from vocaloid6_mcp import vpr
    seq = {"tracks": [{"isMuted": False, "isSoloMode": True}, {"isMuted": True}, {}]}
    saved = vpr.only_tracks(seq, [1])
    ok([(t["isMuted"], t["isSoloMode"]) for t in seq["tracks"]] == [(True, False), (False, False), (True, False)],
       "only_tracks mutes the others and clears solo", seq)
    vpr.restore_tracks(seq, saved)
    ok([(t["isMuted"], t["isSoloMode"]) for t in seq["tracks"]] == [(False, True), (True, False), (False, False)],
       "restore_tracks puts mute/solo back", seq)


async def main():
    live = "--live" in sys.argv
    unit_tests()
    tmp = tempfile.mkdtemp(prefix="vocaloid6_mcp_test_")
    exe = os.path.join(ROOT, ".venv", "Scripts", "vocaloid6-mcp.exe")
    params = StdioServerParameters(command=exe if os.path.isfile(exe) else sys.executable,
                                   args=[] if os.path.isfile(exe) else ["-m", "vocaloid6_mcp.server"],
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    try:
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            c = Client(s)
            ctx = await file_tests(c, tmp)
            if live:
                await live_tests(c, tmp, ctx)
        print(f"\n{len(passed)} checks passed")
    finally:
        if live or os.environ.get("VOCALOID6_MCP_KEEP"):
            print(f"temp folder kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
