"""VOCALOID6 MCP server (stdio). Every tool description and error is English, then Japanese."""

import functools
import os

import pydantic_core
from .schema import FastMCP
from pydantic import BaseModel, Field

from . import __version__, app, live, music, ui, voicebanks, vpr, vsqx
from . import lyrics as lyric_text
from .errors import VocaloidError

INSTRUCTIONS = """\
Control VOCALOID6 and write VOCALOID3/4/5/6 projects, in English or Japanese.
1. Call vocaloid_status first. Live tools drive the running VOCALOID6 editor through Windows UI Automation.
   Project tools take an optional `path`: with a .vpr path they edit that file directly (VOCALOID6 may be closed);
   without it they edit the project open in VOCALOID6 (save there -> edit the file -> reload, one undo step each).
2. Time is in ticks: 480 = quarter note (1920 = one 4/4 bar). Part positions are absolute; note positions are
   relative to their part. Pitch: MIDI number or name, C4 = 60.
3. Indexes count from 0: track, part (within its track), note (within its part, sorted by position).
4. Voicebanks: list_voicebanks. kind "ai" (VOCALOID6 AI banks: VOCALOID:AI tracks, several languages each) or
   "classic" (VOCALOID3/4/5 banks: VOCALOID tracks, one language each). add_track picks the right track type.
5. Lyrics: Japanese = one mora per note (ー becomes a "-" note that holds the vowel). English/Spanish = one
   syllable per note: hyphenate words ("hel-lo") and they become VOCALOID's form "hel-" + "lo". A multi-syllable
   word on one note, or a "-" hold note outside Japanese, sings as "u:" (hold: set the vowel as phoneme).
   Chinese = one hanzi or pinyin syllable per note; Korean = one syllable per note. VOCALOID6 works out the phonemes itself when it loads the project, so
   phonemes read back as null until then. Give `phoneme` only to override the pronunciation (it gets protected).
6. export_vsqx writes .vsqx for the VOCALOID3/4 editors (classic tracks only). VOCALOID2 is not supported.
7. Live tools bring VOCALOID6 to the front while they open its menus, so keys the user types then go to VOCALOID6.
   Before using live tools, ask the user not to type or click until you are done; prefer path= edits otherwise.
8. Before a song task, call usage_guide once for the full workflow and quality rules (skip it if the vocaloid6 skill is loaded).

VOCALOID6 を操作し、VOCALOID3/4/5/6 のプロジェクトを英語・日本語で作成します。
1. まず vocaloid_status を呼んでください。ライブ操作は Windows の UI オートメーションで VOCALOID6 エディターを操作します。
   プロジェクト系ツールは任意の `path` を取ります。.vpr のパスを渡すとそのファイルを直接編集し（VOCALOID6 は閉じたままで可）、
   省略すると VOCALOID6 で開いているプロジェクトを編集します（保存→ファイル編集→再読み込み。1回の呼び出しが1回の取り消し単位）。
2. 時間はティック単位：四分音符 = 480（4/4 の1小節 = 1920）。パート位置は絶対位置、音符位置はパート先頭からの相対値。音高は MIDI 番号か音名（C4 = 60）。
3. 番号は 0 から：track、part（トラック内）、note（パート内、位置順）。
4. 音源は list_voicebanks で確認。kind "ai"（VOCALOID6 の AI 音源：VOCALOID:AI トラック、複数言語）と
   "classic"（VOCALOID3/4/5 音源：VOCALOID トラック、1言語）。add_track が適切なトラック種別を選びます。
5. 歌詞：日本語は1音符1モーラ（「ー」は母音を伸ばす "-" 音符）。英語・スペイン語は1音符1音節で、hel-lo のように
   ハイフンで区切ると VOCALOID 形式の "hel-" + "lo" になります。複数音節の単語を1音符に置いたり、日本語以外で "-" の
   伸ばし音符を使うと "u:" になります（伸ばしは母音を phoneme に指定）。中国語は1音符1字（またはピンイン1音節）、韓国語は1音符1音節。発音記号は VOCALOID6 が
   読み込み時に自動で付けるため、それまでは null です。発音を変えたいときだけ `phoneme` を指定してください（保護されます）。
6. export_vsqx は VOCALOID3/4 用の .vsqx を書き出します（VOCALOID トラックのみ）。VOCALOID2 には対応していません。
7. ライブ操作はメニューを開く間 VOCALOID6 を前面に出すため、そのときのユーザーの入力は VOCALOID6 に届きます。
   ライブ操作の前に、終わるまでキーボードやマウスに触れないようユーザーに伝えてください。難しければ path= で編集してください。
8. 曲作りの前に usage_guide を一度呼び、手順と品質ルールの全文を読んでください（vocaloid6 スキルを読み込み済みなら不要）。
"""

