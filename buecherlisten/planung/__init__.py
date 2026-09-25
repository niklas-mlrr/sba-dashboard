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
:mod:`~buecherlisten.planung.abgleich` das Zusammenführen und die Eintragungen,
:mod:`~buecherlisten.planung.vergleich` den Vergleich der Datei mit IServ.
"""
from .abgleich import (
    Buchreiheneingabe,
    Jahrgangseingabe,
    Ruecklageneingabe,
    UnbekanntesBuch,
    UngueltigeEingabe,
    bestaetige_fach,
    fuege_buch_hinzu,
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
    endet_mit_vorjahr,
    fach_bestaetigung,
    fach_status,
    planungs_status,
    planungs_zusatz,
    schuljahr_zahl,
    wirkt_im_schuljahr,
    zum_schuljahr_ausgemustert,
)
from .vergleich import (
    BEIDE,
    NUR_EXCEL,
    NUR_ISERV,
    Abweichung,
    IservBuch,
    aktive_paare,
    vergleiche,
)

__all__ = [
    "BEIDE",
    "NUR_EXCEL",
    "NUR_ISERV",
    "Abweichung",
    "IservBuch",
    "aktive_paare",
    "vergleiche",
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
    "endet_mit_vorjahr",
    "fach_bestaetigung",
    "fach_status",
    "fuege_buch_hinzu",
    "lade_schnappschuss",
    "lies_datei",
    "lies_mappe",
    "neue_mappe",
    "planungs_status",
    "planungs_zusatz",
    "schreibe_datei",
    "schreibe_mappe",
    "schuljahr_zahl",
    "setze_buchplanung",
    "setze_buchreihe",
    "setze_planung",
    "setze_ruecklage",
    "wirkt_im_schuljahr",
    "zum_schuljahr_ausgemustert",
    "zusammenfuehren",
]
