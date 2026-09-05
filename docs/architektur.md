# Architektur und Struktur-Befunde

> Diese Datei ist die **kanonische** Beschreibung. `README.md` trägt
> Schnellstart, Routentabelle und Verweise, die Wiki-Seite fasst zusammen —
> beide erklären nichts von dem, was hier steht, ein zweites Mal. Bis zum
> 2026-09-05 taten sie das, und Cache, Konfigurationsebenen und
> Schreibsicherheit standen dreifach da: an dem Tag noch übereinstimmend, weil
> sie am selben Tag geschrieben worden waren.

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

## Aufteilung innerhalb von `app/`

Eine Datei, eine Aufgabe. Bis zum 2026-09-05 vereinte `main.py` vier davon —
App-Factory, sämtliche Routen, das Domänenlesen und die Mappenprüfung — und war
damit die Datei, die jedes neue Feature anfassen musste.

```
app/
  main.py           App-Factory: Zustand, Middleware, Handler, Router. Sonst nichts.
  konfiguration.py  lade_einstellungen - Laden MIT Konsolenhinweis
  sicherheit.py     Host- und Origin-Prüfung (siehe "Warum 127.0.0.1")
  fehler.py         Ausnahme -> HTTP, einmal für die ganze Anwendung
  modelle.py        Anfragekörper als Pydantic-Modelle + deutsche Meldungen
  api/
    seite.py        GET /            und POST /api/einrichtung   (HTML + sein Formular)
    tabelle.py      GET /api/rows    und POST /api/cell
    abruf.py        POST /api/refresh und GET /api/refresh/status
    system.py       GET /health      und POST /api/beenden
    gemeinsam.py    Vorlagen, Einstellungen aus dem Request, der 503-Leerfall
  rows.py           Raster -> Anzeigezeilen, lies_tabelle -> Tabellenstand
  excel.py          Laden, Sperren, Schreiben, Prüfen einer Mappe
  refresh.py        IServ-Abruf mit instanzgebundenem Fortschritt
  cache.py          Sidecar mit Titel, ISBN, Preis
  settings.py       Zwei Konfigurationsebenen
  paths.py          Plattformabhängige Ordner
  dateien.py        Atomares Schreiben kleiner Dateien
  start.py          Freier Port, uvicorn, Browser
```

`rows.py`, `excel.py`, `refresh.py`, `cache.py`, `settings.py`, `paths.py` und
`dateien.py` importieren **kein FastAPI**. Das ist keine Ordnungsliebe, sondern
die Voraussetzung für den nächsten Abschnitt: Ausnahmen, die nichts über HTTP
wissen, lassen sich an einer Stelle auf HTTP abbilden.

### Ausnahme → HTTP steht an genau einer Stelle

`app/fehler.py` registriert einen Handler je Ausnahme. Vorher tat das jede
Route für sich, mit von Route zu Route driftendem Ergebnis: `BlattFehlt` war im
Lesepfad 500 und im Schreibpfad 503.

| Ausnahme | Status | zusätzlich im Körper |
|----------|--------|----------------------|
| `MappeUngeeignet`, `UngueltigeAenderung` | 400 | — |
| ungültiger Anfragekörper | 400 | — |
| `Konflikt` | 409 | `mtime` |
| `LaeuftBereits` | 409 | `status` |
| `Gesperrt` | 423 | `benutzer` |
| `EinstellungsFehler`, `BlattFehlt` | 500 | — |
| `ExcelFehlt` | 503 | — |

Jede Antwort hat die Form `{"fehler": "<deutscher Klartext>"}`, weil
`app/static/app.js` genau dieses Feld wörtlich anzeigt. **Eine** Route fällt
heraus: `GET /` liefert HTML und fängt ihre Fehler weiterhin selbst, mit
denselben Statuscodes — drei Zeilen JSON im Browserfenster wären für die
Lehrkraft die schlechteste aller Antworten.

`MappeUngeeignet` gibt es nur, damit diese Tabelle eindeutig sein kann: eine
*neu ausgewählte* Datei ohne Raster ist eine Eingabe der Lehrkraft (400), ein
fehlendes Blatt in der Mappe, mit der schon gearbeitet wird, ein Serverzustand
(500). Vorher war beides dieselbe Ausnahmeklasse mit zwei Bedeutungen.

