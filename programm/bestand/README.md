# Bestand- und Nachbestellungen — Excel-Tooling

Aktualisiert die Excel-Bestands- und Nachbestellungsliste aus der IServ-Ausleihe-API
(rein lesend, nur GET).

## Für Nachfolger — nur dieses Skript verwenden

| Pfad | Status | Verwendung |
|------|--------|------------|
| **`update_bestand_auto.py`** | ✅ **aktuell** | **Das einzige Skript, das Nachfolger brauchen.** Auto-Discovery: liest die Excel-Struktur selbst aus; `config.json` enthält nur Datei-/Blatt-Defaults, Sicherheitsbestand und explizite Konflikt-Overrides. |

> Die beiden abgelösten Vorgänger (`update_bestand.py` mit von Hand gepflegten
> ISBN↔Zellen-Mappings und der Webscraper `Old - Webscraper for Excel/`) sind
> entfernt; sie stehen nur noch in der Git-Historie.

## Schnellstart (für Nachfolger)

```bash
cd bestand
# 1) Erst prüfen, ohne zu schreiben (Trockenlauf):
python3 update_bestand_auto.py --dry-run --excel "Bestand- und Nachbestellungsliste 2026.xlsx" -v

# 2) Wenn alles plausibel aussieht, wirklich ausführen:
python3 update_bestand_auto.py --excel "Bestand- und Nachbestellungsliste 2026.xlsx"
```

Automatische Zuordnung ist absichtlich fail-closed: Wenn ein Fach mehrere
Bücher treffen kann oder die Tabellenstruktur unvollständig ist, wird nichts
gespeichert. Den im Bericht genannten Schlüssel in `match_overrides` der
`config.json` auf die gewünschte ISBN setzen und den Trockenlauf wiederholen.
`safety_stock` (Standard: 5) ist ebenfalls dort oder über `--safety-stock`
konfigurierbar. Erfolgreiche Läufe erstellen standardmäßig eine zeitgestempelte
Kopie im Unterordner `backups/`; nur bei bewusstem Risiko `--no-backup` nutzen.

Voraussetzungen: das Geschwister-Repo `ausleihe-api` liegt **neben** diesem Repo
und enthält eine `.env` mit den IServ-Zugangsdaten. Abhängigkeiten via `uv sync`
im `sba-bestand`-Root (siehe `../README.md`).

Die vollständige Anleitung für Nachfolger (inkl. Ersteinrichtung und typischer
Fehler) liegt im Schwester-Projekt unter
`ausleihe-ausgabe/docs/nachfolge-anleitung.md` (Teil 3).

## Wichtiger Hinweis zur Lebensdauer

Das Skript greift auf die IServ-Ausleihe-API zu, die nicht offiziell dokumentiert ist
und sich jederzeit ändern kann. Wenn die IServ-Website/API aktualisiert wird, kann
das Skript Buchreihen nicht mehr korrekt zuordnen (insbesondere bei neuen oder
umbenannten Fächern). Das ist kein Fehler der Anwenderin/des Anwenders — siehe
Fehler-Abschnitt in der Nachfolge-Anleitung.
