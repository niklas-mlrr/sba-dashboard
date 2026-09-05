# Was noch offen ist

Stand: 2026-09-05. Diese Datei löst `PLAN.md` als Arbeitsliste ab; `PLAN.md`
bleibt als abgeschlossener v1-Plan liegen.

Zwei Arbeitslisten stehen hier nebeneinander: die **Funktionslücken** (unten,
allen voran der Testlauf auf dem Schul-Laptop) und der **Struktur-Backlog**
aus dem Review vom 2026-09-05. Ersteres blockiert die Inbetriebnahme,
Letzteres die Wartbarkeit — der Struktur-Backlog ist deshalb billig jetzt und
teuer später, aber nie dringend.

## Der Windows-Job hat sofort einen echten Fehler gefunden

Genau dafür war er da. `os.replace` — der letzte Schritt jedes atomaren
Schreibvorgangs — scheitert unter Windows mit `PermissionError` (`WinError 5`),
solange **irgendein** Handle auf die Zieldatei offen ist. Unter POSIX gelingt
dasselbe `rename` klaglos, deshalb konnte das lokal nie auffallen.

Betroffen war der Sidecar-Cache: vier lesende Threads gegen 60 Schreibvorgänge,
und **beide** Speicherorte fielen mit `WinError 5` aus. Das ist kein
Testartefakt — das Dashboard ist ausdrücklich für mehrere gleichzeitige Fenster
gedacht (Prüfliste, Abschnitt G), der Sidecar liegt auf dem Gruppenlaufwerk,
und ein Abruf schreibt ihn genau dann, wenn ein anderes Fenster ihn beim
Seitenaufbau liest. Auf dem Schul-Laptop hätte das gelegentlich die Meldung
„Titel und ISBN konnten diesmal nicht zwischengespeichert werden" erzeugt,
ohne dass etwas kaputt gewesen wäre.

Behoben durch kurzes Wiederholen (`_ersetze_mit_wiederholung`, sieben Versuche
über gut eine halbe Sekunde): ein Leser hält die Datei nur für die Dauer eines
`read()`. Hört der Fehler nicht auf, ist es kein Leser mehr, und der Rückfall
auf den lokalen Ordner greift wie zuvor. Zwei neue Tests stellen den
Windows-Fehler unter POSIX nach, damit beides prüfbar bleibt.

**Dieselbe Ursache traf auch die Leseseite.** Mit der Wiederholung beim
Schreiben war `WinError 5` weg, der nächste Lauf scheiterte im selben Test
aber an einem *leeren* Cache: während `os.replace` läuft, beantwortet Windows
ein `open()` mit einer Zugriffsverletzung, und `_datei_lesen` machte daraus
unter seinem gemeinsamen `except OSError` stillschweigend „kein Cache
vorhanden". Ein Seitenaufbau, der zufällig in einen Abruf fällt, hätte Titel
und ISBN leer gezeigt. Die Leseseite wiederholt jetzt mit denselben Werten.

**Und dieselbe Ursache steckte in der Arbeitsmappe selbst** (`sba-bestand`,
`atomic_save_workbook`) — dort ungefunden, weil die CI nur den Cache
provoziert. Erreichbar ist sie mit Absicht: der Lesepfad (`GET /` und
`/api/rows`) lädt die Mappe **ohne** Sperre, damit ein Leser nie auf einen
Schreiber warten muss; nur der Schreibpfad nimmt `arbeitsmappe_sperren`. Zwei
Fenster — Abschnitt G der Prüfliste — überlappen sich also genau so. Die Folge
wäre nicht nur ein verlorener Schreibvorgang, sondern eine falsche Erklärung:
`app/excel.py` übersetzt jeden `PermissionError` in „Die Datei ist gerade in
Excel geöffnet", und die Lehrkraft hätte Excel geschlossen und dieselbe
Meldung wieder bekommen. Der bestehende Test
`test_lesen_waehrend_des_schreibens_…` trifft den Fall nicht, weil er den Save
*vor* dem Ersetzen anhält.

**Zweiter Befund aus demselben Fehlschlag:** Pytest war auf Windows nach zwei
Minuten fertig, der Prozess lief danach aber weitere zehn Minuten, bis die CI
ihn abbrach. Ursache war der fehlgeschlagene Test selbst — er setzte sein
Stopp-Signal erst *nach* der Schleife, in der die Ausnahme flog, sodass vier
Leser-Threads endlos weiterliefen und der Interpreter beim Beenden auf sie
wartete. Jetzt stehen sie in einem `finally` und sind Daemon-Threads: ein
Fehlschlag kann den Lauf nicht mehr aufhängen. Das ist auch der Grund, warum
`--timeout` je Test hier nicht half — die Tests waren längst durch.

