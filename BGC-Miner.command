#!/bin/bash
# =====================================================================
#  BGC-Miner - Ein-Klick-Start (macOS / Linux). Doppelklick (macOS) oder
#  im Terminal ausfuehren. Startet die App und oeffnet die Oberflaeche.
#  Hinweis macOS: einmalig "chmod +x BGC-Miner.command" ausfuehren.
# =====================================================================
cd "$(dirname "$0")" || exit 1
PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
command -v $PY >/dev/null 2>&1 || { echo "Python 3 nicht gefunden. Bitte installieren: https://www.python.org/downloads/"; read -r _; exit 1; }
echo "Starte BGC Miner ... Fenster bitte offen lassen. Browser oeffnet sich automatisch."
# Einem Netzwerk beitreten: SEED setzen, z.B.  SEED=1.2.3.4:9333
SEED=""
if [ -n "$SEED" ]; then exec "$PY" bgc_app.py --peers "$SEED" "$@"; else exec "$PY" bgc_app.py "$@"; fi
