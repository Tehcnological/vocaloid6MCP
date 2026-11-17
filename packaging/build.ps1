# Builds dist\vocaloid6-mcp.exe: the whole server in one Windows .exe (no Python needed to run it).
# Needs uv (https://docs.astral.sh/uv/). From the repo root:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root
$venv = "$root\.build\venv"

uv venv -q -p 3.11 --clear $venv
if ($LASTEXITCODE) { throw "uv venv failed" }
uv pip install -q -p $venv ".[kanji]"
if ($LASTEXITCODE) { throw "uv pip install failed" }
# What goes into the exe, before the build tools are added (local package lines would carry local paths)
$packages = uv pip freeze -p $venv | Where-Object { $_ -notmatch ' @ file:' }
uv pip install -q -p $venv "pyinstaller==6.22.3"
if ($LASTEXITCODE) { throw "uv pip install failed" }

& "$venv\Scripts\pyinstaller.exe" --onefile --noconfirm --clean --log-level WARN -n vocaloid6-mcp `
    --collect-data pykakasi --add-data "$root\skill\SKILL.md;vocaloid6_mcp" `
    --distpath "$root\dist" --workpath "$root\.build\pyinstaller" --specpath "$root\.build" `
    "$root\packaging\entry.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# The exe contains pykakasi (GPL-3.0-or-later), so it ships with that license text and a note that says so.
$gpl = Get-ChildItem "$venv\Lib\site-packages\pykakasi-*.dist-info" -Recurse -Filter COPYING | Select-Object -First 1
if (-not $gpl) { throw "pykakasi's COPYING file was not found in the build venv" }
Copy-Item $gpl.FullName "$root\dist\GPL-3.0.txt" -Force
Copy-Item "$root\packaging\EXE-LICENSE.md" "$root\dist\" -Force
# Record exactly what went into the exe, next to it.
$packages | Out-File -Encoding utf8 "$root\dist\vocaloid6-mcp-packages.txt"
Get-FileHash "$root\dist\vocaloid6-mcp.exe" -Algorithm SHA256 | ForEach-Object { "$($_.Hash)  vocaloid6-mcp.exe" } |
    Out-File -Encoding ascii "$root\dist\SHA256SUMS.txt"
Write-Host "Built $root\dist\vocaloid6-mcp.exe"