### Der Anfragekörper: Pydantic plus ein deutscher Handler

`app/modelle.py` beschreibt die drei schreibenden Routen als Modelle. Der Grund,
das nicht früher zu tun, war echt: FastAPIs Vorgabeantwort auf einen ungültigen
Körper ist ein englisches, schemaförmiges 422, und die Oberfläche zeigt
`fehler` wörtlich an. Gelöst ist das mit **einem** `RequestValidationError`-
Handler, der die Fehlerliste auf einen deutschen Satz abbildet und dabei den
Statuscode 400 behält. Er gibt insbesondere nie den Eingabewert zurück — bei
`POST /api/refresh` wäre das das Passwort.

Was Pydantic bewusst **nicht** prüft: ob `wert` eine schreibbare Zahl ist. Diese
Regel gehört zur Mappe und steht mit ihrer Begründung in `app.excel.pruefe_wert`.

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

### Die Paketgrenze ist geprüft, nicht nur beschrieben

`sba-bestand` liefert seit dem 2026-09-05 eine `bestand/py.typed`. Vorher waren
`Snapshot`, `GridEntry`, `UpdateResult` und `BestandConfig` für mypy hier
schlicht `Any`: sie standen in den Signaturen von `app/refresh.py` für den
Leser, geprüft wurde an der Grenze nichts. Ein vertauschtes Argumentpaar wäre
erst zur Laufzeit aufgefallen.

Zwei Dinge waren dafür nötig, und das zweite ist das unerwartete:

1. Der Marker selbst plus sein Eintrag in `[tool.setuptools.package-data]` von
   `sba-bestand` — `packages.find` sammelt nur `.py`-Dateien ein.
2. `mypy_path = "../sba-bestand"` **hier**. Der editable-Install von setuptools
   legt in `site-packages` keinen Paketordner ab, sondern einen Import-Finder
   (`__editable___sba_bestand_0_1_0_finder.py` plus `.pth`). mypy liest
   `sys.path`, nicht die Import-Hooks der Laufzeit, und sah das Paket damit
   überhaupt nicht — der Marker allein hätte nichts geändert. Nachgeprüft mit
   `reveal_type`, nicht am ausbleibenden Fehler.

Deshalb steht in `[tool.mypy]` auch **kein** globales `ignore_missing_imports`
mehr, sondern nur noch die namentliche Ausnahme. Global gesetzt würde es einen
Bruch der Pfad-Auflösung lautlos verschlucken: `bestand.core` fiele auf `Any`
zurück, und kein Lauf würde rot.

Die CI baut das Geschwister-Layout im Workspace nach (`sba-dashboard/`,
`sba-bestand/`, `ausleihe-api/` nebeneinander), der relative Pfad trägt dort
also genauso.

Am selben Tag bekam `ausleihe-api` dieselbe Behandlung — es war die letzte
Stelle, an der eine Paketgrenze unkontrolliert war, und sie stand in **beiden**
Nachbar-Repos unter `ignore_missing_imports`. Dasselbe Muster, dieselbe Falle:
Marker plus `package-data`, `mypy_path` um `../ausleihe-api` erweitert (mypy
trennt mehrere Pfade am Komma; ein Doppelpunkt wäre unter Windows Teil eines
Laufwerksbuchstabens), und wieder mit `reveal_type` nachgeprüft — vorher
viermal `Any` bei grünem Lauf.

Was das hier konkret bringt, sind zwei Stellen in `app/refresh.py`:

- `fehlerabbildung()` bildet `AuthError`, `ForbiddenError` und `TransportError`
  auf 401/403/504 ab. Ein Tippfehler in einem dieser Namen war vorher kein
  Fehler, sondern ein `Any`, das jedes `isinstance` klaglos schluckte.
- `melde_an()` setzt `client_factory = AusleiheClient`. Erst jetzt prüft mypy,
  dass die Klasse überhaupt zu `ClientFabrik` passt — also mit drei Strings
  aufrufbar ist und etwas mit `login() -> None` zurückgibt. Gegengeprüft: eine
  andere Klasse aus `ausleihe` an derselben Stelle wird abgelehnt.

`ausleihe.*` steht jetzt wie `bestand.*` unter `follow_imports = "silent"` —
Typen benutzen, aber Meldungen aus dem Bibliothekscode dort melden, wo er
gepflegt wird. Beide Bibliotheken haben dafür einen eigenen mypy-Lauf;
`ausleihe-api` prüft in seiner CI mit.

