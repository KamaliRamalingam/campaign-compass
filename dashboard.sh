#!/usr/bin/env bash
# Local dashboard runner (T8). Run it with:
#   bash dashboard.sh
# Run `bash run.sh` first so the result tables exist. Creates
# .venv if missing, installs requirements.txt and
# requirements-dashboard.txt, then starts the Streamlit app.
# Local only: no hosting, login, uploads or network access.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q -r requirements-dashboard.txt
.venv/bin/streamlit run dashboard/app.py