mcp = FastMCP("vocaloid6", instructions=INSTRUCTIONS, log_level="WARNING")
mcp._mcp_server.version = __version__  # FastMCP would report the MCP SDK's version


def _tool():
    """mcp.tool() that turns unexpected exceptions into bilingual errors."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                r = fn(*args, **kwargs)
                # one JSON text block: FastMCP would send a list as one block per item (none when empty)
                return pydantic_core.to_json(r, fallback=str, indent=2).decode() if isinstance(r, list) else r
            except VocaloidError:
                raise
            except Exception as e:  # noqa: BLE001 - surface anything else in both languages
                raise VocaloidError(f"{type(e).__name__}: {e}", f"予期しないエラー {type(e).__name__}: {e}") from e
        return mcp.tool(structured_output=False)(wrapper)
    return deco


Pitch = int | str
_PITCH = "MIDI number or note name (C4 = 60). / MIDI 番号または音名（C4 = 60）"
_PATH = (".vpr file to edit directly; omit to edit the project open in VOCALOID6. / "
         "直接編集する .vpr ファイル。省略すると VOCALOID6 で開いているプロジェクトを編集")


class NoteIn(BaseModel):
    position: int = Field(description="Start tick, relative to the part. / パート先頭からの開始ティック")
    duration: int = Field(description="Length in ticks (480 = quarter note). / 長さ（ティック、480 = 四分音符）")
    tone: Pitch = Field(description=_PITCH)
    lyric: str = Field("a", description="Lyric. / 歌詞")
    phoneme: str | None = Field(None, description="Optional phoneme override, e.g. 'h @ l @U' (protected). / 発音記号の指定（任意、保護されます）")
    velocity: int = Field(64, description="Velocity 0..127: consonant length, VOCALOID tracks only. / ベロシティ 0〜127（子音の長さ、VOCALOID トラックのみ）")
    language: str | None = Field(None, description="ja/en/ko/es/zh (AI voices only). / 言語（AI 音源のみ）")


class Vibrato(BaseModel):
    type: int | None = Field(None, description="Vibrato type (0 = none, 1..), VOCALOID tracks only. / ビブラートの種類（0 = なし、VOCALOID トラックのみ）")
    duration: int | None = Field(None, description="Ticks at the end of the note that get vibrato; 0 = none heard. / 音符末尾のビブラートの長さ（ティック、0 = 効かない）")
    depth: int | None = Field(None, description="Depth 0..127. / 深さ 0〜127")
    rate: int | None = Field(None, description="Rate 0..127. / 速さ 0〜127")


class NoteEdit(BaseModel):
    index: int = Field(description="Note index in the part. / パート内の音符番号")
    position: int | None = Field(None, description="New start tick. / 新しい開始ティック")
    duration: int | None = Field(None, description="New length in ticks. / 新しい長さ")
    tone: Pitch | None = Field(None, description=_PITCH)
    lyric: str | None = Field(None, description="New lyric (pronunciation is recomputed). / 新しい歌詞（発音は再計算）")
    phoneme: str | None = Field(None, description="Phoneme override; '' gives it back to VOCALOID6. / 発音記号。'' で自動に戻す")
    velocity: int | None = Field(None, description="Velocity 0..127: consonant length, VOCALOID tracks only. / ベロシティ（子音の長さ、VOCALOID トラックのみ）")
    language: str | None = Field(None, description="ja/en/ko/es/zh (AI voices only). / 言語（AI 音源のみ）")
    vibrato: Vibrato | None = Field(
        None, description="Manual vibrato. VOCALOID tracks: type + duration + depth + rate. VOCALOID:AI tracks: duration "
        "(e.g. half the note) + depth + rate, no type; this is the audible long-note vibrato. "
        "/ 手動ビブラート。VOCALOID:AI トラックでは type なしで duration（例: 音符の半分）・depth・rate")
    ai_vibrato: bool | None = Field(None, description="AI auto-vibrato on/off (VOCALOID:AI tracks). / AI ビブラートの有効・無効")
    ai_exp: dict[str, float] | None = Field(  # keys listed as properties: Gemini rejects an object without any
        None, json_schema_extra={"properties": {k: {"type": "number"} for k in vpr.AI_EXP_KEYS}}, description="VOCALOID:AI note settings 0..1 (0.5 = unchanged), e.g. {'amplitudeEnd': 0.3}. "
        "vibratoLeading/FollowingDepth only scale the AI's own auto-vibrato (little on short notes). Keys: "
        "vibratoLeadingDepth, vibratoFollowingDepth, amplitudeWhole/Start/End, pitchFine, pitchDriftStart/End, "
        "pitchScalingCenter/Origin, pitchTransitionStart/End. / AI 音符の設定 0〜1（0.5 = 変更なし）")
    timing: list[int | None] | None = Field(
        None, description="Timing tool (VOCALOID:AI): ticks from the note start for each phoneme's start, then the end "
        "of the sound; null = automatic. 'r e' on a 960-tick note: [null, 119, 840] = vowel a 16th late, sound ends a "
        "16th early. [] = all automatic. Cleared when lyric or phoneme changes. / タイミングツール: 各音素の開始と音の終わり"
        "（音符の先頭からのティック、null = 自動）")


def _do(path: str | None, fn) -> dict:
    """Apply fn(seq) to a .vpr file (path) or to the project open in VOCALOID6 (live)."""
    if path:
        path = os.path.abspath(path)
        seq = vpr.load(path)
        result = fn(seq)
        vpr.save(path, seq)
        return {"result": result, "path": path, "mode": "file"}
    out = ui.run(live.edit, fn)
    if not out["dialogs"]:
        out.pop("dialogs")
    return out


def _get(path: str | None, fn):
    if path:
        return fn(vpr.load(path))
    result, _ = ui.run(live.read, fn)
    return result


def _split(text: str, language: str) -> tuple[list[str], list[str], str]:
    tokens, warnings, lang = lyric_text.split_lyrics(text, language)
    if not tokens:
        raise VocaloidError("No lyrics found in the text", "テキストに歌詞が見つかりません")
    return tokens, warnings, lang


# ======================= app =======================

@_tool()
def vocaloid_status() -> dict:
    """Is VOCALOID6 running, which project is open, and what to do next. Call this first.
    / VOCALOID6 が起動しているか、開いているプロジェクト、次にすべきこと。最初に呼んでください。"""
    return app.status()
_GUIDE_NOTE = ("\n\n---\nNote for agents without the skill: files this guide mentions next to it (voicebanks.md, "
               "mix_stems.py, scripts/) live in the skill folder of the repository and are not part of this server. "
               "Skip the steps that need them if they are not available.\n")


def _guide_text() -> str:
    """skill/SKILL.md without its front matter (bundled next to this file in wheels and the single-file build)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "SKILL.md"), os.path.join(here, "..", "..", "skill", "SKILL.md")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                text = f.read()
            return (text.split("---", 2)[2].lstrip() if text.startswith("---") else text) + _GUIDE_NOTE
    raise VocaloidError("Usage guide not found", "使い方ガイドが見つかりません")


