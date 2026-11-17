"""Drive the VOCALOID6 editor through Windows UI Automation (the accessibility API).

No code inside VOCALOID6 is touched: this only clicks its menus, buttons and dialogs the way a screen reader
would. Every selector lives in SELECTORS so a VOCALOID6 update means editing one table; self_check() reports
which selectors still match. Never sends keystrokes (they would go to whatever window is in front).
All calls run on one worker thread that owns COM.
"""

import concurrent.futures
import os
import sys
import threading
import time

# UI Automation in the multithreaded apartment: clicks can then run on helper threads (see _invoke)
sys.coinit_flags = 0  # COINIT_MULTITHREADED, read by comtypes/pywinauto at import

from .errors import VocaloidError

SELECTORS = {
    "main_window": {"auto_id": "xMainWindow"},
    "home_window": {"auto_id": "xHomeWindow"},  # VOCALOID6 may show its Home screen as its own window at startup
    "main_menu": {"auto_id": "xMainMenu"},
    "menu": {
        "File": ["New", "Open...", "Save", "Save As...", "Revert", "Import", "Export MIDI...", "Audio Mixdown..."],
        "Edit": ["Undo", "Redo", "Add VOCALOID:AI Track", "Add VOCALOID Track"],
        "Transport": ["Play", "Stop"],
    },
    "import_midi": ["Import", "MIDI File..."],
    "home_open_text": "OPEN",
    "play_button": {"auto_id": "xPlaybackButton"},
    "stop_button": {"auto_id": "xStopButton"},
    "voice_changed_dialog": {"auto_id": "xVoiceChangedDlg", "ok": "xOKButton"},
    "mixdown_dialog": {"auto_id": "xAudioMixdownDlg", "ok": "xOKButton", "main": "xRBMasterTrack",
                       "open_folder": "xOpenExplorerCheckBox", "bypass": "xIsBypassCheckBox",
                       "bit_depth": "xBitDepthComboBox"},
    "smf_import_dialog": {"auto_id": "xImportSMFSettingsDialog", "ok": "xOkButton", "track_type": "xTrackTypeComboBox",
                          "tempo": "xTempoTimeSigCheckBox"},
    "file_dialog_class": "#32770",
    "file_name_edit_ids": ("1148", "1001"),
    "file_dialog_ok_id": "1",
    "title_prefix": "VOCALOID6 Editor - ",
}

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="vocaloid-ui")
_com = threading.local()


def run(fn, *args, timeout: float = 600, **kwargs):
    """Run fn on the UI thread (COM initialised once there). A COM error means a VOCALOID6 window vanished while it
    was read: reported as an exit when VOCALOID6 is gone, else as a normal error."""
    def call():
        import comtypes
        if not getattr(_com, "ready", False):
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            _com.ready = True
        try:
            return fn(*args, **kwargs)
        except comtypes.COMError as e:
            if not processes():
                raise exited_error() from None
            raise VocaloidError(f"VOCALOID6 did not answer: {e}", f"VOCALOID6 が応答しませんでした: {e}") from e
    return _pool.submit(call).result(timeout=timeout)


_user32 = None
_ENUM_PROC = None


def _win32():
    """user32 with this module's own prototypes: pywinauto sets its own on the shared ctypes.windll.user32."""
    global _user32, _ENUM_PROC
    if _user32 is None:
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        _ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u.EnumWindows.argtypes = [_ENUM_PROC, wintypes.LPARAM]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.IsWindowVisible.argtypes = u.IsWindow.argtypes = [wintypes.HWND]
        u.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                          wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        _user32 = u
    return _user32


def _is_vocaloid(name: str | None) -> bool:
    return (name or "").lower() == "vocaloid6.exe"


def processes() -> list:
    """Running VOCALOID6 processes."""
    import psutil
    return [p for p in psutil.process_iter(["name"]) if _is_vocaloid(p.info.get("name"))]


