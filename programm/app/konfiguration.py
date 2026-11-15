"""Der Bootstrap der Konfiguration - Laden **mit** Konsolenausgabe.

Getrennt von ``app/settings.py``, weil dort das Laden bewusst seiteneffektfrei
bleibt: ``Einstellungen.laden_mit_benutzerkonfiguration`` *gibt* einen Hinweis
zurück, statt ihn auszugeben. Wohin dieser Hinweis geht, entscheidet der
Aufrufer - und für den Start des Dashboards ist das die Konsole, also das
schwarze Fenster, das ohnehin offen bleiben muss.

Getrennt von ``app/main.py``, weil sowohl ``app/start.py`` (beim Start) als
auch die Routen (beim Nachladen einer Anwendung ohne injizierte Einstellungen)
diese Funktion brauchen - stünde sie in ``main.py``, wäre der Import aus
``app/api/`` ein Kreis.
"""
from __future__ import annotations

from pathlib import Path

from .settings import Einstellungen

_WURZEL = Path(__file__).resolve().parent.parent


def lade_einstellungen(pfad: Path | None = None) -> Einstellungen:
    """Lädt die Konfiguration - mit oder ohne Overlay.

    Mit explizitem ``pfad`` (Arbeitskopie-Modus, ``--config PATH``) wird genau
    diese eine Datei gelesen und später auch beschrieben - kein Overlay, siehe
    ``Einstellungen.laden``.

    Ohne ``pfad`` gilt der Produktivmodus: der ausgelieferte Standard aus
    ``config.json`` wird geladen und die Benutzerkonfiguration im
    plattformabhängigen Ordner (``app.paths.benutzer_konfigurationspfad``)
    darübergelegt. Ein fehlendes oder kaputtes Overlay verhindert den Start
    nicht; ein Klartext-Grund landet dann auf der Konsole.
    """
    if pfad is not None:
        return Einstellungen.laden(pfad)
    einstellungen, hinweis = Einstellungen.laden_mit_benutzerkonfiguration(_WURZEL / "config.json")
    if hinweis:
        print(hinweis)
    return einstellungen
