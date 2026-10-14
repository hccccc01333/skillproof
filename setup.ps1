# One command from a fresh clone to a working install, on Windows without Git
# Bash. The same steps as setup.sh, for people who do not have a POSIX shell.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

Write-Host '==> virtualenv'
if (-not (Test-Path '.venv')) {
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "could not create a virtualenv. Install Python 3.11+ and re-run, or set `$env:PYTHON."
        exit 1
    }
}

$venvPy = Join-Path '.venv' 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) { $venvPy = Join-Path '.venv' 'bin/python' }

Write-Host '==> dependencies'
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements.txt

Write-Host '==> chromium (about 150 MB, once)'
& $venvPy -m playwright install chromium

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ''
    Write-Host '!! ffmpeg is not on PATH. Episodes record video, and ffmpeg converts it'
    Write-Host '   to the mp4 the schema specifies. Everything else works without it.'
}

Write-Host ''
Write-Host '==> checking the published result, no model and no credentials'
& $venvPy reproduce.py

Write-Host @'

Ready.

  record a workflow    .venv\Scripts\python.exe record_session.py --url <page> --episode <name>
  induce a skill       .venv\Scripts\python.exe run_induct.py --episode <name> --interactive
  run that skill       .venv\Scripts\python.exe run_skill.py --skill <dir> --url <page> --instruction "<the goal>"
  score a replay       .venv\Scripts\python.exe run_macro.py --variant default

Induction needs a model endpoint:

  $env:S2S_INDUCT_BASE_URL = 'https://api.example.com/v1'
  $env:S2S_INDUCT_API_KEY  = '...'
  $env:S2S_INDUCT_MODEL    = '...'

Everything else -- recording, running a skill, replaying, scoring, and the whole
benchmark -- runs without one.
'@
