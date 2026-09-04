# Architektur und Struktur-Befunde

## Warum das Raster nicht naiv gelesen werden darf

Vier am echten Workbook gemessene Eigenheiten bestimmen den gesamten Entwurf.
Wer eine davon übersieht, schreibt Zahlen in die falsche Zelle.

### 1. Es gibt keine Bezahlt-Spalte

Die Zustandszeile kennt genau vier Beschriftungen, je Fach viermal 15 Blöcke:
`Angemeldet | Bestand | Bestellt | zu bestellen`. Eine `Bezahlt`-Spalte, wie sie
ältere Fassungen des Skripts erwarten, existiert nicht mehr. Der Kern kann sie
weiterhin füllen (`WRITABLE_ZUSTAENDE`), stößt im aktuellen Workbook aber nie
darauf.

### 2. "zu bestellen" sind echte Formeln

`E3` enthält `=B3-C3-D3`, `M3` enthält `=J3+J4-K3-L3`. Die Mappe wird deshalb
**immer** mit `data_only=False` geladen. Mit `data_only=True` gelesen und wieder
gespeichert wären die Formeln unwiderruflich durch ihren letzten berechneten
Wert ersetzt — und ohne laufendes Excel gäbe es diesen Wert oft gar nicht.

Folge: Der Bedarf wird in Python gerechnet
(`angemeldet - bestand - bestellt`, `app/rows.py`), nie aus der Spalte gelesen.

### 3. Die Merge-Topologie der Bestand-Spalte definiert die Zeilengruppe

Ein Buch, das mehrere Jahrgänge bedient, hat **eine** Bestand-Zelle über mehrere
Jahrgangszeilen:

| Merge | Jahrgänge |
|-------|-----------|
| `K3:K4` | 5–6 |
| `BC4:BC7` | 6–9 |
| `AU9:AU12` | 11–12 |

Die **Angemeldet**-Spalte bleibt dabei je Jahrgang einzeln (`J3=94`, `J4=73`) und
wird summiert — genau das tut auch die Excel-Formel `=J3+J4-K3-L3`.

Der Gruppenschlüssel einer Listenzeile ist deshalb der Anker der Bestand-Zelle:
`GridEntry.key = f"{block}:{fach_label}:{bestand_ref}"`.

### 4. Merges über die volle Blockbreite sind Sperrflächen

`R3:U5`, `AD3:AG6`, `AX6:BA9`, `B12:E13` und elf weitere überdecken einen
kompletten Fachblock in mehreren Jahrgangszeilen. Sie bedeuten **"in diesen
Jahrgängen nicht angeboten"** und sind leer.

Bis zum Refactor wurden sie nur zufällig verschont: `match_book` fand für das Fach
kein Buch und brach die Spalte ab. Jetzt ist es eine ausdrückliche Regel
(`grid.py`, `_blocked_refs`) mit Test. Sichtbarer Unterschied: die zwölf
irreführenden Meldungen `Kein Buch-Match für Fach 'Latein'` je Sperrfläche
verschwinden aus der Konsolenausgabe. Eine Lücke, in der das Fach angeboten
wird, aber kein Buch in der Bücherliste steht, meldet das Skript weiterhin.

Ein Fachblock wird nicht über die Merges der Fach-Zeile erkannt (die kann ein
Bearbeiter jederzeit auflösen), sondern über die Zustandszeile: jede Spalte
`Angemeldet` eröffnet einen Block.

## Aufteilung auf die Repos

```
ausleihe-api/      IServ-Client, hält die .env
sba-bestand/       bestand/core/  ← die gesamte Logik, netzfrei testbar
                   bestand/update_bestand_auto.py  ← nur noch CLI-Schale
sba-dashboard/     app/  ← FastAPI, Vorlagen, Zeilenmodell
```

`bestand/core/` liest kein `os.environ`, lädt keine `.env`, parst keine Argumente
und schreibt nichts nach stdout. Der IServ-Client wird **injiziert**. Deshalb
laufen die Tests beider Repos ohne Netz und ohne die echte Mappe: beide bauen
sich ihr Prüfblatt mit `bestand.core.testing.build_workbook`, das die vier
Befunde oben im Kleinen nachbildet.

## Warum 127.0.0.1

Die Mappe enthält Anmeldezahlen je Jahrgang. Ein Server, der im Schulnetz
lauscht, macht daraus eine offene Seite ohne Anmeldung. Das Dashboard hört
ausschließlich auf die Loopback-Adresse; wer es benutzt, sitzt am Rechner.

## Warum die Mappe nie im Speicher bleibt

Sie liegt auf einem Netzlaufwerk und kann jederzeit in Excel geöffnet oder von
jemand anderem gespeichert werden. Jede Anfrage lädt sie neu und merkt sich nur
die Änderungszeit. Ein gehaltenes Workbook würde still veralten und beim
Speichern fremde Änderungen überschreiben.
