"""Buchplanung: Fachbestätigung, Einführung und Ausmusterung.

Die Bücherlisten stehen in IServ, aber der Weg zu ihnen ist Arbeit über ein
ganzes Schuljahr: Listen von den Fachkonferenzen bestätigen lassen,
Neueinführungen und Ausmusterungen festhalten, Exemplare für die
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
    Buchreiheneingabe,
    Jahrgangseingabe,
    Ruecklageneingabe,
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    setze_buchplanung,
    setze_buchreihe,
    setze_planung,
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
    ISERV_FELD,
    LEGENDE,
    OHNE_FACH,
    OHNE_VERLAG,
    PLANUNG_AUSGEMUSTERT,
    PLANUNG_GEPLANT,
    PLANUNG_IM_EINSATZ,
    PLANUNG_LAEUFT_AUS,
    RUECKLAGE_STATUS,
    Buch,
    Buchbemerkung,
    Buchplanung,
    Planungszeile,
    Ruecklage,
    UngueltigesSchuljahr,
    fach_bestaetigung,
    fach_status,
    planungs_status,
    schuljahr_zahl,
    wirkt_im_schuljahr,
)

__all__ = [
    "BLAETTER",
    "FACH_BESTAETIGT",
    "FACH_OFFEN",
    "FACH_TEILWEISE",
    "ISERV_FELD",
    "LEGENDE",
    "OHNE_FACH",
    "OHNE_VERLAG",
    "PLANUNG_AUSGEMUSTERT",
    "PLANUNG_GEPLANT",
    "PLANUNG_IM_EINSATZ",
    "PLANUNG_LAEUFT_AUS",
    "RUECKLAGE_STATUS",
    "AusleiheClient",
    "Buch",
    "Buchplanung",
    "Buchreiheneingabe",
    "Jahrgangseingabe",
    "MappeUnlesbar",
    "Planungszeile",
    "Buchbemerkung",
    "Ruecklage",
    "Ruecklageneingabe",
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
    "schreibe_datei",
    "schreibe_mappe",
    "schuljahr_zahl",
    "setze_buchplanung",
    "setze_buchreihe",
    "setze_planung",
    "setze_ruecklage",
    "wirkt_im_schuljahr",
    "zusammenfuehren",
]
