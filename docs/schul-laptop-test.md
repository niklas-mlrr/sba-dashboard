# Testlauf auf dem Schul-Laptop — Prüfliste

Diese Liste ist für **Niklas**, nicht für die Lehrkraft. Sie ist der einzige
offene Punkt, für den echte Hardware nötig ist; alles andere ist offline und in
der CI geprüft.

Zuletzt geprüft: *auf Hardware noch nicht.* Was am 2026-09-04 **offline
vorweggenommen** wurde, steht unten unter „Trockenlauf". Es ersetzt den
Durchgang nicht, nimmt ihm aber die Zeilen ab, die kein Windows brauchen.

## Vorher wissen

Was am 2026-09-02 auf einem Schulgerät (Windows 10 19045, Domäne `SCHULE`)
schon gemessen wurde und **nicht** erneut gebraucht wird:

- Bind auf `127.0.0.1` läuft ohne Firewall-Abfrage; `0.0.0.0` löst sie aus.
- `python -m venv` und `pip install` von pypi.org funktionieren ohne
  Admin-Rechte, aus dem Schulnetz erreichbar.
- Python 3.13.5 liegt im Benutzerprofil.
- Python greift zuverlässig auf die Excel im Gruppenordner zu.

Was **neu** ist und deshalb der eigentliche Anlass dieses Durchgangs:

1. Die beiden Geschwister-Bibliotheken werden ins venv **installiert** statt
   über den `PYTHONPATH` untergeschoben (`docs/verteilung.md`).
2. Die Benutzerkonfiguration liegt getrennt vom ausgelieferten Standard, und
   eine alte Vollkopie wird migriert (`docs/architektur.md`).
3. Der Sidecar-Cache weicht bei einem schreibgeschützten Gruppenordner auf einen
   lokalen Ordner aus und meldet das als Warnung statt als Fehlschlag.

## Werkzeug

`tools/diagnose.py` misst die halbe Liste selbst. Es schreibt nie in die Mappe
und braucht keine IServ-Zugangsdaten:

```bat
cd /d "%LOCALAPPDATA%\sba-dashboard\app\sba-dashboard"
"%LOCALAPPDATA%\sba-dashboard\venv\Scripts\python.exe" tools\diagnose.py --datei "%USERPROFILE%\Desktop\sba-diagnose.txt"
```

Rückgabewert 0 heißt „kein harter Fehler". Die Datei auf dem Desktop ist das,
was man mitschickt.

## Trockenlauf am 2026-09-04 (Linux, ohne Schulgerät)

Damit der Durchgang am Gerät nicht an einem Fehler scheitert, den man auch
offline gefunden hätte, wurden die Zeilen, die keine Windows-Eigenheit prüfen,
gegen die mitgelieferte Vorlage (`vorlage/…xlsx`) in einem Wegwerfordner
vorweggenommen — mit `SBA_CONFIG_DIR` und `SBA_CACHE_DIR` auf denselben Ordner,
damit nichts im echten Benutzerprofil landet.

**Was dabei schon zusammenpasste** (am Gerät nur noch bestätigen, nicht
erarbeiten):

- **A3–A6:** Rückgabewert 0, beide Geschwister-Pakete als `installiert`
  gemeldet, `PYTHONPATH` nicht gesetzt, und die Rasterzahlen sind genau die
  erwarteten **72 Zeilen und 16 Sperrflächen**. Die Blätter der Vorlage:
  `Bestand- und Nachbestellung, zu Bestellen, bestellt, erhalten`.
- **C1–C3:** Eine künstlich hergestellte alte Vollkopie (alle sieben Schlüssel,
  erster Excel-Pfad auf die echte Mappe) wurde beim Start auf **genau einen**
  Schlüssel eingekürzt, `excel_pfad_kandidaten`, mit der gewählten Mappe an
  erster Stelle und den beiden ausgelieferten Kandidaten dahinter. Die
  ausgelieferte `config.json` blieb byteweise gleich (per Prüfsumme
  verglichen), und es blieb keine `.tmp`-Datei liegen. Der Hinweis dazu
  erscheint im Bericht als `Warnung`, nicht als Fehler.
  **Ein zweiter Start schrieb die Datei nicht erneut** (Zeitstempel
  unverändert) und meldete den Hinweis nicht mehr — die Migration ist also
  einmalig, nicht bei jedem Start.