Damit liefern alle drei Repos des Geschwister-Layouts `py.typed`, und die
einzige verbliebene namentliche Ausnahme ist `openpyxl.*`.

## Warum 127.0.0.1

Die Mappe enthält Anmeldezahlen je Jahrgang. Ein Server, der im Schulnetz
lauscht, macht daraus eine offene Seite ohne Anmeldung. Das Dashboard hört
ausschließlich auf die Loopback-Adresse; wer es benutzt, sitzt am Rechner.

### Was die Bindung allein nicht abdeckt

Sie hält das **Netz** ab, nicht den **Browser** auf demselben Rechner. Zwei
Wege blieben deshalb bis zum 2026-09-05 offen, und beide sind nicht
theoretisch:

- **Auslösen von einer fremden Seite.** `POST /api/beenden` nimmt keinen
  Körper. Eine beliebige Seite im Nachbartab kann sie mit einem einfachen
  `fetch` auslösen — kein Preflight nötig. Die Antwort bleibt der fremden
  Seite verborgen, die Wirkung nicht: das Dashboard ist zu.
- **DNS-Rebinding.** Eine fremde Domain, deren DNS-Eintrag auf 127.0.0.1
  zeigt, gilt dem Browser als eigene Herkunft. Ihre Seite darf `GET /` und
  `/api/rows` lesen **und auswerten** — also genau die Zahlen, deren
  Offenlegung dieser Abschnitt einen Datenschutzvorfall nennt.

Dagegen stehen zwei Schichten (`app/sicherheit.py`), und sie greifen an
verschiedenen Stellen:

| Schicht | Prüft | Fängt |
|---------|-------|-------|
| `TrustedHostMiddleware` | `Host` gegen `127.0.0.1`/`localhost` | DNS-Rebinding, auch auf den Lesewegen |
| `HerkunftMiddleware` | `Origin` bei POST/PUT/PATCH/DELETE | die fremde Seite im Nachbartab |

Gegen Rebinding hilft der Origin-Vergleich **nicht** — die Herkunft *ist* dann
dieselbe; nur der `Host`-Kopf trägt weiter den Namen des Angreifers. Umgekehrt
hilft die Host-Prüfung nicht gegen den Nachbartab, der das Dashboard korrekt
unter `127.0.0.1` anspricht. Deshalb beide.

Der Port wird in beiden Fällen nicht geprüft: `app.start.freier_port` weicht
bei belegtem Port aus, ein zweites Fenster läuft also regulär unter einem
anderen. Ein fehlender `Origin` gilt als erlaubt — ein Browser setzt ihn bei
jeder zustandsändernden Anfrage einer fremden Seite, ohne ihn kommt die
Anfrage aus `curl` oder `tools/diagnose.py`, und die laufen ohnehin schon auf
diesem Rechner.

Das ist **keine Anmeldung**. Wer am Rechner sitzt, darf weiterhin alles.

Praktische Folge für Tests: der `TestClient` schickt `Host: testserver` und
bekäme sonst durchweg 400. `tests/conftest.py` setzt deshalb
`base_url="http://127.0.0.1"`.

## Warum die Mappe nie im Speicher bleibt

Sie liegt auf einem Netzlaufwerk und kann jederzeit in Excel geöffnet oder von
jemand anderem gespeichert werden. Jede Anfrage lädt sie neu und merkt sich nur
die Änderungszeit. Ein gehaltenes Workbook würde still veralten und beim
Speichern fremde Änderungen überschreiben.

## Der Schreibpfad: vier Schutzschichten

`POST /api/cell` ändert genau eine Zahl. Vier Schichten stehen davor, und alle
vier sind nötig:

**Kein freier Zellbezug.** Die Route nimmt den Zeilenschlüssel entgegen
(`0:Deutsch:C3`), nie eine Referenz wie `"K3"`. Der Schlüssel wird gegen das
*frisch geparste* Raster aufgelöst. Ein Bearbeiter, der eine Zeile einfügt,
verschiebt damit keine Zahl in die falsche Zelle — und ein manipulierter Aufruf
kann keine beliebige Zelle der Mappe beschreiben. Schreibbar sind nur `bestand`
und `bestellt`; `angemeldet` kommt aus IServ und `zu bestellen` ist eine Formel.

