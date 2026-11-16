"""Windows folders that MCP clients may leave out of the server's environment."""

import os


def known_dir(env: str, reg_value: str, default: str) -> str:
    """A Windows folder from its environment variable, else the registry, else <SystemDrive>\\default: MCP clients
    often start servers with a short environment that has no ProgramFiles or CommonProgramFiles."""
    if os.environ.get(env):
        return os.environ[env]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion") as k:
            return winreg.QueryValueEx(k, reg_value)[0]
    except (ImportError, OSError):
        return os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, default)
