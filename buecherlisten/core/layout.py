"""Das PDF-Layout der Bücherlisten nach Fach (reportlab).

Unverändert aus ``generate_booklists.py`` verschoben (2026-09-17); die
Ausmessungen und Begründungen in den Kommentaren gelten weiter. Neu ist nur,
dass ``write_pdf`` und ``write_combined_confirmation_pdf`` auch in einen
Puffer schreiben können (``BinaryIO``), damit das Dashboard das PDF ohne
Umweg über eine Datei ausliefern kann.
"""
from __future__ import annotations

import io
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import combinations, product
from pathlib import Path
from typing import Any, BinaryIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
)

from buecherlisten.trg_web import find_kollegium_kuerzel, find_mapped_value

# Rückfall für die Fußzeile, falls die Anschrift der Schule nicht aus der
# Ausleihe-API zu holen ist (``GET /school/address``) — an der Aufmachung der
# offiziellen IServ-Bücherlisten-PDFs orientiert (dort im Footer geführt).
SCHOOL_NAME = "Tilman-Riemenschneider-Gymnasium Osterode am Harz"

# ── Maße aus der offiziellen IServ-Bücherliste ───────────────────────────────
# Alle Werte unten sind aus "Bücherliste Jahrgang 5.pdf" ausgemessen
# (pdfplumber, 2026-08-18) und bewusst als absolute Punkt-Angaben gepflegt:
# Kopfbereich, Überschrift und Tabellen sollen deckungsgleich mit dem Original
# sitzen. Alles unterhalb der Tabellen (Fußzeile) ist davon ausgenommen.
PAGE_W, PAGE_H = A4

LEFT_MARGIN = 72.0                          # Textkante links (Original: x0 = 72.00)
RIGHT_EDGE = 537.28                         # Textkante rechts (Original: x1 = 537.28)
RIGHT_MARGIN = PAGE_W - RIGHT_EDGE          # = 58.0 (Original ist asymmetrisch)
CONTENT_WIDTH = RIGHT_EDGE - LEFT_MARGIN    # = 465.28 — auch die Tabellenbreite

# Grundlinien (Baselines) gemessen vom Seitenoberrand.
HEADER_LABEL_FONT, HEADER_LABEL_SIZE = "Helvetica", 8.0
HEADER_LABEL_BASELINE = PAGE_H - 45.74      # "Liste für" / "gültig für"
HEADER_VALUE_FONT, HEADER_VALUE_SIZE = "Helvetica-Bold", 12.0
# "Schuljahr 26/27" / "<Fach>": Abweichend vom Original (56.02) so weit unter
# der Label-Zeile, dass sich die Zeilen bei keinem Zeichen berühren können —
# auch nicht Unterlänge ("g" in "gültig für") über Versal mit Akzent ("Ü", "Å").
# Maßgeblich sind die FontBBox-Grenzen aus den Adobe-AFM-Dateien (Einheiten
# pro 1000): tiefster Punkt Helvetica -225, höchster Helvetica-Bold 962.
HEADER_LINE_CLEARANCE = 1.0
HEADER_VALUE_BASELINE = HEADER_LABEL_BASELINE - (
    0.225 * HEADER_LABEL_SIZE + 0.962 * HEADER_VALUE_SIZE + HEADER_LINE_CLEARANCE
)                                           # = PAGE_H - 60.08
TITLE_FONT, TITLE_SIZE = "Helvetica-Bold", 24.0
TITLE_BASELINE = PAGE_H - 105.73            # "Bücherliste <Fach>"

# Mindestlücke zwischen den nebeneinander stehenden Kopf-Blöcken ("Liste für",
# "Zu bestätigen durch", Rückgabe-Angaben, "gültig für"); wird sie unterschritten,
# schrumpft die große Schrift der mittleren Blöcke (siehe SubjectHeading).
MIN_HEADER_BLOCK_GAP = 6.0

# Der Fließtext-Rahmen beginnt oben auf der Seite; der Kopf-/Titelblock wird
# absolut positioniert gezeichnet und reserviert nur seine Höhe (siehe
# SubjectHeading). INTRO_TOP ist die Oberkante des Einleitungstexts.
FRAME_TOP = PAGE_H - 30.0
INTRO_TOP = 714.0
HEADING_BLOCK_HEIGHT = FRAME_TOP - INTRO_TOP
BOTTOM_MARGIN = 18 * mm
# Die Fußzeile fluchtet mit dem Inhalt (LEFT_MARGIN/RIGHT_EDGE) — sie darf
# nicht breiter sein als Tabellen/Text darüber.
FOOTER_CENTER_X = (LEFT_MARGIN + RIGHT_EDGE) / 2

# Fußzeile exakt wie im Original ("Bücherliste Jahrgang 5.pdf", pdfplumber
# 2026-08-21): zwei Zeilen Helvetica 6pt in Schwarz, Grundlinien absolut vom
# Seitenunterrand aus gemessen. Obere Zeile rechtsbündig "Seite n von N",
# untere Zeile links das Erstelldatum (im Original: die URL) und rechtsbündig
# Schule + Kontext.
FOOTER_FONT, FOOTER_SIZE = "Helvetica", 6.0
FOOTER_PAGE_BASELINE = 25.692               # Grundlinie "Seite n von N"
FOOTER_INFO_BASELINE = 20.142               # Grundlinie Datum / Schule+Kontext
FOOTER_COLOR = colors.black
# Ortszusatz, den das Original hinter dem Schulnamen führt.
SCHOOL_CITY = "Osterode am Harz"

ACCENT_COLOR = colors.Color(0.6627, 0.2667, 0.2588)  # Original-Rot der Abschnittstitel
RULE_COLOR = colors.black                            # Linie unter der Kopfzeile (1.0pt schwarz)
ROW_RULE_COLOR = colors.Color(0.6667, 0.6667, 0.6667)  # Zeilentrenner (1.0pt grau)
GREY = colors.HexColor("#666666")
# Planung mit Antragsinformationen (app/planungsdruck.py): offen ist grau,
# abgelehnt durchgestrichen. Heller als GREY, damit es sich vom Schwarz der
# übrigen Zeilen auch gedruckt deutlich abhebt.
STIL_GRAU = "grau"
STIL_DURCH = "durch"
ANTRAG_GRAU_HEX = "#8c8c8c"

# Tabellen-Typografie exakt wie im Original: durchgehend Helvetica 10, nur die
# ISBN-Werte 8pt; Kopfzeile ist ebenfalls Helvetica 10 (nicht fett).
BODY_FONT = "Helvetica"
HEADER_FONT = "Helvetica"
CELL_FONT_SIZE = 10.0
ISBN_FONT_SIZE = 8.0
# Mindestbreite der Jahrgänge im Raster „weiterhin leihbar in“ (siehe
# _weiter_tabelle). Die umbrechenden Tabellenspalten haben keine feste
# Mindestbreite mehr - nur ihr breitestes Wort und ihren Kopf (Vorgabe vom
# 2026-11-11, siehe _aufteilen).
MIN_WRAP_COL = 20 * mm
# Mindestabstand zwischen zwei Spalten (4 pt je Seite), auch wenn der Inhalt
# die Tabellenbreite fast ausfüllt — sonst kann der rechnerisch gleichmäßig
# verteilte Rest pro Lücke gegen 0 gehen und Text ohne sichtbaren Abstand
# aneinanderstoßen (beobachtet 2026-08-18, "Klasse"-Wert direkt vor dem
# Titel). Er wird nie unterschritten (Vorgabe vom 2026-11-11: 8 pt; die
# IServ-Bücherliste hat 16 pt, ausgemessen an "Bücherliste Jahrgang 5.pdf").
MIN_GAP = 8.0
# Spalt zwischen den beiden Unterschriftslinien des Bestätigungs-Blocks.
SIGNATUR_SPALT = 14.0
# Abstand einer Tabellenzeile zur Trennlinie darüber/darunter (Original: 4pt).
CELL_VPAD = 2.0
# Siehe TOPPADDING/BOTTOMPADDING in render_table.
VPAD_SHIFT = 0.66
# Siehe ISBN-TOPPADDING in render_table.
ISBN_VSHIFT = 1.278

STYLES = getSampleStyleSheet()
INTRO_STYLE = ParagraphStyle(
    "Intro", parent=STYLES["Normal"], fontName=BODY_FONT, fontSize=10, leading=12.5,
    textColor=colors.black, spaceAfter=6 * mm,
)
SECTION_STYLE = ParagraphStyle(
    "Abschnitt", parent=STYLES["Heading2"], fontName="Helvetica-Bold", fontSize=16,
    textColor=ACCENT_COLOR, spaceBefore=6 * mm, spaceAfter=3 * mm, leading=19,
)
EMPTY_STYLE = ParagraphStyle("Leer", parent=STYLES["Normal"], fontSize=9, textColor=GREY)
# Schriftgröße wie die Fließtexte ("Die folgenden Bücher können …") in den
# offiziellen IServ-Jahrgangslisten: Helvetica 10 pt. Deren Zeilenabstand
# (9,25 pt) ist aber so eng, dass Unter- und Oberlängen sich fast berühren.
# 12,2 pt: vertikale Lücke zwischen dem tiefsten Punkt einer Zeile (g, -220)
# und dem höchsten der nächsten (Ä, 901) = 12,2 - 11,21 = ~0,9 pt, also etwa
# die mittlere horizontale Lücke zwischen zwei Buchstaben bei 10 pt
# (gerendert gemessen 2026-09-16: ~0,9 pt über a-z, A-Z, äöü, ÄÖÜ, ß).
CONFIRM_STYLE = ParagraphStyle(
    "Bestaetigung", parent=STYLES["Normal"], fontName=BODY_FONT, fontSize=10, leading=12.2,
    alignment=TA_JUSTIFY,
)
# Prüfauftrag im Bestätigungs-Lauf: gesetzt wie der Bestätigungstext
# (Schriftgröße, Zeilenabstand, Blocksatz), nach dem letzten Absatz aber mit
# dem vollen INTRO_STYLE-Abstand zur Tabelle. Absätze innerhalb dieser
# mehrteiligen Einleitung haben nur eine halbe Leerzeile Abstand.
INTRO_CONFIRM_STYLE = ParagraphStyle(
    "IntroBestaetigung", parent=CONFIRM_STYLE, spaceAfter=INTRO_STYLE.spaceAfter,
)
INTRO_PART_STYLE = ParagraphStyle(
    "IntroTeil", parent=INTRO_CONFIRM_STYLE, spaceAfter=CONFIRM_STYLE.leading / 2,
)
SIGNATURE_LABEL_STYLE = ParagraphStyle(
    "SignaturLabel", parent=STYLES["Normal"], fontName=BODY_FONT, fontSize=8, leading=10,
)
# Cap-Height (Höhe eines Großbuchstabens) des Bestätigungstexts — Helvetica
# laut AFM: 718/1000 der Schriftgröße.
CONFIRM_CAP_HEIGHT = CONFIRM_STYLE.fontSize * 0.718
# Kantenlänge des quadratischen Ankreuzkästchens vor dem Bestätigungstext:
# etwa halb so hoch wie der zweizeilige Text daneben, auf einen glatten Wert
# gerundet. Es sitzt mittig in diesen zwei Zeilen (siehe ConfirmationBlock).
CHECKBOX_SIZE = 9.0
# Freier Platz über den Unterschriftslinien für die handschriftliche
# Unterschrift: zwei Schreibzeilen im Zeilenabstand des Bestätigungstexts.
SIGNATURE_LINE_HEIGHT = 2 * CONFIRM_STYLE.leading

# Umbrechende Spalten (Jahrgang, Titel, Verlag, Fach) sind Paragraphs; alle
# anderen bleiben Klartext in exakt passend berechneten Breiten (siehe
# render_table). splitLongWords=0
# verhindert, dass reportlab ein Wort mitten im Zeichen umbricht, wenn die
# zugewiesene Breite durch Rundung minimal knapper ist als das Wort selbst
# (beobachtet 2026-08-18, "Westermann" bei Erdkunde) — ein Wort, das nicht
# passt, läuft dann lieber minimal über, statt aufgetrennt zu werden.
CELL_STYLE = ParagraphStyle(
    "Zelle", parent=STYLES["Normal"], fontName=BODY_FONT, fontSize=CELL_FONT_SIZE, leading=11.5,
    splitLongWords=0,
)
# Einleitung, auf die noch ein Absatz folgt (Sternchen-Hinweis): eine halbe
# Leerzeile Abstand statt des vollen Abstands zur Tabelle.
INTRO_ABSATZ_STYLE = ParagraphStyle(
    "IntroAbsatz", parent=INTRO_STYLE, spaceAfter=INTRO_STYLE.leading / 2,
)
# Erklärzeilen der Sternchen unter einer Tabelle ("* auch für Chemie"): in der
# Schriftgröße der ISBN, eng untereinander, ohne Linien (Vorgabe 2026-11-10).
ERKLAER_STYLE = ParagraphStyle(
    "Erklaerung", parent=STYLES["Normal"], fontName=BODY_FONT, fontSize=ISBN_FONT_SIZE,
    leading=ISBN_FONT_SIZE * 1.25,
)



