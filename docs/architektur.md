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

## Der Schreibpfad: drei Schutzschichten

`POST /api/cell` ändert genau eine Zahl. Drei Schichten stehen davor, und alle
drei sind nötig:

**Kein freier Zellbezug.** Die Route nimmt den Zeilenschlüssel entgegen
(`0:Deutsch:C3`), nie eine Referenz wie `"K3"`. Der Schlüssel wird gegen das
*frisch geparste* Raster aufgelöst. Ein Bearbeiter, der eine Zeile einfügt,
verschiebt damit keine Zahl in die falsche Zelle — und ein manipulierter Aufruf
kann keine beliebige Zelle der Mappe beschreiben. Schreibbar sind nur `bestand`
und `bestellt`; `angemeldet` kommt aus IServ und `zu bestellen` ist eine Formel.

**Optimistisches Sperren.** Der Browser schickt die `mtime` mit, die er beim
Laden gesehen hat. Weicht sie ab, hat jemand anderes gespeichert (oder der
Abruf lief) → HTTP 409, die Seite lädt neu. Ohne diese Prüfung würde ein Klick
in einem seit einer Stunde offenen Tab stillschweigend einen frischen Abruf
überschreiben.

**Atomar speichern.** `atomic_save_workbook` schreibt in eine Nachbardatei,
`fsync`t und ersetzt dann per `os.replace`. Ein Abbruch mittendrin — WLAN weg,
Akku leer — lässt die alte Mappe unberührt. Jeder Speichervorgang legt zusätzlich
ein Backup in `backups/` an; der Ordner wird auf `backups_behalten` (Standard 30)
gekürzt, sonst füllt er auf dem Netzlaufwerk unbemerkt zu.

### "Die Datei ist in Excel geöffnet"

Der häufigste Fehler im Alltag. `PermissionError` beim Ersetzen heißt unter
Windows praktisch immer: die Mappe ist offen. Das wird zu HTTP **423** mit
Klartext. Liegt eine `~$<name>.xlsx` daneben, steht der Benutzername darin und
wird mitgenannt.

Das Format dieser Datei ist unangenehm: Byte 0 ist die Länge des Namens,
danach folgt er — je nach Excel-Version als UTF-16LE ab Byte 2 oder als 8-Bit-Text
ab Byte 1. Beides blind zu probieren reicht nicht: `j.klein` als UTF-16 gelesen
ergibt druckbaren CJK-Unsinn, der als Name durchginge. Byte 1 entscheidet — in
der UTF-16-Fassung ist es das Nullbyte des ersten Zeichens.

Eine vorhandene `~$…`-Datei allein blockiert das Schreiben **nicht**: sie kann
verwaist sein (Excel abgestürzt). Erst der echte `PermissionError` ist einer.
Die Startseite weist trotzdem darauf hin.

## Der Abruf: ein Lauf, Zugangsdaten nur für ihn

`POST /api/refresh` prüft die Zugangsdaten **synchron** (`AusleiheClient(...)`,
`login()`) und antwortet erst dann mit `202`. Nur an dieser Stelle lässt sich
"Passwort falsch" noch als 401 beantworten; wäre die Anmeldung Teil des
Hintergrundlaufs, stünde der Fehler in einem Statusobjekt, das niemand liest.

| Fehler | Status | Klartext |
|--------|--------|----------|
| `AuthError` | 401 | Zugangsdaten stimmen nicht |
| `ForbiddenError` | 403 | Konto hat keine Ausleihe-Verwalter-Rolle |
| `TransportError` | 504 | IServ hat nicht geantwortet |
| Diagnosen aus `apply_snapshot` | 422 | Zuordnung mehrdeutig, **nichts gespeichert** |
| Mappe in Excel offen | 423 | siehe oben |

Die letzten beiden treten erst im Lauf auf und stehen deshalb als `fehlercode`
im Statusobjekt, nicht als HTTP-Status. `GET /api/refresh/status` antwortet immer
mit 200 — es ist eine Abfrage, kein zweiter Versuch.

**Zugangsdaten** kommen ausschließlich im POST-Körper an, gehen direkt in den
Client und werden danach fallen gelassen. Sie landen nie in `app.state`, nie in
einem Log, nie in einer Antwort, nie im Cache und nie in der Mappe. `test_refresh.py`
prüft genau das.

**Ganz oder gar nicht.** Meldet `apply_snapshot` Diagnosen, ist die Zuordnung
Fach → Buch mehrdeutig; dann wird *nichts* gespeichert. Eine halb aktualisierte
Bestandsliste wäre schlimmer als eine veraltete, weil ihr niemand ansieht, welche
Zahl von wann ist.

**Ein Modul-Lock** erlaubt genau einen Lauf. Ein zweiter Versuch bekommt 409 mit
dem Stand des laufenden.

### Fortschritt

Die Jahrgangs-Bücherlisten werden bewusst nicht über `fetch_snapshot(eager=True)`
geladen, sondern in `refresh._lade_jahrgaenge` selbst durchlaufen. Erst danach
steht ihre Anzahl fest — und nur mit ihr lässt sich der längste Abschnitt des
Abrufs als bewegter Balken zeigen statt als stehender. Ein Jahrgang, der im Raster
steht, aber in IServ keine Bücherliste hat, ist kein Fehler: seine Zellen bleiben
leer, und der Bericht sagt warum.

### Der Sidecar-Cache

Titel, ISBN und Preis stehen nicht in der Mappe, sondern kommen aus IServ. Der
Abruf legt sie als `<Mappe>.dashboard-cache.json` daneben. Die ISBN wird dabei
mit `bestand.core.format_isbn` formatiert (`978-3-06-205222-4`): im Live-Test
stand in der Mappe die Strichfassung und im Cache die nackte Ziffernfolge — zwei
Schreibweisen derselben Zahl in derselben Tabellenzeile.

Der Cache ist **reine Anzeige**. Keine Zahl der Tabelle wird je aus ihm gelesen.

## Warum das venv nach %LOCALAPPDATA%

`START.bat` spiegelt die drei Quellbäume vom Netzlaufwerk nach
`%LOCALAPPDATA%\sba-dashboard\app\` und legt das venv daneben. Ein venv auf
einem SMB-Laufwerk ist quälend langsam und übersteht keinen Verbindungsabbruch.
Kopiert wird nur der Programmcode — die Excel-Datei bleibt, wo sie ist, sonst
gäbe es zwei Wahrheiten.

Die beiden Geschwister-Repos kommen über den `PYTHONPATH`, nicht über
`pip install -e`. Ein Editable-Install bräuchte auf dem Laptop ein Build-Backend
aus dem Netz und scheitert genau dort, wo niemand mehr weiterhelfen kann. Beide
sind reines Python ohne Kompilat, ein Pfadeintrag genügt.
