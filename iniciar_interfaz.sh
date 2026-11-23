#!/usr/bin/env bash
# Inicia el servidor del Centro de Control y abre la interfaz web
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python -m kit.servidor
