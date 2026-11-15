"""Die Regeln der Mehrjahresbände-Übersicht, jede einzeln.

Ohne Netz, ohne Datei, ohne IServ: ``vergleiche`` bekommt zwei
:class:`Schuljahr`-Objekte und gibt die fertige Matrix zurück. Genau deshalb
steht sie in einem eigenen Modul - die Regeln sind die Stelle, an der ein
Fehler teuer ist (eine Klasse gibt Bücher ab, die sie behalten dürfte), und
hier kosten sie drei Zeilen Testdaten.
"""
from __future__ import annotations

from datetime import date

import pytest

from mehrjahresbaende.core import Jahrgangsliste, Schuljahr, vergleiche
from mehrjahresbaende.core.laden import UnbekanntesSchuljahr, vorjahr_kennung
from mehrjahresbaende.core.modelle import Buchvorkommen

FELDER = {"Deutsch": "Aufgabenfeld A", "Englisch": "Aufgabenfeld A",
          "Politik": "Aufgabenfeld B", "Mathematik": "Aufgabenfeld C"}


def buch(isbn: str, titel: str, fach: str, *, leihbar: bool = True) -> Buchvorkommen:
    return Buchvorkommen(isbn=isbn, titel=titel, faecher=(fach,), leihbar=leihbar)


def jahr(kennung: str, *listen: Jahrgangsliste) -> Schuljahr:
    return Schuljahr(kennung=kennung, name=kennung, listen=listen)


def liste(jahrgang: int, *buecher: Buchvorkommen, paket: bool = True) -> Jahrgangsliste:
    return Jahrgangsliste(jahrgang=jahrgang, paket=paket, buecher=buecher)


def marke(uebersicht, jahrgang: int, fach: str) -> str:
    zeile = uebersicht.zeile(jahrgang)
    assert zeile is not None, f"keine Zeile für Jahrgang {jahrgang}"
    zelle = zeile.zelle(fach)
    assert zelle is not None, f"keine Spalte {fach}"
    return zelle.marke


def rechne(alt: Schuljahr, neu: Schuljahr, **kwargs):
    return vergleiche(alt, neu, aufgabenfelder=FELDER, heute=date(2026, 9, 19), **kwargs)


def test_mehrjahresband_bleibt_beim_schueler() -> None:
    """Steht das Buch im neuen Jahr in Jg. N+1, bleibt die Zelle leer."""
    alt = jahr("2025/2026", liste(5, buch("1", "Deutschbuch 5/6", "Deutsch")))
    neu = jahr("2026/2027",
               liste(6, buch("1", "Deutschbuch 5/6", "Deutsch")),
               liste(7, buch("9", "Irgendwas", "Deutsch")))
    assert marke(rechne(alt, neu), 5, "Deutsch") == ""


def test_auslaufendes_buch_ist_abzugeben() -> None:
    """Das Buch gibt es im neuen Jahr noch - aber nicht in Jg. N+1."""
    alt = jahr("2025/2026", liste(5, buch("1", "Deutschbuch 5", "Deutsch")))
    neu = jahr("2026/2027",
               liste(5, buch("1", "Deutschbuch 5", "Deutsch")),
               liste(6, buch("2", "Deutschbuch 6", "Deutsch")))
    assert marke(rechne(alt, neu), 5, "Deutsch") == "X"


def test_ausgemustertes_buch_darf_bleiben() -> None:
    """Kommt die Reihe in keiner Liste mehr vor, lohnt das Einsammeln nicht."""
    alt = jahr("2025/2026", liste(5, buch("1", "Alte Reihe", "Deutsch")))
    neu = jahr("2026/2027", liste(6, buch("2", "Neue Reihe", "Deutsch")))
    assert marke(rechne(alt, neu), 5, "Deutsch") == "B"


def test_fach_ohne_leihbares_buch_bekommt_striche() -> None:
    """Jg. 5 hat noch kein Politikbuch - die Spalte gibt es trotzdem (Jg. 6 hat eins)."""
    alt = jahr("2025/2026",
               liste(5, buch("1", "Deutschbuch 5", "Deutsch")),
               liste(6, buch("3", "Politik 6", "Politik")))
    neu = jahr("2026/2027", liste(6, buch("1", "Deutschbuch 5", "Deutsch")))
    assert marke(rechne(alt, neu), 5, "Politik") == "---"