- **Cache-Ausweichen:** Mit schreibgeschütztem Mappenordner landete der Cache
  im lokalen Rückfallordner, und `laden` gab ihn danach vollständig zurück
  (Titel, ISBN mit Bindestrichen, Preis). Das ist der Mechanismus hinter F3
  und F6.

**Vergleichswert für die Wartezeiten:** auf dieser (nicht schnellen)
Linux-Kiste, mit der Mappe auf einer lokalen Platte, braucht ein Aufruf von
`/` rund **147 ms** und einer von `/api/rows` rund **136 ms**. Dauert es am
Schul-Laptop spürbar länger, liegt das am Netzlaufwerk und nicht an der
Anwendung — das Laden der Mappe über SMB ist der einzige Teil, der dort
wesentlich teurer wird. (Vor dem 2026-09-04 behobenen Fehler in
`bestand.core.grid` waren es über drei Sekunden je Aufruf; wer die Oberfläche
von früher als zäh in Erinnerung hat, hat das gesehen.)

**Was der Trockenlauf ausdrücklich nicht zeigt** und deshalb am Gerät der
eigentliche Punkt bleibt: der komplette Abschnitt **B** (er prüft `START.bat`
und `robocopy`, die der Trockenlauf gar nicht anfasst), alles mit einer Uhr
daran (A2), der Windows-Sperrpfad (E1–E3), SMB (D5, F3), IServ (F1–F6) und
zwei Fenster gleichzeitig (G1–G3). Der Trockenlauf lief auf Linux;
`msvcrt.locking`, Laufwerksbuchstaben und `~$…`-Dateien kommen dort nicht vor.

**Abschnitt G ist seit dem 2026-09-04 die wichtigste Zeile nach D4.** Dort
wurde ein Fehler behoben, den nur Windows zeigt: `os.replace` scheitert mit
`WinError 5`, solange irgendein Handle auf die Zieldatei offen ist. Ein
zweites Fenster, das die Mappe nur *liest*, brachte damit ein Speichern zum
Scheitern — gemeldet als „Die Datei ist gerade in Excel geöffnet", obwohl
niemand Excel offen hatte. Behoben durch kurzes Wiederholen, geprüft in der
CI auf `windows-latest`. Ob es unter SMB genauso trägt, zeigt erst G2/G3.
Erscheint dort „in Excel geöffnet", ohne dass Excel läuft, ist genau dieser
Fall wieder da und gehört gemeldet.

Nachstellen lässt sich der Migrationsfall auf jeder Plattform so:

```bash
mkdir -p /tmp/c-test/cfg
python3 -c 'import json;r=json.load(open("config.json"));r["excel_pfad_kandidaten"]=["<echte Mappe>",*r["excel_pfad_kandidaten"]];json.dump(r,open("/tmp/c-test/cfg/config.json","w"),indent=2)'
SBA_CONFIG_DIR=/tmp/c-test/cfg python tools/diagnose.py
```

## Prüfliste

Jede Zeile hat ein **messbares** Ergebnis. Keine Ja/Nein-Frage an einen
Menschen — die frühere Fehlmeldung des Testskripts kam genau daher.

### A. Erststart auf einem Gerät, das das Dashboard noch nie gesehen hat

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| A1 | `START.bat` doppelklicken | Fenster öffnet sich, keine Admin-Abfrage, keine Firewall-Abfrage | Uhrzeit Start |
| A2 | Warten, bis der Browser aufgeht | Liste ist sichtbar oder die Einrichtungsseite | **Dauer in Sekunden** |
| A2b | Das **Programmfenster** ansehen | Es ist da, zeigt Server und Ordner, und die Knöpfe „Seite öffnen" und „Beenden" | ob es lesbar ist, Schriftgröße |
| A2c | Zahnrad ⚙ → „Durchsuchen…" | Windows-Ordnerauswahl geht auf; ausgewählter Ordner steht danach im Feld | ob der Netzlaufwerk-Ordner darin auffindbar ist |
| A3 | `tools\diagnose.py` laufen lassen | Rückgabewert 0 | Bericht anhängen |
| A4 | Im Bericht: Zeilen „Paket ausleihe" / „Paket bestand" | beide `ok`, Text „installiert" | Textzeile |
| A5 | Im Bericht: Zeile „PYTHONPATH" | `ok`, „nicht gesetzt" | — |
| A6 | Im Bericht: Zeile „Raster" | `ok`, 72 Zeilen, 16 Sperrflächen | Zahlen |

Bricht A2 mit einer Meldung ab: der Text im schwarzen Fenster ist der Befund,
nicht der Traceback.

