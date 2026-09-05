#!/usr/bin/env bash
# Schulbuchausleihe Dashboard auf macOS oder Linux starten.
#
# Diese Datei arbeitet absichtlich mit einer lokalen Kopie der Excel-Mappe.
# Ohne SBA_ORIGINAL_EXCEL kommt die mitgelieferte, leere Vorlage zum Einsatz.
#
# Die Arbeitskopie liegt im Projektordner selbst, nicht in einem versteckten
# Unterordner: wer sie in Excel öffnen will, soll sie im Dateimanager sehen,
# ohne erst "versteckte Dateien anzeigen" einzuschalten. Bis 2026-09-05 war das
# ".local/", und genau daran ist sie niemandem aufgefallen. Beides - Mappe und
# die Konfiguration, die auf sie zeigt - steht in .gitignore.
set -euo pipefail

WURZEL="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VORLAGE="$WURZEL/vorlage/Bestand- und Nachbestellungsliste 2026.xlsx"
QUELLE="${SBA_ORIGINAL_EXCEL:-$VORLAGE}"
ARBEITSORDNER="${SBA_ARBEITSORDNER:-$WURZEL}"
MAPPE="$ARBEITSORDNER/Bestand- und Nachbestellungsliste 2026.xlsx"
# NICHT "config.json": das ist der ausgelieferte Standard, aus dem die Zeile
# unten Domain, Blattname und Schutzwerte übernimmt. Läge die erzeugte Datei
# unter demselben Namen, überschriebe der erste Lauf im Projektordner die
# Quelle, aus der er gerade gelesen hat.
KONFIGURATION="$ARBEITSORDNER/config.local.json"

echo "Schulbuchausleihe - Bestand und Nachbestellung"
echo

if ! command -v uv >/dev/null 2>&1; then
    echo "uv wurde nicht gefunden. Auf dem Mac einmal ausführen: brew install uv"
    exit 1
fi

if [[ ! -f "$QUELLE" ]]; then
    echo "Die Quellmappe wurde nicht gefunden:"
    echo "  $QUELLE"
    echo
    echo "Die Git-Vorlage fehlt. Bitte den Clone erneut vollständig laden."
    echo "Für eine echte Mappe SBA_ORIGINAL_EXCEL auf ihren Pfad setzen."
    exit 1
fi

mkdir -p "$ARBEITSORDNER"
if [[ ! -f "$MAPPE" ]]; then
    cp -p -- "$QUELLE" "$MAPPE"
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