def _vocaloid_windows() -> list:
    """VOCALOID6's visible top-level windows. Only its own windows are asked: listing the whole desktop through UI
    Automation waits about 5 s on every window that does not answer, such as a suspended Settings app. Windows are
    matched by their process name (a few lookups for the visible windows), so any VOCALOID6 process is found."""
    import ctypes
    from ctypes import wintypes

    import psutil
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_element_info import UIAElementInfo
    u, found, names = _win32(), [], {}

    def collect(hwnd, _):
        if u.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in names:
                try:
                    names[pid.value] = psutil.Process(pid.value).name()
                except psutil.Error:
                    names[pid.value] = None
            if _is_vocaloid(names[pid.value]):
                found.append(hwnd)
        return True

    u.EnumWindows(_ENUM_PROC(collect), 0)
    wrapped = []
    for h in found:
        try:
            wrapped.append(UIAWrapper(UIAElementInfo(h)))
        except Exception:  # noqa: BLE001 - a window that closed after it was listed (e.g. a splash at startup)
            pass
    return wrapped


def main_window(required: bool = True):
    """The editor window, else the separate Home window (on_home_screen() is then True)."""
    home = None
    for w in _vocaloid_windows():
        try:
            aid = w.element_info.automation_id
        except Exception:  # noqa: BLE001 - a window that closed after it was listed (e.g. a splash at startup)
            continue
        if aid == SELECTORS["main_window"]["auto_id"]:
            return w
        if aid == SELECTORS["home_window"]["auto_id"]:
            home = w
    if home is not None:
        return home
    if required:
        raise VocaloidError("VOCALOID6 is not running (call launch_vocaloid)",
                            "VOCALOID6 が起動していません（launch_vocaloid を呼んでください）")
    return None


def is_editor(w) -> bool:
    """True for the editor window, False for None or the separate Home window."""
    return w is not None and w.element_info.automation_id == SELECTORS["main_window"]["auto_id"]


def _wait(pred, timeout: float, step: float = 0.3):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = pred()
        except Exception:  # noqa: BLE001 - UI elements come and go while windows open
            v = None
        if v:
            return v
        time.sleep(step)
    return None


def _invoke(e, wait: float = 1.5) -> None:
    """Click through UI Automation without blocking: Invoke does not return until VOCALOID6's click handler does,
    and that handler may be waiting on a modal dialog only we can close. So invoke on a helper thread."""
    def go():
        try:
            import comtypes
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            e.invoke()
        except Exception:  # noqa: BLE001 - some items raise when they open a modal dialog
            pass
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(wait)


def dialogs(w=None) -> list:
    w = w or main_window()
    return [c for c in w.children() if c.element_info.control_type == "Window"]


def _texts(e) -> list[str]:
    return [x.window_text() for x in e.descendants() if x.element_info.control_type in ("Text", "Button")
            and x.window_text()]


def title(w=None) -> str:
    w = w or main_window()
    for t in w.descendants(control_type="Text"):
        txt = t.window_text()
        if txt.startswith("VOCALOID6 Editor"):
            return txt
    return w.window_text()


def project_name(w=None) -> str | None:
    t = title(w)
    return t[len(SELECTORS["title_prefix"]):] if t.startswith(SELECTORS["title_prefix"]) else None


def on_home_screen(w=None) -> bool:
    w = w or main_window()
    return not any(e.element_info.automation_id == SELECTORS["main_menu"]["auto_id"]
                   for e in w.descendants(control_type="Menu"))


def _menu_path(w, path: list[str], deadline: float | None = None):
    """Open each menu level and invoke the last item (waiting up to 15 s for it to become enabled)."""
    deadline = deadline if deadline is not None else time.time() + 15
    _ensure_idle(w)
    if on_home_screen(w):
        raise VocaloidError("VOCALOID6 shows its Home screen; open or create a project first",
                            "VOCALOID6 がホーム画面です。先にプロジェクトを開くか作成してください")
    top = next((m for m in w.descendants(control_type="MenuItem") if m.window_text() == path[0]), None)
    if top is None:
        raise VocaloidError(f"Menu {path[0]!r} not found (run self_check)", f"メニュー {path[0]!r} が見つかりません（self_check を実行してください）")
    cur = top
    for name in path[1:]:
        item = None
        for _ in range(3):  # a submenu is built when it first opens: expand again if it did not show up
            try:
                cur.expand()
            except Exception:  # noqa: BLE001
                pass
            item = _wait(lambda: next((m for m in cur.descendants(control_type="MenuItem") if m.window_text() == name), None), 2)
            if item:
                break
        if item is None:
            try:
                top.collapse()
            finally:
                raise VocaloidError(f"Menu item {' > '.join(path)} not found (run self_check)",
                                    f"メニュー項目 {' > '.join(path)} が見つかりません（self_check を実行してください）")
        if name == path[-1]:
            if not item.is_enabled():
                top.collapse()
                # VOCALOID6 disables menus for a while after loading a project: try again until it is ready
                if time.time() < deadline:
                    time.sleep(1)
                    return _menu_path(w, path, deadline)
                raise VocaloidError(f"{' > '.join(path)} stayed disabled (VOCALOID6 busy?)",
                                    f"{' > '.join(path)} が使えないままです（VOCALOID6 が処理中？）")
            _invoke(item)
        cur = item
    return cur


