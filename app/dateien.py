"""Atomares Schreiben einer Textdatei - eine Implementierung, zwei Aufrufer.

``app/cache.py`` (der Sidecar-Cache) und ``app/settings.py`` (die
Benutzerkonfiguration) brauchen exakt dieselbe Garantie: ein Abbruch
mittendrin (Stromausfall, WLAN weg, Prozess beendet) darf die vorherige
Fassung der Datei nicht durch eine halbe/leere ersetzen. Deshalb: Nachbardatei,
``fsync``, dann ein wiederholendes ``os.replace``.

Die Wiederholung braucht es unter Windows: ``os.replace`` scheitert dort mit
``PermissionError`` (``WinError 5``), solange irgendein Handle auf die
Zieldatei offen ist - ein lesendes ``open()`` genügt schon. Unter POSIX
ersetzt ``rename`` in diesem Fall stillschweigend. Die Wiederholung selbst
steht in ``bestand.core.replace_with_retry`` (geteilt mit der CLI, die
dieselbe Mappe speichert); diese Datei ruft sie nur auf.

Zwei Aufrufer, eine Garantie: deshalb eine gemeinsame Funktion statt zweier
gepflegter Kopien. Wie ``app/paths.py`` bleibt auch dieses Modul bewusst frei
von FastAPI- und openpyxl-Importen, damit es ohne den Rest der Anwendung
importierbar und testbar bleibt.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from bestand.core import replace_with_retry


def schreibe_atomar(pfad: Path, inhalt: str) -> None:
    """Schreibt ``inhalt`` unterbrechungssicher: Nachbardatei, ``fsync``, dann ``os.replace``.

    Die Nachbardatei liegt bewusst im selben Verzeichnis wie ``pfad`` - ``os.replace``
    ist nur innerhalb eines Dateisystems atomar. Schlägt das Schreiben oder das
    Ersetzen fehl, wird die Nachbardatei aufgeräumt und die ursprüngliche ``pfad``
    bleibt unangetastet; der Aufrufer entscheidet, was ein Fehlschlag bedeutet
    (der Cache weicht z. B. auf einen zweiten Ort aus, die Benutzerkonfiguration
    gibt den Grund als Klartext-Hinweis zurück).
    """
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{pfad.stem}.", suffix=pfad.suffix, dir=pfad.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(inhalt)
            handle.flush()
            os.fsync(handle.fileno())
        replace_with_retry(tmp_name, pfad)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
