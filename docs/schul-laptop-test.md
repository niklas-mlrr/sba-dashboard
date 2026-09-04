# Testlauf auf dem Schul-Laptop — Prüfliste

Diese Liste ist für **Niklas**, nicht für die Lehrkraft. Sie ist der einzige
offene Punkt, für den echte Hardware nötig ist; alles andere ist offline und in
der CI geprüft.

Zuletzt geprüft: *(noch nicht — Stand 2026-09-04 ist alles ungeprüft)*

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

## Prüfliste

Jede Zeile hat ein **messbares** Ergebnis. Keine Ja/Nein-Frage an einen
Menschen — die frühere Fehlmeldung des Testskripts kam genau daher.

### A. Erststart auf einem Gerät, das das Dashboard noch nie gesehen hat

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| A1 | `START.bat` doppelklicken | Fenster öffnet sich, keine Admin-Abfrage, keine Firewall-Abfrage | Uhrzeit Start |
| A2 | Warten, bis der Browser aufgeht | Liste ist sichtbar oder die Einrichtungsseite | **Dauer in Sekunden** |
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
| D2 | Eine `Bestand`-Zahl ändern | Feld übernimmt den Wert ohne Fehlermeldung | alter/neuer Wert |
| D3 | Mappe in Excel öffnen und nachsehen | Die Zahl steht drin | — |
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
| F1 | „Aus IServ abrufen", Zugangsdaten eingeben | Fortschrittsbalken bewegt sich | **Gesamtdauer** |
| F2 | Zusammenfassung am Ende | Zahl geänderter Zellen, Nachbestellungen | Zahlen |
| F3 | Warnungen in der Zusammenfassung | Falls „Titel und ISBN konnten nicht zwischengespeichert werden": der Gruppenordner ist schreibgeschützt | Wortlaut |
| F4 | Falsches Passwort eingeben | „Zugangsdaten stimmen nicht", HTTP 401, **kein** Absturz | — |
| F5 | Nach dem Abruf: Titel und ISBN in der Liste | gefüllt, ISBN mit Bindestrichen | ein Beispiel |
| F6 | Cache-Zeilen im Diagnosebericht | sagt, ob geteilt oder lokal geschrieben wurde | Zeilen |

### G. Zwei Fenster gleichzeitig

| # | Schritt | Erwartet | Notieren |
|---|---------|----------|----------|
| G1 | `START.bat` zweimal starten | Zweites Fenster nimmt den nächsten freien Port | beide Ports |
| G2 | In Fenster 1 eine Zahl ändern, dann in Fenster 2 dieselbe Zeile | Fenster 2 meldet, die Datei habe sich geändert, und lädt neu | Meldung |
| G3 | In beiden Fenstern gleichzeitig abrufen | Einer läuft, der andere wartet oder wird abgewiesen — **nie beide gleichzeitig schreiben** | Verhalten |

### H. Beenden

| # | Schritt | Erwartet |
|---|---------|----------|
| H1 | Knopf „Beenden" | Seite sagt, man könne das Fenster schließen; Fenster endet |
| H2 | Danach `START.bat` erneut | startet normal |

## Wenn etwas fehlschlägt

Nicht reparieren, sondern **messen und mitschicken**:

1. Den Bericht aus `tools/diagnose.py --datei …`.
2. Den vollständigen Text aus dem schwarzen Fenster (Rechtsklick → Markieren →
   Enter kopiert ihn).
3. Die Nummer der Zeile aus dieser Liste, an der es passiert ist.

Ein Fehlschlag in einer Zeile macht die vorherigen Zeilen nicht ungültig. Ein
übersprungener Schritt ist kein Fehlschlag — er wird als übersprungen notiert.