def handle_dialogs(w=None, wait: float = 1.5) -> list[dict]:
    """Close the known informational dialogs and report them. Unknown dialogs are reported, not touched."""
    w = w or main_window()
    seen = []
    end = time.time() + wait
    while time.time() < end:
        found = False
        for d in dialogs(w):
            aid = d.element_info.automation_id
            if aid == SELECTORS["voice_changed_dialog"]["auto_id"]:
                rows = [[t.window_text() for t in item.descendants(control_type="Text")]
                        for item in d.descendants(control_type="DataItem")]
                ok = next(b for b in d.descendants(control_type="Button")
                          if b.element_info.automation_id == SELECTORS["voice_changed_dialog"]["ok"])
                _invoke(ok)
                seen.append({"dialog": "voice banks replaced", "replaced": [{"from": r[0], "to": r[1]} for r in rows if len(r) >= 2]})
                found = True
        if not found:
            break
        time.sleep(0.5)
    return seen


def _ensure_idle(w) -> None:
    """Menus are disabled while a modal dialog is open: close the known leftovers, report anything else."""
    handle_dialogs(w, 1)
    for d in dialogs(w):
        text = " ".join(_texts(d))
        if "Revert to the previously saved version" in text:
            _press(d, "OK")
            _wait(lambda: d not in dialogs(w), 5)
            continue
        if d.element_info.automation_id == "xAddTrackDlg":
            # left open e.g. after a failed open (VOCALOID6 then starts a new project); nothing changes until Create
            _press(d, "Cancel")
            _wait(lambda: d not in dialogs(w), 5)
            continue
        if _is_file_dialog(d):
            # a leftover Open/Save dialog (e.g. keys typed into it while a live tool ran): close its message box
            # ("File not found") first, then cancel the dialog itself; nothing is opened or saved
            for box in [c for c in d.children() if c.element_info.control_type == "Window"]:
                _press(box, "OK", "Close")
            _wait(lambda: not [c for c in d.children() if c.element_info.control_type == "Window"], 3)
            _press(d, "Cancel")
            _wait(lambda: d not in dialogs(w), 5)
            continue
        raise VocaloidError(f"A dialog is open in VOCALOID6: {d.window_text()!r} ({text}). Close it first",
                            f"VOCALOID6 でダイアログが開いています: {d.window_text()!r}（{text}）。先に閉じてください")


def _is_file_dialog(d) -> bool:
    return d.element_info.class_name == SELECTORS["file_dialog_class"] and any(
        e.element_info.automation_id in SELECTORS["file_name_edit_ids"] for e in d.descendants(control_type="Edit"))


def _message_box(w):
    for d in dialogs(w):
        if d.element_info.class_name == SELECTORS["file_dialog_class"] and not _is_file_dialog(d):
            return d
    return None


def _press_id(d, *ids) -> bool:
    for b in d.descendants(control_type="Button"):
        if b.element_info.automation_id in ids:
            _invoke(b)
            return True
    return False


def _press(d, *labels) -> bool:
    for b in d.descendants(control_type="Button"):
        if b.window_text().replace("&", "") in labels:
            _invoke(b)
            return True
    return False