## Die CI ist gelaufen — was sie bestätigt hat

Der erste Lauf hat die Annahme abgeräumt, die beim Einrichten offen blieb: das
Standard-`GITHUB_TOKEN` checkt die beiden öffentlichen Geschwister-Repos ohne
zusätzliches Secret in den Workspace aus, `astral-sh/setup-uv@v10.0.1` greift,
und der Abgleich von `requirements.txt` gegen `uv export` läuft in neun
Sekunden durch. Linux 3.10 und 3.11 sind grün.

Zwei Dinge, die dabei aufgefallen sind und behoben wurden:

- Es gab **keine Zeitgrenze**, weder je Job noch je Test. Ein Lauf, der nicht
  von selbst endet, hätte die GitHub-Vorgabe von 360 Minuten ausgeschöpft.
  Jetzt: `timeout-minutes: 30` je Job und `pytest-timeout` mit
  `--timeout-method=thread`, das im Ernstfall den Stack jedes Threads ausgibt
  statt schweigend weiterzulaufen.
- Die Suite brauchte **74 Sekunden** statt der angenommenen zehn. Der
  Nachmessung nach war das keine langsame Datei-Ein- und -Ausgabe, sondern ein
  Fehler in `bestand.core.grid`, der auch das Dashboard selbst betraf — siehe
  den nächsten Abschnitt. Nach der Behebung: 9,6 Sekunden.

## Nebenbefund aus der CI: `parse_grid` war 92x zu langsam

Die auffällige Laufzeit der Testsuite hatte eine Ursache, die den Schul-Laptop
unmittelbar betrifft. `bestand.core.grid` fragte für jede Zelle über
`"K3" in merged` ab, ob sie in einem Zellenverbund liegt. Openpyxl baut dabei
jedes Mal ein neues `CellRange` samt Prüfung seiner vier Deskriptoren — am
echten Blatt (142 Zellenverbünde) **1496 µs je Abfrage**. `parse_grid` stellt
rund 250.000 solcher Abfragen und brauchte damit **gut drei Sekunden**.

Das Dashboard ruft `parse_grid` bei **jedem** Seitenaufruf und **jeder**
Zellenänderung auf. Die drei Sekunden lagen also auf jedem Klick, zusätzlich
zur Wartezeit über das Netzlaufwerk.

Behoben in `sba-bestand` durch einen reinen Ganzzahlvergleich der vier Grenzen
(`merge_deckt_ab`) — inhaltlich dieselbe Prüfung, die `CellRange.__contains__`
am Ende auch macht, nur ohne Objektbau: 7,5 µs statt 1496 µs.
`parse_grid` fällt damit von **3,09 s auf 0,034 s** (Faktor 92), das Raster
ist unverändert (72 Zeilen, 16 Sperrflächen), und alle 43 Tests von
`sba-bestand` bleiben grün.

Beim Testlauf auf dem Schul-Laptop ist das die Erklärung, falls jemand die
Oberfläche von früher als zäh in Erinnerung hat. Nicht mituntersucht:
`sba-launcher/core/catalog.py` hat eigene Kopien derselben Hilfsfunktionen mit
demselben Muster — dort lohnt sich derselbe Handgriff, gehört aber nicht in
dieses Repo.

## Nur Niklas kann es erledigen

### 1. Testlauf auf dem Schul-Laptop

Der einzige Punkt, an dem wirklich Hardware fehlt. Alles andere ist offline
geprüft. Ablauf und Abnahmekriterien stehen in
[`schul-laptop-test.md`](schul-laptop-test.md); `tools/diagnose.py` sammelt die
Messwerte, die dabei anfallen, in eine Datei, die man mitschicken kann.

