# AGENTS.md

Notes for AI agents: those that use this MCP server from any client, and those that work on this repository.
Claude users can install [skill/](skill/) as a skill instead; the content is the same.

## Using the server

- Call `vocaloid_status` first, then `usage_guide` once before a song task. `usage_guide` returns
  [skill/SKILL.md](skill/SKILL.md): the full workflow and quality rules. It is plain Markdown (the block between
  the first two `---` lines is Claude skill metadata and can be ignored), so it can also be pasted into a client's
  project rules or custom instructions.
- Essentials, also sent as the server's MCP instructions:
  - 480 ticks = quarter note (1920 = one 4/4 bar). Part positions are absolute, note positions relative to their
    part. Pitch is a MIDI number or a name (`C4` = 60). Track, part and note indexes count from 0.
  - Project tools take an optional `path`: with a `.vpr` path they edit that file (VOCALOID6 may be closed); without
    it they edit the project open in VOCALOID6.
  - Lyrics: Japanese one mora per note; English and Spanish one syllable per note, hyphenated (`hel-lo`); Chinese and
    Korean one syllable per note.
  - Live tools bring VOCALOID6 to the front: ask the user not to type or click until they finish, or use `path=`.
- The song scripts in `skill/scripts/` (backing-track analysis, stem mix) are separate Python tools, not server
  tools; see the README.

## Working on this repository

- `src/vocaloid6_mcp/server.py` defines every tool. Descriptions and errors are English, then Japanese.
  `vpr.py` reads and writes `.vpr`, `ui.py` holds every UI Automation selector (`SELECTORS`), `schema.py` simplifies
  the advertised tool schemas for strict clients.
- Tests: `.venv\Scripts\python tests\e2e_test.py` (file mode) and `.venv\Scripts\python tests\schema_check.py`.
  Never run `e2e_test.py --live` without the user's consent: it drives the running VOCALOID6.
- After changing a tool signature, run `schema_check.py`; it must report 0 errors.
- Single-file build: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`.
- Keep the repository generic: no personal names, song titles or local paths in code, docs or tests.