def _file_dialog(w, path: str, timeout: float = 15) -> None:
    def find():
        for d in dialogs(w):
            if d.element_info.class_name == SELECTORS["file_dialog_class"]:
                edits = [e for e in d.descendants(control_type="Edit")
                         if e.element_info.automation_id in SELECTORS["file_name_edit_ids"]]
                if edits:
                    return d, edits[0]
        return None
    found = _wait(find, timeout)
    if not found:
        raise VocaloidError("The file dialog did not appear", "ファイルダイアログが表示されませんでした")
    d, edit = found
    path = os.path.normpath(os.path.abspath(path))
    for _ in range(5):
        try:
            edit.set_edit_text(path)
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
            continue
        if edit.get_value() == path:
            break
        time.sleep(0.5)
    else:
        _press(d, "Cancel")
        raise VocaloidError("Could not type the file name into the dialog", "ダイアログにファイル名を入力できませんでした")
    # Windows 11 shows Open as a SplitButton (it has a dropdown), Save as a plain Button
    ok = next((b for b in d.descendants() if b.element_info.control_type in ("Button", "SplitButton")
               and b.element_info.automation_id == SELECTORS["file_dialog_ok_id"]), None)
    if ok is None:
        _press(d, "Cancel")
        raise VocaloidError("The file dialog's Open/Save button was not found (run self_check)",
                            "ファイルダイアログの開く/保存ボタンが見つかりません（self_check を実行してください）")
    _invoke(ok)
    # "replace existing file?" confirmation
    confirm = _wait(lambda: next((x for x in dialogs(w) if x.element_info.class_name == SELECTORS["file_dialog_class"]
                                  and "already exists" in " ".join(_texts(x))), None), 1.5)
    if confirm:
        _press(confirm, "Yes")


def _wait_title(w, stem: str, timeout: float) -> bool:
    return bool(_wait(lambda: project_name(w) == stem, timeout))


def _resolve_unsaved_prompt(w, force: bool) -> bool:
    """When VOCALOID6 asks about unsaved changes: discard if force, else cancel. Returns True if a prompt was seen."""
    box = _wait(lambda: _message_box(w), 2)
    if not box:
        return False
    text = " ".join(_texts(box))
    # message-box button ids (IDNO = 7, IDCANCEL = 2) work whatever the Windows display language; labels are a fallback
    if force:
        if not (_press_id(box, "7") or _press(box, "No", "Don't Save", "Discard") or _press(box, "OK")):
            raise VocaloidError(f"Unexpected dialog: {text}", f"予期しないダイアログ: {text}")
        return True
    _press_id(box, "2") or _press(box, "Cancel")
    raise VocaloidError(
        f"VOCALOID6 has unsaved changes ({text.strip()}). Save them first, or pass force=true to discard them",
        f"VOCALOID6 に未保存の変更があります（{text.strip()}）。先に保存するか、破棄してよければ force=true を指定してください")


# ----------------------------------------------------------------------------- actions (run on the UI thread)

def is_question(box) -> bool:
    """Yes/No prompts (e.g. unsaved changes) have IDYES/IDNO buttons (6/7); ids do not depend on the UI language."""
    return any(b.element_info.automation_id in ("6", "7") for b in box.descendants(control_type="Button"))


def _idle(w, timeout: float = 240) -> bool:
    """True once VOCALOID6's UI thread answers a no-op message (WM_NULL). VOCALOID6 loads a project on that thread,
    so this returns when the load is done or a message box is up (a modal box keeps messages flowing). Checked live
    on small, large, same-name and broken projects."""
    import ctypes
    u = _win32()
    try:
        hwnd = w.handle
    except Exception:  # noqa: BLE001 - a stale element: nothing left to wait for
        return True
    if not hwnd or not u.IsWindow(hwnd):  # the window is gone: nothing left to wait for
        return True
    if u.SendMessageTimeoutW(hwnd, 0, 0, 0, 0, int(timeout * 1000), ctypes.byref(ctypes.c_size_t())):
        return True
    return ctypes.get_last_error() != 1460  # only ERROR_TIMEOUT means busy; a window destroyed meanwhile is not


def _message(box) -> str:
    """A message box's text without its button labels."""
    return " ".join(e.window_text() for e in box.descendants(control_type="Text") if e.window_text())


