"""Anfragekörper der drei schreibenden Routen - als Pydantic-Modelle.

Bis 2026-09-05 stand hier nichts: jede Route nahm ``dict = Body(...)`` und
prüfte danach von Hand mit ``isinstance``-Ketten nach. Das war rund vierzig
Zeilen, die bei jeder neuen Route wieder anfielen - und bei drei Anfrageformen
noch überschaubar, bei dreißig nicht mehr.

Der Grund, warum es *nicht* von Anfang an Pydantic war, ist trotzdem echt und
hat sich nicht erledigt: FastAPIs Vorgabeantwort auf einen ungültigen Körper
ist ein **englisches, schemaförmiges 422**::

    {"detail": [{"type": "missing", "loc": ["body", "key"], ...}]}

Die Oberfläche zeigt aber ``koerper.fehler`` **wörtlich** einer Lehrkraft an
(``app/static/app.js``). Ein solcher Text wäre dort schlimmer als gar keiner.

Gelöst ist das nicht durch Verzicht auf Pydantic, sondern durch **einen**
Handler für ``RequestValidationError`` (``app/fehler.py``), der die Fehlerliste
auf genau einen deutschen Satz abbildet - die Zuordnung Feld → Satz steht
unten in :data:`MELDUNGEN`, direkt neben den Feldern, die sie beschreibt.
Der Statuscode bleibt dabei **400**, nicht FastAPIs 422: er war es vorher
schon, die Tests halten ihn fest, und für die Oberfläche ist "ich habe Unsinn
geschickt" ohnehin ein Fall, kein zwei.

Was hier bewusst **nicht** geprüft wird: ob ``wert`` eine schreibbare Zahl ist.
Diese Regel ("ganze Zahl ab 0 oder leer, und leer heißt ``None``, nicht ``0``")
gehört zur Mappe, nicht zum HTTP-Körper, und steht mit ihrer Begründung in
``app.excel.pruefe_wert``. Sie dort *und* hier zu formulieren hieße, sie an
zwei Stellen auseinanderdriften zu lassen; ``wert: object`` reicht das
JSON unverändert durch.

Unbekannte Schlüssel im Körper sind kein Fehler (Pydantic-Vorgabe ``extra=
"ignore"``) - dieselbe Entscheidung wie bei der Konfiguration (``app/settings.py``,
"Unbekannte Schlüssel"): eine neuere Oberfläche darf ein Feld mitschicken, das
eine ältere Fassung des Servers noch nicht liest, ohne dass die Anfrage
scheitert.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from .excel import erlaubte_spalten_satz

# Leerraum wird abgeschnitten, *dann* wird die Mindestlänge geprüft - ein Feld
# aus lauter Leerzeichen gilt damit als leer, wie in der handgeschriebenen
# Fassung (``not pfad_text.strip()``).
NichtLeer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EinrichtungAnfrage(BaseModel):
    """``POST /api/einrichtung`` - der von Hand eingetragene Pfad zur Mappe."""

    pfad: NichtLeer


class ZellAnfrage(BaseModel):
    """``POST /api/cell`` - eine Zahl, mit dem zuletzt gesehenen Versionsstand."""

    key: NichtLeer
    spalte: str
    # Ohne Vorgabewert wäre ein fehlendes ``wert`` ein Fehler; es bedeutet aber
    # "Feld geleert" und ist der reguläre Weg, eine Zelle zu löschen.
    wert: object = None
    # Pflichtfeld: ohne den beim Laden gesehenen Stand darf nicht geschrieben
    # werden (optimistisches Sperren, siehe docs/architektur.md). ``float``
    # akzeptiert auch die Ganzzahl, die JSON aus einer runden mtime macht.
    mtime: float


class AbrufAnfrage(BaseModel):
    """``POST /api/refresh`` - Zugangsdaten, die nur diese eine Anfrage überlebt.

    ``passwort`` wird **nicht** beschnitten: ein Leerzeichen am Rand kann Teil
    des Passworts sein. Nur die Mindestlänge gilt, wie in der handgeschriebenen
    Fassung (``not passwort``).
    """

    benutzer: NichtLeer
    passwort: Annotated[str, StringConstraints(min_length=1)]


# Feldname → der eine Satz, den die Lehrkraft zu sehen bekommt. Die Schlüssel
# sind über alle drei Modelle hinweg eindeutig; wo sich das einmal ändert, muss
# hier auf (Modell, Feld) umgestellt werden - bis dahin wäre das eine Ebene
# Umweg ohne Nutzen.
MELDUNGEN: dict[str, str] = {
    "pfad": "Bitte einen Pfad zur Excel-Datei eingeben.",
    "key": "Es fehlt der Schlüssel der Zeile.",
    "spalte": erlaubte_spalten_satz(),
    "mtime": "Es fehlt eine gültige Änderungszeit der geladenen Datei.",
    "benutzer": "Bitte IServ-Benutzername und Passwort eingeben.",
    "passwort": "Bitte IServ-Benutzername und Passwort eingeben.",
}

# Wenn der Körper als Ganzes unbrauchbar ist (kein JSON, ein Array statt eines
# Objekts), zeigt ``loc`` auf ``("body",)`` und nicht auf ein Feld.
KOERPER_UNBRAUCHBAR = "Die Anfrage enthielt keine lesbaren Daten."
