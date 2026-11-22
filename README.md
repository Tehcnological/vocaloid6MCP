# VOCALOID6 MCP

[日本語版 README はこちら](README.ja.md)

Lets AI assistants in any MCP client (Claude, Cursor, VS Code, Codex, Gemini CLI and others) operate the **VOCALOID6 Editor** on Windows and write projects for
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
- Voicebanks: VOCALOID6 AI banks and VOCALOID3/4/5 banks that VOCALOID6 can load. VOCALOID2 is not supported.
- Any MCP client that runs local (stdio) servers: Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, Cline,
  Continue, Codex CLI, Gemini CLI, LM Studio and others.

## Install

Pick one way to get the server. Both give your MCP client a command to start.

**A. Single file, no Python needed.** Download `vocaloid6-mcp.exe` from this repository's **Releases** page and put
it in a folder of your choice, e.g. `C:\Tools\`. The command is the path to the file: `C:\Tools\vocaloid6-mcp.exe`.

- Optional check that the download is intact: `Get-FileHash C:\Tools\vocaloid6-mcp.exe` in PowerShell must print
  the same value as `SHA256SUMS.txt` on the release.
- The exe is not code-signed. If Windows blocks it: right-click the file, Properties, tick **Unblock**, OK.
- Japanese kanji-to-kana support (`pykakasi`) is built in.

**B. uvx, always the latest code.** Needs [uv](https://docs.astral.sh/uv/). Nothing to clone; uv downloads and caches
the server the first time the client starts it. The command is `uvx` with these arguments:

```text
--from "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP" vocaloid6-mcp
```

**C. From a clone (to change the code).** Needs Python 3.11+ and uv:

```bash
git clone https://github.com/Tehcnological/vocaloid6MCP vocaloid6-mcp
```

```bash
cd vocaloid6-mcp
uv venv -p 3.11
uv pip install -e ".[kanji]"
```

The command is then `C:\path\to\vocaloid6-mcp\.venv\Scripts\vocaloid6-mcp.exe`.

### Register with your MCP client

The examples use route A (`C:\Tools\vocaloid6-mcp.exe`). For route B, replace the command line with `"command":
"uvx"` plus the `args` shown under each client. Restart the client (or reload its MCP servers) after editing a config
file. In JSON every `\` in a path is written `\\`.

**Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI, LM Studio** all use the same JSON shape:

```json
{
  "mcpServers": {
    "vocaloid6": {
      "command": "C:\\Tools\\vocaloid6-mcp.exe",
      "args": []
    }
  }
}
```

Route B: `"command": "uvx", "args": ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`.

| Client | Config file (merge the `vocaloid6` entry into `mcpServers`) |
|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` (Settings, Developer, Edit Config). The Microsoft Store version may read `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` instead. |
| Cursor | `%USERPROFILE%\.cursor\mcp.json` (all projects) or `.cursor\mcp.json` (one project). Add `"type": "stdio"` to the entry. |
| Windsurf (now Devin Desktop) | `%APPDATA%\devin\mcp_config.json`; older Windsurf versions: `%USERPROFILE%\.codeium\windsurf\mcp_config.json` |
| Cline | Cline panel, MCP Servers, Configure, **Configure MCP Servers** opens `cline_mcp_settings.json` |
| Gemini CLI | `%USERPROFILE%\.gemini\settings.json`, or in one step: `gemini mcp add -s user vocaloid6 "C:\Tools\vocaloid6-mcp.exe"` |
| LM Studio (0.3.17+) | `%USERPROFILE%\.lmstudio\mcp.json` (Program tab, Install, Edit mcp.json) |

**Claude Code** (one command, no file to edit):

```bash
claude mcp add --scope user vocaloid6 -- "C:\Tools\vocaloid6-mcp.exe"
```

```bash
claude mcp add --scope user vocaloid6 -- uvx --from "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP" vocaloid6-mcp
```

**VS Code (GitHub Copilot, agent mode)**: Command Palette, **MCP: Open User Configuration** (or `.vscode\mcp.json` in
a workspace). The top-level key is `servers`, not `mcpServers`:

```json
{
  "servers": {
    "vocaloid6": {
      "type": "stdio",
      "command": "C:\\Tools\\vocaloid6-mcp.exe"
    }
  }
}
```

Copilot's newer shared files, `%USERPROFILE%\.copilot\mcp-config.json` and `.mcp.json` in a workspace, take the
`mcpServers` shape above instead.

**Continue** (MCP works in agent mode only): create `.continue\mcpServers\vocaloid6.yaml` in your workspace:

```yaml
name: VOCALOID6
version: 0.0.1
schema: v1
mcpServers:
  - name: vocaloid6
    type: stdio
    command: 'C:\Tools\vocaloid6-mcp.exe'
```

Route B: `command: uvx` and `args: ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`.