def _asks_about(text: str, name: str | None) -> bool:
    """The unsaved-changes prompt quotes the open project's name, e.g. 'Do you want to save "Untitled"?'."""
    return bool(name) and any(f"{a}{name}{b}" in text for a, b in ('""', "“”", "「」", "『』", "''"))


def _answer_unsaved(w, box, text: str, before: str | None, force: bool) -> None:
    """The unsaved-changes question (it quotes the open project's name) is answered as _resolve_unsaved_prompt does;
    any other question is left to the user."""
    if not _asks_about(text, before):
        raise VocaloidError(f"VOCALOID6 is asking: {text}. Answer it in VOCALOID6, then call vocaloid_status",
                            f"VOCALOID6 が質問しています: {text}。VOCALOID6 で答えてから vocaloid_status を呼んでください")
    _resolve_unsaved_prompt(w, force)  # raises unless force


def busy_error() -> VocaloidError:
    return VocaloidError("VOCALOID6 is still busy after 4 minutes; call vocaloid_status later",
                         "VOCALOID6 が4分たっても処理中です。しばらくしてから vocaloid_status を呼んでください")


def _gone(w, box) -> bool:
    try:
        return box not in dialogs(w)
    except Exception:  # noqa: BLE001 - the window itself is gone, and its boxes with it
        return True


def _alive(w) -> bool:
    try:
        return bool(_win32().IsWindow(w.handle))
    except Exception:  # noqa: BLE001 - a stale element
        return False


def _stuck_error(text: str) -> VocaloidError:
    return VocaloidError(f"VOCALOID6 shows a box this server cannot close: {text}. Close it in VOCALOID6",
                         f"このサーバーで閉じられないボックスがあります: {text}。VOCALOID6 で閉じてください")


def exited_error() -> VocaloidError:
    return VocaloidError("VOCALOID6 exited while starting or loading", "VOCALOID6 が起動中か読み込み中に終了しました")


def still_loading_error() -> VocaloidError:
    return VocaloidError("VOCALOID6 is still starting or loading; call vocaloid_status in a moment",
                         "VOCALOID6 はまだ起動中か読み込み中です。少ししてから vocaloid_status を呼んでください")


def settle(w):
    """Wait for a load to end: VOCALOID6 idle, then, when it loaded from the separate Home window, the editor that
    replaces it (may take a while once the Home window is gone; 10 s with it still up means nothing is loading).
    Returns the main window."""
    if not _idle(w):  # the load runs on VOCALOID6's UI thread
        raise busy_error()
    procs = processes()  # checked by PID while waiting: listing every process each poll is slow

    def gone():
        return not any(p.is_running() for p in procs)
    start = time.time()
    _wait(lambda: gone() or is_editor(main_window(required=False)) or _message_box(w)
          or (_alive(w) and time.time() - start > 10), 120)
    if gone():
        raise exited_error()
    w = main_window(required=False)
    if w is None:  # running, but the editor has not replaced the Home window yet
        raise still_loading_error()
    return w


