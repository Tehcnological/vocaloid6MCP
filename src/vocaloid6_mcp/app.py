"""Find, launch and close the VOCALOID6 editor."""

import os
import subprocess
import time

import psutil

from . import ui
from .errors import VocaloidError


def find_exe() -> str | None:
    candidates = [os.environ.get("VOCALOID6_EXE")]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(os.path.join(base, "VOCALOID6", "Editor", "VOCALOID6.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def processes() -> list[psutil.Process]:
    return [p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == "vocaloid6.exe"]


def _window_info() -> dict:
    w = ui.main_window(required=False)
    if not w:
        return {"window": False}
    return {"window": True, "home_screen": ui.on_home_screen(w), "project": ui.project_name(w),
            "open_dialogs": [d.window_text() for d in ui.dialogs(w)]}


def status() -> dict:
    procs = processes()
    info = {"running": bool(procs), "pids": [p.pid for p in procs], "exe": find_exe()}
    if procs:
        info.update(ui.run(_window_info))
    if not procs:
        info["hint"] = "VOCALOID6 is not running: call launch_vocaloid. / VOCALOID6 が起動していません。launch_vocaloid を呼んでください。"
    elif info.get("open_dialogs"):
        info["hint"] = ("A dialog is open in VOCALOID6; close it there before live edits. / "
                        "VOCALOID6 でダイアログが開いています。ライブ編集の前に閉じてください。")
    elif info.get("home_screen"):
        info["hint"] = "VOCALOID6 shows its Home screen: call open_project or new_project. / ホーム画面です。open_project か new_project を呼んでください。"
    else:
        info["hint"] = "Ready. / 準備完了です。"
    return info


def launch(project_path: str | None = None, wait_seconds: float = 90) -> dict:
    if project_path:
        project_path = os.path.abspath(project_path)
        if not os.path.isfile(project_path):
            raise VocaloidError(f"File not found: {project_path}", f"ファイルが見つかりません: {project_path}")
    if processes():
        if project_path:
            return {"launched": False, **ui.run(ui.open_project, project_path)}
        return {"launched": False, **status()}
    exe = find_exe()
    if not exe:
        raise VocaloidError("VOCALOID6.exe not found; set the VOCALOID6_EXE environment variable",
                            "VOCALOID6.exe が見つかりません。環境変数 VOCALOID6_EXE を設定してください")
    subprocess.Popen([exe] + ([project_path] if project_path else []), cwd=os.path.dirname(exe), close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + wait_seconds
    while time.time() < deadline and not ui.run(lambda: ui.main_window(required=False) is not None):
        time.sleep(1)
    time.sleep(3)  # let the window finish building
    out = {"launched": True}
    if project_path:
        stem = os.path.splitext(os.path.basename(project_path))[0]
        if ui.run(lambda: ui.project_name()) != stem:
            out.update(ui.run(ui.open_project, project_path))
    return {**out, **status()}


def _close_window(force: bool):
    w = ui.main_window()
    try:
        w.iface_window.Close()
    except Exception:  # noqa: BLE001 - fall back to the title-bar button
        btn = next((b for b in w.descendants(control_type="Button") if b.window_text() == "Close"), None)
        if btn is None:
            raise
        ui._invoke(btn)
    ui._resolve_unsaved_prompt(w, force)


def close(force: bool = False) -> dict:
    procs = processes()
    if not procs:
        return {"closed": False, "message": "VOCALOID6 is not running. / VOCALOID6 は起動していません。"}
    ui.run(_close_window, force)
    gone, alive = psutil.wait_procs(procs, timeout=20)
    if alive:
        if force:
            for p in alive:
                p.kill()
            return {"closed": True, "killed": [p.pid for p in alive]}
        return {"closed": False, "still_running": [p.pid for p in alive],
                "hint": "VOCALOID6 did not close (busy or showing a dialog). / VOCALOID6 が閉じませんでした（処理中かダイアログ表示中）。"}
    return {"closed": True, "pids": [p.pid for p in gone]}
