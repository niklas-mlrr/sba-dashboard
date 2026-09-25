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

from datetime import date
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from .excel import erlaubte_spalten_satz

# Leerraum wird abgeschnitten, *dann* wird die Mindestlänge geprüft - ein Feld
# aus lauter Leerzeichen gilt damit als leer, wie in der handgeschriebenen
# Fassung (``not pfad_text.strip()``).
NichtLeer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EinstellungenAnfrage(BaseModel):
    """``POST /api/einstellungen`` - die zwei Werte hinter dem Zahnrad im Fenster.

    Bis 2026-09-10 hieß dieses Modell ``EinrichtungAnfrage`` und trug einen
    einzigen ``pfad``: den vollen Dateipfad der Mappe, eingegeben auf einer
    Browserseite. Beides hat sich geändert - eingestellt wird der **Ordner**
    (der Dateiname trägt die Jahreszahl und wechselt, siehe
    ``app.settings.mappe_im_ordner``), und dazu der IServ-Server, der vorher nur
    von Hand in der JSON-Datei änderbar war.
    """

    server: NichtLeer
    ordner: NichtLeer


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


class MarkenAnfrage(BaseModel):
    """``POST /api/mehrjahresbaende/marke`` - eine Zelle der Übersicht.

    Angesprochen wird die Zelle über ihre Beschriftung (Jahrgang und Fach), nie
    über einen Zellbezug - aus demselben Grund wie bei ``ZellAnfrage``: eine in
    Excel verschobene Zeile darf keine falsche Zelle treffen.

    ``marke`` darf leer sein: das ist die Marke „darf behalten werden", die in
    der Datei als leere Zelle steht. Welche Buchstaben sonst erlaubt sind, hängt
    an der Legende **dieser** Datei und wird deshalb erst beim Schreiben geprüft
    (``app.mehrjahresbaende.schreibe_marke``).
    """

    jahrgang: int
    fach: NichtLeer
    marke: str = ""
    mtime: float


class ErzeugenAnfrage(BaseModel):
    """``POST /api/mehrjahresbaende/erzeugen`` - beide Schuljahre, beide freiwillig.

    Ohne Angabe gilt das laufende Schuljahr aus IServ und das daraus
    abgeleitete Vorjahr. Übersteuern lässt sich beides, weil der Wechsel
    manchmal vor und manchmal nach dem Schuljahresbeginn erledigt wird.
    """

    schuljahr: str | None = None
    vorjahr: str | None = None


class AbgleichAnfrage(BaseModel):
    """``POST /api/buchplanung/abgleich`` - beide Schuljahre, beide freiwillig.

    Wie ``ErzeugenAnfrage``: ohne Angabe gilt das laufende Schuljahr aus IServ
    und das daraus abgeleitete Vorjahr.
    """

    schuljahr: str | None = None
    vorjahr: str | None = None


class _BuchplanungAnfrage(BaseModel):
    """Was jede Eintragung in die Buchplanung mitbringt.

    ``schuljahr`` steht hier, weil es je Schuljahr **eine eigene Datei** gibt -
    es sagt nicht, was eingetragen wird, sondern wohin. ``mtime`` ist wie
    überall der beim Laden gesehene Stand: ohne ihn wird nicht geschrieben.
    """

    schuljahr: NichtLeer
    mtime: float


class FachbestaetigungAnfrage(_BuchplanungAnfrage):
    """``POST /api/buchplanung/fach`` - die Freigabe durch die Fachkonferenzleitung.

    Bestätigt wird je Zeile (Buch, Fach, Jahrgang); diese Anfrage setzt Kürzel
    und Datum in alle Zeilen des Fachs. ``kuerzel`` darf leer sein: das nimmt
    die Bestätigung des ganzen Fachs zurück.
    """

    fach: NichtLeer
    kuerzel: str = ""
    datum: date | None = None


class PlanungsAnfrage(_BuchplanungAnfrage):
    """``POST /api/buchplanung/planung`` - eine Zeile (Buch, Fach, Jahrgang).

    Der Jahrgang muss kein heutiges Vorkommen des Buchs sein: „wird ab 2028/29
    auch in Jahrgang 9 eingeführt" ist der Fall, für den es diese Zeile gibt.
    Sind alle Felder leer, verschwindet die Zeile wieder.
    """

    isbn: NichtLeer
    fach: NichtLeer
    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""


class JahrgangEingabe(BaseModel):
    """Eine Zeile der Planungstabelle im Menü eines Buchs.

    Ohne Kürzel und Datum: bestätigt wird die Liste als Ganzes, oben auf der
    Fach-Seite (``POST /api/buchplanung/fach``). Was mit einer schon
    bestätigten Zeile geschieht, wenn sie sich ändert, entscheidet
    ``buecherlisten/planung/abgleich.py::setze_buchplanung`` - nicht der Körper
    der Anfrage.
    """

    jahrgang: int
    eingefuehrt_ab: str = ""
    ausgemustert_nach: str = ""
    bemerkung: str = ""


