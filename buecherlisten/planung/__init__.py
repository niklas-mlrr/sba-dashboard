"""Buchplanung: Preisprüfung, Fachbestätigung, Einführung und Ausmusterung.

Die Bücherlisten stehen in IServ, aber der Weg zu ihnen ist Arbeit über ein
ganzes Schuljahr: Preise prüfen, Listen von den Fachkonferenzen bestätigen
lassen, Neueinführungen und Ausmusterungen festhalten, Exemplare für die
Fachschaften zurücklegen. Dieses Paket hält diesen Weg in **einer Exceldatei**
je Schuljahr fest - lesbar auch dann, wenn das Dashboard gerade nicht läuft.

Es liegt unter ``buecherlisten/``, weil es keine eigene Seite hat: eingetragen
wird in den Bücherlisten-Seiten selbst, und die Daten kommen aus
``buecherlisten.core.daten``. Hier steht der Kern - keine HTTP-Schicht, keine
Einstellungen, keine Sperren; das ist ``app/buchplanung.py``.

Aufbau: :mod:`~buecherlisten.planung.modelle` die Begriffe und die gerechneten
Status, :mod:`~buecherlisten.planung.mappe` die Arbeitsmappe,
:mod:`~buecherlisten.planung.laden` die beiden Schuljahre aus IServ,
:mod:`~buecherlisten.planung.abgleich` das Zusammenführen und die Eintragungen.
"""
from .abgleich import (
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    setze_planung,
    setze_preis,
    setze_preise_des_verlags,
    setze_ruecklage,
    zusammenfuehren,
)
from .laden import AusleiheClient, Schnappschuss, lade_schnappschuss
from .mappe import (
    BLAETTER,
    MappeUnlesbar,
    lies_datei,
    lies_mappe,
    neue_mappe,
    schreibe_datei,
    schreibe_mappe,
)
from .modelle import (
    FACH_BESTAETIGT,
    FACH_OFFEN,
    FACH_TEILWEISE,
    LEGENDE,
    OHNE_FACH,
    OHNE_VERLAG,
    PLANUNG_AUSGEMUSTERT,
    PLANUNG_GEPLANT,
    PLANUNG_IM_EINSATZ,
    PLANUNG_LAEUFT_AUS,
    PREIS_ABWEICHEND,
    PREIS_BESTAETIGT,
    PREIS_OFFEN,
    RUECKLAGE_STATUS,
    Buch,
    Buchplanung,
    Planungszeile,
    Preispruefung,
    Ruecklage,
    UngueltigesSchuljahr,
    fach_bestaetigung,
    fach_status,
    planungs_status,
    preis_status,
    schuljahr_zahl,
)

__all__ = [
    "BLAETTER",
    "FACH_BESTAETIGT",
    "FACH_OFFEN",
    "FACH_TEILWEISE",
    "LEGENDE",
    "OHNE_FACH",
    "OHNE_VERLAG",
    "PLANUNG_AUSGEMUSTERT",
    "PLANUNG_GEPLANT",
    "PLANUNG_IM_EINSATZ",
    "PLANUNG_LAEUFT_AUS",
    "PREIS_ABWEICHEND",
    "PREIS_BESTAETIGT",
    "PREIS_OFFEN",
    "RUECKLAGE_STATUS",
    "AusleiheClient",
    "Buch",
    "Buchplanung",
    "MappeUnlesbar",
    "Planungszeile",
    "Preispruefung",
    "Ruecklage",
    "Schnappschuss",
    "UnbekanntesBuch",
    "UngueltigeEingabe",
    "UngueltigesSchuljahr",
    "bestaetige_fach",
    "fach_bestaetigung",
    "fach_status",
    "lade_schnappschuss",
    "lies_datei",
    "lies_mappe",
    "neue_mappe",
    "planungs_status",
    "preis_status",
    "schreibe_datei",
    "schreibe_mappe",
    "schuljahr_zahl",
    "setze_planung",
    "setze_preis",
    "setze_preise_des_verlags",
    "setze_ruecklage",
    "zusammenfuehren",
]