### B. Zweiter Start (der wichtige)

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| B1 | Fenster schließen, `START.bat` erneut | Kein „Pakete werden installiert", kein „Bibliotheken werden eingerichtet" | Ausgabe |
| B2 | Dauer bis der Browser aufgeht | **deutlich unter A2**, Zielmarke wenige Sekunden | Dauer |

Erscheint bei B1 doch „Bibliotheken werden eingerichtet", meldet `robocopy` bei
jedem Lauf Änderungen. Dann ist die Ursache zu suchen (Zeitstempel über SMB),
sonst baut jeder Start unnötig.

### C. Migration einer alten Konfiguration

Nur auf einem Gerät sinnvoll, das die **alte** Fassung schon benutzt hat. Sonst
künstlich herstellen: eine vollständige Kopie der ausgelieferten `config.json`
nach `%LOCALAPPDATA%\sba-dashboard\config.json` legen und darin den ersten
Excel-Pfad auf die echte Mappe ändern.

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| C1 | Starten | Die Liste kommt, mit der Mappe aus der Benutzerkonfiguration | — |
| C2 | `%LOCALAPPDATA%\sba-dashboard\config.json` ansehen | Enthält **nur noch** `excel_pfad_kandidaten`, nicht mehr alle Schlüssel | Dateiinhalt |
| C3 | Die ausgelieferte `config.json` im Quellordner ansehen | **unverändert** | — |

### D. Lesen und Schreiben gegen die echte Mappe

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| D1 | Liste öffnen | 72 Zeilen, Mehrjahresbänder zeigen z. B. `5-6` | — |
| D2 | In einer Zeile mit Eingabefeld eine `Bestellt`-Zahl ändern | Feld übernimmt den Wert ohne Fehlermeldung | alter/neuer Wert |
| D3 | Mappe in Excel öffnen und nachsehen | Die Zahl steht im Blatt `bestellt` | — |
| D4 | Spalte „zu bestellen" in Excel | Enthält weiterhin **Formeln**, keine festen Zahlen | eine Zelle notieren |
| D5 | Ordner `backups` neben der Mappe | Eine neue Datei mit Zeitstempel | Dateiname |
| D6 | Wert zurücksetzen | wieder der alte Stand | — |

D4 ist die wichtigste Zeile der ganzen Liste. Wären die Formeln weg, wäre die
Mappe beschädigt und niemand würde es sofort sehen.

### E. „Datei ist in Excel geöffnet"

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| E1 | Mappe in Excel offen lassen, Liste neu laden | Liste kommt trotzdem, mit Hinweis oben | Hinweistext |
| E2 | Bei offener Mappe eine Zahl ändern | Klartextmeldung „ist gerade in Excel geöffnet", **mit Benutzernamen** wenn lesbar | genauer Text |
| E3 | Excel schließen, dieselbe Änderung erneut | geht durch | — |

Steht in E2 kein Name, obwohl eine `~$…`-Datei daneben liegt: die Datei mit
einem Hex-Editor ansehen und die ersten Bytes notieren — das Format
unterscheidet sich je Excel-Version.

### F. Abruf aus IServ

Mit dem **eigenen** Konto, nicht mit einem Verwalterzugang von jemand anderem.

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| F0 | Ohne Anmeldung „Abrufen" klicken | Klartext „Bitte im Programmfenster anmelden", HTTP 401, kein Absturz | Wortlaut |
| F1a | Im Programmfenster anmelden | Statuszeile: „Angemeldet als …, verfällt in 30 Minuten"; das Passwortfeld ist sofort leer | **Dauer der Anmeldung** |
| F1 | „Aktuelle Daten aus IServ abrufen", dann „Abrufen" | Der Fortschrittsbalken bewegt sich | **Gesamtdauer** |
| F2 | Zusammenfassung am Ende | Zahl geänderter Zellen, Nachbestellungen | Zahlen |
| F2b | Direkt nach dem Neuladen | Die geänderten Zahlen sind ~10 s gelb hinterlegt, danach nicht mehr | ob es auffällt |
| F2c | Während des Abrufs ein zweites Fenster auf `127.0.0.1:8765` öffnen | Auch dort läuft der Fortschrittsbalken, und auch dort lädt die Seite am Ende neu | — |
| F3 | Warnungen in der Zusammenfassung | Erwartet wird **keine** Cache-Warnung. Steht dort „Titel und ISBN konnten diesmal nicht zwischengespeichert werden", ist **beides** fehlgeschlagen, Gruppenordner *und* lokaler Rückfallort | Wortlaut |
| F4 | Falsches Passwort im Fenster eingeben | „Zugangsdaten stimmen nicht", **kein** Absturz, die bestehende Anmeldung bleibt bestehen | — |
| F4b | „Abmelden" im Fenster, dann „Abrufen" | Wieder der 401 aus F0 | — |
| F4c | Zeitschloss: `START.bat` mit gesetztem `SBA_ANMELDUNG_ABLAUF=60` starten (in der Eingabeaufforderung: `set SBA_ANMELDUNG_ABLAUF=60` und dann `START.bat`), anmelden, eine Minute warten | Die Statuszeile schlägt auf „Nicht angemeldet" um, ein Abruf verlangt eine neue Anmeldung | ob es nachvollziehbar ist |
| F5 | Nach dem Abruf: Titel und ISBN in der Liste | gefüllt, ISBN mit Bindestrichen | ein Beispiel |
| F6 | Cache-Zeilen im Diagnosebericht | sagt, ob geteilt oder lokal geschrieben wurde | Zeilen |