class RuecklageEingabe(BaseModel):
    """Der Rücklage-Block desselben Menüs - ohne Stand.

    Welchen Stand eine Rücklage hat (``gewünscht``/``zugesagt``/
    ``zurückgelegt``), setzt nicht die Fachschaft im Menü, sondern wer die
    Bücher zurücklegt; ein schon eingetragener Stand bleibt beim Speichern
    stehen (``buecherlisten/planung/abgleich.py::setze_buchplanung``).
    """

    anzahl: int | None = None
    bemerkung: str = ""


class BuchreiheEingabe(BaseModel):
    """Der Block „Buchreihe“ des Menüs - die Felder, wie IServ sie nennt.

    Korrigiert wird nur in der Datei, nicht in IServ. Ohne ISBN: sie steht im
    Menü nur zum Lesen. Ein leerer Preis heißt: gilt wie in IServ.
    """

    titel: str = ""
    verlag: str = ""
    neupreis: float | None = None
    leihgebuehr: float | None = None


class BuchplanungsAnfrage(_BuchplanungAnfrage):
    """``POST /api/buchplanung/buch`` - das ganze Menü eines Buchs in einem Fach.

    ``zeilen`` ist der **vollständige** Stand dieses (Buch, Fach): ein Jahrgang,
    der nicht mehr darin steht, wurde im Menü gelöscht und verschwindet aus der
    Datei. Eine Liste von Änderungen wäre hier falsch - das Menü zeigt den
    ganzen Stand, also schickt es ihn auch ganz zurück.

    ``buchreihe`` ist der Stand des Blocks „Buchreihe“. Was davon als
    Korrektur gilt, entscheidet der Server gegen die IServ-Werte, die die
    Datei zu jedem Buch kennt.
    """

    isbn: NichtLeer
    fach: NichtLeer
    zeilen: list[JahrgangEingabe] = []
    ruecklage: RuecklageEingabe | None = None
    buchreihe: BuchreiheEingabe | None = None


class BuchHinzufuegenAnfrage(_BuchplanungAnfrage):
    """``POST /api/buchplanung/buch/neu`` - ein Buch in die Liste eines Fachs aufnehmen.

    Anders als im Bearbeiten-Menü ist die ISBN hier eine Eingabe: sie wählt ein
    Buch aus einem anderen Fach oder legt ein neues an. Die Prüfung, ob sie
    eine ISBN ist, steht im Kern (``fuege_buch_hinzu``) - hier nur, dass sie da ist.
    """

    isbn: NichtLeer
    fach: NichtLeer
    zeilen: list[JahrgangEingabe] = []
    buchreihe: BuchreiheEingabe


class RuecklageAnfrage(_BuchplanungAnfrage):
    """``POST /api/buchplanung/ruecklage`` - der Wunsch einer Fachschaft."""

    isbn: NichtLeer
    fach: NichtLeer
    anzahl: int | None = None
    status: str = ""
    kuerzel: str = ""
    datum: date | None = None
    bemerkung: str = ""


class AnmeldeAnfrage(BaseModel):
    """``POST /api/anmeldung`` - die Zugangsdaten, die das Programmfenster sendet.

    Bis 2026-09-10 hieß dieses Modell ``AbrufAnfrage`` und war der Körper von
    ``POST /api/refresh``: jeder Abruf brachte seine eigenen Zugangsdaten mit.
    Angemeldet wird jetzt einmal im Fenster (``app/sitzung.py``), und
    ``/api/refresh`` nimmt überhaupt keinen Körper mehr.

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
    "server": "Bitte die Adresse des IServ-Servers eingeben, etwa 'meine-schule.de'.",
    "ordner": "Bitte den Ordner angeben, in dem die Excel-Datei liegt.",
    "key": "Es fehlt der Schlüssel der Zeile.",
    "spalte": erlaubte_spalten_satz(),
    "mtime": "Es fehlt eine gültige Änderungszeit der geladenen Datei.",
    "jahrgang": "Es fehlt der Jahrgang der Zeile.",
    "fach": "Es fehlt das Fach der Spalte.",
    "isbn": "Es fehlt die ISBN des Buchs.",
    "verlag": "Es fehlt der Verlag.",
    "kuerzel": "Bitte das Kürzel eintragen, mit dem bestätigt wird.",
    "schuljahr": "Es fehlt das Schuljahr, zu dem die Datei gehört.",
    "benutzer": "Bitte IServ-Benutzername und Passwort eingeben.",
    "passwort": "Bitte IServ-Benutzername und Passwort eingeben.",
}

# Wenn der Körper als Ganzes unbrauchbar ist (kein JSON, ein Array statt eines
# Objekts), zeigt ``loc`` auf ``("body",)`` und nicht auf ein Feld.
KOERPER_UNBRAUCHBAR = "Die Anfrage enthielt keine lesbaren Daten."