@_tool()
def usage_guide() -> str:
    """Full workflow and quality rules for making good vocals with this server (same text as the Claude skill).
    Read it once before a song task. / この MCP で良い歌声を作るための手順と品質ルールの全文（Claude 用スキルと同じ内容）。
    曲作りの前に一度読んでください。"""
    return _guide_text()



@_tool()
def launch_vocaloid(project_path: str | None = None) -> dict:
    """Start VOCALOID6 (optionally opening a .vpr/.vsqx). If it is running, opens the project there.
    / VOCALOID6 を起動します（.vpr/.vsqx を指定可）。起動済みならそのプロジェクトを開きます。"""
    out = app.launch(project_path)
    if project_path and project_path.lower().endswith(".vpr"):
        live.remember(project_path)
    return out


@_tool()
def close_vocaloid(force: bool = False) -> dict:
    """Close VOCALOID6. Refuses if it has unsaved changes unless force=true (discards them).
    / VOCALOID6 を終了します。未保存の変更があれば force=true でない限り中止します（true で破棄）。"""
    return app.close(force)


@_tool()
def self_check() -> dict:
    """Check that the menus and buttons the live tools use still exist in this VOCALOID6 version.
    / ライブ操作が使うメニューとボタンがこの VOCALOID6 にあるか確認します。"""
    return ui.run(ui.self_check)