Am 2026-09-04 wurde die Liste **offline vorweggenommen**, soweit das ohne
Windows geht (Abschnitt „Trockenlauf" dort). Ergebnis: die Diagnose läuft mit
Rückgabewert 0 durch, meldet beide Geschwister-Pakete als installiert und das
Raster mit den erwarteten 72 Zeilen und 16 Sperrflächen; die Migration einer
alten Vollkopie (Abschnitt C) kürzt sie auf den einen abweichenden Schlüssel
ein, lässt den ausgelieferten Standard unangetastet und schreibt beim zweiten
Start nichts mehr; das Cache-Ausweichen auf den lokalen Ordner funktioniert
samt Rücklesen. Am Gerät bleibt damit das, was Windows, SMB, IServ und eine
Uhr braucht.

Besonders zu prüfen, weil hier zuletzt etwas Grundlegendes umgestellt wurde:

- Der erste Start nach der Umstellung installiert `ausleihe-api` und
  `sba-bestand` ins venv (vorher `PYTHONPATH`). Dauert das länger als ein paar
  Sekunden? Läuft es beim **zweiten** Start ohne Neuinstallation durch?
- Eine schon vorhandene `%LOCALAPPDATA%\sba-dashboard\config.json` aus der alten
  Fassung: bleibt der ausgewählte Excel-Pfad nach der Migration erhalten?
- Ist der Sidecar-Cache auf dem Gruppenlaufwerk schreibbar, oder weicht das
  Dashboard auf den lokalen Ordner aus? (Die Antwort steht in den Warnungen des
  Abrufs.)

### 2. Gestaltungsvorlage — weiterhin blockiert

**Offen und nicht auflösbar, solange keine Referenz vorliegt.** Das Dashboard
soll sich am offiziellen Schulbuchausleihe-Modul orientieren. Es gibt lokal
keine brauchbare Vorlage: die PNGs in `ausleihe-ausgabe/` sind Clipart,
`web/scan-view.css` ist iOS-Stil.

Gebraucht werden Screenshots des Moduls oder eine Beschreibung von Farben,
Typografie, Tabellenkopf und Knopfformen. Bis dahin läuft `app/static/app.css`
mit einem zurückhaltenden Platzhaltersatz an Marken; wenn die Vorlage da ist,
werden **nur die Werte in `:root`** ersetzt, nicht die Regeln darunter.

## Struktur-Backlog (Review vom 2026-09-05)

Ein Struktur-Review fand 16 Punkte; sechs sind erledigt (Commit `24aaa08`,
dazu `sba-bestand` `6478e4c`) — der dritte `os.replace`-Ort, die doppelte
Plattform-Ordner-Auflösung, die zwei Formen von `/api/refresh/status`, die
erinnerte Testisolation und zwei Fehler in `app.js`. Die folgenden zehn stehen
noch aus, absteigend nach Nutzen je Aufwand.

### 1. `Host`- und `Origin`-Prüfung fehlt (das Wichtigste hier)

Es gibt keine Middleware. Die Bindung an 127.0.0.1 hält das Netz ab, **nicht
den Browser**:

- `POST /api/beenden` nimmt keinen Body und ist damit cross-origin auslösbar.
  Eine beliebige Seite, die die Lehrkraft während des Betriebs öffnet, kann das
  Dashboard beenden (einfache Anfrage, kein Preflight; die Antwort ist
  blockiert, die Wirkung nicht).
- **DNS-Rebinding:** eine fremde Domain, die auf 127.0.0.1 auflöst, gilt dem
  Browser als dieselbe Herkunft und darf `GET /` und `/api/rows` lesen — also
  genau die Anmeldezahlen, deren Offenlegung `architektur.md` einen
  Datenschutzvorfall nennt.

Behebung: `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost"])`
(Starlette schneidet den Port selbst ab) plus Ablehnung zustandsändernder
Anfragen mit fremdem `Origin`. ⚠️ Bricht den `TestClient`, der `Host:
testserver` schickt — `conftest.py` braucht dann `base_url="http://127.0.0.1"`.

### 2. Fehler-auf-HTTP-Abbildung steht in jeder Route einzeln

`main.py` bildet dieselben Ausnahmen in jeder Route erneut ab, mit von Route zu
Route driftendem Wortlaut. Einmal registrierte
`@application.exception_handler(...)` für `Konflikt`, `Gesperrt`,
`EinstellungsFehler` und `BlattFehlt` ersetzen das; rund 60 Zeilen verlassen
`main.py`, und „welchen Code gibt `Gesperrt`?" hat wieder **eine** Antwort.
⚠️ `index()` rendert für dieselben Fehler HTML statt JSON und behält seinen
eigenen Zweig.

### 3. `main.py` mischt vier Aufgaben

App-Factory, Routen, Domänenlesen (`lies_tabelle`) und Mappenprüfung
(`validiere_excel_mappe`). Die letzten beiden enthalten kein FastAPI und
gehören nach `app/rows.py` bzw. `app/excel.py`; die Routen in `app/api/` als
`APIRouter`, `create_app` bleibt reine Verdrahtung. Das ist die Datei, die
jedes neue Feature anfasst.

### 4. Handgeschriebene Body-Validierung statt Pydantic

`dict = Body(...)` plus `isinstance`-Ketten, rund 40 Zeilen. Der Grund, es
nicht blind umzustellen, ist echt: FastAPIs 422 ist englisch und
Schema-förmig, und die Oberfläche zeigt `fehler` wörtlich einer Lehrkraft.
Lösbar mit Pydantic-Modellen plus **einem** `RequestValidationError`-Handler,
der auf `{"fehler": "<deutsch>"}` abbildet. Heute drei Anfrageformen, später
dreißig.

### 5. Untypisierte Notausgänge

`Schreibergebnis.ws: object = None` und `eintrag: object = None`; dazu gibt
`lies_tabelle` ein untypisiertes 4-Tupel zurück, dessen Leerfall
`(None, [], None, None)` jeder Aufrufer erst zerlegt und dann auf `None`
prüft. Typisieren und den Rückgabewert zu einem kleinen `Tabellenstand`
machen — das ist zugleich die Voraussetzung für Punkt 6.

### 6. Kein Typprüfer in der CI

Der Code ist durchgehend annotiert; mypy (oder ty/pyright) auf `app/` kostet
jetzt einen Konfigurationsblock und später viel mehr, sobald sich die
`object`-Felder aus Punkt 5 vermehren.

### 7. Keine Abdeckungsmessung

237 Tests, und niemand weiß, was sie abdecken. `pytest-cov` mit einer
Sichtbarkeitsschwelle, kein Tor bei 100 %.

### 8. `app/static/app.js` ist ungetestet

271 Zeilen, darin die Browserhälfte des optimistischen Sperrens (409 →
Neuladen, `mtime`-Buchführung, Escape-Rücknahme). Der pragmatische Weg, weil
„kein Build-Schritt" bewusste Entscheidung ist: das JS dumm halten (es ist
fast dort — `/api/cell` liefert die fertige Zeile) und die letzten
Logikreste hinter Datenattribute ziehen, die ein Template-Test prüfen kann.
Ab etwa 400 Zeilen trennt `<script type="module">` die Datei ohne Build.