WIDTH_EPSILON = 0.5

# Leerzeichen, an denen umbrochen wird - wie reportlabs Paragraph: das
# geschützte Leerzeichen (\xa0) gehört zum Wort. ``str.split()`` ohne Argument
# trennt auch dort und würde Breiten messen, die der Satz nie erzeugt.
_UMBRUCH = re.compile(r"[^\S\xa0]+")


def _woerter(text: str) -> list[str]:
    return [wort for wort in _UMBRUCH.split(text) if wort]


# Notfall-Trennstelle (Vorgabe vom 2026-11-11): in einem Wort, das die Tabelle
# sonst über den rechten Rand drückt, eine Stelle, an der ohne Leerzeichen
# umbrochen werden darf - hinter einem Bindestrich oder zwischen zwei Zeichen
# (siehe _notfall_trennen). Ein Zeichen aus dem privaten Bereich, nie gedruckt.
TRENNSTELLE = "\ue001"


def _stuecke(text: str) -> list[tuple[str, str]]:
    """Die unteilbaren Stücke eines Texts, je mit dem, was sie vom vorigen
    trennt: " " zwischen Wörtern, "" an einer TRENNSTELLE."""
    stuecke: list[tuple[str, str]] = []
    for wort in _woerter(text):
        for i, stueck in enumerate(wort.split(TRENNSTELLE)):
            if stueck:
                stuecke.append((" " if i == 0 else "", stueck))
    return stuecke


# Ein erzwungener Zeilenumbruch in einem Zellwert: im Paragraph ``<br/>``
# (siehe _zelle), beim Messen das Ende einer Zeile. app/planungsdruck.py setzt
# ihn vor und hinter einen Jahrgang mit Jahreszusatz.
ZEILENUMBRUCH = "\n"
# Hängender Einzug (Vorgabe vom 2026-11-10): steht in einer Zeile des Werts
# hinter „7 (“; bricht der Zusatz danach um, beginnt jede weitere Zeile
# bündig unter seinem Anfang („ab“, „bis“, „von“). Ein Zeichen aus dem
# privaten Bereich: kein Leerzeichen, nie gedruckt, beim Messen entfernt.
EINZUG = "\ue000"


def _einzug(teil: str, font: str = BODY_FONT, size: float = CELL_FONT_SIZE) -> tuple[str, str, float]:
    """(Kopf, Rest, Breite des Kopfs) einer Zeile; ohne Einzug ist der Kopf leer."""
    kopf, _, rest = teil.rpartition(EINZUG)
    return kopf, rest, stringWidth(kopf, font, size) if kopf else 0.0


def _zeilen_breite(text: str, font: str = BODY_FONT, size: float = CELL_FONT_SIZE) -> float:
    """Die Breite der breitesten erzwungenen Zeile eines Werts."""
    return max(stringWidth(teil.replace(EINZUG, ""), font, size)
               for teil in text.split(ZEILENUMBRUCH))


def _raw_width(header: str, values: list[str], *, value_size: float = CELL_FONT_SIZE) -> float:
    """Reine Inhaltsbreite (kein Zellenpolster) = längster Kopf- oder Zellentext.

    "Länge" heißt hier immer gemessene Textbreite (`stringWidth`), nie
    Zeichenanzahl — ein kurzes "M" ist breiter als ein langes "iii". Ein Wert
    mit erzwungenem Umbruch ist so breit wie seine breiteste Zeile.
    """
    widths = [stringWidth(header, HEADER_FONT, CELL_FONT_SIZE)]
    widths += [_zeilen_breite(v, BODY_FONT, value_size) for v in values]
    return (max(widths) + WIDTH_EPSILON) if widths else 0.0


def _wrap_lines(text: str, width: float, *, font: str = BODY_FONT, size: float = CELL_FONT_SIZE) -> list[str]:
    """Greedy Wortumbruch wie reportlabs Paragraph (Standard, ohne Silbentrennung).

    Bricht ausschließlich an Leerzeichen — ein einzelnes Wort, das breiter als
    `width` ist, bleibt trotzdem als Ganzes auf einer Zeile (siehe Gotcha zu
    splitLongWords bei CELL_STYLE) - und an jedem erzwungenen Umbruch. Hinter
    einem Einzug (EINZUG) steht der Rest um die Breite des Kopfs eingerückt:
    er bricht auf ``width`` minus diese Breite um, der Kopf hängt vor seiner
    ersten Zeile."""
    return [zeile for zeile, _ in _umbrochen(text, width, font=font, size=size)]


def _umbrochen(
    text: str, width: float, *, font: str = BODY_FONT, size: float = CELL_FONT_SIZE,
) -> list[tuple[str, float]]:
    """Die Zeilen von :func:`_wrap_lines` mit ihrer Breite samt Einzug."""
    zeilen: list[tuple[str, float]] = []
    for teil in text.split(ZEILENUMBRUCH):
        kopf, rest, kopf_w = _einzug(teil, font, size)
        for i, zeile in enumerate(_wrap_einfach(rest, width - kopf_w, font=font, size=size)):
            zeilen.append((kopf + zeile if i == 0 else zeile,
                           kopf_w + stringWidth(zeile, font, size)))
    return zeilen


def _wrap_einfach(text: str, width: float, *, font: str, size: float) -> list[str]:
    stuecke = _stuecke(text)
    if not stuecke:
        return [""]
    lines: list[str] = []
    current = stuecke[0][1]
    for trenner, stueck in stuecke[1:]:
        candidate = current + trenner + stueck
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = stueck
    lines.append(current)
    return lines


def _wrap_info(
    text: str, width: float, *, font: str = BODY_FONT, size: float = CELL_FONT_SIZE,
) -> tuple[int, float]:
    """(Zeilenzahl, breiteste tatsächlich benötigte Zeile) beim Umbruch auf `width`."""
    lines = _umbrochen(text, width, font=font, size=size)
    max_line_w = max((breite for _, breite in lines), default=0.0)
    return len(lines), max_line_w + WIDTH_EPSILON


def _max_word_width(values: list[str], *, font: str = BODY_FONT, size: float = CELL_FONT_SIZE) -> float:
    """Breitestes einzelnes Wort über alle Werte — `_wrap_lines` bricht nie
    innerhalb eines Worts um, also kann eine Spalte nie schmaler werden als
    das breiteste unteilbare Wort, das in ihr vorkommt - hinter einem Einzug
    samt dessen Breite (das erste Wort hängt ohnehin am Kopf)."""
    widest = 0.0
    for v in values:
        for teil in v.split(ZEILENUMBRUCH):
            _, rest, kopf_w = _einzug(teil, font, size)
            for _, stueck in _stuecke(rest):
                widest = max(widest, kopf_w + stringWidth(stueck, font, size))
    return widest + WIDTH_EPSILON if widest else 0.0


def _breiten_kandidaten(values: list[str]) -> list[float]:
    """Alle Breiten, bei denen sich der Umbruch einer Spalte ändern kann: die
    Breiten jeder zusammenhängenden Wortfolge eines Werts."""
    kandidaten = set()
    for v in (teil for wert in values for teil in wert.split(ZEILENUMBRUCH)):
        _, rest, kopf_w = _einzug(v)
        stuecke = _stuecke(rest)
        for a in range(len(stuecke)):
            folge = stuecke[a][1]
            kandidaten.add(kopf_w + stringWidth(folge, BODY_FONT, CELL_FONT_SIZE) + WIDTH_EPSILON)
            for trenner, stueck in stuecke[a + 1:]:
                folge += trenner + stueck
                kandidaten.add(kopf_w + stringWidth(folge, BODY_FONT, CELL_FONT_SIZE) + WIDTH_EPSILON)
    return sorted(kandidaten)


def _notfall_trennen(
    werte: list[list[str]], koepfe: list[float], verfuegbar: float, teilbar: list[list[bool]],
) -> list[list[str]]:
    """Die Werte der umbrechenden Spalten, so getrennt, dass die Tabelle in die
    Breite passt (Vorgabe vom 2026-11-11).

    Solange nicht einmal jede Spalte auf ihr breitestes Stück passt, wird das
    breiteste Stück aufgebrochen, das eine Spalte breiter als ihren Kopf hält:
    zuerst hinter seinen Bindestrichen, hat es keine (mehr), zwischen allen
    Zeichen - überall, wo es in dieser Spalte steht. Nur Zellen mit
    ``teilbar`` werden getrennt (nicht die Jahrgänge mit Zusatz). Passt es
    auch dann nicht, bleibt der Überstand.
    """
    werte = [list(spalte) for spalte in werte]
    while sum(max(_max_word_width(w), k) for w, k in zip(werte, koepfe, strict=True)) > verfuegbar:
        breitestes: tuple[float, int, str] | None = None
        for s, (spalte, kopf_w) in enumerate(zip(werte, koepfe, strict=True)):
            stuecke = [stueck for wert, ja in zip(spalte, teilbar[s], strict=True) if ja
                       for teil in wert.split(ZEILENUMBRUCH)
                       for _, stueck in _stuecke(_einzug(teil)[1]) if len(stueck) > 1]
            if not stuecke:
                continue
            stueck = max(stuecke, key=lambda x: stringWidth(x, BODY_FONT, CELL_FONT_SIZE))
            breite = stringWidth(stueck, BODY_FONT, CELL_FONT_SIZE) + WIDTH_EPSILON
            # Nur ein Stück, das seine Spalte breit hält, macht sie schmaler.
            if breite > kopf_w and breite >= _max_word_width(spalte) - 1e-6 and (
                    breitestes is None or breite > breitestes[0]):
                breitestes = (breite, s, stueck)
        if breitestes is None:
            break
        _, s, stueck = breitestes
        if re.search(r"-(?=.)", stueck):
            getrennt = re.sub(r"-(?=.)", "-" + TRENNSTELLE, stueck)
        else:
            getrennt = TRENNSTELLE.join(stueck)
        werte[s] = [wert.replace(stueck, getrennt) if ja else wert
                    for wert, ja in zip(werte[s], teilbar[s], strict=True)]
    return werte


@dataclass(frozen=True)
class _Umbruch:
    """Ein Umbruch einer Spalte: die kleinste Breite, bei der er entsteht, die
    Zeilen je Tabellenzeile und die Breite, die er tatsächlich braucht."""

    breite: float
    zeilen: tuple[int, ...]
    genutzt: float


def _umbrueche(werte: list[str], kopf_w: float) -> list[_Umbruch]:
    """Alle verschiedenen Umbrüche einer Spalte, aufsteigend nach Breite.

    Die schmalste Breite ist das breiteste unteilbare Wort, nie schmaler als
    der Kopf (der bricht nicht um). Mit der Breite werden die Zeilen jedes
    Werts nur weniger; ein Umbruch kommt also nie wieder, und zwischen zwei
    Einträgen gilt der schmalere."""
    minimum = max(_max_word_width(werte), kopf_w)
    umbrueche: list[_Umbruch] = []
    for breite in [minimum, *(k for k in _breiten_kandidaten(werte) if k > minimum)]:
        infos = [_wrap_info(v, breite) for v in werte]
        zeilen = tuple(n for n, _ in infos)
        if umbrueche and umbrueche[-1].zeilen == zeilen:
            continue
        umbrueche.append(_Umbruch(breite, zeilen, max([kopf_w, *(w for _, w in infos)])))
    return umbrueche