# ======================= project =======================

@_tool()
def new_project(path: str, title: str | None = None, bpm: float = 120, numer: int = 4, denom: int = 4,
                open_in_vocaloid: bool = False, overwrite: bool = False, force: bool = False) -> dict:
    """Create an empty .vpr project (no tracks yet; add them with add_track). open_in_vocaloid=true opens it in
    VOCALOID6 (force=true discards unsaved changes there). / 空の .vpr を作成します（トラックは add_track で追加）。
    open_in_vocaloid=true で VOCALOID6 で開きます（force=true で VOCALOID6 の未保存の変更を破棄）。"""
    path = os.path.abspath(path)
    if os.path.exists(path) and not overwrite:
        raise VocaloidError(f"{path} exists; pass overwrite=true to replace it", f"{path} は既に存在します。置き換えるなら overwrite=true")
    if os.path.exists(path):
        os.remove(path)
    seq = vpr.new(title or os.path.splitext(os.path.basename(path))[0], bpm, numer, denom)
    vpr.save(path, seq)
    out = {"path": path, "summary": vpr.summary(seq)}
    if open_in_vocaloid:
        out["opened"] = ui.run(ui.open_project, path, force)
        live.remember(path)
    return out


@_tool()
def open_project(path: str, force: bool = False) -> dict:
    """Open a .vpr or .vsqx in VOCALOID6. force=true discards unsaved changes in the current project.
    / .vpr または .vsqx を VOCALOID6 で開きます。force=true で現在の未保存の変更を破棄します。"""
    out = ui.run(ui.open_project, path, force)
    if path.lower().endswith(".vpr"):
        live.remember(path)
    return out


@_tool()
def save_project(path: str | None = None) -> dict:
    """Save the project open in VOCALOID6; with a .vpr path, save it there (Save As).
    / VOCALOID6 のプロジェクトを保存します。.vpr のパスを渡すとその場所に保存します（名前を付けて保存）。"""
    if path:
        out = ui.run(ui.save_as, path)
        live.remember(path)
        return out
    return ui.run(ui.save)


@_tool()
def reload_project() -> dict:
    """Reload the open project from disk (File > Revert): use after editing its .vpr with path=... tools.
    / 開いているプロジェクトをディスクから読み直します（path 指定で .vpr を編集した後に）。"""
    return ui.run(ui.revert)


