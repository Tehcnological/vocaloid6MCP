"""Find, launch and close the VOCALOID6 editor."""

import os
import subprocess
import time

import psutil

from . import ui
from .errors import VocaloidError


def find_exe() -> str | None:
    candidates = [os.environ.get("VOCALOID6_EXE")]
    # MCP clients often start servers with a short env whitelist that has no ProgramFiles (but has SystemDrive)
    drive = os.environ.get("SystemDrive", "C:") + os.sep
    for base in (os.environ.get("ProgramFiles") or os.path.join(drive, "Program Files"),
                 os.environ.get("ProgramFiles(x86)") or os.path.join(drive, "Program Files (x86)")):
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


_SPAWN_PS = """
$a = @{CommandLine = $env:MCP_SPAWN_CMD; CurrentDirectory = $env:MCP_SPAWN_DIR}
if ($env:MCP_SPAWN_HIDE) {
  $a.ProcessStartupInformation = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow = [uint16]0}
}
try { $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments $a -ErrorAction Stop } catch { exit 1 }
if ($null -eq $r) { exit 1 }
exit $r.ReturnValue
"""


def spawn(args: list[str], cwd: str, env_prefix: str | None = None) -> None:
    """Start the editor so it outlives this server. Some MCP clients (e.g. the official Python SDK on Windows) run
    the server in a job object that kills every child process when the client disconnects, which would close the
    editor with unsaved work; Windows creates a process started through WMI outside that job. That process gets the
    user's full environment; this server's variables whose names start with env_prefix are added by a hidden cmd
    that then starts the editor (WMI's own environment option would replace the whole environment)."""
    cmd = subprocess.list2cmdline(args)
    # skip values cmd would expand or misquote (% and "); Windows paths cannot contain "
    extra = {k: v for k, v in os.environ.items()
             if env_prefix and k.upper().startswith(env_prefix) and not {'"', "%"} & set(v)}
    wrap = bool(extra) and "%" not in cmd
    if wrap:  # every argument in quotes, so cmd reads & | < > ^ in a path as text
        cmd = ("cmd /c " + " && ".join(f'set "{k}={v}"' for k, v in extra.items())
               + ' && start "" ' + " ".join(f'"{a}"' for a in args))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SPAWN_PS], capture_output=True,
                           env={**os.environ, "MCP_SPAWN_CMD": cmd, "MCP_SPAWN_DIR": cwd,
                                "MCP_SPAWN_HIDE": "1" if wrap else ""},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)
        if r.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    for _ in range(5):  # a slow WMI call may still have started it: never start a second copy
        if processes():
            return
        time.sleep(1)
    subprocess.Popen(args, cwd=cwd, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


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
    spawn([exe] + ([project_path] if project_path else []), os.path.dirname(exe))
    deadline = time.time() + wait_seconds
    # with a project, wait for the editor window, not a Home window shown while it loads
    def ready():
        w = ui.main_window(required=False)
        return w is not None and (not project_path or ui.is_editor(w) or ui._message_box(w))
    while time.time() < deadline and not ui.run(ready):
        time.sleep(1)
    time.sleep(3)  # let the window finish building
    out = {"launched": True}
    if project_path:
        def check_boxes():  # an error box: raise if the project did not open, else report it
            w = ui.main_window(required=False)
            box = w and ui._message_box(w)
            return ui.finish_load(w, project_path) if box and not ui.is_question(box) else []
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
