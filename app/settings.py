"""Einstellungen aus config.json - deutsche Schlüssel, weil die Lehrkraft sie bearbeitet.

Der Excel-Pfad ist bewusst eine **Liste von Kandidaten**: dieselbe Datei heißt auf
dem einen Rechner ``N:\\Buchausleihe Admins\\...`` und auf dem anderen
``\\\\iserv...\\Gruppen\\Buchausleihe Admins\\...``. Der erste existierende Pfad
gewinnt; existiert keiner, zeigt die Startseite alle geprüften Pfade an, statt mit
einer Ausnahme abzubrechen.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from bestand.core import BestandConfig


class EinstellungsFehler(ValueError):
    """config.json ist unbrauchbar; der Aufrufer entscheidet über die Folge."""


@dataclass(frozen=True)
class Einstellungen:
    iserv_domain: str
    excel_pfad_kandidaten: tuple[Path, ...]
    blatt_raster: str
    sicherheitsbestand: int = 5
    match_overrides: dict[str, str] = field(default_factory=dict)
    port: int = 8765
    backups_behalten: int = 30

    @classmethod
    def laden(cls, pfad: Path) -> "Einstellungen":
        pfad = Path(pfad)
        try:
            with open(pfad, encoding="utf-8") as handle:
                roh = json.load(handle)
        except FileNotFoundError as exc:
            raise EinstellungsFehler(f"config.json nicht gefunden: {pfad}") from exc
        except json.JSONDecodeError as exc:
            raise EinstellungsFehler(f"config.json ist kein gültiges JSON: {exc}") from exc

        kandidaten = roh.get("excel_pfad_kandidaten")
        if not isinstance(kandidaten, list) or not kandidaten:
            raise EinstellungsFehler(
                "config.json: 'excel_pfad_kandidaten' muss eine nicht leere Liste von Pfaden sein."
            )
        blatt = roh.get("blatt_raster")
        if not blatt:
            raise EinstellungsFehler("config.json: 'blatt_raster' fehlt.")

        stock = roh.get("sicherheitsbestand", 5)
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
            raise EinstellungsFehler("config.json: 'sicherheitsbestand' muss eine Zahl >= 0 sein.")

        overrides = roh.get("match_overrides", {})
        if not isinstance(overrides, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in overrides.items()
        ):
            raise EinstellungsFehler(
                "config.json: 'match_overrides' muss ein Objekt aus Text-Schlüsseln und ISBNs sein."
            )

        return cls(
            iserv_domain=str(roh.get("iserv_domain", "")),
            excel_pfad_kandidaten=tuple(Path(str(k)) for k in kandidaten),
            blatt_raster=str(blatt),
            sicherheitsbestand=stock,
            match_overrides=dict(overrides),
            port=int(roh.get("port", 8765)),
            backups_behalten=int(roh.get("backups_behalten", 30)),
        )

    # ── Pfadauflösung ─────────────────────────────────────────────────────────

    def geprüfte_pfade(self) -> list[tuple[Path, bool]]:
        """Alle Kandidaten mit der Angabe, ob sie existieren - für die Fehlerseite."""
        return [(pfad, pfad.is_file()) for pfad in self.excel_pfad_kandidaten]

    def excel_pfad(self) -> Path | None:
        """Der erste existierende Kandidat, sonst None."""
        for pfad, vorhanden in self.geprüfte_pfade():
            if vorhanden:
                return pfad
        return None

    def bestand_config(self) -> BestandConfig:
        """Übersetzt in die Konfiguration der Bibliothek (englische Feldnamen)."""
        pfad = self.excel_pfad()
        if pfad is None:
            raise EinstellungsFehler("Keine der eingetragenen Excel-Dateien wurde gefunden.")
        return BestandConfig(
            excel_path=pfad,
            sheet_name=self.blatt_raster,
            safety_stock=self.sicherheitsbestand,
            match_overrides=dict(self.match_overrides),
        )


def speichere_excel_pfad(config_pfad: Path, excel_pfad: Path) -> Einstellungen:
    """Merkt einen geprüften Pfad vor den zentralen Vorschlägen."""
    with open(config_pfad, encoding="utf-8") as handle:
        roh = json.load(handle)
    auswahl = str(excel_pfad)
    alte_pfade = (str(p) for p in roh["excel_pfad_kandidaten"] if str(p) != auswahl)
    roh["excel_pfad_kandidaten"] = [auswahl, *alte_pfade]
    temporaer = config_pfad.with_suffix(config_pfad.suffix + ".tmp")
    temporaer.write_text(json.dumps(roh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporaer, config_pfad)
    return Einstellungen.laden(config_pfad)