@_tool()
def get_project(path: str | None = None) -> dict:
    """Tempo, time signatures, tracks, parts, singers, curves. / テンポ・拍子・トラック・パート・歌手・カーブの概要"""
    if path:
        return {"path": os.path.abspath(path), **vpr.summary(vpr.load(path))}
    summary, p = ui.run(live.read, vpr.summary)
    return {"path": p, **summary}


@_tool()
def undo() -> dict:
    """Undo the last live edit made by these tools (reloads the project). / これらのツールによる直前のライブ編集を取り消します"""
    return ui.run(live.undo)


@_tool()
def redo() -> dict:
    """Redo the last undone live edit. / 取り消したライブ編集をやり直します"""
    return ui.run(live.redo)


# ======================= tempo & time =======================

@_tool()
def set_tempo(bpm: float, position: int = 0, path: str | None = None) -> dict:
    """Set the tempo at a tick (0 = song tempo). / 指定ティックのテンポを設定します（0 = 曲全体）"""
    return _do(path, lambda s: vpr.set_tempo(s, bpm, position))


@_tool()
def remove_tempo(position: int, path: str | None = None) -> dict:
    """Remove a tempo change. / テンポ変更を削除します"""
    return _do(path, lambda s: vpr.remove_tempo(s, position))


@_tool()
def set_time_signature(numer: int, denom: int, bar: int = 0, path: str | None = None) -> dict:
    """Set the time signature from a bar (0-based). / 指定小節（0 から）からの拍子を設定します"""
    return _do(path, lambda s: vpr.set_time_signature(s, bar, numer, denom))


# ======================= voicebanks =======================

@_tool()
def list_voicebanks(kind: str | None = None) -> list[dict]:
    """Installed VOCALOID3-6 voicebanks: name, comp_id, kind (ai/classic), era, languages, track type.
    / インストール済みの VOCALOID3〜6 音源（名前・comp_id・種類・世代・言語・トラック種別）"""
    if kind not in (None, "ai", "classic"):
        raise VocaloidError("kind must be ai or classic", "kind は ai か classic です")
    return voicebanks.list_voicebanks(kind)


@_tool()
def get_voicebank(voice: str) -> dict:
    """One voicebank by name or comp ID. / 名前または comp ID で音源を1つ取得します"""
    return voicebanks.find(voice)


@_tool()
def list_styles(filter: str | None = None) -> list[dict]:
    """VOCALOID6 style presets (e.g. filter="Soft"). Apply them in VOCALOID6's part inspector.
    / VOCALOID6 のスタイルプリセット一覧（例 filter="Soft"）。適用は VOCALOID6 のパートのインスペクターで。"""
    return voicebanks.list_styles(filter)


# ======================= tracks & parts =======================

@_tool()
def add_track(voice: str, name: str | None = None, language: str | None = None, part_position: int = 0,
              part_duration: int = 1920, path: str | None = None) -> dict:
    """Add a track for a voicebank (VOCALOID:AI track for AI banks, VOCALOID track for classic ones) with one
    empty part. language picks the AI voice's language (ja/en/ko/es/zh). / 音源のトラックを追加します（AI 音源は
    VOCALOID:AI、旧世代は VOCALOID トラック）。空のパートを1つ作ります。language は AI 音源の言語です。"""
    bank = voicebanks.find(voice)
    return _do(path, lambda s: {"track": vpr.add_track(s, bank, name, language, part_position, part_duration), "part": 0})