**Optimistisches Sperren.** Der Browser muss die `mtime` mitschicken, die er beim
Laden gesehen hat. Weicht sie ab, hat jemand anderes gespeichert (oder der
Abruf lief) → HTTP 409, die Seite lädt neu. Ohne diese Prüfung würde ein Klick
in einem seit einer Stunde offenen Tab stillschweigend einen frischen Abruf
überschreiben.

**Schreibvorgänge serialisieren.** `arbeitsmappe_sperren` hält ein lokales
Thread-Schloss und zusätzlich eine Betriebssystem-Sperre auf einer Sidecar-Datei
neben der Mappe. Die Sperre umfasst Laden, Versionsprüfung, Änderung und
Speichern. Manuelle Änderungen und Refresh verwenden denselben Weg. Dadurch
können zwei Prozesse nicht beide dieselbe alte Fassung laden und nacheinander
speichern. Auf dem SMB-Laufwerk gilt dies, sofern der Server Dateisperren
weitergibt.

**Atomar speichern.** `atomic_save_workbook` (in `bestand.core`, nicht mehr im
IServ-Client — siehe [`verteilung.md`](verteilung.md)) schreibt in eine Nachbardatei,
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

Jede mit `create_app` gebaute FastAPI-Instanz besitzt einen eigenen
`RefreshManager`. Er hält Status und Lauf-Lock der Instanz. Ein zweiter Abruf in
derselben Instanz bekommt 409. Der gemeinsame Workbook-Lock schützt die Datei
zusätzlich vor anderen App-Instanzen und manuellen Zelländerungen.

### Fortschritt

Die Jahrgangs-Bücherlisten werden bewusst nicht über `fetch_snapshot(eager=True)`
geladen, sondern in `RefreshManager._lade_jahrgaenge` selbst durchlaufen. Erst danach
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
Das ist nicht nur eine Beschreibung, sondern die Begründung dafür, wie hart mit
ihm umgegangen werden darf: eine kaputte Cache-Datei darf niemals eine Anfrage
scheitern lassen. `laden()` wirft deshalb unter keinen Umständen. Ungültiges
JSON, ein `stand`, der kein Zeitstempel ist, eine Eintragsliste, die ein Array
ist, ein Preis als `"12,50"` — jeder dieser Fälle wird zu einem leeren oder
teilweise gefüllten Cache, nicht zu einem Fehler. Ein einzelner kaputter Eintrag
wird bereinigt, statt die ganze Datei zu verwerfen.

Geschrieben wird atomar: Nachbardatei, `fsync`, `os.replace`. Ohne das
hinterlässt ein Abbruch mittendrin eine halbe JSON-Datei, die beim nächsten Start
genau so aussieht wie ein Cache, der nie geschrieben wurde — nur dass sie
existiert und die Frage „lief der Abruf?" falsch beantwortet.

### Ein Cache-Fehler ist eine Warnung, kein gescheiterter Abruf

Der Cache wird geschrieben, **nachdem** die Mappe erfolgreich gespeichert wurde.
Zu diesem Zeitpunkt sind die Zahlen sicher. Schlägt danach das Schreiben des
Caches fehl, wäre „Abruf fehlgeschlagen" eine Lüge mit Folgen: die Lehrkraft
würde ihn wiederholen, obwohl er getan hat, was er sollte. Der Lauf endet
deshalb erfolgreich, und in den Warnungen steht, dass Titel und ISBN diesmal
leer bleiben können.

### Speicherort: geteilt vor schreibbar

Der Sidecar bleibt primär neben der Mappe, weil er gemeinsame Anzeigedaten sind
— ein Abruf von einem Rechner füllt Titel und ISBN für alle, die die Mappe
öffnen, und der Cache verschwindet mit ihr, ohne dass ihn jemand extra
aufräumen muss. Das Gruppenlaufwerk kann aber schreibgeschützt oder kurz nicht
erreichbar sein. Deshalb weicht `speichern()` bei einem `OSError` auf einen
zweiten, plattformabhängigen Ordner im lokalen Benutzerprofil aus
(`cache_pfad_lokal`, überschreibbar über `SBA_CACHE_DIR`). Scheitert auch das,
bleibt es bei der Warnung oben.