F3 und F6 gehören zusammen, und die Reihenfolge ist wichtig: das Ausweichen auf
den lokalen Ordner ist **kein** Fehler und erzeugt **keine** Warnung — es steht
nur in den beiden Cache-Zeilen des Diagnoseberichts (F6). Ist „Cache (geteilt)"
übersprungen und „Cache (lokal)" `ok`, dann ist genau das passiert, und alles
funktioniert wie vorgesehen.

Ein schreibgeschützter Gruppenordner ist dabei nicht die Erklärung, die man
zuerst vermutet: er würde schon das **Speichern der Mappe** verhindern
(`atomic_save_workbook` legt seine Zwischendatei im Ordner der Mappe an), der
Abruf käme also gar nicht bis zum Cache. Kommt die Warnung aus F3 trotz
gespeicherter Zahlen, ist der Sidecar selbst nicht ersetzbar (vorhandene Datei
schreibgeschützt oder von einem anderen Programm gehalten) *und* zusätzlich der
lokale Ordner unbeschreibbar. Der genaue Wortlaut aus dem Bericht ist dann der
Befund, nicht die Vermutung.

### G. Zwei Fenster gleichzeitig

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| G1 | `START.bat` zweimal starten | Zweites Fenster nimmt den nächsten freien Port | beide Ports |
| G2 | In Fenster 1 eine Zahl ändern, dann in Fenster 2 dieselbe Zeile | Fenster 2 meldet, die Datei habe sich geändert, und lädt neu | Meldung |
| G3 | In beiden Fenstern gleichzeitig abrufen | Einer läuft, der andere wartet oder wird abgewiesen — **nie beide gleichzeitig schreiben** | Verhalten |

### G2. Bücherlisten

| # | Schritt | Erwartet |
|---|---------|----------|
| G2-1 | Ohne Anmeldung „Bücherliste" → „Fach" | Hinweis, im Programmfenster anzumelden; kein JSON |
| G2-2 | Angemeldet „Fach", „Verlag", „Jahrgang" öffnen | Tabellen wie bei IServ, Status als graues Label „offen"; wie lange dauert das Laden? |
| G2-3 | Ein Fach anklicken (z. B. Chemie) | Bücher mit Jahrgang, Mehrjahresbände nur einmal; „« Zurück zur Übersicht" funktioniert |
| G2-4 | „Jahrgang 5" anklicken | Grundpaket und Wahlbereiche wie bei IServ, ohne Bearbeitungsknöpfe |
| G2-5 | Dort Spaltenüberschriften anklicken, z. B. erst „Fach", dann „Verlag" | Sortiert auf/ab; gleicher Verlag bleibt nach Fach geordnet |
| G2-6 | „Paketansicht" abwählen, wieder anwählen | Alle Bücher in einer Tabelle, bisherige Sortierung übernommen; bei Jahrgang 12/13 (Individuell) gibt es den Knopf nicht |
| G2-7 | Nach dem ersten Start: installiert sich alles? (reportlab und **Pillow** sind seit dem Druck neu) | kein pip-Fehler zu Pillow |
| G2-8 | „Fach" → Druck-Knopf → „PDF öffnen" | PDF öffnet in neuem Tab, **kein** Download; wie lange dauert es? |
| G2-9 | Druckmenü: „Bestätigungsaufforderung" an, Rückgabe bis/an ausfüllen, „Individuell" mit 2 Fächern, doppelseitig | Nur die 2 Fächer, Rückgabe im Kopf, Seitenzahl je Fach gerade |
| G2-10 | Auf der Seite eines Fachs drucken | PDF nur dieses Fachs |
| G2-11 | „Verlag" → Druck-Knopf → „PDF öffnen" | PDF je Verlag, Spalten Titel, Fach, Klasse, ISBN, Neupreis, Leihgebühr; keine Verlags-Spalte auf der Seite selbst |
| G2-12 | „Jahrgang" → Druck-Knopf, „Schülerliste" **aus** | Eigene Liste je Jahrgang, Spalten wie die IServ-Liste, alle Bücher in einer Tabelle |
| G2-13 | Dasselbe mit „Schülerliste" **an** | Die IServ-Druckversionen, aneinandergehängt; mit „doppelseitig" endet jeder Jahrgang auf gerader Seitenzahl |

