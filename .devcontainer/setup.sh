#!/usr/bin/env bash
# Codespaces install: the documented path, plus the one thing a devcontainer
# image does not ship.
#
# This deliberately calls the repo's own setup.sh rather than reimplementing it,
# so a codespace is a test of the install path a reader is told to use. The only
# extra is ffmpeg; without it episodes cannot record video and a few tests
# skip instead of run.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> ffmpeg"
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg

echo "==> the repo's own install"
bash setup.sh
