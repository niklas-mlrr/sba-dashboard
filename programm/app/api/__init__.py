"""Die HTTP-Schicht: je Router eine Aufgabe, kein Domänenwissen.

Was keine Zeile FastAPI braucht, liegt nicht hier, sondern in den
Domänenmodulen (``app/rows.py``, ``app/excel.py``, ``app/buchplanung.py`` ...);
``create_app`` in ``app/main.py`` ist reine Verdrahtung.

Die sieben Router hier sind nach dem geschnitten, was ein Leser sucht:

* :mod:`~app.api.seite` - die HTML-Oberfläche (``GET /``) und die Einstellungen,
  die das Programmfenster liest und schreibt (``GET/POST /api/einstellungen``).
* :mod:`~app.api.tabelle` - die Tabelle als JSON und die Änderung einer Zahl.
* :mod:`~app.api.abruf` - die Anmeldung (``/api/anmeldung``) sowie Start und
  Fortschritt des IServ-Abrufs.
* :mod:`~app.api.buecherliste` - die Bücherlisten nach Fach, Verlag und
  Jahrgang, aus der Buchplanungs-Datei, verglichen mit IServ live (HTML).
* :mod:`~app.api.buchplanung` - der gespeicherte Stand eines Schuljahrs:
  Fachbestätigung, Planung, Rücklagen und Anträge (nur API; eingetragen
  wird in den Bücherlisten-Ansichten).
* :mod:`~app.api.mehrjahresbaende` - die Übersicht, welche Bücher am
  Schuljahreswechsel abzugeben sind (HTML plus drei API-Routen).
* :mod:`~app.api.system` - Lebenszeichen und Beenden.

Was in **keinem** dieser Module steht: eine Abbildung von Ausnahmen auf
Statuscodes. Die steht einmal in ``app/fehler.py``.
"""
from __future__ import annotations

from .abruf import router as abruf_router
from .buchplanung import router as buchplanung_router
from .buecherliste import router as buecherliste_router
from .mehrjahresbaende import router as mehrjahresbaende_router
from .seite import router as seite_router
from .system import router as system_router
from .tabelle import router as tabelle_router

# Reihenfolge = Reihenfolge der Registrierung in create_app. ``seite`` steht
# zuletzt, damit sein ``GET /`` keine der spezifischeren API-Routen verdeckt -
# heute unkritisch (die Pfade überschneiden sich nicht), aber die Regel kostet
# nichts und hält das so.
ROUTER = (system_router, tabelle_router, abruf_router, buecherliste_router,
          buchplanung_router, mehrjahresbaende_router, seite_router)

__all__ = ["ROUTER"]
