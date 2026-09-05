"""Die HTTP-Schicht: je Router eine Aufgabe, kein Domänenwissen.

Bis 2026-09-05 stand alles davon in ``app/main.py``, zusammen mit der
App-Factory, dem Domänenlesen (``lies_tabelle``) und der Mappenprüfung
(``validiere_excel_mappe``) - vier Aufgaben in einer Datei, und es war die
Datei, die jedes neue Feature anfassen musste. Die beiden letzten Aufgaben
enthielten keine Zeile FastAPI und liegen jetzt in ``app/rows.py`` bzw.
``app/excel.py``; ``create_app`` ist reine Verdrahtung.

Die vier Router hier sind nach dem geschnitten, was ein Leser sucht:

* :mod:`~app.api.seite` - die HTML-Oberfläche (``GET /``) und das eine
  Formular, das sie einrichtet (``POST /api/einrichtung``).
* :mod:`~app.api.tabelle` - die Tabelle als JSON und die Änderung einer Zahl.
* :mod:`~app.api.abruf` - Start und Fortschritt des IServ-Abrufs.
* :mod:`~app.api.system` - Lebenszeichen und Beenden.

Was in **keinem** dieser Module steht: eine Abbildung von Ausnahmen auf
Statuscodes. Die steht einmal in ``app/fehler.py``.
"""
from __future__ import annotations

from .abruf import router as abruf_router
from .seite import router as seite_router
from .system import router as system_router
from .tabelle import router as tabelle_router

# Reihenfolge = Reihenfolge der Registrierung in create_app. ``seite`` steht
# zuletzt, damit sein ``GET /`` keine der spezifischeren API-Routen verdeckt -
# heute unkritisch (die Pfade überschneiden sich nicht), aber die Regel kostet
# nichts und hält das so.
ROUTER = (system_router, tabelle_router, abruf_router, seite_router)

__all__ = ["ROUTER"]