### G4. Mehrjahresbände

Der Reiter schreibt in eine **zweite** Datei im Ordner der Bestandsmappe. Vor
G4-3 eine Kopie der bisherigen `Mehrjahresbände Schulbuchausleihe.xlsx`
beiseitelegen — „Erzeugen" überschreibt sie vollständig.

| # | Schritt | Erwartet |
|---|---------|----------|
| G4-1 | Reiter „Mehrjahresbände" ohne Anmeldung öffnen | Die vorhandene Übersicht wird angezeigt, Spalten und Jahrgänge wie in der Datei |
| G4-2 | Legende unter der Tabelle lesen | Dieselben vier Zeilen wie in der Datei |
| G4-3 | Angemeldet „Aus IServ erzeugen", Rückfrage bestätigen | Dauer? Danach Tabelle neu, unten „Erzeugt am … aus 2025/2026 → 2026/2027" |
| G4-4 | Die erzeugte Datei in Excel öffnen | Sieht aus wie die alte: Aufgabenfelder oben, Fachnamen gedreht, Legende unten |
| G4-5 | Erzeugte Marken mit der beiseitegelegten Kopie vergleichen | Jede Abweichung erklären: entweder eine echte Änderung in IServ oder ein Fehler in der Regel |
| G4-6 | Steht ein Fach doppelt oder mit unbekanntem Namen in den Spalten? | Dann einen Eintrag in `mehrjahresbaende_fach_aliase` (siehe `docs/roadmap.md`) |
| G4-7 | Eine Zelle über das Auswahlfeld ändern | Feld kurz hervorgehoben; in Excel steht der neue Wert, `backups/` hat eine Sicherung |
| G4-8 | Dieselbe Datei in Excel offen lassen und erneut ändern | Meldung „Datei ist in Excel geöffnet" (423), nichts geht verloren |

### G5. Buchplanung (Freigaben, Einführung/Ausmusterung)

Schreibt in eine **dritte** Datei im Ordner der Bestandsmappe, je Schuljahr eine
eigene (`Bücherlisten und Planung 2026-2027.xlsx`). Sie entsteht neu; es gibt
nichts zu sichern.