@_tool()
def edit_track(track: int, name: str | None = None, mute: bool | None = None, solo: bool | None = None,
               volume: int | None = None, pan: int | None = None, voice: str | None = None,
               language: str | None = None, path: str | None = None) -> dict:
    """Rename, mute, solo, set volume (dB x10) / pan (-64..64), or change the singer of every part.
    Changing voice without language keeps each note's language and phonemes (VOCALOID6 does not convert them):
    pass language to reset them.
    / トラック名・ミュート・ソロ・音量（dB×10）・パン（-64〜64）・全パートの歌手を変更します"""
    bank = voicebanks.find(voice) if voice else None

    def fn(s):
        vpr.set_track(s, track, name, mute, solo, volume, pan)
        if bank:
            vpr.set_voice(s, track, bank, language)
        return vpr.summary(s)["tracks"][track]
    return _do(path, fn)


@_tool()
def remove_track(track: int, path: str | None = None) -> dict:
    """Delete a track. / トラックを削除します"""
    return _do(path, lambda s: vpr.remove_track(s, track))


@_tool()
def add_part(track: int, position: int, duration: int = 1920, name: str | None = None, voice: str | None = None,
             language: str | None = None, path: str | None = None) -> dict:
    """Add an empty part (absolute position). Uses the track's singer unless voice is given.
    / 空のパートを追加します（絶対位置）。voice を省くとトラックの歌手を使います"""
    bank = voicebanks.find(voice) if voice else None
    return _do(path, lambda s: {"part": vpr.add_part(s, track, position, duration, name, bank, language)})


@_tool()
def edit_part(track: int, part: int, position: int | None = None, duration: int | None = None,
              name: str | None = None, path: str | None = None) -> dict:
    """Move, resize or rename a part. / パートの移動・長さ変更・名前変更"""
    return _do(path, lambda s: {k: v for k, v in vpr.edit_part(s, track, part, position, duration, name).items()
                                if k in ("name", "pos", "duration")})


@_tool()
def remove_part(track: int, part: int, path: str | None = None) -> dict:
    """Delete a part. / パートを削除します"""
    return _do(path, lambda s: vpr.remove_part(s, track, part))


@_tool()
def fit_part(track: int, part: int, path: str | None = None) -> dict:
    """Make a part end on the first bar line after its last note. / パートを最後の音符の次の小節線までに合わせます"""
    return _do(path, lambda s: vpr.fit_part(s, track, part))


# ======================= notes & lyrics =======================

@_tool()
def list_notes(track: int, part: int, start: int = 0, count: int | None = None, path: str | None = None) -> list[dict]:
    """Notes of a part with lyric, phoneme (null = not computed yet), language, vibrato.
    / パートの音符一覧（歌詞・発音記号（null は未計算）・言語・ビブラート）"""
    return _get(path, lambda s: vpr.list_notes(s, track, part, start, count))


@_tool()
def add_notes(track: int, part: int, notes: list[NoteIn], language: str | None = None, path: str | None = None) -> dict:
    """Add notes (positions relative to the part; the part grows to fit). / 音符を追加します（位置はパート相対、パートは自動で伸びます）"""
    payload = [n.model_dump() for n in notes]
    return _do(path, lambda s: {"indexes": vpr.add_notes(s, track, part, payload, language)})


@_tool()
def edit_notes(track: int, part: int, edits: list[NoteEdit], path: str | None = None) -> dict:
    """Change position, length, pitch, lyric, phoneme, velocity, language, vibrato or phoneme timing of notes by index.
    / 番号で指定した音符の位置・長さ・音高・歌詞・発音記号・ベロシティ・言語・ビブラート・発音タイミングを変更します"""
    payload = [e.model_dump(exclude_none=True) for e in edits]
    return _do(path, lambda s: vpr.edit_notes(s, track, part, payload))


@_tool()
def delete_notes(track: int, part: int, indexes: list[int], path: str | None = None) -> dict:
    """Delete notes by index. / 番号で指定した音符を削除します"""
    return _do(path, lambda s: {"deleted": vpr.delete_notes(s, track, part, indexes)})