Der Trade-off ist bewusst **geteilt vor garantiert schreibbar**, weil der Cache
reine Anzeige ist: im schlimmsten Fall fehlt eine Spalte, nie steht eine falsche
Zahl in der Tabelle. Beim Lesen werden beide Orte tolerant geparst, und der mit
dem neueren `stand` gewinnt — damit ein Abruf, der auf den lokalen Ordner
ausweichen musste, beim nächsten Laden trotzdem sichtbar wird.

## Zwei Ebenen: ausgelieferter Standard + Benutzerkonfiguration

`config.json` im Repo ist der ausgelieferte Standard und wird im Normalbetrieb
nie beschrieben — eine Anpassung der Lehrkraft darf einen Git-Pull oder eine
Neukopie durch `START.bat` nicht verlieren. Vorher war genau das der Fall: die
Ersteinrichtung schrieb den gewählten Excel-Pfad in die versionierte Datei
zurück.

Anpassungen landen jetzt in einer Benutzerkonfiguration in einem
plattformabhängigen Ordner:

| Plattform | Pfad |
|-----------|------|
| Windows | `%LOCALAPPDATA%\sba-dashboard\config.json` |
| macOS | `~/Library/Application Support/sba-dashboard/config.json` |
| Linux | `$XDG_CONFIG_HOME/sba-dashboard/config.json`, sonst `~/.config/…` |

`SBA_CONFIG_DIR` überschreibt den Ordner auf jeder Plattform; die Tests setzen
sie immer, damit nichts im echten Benutzerprofil landet.

Diese Datei enthält **nur tatsächlich geänderte Schlüssel**, kein Vollduplikat,
und wird flach über den Standard gelegt. Fehlt sie oder ist sie kaputt, gilt der
Standard — der Start wird dadurch nie verhindert. Ein *zusammengesetztes*
Ergebnis, das semantisch ungültig ist (etwa ein Port aus dem Overlay außerhalb
1024–65535), bricht dagegen mit Klartext ab: zu raten, welche Ebene schuld ist,
wäre schlimmer als ein deutlicher Fehler.

`config.beispiel.json` ist damit weggefallen. Sie war byteweise identisch zur
ausgelieferten `config.json` und damit eine zweite Wahrheit ohne Zusatznutzen.

### Migration einer alten Vollkopie

Auf schon eingerichteten Rechnern lag unter `%LOCALAPPDATA%` eine vollständige
Kopie der alten `config.json`, angelegt von der früheren `START.bat`. Sie würde
jedes künftige Update des Standards maskieren. Beim ersten Laden mit dem
Ebenenmodell wird sie einmalig bereinigt: Schlüssel, die weiterhin mit dem
Standard übereinstimmen, werden verworfen, echte Abweichungen — allen voran der
gewählte Excel-Pfad — bleiben erhalten. Zurückgeschrieben wird nur, wenn sich
dabei wirklich etwas ändert.

Der Arbeitskopie-Modus (`--config PATH`, benutzt von `START.sh`) bleibt
unverändert: dort sind Standard und Benutzerkonfiguration bewusst dieselbe
Datei, und geschrieben wird genau dorthin.

### Was validiert wird

Nicht aus Ordnungsliebe, sondern weil jeder dieser Werte einen Fehlerweg hat,
der sonst erst spät und unverständlich auffällt: `iserv_domain` (ein
`https://`-Präfix ist der häufigste Tippfehler und wird ausdrücklich benannt),
`port` (1024–65535; darunter bräuchte es Rechte, die niemand haben soll),
`backups_behalten` (0–1000), `blatt_raster`, `excel_pfad_kandidaten` und
`sicherheitsbestand`. Unbekannte Schlüssel sind **kein** Fehler — eine spätere
Fassung darf welche ergänzen —, werden aber gesammelt und beim Start genannt,
damit ein Tippfehler im Schlüsselnamen nicht stillschweigend wirkungslos bleibt.

### Die echte IServ-Domain steht im ausgelieferten Standard — und das Repo ist öffentlich

