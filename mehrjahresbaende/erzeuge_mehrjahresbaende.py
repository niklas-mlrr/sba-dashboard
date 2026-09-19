#!/usr/bin/env python3
"""Die Mehrjahresbände-Übersicht aus zwei Schuljahren erzeugen und als .xlsx ablegen.

Vergleicht alle Jahrgangs-Bücherlisten des abgelaufenen Schuljahres mit denen
des laufenden und schreibt daraus die Matrix Jahrgang × Fach, die bisher von
Hand gepflegt wurde. Rein lesend gegenüber IServ (nur GET).

Dieselbe Arbeit macht der Reiter „Mehrjahresbände" im Dashboard; dieses Skript
ist der Weg ohne Oberfläche - für einen Rechner ohne Browser und als Notnagel,
wenn am Dashboard etwas klemmt.

Verwendung::

    python3 erzeuge_mehrjahresbaende.py [--schuljahr 2026/2027] [--vorjahr 2025/2026]
                                        [--datei PFAD] [--trocken]

  --schuljahr  das **neue** Schuljahr (Default: das laufende laut IServ)
  --vorjahr    das abgelaufene (Default: aus --schuljahr abgeleitet)
  --datei      Zieldatei (Default: "Mehrjahresbände Schulbuchausleihe.xlsx"
               neben diesem Skript)
  --trocken    nichts schreiben, nur auf der Konsole zeigen, was herauskäme
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
_API_ROOT = _ROOT.parent / "ausleihe-api"

# Wie in buecherlisten/generate_booklists.py: die Zugangsdaten liegen in der
# ``.env`` des Geschwister-Repos, und ``ausleihe`` kommt aus dem Venv oder
# ersatzweise von dort.
if _API_ROOT.is_dir():
    sys.path.insert(0, str(_API_ROOT))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_API_ROOT / ".env")

from ausleihe import AusleiheClient  # noqa: E402

from buecherlisten.core.erzeugen import aufgabenfeld_zuordnung  # noqa: E402
from mehrjahresbaende.core import (  # noqa: E402
    lade_schuljahr,
    lies_uebersicht,
    schreibe_datei,
    vergleiche,
    vorjahr_kennung,
)

STANDARD_DATEI = "Mehrjahresbände Schulbuchausleihe.xlsx"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mehrjahresbände-Übersicht aus zwei Schuljahren erzeugen.",
    )
    parser.add_argument("--schuljahr", default=None,
                        help='das neue Schuljahr, z.B. "2026/2027" (Default: laufendes)')
    parser.add_argument("--vorjahr", default=None,
                        help="das abgelaufene Schuljahr (Default: aus --schuljahr abgeleitet)")
    parser.add_argument("--datei", default=None, help=f"Zieldatei (Default: {STANDARD_DATEI})")
    parser.add_argument("--trocken", action="store_true",
                        help="nichts schreiben, nur zeigen, was herauskäme")
    args = parser.parse_args()

    ziel = Path(args.datei) if args.datei else _HERE / STANDARD_DATEI

    client = AusleiheClient(allow_writes=False)
    neu = lade_schuljahr(client, args.schuljahr)
    alt = lade_schuljahr(client, args.vorjahr or vorjahr_kennung(neu.kennung))

    warnungen: list[str] = []
    aufgabenfelder = aufgabenfeld_zuordnung(
        None, warnungen,
        rueckfall="die Spaltenfolge der vorhandenen Datei bleibt, neue Fächer kommen ans Ende",
    )

    bestehende = lies_uebersicht(ziel).spalten if ziel.is_file() else ()
    uebersicht = vergleiche(alt, neu, bestehende_spalten=bestehende,
                            aufgabenfelder=aufgabenfelder, warnungen=tuple(warnungen))

    for warnung in uebersicht.warnungen:
        print(warnung, file=sys.stderr)
    print(f"{alt.name} → {neu.name}: {len(uebersicht.zeilen)} Jahrgänge, "
          f"{len(uebersicht.spalten)} Fächer, {len(uebersicht.sonderfaelle)} Sonderfälle")
    for zeile in uebersicht.zeilen:
        inhalt = zeile.hinweis or " ".join(
            f"{zelle.fach[:3]}:{zelle.marke or '·'}" for zelle in zeile.zellen
        )
        print(f"  {zeile.name}: {inhalt}")
    for eintrag in uebersicht.legende:
        print(f"  {eintrag}")

    if args.trocken:
        print("(--trocken: nichts geschrieben)")
        return
    schreibe_datei(ziel, uebersicht, backup_ordner=ziel.parent / "backups")
    print(f"Geschrieben: {ziel}")


if __name__ == "__main__":
    main()
