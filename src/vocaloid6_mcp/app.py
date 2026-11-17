"""Find, launch and close the VOCALOID6 editor."""

import os
import subprocess
import time

import psutil

from . import ui
from .errors import VocaloidError
from .winpaths import known_dir


def find_exe() -> str | None:
    candidates = [os.environ.get("VOCALOID6_EXE")]
    for base in (known_dir("ProgramFiles", "ProgramFilesDir", "Program Files"),
                 known_dir("ProgramFiles(x86)", "ProgramFilesDir (x86)", "Program Files (x86)")):
        candidates.append(os.path.join(base, "VOCALOID6", "Editor", "VOCALOID6.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


processes = ui.processes  # one rule for finding VOCALOID6, shared with the window lookup


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


_SPAWN_PS = """
$a = @{CommandLine = $env:MCP_SPAWN_CMD; CurrentDirectory = $env:MCP_SPAWN_DIR}
try { $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments $a -ErrorAction Stop } catch { exit 1 }
if ($null -eq $r) { exit 1 }
exit $r.ReturnValue
"""


def spawn(args: list[str], cwd: str) -> list[str]:
    """Start the editor so it outlives this server. Some MCP clients (e.g. the official Python SDK on Windows) run
    the server in a job object that kills every child process when the client disconnects, which would close the
    editor with unsaved work; Windows creates a process started through WMI outside that job, with the user's full
    environment (a child process would get only the client's trimmed one). Returns warnings for the caller."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SPAWN_PS], capture_output=True,
                           env={**os.environ, "MCP_SPAWN_CMD": subprocess.list2cmdline(args), "MCP_SPAWN_DIR": cwd},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=20)
        started = r.returncode == 0
    except subprocess.TimeoutExpired:
        started = None  # WMI may still be creating it: wait longer before trying another way
    except OSError:
        started = False
    # a slow WMI call may still have started it: never start a second copy
    for _ in range(10 if started else 30 if started is None else 5):
        if processes():
            return []
        time.sleep(1)
    subprocess.Popen(args, cwd=cwd, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return ["Started as a child of this server: if the MCP client closes it, the editor may close too. "
            "Save often. / このサーバーの子プロセスとして起動しました。MCP クライアントが終了すると"
            "エディターも閉じることがあります。こまめに保存してください。"]


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
    warnings = spawn([exe] + ([project_path] if project_path else []), os.path.dirname(exe))
    deadline = time.time() + wait_seconds
    # with a project, wait for the editor window, not a Home window shown while it loads
    def ready():
        w = ui.main_window(required=False)
        return w is not None and (not project_path or ui.is_editor(w) or ui._message_box(w))
    while time.time() < deadline and not ui.run(ready):
        time.sleep(1)
    time.sleep(3)  # let the window finish building
    out = {"launched": True}
    if warnings:
        out["warnings"] = warnings
    if project_path:
        def check_boxes():  # a box: raise if the project did not open (or VOCALOID6 asks something), else report it
            w = ui.main_window(required=False)
            if w is None:
                return []
            if not ui._idle(w):  # the load from the command line is still running: never open it a second time
                raise ui.busy_error()
            w = ui.main_window(required=False)  # the Home window may have been replaced by the editor meanwhile
            return ui.finish_load(w, project_path) if w and ui._message_box(w) else []
        notes = ui.run(check_boxes)
        if notes:
            out["dialogs"] = notes
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