def _aufteilen(werte: list[list[str]], koepfe: list[float], verfuegbar: float) -> list[float]:
    """Die Breiten der umbrechenden Spalten (Vorgabe vom 2026-11-11).

    Probiert jeden Umbruch jeder Spalte außer der letzten (:func:`_umbrueche`);
    die letzte bekommt den Rest. Gewählt wird die Aufteilung, mit der die
    Tabelle am wenigsten Zeilen hoch ist; bei Gleichstand die mit den wenigsten
    Zellzeilen (keine Spalte bricht um, ohne dass es Höhe spart), dann die
    schmalste. Jede Spalte ist nur so breit wie ihre breiteste Zeile.

    ``koepfe`` sind die Breiten der Köpfe. Passen nicht einmal die schmalsten
    Umbrüche, bekommt jede Spalte ihren schmalsten: die Tabelle wird dann
    geringfügig breiter (unvermeidbar bei einem einzelnen sehr breiten Wort).
    """
    umbrueche = [_umbrueche(w, k) for w, k in zip(werte, koepfe, strict=True)]
    *vorne, letzte = umbrueche
    letzte_breiten = [u.breite for u in letzte]
    best: tuple[tuple[int, int, float], tuple[_Umbruch, ...]] | None = None
    for kombi in product(*vorne):
        rest = verfuegbar - sum(u.breite for u in kombi)
        i = bisect_right(letzte_breiten, rest) - 1
        if i < 0:
            continue
        wahl = (*kombi, letzte[i])
        je_zeile = list(zip(*(u.zeilen for u in wahl), strict=True))
        key = (sum(max(z) for z in je_zeile), sum(sum(z) for z in je_zeile),
               sum(u.genutzt for u in wahl))
        if best is None or key < best[0]:
            best = (key, wahl)
    wahl = best[1] if best else tuple(u[0] for u in umbrueche)
    return [u.genutzt for u in wahl]


def _lange_koepfe(breiten: list[float], lang: dict[int, float], verfuegbar: float) -> tuple[int, ...]:
    """Die Spalten, deren Kopf lang geschrieben wird (Vorgabe vom 2026-11-11).

    ``lang`` ist je Spalte mit kurzem Kopf ihre Breite mit langem. Es gewinnt
    die Auswahl mit den meisten langen Köpfen, die neben ``breiten`` noch in
    ``verfuegbar`` passt; bei Gleichstand die, deren Spalten am weitesten
    vorn stehen ("Jahrgang" vor "Leihgebühr" vor "Rücklagen").
    """
    frei = verfuegbar - sum(breiten)
    for anzahl in range(len(lang), 0, -1):
        # combinations liefert in lexikographischer Folge: vordere Spalten zuerst.
        for wahl in combinations(sorted(lang), anzahl):
            if sum(lang[i] - breiten[i] for i in wahl) <= frei:
                return wahl
    return ()


@dataclass(frozen=True)
class Spalte:
    """Eine Tabellenspalte. ``umbruch``: darf umbrechen (mindestens eine je
    Tabelle); die anderen stehen einzeilig.

    ``kurz`` ist der Kopf, mit dem die Spalte zuerst gemessen wird; lang
    geschrieben wird er nur, wenn danach noch Platz ist (siehe render_table).
    """

    key: str
    kopf: str
    umbruch: bool = False
    kurz: str | None = None
    schrift: float = CELL_FONT_SIZE
    rechts: bool = False


# Die Spalte heißt "Jahrgang" (Vorgabe vom 2026-11-10, vorher "Klasse"); der
# Schlüssel ``klasse`` bleibt. Sie bricht um wie Titel und Verlag (Vorgabe
# vom 2026-11-11), nur an gewöhnlichen Leerzeichen: app/planungsdruck.py setzt
# geschützte, wo nicht umbrochen werden darf („7 (ab 2027/2028)“), und
# erzwingt den Umbruch vor und hinter einem Jahrgang mit Jahreszusatz - der
# steht allein in seinen Zeilen (ZEILENUMBRUCH, Vorgabe vom 2026-11-10).
KLASSE = Spalte("klasse", "Jahrgang", umbruch=True, kurz="Jg.")
TITEL = Spalte("titel", "Titel", umbruch=True)
VERLAG = Spalte("verlag", "Verlag", umbruch=True)
ISBN = Spalte("isbn", "ISBN", schrift=ISBN_FONT_SIZE)
NEUPREIS = Spalte("neupreis", "Neupreis", rechts=True)
LEIHGEBUEHR = Spalte("leihgebuehr", "Leihgebühr", kurz="Leihgeb.", rechts=True)


# Die Rücklagen einer Fachschaft (Exemplare je Buchreihe) - nur in den
# Tabellen der leihbaren Buchreihen aus der Planungsdatei, und nur in einer, in
# der mindestens eine Buchreihe eine hat (Vorgabe vom 2026-11-10;
# app/planungsdruck.py füllt ``ruecklage``). Letzte Spalte.
RUECKLAGEN = Spalte("ruecklage", "Rücklagen", kurz="Rückl.", rechts=True)

FACH = Spalte("fach", "Fach", umbruch=True)


@dataclass(frozen=True)
class Listenart:
    """Was eine Fach-, Verlags- und Jahrgangsliste unterscheidet: Texte und Spalten.

    Kopf, Schrift, Abstände und Tabellenbild sind für alle gleich; die Texte
    enthalten ``{name}`` für das Fach, den Verlag oder "Jahrgang N".
    """

    einleitung: str
    leer_leih: str
    leer_kauf: str
    spalten: tuple[Spalte, ...]
    # Sternchen für Buchreihen mehrerer Fächer und Jahrgänge, mit Hinweis
    # unter der Einleitung und Erklärzeilen unter der Tabelle - nur mit
    # "IServ-Stand benutzen" (siehe iserv_fach_liste, _sternchen).
    sternchen: bool = False


_ZWEITE_TABELLE = "Bücher, die selbst anzuschaffen sind, werden gesondert in der zweiten Tabelle ausgewiesen."
FACH_LISTE = Listenart(
    "Die folgenden Bücher können für das Fach {name} über die Schule ausgeliehen werden. "
    + _ZWEITE_TABELLE,
    "Keine leihbaren Buchreihen in diesem Fach.",
    "Keine selbst anzuschaffenden Buchreihen in diesem Fach.",
    (KLASSE, TITEL, VERLAG, ISBN, NEUPREIS, LEIHGEBUEHR),
)
# Verlag: der Verlag steht im Kopf, dafür das Fach - das neben dem Titel
# umbrechen darf, weil fächerübergreifende Bücher mehrere Fächer tragen.
VERLAG_LISTE = Listenart(
    "Die folgenden Bücher des Verlags {name} können über die Schule ausgeliehen werden. "
    + _ZWEITE_TABELLE,
    "Keine leihbaren Buchreihen dieses Verlags.",
    "Keine selbst anzuschaffenden Buchreihen dieses Verlags.",
    (TITEL, FACH, KLASSE, ISBN, NEUPREIS, LEIHGEBUEHR),
)
# Jahrgang: Spalten wie in der IServ-Druckversion. Titel, Fach und Verlag
# brechen um, aber nur, wo es Zeilen spart ("Werte und Normen" hielt sonst die
# ganze Spalte breit und brach dafür die Hälfte der Titel um; siehe _aufteilen).
JAHRGANG_LISTE = Listenart(
    "Die folgenden Bücher können für den {name} über die Schule ausgeliehen werden. "
    + _ZWEITE_TABELLE,
    "Keine leihbaren Buchreihen in diesem Jahrgang.",
    "Keine selbst anzuschaffenden Buchreihen in diesem Jahrgang.",
    (TITEL, FACH, VERLAG, ISBN, NEUPREIS, LEIHGEBUEHR),
)


def iserv_fach_liste(schoolyear_name: str, listen_anzahl: int) -> Listenart:
    """Die Fachliste mit "IServ-Stand benutzen" (Vorgabe vom 2026-11-10).

    Der Satz vor den Tabellen ersetzt die Einleitung ganz. Einzahl oder
    Mehrzahl richtet sich nach der Anzahl der Bücherlisten des Schuljahrs,
    nicht danach, in wie vielen davon das Fach vorkommt.
    """
    fuehren = "führt" if listen_anzahl == 1 else "führen"
    # ``einleitung`` wird mit str.format gefüllt: geschweifte Klammern im
    # Schuljahr dürfen dort nicht als Platzhalter gelten.
    schuljahr = schoolyear_name.replace("{", "{{").replace("}", "}}")
    return replace(
        FACH_LISTE,
        einleitung=(f"Folgende Buchreihen {fuehren} die {iserv_quelle(listen_anzahl)} "
                    f"für das Fach {{name}} im {schuljahr}."),
        sternchen=True,
    )


# Steht nach der Einleitung, wenn mindestens eine Buchreihe ein Sternchen hat
# (Vorgabe vom 2026-11-10).
STERNCHEN_HINWEIS = (
    "Da IServ Fächer nicht Jahrgängen, sondern Buchreihen zuordnet, werden bei "
    "Buchreihen mit mehreren Fächern und Jahrgängen alle Jahrgänge allen Fächern "
    "zugeschrieben, auch wenn einzelne Fächer die Buchreihe nicht für alle Jahrgänge "
    "möchten. Betroffene Buchreihen sind mit einem * markiert. Unter der Tabelle "
    "sind die jeweils anderen Fächer aufgeführt."
)


def _sternchen(
    fach: str, tables: dict[str, list[dict]],
) -> tuple[dict[str, list[dict]], dict[str, list[tuple[str, str]]]]:
    """Markiert Buchreihen mehrerer Fächer und Jahrgänge (Vorgabe vom 2026-11-10).

    Jede Kombination der anderen Fächer bekommt einen Stern mehr ("*", "**",
    …), in der Reihenfolge ihres ersten Auftretens, über beide Tabellen des
    Fachs hinweg - gleiche Kombination, gleiches Zeichen. Das Zeichen steht
    mit einem Leerzeichen hinter den Jahrgängen.

    Zurück kommen die Tabellen mit markierten Kopien der Zeilen und je Tabelle
    die Erklärzeilen ``(Sterne, "auch für <Fächer>")`` der Sterne, die in ihr
    vorkommen, aufsteigend.
    """
    sterne: dict[tuple[str, ...], str] = {}
    markiert: dict[str, list[dict]] = {}
    erklaerungen: dict[str, list[tuple[str, str]]] = {}
    for bucket in ("leih", "kauf"):
        zeilen: list[dict] = []
        in_tabelle: dict[str, tuple[str, ...]] = {}
        for zeile in tables[bucket]:
            andere = tuple(sorted((f for f in zeile.get("faecher", ()) if f != fach),
                                  key=str.casefold))
            if not andere or zeile.get("jahrgang_anzahl", 0) < 2:
                zeilen.append(zeile)
                continue
            stern = sterne.setdefault(andere, "*" * (len(sterne) + 1))
            in_tabelle[stern] = andere
            zeilen.append({**zeile, "klasse": f"{zeile['klasse']} {stern}"})
        markiert[bucket] = zeilen
        erklaerungen[bucket] = [(stern, "auch für " + ", ".join(andere))
                                for stern, andere in sorted(in_tabelle.items(),
                                                            key=lambda e: len(e[0]))]
    return markiert, erklaerungen


# Hinweis unter der Tabelle der ausgemusterten Buchreihen aus der
# Planungsdatei (Vorgabe vom 2026-11-10): je weiteres Fach eine Zeile, Fächer
# und Jahrgänge bündig untereinander.
WEITER_TEXT = "weiterhin leihbar in"

# Je Fach (Fach, Gruppen); eine Gruppe ist (Kopf, Zusatz): „5, 6,“ ohne
# Zusatz, oder „7 (“ mit „ab 2027/2028),“ (app/planungsdruck.py, _gruppen).
Weiter = tuple[tuple[str, tuple[tuple[str, str], ...]], ...]


def _weiter_sterne(zeilen: list[dict]) -> tuple[list[dict], list[tuple[str, Weiter]]]:
    """Markiert ausgemusterte Buchreihen, die in anderen Fächern weiterhin
    leihbar sind (``weiter``: (Fach, Jahrgänge) je Fach, app/planungsdruck.py).

    Wie :func:`_sternchen`: jede Kombination bekommt einen Stern mehr, in der
    Reihenfolge ihres ersten Auftretens; das Zeichen hängt mit geschütztem
    Leerzeichen an den Jahrgängen. Zurück kommen die markierten Zeilen und je
    Stern seine Fächer, aufsteigend."""
    sterne: dict[Weiter, str] = {}
    markiert: list[dict] = []
    for zeile in zeilen:
        weiter = tuple(zeile.get("weiter", ()))
        if not weiter:
            markiert.append(zeile)
            continue
        stern = sterne.setdefault(weiter, "*" * (len(sterne) + 1))
        markiert.append({**zeile, "klasse": f"{zeile['klasse']}\xa0{stern}"})
    return markiert, [(stern, weiter) for weiter, stern in sterne.items()]


