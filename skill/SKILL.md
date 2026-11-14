---
name: vocaloid6
description: Make good-sounding sung vocals in VOCALOID6 (and VOCALOID3/4/5 projects) through the vocaloid6 MCP server - lyrics in English, Japanese, Chinese, Korean, Spanish, melody, singer choice across AI and classic voicebanks, timing, pitch, expression curves, vibrato, export and report. Use for any VOCALOID / VOCALOID6 / .vpr / .vsqx task. / vocaloid6 MCP で VOCALOID6 の歌声を作るための手順とルール。
---

# VOCALOID6 vocals / VOCALOID6 歌声制作

Follow these rules every time. Defaults are starting points; the user's ear wins.
If a `voicebanks.md` file sits next to this one, read it first: it lists the user's singers, their languages,
comfortable registers and per-bank findings.

Basics: 480 ticks = quarter note (1920 = 4/4 bar, 240 = 8th, 120 = 16th). Part positions are absolute, note
positions relative to the part. Pitch: MIDI number or name, C4 = 60. Track, part and note numbers count from 0.
Never pass `force=true` unless the user agreed to lose unsaved work.

## 1. Workflow (always in this order) / 手順

1. **Start.** `vocaloid_status`. Launch if needed. Before live edits, `get_project` and check `path` is the project
   you expect. Live tools need no dialog open in VOCALOID6 (`open_dialogs` must be empty).
2. **Source.** Never guess or "remember" a melody. Use the user's melody (their notes/MIDI are the source of truth:
   keep BPM, pitches and lengths exactly), the user's own song, or a public-domain tune you can cite. No source:
   ask. Write the source in the report.
3. **Lyrics first, approval before building.** Show a table per phrase: source lyric | lyric per note (one cell per
   note) | note count. Counts must match the melody's sounding notes. Wait for the user's OK.
4. **Singer.** `list_voicebanks`. Prefer an AI bank (`kind: "ai"`) that lists the lyric language; classic banks
   sing one language only (their `languages` is guessed from the name: check it). Say which you picked and why.
5. **Build in stages, check after each:**
   a. `new_project(path, bpm, numer, denom)` (only if the user agrees) → `add_track(voice, language)` →
      `add_melody(track, 0, "A4:1 A4:1 B4:2 r:1 ...", lyrics=...)` → `fit_part`.
   b. Open it (`open_project`), then `list_notes`: every note must have a phoneme, none `u:` unless the lyric is
      "oo". Fix lyrics before any expression work.
   c. Expression (section 4), then listen (`export_wav`) and report.
6. **Prefer file edits for big builds.** Building with `path=` is fast (no reload per call); open the file in
   VOCALOID6 at the end, or call `reload_project` if it is already open there. Use live edits (no `path`) for small
   changes to what the user has open.

## 2. Lyrics rules / 歌詞

- Japanese: one mora per note (きゃ is one note, っ its own note). ー or a melisma note → lyric `-` (holds the vowel).
- English/Spanish: one syllable per note, VOCALOID form: `hel-` + `lo`, `beau-` + `ti-` + `ful`. Write hyphens in
  the text (`hel-lo`) and the tools convert. A multi-syllable word on ONE note sings `u:` (the tools warn). Single
  syllable words stay whole (`love`, `world`).
- English melisma (one syllable over several notes): a `-` note sings `u:`. Instead give the extra notes the
  vowel as phoneme with `edit_notes` (e.g. `{"index": 5, "lyric": "-", "phoneme": "@U"}`), copying the vowel from
  the previous note's phoneme in `list_notes`.
- Chinese: one hanzi or one pinyin syllable per note. Korean: one hangul syllable per note.
- AI voices sing several languages: set `language` on `add_track` (the part's language) or per note.
- Phonemes are VOCALOID6's: they read `null` until VOCALOID6 has loaded the project. Override only to fix a word
  (the note becomes protected; `phoneme: ""` gives it back).

## 3. Timing / タイミング

- Keep the user's note lengths. Leave rests as gaps (`r:1` in `add_melody`); do not stretch notes over them.
- Consonants start before the beat automatically; do not shift notes early to compensate.
- Very short notes (< 120 ticks) on consonant-heavy syllables blur: merge or lengthen with the user's OK.

## 4. Expression / 表情

Work in this order and change one thing at a time; export and compare.

| Goal | Tool | Typical values |
|---|---|---|
| Phrase loudness shape | `set_curve dynamics` | 64 neutral; 50 → 80 → 60 over a phrase; 0..127 |
| Breathy intro / outro | `set_curve breathiness` | 0 → 30 at phrase ends |
| Brighter / darker | `brightness` (classic) or `character` | brightness 64 neutral; character -64..63, 0 neutral |
| Scoops, falls | `pitchBend` with `pitchBendSens` | PBS 2 = ±2 semitones over ±8192; keep bends short (60-120 ticks) |
| Long-note vibrato | `edit_notes vibrato` | type 1, duration = last 40-60 % of the note, depth ~64, rate ~50 |
| AI air / exciter | `air`, `exciter` (AI tracks) | small amounts (10-30) |

Curves are per part; positions are relative to the part; `set_curve` replaces the span between its first and last
point. Read back with `get_curve`.

## 5. Export & report / 書き出しと報告

- `export_wav(output)` renders the main mix (seconds to minutes). `export_midi` for a DAW. `export_vsqx(version=4)`
  for the VOCALOID4 editor (classic tracks only; AI tracks are skipped).
- Report: source of the melody, singer and language, lyric table, what expression you added, the files written,
  and anything not checked by ear.

## 6. Recovery / 復旧

- A live edit failed halfway: `get_project`, then `undo` (this server keeps file snapshots of every live edit).
- "Cannot tell where ... is saved": call `open_project(path)` once so the server learns the path.
- Live tools say a menu or button is missing: run `self_check` (a VOCALOID6 update may have renamed it) and fall
  back to file edits with `path=` plus `reload_project`.
- "voice banks replaced" in a result: VOCALOID6 swapped a singer it does not have; check `get_project` voices.
