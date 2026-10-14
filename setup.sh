#!/usr/bin/env bash
# One command from a fresh clone to a working install.
#
# REA's README opens with `npx rea-agents setup`, and that is the right shape:
# the first thing a reader should see is the thing that makes it work, not a
# list of prerequisites. This is the same idea without an npm package.
#
# It is idempotent. Running it twice is fine, and it will not clobber an
# existing virtualenv.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python not found. Install Python 3.11+ and re-run, or set PYTHON=/path/to/python" >&2
  exit 1
fi

echo "==> virtualenv"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi

# Windows (Git Bash / MSYS) puts the interpreter in Scripts, POSIX in bin.
if [ -x .venv/Scripts/python.exe ]; then
  VENV_PY=".venv/Scripts/python.exe"
else
  VENV_PY=".venv/bin/python"
fi

echo "==> dependencies"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet playwright pillow

echo "==> chromium (about 150 MB, once)"
"$VENV_PY" -m playwright install chromium

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "!! ffmpeg is not on PATH. Episodes record video, and ffmpeg converts it"
  echo "   to the mp4 the schema specifies. Everything else works without it."
fi

echo
echo "==> checking the published result, no model and no credentials"
"$VENV_PY" reproduce.py

cat <<'EOF'

Ready.

  record a workflow    .venv/Scripts/python.exe record_session.py --url <page> --episode <name>
  induce a skill       .venv/Scripts/python.exe run_induct.py --episode <name> --interactive
  run that skill       .venv/Scripts/python.exe run_skill.py --skill <dir> --url <page>                            --instruction "<the goal>"
  score a replay       .venv/Scripts/python.exe run_macro.py --variant default

Induction needs a model endpoint:

  export S2S_INDUCT_BASE_URL=https://api.example.com/v1
  export S2S_INDUCT_API_KEY=...
  export S2S_INDUCT_MODEL=...

Everything else -- recording, replaying, scoring, and the whole benchmark --
runs without one.
EOF