def _weiter_tabelle(weiter: list[tuple[str, Weiter]], breite: float) -> Table:
    """Die Erklärzeilen der Sterne als Raster: Stern, „weiterhin leihbar in“,
    „Fach:“, Jahrgänge. Jede Spalte ist so breit wie ihr breitester Text plus
    ein Leerzeichen; die Jahrgänge nehmen den Rest und brechen darin um.

    In den Jahrgängen beginnt jede Gruppe eine Zeile; ein Jahrgang mit Zusatz
    steht mit hängendem Einzug hinter „7 (“, so läuft dessen Umbruch bündig
    unter „ab“/„bis“/„von“ weiter (Vorgabe vom 2026-11-10)."""
    luecke = stringWidth(" ", BODY_FONT, ISBN_FONT_SIZE)
    # Je Zeile die drei Texte vor den Jahrgängen und die Gruppen der Jahrgänge.
    daten: list[tuple[tuple[str, str, str], tuple[tuple[str, str], ...]]] = [
        ((stern if i == 0 else "", WEITER_TEXT if i == 0 else "", f"{fach}:"), gruppen)
        for stern, faecher in weiter for i, (fach, gruppen) in enumerate(faecher)
    ]
    breiten = [
        max(stringWidth(texte[spalte], BODY_FONT, ISBN_FONT_SIZE) for texte, _ in daten)
        + luecke + WIDTH_EPSILON
        for spalte in range(3)
    ]
    breiten.append(max(breite - sum(breiten), MIN_WRAP_COL))
    zellen: list[list[Any]] = [
        [Paragraph(escape(text), ERKLAER_STYLE) for text in texte]
        + [[_jahrgangsgruppe(kopf, zusatz) for kopf, zusatz in gruppen]]
        for texte, gruppen in daten
    ]
    tabelle = Table(zellen, colWidths=breiten, hAlign="LEFT")
    tabelle.setStyle(_OHNE_POLSTER)
    return tabelle


_OHNE_POLSTER = TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
])


def _jahrgangsgruppe(kopf: str, zusatz: str) -> Paragraph:
    """Eine Gruppe der Jahrgänge: ein Absatz, mit Zusatz hängend hinter dem
    Kopf („7 (“) wie in der Spalte „Jahrgang“ (_zeilen_mit_einzug)."""
    stil = _haengend(ERKLAER_STYLE, kopf) if zusatz else ERKLAER_STYLE
    return Paragraph(escape(kopf + zusatz), stil)


def _anmerkungen_tabelle(zeilen: tuple[tuple[str, ...], ...], breite: float) -> Table:
    """Die Anmerkungen zu den Anträgen einer Buchreihe (app/planungsdruck.py,
    Vorgabe vom 2026-11-12) als Raster: je Antrag eine Zeile, die Zellen bündig
    untereinander. Jede Spalte ist so breit wie ihr breitester Text plus ein
    Leerzeichen; eine, die in keiner Zeile etwas hat, fällt weg. Die letzte
    nimmt den Rest und bricht darin um; ein Text mit EINZUG („Begründung: “)
    hängt hinter seinem Kopf, sein Umbruch läuft bündig unter dem Anfang des
    Begründungstexts weiter. Eine Spalte nur aus Zahlen (der Jahrgang) steht
    rechtsbündig, Einer über Einern, Zehner über Zehnern; ihr Leerzeichen
    steht dann rechts von der Zahl."""
    luecke = stringWidth(" ", BODY_FONT, ISBN_FONT_SIZE)
    n = max(len(zeile) for zeile in zeilen)
    voll = [tuple(zeile) + ("",) * (n - len(zeile)) for zeile in zeilen]
    spalten = [s for s in range(n) if any(zeile[s] for zeile in voll)]
    daten = [[zeile[s] for s in spalten] for zeile in voll]
    breiten = [
        max(_zeilen_breite(zeile[s], BODY_FONT, ISBN_FONT_SIZE) for zeile in daten)
        + luecke + WIDTH_EPSILON
        for s in range(len(spalten) - 1)
    ]
    breiten.append(max(breite - sum(breiten), MIN_WRAP_COL))
    rechts = [all(zeile[s].isdigit() for zeile in daten if zeile[s])
              for s in range(len(spalten))]
    zellen: list[list[Any]] = [[_anmerkung(text, rechts=rechts[s]) for s, text in enumerate(zeile)]
                               for zeile in daten]
    tabelle = Table(zellen, colWidths=breiten, hAlign="LEFT")
    tabelle.setStyle(_OHNE_POLSTER)
    tabelle.setStyle(TableStyle([("RIGHTPADDING", (s, 0), (s, -1), luecke)
                                 for s, zahl in enumerate(rechts) if zahl]))
    return tabelle


_ERKLAER_RECHTS = ParagraphStyle("Erklaerung-rechts", parent=ERKLAER_STYLE, alignment=TA_RIGHT)


def _anmerkung(text: str, *, rechts: bool = False) -> Paragraph:
    if rechts:
        return Paragraph(_markup(text, ()), _ERKLAER_RECHTS)
    kopf, _, rest = text.rpartition(EINZUG)
    stil = _haengend(ERKLAER_STYLE, kopf) if kopf else ERKLAER_STYLE
    return Paragraph(_markup(kopf + rest, ()), stil)


def iserv_quelle(listen_anzahl: int) -> str:
    """Quelle unten links in der Fußzeile der PDFs mit "IServ-Stand benutzen".

    "Erstellt: <Datum>" rückt dafür eine Zeile höher, auf die Grundlinie von
    "Seite n von N" (Vorgabe vom 2026-11-10). Einzahl wie in der Einleitung
    (:func:`iserv_fach_liste`): nur bei genau einer Bücherliste im Schuljahr.
    """
    return "IServ-Bücherliste" if listen_anzahl == 1 else "IServ-Bücherlisten"


# Quelle unten links in der Fußzeile aller Bücherlisten-PDFs ohne "IServ-Stand
# benutzen": sie zeigen den Stand der Buchplanung (Excel-Datei), nicht IServ
# (Vorgabe vom 2026-11-10). Immer Einzahl; gleiche Stelle und gleiche
# Verschiebung wie bei iserv_quelle().
PLANUNG_QUELLE = "Planungsbücherliste"


def _markup(text: str, stile: tuple[str, ...] | frozenset[str]) -> str:
    """Text für einen Paragraph: grau und/oder durchgestrichen (STIL_*)."""
    inhalt = escape(text.replace(EINZUG, "")).replace(ZEILENUMBRUCH, "<br/>")
    if STIL_DURCH in stile:
        inhalt = f"<strike>{inhalt}</strike>"
    if STIL_GRAU in stile:
        inhalt = f'<font color="{ANTRAG_GRAU_HEX}">{inhalt}</font>'
    return inhalt


def _zellstil(spalte: Spalte) -> ParagraphStyle:
    """Der Paragraph-Stil einer Spalte - wie ihr Klartext gesetzt (Größe, Ausrichtung)."""
    if spalte.schrift == CELL_FONT_SIZE and not spalte.rechts:
        return CELL_STYLE
    return ParagraphStyle(
        f"Zelle-{spalte.key}", parent=CELL_STYLE, fontSize=spalte.schrift,
        alignment=TA_RIGHT if spalte.rechts else CELL_STYLE.alignment,
    )


def _haengend(stil: ParagraphStyle, kopf: str) -> ParagraphStyle:
    """``stil`` mit hängendem Einzug um die Breite von ``kopf``."""
    breite = stringWidth(kopf, stil.fontName, stil.fontSize)
    return ParagraphStyle(f"{stil.name}-haengend", parent=stil,
                          leftIndent=breite, firstLineIndent=-breite)


def _zeilen_mit_einzug(
    teile: tuple[tuple[str, tuple[str, ...]], ...], eigen: frozenset[str], stil: ParagraphStyle,
) -> list[Paragraph]:
    """Je erzwungene Zeile ein Absatz; einer mit EINZUG hängend hinter seinem
    Kopf („7 (“), so beginnt der umgebrochene Zusatz bündig unter „ab“/„bis“/„von“."""
    zeilen: list[list[tuple[str, tuple[str, ...]]]] = [[]]
    for stueck, stile in teile:
        if stueck == ZEILENUMBRUCH:
            zeilen.append([])
        else:
            zeilen[-1].append((stueck, stile))
    absaetze = []
    for zeile in zeilen:
        inhalt = "".join(_markup(stueck, eigen | set(stile)) for stueck, stile in zeile)
        kopf = "".join(stueck for stueck, _ in zeile).partition(EINZUG)
        absaetze.append(Paragraph(inhalt, _haengend(stil, kopf[0]) if kopf[1] else stil))
    return absaetze


def _zelle(zeile: dict, spalte: Spalte) -> Any:
    """Eine Zelle: Klartext, oder ein Paragraph, wenn die Spalte umbricht oder
    die Zeile einen Stil hat (``stil``, ``klasse_teile``, app/planungsdruck.py).

    Ein Klartext-Wert, der nur wegen des Stils zum Paragraph wird, bekommt
    geschützte Leerzeichen: gemessen wurde er einzeilig, so bleibt er es.
    """
    text = zeile[spalte.key]
    zeilenstil = zeile.get("stil") or ""
    teile = zeile.get("klasse_teile") if spalte.key == "klasse" else None
    if not zeilenstil and not teile:
        if spalte.umbruch and ZEILENUMBRUCH in text:
            return Paragraph(_markup(text, frozenset()), CELL_STYLE)
        return Paragraph(text, CELL_STYLE) if spalte.umbruch else text
    eigen = frozenset((zeilenstil,)) if zeilenstil else frozenset()
    if teile and any(stueck == EINZUG for stueck, _ in teile):
        return _zeilen_mit_einzug(teile, eigen, _zellstil(spalte))
    if teile:
        inhalt = "".join(_markup(stueck, eigen | set(stile)) for stueck, stile in teile)
    else:
        inhalt = _markup(text if spalte.umbruch else text.replace(" ", "\xa0"), eigen)
    return Paragraph(inhalt, _zellstil(spalte))


