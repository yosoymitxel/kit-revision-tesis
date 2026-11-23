#!/usr/bin/env bash
# Linux / macOS: ./revisar.sh   (o ./revisar.sh limpiar)
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
[ -f .venv/.instalado ] || { .venv/bin/python -m pip install -q -r requirements.txt && touch .venv/.instalado; }
if [ "$1" = "limpiar" ]; then .venv/bin/python -m kit.limpiar; else .venv/bin/python -m kit.revisar "$@"; fi