`config.json` nennt die echte Domain und die echten Kandidatenpfade, und die
drei Repos sind öffentlich. Das ist eine Entscheidung, kein Versäumnis. Die
Domain ist keine Zugangsberechtigung — jede Lehrkraft tippt sie ohnehin in den
Browser —, und ein Platzhalter im Standard ließe den allerersten Start an der
Anmeldung scheitern, bevor die Lehrkraft überhaupt etwas wählen kann. Die
Excel-Kandidaten sind ohnehin nur Vorschläge: die Ersteinrichtung lässt die
Lehrkraft die Datei auswählen, und genau diese Auswahl wandert in die
Benutzerkonfiguration, nicht in den Standard.

Was dagegen nie im Repo liegen darf, wird durch `.gitignore` und die Vorlage
gehalten: Zugangsdaten (das Passwort existiert nur in der einen Abrufanfrage,
siehe „Der Abruf"), personenbezogene Zahlen und die echte Arbeitsmappe.
`vorlage/` ist die bereinigte, mit `tools/erzeuge_vorlage.py` erzeugte
Strukturvorlage; `.local/` ist ignoriert und wird auch von `START.bat` nicht
gespiegelt.

Umschaltpunkt: widerspricht die Schule der Nennung ihres Servernamens in einem
öffentlichen Repo, wandert die Domain in die Benutzerkonfiguration — dann muss
die Ersteinrichtung ein Feld für sie bekommen.

## Wie hier dokumentiert wird

Dokumentation liegt an drei Orten mit je einer Aufgabe: die Wiki-Seite fasst
zusammen und verlinkt, `roadmap.md` hält die Arbeitsliste und die Hergänge von
Änderungen, und dieses Dokument ist kanonisch für das *Warum*. In den
Docstrings des Codes steht deshalb nur der zeitlose Grund einer Entscheidung —
keine datierte Erzählung („bis zum TT.MM.JJJJ war es anders"). Der Grund: eine
datierte Erzählung im Code ist beim nächsten Commit sofort falsch und wird dann
stillschweigend ignoriert; Hergänge gehören dorthin, wo sie gepflegt werden
(`roadmap.md` und die Wiki-Logs). Bestehende Docstrings, die nach dem alten
Stil erzählen, werden beim nächsten Anfassen ihrer Stelle auf den zeitlosen
Kern gekürzt — nicht in einem eigenen Umbaulauf.

## Warum das venv nach %LOCALAPPDATA%

`START.bat` spiegelt die drei Quellbäume vom Netzlaufwerk nach
`%LOCALAPPDATA%\sba-dashboard\app\` und legt das venv daneben. Ein venv auf
einem SMB-Laufwerk ist quälend langsam und übersteht keinen Verbindungsabbruch.
Kopiert wird nur der Programmcode — die Excel-Datei bleibt, wo sie ist, sonst
gäbe es zwei Wahrheiten.

Eine Kopie von `requirements.txt` im venv bezeichnet den zuletzt erfolgreich
installierten Stand. `START.bat` führt `pip install` erneut aus, wenn die
gespiegelte Datei davon abweicht. Der Marker wird erst nach erfolgreicher
Installation ersetzt. Ein abgebrochenes Update wird beim nächsten Start daher
erneut versucht.

Die beiden Geschwister-Repos werden in dasselbe venv **installiert**, nicht über
den `PYTHONPATH` untergeschoben. Ein `PYTHONPATH` koppelt die *laufende*
Anwendung an eine Ordnerstruktur; ein halb gespiegelter Baum oder ein Fenster mit
altem `PYTHONPATH` bricht sie dann an einer Stelle, an der niemand mehr sucht.
Nach dem Install hängt sie an nichts außer dem venv, und die gespiegelten
Quellbäume sind nur noch Bauzutat.

Damit das auch offline funktioniert, bekommt das venv beim Anlegen `setuptools`
und `wheel` mit; installiert wird dann mit `--no-build-isolation --no-deps`.
Ohne `--no-build-isolation` holte sich pip bei jedem Update ein Build-Backend aus
dem Netz — genau der Fall, der auf dem Schul-Laptop nicht verlässlich klappt.
`--no-deps` hält `requirements.txt` als einzige Quelle für Paketversionen.
Neu installiert wird nur, wenn `robocopy` gemeldet hat, dass sich an den beiden
Bäumen etwas geändert hat, oder wenn das venv neu ist.

Warum es überhaupt drei Repos bleiben und was die Alternativen wären (uv-
Workspace, versionierte Wheels), steht mit Migration und Rollback in
[`verteilung.md`](verteilung.md).