@_tool()
def assign_lyrics(track: int, part: int, text: str | None = None, lyrics: list[str] | None = None,
                  start: int = 0, language: str = "auto", path: str | None = None) -> dict:
    """Put lyrics on existing notes from note `start` on: `text` is split one syllable per note (see the rules),
    or pass `lyrics` as a ready list. / 既存の音符（start 番から）に歌詞を付けます。text は1音符1音節に分割、
    または lyrics にリストで渡します。"""
    if (text is None) == (lyrics is None):
        raise VocaloidError("Give either text or lyrics", "text か lyrics のどちらか一方を指定してください")
    warnings, lang = [], None if language == "auto" else language
    if text is not None:
        lyrics, warnings, lang = _split(text, language)
    out = _do(path, lambda s: {"assigned": vpr.assign_lyrics(s, track, part, lyrics, start, lang), "lyrics": lyrics})
    if warnings:
        out["warnings"] = warnings
    return out


@_tool()
def add_melody(track: int, part: int, melody: str, lyrics: str | None = None, language: str = "auto",
               start: int | None = None, path: str | None = None) -> dict:
    """Add a melody and its lyrics in one call. melody: 'A4:1 A4:1 B4:2 r:1 C5:1/2' (length in quarter-note beats,
    r = rest). lyrics are split one syllable per sounding note and must match the note count. start defaults to
    the end of the part's last note. / メロディと歌詞を一度に追加します。melody 例 'A4:1 A4:1 B4:2 r:1 C5:1/2'
    （長さは四分音符単位、r = 休符）。歌詞は1音符1音節に分割し、音符数と一致させてください。"""
    tokens, warnings, lang = (None, [], None)
    if lyrics:
        tokens, warnings, lang = _split(lyrics, language)
    out = _do(path, lambda s: {"indexes": vpr.add_melody(s, track, part, melody, tokens, start, lang), "lyrics": tokens})
    if warnings:
        out["warnings"] = warnings
    return out


# ======================= curves =======================

@_tool()
def set_curve(track: int, part: int, curve: str, points: list[list[int]], path: str | None = None) -> dict:
    """Write a part curve: points [[tick, value], ...] relative to the part replace the curve between the first and
    last tick. VOCALOID:AI tracks: dynamics, pitchBend, pitchBendSens, expression (0..100), air (-100..100),
    character (-64..63). VOCALOID tracks: dynamics, pitchBend, pitchBendSens, breathiness, brightness, clearness,
    portamento, growl, xSynth, character, air, exciter (short names DYN, PIT, PBS, EXP, BRE, BRI, CLE, POR, GWL,
    XSY, GEN/CHA, AIR, EXC). A lane the track type ignores is refused.
    / パートのカーブを書きます。points は [[ティック, 値], ...]（パート相対）で、最初と最後のティックの間を置き換えます。"""
    return _do(path, lambda s: {"points": vpr.set_curve(s, track, part, curve, [tuple(p) for p in points])})


@_tool()
def get_curve(track: int, part: int, curve: str, path: str | None = None) -> dict:
    """Points, range and default of a part curve. / パートのカーブの点・範囲・既定値"""
    return _get(path, lambda s: vpr.get_curve(s, track, part, curve))


@_tool()
def clear_curve(track: int, part: int, curve: str, start: int | None = None, end: int | None = None,
                path: str | None = None) -> dict:
    """Remove curve points (all, or between start and end ticks). / カーブの点を削除します（全部、または範囲内）"""
    return _do(path, lambda s: {"removed": vpr.clear_curve(s, track, part, curve, start, end)})


# ======================= playback & export =======================

@_tool()
def play() -> dict:
    """Start playback in VOCALOID6. / VOCALOID6 で再生を開始します"""
    return ui.run(ui.play)


@_tool()
def stop() -> dict:
    """Stop playback. / 再生を停止します"""
    return ui.run(ui.stop)