def finish_load(w, path: str, force: bool = False, before: str | None = None) -> tuple[list[dict], object]:
    """After the file dialog: wait until VOCALOID6 is idle, then deal with its message boxes. OK boxes are closed (a
    broken file gives two in a row); the unsaved-changes question is answered as _resolve_unsaved_prompt does (the
    load starts after it); any other question is left to the user. Returns the OK boxes as notes if the project
    opened anyway (a box may be only a warning), with the main window as it is now (the editor may have replaced the
    Home window); else raises with their text."""
    stem = os.path.splitext(os.path.basename(path))[0]
    msgs, last = [], None
    for _ in range(12):  # each box takes a pass, plus one if it is slow to close
        if not _idle(w):
            raise busy_error()
        box = _wait(lambda: _message_box(w), 0.5)  # also a box posted just after the load
        if not box:
            break
        text = _message(box)
        if box == last:  # answered last pass and still there once VOCALOID6 is idle again
            if not _wait(lambda: _gone(w, box), 2):
                raise _stuck_error(text)
            continue
        if is_question(box):
            _answer_unsaved(w, box, text, before, force)  # raises unless it is the unsaved prompt and force
        else:
            msgs.append(text)
            _press_id(box, "1", "2") or _press(box, "OK", "Close")  # IDOK / an OK-only box's single button
        last = box
    else:  # out of passes: only a failure if a box is still up once VOCALOID6 is idle
        if not _idle(w):
            raise busy_error()
        box = _wait(lambda: _message_box(w), 0.5)
        if box:
            raise _stuck_error(" / ".join(msgs + [_message(box)]))
    w = main_window()  # once: opening from the Home window may have replaced it
    _idle(w)
    # a failed load makes VOCALOID6 start a new project, so the title shows it even when the old one had the same name
    # (a title that cannot be read is not taken as that switch)
    if _wait_title(w, stem, 3) and not (msgs and _wait(lambda: project_name(w) not in (None, stem), 2)):
        return [{"dialog": "message", "text": m} for m in msgs], w
    now = project_name(w)
    en = f"{' / '.join(msgs)}; " if msgs else ""
    ja = f"{' / '.join(msgs)}。" if msgs else ""
    raise VocaloidError(f"VOCALOID6 did not open {path} ({en}open now: {now or 'the Home screen'})",
                        f"VOCALOID6 で {path} を開けませんでした（{ja}現在: {now or 'ホーム画面'}）")


def open_project(path: str, force: bool = False) -> dict:
    w = main_window()
    before = project_name(w)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise VocaloidError(f"File not found: {path}", f"ファイルが見つかりません: {path}")
    if on_home_screen(w):
        btn = next((t.parent() for t in w.descendants(control_type="Text") if t.window_text() == SELECTORS["home_open_text"]), None)
        if btn is None:
            raise VocaloidError("Home screen OPEN button not found (run self_check)", "ホーム画面の OPEN ボタンが見つかりません")
        _invoke(btn)
    else:
        _menu_path(w, ["File", "Open..."])
        # VOCALOID6 may ask about unsaved changes before or after the file dialog
        _wait(lambda: any(d.element_info.class_name == SELECTORS["file_dialog_class"] for d in dialogs(w)), 5)
        box = _message_box(w)
        if box and is_question(box):
            _answer_unsaved(w, box, _message(box), before, force)
            if not _wait(lambda: _gone(w, box), 3):  # nothing loads yet here, so the box closes at once
                raise _stuck_error(_message(box))
        elif box:
            raise VocaloidError(f"VOCALOID6 shows: {_message(box)}. Close it in VOCALOID6, then try again",
                                f"VOCALOID6 の表示: {_message(box)}。VOCALOID6 で閉じてから、もう一度試してください")
    _file_dialog(w, path)
    _wait(lambda: not any(_is_file_dialog(d) for d in dialogs(w)), 30)
    w = settle(w)
    events = handle_dialogs(w, 3)
    notes, w = finish_load(w, path, force, before)
    events += notes + handle_dialogs(w, 2)
    return {"opened": path, "dialogs": events}


def save() -> dict:
    w = main_window()
    name = project_name(w)
    if not name or name == "Untitled":
        raise VocaloidError("The project has never been saved: call save_project with a path",
                            "プロジェクトがまだ保存されていません。path を指定して save_project を呼んでください")
    _menu_path(w, ["File", "Save"])
    time.sleep(0.5)
    if any(d.element_info.class_name == SELECTORS["file_dialog_class"] for d in dialogs(w)):
        for d in dialogs(w):
            _press(d, "Cancel")
        raise VocaloidError("VOCALOID6 asked where to save: call save_project with a path",
                            "VOCALOID6 が保存先を求めました。path を指定して save_project を呼んでください")
    return {"saved": name}


def save_as(path: str) -> dict:
    w = main_window()
    path = os.path.abspath(path)
    if not path.lower().endswith(".vpr"):
        raise VocaloidError("VOCALOID6 saves .vpr files", "VOCALOID6 は .vpr 形式で保存します")
    before = os.path.getmtime(path) if os.path.exists(path) else None
    _menu_path(w, ["File", "Save As..."])
    _file_dialog(w, path)
    ok = _wait(lambda: os.path.exists(path) and os.path.getmtime(path) != before, 20)
    stem = os.path.splitext(os.path.basename(path))[0]
    if not ok or not _wait_title(w, stem, 5):
        raise VocaloidError(f"Saving to {path} did not finish", f"{path} への保存が完了しませんでした")
    return {"saved": path}


