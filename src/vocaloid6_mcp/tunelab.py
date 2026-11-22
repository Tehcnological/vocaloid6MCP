"""Optional TuneLab integration: find TuneLab's command line and ask which VOCALOID6 voices it can sing.

TuneLab only sings VOCALOID6 voices with a VOCALOID6 voice extension for TuneLab, installed separately. Everything
here is best-effort: without TuneLab (or without that extension) the VOCALOID6-only workflow is unaffected.
"""

import json
import os
import shutil
import subprocess

ENGINE = "VOCALOID6"
NO_EXTENSION_HINT = ("TuneLab has no VOCALOID6 voice engine: the TuneLab route needs a VOCALOID6 voice extension for "
                     "TuneLab, installed separately. The VOCALOID6-only workflow works without it. / TuneLab に VOCALOID6 "
                     "の音声エンジンがありません。TuneLab で使うには別途 TuneLab 用の VOCALOID6 音声拡張が必要です。"
                     "VOCALOID6 だけの作業にはなくても問題ありません。")


def find_cli() -> str | None:
    """TUNELAB_CLI if set (a missing file there means: treat TuneLab as absent), else the per-user install, else PATH."""
    override = os.environ.get("TUNELAB_CLI")
    if override is not None:
        return override if os.path.isfile(override) else None
    default = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "TuneLab", "TuneLab.Cli.exe")
    if os.path.isfile(default):
        return default
    return shutil.which("TuneLab.Cli")  # not "tunelab": PATHEXT would pick the editor, TuneLab.exe


def status() -> dict:
    """Fast: no process is started."""
    cli = find_cli()
    return {"installed": cli is not None, "cli": cli}


def _run(cmd: list[str], timeout: float) -> tuple[int, str, str]:
    """(exit code, stdout, stderr). stderr is kept apart so log lines cannot break the JSON on stdout."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # kill the whole tree: a wrapper's child would otherwise hold the pipe open
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass  # a grandchild still holds the pipe: give up on it rather than hang
        raise
    return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


def engines(timeout: float = 30) -> dict:
    """Ask TuneLab (headless) whether it has the VOCALOID6 voice engine and how many voices it lists."""
    cli = find_cli()
    if cli is None:
        return {"installed": False}
    try:
        code, out, err = _run([cli, "--headless", "--json", "source", "list", "--engine", ENGINE], timeout)
    except subprocess.TimeoutExpired:
        return {"installed": True, "error": f"TuneLab did not answer within {timeout:g} s / TuneLab が {timeout:g} 秒以内に応答しませんでした"}
    except OSError as e:
        return {"installed": True, "error": f"TuneLab could not be started: {e} / TuneLab を起動できません: {e}"}
    start = out.find("{")
    if code != 0 and f'"{ENGINE}"' in out + err:  # TuneLab: no engine with type id "VOCALOID6"
        return {"installed": True, "vocaloid6_engine": False, "voices": 0, "hint": NO_EXTENSION_HINT}
    if code != 0 or start < 0:
        last = ((err.strip() or out.strip()).splitlines() or ["(no output)"])[-1]
        return {"installed": True, "error": f"TuneLab exited with {code}: {last} / TuneLab がエラー {code} で終了: {last}"}
    try:
        data = json.loads(out[start:])
    except ValueError:
        return {"installed": True, "error": "TuneLab returned unreadable output / TuneLab の出力を読めません"}
    loaded = bool(data.get("loaded", True))
    result = {"installed": True, "vocaloid6_engine": loaded, "voices": int(data.get("total", len(data.get("sources", []))))}
    if not loaded:
        result["hint"] = NO_EXTENSION_HINT
    return result
