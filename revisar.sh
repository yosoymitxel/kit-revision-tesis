#!/usr/bin/env bash
# Linux / macOS: ./revisar.sh   (o ./revisar.sh limpiar)
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
cmp -s requirements.txt .venv/.instalado || { .venv/bin/python -m pip install -q -r requirements.txt && cp requirements.txt .venv/.instalado; }
if [ "$1" = "limpiar" ]; then .venv/bin/python -m kit.limpiar; else .venv/bin/python -m kit.revisar "$@"; fi