def render_table(
    rows: list[dict], *, with_fee: bool, spalten: tuple[Spalte, ...] | None = None,
    erklaerungen: list[tuple[str, str]] | None = None,
    weiter: list[tuple[str, Weiter]] | None = None,
) -> Table:
    """Tabelle mit ``spalten`` (Default: die der Fachliste); ohne ``with_fee``
    entfällt die Leihgebühr.

    ``erklaerungen`` (Sterne, Text) stehen als weitere Zeilen unter der letzten,
    über die ganze Breite, kleiner und ohne Trennlinien (siehe _sternchen);
    ``weiter`` ebenso, als Raster (siehe _weiter_sterne, _weiter_tabelle).
    Die ``anmerkungen`` einer Zeile (app/planungsdruck.py) stehen als Raster
    in ihr unter ihren Zellen, über alle Spalten; die Trennlinie kommt erst
    darunter (siehe _anmerkungen_tabelle)."""
    if spalten is None:
        spalten = (KLASSE, TITEL, VERLAG, ISBN, NEUPREIS, LEIHGEBUEHR)
    spalten = tuple(sp for sp in spalten if with_fee or sp.key != "leihgebuehr")
    n_cols = len(spalten)
    n_gaps = n_cols - 1
    umbruch = [i for i, sp in enumerate(spalten) if sp.umbruch]
    assert umbruch, "mindestens eine umbrechende Spalte"

    # Für jeden der n_gaps Zwischenräume wird vorab MIN_GAP reserviert, bevor
    # Spaltenbreiten überhaupt berechnet werden — sonst kann der nach Schritt 4
    # rechnerisch übrige Platz pro Lücke gegen 0 gehen, wenn der Inhalt die
    # Tabellenbreite fast ausfüllt (beobachtet 2026-08-18: "12Duden..." ohne
    # sichtbaren Abstand). effective_width ist das Budget, mit dem Schritt 1-3
    # rechnen — der danach ermittelte Gesamtinhalt passt dadurch garantiert
    # mit mindestens MIN_GAP Luft pro Lücke in CONTENT_WIDTH.
    effective_width = CONTENT_WIDTH - MIN_GAP * n_gaps

    werte = [[r[sp.key] for r in rows] for sp in spalten]

    # 1) Jede Spalte zuerst mit ihrem kurzen Kopf ("Jg.", "Leihgeb.",
    #    "Rückl."); die einzeiligen sind so breit wie Kopf oder breitester Wert
    #    (Vorgabe vom 2026-11-11).
    koepfe = [sp.kurz or sp.kopf for sp in spalten]
    breiten = [0.0 if sp.umbruch else _raw_width(koepfe[i], werte[i], value_size=sp.schrift)
               for i, sp in enumerate(spalten)]

    # 2) Die umbrechenden Spalten teilen sich den Rest so, dass die Tabelle
    #    am wenigsten Zeilen hoch ist; jede ist danach nur so breit wie ihre
    #    breiteste Zeile (siehe _aufteilen).
    #    Passt nicht einmal jedes breiteste Wort, werden die zu breiten
    #    Wörter vorher getrennt (siehe _notfall_trennen).
    kopf_breiten = [_raw_width(koepfe[i], []) for i in umbruch]
    verfuegbar = effective_width - sum(breiten)
    teilbar = [[not (spalten[i].key == "klasse" and r.get("klasse_teile")) for r in rows]
               for i in umbruch]
    for i, getrennt in zip(umbruch, _notfall_trennen(
            [werte[i] for i in umbruch], kopf_breiten, verfuegbar, teilbar), strict=True):
        werte[i] = getrennt
    for i, breite in zip(umbruch, _aufteilen(
            [werte[i] for i in umbruch], kopf_breiten, verfuegbar), strict=True):
        breiten[i] = breite

    # 3) Bleibt Platz, werden möglichst viele Köpfe lang geschrieben (siehe
    #    _lange_koepfe). Erst danach wird verteilt, damit die dadurch breiter
    #    gewordenen Spalten in der Gleichverteilung berücksichtigt sind.
    lang = {i: max(breiten[i], _raw_width(sp.kopf, []))
            for i, sp in enumerate(spalten) if sp.kurz is not None}
    for i in _lange_koepfe(breiten, lang, effective_width):
        breiten[i] = lang[i]
        koepfe[i] = spalten[i].kopf

    # 4) Restplatz gleichmäßig auf alle Spaltenzwischenräume verteilen —
    #    jede Spalte bleibt exakt so breit wie ihr tatsächlich benötigter
    #    Inhalt (keine Spalte länger als der längste Inhalt einer Zeile).
    #    Dank effective_width in Schritt 1-3 ist gap hier immer >= MIN_GAP.
    #    Passt die Tabelle selbst nach der Notfall-Trennung nicht, bleibt es
    #    bei MIN_GAP und sie läuft rechts über, statt dass Text aneinanderstößt.
    total_content = sum(breiten)
    gap = max((CONTENT_WIDTH - total_content) / n_gaps, MIN_GAP) if n_gaps else 0.0
    half_gap = gap / 2

    # colWidths braucht die VOLLE Spaltenbreite inkl. ihres Anteils an der
    # Lücke (reportlab zieht das TableStyle-Padding von colWidth ab, um die
    # Textfläche zu bestimmen — reine Inhaltsbreite hier würde bei jeder
    # Spalte außer der ersten/letzten ins Negative laufen).
    col_widths = [
        w + (0.0 if i == 0 else half_gap) + (0.0 if i == n_cols - 1 else half_gap)
        for i, w in enumerate(breiten)
    ]

    # Notfall-getrennte Zellen bekommen ihre Zeilen fest: reportlab kennt
    # die TRENNSTELLE nicht, gesetzt wird wie gemessen.
    rows = [{**r, **{sp.key: ZEILENUMBRUCH.join(_wrap_lines(werte[i][z], breiten[i]))
                     for i, sp in enumerate(spalten) if TRENNSTELLE in werte[i][z]}}
            for z, r in enumerate(rows)]
    # Eine über alle Spalten gespannte Zelle hat rechts das Polster ihrer
    # ersten Spalte.
    spann_breite = sum(col_widths) - (half_gap if n_cols > 1 else 0.0)
    data: list[list] = [list(koepfe)]
    # Je Buchreihe ihre erste und letzte Zeile in data; mit Anmerkungen
    # (erst nach der Breitenberechnung angehängt, sie machen keine Spalte
    # breiter) sind es zwei.
    buchreihen: list[tuple[int, int]] = []
    for r in rows:
        data.append([_zelle(r, sp) for sp in spalten])
        anfang = len(data) - 1
        if r.get("anmerkungen"):
            data.append([_anmerkungen_tabelle(r["anmerkungen"], spann_breite)]
                        + [""] * (n_cols - 1))
        buchreihen.append((anfang, len(data) - 1))

    last_row = len(data) - 1
    # Tabellenbild wie im Original: keine Füllfarben, kein Gitternetz, 1.0pt
    # schwarze Linie unter der Kopfzeile, 1.0pt graue Trennlinie unter jeder
    # Datenzeile. Klasse/Titel/Verlag/ISBN linksbündig, Neupreis/Leihgebühr
    # rechtsbündig (nur Datenzeilen — die Kopfzeile bleibt linksbündig).
    style = [
        ("FONTNAME", (0, 0), (-1, 0), HEADER_FONT),
        ("FONTNAME", (0, 1), (-1, -1), BODY_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), CELL_FONT_SIZE),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, RULE_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        # Reportlab nimmt für Klartext-Zellen (Klasse/ISBN/Neupreis/Leihgebühr)
        # standardmäßig eine andere Zeilenhöhe an (fontSize*1.2) als für die
        # Paragraph-Zellen Titel/Verlag (CELL_STYLE.leading=11.5) — das ergab
        # bei einzeiligen Zeilen eine andere Zeilenhöhe als bei umbrochenen und
        # dadurch einen row-abhängigen Rest-Versatz. LEADING gleicht das an.
        ("LEADING", (0, 0), (-1, -1), CELL_STYLE.leading),
        # TOPPADDING/BOTTOMPADDING sind bewusst NICHT symmetrisch: reportlab
        # reserviert bei TOP-VALIGN über der Textzeile die volle Oberlänge und
        # darunter die volle Unterlänge. Optisch maßgeblich ist aber die
        # Versalhöhe oben (Oberkante Großbuchstabe) und die Grundlinie unten
        # (Unterkante ohne g/p/q/Komma) — dazwischen sitzt der Text sonst zu
        # hoch. VPAD_SHIFT verschiebt ihn so weit nach unten, dass der Abstand
        # Versalhöhe→Linie darüber und Grundlinie→Linie darunter gleich groß
        # ist (kalibriert 2026-08-19: gemessen wurde die Grundlinie aus der
        # Text-Matrix des PDFs plus Helvetica-CapHeight 718/1000 — pdfplumbers
        # char-Bounding-Box taugt dafür nicht, sie ist für JEDES Zeichen exakt
        # 1 em hoch, egal ob "D" oder "g"). Summe TOP+BOTTOM bleibt 2*CELL_VPAD,
        # die Zeilenhöhe ändert sich also nicht. Reine Y-Position —
        # Schriftgröße/-farbe bleiben unverändert.
        ("TOPPADDING", (0, 0), (-1, -1), CELL_VPAD - VPAD_SHIFT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_VPAD + VPAD_SHIFT),
        # ISBN ist mit 8pt kleiner als der restliche 10pt-Zeilentext (siehe
        # ISBN_FONT_SIZE) und hat damit eine kleinere Versalhöhe. Damit ihr
        # Versalhöhe/Grundlinie-Kasten auf derselben Mitte sitzt wie der der
        # 10pt-Spalten, muss ihre Grundlinie um die halbe Versalhöhen-Differenz
        # höher liegen — ISBN_VSHIFT stellt genau das ein. Reine Y-Position,
        # Schriftgröße bleibt 8pt.
        # ISBN_VSHIFT wird der ISBN-Spalte oben aufgeschlagen und unten wieder
        # abgezogen — die Zellenhöhe (und damit ggf. die Zeilenhöhe bei
        # einzeiligen Zeilen) bleibt dadurch identisch zu den anderen Spalten.
        # Gleicher Abstand zwischen allen Spalten: jede Innenkante bekommt die
        # halbe Lücke, außen (erste/letzte Spalte) bleibt 0 — Tabelle fluchtet
        # weiterhin links mit "Liste für"/Überschrift, rechts mit "gültig für".
        ("LEFTPADDING", (0, 0), (-1, -1), half_gap),
        ("RIGHTPADDING", (0, 0), (-1, -1), half_gap),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
    ]
    for i, sp in enumerate(spalten):
        if sp.schrift != CELL_FONT_SIZE:
            style.append(("FONTSIZE", (i, 1), (i, -1), sp.schrift))
        if sp.rechts:
            style.append(("ALIGN", (i, 1), (i, -1), "RIGHT"))
        if sp.key == "isbn":
            # Siehe ISBN_VSHIFT oben.
            style += [
                ("TOPPADDING", (i, 1), (i, -1), CELL_VPAD - VPAD_SHIFT + ISBN_VSHIFT),
                ("BOTTOMPADDING", (i, 1), (i, -1), CELL_VPAD + VPAD_SHIFT - ISBN_VSHIFT),
            ]
    for anfang, ende in buchreihen:
        style.append(("LINEBELOW", (0, ende), (-1, ende), 1.0, ROW_RULE_COLOR))
        if ende > anfang:
            # Die Anmerkungen gehören zur Buchreihe: keine Linie dazwischen,
            # nicht von ihr getrennt auf die nächste Seite.
            style += [
                ("SPAN", (0, ende), (-1, ende)),
                ("TOPPADDING", (0, ende), (-1, ende), 0),
                ("NOSPLIT", (0, anfang), (-1, ende)),
            ]
    if erklaerungen or weiter:
        # Erst nach der Breitenberechnung angehängt: die Erklärzeilen spannen
        # über alle Spalten und sollen keine Spalte breiter machen.
        for stern, text in erklaerungen or ():
            data.append([Paragraph(f"{escape(stern)} {escape(text)}", ERKLAER_STYLE)]
                        + [""] * (n_cols - 1))
        if weiter:
            data.append([_weiter_tabelle(weiter, spann_breite)] + [""] * (n_cols - 1))
        erste = last_row + 1
        style += [
            ("SPAN", (0, zeile), (-1, zeile)) for zeile in range(erste, len(data))
        ]
        style += [
            ("TOPPADDING", (0, erste), (-1, -1), 0),
            ("BOTTOMPADDING", (0, erste), (-1, -1), 0),
            ("TOPPADDING", (0, erste), (-1, erste), CELL_VPAD),
            # Nicht von der letzten Buchreihe getrennt auf die nächste Seite.
            ("NOSPLIT", (0, buchreihen[-1][0] if buchreihen else last_row), (-1, -1)),
        ]
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle(style))
    return table


