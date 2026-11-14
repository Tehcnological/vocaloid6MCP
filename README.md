# VOCALOID6 MCP

[日本語版 README はこちら](README.ja.md)

Lets Claude (Claude Desktop / Claude Code) operate the **VOCALOID6 Editor** on Windows and write projects for
**VOCALOID3, 4, 5 and 6**: melodies and lyrics in English, Japanese, Chinese, Korean and Spanish, any installed
voicebank (VOCALOID:AI banks and classic VOCALOID3/4/5 banks), pitch and expression curves, playback and
WAV/MIDI export.

| Part | What it does |
|---|---|
| Project tools (`.vpr`) | Read and edit VOCALOID5/6 projects directly. Every edit tool takes an optional `path`: with it the file is edited (VOCALOID6 may be closed); without it the project open in VOCALOID6 is edited live. |
| Live tools (UI Automation) | Open, save, reload, play, stop, export WAV/MIDI, import MIDI in the running editor through the Windows accessibility API. |
| `export_vsqx` | Writes `.vsqx` for the VOCALOID3 (vsq3) and VOCALOID4 (vsq4) editors, checked against the schemas Yamaha ships. |

## How it works (and why there is no plugin)

VOCALOID6 has no plugin system, and its licence forbids reverse engineering it, so nothing here touches its code:

- The `.vpr` format was learned from projects VOCALOID6 itself saved; `.vsqx` follows `vsq3.xsd` / `vsq4.xsd`
  from the editor folder.
- The live tools click VOCALOID6's menus and dialogs through **Windows UI Automation**, the same interface screen
  readers use. They never send keystrokes, so they cannot type into another window.
- A **live edit** saves the project in VOCALOID6 (keeping anything you changed by hand), edits the `.vpr`, then
  reloads it with *File > Revert*. Each call is one step of this server's own `undo` / `redo` (VOCALOID6's undo
  history restarts after a reload). Expect a few seconds per live edit.
- **Pronunciation is VOCALOID6's own**: new notes carry a placeholder phoneme and VOCALOID6 works out the real
  one from the lyric when it loads the project. Pass `phoneme` only to override it (the note is then protected).

Every selector the live tools use lives in one table (`SELECTORS` in `src/vocaloid6_mcp/ui.py`); `self_check`
reports which still match after a VOCALOID6 update. The project tools do not depend on the UI at all.

## Requirements

- Windows with VOCALOID6 Editor (tested with 6.13; default install `C:\Program Files\VOCALOID6\Editor`)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or pip)
- Voicebanks: VOCALOID6 AI banks and VOCALOID3/4/5 banks that VOCALOID6 can load. VOCALOID2 is not supported.

## Install

```bash
git clone <this repo> vocaloid6-mcp
cd vocaloid6-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

The `kanji` extra installs `pykakasi`, which turns Japanese kanji lyrics into hiragana.

### Register with Claude

**Claude Code**

```bash
claude mcp add vocaloid6 -- "C:\path\to\vocaloid6-mcp\.venv\Scripts\vocaloid6-mcp.exe"
```

**Claude Desktop**: edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vocaloid6": {
      "command": "C:\\path\\to\\vocaloid6-mcp\\.venv\\Scripts\\vocaloid6-mcp.exe"
    }
  }
}
```

Optional environment variable: `VOCALOID6_EXE` (path to `VOCALOID6.exe`). Optionally copy the `skill` folder into
your Claude skills folder (e.g. `.claude/skills/vocaloid6/`). Its `scripts/` are the song tools the skill uses for
songs over a backing track: `analyze_backing.py` (tempo, beat 1, key, chords per bar, chord loop), `check8.py` (8-bar
click + scale check), `assemble.py` and `mix.py` (stem placement and vocal mix). They are not part of the server and
need their own Python with `librosa` and `soundfile`, plus ffmpeg on PATH:

```bash
python -m venv %LOCALAPPDATA%\song-analysisenv
%LOCALAPPDATA%\song-analysisenv\Scripts\pip install librosa soundfile
```

## Usage

Ask Claude things like:

- "Is VOCALOID6 ready?" → `vocaloid_status`
- "Make a new song with an AI voicebank at 128 BPM and sing さくら さくら on A4 A4 B4."
- "Add a track for my English voicebank and sing 'hel-lo world' as quarter notes from C4."
- "Export a WAV to my desktop."

Basics: 480 ticks = one quarter note; pitch `C4` = 60; part positions are absolute, note positions are relative to
their part; track, part and note numbers count from 0.

### Lyrics