def revert() -> dict:
    """Reload the project from disk (File > Revert, confirmed)."""
    w = main_window()
    _menu_path(w, ["File", "Revert"])
    for _ in range(3):  # press OK until the confirmation is really gone
        box = _wait(lambda: _message_box(w), 5)
        if not box:
            break
        _press(box, "OK", "Yes")
        if _wait(lambda: _message_box(w) is None, 5):
            break
    events = handle_dialogs(w, 5)
    return {"reverted": project_name(w), "dialogs": events}


def play() -> dict:
    w = main_window()
    b = next((e for e in w.descendants(control_type="RadioButton")
              if e.element_info.automation_id == SELECTORS["play_button"]["auto_id"]), None)
    if b is None:
        raise VocaloidError("Play button not found (run self_check)", "再生ボタンが見つかりません（self_check を実行してください）")
    b.select()
    return {"playing": True}


def stop() -> dict:
    w = main_window()
    b = next((e for e in w.descendants(control_type="Button")
              if e.element_info.automation_id == SELECTORS["stop_button"]["auto_id"]), None)
    if b is None:
        raise VocaloidError("Stop button not found (run self_check)", "停止ボタンが見つかりません（self_check を実行してください）")
    _invoke(b)
    return {"playing": False}


def _by_id(d, aid):
    return next((e for e in d.descendants() if e.element_info.automation_id == aid), None)


def _pick_combo(combo, want: str) -> str:
    """Select the combo box item whose text contains want; returns that text. Raises with the offered texts."""
    combo.expand()
    items = _wait(lambda: combo.descendants(control_type="ListItem"), 3) or []
    texts = [" ".join(t.window_text() for t in i.descendants(control_type="Text")) or i.window_text() for i in items]
    hit = next((i for i, t in zip(items, texts) if want in t.replace(" ", "")), None)
    if hit is None:
        combo.collapse()
        raise VocaloidError(f"{want} not offered: {texts}", f"{want} は選べません: {texts}")
    hit.select()
    combo.collapse()
    return texts[items.index(hit)]


def export_wav(path: str, bypass_effects: bool = False, timeout: float = 600, bit_depth: int | None = None) -> dict:
    w = main_window()
    path = os.path.abspath(path)
    if not path.lower().endswith(".wav"):
        raise VocaloidError("Output must be a .wav file", "出力ファイルは .wav にしてください")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    sel = SELECTORS["mixdown_dialog"]
    _menu_path(w, ["File", "Audio Mixdown..."])
    d = _wait(lambda: next((x for x in dialogs(w) if x.element_info.automation_id == sel["auto_id"]), None), 10)
    if not d:
        raise VocaloidError("Audio Mixdown dialog did not open", "オーディオミックスダウンのダイアログが開きませんでした")
    main = _by_id(d, sel["main"])
    if main:
        main.select()
    for key, want in (("open_folder", False), ("bypass", bypass_effects)):
        cb = _by_id(d, sel[key])
        if cb and bool(cb.get_toggle_state()) != want:
            cb.toggle()
    depth = None
    if bit_depth is not None:
        combo = _by_id(d, sel["bit_depth"])
        if combo is None:
            raise VocaloidError("Bit depth box not found in Audio Mixdown (run self_check)",
                                "オーディオミックスダウンにビット深度の欄が見つかりません（self_check を実行してください）")
        depth = _pick_combo(combo, str(int(bit_depth)))
    _invoke(_by_id(d, sel["ok"]))
    t0 = time.time()
    _file_dialog(w, path)
    done = _wait(lambda: os.path.exists(path) and not dialogs(w) and os.path.getsize(path) > 44, timeout, 1)
    if not done:
        raise VocaloidError(f"WAV export did not finish within {timeout}s", f"WAV の書き出しが {timeout} 秒以内に終わりませんでした")
    time.sleep(1)
    out = {"wav": path, "bytes": os.path.getsize(path), "seconds": round(time.time() - t0, 1)}
    if depth:
        out["bit_depth"] = depth
    return out