class SubjectHeading(Flowable):
    """Kopfbereich + Überschrift an den exakten Positionen des Originals.

    Die drei Textzeilen werden **absolut** auf der Seite gezeichnet (Baselines
    und x-Kanten aus der offiziellen IServ-Bücherliste ausgemessen), nicht im
    normalen Textfluss positioniert. Der Flowable reserviert im Fluss nur die
    Höhe des Blocks, damit der Einleitungstext darunter beginnt.
    """

    def __init__(
        self, schoolyear_name: str, subject: str, *, confirm_value: str | None = None,
        return_by: str | None = None, return_to: str | None = None,
    ) -> None:
        super().__init__()
        self.schoolyear_name = schoolyear_name
        self.subject = subject
        self.confirm_value = confirm_value
        self.return_by = return_by
        self.return_to = return_to
        self.width = CONTENT_WIDTH
        self.height = HEADING_BLOCK_HEIGHT

    def _return_columns(self) -> list[tuple[str, str]]:
        """Spalten des Rückgabe-Blocks als (Label, Wert)-Paare.

        "Rückgabe" gehört immer zum ersten vorhandenen Wert: mit Datum heißen
        die Labels "Rückgabe bis" / "an", fehlt das Datum, steht über dem
        Kürzel "Rückgabe an". Fehlt ein Wert, entfällt seine Spalte ganz."""
        columns: list[tuple[str, str]] = []
        if self.return_by:
            columns.append(("Rückgabe bis", self.return_by))
        if self.return_to:
            columns.append(("an" if self.return_by else "Rückgabe an", self.return_to))
        return columns

    def _draw_middle_blocks(self, c: Canvas, dx: float, dy: float) -> None:
        """"Zu bestätigen durch" und Rückgabe-Angaben zwischen den Rand-Spalten.

        Beide stehen auf denselben beiden Grundlinien wie "Liste für"/
        <Schuljahr> links und "gültig für"/<Fach> rechts: Label in der kleinen,
        Wert in der großen Kopf-Schrift, Label jeweils mittig über seinem Wert.
        Die vier Teile (links, Bestätigung, Rückgabe, rechts) bekommen
        untereinander denselben Abstand — der nach allen Blockbreiten
        verbleibende Platz wird gleichmäßig auf die drei Lücken verteilt. Wird
        es eng (langer Fachname, langes Datum), schrumpft die große Schrift der
        beiden mittleren Blöcke, bis die Lücken wieder mindestens
        MIN_HEADER_BLOCK_GAP breit sind.

        Der Rückgabe-Block selbst besteht aus bis zu zwei Spalten (Datum,
        Kürzel), die untereinander nur zwei Leerzeichen der großen Schrift
        Abstand halten — sie gehören sichtbar zusammen.

        Ohne Rückgabe-Angaben bleibt die Bestätigung wie bisher mittig auf der
        Seite (unveränderte Ausgabe für Läufe ohne --return-by/--return-to)."""
        # Nur aufgerufen, wenn confirm_value gesetzt ist (siehe draw()).
        blocks: list[list[tuple[str, str]]] = [[("Zu bestätigen durch", self.confirm_value or "")]]
        return_columns = self._return_columns()
        if not return_columns:
            self._draw_centered_confirm(c, dx, dy)
            return
        blocks.append(return_columns)

        # Die Rand-Blöcke sind so breit wie ihr breiterer Text (Label oder
        # Wert) — sie sind links- bzw. rechtsbündig gesetzt und rücken nicht.
        left_w = max(
            c.stringWidth("Liste für", HEADER_LABEL_FONT, HEADER_LABEL_SIZE),
            c.stringWidth(self.schoolyear_name, HEADER_VALUE_FONT, HEADER_VALUE_SIZE),
        )
        right_w = max(
            c.stringWidth("gültig für", HEADER_LABEL_FONT, HEADER_LABEL_SIZE),
            c.stringWidth(self.subject, HEADER_VALUE_FONT, HEADER_VALUE_SIZE),
        )

        value_fs = HEADER_VALUE_SIZE
        while True:
            inner_gap = c.stringWidth("  ", HEADER_VALUE_FONT, value_fs)
            col_widths = [
                [
                    max(
                        c.stringWidth(value, HEADER_VALUE_FONT, value_fs),
                        c.stringWidth(label, HEADER_LABEL_FONT, HEADER_LABEL_SIZE),
                    )
                    for label, value in block
                ]
                for block in blocks
            ]
            block_widths = [
                sum(widths) + inner_gap * (len(widths) - 1) for widths in col_widths
            ]
            gap = (
                CONTENT_WIDTH - left_w - right_w - sum(block_widths)
            ) / (len(blocks) + 1)
            if gap >= MIN_HEADER_BLOCK_GAP or value_fs <= 7.0:
                break
            value_fs -= 0.25

        x = dx + LEFT_MARGIN + left_w
        for block, widths in zip(blocks, col_widths, strict=True):
            x += gap
            for (label, value), col_w in zip(block, widths, strict=True):
                center = x + col_w / 2
                c.setFont(HEADER_LABEL_FONT, HEADER_LABEL_SIZE)
                c.drawCentredString(center, dy + HEADER_LABEL_BASELINE, label)
                c.setFont(HEADER_VALUE_FONT, value_fs)
                c.drawCentredString(center, dy + HEADER_VALUE_BASELINE, value)
                x += col_w + inner_gap
            x -= inner_gap

    def _draw_centered_confirm(self, c: Canvas, dx: float, dy: float) -> None:
        """Nur "Zu bestätigen durch" + Kürzel, mittig auf der Seite.

        Wert-Zeile: bei langem Fachnamen + langem Ersatzwert (Fallback: Name
        statt Kürzel) notfalls verkleinern, damit nichts mit den beiden
        Rand-Werten kollidiert (analog Fußzeile)."""
        center_x = dx + FOOTER_CENTER_X

        # Label-Zeile ("Liste für"/"gültig für"-Höhe): kurzer, fester
        # Text — bei den üblichen Fach-/Jahr-Kürzeln links/rechts nie eng.
        c.setFont(HEADER_LABEL_FONT, HEADER_LABEL_SIZE)
        c.drawCentredString(center_x, dy + HEADER_LABEL_BASELINE, "Zu bestätigen durch")

        left_val_w = c.stringWidth(
            self.schoolyear_name, HEADER_VALUE_FONT, HEADER_VALUE_SIZE,
        )
        right_val_w = c.stringWidth(self.subject, HEADER_VALUE_FONT, HEADER_VALUE_SIZE)
        left_end = dx + LEFT_MARGIN + left_val_w
        right_start = dx + RIGHT_EDGE - right_val_w
        max_half_width = max(min(center_x - left_end, right_start - center_x) - 6, 10)

        center_fs = HEADER_VALUE_SIZE
        while (
            center_fs > 7.0
            and c.stringWidth(self.confirm_value, HEADER_VALUE_FONT, center_fs) / 2 > max_half_width
        ):
            center_fs -= 0.25

        c.setFont(HEADER_VALUE_FONT, center_fs)
        c.drawCentredString(center_x, dy + HEADER_VALUE_BASELINE, self.confirm_value)

    def draw(self) -> None:
        c = self.canv
        # draw() zeichnet in lokalen Koordinaten — Ursprung auf die absoluten
        # Seitenkoordinaten zurückrechnen, damit der Block unabhängig von
        # seiner Position im Fluss immer exakt gleich sitzt.
        origin_x, origin_y = c.absolutePosition(0, 0)
        dx, dy = -origin_x, -origin_y

        c.saveState()
        c.setFillColor(colors.black)
        c.setFont(HEADER_LABEL_FONT, HEADER_LABEL_SIZE)
        c.drawString(dx + LEFT_MARGIN, dy + HEADER_LABEL_BASELINE, "Liste für")
        c.drawRightString(dx + RIGHT_EDGE, dy + HEADER_LABEL_BASELINE, "gültig für")

        c.setFont(HEADER_VALUE_FONT, HEADER_VALUE_SIZE)
        c.drawString(
            dx + LEFT_MARGIN, dy + HEADER_VALUE_BASELINE,
            self.schoolyear_name,
        )
        c.drawRightString(dx + RIGHT_EDGE, dy + HEADER_VALUE_BASELINE, self.subject)

        if self.confirm_value:
            self._draw_middle_blocks(c, dx, dy)

        c.setFont(TITLE_FONT, TITLE_SIZE)
        c.drawString(dx + LEFT_MARGIN, dy + TITLE_BASELINE, f"Bücherliste {self.subject}")
        c.restoreState()