### 9. Drei Beschreibungen derselben Architektur

`README.md`, `docs/architektur.md` und die Wiki-Seite beschreiben Cache,
Konfigurationsebenen und Schreibsicherheit jeweils erneut. Heute konsistent,
weil am selben Tag geschrieben. `architektur.md` sollte kanonisch sein, das
README nur noch Routentabelle, Schnellstart und Verweise tragen, die
Wiki-Seite zusammenfassen statt nachzuerzählen.

### 10. `PLAN.md` steht neben den lebenden Dokumenten

Als historisch markiert, aber in `README.md` und der Wiki-Tabelle in derselben
Liste geführt. Nach `docs/archiv/` verschieben oder löschen — Git hat sie.
Ebenso: die Wiki-Seite nennt Zahlen („231 Tests", „9,6 s"), die jeder Commit
falsch machen kann.

## Bewusst zurückgestellt

### Versionierte Wheels für die drei Repos

Heute binden sich die Repos über Pfade aneinander; ausgeliefert wird per Install
ins venv. Das trägt, solange eine Person an allen drei Repos gleichzeitig
arbeitet. Der Wechsel auf versionierte Wheels lohnt sich, sobald ein zweiter
Rechner eine *andere* Fassung von `sba-bestand` fahren soll als der
Entwicklungsstand. Begründung und Umschaltpunkt: [`verteilung.md`](verteilung.md).

### Refresh überschreibt Bestand und Bestellt

Bekannte Eigenschaft, keine Panne: der Abruf schreibt alle drei Spalten, wie es
das abgelöste Skript tat. Änderungen aus dem Browser an Bestand und Bestellt
leben also nur bis zum nächsten Abruf. Die Oberfläche sagt das an der Spalte
dazu. Eine Zusammenführung wäre erst sinnvoll, wenn jemand feststellt, dass ihn
das im Alltag stört.

### `zu Bestellen` im Browser bearbeiten

Nicht vorgesehen. Das Blatt wird beim Abruf neu aufgebaut; eine Bearbeitung
darin wäre beim nächsten Lauf weg, ohne dass es jemand merkt.

## Erledigt und damit hier nur noch als Stichwort

Lesen, Schreiben, IServ-Abruf, Windows- und macOS-Start, Ersteinrichtung mit
geprüfter Mappe, prozessübergreifende Schreibsperre, gehärteter Sidecar-Cache,
Trennung von ausgeliefertem Standard und Benutzerkonfiguration, eigenständige
Auslieferung ohne `PYTHONPATH`, CI mit Ruff und pytest auf Linux und Windows.
Wo das jeweils steht, sagt [`architektur.md`](architektur.md).
