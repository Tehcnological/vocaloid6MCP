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
   **Tell the user, before the first live tool:** "While I work in VOCALOID6, please don't type or click: it comes
   to the front when I open its menus, and your keys would go to it." Say it again before long live runs
   (several edits in a row, `export_wav`). Prefer file edits (`path=`) when the user is busy on the computer.
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
- Imported UST/MIDI: a short rest inside a word may be a dropped melisma (the vowel moving to a new pitch), not a
  pause. Compare with the original recording. Fix it with a `-` note at the new pitch filling the gap; closing the
  gap by lengthening the note sounds wrong. A melisma can also dip below the note: check, do not assume "up".
- UST → MIDI keeps only notes and lyrics: the UST's own tuning (VBR vibrato, PBS/PBW portamento) is lost. Its VBR
  (length %, cycle ms, depth cents, fade-in/out %) ports well as a pitchBend sine on the AI track; its portamento
  does not (it doubles the AI's own transitions).
- Long held notes at phrase ends: singers usually release them after 55-70 % and breathe. A synth that holds every
  long note to full length sounds strained; shorten those notes (compare with the original if there is one).
- Timing tool (AI tracks): `edit_notes timing` = ticks from the note start for each phoneme's start, then the sound
  end (null = automatic), e.g. `[null, 40]` = vowel 40 ticks late, `[-40]` = consonant 40 ticks early. Use it by
  hand on single notes; copied wholesale from a recording it makes fast lines choppy (silence before an unvoiced
  consonant such as s/t/k is that consonant, not a break).

## 4. Expression / 表情

Work in this order and change one thing at a time; export and compare.

| Goal | Tool | Typical values |
|---|---|---|
| Phrase loudness shape | `set_curve dynamics` | 64 neutral; 50 → 80 → 60 over a phrase; 0..127 |
| Breathy intro / outro | `set_curve breathiness` | 0 → 30 at phrase ends |
| Brighter / darker | `brightness` (classic) or `character` | brightness 64 neutral; character -64..63, 0 neutral |
| Scoops, falls | `pitchBend` with `pitchBendSens` | PBS 2 = ±2 semitones over ±8192; keep bends short (60-120 ticks) |
| Long-note vibrato | `edit_notes vibrato`. AI tracks: no type, just duration + depth + rate (duration 0 = nothing heard). `ai_exp` vibratoLeading/FollowingDepth only scale the AI's own auto-vibrato (inaudible on short notes) | classic: type 1, last 40-60 % of the note, depth ~64, rate ~50. AI: duration ~half the note, depth ~110, rate ~100 as a start. Notes under ~0.5 s are too short for audible vibrato |
| AI tracks | `expression` (0..100, part default 50), `air` (-100..100), `character` | AI tracks accept only dynamics, pitchBend, pitchBendSens and these three; breathiness, brightness, exciter etc. are classic only |

Curves are per part; positions are relative to the part; `set_curve` replaces the span between its first and last
point. Read back with `get_curve`.

AI tracks already move pitch and loudness on their own (they scoop into notes from below and droop at the end).
Copying a human singer's pitch or loudness curve note by note on top of that sounds worse, not more human: prefer
song-wide changes (note releases, Expression contrast between verse and chorus, vibrato on held parts, EQ, mix
balance) and hand-tune only the few notes the user points at. Render a stem and measure before and after when a
change is meant to fix something.

## 5. Export & report / 書き出しと報告

- `export_wav(output)` renders the main mix (seconds to minutes). `export_wav(output, tracks=[0, 1])` renders only
  those tracks (a stem; the others are muted for the export and mute/solo are restored). `bit_depth=24` for a
  file going to a DAW (VOCALOID6 remembers the choice). `export_midi` for a DAW.
- Mix check over a finished backing track: a synth lead easily sits several dB above where the original singer sat;
  compare vocal-vs-backing level per section with the original (separate it with a source-separation tool such as
  Demucs) and turn the vocal tracks down before reaching for more tuning. Check the true peak stays below 0 dBFS.
  `export_vsqx(version=4)` for the VOCALOID4 editor (classic tracks only; AI tracks are skipped).
- Live tools close a leftover Open/Save dialog (and its "File not found" box) by themselves; other dialogs stop them.
- Report: source of the melody, singer and language, lyric table, what expression you added, the files written,
  and anything not checked by ear.

## 5b. Songs over a backing track: the song analysis tool / 伴奏に合わせた曲

**Never guess tempo, beat, key or chords; measure them, and let the user confirm by ear before writing a note.**
Beat trackers can lock onto a related tempo (2:1 or 3:2): vocals written on a wrong grid never sit in time, however
good the melody is.

Setup once (a separate Python, not part of the MCP server):
`python -m venv %LOCALAPPDATA%\song-analysis\venv` then
`%LOCALAPPDATA%\song-analysis\venv\Scripts\pip install librosa soundfile`. Run the scripts with that python
(`PY` below); ffmpeg must be on PATH.

1. `PY scripts/analyze_backing.py TRACK.wav [--speed 1.25] --json facts.json`: tempo fitted to a constant grid (and
   how far the real beats stray from it: "steady" means a fixed-tempo editor can follow), beat 1, key with
   confidence (r above ~0.75 is clear), tuning offset, chord per bar, the repeating chord loop, loudness per bar.
   `--speed` gives the numbers for the track sped up with pitch kept (`ffmpeg -af atempo=1.25`).
   `--table *.wav` makes a tempo/key table when the user is choosing a backing.
2. `PY scripts/check8.py TRACK.wav facts.json check.wav [start_bar]`: 8 bars of backing + click (high = beat 1) + the
   key's scale. Send it; the user confirms "in time and in tune" in seconds. Fix the analysis before going on.
3. Put song bar 0 on a measured bar line (sections start where the chord loop starts) and use only chord tones or
   short passing steps for long notes. Build **one chorus first** (8 bars, 2 bars of lead-in) and iterate on it;
   write the rest only once the user likes the hook.
4. Stems: `export_wav(output, tracks=[...])` per voice group (lead, harmony, answer, ...). Mix with
   `PY scripts/assemble.py` (lay takes on the song timeline, `file@offset_s`) and `PY scripts/mix.py backing lead
   harmony out bpm [answer]` (reverb, 1/8-note echo, harmony width, backing EQ dip and ducking), then
   `ffmpeg -af loudnorm=I=-14:TP=-1.0`. Per-stem ffmpeg filters before mixing:
   lead `highpass=f=120,deesser=i=0.4,acompressor=threshold=-22dB:ratio=2.5:attack=8:release=120:makeup=3,highshelf=f=10000:g=2`;
   harmony `highpass=f=200,acompressor=threshold=-24dB:ratio=3:attack=8:release=120:makeup=3`;
   answer voice `highpass=f=250,acompressor=threshold=-20dB:ratio=3:attack=3:release=80:makeup=3,highshelf=f=6000:g=2`.
   Lead vocals end up about +5 dB (RMS) over the backing; harmony about 12 dB under the lead.
5. Clarity: keep the verse to one voice (same-voice harmony in the lead's range blurs the words), keep words that
   start with a vowel after "-ng" off the bottom of the range, and keep breathiness low (~10) on lines that must read.

## 6. Recovery / 復旧

- A live edit failed halfway: `get_project`, then `undo` (this server keeps file snapshots of every live edit).
- "Cannot tell where ... is saved": call `open_project(path)` once so the server learns the path.
- Live tools say a menu or button is missing: run `self_check` (a VOCALOID6 update may have renamed it) and fall
  back to file edits with `path=` plus `reload_project`.
- "voice banks replaced" in a result: VOCALOID6 swapped a singer it does not have; check `get_project` voices.

## 7. TuneLab (optional) / TuneLab（任意）

Skip this section unless the user wants TuneLab. Everything above works without it.

**Availability.** TuneLab sings VOCALOID voices only with a VOCALOID6 voice extension for TuneLab, installed
separately. There is no public source for one: the user may need to source or make their own. Do not suggest where
to get one, and do not ask the user where to get one. Check with `vocaloid_status` (`tunelab.installed`) and
`self_check` (`tunelab.vocaloid6_engine`, `tunelab.voices`). If either is missing, stay on the VOCALOID6 workflow.
/ TuneLab で VOCALOID の声を使うには別途 TuneLab 用の VOCALOID6 音声拡張が必要です（公開されている入手先はなく、
ユーザーが用意する必要があるかもしれません）。入手先を案内したり尋ねたりせず、ない場合は VOCALOID6 だけで作業します。

**Which program does what.** VOCALOID6: drafting (sections 1 to 4), the Timing tool, style EQ/compressor, Korean and
Spanish on AI voices, `.vsqx`. TuneLab: pitch tuning, vibrato, expression/air/character curves and styles, in English
and Japanese on every voice. Chinese on AI voices works for some voices only: check the render.

**Handoff (one-way).**
1. Draft in VOCALOID6, then `export_tunelab(output="....tlp", path=...)`. Read `dropped` and `warnings` and tell the
   user what did not carry over. Never re-export over a `.tlp` that has been tuned: export later tracks with
   `tracks=[...]` to a new file and import them in TuneLab.
2. With the user's OK, open the `.tlp` in TuneLab and edit it through TuneLab's own command line or MCP server
   (`TuneLab.Cli.exe`). Run its `--help` and `docs script-api` at the start of each session instead of relying on
   memory: its commands change between versions.

**Tuning rules in TuneLab.** Use TuneLab vibrato objects for vibrato. The per-note pitch settings take effect only
when the part's `Mode(PIT/PIT+/Snap)` is not 2. Voice ids differ per voice; read them with TuneLab's `source list`.

**Checking.** Export a `.tlp` copy, render it with a headless TuneLab into a temporary folder, and analyse it with
the song-analysis scripts (section 5b). Never render, export audio from or save the user's open TuneLab session
unless asked. Final mix: per-track stems from TuneLab and VOCALOID6 plus the backing, mixed with
`skill/scripts/mix.py`.