class ConfirmationBlock(Flowable):
    """Einleitungssatz + zwei Ankreuzfelder + Unterschrift-Zeile am Fach-Listenende.

    Einleitungssatz: "Hiermit bestätige ich im Namen der Fachschaft <Fach>,
    dass ...". Oberes Kreuz: die Liste ist NICHT korrekt und soll um die
    handschriftlich eingetragenen Änderungen ergänzt werden. Unteres Kreuz:
    die Bücher sind richtig. Fließt normal im Textfluss mit — bei kurzen
    Listen landet der Block dadurch am Ende der Tabellen, bei sehr langen
    ggf. auf einer eigenen Folgeseite.
    """

    # Abstände zwischen einleitendem Satz, den beiden Ankreuzzeilen und dem
    # Unterschriftsfeld: überall der Absatzabstand des Prüfauftrags (halbe
    # Leerzeile, siehe INTRO_PART_STYLE).
    INTRO_GAP = CHECKBOX_ROW_GAP = SIGNATURE_GAP = INTRO_PART_STYLE.spaceAfter

    def __init__(
        self, subject: str, schoolyear_name: str, book_count: int, grade_count: int | None = None, *,
        teacher_kuerzel: str | None = None, confirm_page: int | None = None,
    ) -> None:
        super().__init__()
        self.width = CONTENT_WIDTH
        signature_label = f"Unterschrift Fachkonferenzleitung {subject}"
        if teacher_kuerzel:
            signature_label += f" ({teacher_kuerzel})"
        # Verweis auf die Tabelle(n) weiter oben: "oben", solange das Fach nur
        # 1 Seite braucht; "umseitig", wenn die Bestätigung auf Seite 2 des
        # Fachs landet (die Tabelle also komplett auf der vorigen Seite
        # steht); ab Seite 3 "auf den vorliegenden Seiten" (Plural, da
        # mehrere Seiten vorausgehen können).
        if confirm_page is None or confirm_page <= 1:
            location = "oben"
        elif confirm_page == 2:
            location = "umseitig"
        else:
            location = "auf den vorliegenden Seiten"
        if book_count == 1:
            # Einzelnes Buch: Singular ("das ... Buch", "seine", "dessen")
            # statt Plural ("die ... Bücher", "ihre", "deren"). Die
            # Klassenstufe(n) richten sich dabei nach den tatsächlich diesem
            # einen Buch zugeordneten Klassenstufen, nicht nach der Bücherzahl.
            klassenstufe_word = "Klassenstufe" if grade_count == 1 else "Klassenstufen"
            intro_text = (
                f"Hiermit bestätige ich im Namen der Fachschaft {subject}, dass die {location} "
                f"aufgeführte <b>Bücherliste {subject}</b>, das heißt das durch seine "
                f"<b>ISBN</b> beschriebene Buch und dessen zugeordnete <b>{klassenstufe_word}</b>, "
                f"für das <b>{schoolyear_name}</b> ..."
            )
        else:
            intro_text = (
                f"Hiermit bestätige ich im Namen der Fachschaft {subject}, dass die {location} "
                f"aufgeführte <b>Bücherliste {subject}</b>, das heißt die durch ihre <b>ISBN</b> "
                f"beschriebenen Bücher und deren zugeordnete <b>Klassenstufen</b>, für das "
                f"<b>{schoolyear_name}</b> ..."
            )
        self._intro_par = Paragraph(intro_text, CONFIRM_STYLE)
        _, self._intro_h = self._intro_par.wrap(self.width, 0xFFFFFF)

        text_width = self.width - CHECKBOX_SIZE - 6
        self._checkbox_pars = [
            Paragraph(
                "... <b>nicht korrekt</b> ist und um die <b>handschriftlichen Anmerkungen</b> "
                "(Durchstreichungen, Eintragungen neuer Bücher, Klassen, ...) "
                "verändert werden muss.",
                CONFIRM_STYLE,
            ),
            Paragraph(
                "... <b>korrekt</b> ist, <b>an</b> die <b>Schüler übermittelt</b> werden kann und eine "
                "<b>nachträgliche Änderung</b> unter Umständen <b>nicht</b> mehr <b>gestattet</b> werden "
                "kann.",
                CONFIRM_STYLE,
            ),
        ]
        self._checkbox_heights = [p.wrap(text_width, 0xFFFFFF)[1] for p in self._checkbox_pars]
        checkbox_block_h = (
            sum(max(h, CHECKBOX_SIZE) for h in self._checkbox_heights)
            + self.CHECKBOX_ROW_GAP
        )

        # Linke Hälfte: "Ort, Datum" mit einer Linie. Rechte Hälfte:
        # "Unterschrift Fachkonferenzleitung <Fach>" mit einer eigenen Linie.
        # Eine leere Spalter dazwischen (ohne Linie) sorgt für einen
        # sichtbaren Spalt zwischen den beiden Linien.
        sig_col_w = (self.width - SIGNATUR_SPALT) / 2
        self._sig_table = Table(
            [
                ["", "", ""],
                [
                    Paragraph("Ort, Datum", SIGNATURE_LABEL_STYLE),
                    "",
                    Paragraph(signature_label, SIGNATURE_LABEL_STYLE),
                ],
            ],
            colWidths=[sig_col_w, SIGNATUR_SPALT, sig_col_w],
            rowHeights=[SIGNATURE_LINE_HEIGHT, None],
        )
        self._sig_table.setStyle(TableStyle([
            ("LINEABOVE", (0, 1), (0, 1), 0.75, colors.black),
            ("LINEABOVE", (2, 1), (2, 1), 0.75, colors.black),
            ("TOPPADDING", (0, 1), (-1, 1), 2.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ]))
        _, self._sig_h = self._sig_table.wrap(self.width, 0xFFFFFF)
        self.height = self._intro_h + self.INTRO_GAP + checkbox_block_h + self.SIGNATURE_GAP + self._sig_h

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setLineWidth(0.75)
        c.setStrokeColor(colors.black)
        self._intro_par.drawOn(c, 0, self.height - self._intro_h)
        y = self.height - self._intro_h - self.INTRO_GAP
        for par, par_h in zip(self._checkbox_pars, self._checkbox_heights, strict=True):
            row_h = max(par_h, CHECKBOX_SIZE)
            # Mittig in dem Band, das die beiden Textzeilen aufspannen: von der
            # Versalhöhe der ersten Zeile bis zur Grundlinie der zweiten.
            # reportlab setzt die erste Grundlinie fontSize unter die
            # Paragraph-Oberkante (rl_config paraFontSizeHeightOffset=1, siehe
            # Paragraph.drawPara).
            first_baseline = y - CONFIRM_STYLE.fontSize
            band_top = first_baseline + CONFIRM_CAP_HEIGHT
            band_bottom = first_baseline - CONFIRM_STYLE.leading
            box_bottom = (band_top + band_bottom - CHECKBOX_SIZE) / 2
            c.rect(0, box_bottom, CHECKBOX_SIZE, CHECKBOX_SIZE)
            par.drawOn(c, CHECKBOX_SIZE + 6, y - par_h)
            y -= row_h + self.CHECKBOX_ROW_GAP
        self._sig_table.drawOn(c, 0, 0)
        c.restoreState()


class BottomAnchor(Flowable):
    """Drückt `inner` an das untere Ende des verbleibenden Frame-Bereichs.

    Beansprucht immer die komplette auf der aktuellen Seite noch verfügbare
    Höhe (statt nur die eigene Inhaltshöhe), sodass `inner` beim Zeichnen
    unten in dieser Fläche landet — also direkt über der Fußzeile, egal wie
    viel Text/Tabellen vorher im Frame stehen. Passt `inner` nicht mehr auf
    die aktuelle Seite, wird der komplette Block (reportlab-Standardverhalten
    für nicht teilbare Flowables) auf die nächste Seite verschoben, wo er
    dann entsprechend am unteren Rand der neuen, leeren Fläche sitzt.
    """

    def __init__(self, inner: Flowable) -> None:
        super().__init__()
        self.inner = inner

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        _, inner_h = self.inner.wrap(availWidth, availHeight)
        self._inner_h = inner_h
        # Passt inner nicht in den Rest der aktuellen Seite: mehr Höhe
        # melden, als zur Verfügung steht, damit reportlab den gesamten Block
        # auf die nächste Seite verschiebt statt ihn hier abzuschneiden.
        self.height = availHeight if inner_h <= availHeight else availHeight + inner_h
        return availWidth, self.height

    def draw(self) -> None:
        self.inner.drawOn(self.canv, 0, 0)


class _RecordPage(Flowable):
    """Nullgroßes Flowable: merkt sich beim Layout die Seitenzahl an dieser
    Stelle im Textfluss (in `holder[0]`) — Grundlage für `_PadToEvenPages`.

    `_ZEROSIZE` weist reportlabs Frame an, `wrap()` auch dann noch
    aufzurufen, wenn im Frame kein Platz mehr übrig ist (z.B. weil ein
    vorangehendes `BottomAnchor` bereits die komplette Resthöhe der Seite für
    sich beansprucht hat) — ohne das würde Frame._add() bei Resthöhe 0 sofort
    (ohne wrap()-Aufruf) auf die nächste Seite ausweichen, und die hier
    gemessene Seitenzahl wäre dann schon die der falschen, nächsten Seite."""

    _ZEROSIZE = 1

    def __init__(self, holder: list) -> None:
        super().__init__()
        self.width = self.height = 0
        self.holder = holder

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.holder[0] = self.canv.getPageNumber()
        return 0, 0

    def draw(self) -> None:
        pass


class _PadToEvenPages(Flowable):
    """Erzwingt eine zusätzliche Leerseite, wenn das Fach seit dem
    zugehörigen `_RecordPage` eine ungerade Seitenzahl belegt (--duplex: jedes
    Fach soll mit gerader Seitenzahl enden, damit beim doppelseitigen Druck
    kein Fach auf der Rückseite eines anderen beginnt).

    Nutzt denselben Trick wie `BottomAnchor`: mehr Höhe melden, als auf der
    aktuellen Seite noch verfügbar ist, damit reportlab dieses (unsichtbare)
    Flowable auf eine neue, sonst leere Seite verschiebt.

    `blank_pages`, falls übergeben, wird um die Seitenzahl der so erzwungenen
    Leerseite ergänzt — `make_footer()` lässt deren Fußzeile dadurch weg,
    damit die Seite wirklich komplett leer bleibt (weißes Blatt, keine
    Kopf-/Fußzeile), wie es für doppelseitigen Druck erwartet wird.

    `_ZEROSIZE` (siehe `_RecordPage`) ist hier essenziell: ohne sie würde
    reportlab bei Resthöhe 0 (typischer Fall direkt nach `BottomAnchor`)
    automatisch und ungefragt eine neue Seite beginnen, bevor `wrap()`
    überhaupt zum Zuge kommt — die Entscheidung "muss gepolstert werden"
    fiele dann immer auf der bereits (fälschlich) neuen Seite, nie auf der
    tatsächlich letzten Inhaltsseite."""

    _ZEROSIZE = 1

    def __init__(self, start_page_holder: list, blank_pages: set[int] | None = None) -> None:
        super().__init__()
        self.width = self.height = 0
        self.start_page_holder = start_page_holder
        self.blank_pages = blank_pages

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        current_page = self.canv.getPageNumber()
        pages_used = current_page - self.start_page_holder[0] + 1
        if pages_used % 2 == 1:
            if self.blank_pages is not None:
                self.blank_pages.add(current_page + 1)
            return availWidth, availHeight + 1
        return 0, 0

    def draw(self) -> None:
        pass


class _RecordEndPage(Flowable):
    """Nullgroßes Flowable (siehe `_RecordPage`): merkt sich am Fach-Ende die
    aktuelle Seitenzahl in `results[index]`, ohne — anders als
    `_PadToEvenPages` — je eine Leerseite zu erzwingen. Grundlage für den
    Messlauf hinter `--duplex-if-needed` (`measure_subject_pages()`): dort
    soll nur die *natürliche* Seitenzahl je Fach ermittelt werden.

    Braucht `_ZEROSIZE` aus demselben Grund wie `_PadToEvenPages`: ohne sie
    würde reportlab bei Resthöhe 0 (typisch direkt nach `BottomAnchor`) schon
    selbst auf eine neue Seite wechseln, bevor `wrap()` aufgerufen wird — die
    hier gemessene Seitenzahl wäre dann um eins zu hoch."""

    _ZEROSIZE = 1

    def __init__(self, start_page_holder: list, results: list[int], index: int) -> None:
        super().__init__()
        self.width = self.height = 0
        self.start_page_holder = start_page_holder
        self.results = results
        self.index = index

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        current_page = self.canv.getPageNumber()
        self.results[self.index] = current_page - self.start_page_holder[0] + 1
        return 0, 0

    def draw(self) -> None:
        pass


def subject_story(
    subject: str, tables: dict[str, list[dict]], schoolyear_name: str, *,
    confirmation: bool = False, fkl_map: dict[str, str] | None = None,
    kollegium_map: dict[str, str] | None = None, duplex: bool = False,
    blank_pages: set[int] | None = None, confirmation_page_count: int | None = None,
    return_by: str | None = None, return_to: str | None = None, art: Listenart = FACH_LISTE,
) -> list:
    confirm_value = None
    teacher_kuerzel = None
    if confirmation:
        fkl_name = find_mapped_value(fkl_map or {}, subject)
        teacher_kuerzel = find_kollegium_kuerzel(kollegium_map or {}, fkl_name)
        # Kopfzeile zeigt bevorzugt das Kürzel; ist das nicht auflösbar,
        # ersatzweise der Name, sonst ein Platzhalter (nie komplett leer).
        confirm_value = teacher_kuerzel or fkl_name or "–"

    start_page_holder: list = [None]
    story: list = []
    if duplex:
        story.append(_RecordPage(start_page_holder))
    story += [
        SubjectHeading(
            schoolyear_name, subject, confirm_value=confirm_value,
            return_by=return_by if confirmation else None,
            return_to=return_to if confirmation else None,
        ),
        Paragraph(art.einleitung.format(name=subject), INTRO_STYLE),
    ]
    erklaerungen: dict[str, list[tuple[str, str]]] = {"leih": [], "kauf": []}
    if art.sternchen:
        tables, erklaerungen = _sternchen(subject, tables)
        if any(erklaerungen.values()):
            # Der Hinweis nur, wenn es Sternchen gibt; als zweiter Absatz mit
            # einer halben Leerzeile Abstand.
            story[-1:] = [
                Paragraph(art.einleitung.format(name=subject), INTRO_ABSATZ_STYLE),
                Paragraph(STERNCHEN_HINWEIS, INTRO_STYLE),
            ]
    book_count = len(tables["leih"]) + len(tables["kauf"])
    # Bei genau einem Buch entscheidet die Anzahl seiner Klassenstufen
    # (Spalte "klasse", z.B. "5" oder "5, 6") über Singular/Plural.
    grade_count = None
    if book_count == 1:
        only_row = (tables["leih"] or tables["kauf"])[0]
        # Mit Antragsinformationen stehen auch Kommas im Zusatz („von … bis …“).
        grade_count = only_row.get("jahrgang_anzahl") or only_row["klasse"].count(",") + 1
    if confirmation:
        # Bestätigungs-Lauf: statt des Einleitungssatzes ein Prüfauftrag an die
        # Fachkonferenzleitung, dessen letzter Absatz auf die beiden
        # Ankreuzfelder im ConfirmationBlock abgestimmt ist. Singular/Plural
        # wie im ConfirmationBlock.
        if book_count == 1:
            klassenstufe_word = "Klassenstufe" if grade_count == 1 else "Klassenstufen"
            books_text = f"das durch seine ISBN beschriebene Buch und dessen zugeordnete {klassenstufe_word}"
        else:
            books_text = "die durch ihre ISBN beschriebenen Bücher und deren zugeordnete Klassenstufen"
        story[-1:] = [
            Paragraph(
                f"Bitte prüfen Sie als Fachkonferenzleitung {subject} im Namen der "
                f"Fachschaft {subject} die folgende Bücherliste {subject}, das heißt "
                f"{books_text}, für das {schoolyear_name}.",
                INTRO_PART_STYLE,
            ),
            Paragraph(
                "Da ein Buch durch seine ISBN eindeutig beschrieben wird, kann der Titel vom "
                "Originaltitel des Buches abweichen und gegebenenfalls auch im nachhinein noch einmal "
                "verändert werden, um z. B. Bücher für verschiedene Leistungsniveaus leichter "
                "auseinanderhalten zu können. Die Leihgebühr dient nur der Information. Sie ergibt "
                "sich aus dem Neupreis des Buches und der Anzahl der Jahrgänge, für die es "
                "vorgesehen ist.",
                INTRO_PART_STYLE,
            ),
            Paragraph(
                "Bitte korrigieren Sie, falls ISBN falsch sind, falsche Klassenstufen zugeordnet "
                "sind, neue Bücher angeschafft oder alte ausgemustert werden sollen, dies "
                "handschriftlich und bestätigen Sie am Ende die Gültigkeit dieser Änderungen, oder "
                "notieren Sie, falls gewünscht, handschriftlich Änderungsvorschläge für Buchtitel "
                "und bestätigen Sie am Ende die Gültigkeit der Bücherliste. Beachten Sie bitte, dass "
                "Änderungsvorschläge für Buchtitel gegebenenfalls nicht oder auch nur abgeändert "
                "übernommen werden.",
                INTRO_CONFIRM_STYLE,
            ),
        ]

    def leih_spalten(zeilen: list[dict]) -> tuple[Spalte, ...]:
        if any(zeile.get("ruecklage") for zeile in zeilen):
            return (*art.spalten, RUECKLAGEN)
        return art.spalten

    # "Buchreihen" statt "Bücher" in den Überschriften (Vorgabe vom 2026-11-10).
    story.append(Paragraph("Leihbare Buchreihen", SECTION_STYLE))
    if tables["leih"]:
        story.append(render_table(tables["leih"], with_fee=True, spalten=leih_spalten(tables["leih"]),
                                  erklaerungen=erklaerungen["leih"]))
    else:
        story.append(Paragraph(art.leer_leih, EMPTY_STYLE))

    story.append(Paragraph("Selbst anzuschaffende Buchreihen", SECTION_STYLE))
    if tables["kauf"]:
        story.append(render_table(tables["kauf"], with_fee=False, spalten=art.spalten,
                                  erklaerungen=erklaerungen["kauf"]))
    else:
        story.append(Paragraph(art.leer_kauf, EMPTY_STYLE))

    # Nur aus der Planungsdatei (app/planungsdruck.py) und nur, wenn es welche
    # gibt; Spalten wie die leihbaren (Vorgabe vom 2026-11-10).
    if tables.get("ausgemustert"):
        story.append(Paragraph("Leihbare nach vorigem Schuljahr ausgemusterte Buchreihen",
                               SECTION_STYLE))
        ausgemustert, weiter = _weiter_sterne(tables["ausgemustert"])
        story.append(render_table(ausgemustert, with_fee=True,
                                  spalten=leih_spalten(ausgemustert), weiter=weiter))

    if confirmation:
        story.append(
            BottomAnchor(
                ConfirmationBlock(
                    subject, schoolyear_name, book_count, grade_count,
                    teacher_kuerzel=teacher_kuerzel, confirm_page=confirmation_page_count,
                )
            )
        )

    if duplex:
        story.append(_PadToEvenPages(start_page_holder, blank_pages))

    return story


def measure_subject_pages(
    subjects: list[str], by_subject: dict[str, dict[str, list[dict]]], schoolyear_name: str, *,
    confirmation: bool, fkl_map: dict[str, str], kollegium_map: dict[str, str],
    return_by: str | None = None, return_to: str | None = None, art: Listenart = FACH_LISTE,
) -> list[int]:
    """Baut alle Fächer einmal probeweise in einen verworfenen Speicherpuffer
    (kein Datei-Output), jedes mit eigenem, frisch beginnendem PageTemplate —
    damit ist die ermittelte Seitenzahl je Fach unabhängig vom später
    tatsächlich gewählten `--mode` (split/alphabet/aufgabenfeld) und entspricht exakt der
    natürlichen (ungepolsterten) Seitenzahl, die dieses Fach auch im
    Enddokument bräuchte.

    Grundlage für `--duplex-if-needed`: nur wenn dabei mindestens ein Fach
    bereits mehr als eine Seite braucht, lohnt sich das Anhängen von
    Leerseiten für den doppelseitigen Druck (siehe `main()`)."""
    doc = BaseDocTemplate(
        io.BytesIO(), pagesize=A4, leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=PAGE_H - FRAME_TOP, bottomMargin=BOTTOM_MARGIN,
    )
    page_counts: list[int] = [0] * len(subjects)
    templates = []
    story: list = []
    for i, subject in enumerate(subjects):
        frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN, CONTENT_WIDTH, FRAME_TOP - BOTTOM_MARGIN,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=f"measure-{i}",
        )
        template_id = f"measure-{i}"
        templates.append(PageTemplate(id=template_id, frames=[frame]))
        if i > 0:
            story.append(NextPageTemplate(template_id))
            story.append(PageBreak())
        start_page_holder: list = [None]
        story.append(_RecordPage(start_page_holder))
        story.extend(
            subject_story(
                subject, by_subject[subject], schoolyear_name,
                confirmation=confirmation, fkl_map=fkl_map, kollegium_map=kollegium_map, duplex=False,
                return_by=return_by, return_to=return_to, art=art,
            )
        )
        story.append(_RecordEndPage(start_page_holder, page_counts, i))
    doc.addPageTemplates(templates)
    doc.build(story)
    return page_counts


