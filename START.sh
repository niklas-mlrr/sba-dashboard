#!/usr/bin/env bash
# Schulbuchausleihe Dashboard auf macOS oder Linux starten.
#
# Diese Datei arbeitet absichtlich mit einer lokalen Kopie der Excel-Mappe.
# Die Originaldatei unter ../sba-bestand/bestand/ wird nie beschrieben.
set -euo pipefail

WURZEL="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL="${SBA_ORIGINAL_EXCEL:-$WURZEL/../sba-bestand/bestand/Bestand- und Nachbestellungsliste 2026.xlsx}"
ARBEITSORDNER="${SBA_ARBEITSORDNER:-$WURZEL/.local}"
MAPPE="$ARBEITSORDNER/Bestand- und Nachbestellungsliste 2026.xlsx"
KONFIGURATION="$ARBEITSORDNER/config.json"

echo "Schulbuchausleihe - Bestand und Nachbestellung"
echo

if ! command -v uv >/dev/null 2>&1; then
    echo "uv wurde nicht gefunden. Auf dem Mac einmal ausführen: brew install uv"
    exit 1
fi

if [[ ! -f "$ORIGINAL" ]]; then
    echo "Die Quellmappe wurde nicht gefunden:"
    echo "  $ORIGINAL"
    echo
    echo "Lege sba-bestand neben sba-dashboard ab oder setze SBA_ORIGINAL_EXCEL"
    echo "auf den Pfad zur Originalmappe."
    exit 1
fi

mkdir -p "$ARBEITSORDNER"
if [[ ! -f "$MAPPE" ]]; then
    cp -p -- "$ORIGINAL" "$MAPPE"
    echo "Arbeitskopie angelegt: $MAPPE"
else
    echo "Vorhandene Arbeitskopie wird weiterverwendet: $MAPPE"
fi

# Übernimmt Domain, Blattname und Schutzwerte aus der ausgelieferten config,
# ersetzt aber ausschließlich die Windows-Pfade durch die Arbeitskopie.
uv run --project "$WURZEL" python - "$WURZEL/config.json" "$MAPPE" "$KONFIGURATION" <<'PY'
import json
import sys
from pathlib import Path

vorlage, mappe, ziel = map(Path, sys.argv[1:])
daten = json.loads(vorlage.read_text(encoding="utf-8"))
daten["excel_pfad_kandidaten"] = [str(mappe)]
ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo
echo "Die Seite öffnet sich gleich im Browser. Dieses Terminal offen lassen."
echo "Arbeitsmappe: $MAPPE"
echo
exec uv run --project "$WURZEL" python -m app.start --config "$KONFIGURATION"