def test_kaufbuch_zaehlt_nicht_mit() -> None:
    """Ein nicht leihbares Buch gehört dem Schüler - es taucht nirgends auf."""
    alt = jahr("2025/2026", liste(5, buch("1", "Arbeitsheft", "Deutsch", leihbar=False),
                                  buch("2", "Lambacher 5", "Mathematik")))
    neu = jahr("2026/2027", liste(6, buch("2", "Lambacher 5", "Mathematik")))
    uebersicht = rechne(alt, neu)
    # Die Spalte bleibt - das Fach wird ja unterrichtet -, aber ohne Marke.
    assert marke(uebersicht, 5, "Deutsch") == "---"
    assert uebersicht.sonderfaelle == ()


def test_gemischtes_fach_bekommt_eigenen_buchstaben_mit_titeln() -> None:
    """Zwei Bücher, zwei Ausgänge: ein Buchstabe, und die Legende nennt die Titel."""
    alt = jahr("2025/2026", liste(5, buch("1", "Deutschbuch 5", "Deutsch"),
                                  buch("2", "Duden", "Deutsch")))
    neu = jahr("2026/2027",
               liste(5, buch("1", "Deutschbuch 5", "Deutsch")),
               liste(6, buch("2", "Duden", "Deutsch")))
    uebersicht = rechne(alt, neu)
    assert marke(uebersicht, 5, "Deutsch") == "A"
    (fall,) = uebersicht.sonderfaelle
    assert fall.buchstabe == "A"
    assert "Deutschbuch 5" in fall.text and "Duden" in fall.text
    assert fall.legende.startswith("A = nur „Deutschbuch 5“ muss abgegeben werden")
    # Der Buchstabe steht mit in der Legende der Übersicht.
    assert fall.legende in uebersicht.legende


def test_gleicher_mischfall_bekommt_nur_einen_buchstaben() -> None:
    """Zwei Zellen, derselbe Fall - eine Legendenzeile, nicht zwei."""
    buecher = (buch("1", "Deutschbuch", "Deutsch"), buch("2", "Duden", "Deutsch"))
    alt = jahr("2025/2026", liste(5, *buecher), liste(6, *buecher))
    # In beiden Zeilen derselbe Fall: „Deutschbuch" wandert mit, „Duden" ist
    # ausgemustert.
    neu = jahr("2026/2027",
               liste(6, buch("1", "Deutschbuch", "Deutsch")),
               liste(7, buch("1", "Deutschbuch", "Deutsch")))
    uebersicht = rechne(alt, neu)
    assert marke(uebersicht, 5, "Deutsch") == marke(uebersicht, 6, "Deutsch") == "A"
    assert len(uebersicht.sonderfaelle) == 1


def test_zweiter_mischfall_bekommt_den_naechsten_buchstaben() -> None:
    """Vergeben wird A, C, D, … - B und X sind schon belegt."""
    alt = jahr("2025/2026",
               liste(5, buch("1", "D5", "Deutsch"), buch("2", "Duden", "Deutsch")),
               liste(6, buch("3", "E6", "Englisch"), buch("4", "Grammar", "Englisch")))
    neu = jahr("2026/2027",
               liste(5, buch("1", "D5", "Deutsch"), buch("3", "E6", "Englisch")),
               liste(6, buch("2", "Duden", "Deutsch")),
               liste(7, buch("4", "Grammar", "Englisch")))
    uebersicht = rechne(alt, neu)
    assert [fall.buchstabe for fall in uebersicht.sonderfaelle] == ["A", "C"]
    assert marke(uebersicht, 5, "Deutsch") == "A"
    assert marke(uebersicht, 6, "Englisch") == "C"


def test_individuelle_ausleihe_bekommt_einen_hinweis_statt_marken() -> None:
    alt = jahr("2025/2026", liste(11, buch("1", "Mathe 11", "Mathematik"),
                                  buch("2", "Politik alt", "Politik"), paket=False))
    neu = jahr("2026/2027", liste(12, buch("1", "Mathe 11", "Mathematik")))
    zeile = rechne(alt, neu).zeile(11)
    assert zeile is not None
    assert zeile.zellen == ()
    assert "keine erneute Anmeldung" in zeile.hinweis
    # Die ausgemusterte Reihe wird namentlich ausgenommen.
    assert "Politik alt" in zeile.hinweis