def footer_context(
    subject_or_label: str, schoolyear_name: str, *,
    school_name: str | None = None, school_city: str | None = None,
) -> str:
    """Rechtsbündiger Fußzeilentext, Wort für Wort wie im Original-PDF
    aufgebaut ("<Schule>, <Ort> – Bücherliste <Kontext> (Schuljahr 26/27)") —
    nur der Kontext ist hier das Fach bzw. "Fächer" statt "Jahrgang X".

    Schule und Ort kommen aus der Ausleihe-API (``GET /school/address``); ohne
    Angabe bleibt es bei SCHOOL_NAME/SCHOOL_CITY."""
    return (
        f"{school_name or SCHOOL_NAME}, {school_city or SCHOOL_CITY} – "
        f"Bücherliste {subject_or_label} ({schoolyear_name})"
    )


def make_footer(
    center_text: str, *, page_offset_holder: list | None = None, blank_pages: set[int] | None = None,
    quelle: str | None = None,
) -> Callable[[Canvas, BaseDocTemplate], None]:
    """onPage-Callback: Fußzeile wie in den offiziellen IServ-Bücherlisten.

    Gezeichnet wird hier noch nichts — die Fußzeile nennt "Seite n von N", und
    N steht erst fest, wenn das Dokument fertig gesetzt ist. Der Callback legt
    darum nur die Angaben der aktuellen Seite auf dem Canvas ab; `FooterCanvas`
    zeichnet sie am Ende des Builds nach (siehe dort).

    `page_offset_holder` ist ein einelementiger mutabler Fach-eigener
    Zwischenspeicher (`[None]`): wird beim ersten Aufruf mit der aktuellen
    (dokumentweiten) `doc.page` belegt, sodass die angezeigte Seitenzahl für
    dieses Fach wieder bei 1 beginnt, statt über das gesamte kombinierte PDF
    durchzuzählen (siehe write_combined_confirmation_pdf).

    `blank_pages` (--duplex) listet die von `_PadToEvenPages` erzwungenen
    Leerseiten dieses Dokuments — auf ihnen wird gar nichts gezeichnet, auch
    keine Fußzeile, damit sie beim doppelseitigen Druck wirklich komplett
    leer (weiß) bleiben.

    `quelle` (z. B. iserv_quelle()) steht unten links; "Erstellt: <Datum>"
    rückt dann eine Zeile höher (siehe draw_footer)."""
    generated = datetime.now().strftime("%d.%m.%Y")

    def _draw(c: Canvas, doc: BaseDocTemplate) -> None:
        if blank_pages is not None and doc.page in blank_pages:
            return
        if page_offset_holder is not None:
            if page_offset_holder[0] is None:
                page_offset_holder[0] = doc.page
            page_num = doc.page - page_offset_holder[0] + 1
        else:
            page_num = doc.page
        # Gruppenschlüssel für "von N": im kombinierten Bestätigungs-PDF zählt
        # jedes Fach eigenständig, und dort ist center_text je Fach verschieden.
        c._footer_spec = (center_text, page_num, generated, quelle)

    return _draw


def draw_footer(
    c: Canvas, page_num: int, total_pages: int, center_text: str, generated: str,
    quelle: str | None = None,
) -> None:
    """Zeichnet die zweizeilige Fußzeile an den aus dem Original übernommenen
    absoluten Grundlinien (FOOTER_PAGE_BASELINE / FOOTER_INFO_BASELINE).

    Mit ``quelle`` steht links unten die Quelle und "Erstellt: <Datum>" eine
    Zeile darüber, neben "Seite n von N" (Vorgabe vom 2026-11-10)."""
    c.saveState()
    c.setFillColor(FOOTER_COLOR)
    c.setFont(FOOTER_FONT, FOOTER_SIZE)
    c.drawRightString(RIGHT_EDGE, FOOTER_PAGE_BASELINE, f"Seite {page_num} von {total_pages}")
    if quelle:
        c.drawString(LEFT_MARGIN, FOOTER_PAGE_BASELINE, f"Erstellt: {generated}")
        c.drawString(LEFT_MARGIN, FOOTER_INFO_BASELINE, quelle)
    else:
        c.drawString(LEFT_MARGIN, FOOTER_INFO_BASELINE, f"Erstellt: {generated}")
    c.drawRightString(RIGHT_EDGE, FOOTER_INFO_BASELINE, center_text)
    c.restoreState()


class FooterCanvas(Canvas):
    """Canvas, der die Fußzeilen erst nach dem Setzen des Dokuments zeichnet.

    Nötig für "Seite n von N": die Gesamtseitenzahl ist während des Builds noch
    unbekannt. Jede Seite wird darum zunächst zwischengespeichert; `save()`
    stellt sie einzeln wieder her, zeichnet die Fußzeile (jetzt mit bekanntem
    N) und gibt sie erst dann aus.

    N ist die Seitenzahl der jeweiligen Fußzeilen-Gruppe (`center_text`), damit
    im kombinierten Bestätigungs-PDF jedes Fach für sich zählt. Seiten ohne
    hinterlegte Angaben (`--duplex`-Leerseiten) bleiben leer und zählen nicht
    mit."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []
        self._footer_specs: list[tuple | None] = []
        self._footer_spec: tuple | None = None

    def showPage(self) -> None:
        self._footer_specs.append(self._footer_spec)
        self._footer_spec = None
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        # Lokale Kopien: __dict__.update() unten überschreibt die Attribute
        # mit dem Stand der jeweiligen Seite.
        states, specs = self._saved_states, self._footer_specs
        totals: dict[str, int] = {}
        for spec in specs:
            if spec is not None:
                totals[spec[0]] = max(totals.get(spec[0], 0), spec[1])
        for state, spec in zip(states, specs, strict=True):
            self.__dict__.update(state)
            if spec is not None:
                center_text, page_num, generated, quelle = spec
                draw_footer(self, page_num, totals[center_text], center_text, generated, quelle)
            super().showPage()
        super().save()


def _ziel(path: str | Path | BinaryIO) -> str | BinaryIO:
    return path if hasattr(path, "write") else str(path)  # type: ignore[return-value]


def write_pdf(
    path: str | Path | BinaryIO, story: list, title: str, footer_center: str, *,
    blank_pages: set[int] | None = None, quelle: str | None = None,
) -> None:
    # BaseDocTemplate statt SimpleDocTemplate: dessen Frame hat 6pt Innenrand,
    # der den Inhalt gegenüber den Seitenrändern verschiebt. Hier soll der Text
    # exakt auf LEFT_MARGIN/RIGHT_EDGE sitzen → Frame-Padding auf 0.
    doc = BaseDocTemplate(
        _ziel(path),
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=PAGE_H - FRAME_TOP,
        bottomMargin=BOTTOM_MARGIN,
        title=title,
    )
    frame = Frame(
        LEFT_MARGIN, BOTTOM_MARGIN, CONTENT_WIDTH, FRAME_TOP - BOTTOM_MARGIN,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="content",
    )
    doc.addPageTemplates(
        [PageTemplate(id="fach", frames=[frame],
                      onPage=make_footer(footer_center, blank_pages=blank_pages, quelle=quelle))]
    )
    doc.build(story, canvasmaker=FooterCanvas)


def write_je_fach_pdf(
    path: str | Path | BinaryIO, subjects: list[str], schoolyear_name: str,
    story_fuer: Callable[[int, str, set[int]], list], *, title: str,
    school_name: str | None = None, school_city: str | None = None, quelle: str | None = None,
) -> None:
    """Ein PDF mit mehreren Fächern, in dem jedes Fach seine Seiten selbst zählt.

    Je Fach ein eigenes PageTemplate: die Seitenzahl beginnt je Fach bei 1,
    und die Fußzeile nennt das jeweilige Fach statt "Fächer". ``story_fuer``
    bekommt Index, Fach und die gemeinsame Menge der Leerseiten und liefert
    die Story dieses Fachs.
    """
    doc = BaseDocTemplate(
        _ziel(path), pagesize=A4, leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=PAGE_H - FRAME_TOP, bottomMargin=BOTTOM_MARGIN, title=title,
    )
    # Eine gemeinsame blank_pages-Menge über das ganze (kombinierte) Dokument
    # hinweg — Seitenzahlen sind dokumentweit eindeutig, auch über die
    # per-Fach-PageTemplates hinweg, daher genügt ein einziges Set.
    blank_pages: set[int] = set()
    templates = []
    story: list = []
    for i, subject in enumerate(subjects):
        frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN, CONTENT_WIDTH, FRAME_TOP - BOTTOM_MARGIN,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=f"content-{i}",
        )
        footer_center = footer_context(
            subject, schoolyear_name, school_name=school_name, school_city=school_city,
        )
        template_id = f"fach-{i}"
        templates.append(
            PageTemplate(
                id=template_id, frames=[frame],
                onPage=make_footer(footer_center, page_offset_holder=[None],
                                   blank_pages=blank_pages, quelle=quelle),
            )
        )
        if i > 0:
            story.append(NextPageTemplate(template_id))
            story.append(PageBreak())
        story.extend(story_fuer(i, subject, blank_pages))
    doc.addPageTemplates(templates)
    doc.build(story, canvasmaker=FooterCanvas)


def write_combined_confirmation_pdf(
    path: str | Path | BinaryIO, subjects: list[str], by_subject: dict[str, dict[str, list[dict]]],
    schoolyear_name: str, *, fkl_map: dict[str, str], kollegium_map: dict[str, str], title: str,
    duplex: bool = False, page_counts: list[int] | None = None,
    return_by: str | None = None, return_to: str | None = None,
    school_name: str | None = None, school_city: str | None = None, quelle: str | None = None,
) -> None:
    """Wie write_pdf, aber ein eigenes PageTemplate je Fach: mit --confirmation
    soll die Seitenzahl je Fach wieder bei 1 beginnen und die Fußzeile das
    jeweilige Fach statt "Fächer" nennen (Bestätigungs-Vorlage ist pro Fach an
    eine reale Person adressiert, da wirkt eine durchlaufende Gesamt-
    Seitenzahl/"Fächer"-Fußzeile über das ganze Dokument fehl am Platz)."""
    def story_fuer(i: int, subject: str, blank_pages: set[int]) -> list:
        return subject_story(
            subject, by_subject[subject], schoolyear_name,
            confirmation=True, fkl_map=fkl_map, kollegium_map=kollegium_map, duplex=duplex,
            blank_pages=blank_pages,
            confirmation_page_count=page_counts[i] if page_counts else None,
            return_by=return_by, return_to=return_to,
        )

    write_je_fach_pdf(path, subjects, schoolyear_name, story_fuer, title=title,
                      school_name=school_name, school_city=school_city, quelle=quelle)


def sanitize_filename(name: str) -> str:
    return name.replace("/", "-")