**Codex CLI**: add to `%USERPROFILE%\.codex\config.toml` (in TOML, single quotes keep `\` as is):

```toml
[mcp_servers.vocaloid6]
command = 'C:\Tools\vocaloid6-mcp.exe'
tool_timeout_sec = 300  # live edits and WAV export can take longer than the 60 s default
```

Route B: `command = "uvx"` and `args = ["--from", "vocaloid6-mcp[kanji] @ git+https://github.com/Tehcnological/vocaloid6MCP", "vocaloid6-mcp"]`.
Or in one step: `codex mcp add vocaloid6 -- "C:\Tools\vocaloid6-mcp.exe"` (then add `tool_timeout_sec` by hand).

Optional environment variable: `VOCALOID6_EXE` (path to `VOCALOID6.exe`). Add it as `"env": {"VOCALOID6_EXE":
"D:\\Apps\\VOCALOID6\\Editor\\VOCALOID6.exe"}` in JSON, or `env = { VOCALOID6_EXE = 'D:\Apps\...' }` in TOML.

### Usage rules in every client

The server sends its essential rules (ticks, indexes, lyrics, live-tool safety) as MCP instructions, and the
`usage_guide` tool returns the full workflow and quality guide ([skill/SKILL.md](skill/SKILL.md)). Some clients do
not pass server instructions to the model; if the assistant skips steps, ask it to "call usage_guide first". Claude
users can install the `skill` folder as a skill instead (e.g. `.claude/skills/vocaloid6/`). See
[AGENTS.md](AGENTS.md) for agents and clients without skill support.

The server has 45 tools. VS Code allows 128 tools per request and Cursor used to send only the first 40, so if a
client warns about too many tools, turn off the ones you do not need (VS Code: the tools picker in Chat; Codex:
`enabled_tools`; Gemini CLI: `includeTools`).

### Song scripts (optional)

The skill's `scripts/` are the song tools for songs over a backing track: `analyze_backing.py` (tempo, beat 1, key,
chords per bar, chord loop), `check8.py` (8-bar click + scale check), `assemble.py` and `mix.py` (stem placement and
vocal mix). They are not part of the server and need their own Python with `librosa` and `soundfile`, plus ffmpeg on
PATH:

```bash
python -m venv %LOCALAPPDATA%\song-analysisenv
```

```bash
%LOCALAPPDATA%\song-analysisenv\Scripts\pip install librosa soundfile
```

### Build the single file yourself

```bash
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

It needs uv and writes `dist\vocaloid6-mcp.exe` (PyInstaller, about 20 MB), `SHA256SUMS.txt` and the list of packages
inside. Pushing a tag such as `v0.4.0` runs the same script on GitHub Actions and attaches the files to a draft
release, which you publish by hand.

## Usage

Ask your assistant things like:

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

### TuneLab (optional)

`export_tunelab` copies a project to a [TuneLab](https://github.com/LiuYunPlayer/TuneLab) project (`.tlp`) for
tuning there: notes, lyrics, phonemes, voices, curves, styles and vibrato, with a report of anything left behind.
TuneLab sings VOCALOID voices only with a VOCALOID6 voice extension for TuneLab, installed separately; none is
publicly available, so you may need to source or make your own. Without one, nothing changes: every other tool
works as before. `vocaloid_status` and `self_check` report what TuneLab has.

### Tool groups

- **App**: `vocaloid_status`, `launch_vocaloid`, `close_vocaloid`, `self_check`
- **Project**: `new_project`, `open_project`, `save_project`, `reload_project`, `get_project`, `undo`, `redo`
- **Tempo**: `set_tempo`, `remove_tempo`, `set_time_signature`
- **Voicebanks**: `list_voicebanks`, `get_voicebank`, `list_styles`
- **Tracks / parts**: `add_track`, `edit_track`, `remove_track`, `add_part`, `edit_part`, `remove_part`, `fit_part`
- **Notes / lyrics**: `list_notes`, `add_notes`, `edit_notes` (also manual vibrato, AI note settings and the
  Timing tool: `timing` = phoneme starts and sound end in ticks from the note start), `delete_notes`,
  `assign_lyrics`, `add_melody` (e.g. `A4:1 A4:1 B4:2 r:1`)
- **Curves**: `set_curve`, `get_curve`, `clear_curve` (AI tracks: dynamics, pitchBend, pitchBendSens,
  expression, air, character; classic tracks: dynamics, pitchBend, pitchBendSens, breathiness, brightness, clearness,
  portamento, growl, xSynth, character, air, exciter)
- **Playback / export**: `play`, `stop`, `export_wav` (`tracks=[...]` renders stems: only those tracks, mute/solo
  restored afterwards; `bit_depth=24` picks the mixdown bit depth), `export_midi`, `import_midi`, `export_vsqx`,
  `export_tunelab`
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
.venv\Scripts\python tests\schema_check.py      # every tool schema against strict client rules
.venv\Scripts\python tests\tlp_test.py          # TuneLab export and detection (no TuneLab needed)
```

When TuneLab is installed, `e2e_test.py` also checks that a headless TuneLab opens the exported `.tlp`; set
`TUNELAB_CLI` to a missing path to test as if TuneLab were absent.

`schema_check.py` is a plain MCP client that lists the tools and checks each input schema against the strictest
documented rules of Gemini, Codex, VS Code and Cursor (rules listed at the top of the file). Set
`MCP_SERVER_EXE=dist\vocaloid6-mcp.exe` to run `e2e_test.py` against the single-file build, or pass the exe to
`schema_check.py`.

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

The single-file `.exe` on the Releases page also contains pykakasi, which is GPL-3.0-or-later, so the `.exe` as a whole is distributed under GPL-3.0-or-later. Each release carries `EXE-LICENSE.md` and `GPL-3.0.txt`. The source in this repository stays MIT.