| # | Schritt | Erwartet |
|---|---------|----------|
| G5-1 | Angemeldet „Bücherlisten → Fach" öffnen | Hinweis „Für das Schuljahr … ist noch nichts gespeichert", Knopf „Aus IServ aktualisieren" |
| G5-2 | „Aus IServ aktualisieren" | Dauer? Danach liegt die Datei im Ordner der Bestandsmappe |
| G5-3 | Die Datei in Excel öffnen | Vier Blätter („Buchreihen", „Fächer & Jahrgang", „Rücklage", „Info"); die eintragbaren Spalten hell hinterlegt; im Blatt „Info" Schuljahr, Vorjahr, Stand |
| G5-4 | Blatt „Buchreihen" durchsehen | Jeder Titel genau einmal; enthält auch **leihbare** Bücher, die es nur im Vorjahr gab — das sind die ausgemusterten. Kaufbücher des Vorjahres fehlen |
| G5-7 | Fach-Ansicht: Kürzel + Datum, „Liste bestätigen" | Status „bestätigt"; auf „Fächer & Jahrgang" tragen alle Zeilen dieses Fachs Kürzel und Datum |
| G5-8 | Ein Buch in IServ zur Fachliste hinzufügen, aktualisieren | Status „teilweise", darunter „Noch ohne Kürzel: …" |
| G5-9 | „Planung…" bei einem Leihbuch: Ausmusterung eintragen | Status der Zeile wechselt; in Excel steht das Schuljahr in „Ausmusterung nach Schuljahr" |
| G5-9b | „Planung…" bei einem **Kaufbuch** | Das Feld „Ausmusterung nach Schuljahr" ist gesperrt |
| G5-10 | „Planung…": weiterer Jahrgang mit „Einführung" | Neue Zeile auf „Fächer & Jahrgang" mit diesem Fach, Status „geplant" |
| G5-11 | Rücklage mit Anzahl und Bemerkung speichern | Steht im Blatt „Rücklage" beim richtigen Fach |
| G5-11a | Menü eines Buchs: Block „Buchreihe" steht vor „Einführung und Ausmusterung", Titel und Neupreis ändern, speichern | Neuer Titel/Preis in Fach-, Verlags- und Jahrgangsansicht und im PDF; im Menü darunter „in IServ: …"; auf „Buchreihen" die Zelle hell mit Kommentar „in IServ: …"; nach „Aus IServ aktualisieren" bleibt die Korrektur. In IServ unverändert |
| G5-11b | Im Feld „Verlag" einen Buchstaben tippen | Darunter alle Verlage, die damit anfangen; Klick oder ↑/↓ + Enter übernimmt; Esc schließt nur die Liste; ein neuer Verlag lässt sich frei eintippen |
| G5-11c | Ins Feld „ISBN" klicken und tippen | Grau hinterlegt, nicht änderbar; markieren und kopieren geht |
| G5-12 | Datei in Excel offen lassen und etwas eintragen | Meldung „Datei ist in Excel geöffnet" (423), nichts geht verloren |
| G5-13 | Druckmenü der Fach-Übersicht: „nicht bestätigte" | Hakt genau die Fächer ohne Freigabe an und springt auf „Individuell"; die PDF-URL nennt sie |

### H. Beenden

Der Anlass für das Programmfenster steht in H2: der Weg zurück, wenn der Tab weg
ist. Bis dahin gab es keinen.

| # | Schritt | Erwartet |
|---|---------|----------|
| H1 | Kopf der Seite ansehen | Reiterleiste im IServ-Stil mit „Bestand", rechts „?" (noch ohne Funktion) und Zahnrad; **kein** Beenden-Knopf. Das Zahnrad öffnet den Einstellungsdialog mit dem Schuljahr |
| H2 | Neu starten, **Browser-Tab schließen**, dann „Seite öffnen" im Programmfenster | Der Tab ist wieder da, mit derselben Liste |
| H3 | Knopf „Beenden" im Programmfenster | Rückfrage, danach endet alles; `http://127.0.0.1:8765/` ist nicht mehr erreichbar |
| H4 | Neu starten und das Programmfenster über das **X** schließen | Dieselbe Rückfrage, dasselbe Ergebnis |
| H5 | Danach `START.bat` erneut | startet normal; Server und Ordner stehen noch, Anmeldung ist weg |

### I. Laufwerksverschlüsselung

Kein Test des Programms, sondern eine Frage an das Gerät — und die einzige, die
das Programm selbst nicht beantworten kann.

Die IServ-Anmeldung hält das Passwort für die Laufzeit im Arbeitsspeicher
(Begründung in [`architektur.md`](architektur.md#warum-das-passwort-jetzt-im-speicher-liegt)).
Windows kann eine Speicherseite jederzeit in die Auslagerungsdatei schreiben;
ohne BitLocker liegt sie danach unverschlüsselt auf der Platte und überlebt das
Beenden.

| # | Schritt | Erwartet |
|---|---------|----------|
| I1 | In der Eingabeaufforderung `manage-bde -status C:` (oder Systemsteuerung → BitLocker) | „Schutz aktiviert" |

Steht dort etwas anderes, ist das ein Befund für die Schul-IT und kein Fehler
des Dashboards. Das Zeitschloss von 30 Minuten begrenzt das Zeitfenster, schließt
es aber nicht.

## Wenn etwas fehlschlägt

Nicht reparieren, sondern **messen und mitschicken**:

1. Den Bericht aus `tools/diagnose.py --datei …`.
2. Den vollständigen Text aus dem schwarzen Fenster (Rechtsklick → Markieren →
   Enter kopiert ihn).
3. Die Nummer der Zeile aus dieser Liste, an der es passiert ist.

Ein Fehlschlag in einer Zeile macht die vorherigen Zeilen nicht ungültig. Ein
übersprungener Schritt ist kein Fehlschlag — er wird als übersprungen notiert.
