"""Installed VOCALOID3-6 voicebanks (from the registry) and VOCALOID6 style presets (from their JSON files).

Classic banks (VOCALOID3, 4, 5) sing on "VOCALOID" tracks; VOCALOID6 AI banks sing on "VOCALOID:AI" tracks.
VOCALOID2 banks are not supported (VOCALOID6 cannot load them).
"""

import glob
import json
import os
import re

from .errors import VocaloidError
from .lyrics import LANG_NAMES

try:
    import winreg
except ImportError:  # not Windows: no installed banks
    winreg = None

_COMP_ID = re.compile(r"^[A-Z0-9]{16}$")
_ROOTS = (("VOCALOID3", 3), ("VOCALOID4", 4), ("VOCALOID5", 5), ("VOCALOID6", 6))
_LANG_WORDS = (("ENG", 1), ("ENGLISH", 1), ("KOR", 2), ("KOREAN", 2), ("ESP", 3), ("SPANISH", 3),
               ("CHN", 4), ("CHS", 4), ("CHINESE", 4), ("MANDARIN", 4))


def known_dir(env: str, reg_value: str, default: str) -> str:
    """A Windows folder from its environment variable, else the registry, else <SystemDrive>\\default: MCP clients
    often start servers with a short environment that has no ProgramFiles or CommonProgramFiles."""
    if os.environ.get(env):
        return os.environ[env]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion") as k:
            return winreg.QueryValueEx(k, reg_value)[0]
    except (AttributeError, OSError):  # winreg is None off Windows
        return os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, default)


_COMMON = known_dir("CommonProgramFiles", "CommonFilesDir", os.path.join("Program Files", "Common Files"))
STYLE_DIRS = [os.path.join(_COMMON, "VOCALOID6", "StylePreset"),
              os.path.join(os.environ.get("APPDATA", ""), "VOCALOID6", "StylePreset")]
PREFS = os.path.join(os.environ.get("APPDATA", ""), "VOCALOID6", "Settings", "preferences_common.json")


def _values(key) -> dict:
    out, i = {}, 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
        except OSError:
            return out
        out[name.lower()] = value
        i += 1


def _walk(root_key, path: str, depth: int):
    """Yield (subkey name, values) for every key under path, depth-first."""
    try:
        key = winreg.OpenKey(root_key, path)
    except OSError:
        return
    with key:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            full = f"{path}\\{sub}"
            try:
                with winreg.OpenKey(root_key, full) as k:
                    yield sub, _values(k), full
            except OSError:
                continue
            if depth > 0:
                yield from _walk(root_key, full, depth - 1)


def _display_name(vals: dict) -> str:
    if vals.get("bankname"):
        return str(vals["bankname"])
    name = str(vals.get("name", ""))
    m = re.search(r"\(([^)]+)\)\s*$", name)  # e.g. "VOCALOID4 Library (BANK_NAME)"
    return m.group(1) if m else name


def _guess_language(name: str) -> int:
    words = set(re.split(r"[^A-Z]+", name.upper()))
    return next((lid for w, lid in _LANG_WORDS if w in words), 0)


def _scan() -> list[dict]:
    if winreg is None:
        return []
    banks: dict[str, dict] = {}
    views = [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
    for root, era in _ROOTS:
        for view in views:
            for software in ("SOFTWARE", "SOFTWARE\\WOW6432Node"):
                try:
                    hk = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
                except OSError:
                    continue
                with hk:
                    for sub, vals, full in _walk(hk, f"{software}\\{root}", 4):
                        if not _COMP_ID.match(sub) or "path" not in vals or "name" not in vals:
                            continue
                        lowered = full.lower()
                        if "\\application" in lowered or "\\attackreleaselib" in lowered or "expression" in lowered:
                            continue  # editors, attack/release libraries, VOCALOID2-style expression DBs
                        if str(vals.get("installed", 1)) == "0":
                            continue
                        is_ai = "pmodelname" in vals or "tmodelname" in vals
                        name = _display_name(vals)
                        if is_ai:
                            mask = int(vals.get("languages", 1) or 1)
                            langs = [lid for lid in range(8) if mask & (1 << lid) and lid in LANG_NAMES]
                            lang_source = "registry"
                        else:
                            langs = [_guess_language(name)]
                            lang_source = "name"
                        entry = {
                            "comp_id": sub, "name": name, "era": era,
                            "kind": "ai" if is_ai else "classic",
                            "track_type": "VOCALOID:AI" if is_ai else "VOCALOID",
                            "languages": [LANG_NAMES[x] for x in langs], "language_ids": langs,
                            "language_source": lang_source,
                            "path": str(vals.get("path", "")),
                            "default_style_id": vals.get("defaultstyleid"),
                        }
                        banks.setdefault(sub, entry)
    return sorted(banks.values(), key=lambda b: (b["kind"] != "ai", -b["era"], b["name"].lower()))


def list_voicebanks(kind: str | None = None) -> list[dict]:
    banks = _scan()
    if kind:
        banks = [b for b in banks if b["kind"] == kind]
    return banks


def find(voice: str) -> dict:
    """Voicebank by comp ID or name (exact, then case-insensitive, then unique substring)."""
    banks = _scan()
    key = (voice or "").strip()
    for test in (lambda b: b["comp_id"] == key, lambda b: b["name"] == key,
                 lambda b: b["name"].lower() == key.lower()):
        hit = [b for b in banks if test(b)]
        if hit:
            return hit[0]
    hit = [b for b in banks if key.lower() in b["name"].lower()]
    if len(hit) == 1:
        return hit[0]
    names = [b["name"] for b in (hit or banks)]
    raise VocaloidError(
        f"Voicebank {voice!r} not found{' (ambiguous)' if hit else ''}; installed: {names}",
        f"音源 {voice!r} が見つかりません{'（候補が複数）' if hit else ''}。インストール済み: {names}")


def default_voice(kind: str) -> dict | None:
    """VOCALOID6's default voice for a track kind, from its preferences; else the first installed one."""
    try:
        with open(PREFS, encoding="utf-8") as f:
            prefs = json.load(f)
        cid = prefs.get("defaultAiVoiceCompID" if kind == "ai" else "defaultVoiceCompID")
    except (OSError, ValueError):
        cid = None
    banks = list_voicebanks(kind)
    return next((b for b in banks if b["comp_id"] == cid), banks[0] if banks else None)


def list_styles(voice: str | None = None) -> list[dict]:
    """VOCALOID6 style presets (shipped and user-made)."""
    out = []
    for d in STYLE_DIRS:
        for path in glob.glob(os.path.join(d, "**", "*.vsstyle"), recursive=True):
            try:
                with open(path, encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({"id": data.get("id"), "name": data.get("name"), "vendor": data.get("vendor"),
                        "tags": sum((v for v in (data.get("filter") or {}).values() if isinstance(v, list)), [])})
    if voice:
        key = voice.lower()
        out = [s for s in out if key in (s["name"] or "").lower()]
    return sorted(out, key=lambda s: (s["name"] or "").lower())
