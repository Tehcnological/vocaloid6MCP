"""Live edits of the project open in VOCALOID6: save it there, edit the .vpr, reload it (File > Revert).

Saving first keeps whatever the user changed by hand in VOCALOID6. Every edit snapshots the file first, so
undo/redo work across reloads (VOCALOID6's own undo history restarts after each reload).
These functions run on the UI thread (ui.run).
"""

import hashlib
import json
import os
import shutil
import time

from . import ui, vpr
from .errors import VocaloidError

STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "vocaloid6-mcp")
STATE = os.path.join(STATE_DIR, "state.json")
MAX_UNDO = 50


def _read_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def remember(path: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    state = _read_state()
    state["current"] = os.path.abspath(path)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def current_path() -> str:
    """Path of the project open in VOCALOID6 (the window shows only its name)."""
    name = ui.project_name()
    if not name or name == "Untitled":
        raise VocaloidError(
            "The project in VOCALOID6 has never been saved: call save_project with a .vpr path first",
            "VOCALOID6 のプロジェクトがまだ保存されていません。先に .vpr のパスを指定して save_project を呼んでください")
    known = _read_state().get("current")
    if known and os.path.splitext(os.path.basename(known))[0] == name and os.path.isfile(known):
        return known
    for p in ui.recent_paths():
        if os.path.splitext(os.path.basename(p))[0] == name and p.lower().endswith(".vpr"):
            remember(p)
            return p
    raise VocaloidError(
        f"Cannot tell where {name!r} is saved: call open_project with its path once",
        f"{name!r} の保存場所がわかりません。一度 open_project でパスを指定してください")


def _save_and_wait(path: str) -> None:
    before = os.path.getmtime(path) if os.path.exists(path) else None
    ui.save()
    # VOCALOID6 writes asynchronously; an unchanged project may not be rewritten at all
    end = time.time() + 5
    while time.time() < end and os.path.exists(path) and os.path.getmtime(path) == before:
        time.sleep(0.2)
    time.sleep(0.3)


def _stack(path: str, kind: str) -> str:
    key = hashlib.sha1(os.path.abspath(path).lower().encode()).hexdigest()[:16]
    d = os.path.join(STATE_DIR, "history", key, kind)
    os.makedirs(d, exist_ok=True)
    return d


def _push(path: str, kind: str) -> None:
    d = _stack(path, kind)
    shutil.copyfile(path, os.path.join(d, f"{time.time_ns()}.vpr"))
    old = sorted(os.listdir(d))[:-MAX_UNDO]
    for f in old:
        os.remove(os.path.join(d, f))


def _pop(path: str, kind: str) -> str | None:
    d = _stack(path, kind)
    files = sorted(os.listdir(d))
    return os.path.join(d, files[-1]) if files else None


def read(fn, save_first: bool = True):
    path = current_path()
    if save_first:
        _save_and_wait(path)
    return fn(vpr.load(path)), path


def edit(fn) -> dict:
    """Save in VOCALOID6, apply fn(seq) to the file, reload. Returns {result, path, dialogs}."""
    path = current_path()
    _save_and_wait(path)
    seq = vpr.load(path)
    result = fn(seq)
    _push(path, "undo")
    shutil.rmtree(_stack(path, "redo"), ignore_errors=True)
    vpr.save(path, seq)
    r = ui.revert()
    return {"result": result, "path": path, "mode": "live", "dialogs": r["dialogs"]}


def undo(kind_from: str = "undo", kind_to: str = "redo") -> dict:
    path = current_path()
    snap = _pop(path, kind_from)
    if not snap:
        raise VocaloidError(f"Nothing to {kind_from}", f"{'元に戻す' if kind_from == 'undo' else 'やり直す'}操作がありません")
    _save_and_wait(path)
    _push(path, kind_to)
    shutil.copyfile(snap, path)
    os.remove(snap)
    r = ui.revert()
    return {"path": path, kind_from: True, "dialogs": r["dialogs"]}


def redo() -> dict:
    return undo("redo", "undo")