def test_letzter_jahrgang_gibt_alles_ab_auch_bei_individueller_ausleihe() -> None:
    """Für Jg. N+1 gibt es keine Liste mehr - dann hilft auch keine Anmeldung."""
    alt = jahr("2025/2026", liste(13, buch("1", "Mathe 13", "Mathematik"),
                                  buch("2", "Alte Reihe", "Deutsch"), paket=False))
    neu = jahr("2026/2027", liste(12, buch("1", "Mathe 13", "Mathematik")))
    uebersicht = rechne(alt, neu)
    zeile = uebersicht.zeile(13)
    assert zeile is not None and zeile.hinweis == ""
    assert marke(uebersicht, 13, "Mathematik") == "X"
    # Ausgemustert bleibt ausgemustert, auch im letzten Jahrgang.
    assert marke(uebersicht, 13, "Deutsch") == "B"


def test_jahrgang_ohne_leihbares_buch_bekommt_keine_zeile() -> None:
    """Wo nichts ausgeliehen wurde, ist auch nichts abzugeben."""
    alt = jahr("2025/2026",
               liste(5, buch("1", "Deutschbuch 5", "Deutsch")),
               liste(6, buch("9", "Arbeitsheft", "Deutsch", leihbar=False)),
               liste(7))
    neu = jahr("2026/2027", liste(6, buch("1", "Deutschbuch 5", "Deutsch")))
    assert [zeile.jahrgang for zeile in rechne(alt, neu).zeilen] == [5]


def test_fach_ohne_aufgabenfeld_steht_in_der_letzten_spalte() -> None:
    alt = jahr("2025/2026", liste(5, buch("1", "Darstellendes Spiel", "Theater"),
                                  buch("2", "Deutschbuch", "Deutsch")))
    neu = jahr("2026/2027", liste(6))
    spalten = rechne(alt, neu).spalten
    assert spalten[-1].fach == "Theater"
    assert spalten[-1].aufgabenfeld == "(ohne Aufgabenfeld)"


def test_bestehende_spalten_behalten_ihre_reihenfolge() -> None:
    """Wer die Datei kennt, soll seine Fächer wiederfinden."""
    from mehrjahresbaende.core import Spalte

    bestehend = (Spalte("Englisch", "Aufgabenfeld A"), Spalte("Deutsch", "Aufgabenfeld A"))
    alt = jahr("2025/2026", liste(5, buch("1", "D", "Deutsch"), buch("2", "E", "Englisch")))
    neu = jahr("2026/2027", liste(6))
    spalten = rechne(alt, neu, bestehende_spalten=bestehend).spalten
    assert [spalte.fach for spalte in spalten] == ["Englisch", "Deutsch"]


def test_fach_alias_bildet_iserv_namen_auf_die_spalte_ab() -> None:
    alt = jahr("2025/2026", liste(5, buch("1", "Religionsbuch", "Evangelische Religion")))
    neu = jahr("2026/2027", liste(6))
    uebersicht = rechne(alt, neu, aliase={"Evangelische Religion": "Religion (ev./kath.)"})
    assert [spalte.fach for spalte in uebersicht.spalten] == ["Religion (ev./kath.)"]
    assert marke(uebersicht, 5, "Religion (ev./kath.)") == "B"


def test_herkunft_nennt_beide_schuljahre() -> None:
    alt = jahr("2025/2026", liste(5, buch("1", "D", "Deutsch")))
    neu = jahr("2026/2027", liste(6, buch("1", "D", "Deutsch")))
    assert rechne(alt, neu).herkunft == (
        "Erzeugt am 19.09.2026 aus den Bücherlisten 2025/2026 → 2026/2027"
    )


def test_vorjahr_wird_aus_der_kennung_abgeleitet() -> None:
    assert vorjahr_kennung("2026/2027") == "2025/2026"
    with pytest.raises(UnbekanntesSchuljahr):
        vorjahr_kennung("Schuljahr 26")