| Language | One note gets | Example |
|---|---|---|
| Japanese | one mora; ー becomes a `-` note that holds the vowel | `きゃりーぱみゅぱみゅ` → きゃ り - ぱ みゅ ぱ みゅ |
| English / Spanish | one syllable, in VOCALOID's form `hel-` + `lo` | `Hel-lo, beau-ti-ful world` → hel- lo beau- ti- ful world |
| Chinese | one hanzi, or one pinyin syllable | `我爱你` → 我 爱 你 |
| Korean | one syllable block | `사랑해` → 사 랑 해 |

English pitfalls VOCALOID6 shows: a word of several syllables on one note (`hello`) sings as `u:`, so hyphenate it
(the tools warn); a `-` hold note outside Japanese also sings `u:`, so give the hold note the vowel as its
`phoneme`.

### Voicebanks and eras

| Era | Banks | Track type | Project format |
|---|---|---|---|
| VOCALOID6 | VOCALOID:AI banks (several languages each) | VOCALOID:AI | `.vpr` |
| VOCALOID5 | V5 banks | VOCALOID | `.vpr` (the server writes file version 5.0.0) |
| VOCALOID4 / 3 | V4 / V3 banks | VOCALOID | `.vpr`, or `.vsqx` via `export_vsqx` |

`list_voicebanks` reads the registry (`HKLM\SOFTWARE\VOCALOID3..6`). AI banks report their languages; for classic
banks the language is guessed from the bank name (`language_source: "name"`).

### Tool groups

- **App**: `vocaloid_status`, `launch_vocaloid`, `close_vocaloid`, `self_check`
- **Project**: `new_project`, `open_project`, `save_project`, `reload_project`, `get_project`, `undo`, `redo`
- **Tempo**: `set_tempo`, `remove_tempo`, `set_time_signature`
- **Voicebanks**: `list_voicebanks`, `get_voicebank`, `list_styles`
- **Tracks / parts**: `add_track`, `edit_track`, `remove_track`, `add_part`, `edit_part`, `remove_part`, `fit_part`
- **Notes / lyrics**: `list_notes`, `add_notes`, `edit_notes`, `delete_notes`, `assign_lyrics`, `add_melody`
  (e.g. `A4:1 A4:1 B4:2 r:1`)
- **Curves**: `set_curve`, `get_curve`, `clear_curve` (dynamics, pitchBend, pitchBendSens, breathiness, brightness,
  clearness, portamento, growl, xSynth, character, air, exciter)
- **Playback / export**: `play`, `stop`, `export_wav` (`tracks=[...]` renders stems: only those tracks, mute/solo
  restored afterwards), `export_midi`, `import_midi`, `export_vsqx`
- **Utilities**: `note_to_midi`, `midi_to_note`, `beats_to_ticks`, `ticks_to_beats`, `split_lyrics`

## Safety

- `open_project`, `new_project(open_in_vocaloid=true)` and `close_vocaloid` refuse to discard unsaved changes in
  VOCALOID6 unless `force=true`.
- Live edits save the open project first, then snapshot the file (last 50 per project, in
  `%LOCALAPPDATA%\vocaloid6-mcp\history`) so `undo` can restore it.
- `.vpr` files are written atomically, and every zip entry and field the server does not know is kept.

## Tests

```bash
uv pip install -e ".[kanji,test]"
.venv\Scripts\python tests\e2e_test.py          # file, voicebank, VSQX and utility tools over stdio
.venv\Scripts\python tests\e2e_test.py --live   # also drives the running VOCALOID6 (needs a voicebank)
```

The live test opens its own temporary project with `force=false`, so it stops if VOCALOID6 has unsaved changes.
With `lxml` installed the VSQX output is validated against Yamaha's `vsq3.xsd` / `vsq4.xsd`.

## Limits

- Live tools bring VOCALOID6's window to the front while they open its menus. Keys you type at that moment go to
  VOCALOID6 (a shortcut can open a dialog that blocks the next step: a leftover Open/Save dialog or its "File not
  found" box is closed automatically, other dialogs are reported). Leave the
  keyboard alone while a live tool runs, and especially during `tests/e2e_test.py --live`.
- Live tools need VOCALOID6's window (not minimised to a dialog-blocked state); a VOCALOID6 update can move menus
  (run `self_check`). The `.vpr` tools keep working regardless.
- Only VOCALOID6 6.13 with VOCALOID4 and VOCALOID6 AI banks was tested. VOCALOID3 and VOCALOID5 banks are found by
  the same registry scan but were not available to test.
- VOCALOID6 ignores the VSQX pre-measure, so a `.vsqx` it opens starts one bar later than in VOCALOID3/4.
- Style presets can be listed but are applied in VOCALOID6 itself.

## License

MIT, see [LICENSE](LICENSE). Not affiliated with Yamaha. VOCALOID is a trademark of Yamaha Corporation.