def export_midi(path: str) -> dict:
    w = main_window()
    path = os.path.abspath(path)
    if os.path.exists(path):
        os.remove(path)
    _menu_path(w, ["File", "Export MIDI..."])
    _file_dialog(w, path)
    if not _wait(lambda: os.path.exists(path) and not dialogs(w), 30):
        raise VocaloidError("MIDI export did not finish", "MIDI の書き出しが完了しませんでした")
    return {"midi": path, "bytes": os.path.getsize(path)}


def import_midi(path: str, track_type: str = "ai", tempo: bool = True) -> dict:
    w = main_window()
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise VocaloidError(f"File not found: {path}", f"ファイルが見つかりません: {path}")
    sel = SELECTORS["smf_import_dialog"]
    _menu_path(w, ["File"] + SELECTORS["import_midi"])
    _file_dialog(w, path)
    d = _wait(lambda: next((x for x in dialogs(w) if x.element_info.automation_id == sel["auto_id"]), None), 10)
    if not d:
        box = _message_box(w)
        msg = " ".join(_texts(box)) if box else "no dialog"
        if box:
            _press(box, "OK")
        raise VocaloidError(f"MIDI import failed: {msg}", f"MIDI の読み込みに失敗しました: {msg}")
    cb = _by_id(d, sel["tempo"])
    if cb and bool(cb.get_toggle_state()) != tempo:
        cb.toggle()
    combo = _by_id(d, sel["track_type"])
    combo.expand()
    items = _wait(lambda: combo.descendants(control_type="ListItem"), 3) or []
    want = "VOCALOID:AI" if track_type == "ai" else "VOCALOID"
    item = next((i for i in items if [t.window_text() for t in i.descendants(control_type="Text")] == [want]), None)
    if item is None:
        combo.collapse()
        raise VocaloidError(f"Track type {want} not offered", f"トラック種別 {want} が選べません")
    item.select()
    combo.collapse()
    _invoke(_by_id(d, sel["ok"]))
    time.sleep(2)
    return {"imported": path, "dialogs": handle_dialogs(w, 3)}


def recent_paths() -> list[str]:
    """Paths in File > Open Recent. WPF hides the first '_' of each (it marks a shortcut key), so names are
    matched against the real files on disk."""
    w = main_window()
    _menu_path(w, ["File", "Open Recent..."])
    items = _wait(lambda: [m.window_text() for m in w.descendants(control_type="MenuItem") if "\\" in m.window_text()], 3) or []
    top = next(m for m in w.descendants(control_type="MenuItem") if m.window_text() == "File")
    top.collapse()
    out = []
    for shown in items:
        if os.path.isfile(shown):
            out.append(shown)
            continue
        folder, name = os.path.split(shown)
        try:
            real = [f for f in os.listdir(folder) if f.replace("_", "", 1) == name]
        except OSError:
            real = []
        if len(real) == 1:
            out.append(os.path.join(folder, real[0]))
    return out


def self_check() -> dict:
    """Which selectors still match the running VOCALOID6."""
    w = main_window()
    report: dict = {"home_screen": on_home_screen(w), "missing": [], "found": []}
    if report["home_screen"]:
        report["note"] = "Open a project to check the menus / メニューを確認するにはプロジェクトを開いてください"
        return report
    for top, items in SELECTORS["menu"].items():
        m = next((x for x in w.descendants(control_type="MenuItem") if x.window_text() == top), None)
        if m is None:
            report["missing"].append(top)
            continue
        m.expand()
        names = set(_wait(lambda: [x.window_text() for x in m.descendants(control_type="MenuItem")], 3) or [])
        m.collapse()
        for it in items:
            (report["found"] if it in names else report["missing"]).append(f"{top} > {it}")
    for key in ("play_button", "stop_button"):
        aid = SELECTORS[key]["auto_id"]
        (report["found"] if any(e.element_info.automation_id == aid for e in w.descendants()) else report["missing"]).append(aid)
    report["ok"] = not report["missing"]
    return report