@_tool()
def export_wav(output: str, tracks: list[int] | None = None, bypass_effects: bool = False,
               bit_depth: int | None = None, timeout_seconds: int = 600) -> dict:
    """Render the main mix of the open project to a WAV file (Audio Mixdown). Can take a while. tracks=[...] renders
    only those tracks (a stem): the others are muted for the export, then mute/solo are restored. bit_depth (16, 24,
    32...) picks the dialog's bit depth, which VOCALOID6 remembers; omitted = keep what the dialog has.
    / 開いているプロジェクトのメインミックスを WAV に書き出します（時間がかかることがあります）。tracks=[...] で
    そのトラックだけを書き出します（ステム）。他のトラックは書き出しの間だけミュートし、後で元に戻します。
    bit_depth（16・24・32 など）でビット深度を選びます（VOCALOID6 が記憶します）。"""
    if tracks:
        return ui.run(live.export_tracks, output, tracks, bypass_effects, timeout_seconds, bit_depth,
                      timeout=timeout_seconds + 120)
    return ui.run(ui.export_wav, output, bypass_effects, timeout_seconds, bit_depth, timeout=timeout_seconds + 60)


@_tool()
def export_midi(output: str) -> dict:
    """Export the open project as a standard MIDI file (with lyrics). / 開いているプロジェクトを MIDI ファイルに書き出します"""
    return ui.run(ui.export_midi, output)


@_tool()
def import_midi(midi_path: str, track_type: str = "ai", import_tempo: bool = True) -> dict:
    """Import a MIDI file into the open project as new tracks (track_type "ai" or "classic"; MIDI lyric events
    become lyrics). / MIDI ファイルを新しいトラックとして読み込みます（track_type は "ai" か "classic"）"""
    if track_type not in ("ai", "classic"):
        raise VocaloidError("track_type must be ai or classic", "track_type は ai か classic です")
    return ui.run(ui.import_midi, midi_path, track_type, import_tempo)


@_tool()
def export_vsqx(output: str, version: int = 4, path: str | None = None) -> dict:
    """Write a .vsqx for the VOCALOID4 (version=4) or VOCALOID3 (version=3) editor. Only classic VOCALOID tracks are
    written; positions shift by one pre-measure bar, as those editors count. / VOCALOID4（version=4）または
    VOCALOID3（version=3）用の .vsqx を書き出します。VOCALOID トラックのみ。位置はプリメジャー1小節分ずれます。"""
    seq = vpr.load(path) if path else ui.run(live.read, lambda s: s)[0]
    data, warnings = vsqx.export(seq, version)
    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "wb") as f:
        f.write(data)
    return {"vsqx": output, "version": version, "warnings": warnings}


# ======================= utilities =======================

@_tool()
def note_to_midi(note: str) -> int:
    """Note name to MIDI number (C4 = 60). / 音名を MIDI 番号に（C4 = 60）"""
    return music.to_midi(note)


@_tool()
def midi_to_note(midi: int) -> str:
    """MIDI number to note name. / MIDI 番号を音名に"""
    return music.to_name(midi)


@_tool()
def beats_to_ticks(beats: float) -> int:
    """Quarter-note beats to ticks (480 per beat). / 拍数をティックに（1拍 = 480）"""
    return music.beats_to_ticks(beats)


@_tool()
def ticks_to_beats(ticks: int) -> float:
    """Ticks to quarter-note beats. / ティックを拍数に"""
    return music.ticks_to_beats(ticks)


@_tool()
def split_lyrics(text: str, language: str = "auto") -> dict:
    """Preview how text splits into one lyric per note. / テキストが1音符ずつの歌詞にどう分かれるかを確認します"""
    tokens, warnings, lang = lyric_text.split_lyrics(text, language)
    return {"lyrics": tokens, "count": len(tokens), "language": lang, "warnings": warnings}


def main() -> None:
    import faulthandler
    import sys
    faulthandler.enable(sys.stderr)  # a native crash in UI Automation prints its stack instead of vanishing
    mcp.run()


if __name__ == "__main__":
    main()
