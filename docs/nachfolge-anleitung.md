# Bestandsliste im Browser — Anleitung

Diese Anleitung setzt kein Programmierwissen voraus. Sie beschreibt, was das
Programm tut, wie man es bedient und was zu tun ist, wenn etwas nicht geht.

Wer den Code verstehen will, liest stattdessen
[`architektur.md`](architektur.md).

---

## 1. Was das Programm ist

Die **Bestands- und Nachbestellungsliste** ist eine Excel-Datei im
IServ-Gruppenordner `Buchausleihe Admins`. Sie ist 62 Spalten breit: für jedes
Fach vier Spalten, für jeden Jahrgang eine Zeile. Das ist zum Lesen und Rechnen
gebaut, nicht zum Bearbeiten.

Dieses Programm zeigt dieselbe Datei als **gewöhnliche Liste** — eine Zeile je
Buch, sortierbar und filterbar, ohne nach rechts zu scrollen. Man kann darin
Zahlen ändern und die aktuellen Anmeldezahlen auf Knopfdruck aus IServ holen.

Drei Dinge, die dabei wichtig sind:

- **Die Excel-Datei bleibt die Datenbank.** Das Programm legt keine eigene
  Datenbank an. Was Sie hier ändern, steht danach in der Excel-Datei, und wer
  sie in Excel öffnet, sieht es.
- **Es läuft nur auf Ihrem Rechner.** Die Seite ist nicht aus dem Schulnetz
  erreichbar. In der Datei stehen Anmeldezahlen je Jahrgang; das gehört nicht
  auf eine offene Seite.
- **Es speichert kein Passwort.** Sie melden sich einmal im Programmfenster mit
  Ihren eigenen IServ-Zugangsdaten an. Die Anmeldung gilt, solange Sie arbeiten,
  und verfällt nach 30 Minuten ohne Abruf. Auf die Festplatte wird davon nichts
  geschrieben — beim nächsten Start ist alles wieder leer.

---

## 2. Starten

**Doppelklick auf `START.bat`.** Das ist alles.

Es öffnen sich ein schwarzes Fenster mit Text, das **Programmfenster** und der
Browser mit der Liste.

> **Weder das schwarze noch das Programmfenster schließen, solange Sie
> arbeiten.** Darin läuft das Programm. Wenn Sie es schließen, ist die Seite im
> Browser tot.

Das Programmfenster ist die Schaltzentrale. Darin:

| Feld oder Knopf | Wofür |
|-----------------|-------|
| Benutzername, Passwort, **Anmelden** | Die IServ-Anmeldung für den Abruf (Abschnitt 5) |
| **Seite öffnen** | Öffnet die Liste erneut im Browser — falls Sie den Tab versehentlich geschlossen haben |
| **Beenden** | Beendet das Programm sauber |
| **⚙** (Zahnrad) | Server und Ordner der Excel-Datei einstellen |

Beim **allerersten Mal** dauert es ein paar Minuten: das Programm richtet sich
im Benutzerprofil ein und lädt die benötigten Bausteine aus dem Internet. Beim
zweiten Start geht es in wenigen Sekunden.

Das Fenster sagt Ihnen auch die Adresse (etwa `http://127.0.0.1:8765/`). Falls
sich der Browser nicht von selbst öffnet, tippen Sie diese Adresse dort ein.

### Beim ersten Start: „Wo liegt die Bestandsliste?"

Findet das Programm die Excel-Datei nicht, sagt die Seite im Browser das und
nennt die geprüften Orte. Einstellen lässt es sich im **Programmfenster**:

1. Auf das **Zahnrad ⚙** klicken.
2. Bei **Ordner der Mappe** auf **Durchsuchen…** klicken und den Ordner
   auswählen, in dem die Bestandsliste liegt (nicht die Datei — den Ordner).
3. **Speichern**. Darunter steht dann, welche Datei das Programm gewählt hat.
4. Zurück im Browser die Seite neu laden (F5).

**Warum den Ordner und nicht die Datei?** Weil der Dateiname die Jahreszahl
trägt und mit dem Schuljahr wechselt. Das Programm nimmt die `.xlsx` mit der
höchsten Jahreszahl im Namen; liegt die alte Mappe noch daneben, ist das also
schon richtig. Sperrdateien, die Excel beim Öffnen anlegt (`~$…`), übergeht es,
und die Sicherungen im Unterordner `backups` ebenfalls.

Im selben Fenster steht auch der **IServ-Server** (etwa `iserv-trg-oha.de`) —
ohne `https://` davor. Er wird für die Anmeldung gebraucht und muss normalerweise
nie geändert werden.

Das Programm öffnet die gefundene Datei und prüft, ob sie wirklich die
Bestandsliste ist, bevor es sich den Ordner merkt. Ein falscher Ordner kann den
funktionierenden also nicht verdrängen. Beides bleibt gespeichert und steht beim
nächsten Start wieder da — auch nach einem Update des Programms.

---

## 3. Die Liste lesen

Eine Zeile ist **ein Buch in einem Jahrgang** — oder in mehreren, wenn es ein
Mehrjahresband ist (dann steht in der Spalte Jahrgang zum Beispiel `5-6`).

| Spalte | Bedeutung |
|--------|-----------|
| Fach | Das Fach aus der Kopfzeile der Excel-Datei |
| Jahrgang | Ein Jahrgang, oder eine Spanne bei Mehrjahresbänden |
| Titel, ISBN | Aus IServ. Leer, solange noch kein Abruf gelaufen ist |
| Angemeldet | Wie viele Schüler das Buch ausleihen. Kommt aus IServ |
| Bestand | Wie viele Exemplare die Schule hat. Kommt aus IServ |
| Bestellt | Wie viele bestellt, aber noch nicht da sind. **Änderbar** |
| zu bestellen | Angemeldet minus Bestand minus Bestellt. Wird gerechnet |

Oben gibt es einen Schalter **„nur Zeilen mit Bedarf"**. Er blendet alles aus,
wo nichts fehlt. Für eine Bestellung ist das meist die einzige interessante
Ansicht.

**Titel und ISBN sind leer?** Dann ist auf diesem Rechner noch kein Abruf
gelaufen. Sie stehen nicht in der Excel-Datei, sondern kommen aus IServ.
Einmal abrufen (siehe unten), dann sind sie da.

---

## 4. Eine Zahl ändern

Nur **Bestellt** lässt sich ändern — es ist die einzige Spalte mit einem
Eingabefeld. In das Feld klicken, Zahl eintippen, das Feld verlassen.
Gespeichert wird sofort.

- Erlaubt sind ganze Zahlen ab 0 — oder ein **leeres Feld**.
- **Leer ist nicht dasselbe wie 0.** Leer heißt „nichts bestellt", `0` heißt
  „nachgesehen, es ist nichts offen". Die Excel-Datei unterscheidet das, und
  das Programm auch.
- **Angemeldet**, **Bestand** und **zu bestellen** kann man nicht ändern. Die
  ersten beiden kommen aus IServ und würden beim nächsten Abruf ohnehin
  überschrieben; die dritte ist eine Rechnung.

> **Ihr Eintrag bleibt stehen.** Der Abruf ergänzt „Bestellt" aus dem Blatt
> `bestellt` derselben Excel-Datei — aber nur dort, wo für dieses Buch auch
> wirklich eine Bestellung eingetragen ist. Was Sie von Hand eintippen, löscht
> er nicht mehr. (Bis September 2026 war das anders.)

### Jede Änderung wird gesichert

Vor jedem Speichern legt das Programm eine Kopie der Excel-Datei im Unterordner
`backups` neben der Datei an, benannt mit Datum und Uhrzeit. Es behält die
letzten 30 und löscht ältere. Wenn etwas schiefgeht, ist die Datei von vorhin
also noch da: einfach aus `backups` zurückkopieren.

---

## 5. Zahlen aus IServ holen

**Zuerst anmelden:** im Programmfenster Benutzername und Passwort eintragen —
**Ihre eigenen IServ-Zugangsdaten**, nicht die von jemand anderem — und auf
**Anmelden** klicken. Darunter steht danach, als wer Sie angemeldet sind und
wann die Anmeldung verfällt.

Dann im Browser der blaue Knopf **„Aktuelle Daten aus IServ abrufen"** oben
rechts, und im Dialog auf **Abrufen**. Der Abruf dauert ein paar
Sekunden und zeigt einen Fortschrittsbalken.

> **„Bitte im Programmfenster anmelden"?** Dann ist die Anmeldung noch nicht
> erfolgt oder inzwischen verfallen — sie hält 30 Minuten ab dem letzten Abruf.
> Einfach im Programmfenster erneut anmelden und den Abruf noch einmal starten.
> Das ist Absicht: so liegt Ihr Passwort nicht den ganzen Tag im Speicher.

Wenn Sie zwischendurch sicher sein wollen, dass niemand an Ihrem Rechner einen
Abruf startet: **Abmelden** im Programmfenster. Das Programm läuft weiter, die
Liste bleibt bedienbar. Am Ende steht in der
Zusammenfassung, wie viele Zellen sich geändert haben und was nachbestellt
werden müsste.

**Die Seite lädt danach von selbst neu, und alle Zahlen, die der Abruf geändert
hat, sind zehn Sekunden lang gelb hinterlegt.** So sieht man auf einen Blick,
was neu ist. Danach verschwindet die Markierung von selbst.

Was der Abruf tut: Anmeldezahlen, Bestandszahlen, Titel und ISBN aus IServ holen
und in die Excel-Datei schreiben, außerdem das Blatt „zu Bestellen" neu
aufbauen.

### Wenn der Abruf nicht klappt

| Meldung | Was los ist |
|---------|-------------|
| „Zugangsdaten stimmen nicht" | Benutzername oder Passwort falsch. Erneut versuchen |
| „Konto hat keine Ausleihe-Verwalter-Rolle" | Ihr IServ-Konto darf diese Zahlen nicht sehen. Ansehen und Ändern geht trotzdem — nur der Abruf nicht. Wer die Rolle vergeben kann, ist die IServ-Administration |
| „IServ hat nicht geantwortet" | Netzverbindung weg oder IServ gerade nicht erreichbar. Später erneut versuchen |
| „Die Zuordnung Fach zu Buch ist nicht eindeutig" | In IServ stehen für ein Fach mehrere Bücher, und das Programm kann nicht raten, welches gemeint ist. **Es wurde nichts gespeichert.** Die Liste darunter sagt, welche Fächer betroffen sind — das muss jemand Technisches auflösen |
| „Die Datei ist gerade in Excel geöffnet" | Siehe nächster Abschnitt |

Wichtig beim vorletzten Fall: Das Programm speichert lieber **gar nichts** als
die Hälfte. Eine halb aktualisierte Liste wäre schlimmer als eine veraltete,
weil man ihr nicht ansieht, welche Zahl von wann ist.

Kommt am Ende ein Hinweis, dass **Titel und ISBN nicht zwischengespeichert**
werden konnten: Die Bestandszahlen sind trotzdem gespeichert. Nur die beiden
Anzeigespalten können leer bleiben. Kein Grund, den Abruf zu wiederholen.

---

## 6. „Die Datei ist gerade in Excel geöffnet"

Der häufigste Fehler im Alltag — und meist der eigene zweite Bildschirm.

**Lösung:** Die Bestandsliste in Excel schließen und es erneut versuchen. Steht
in der Meldung ein Name, hat diese Person die Datei offen; dann hilft nur ein
kurzer Anruf.

Zwei Dinge, die dabei zu wissen sind:

- Das Programm **kann** die Datei lesen, während sie in Excel offen ist. Nur
  Schreiben geht nicht.
- Manchmal liegt neben der Datei eine Datei mit `~$` am Anfang, obwohl niemand
  sie offen hat — Excel ist dann irgendwann abgestürzt und hat sie
  liegengelassen. Sie allein blockiert nichts; wenn das Speichern trotzdem
  klappt, ist alles in Ordnung. Man kann sie gefahrlos löschen, wenn sicher ist,
  dass niemand die Datei offen hat.

---

## 7. Beenden

Knopf **„Beenden"** — im Programmfenster oder auf der Seite, beide tun dasselbe.
Danach kann auch das schwarze Fenster geschlossen werden.

Der Knopf im Programmfenster ist der Weg, der immer funktioniert: Er ist auch
dann noch da, wenn Sie den Browser-Tab schon zugemacht haben. Und wenn Sie das
Programmfenster einfach zuklappen, fragt es nach und beendet dann ebenfalls
alles. Es geht dabei nichts verloren, weil jede Änderung sofort gespeichert wird.

---

## 8. Wenn gar nichts geht

Der Reihe nach:

1. **Ist das Netzlaufwerk verbunden?** Im Explorer den Ordner
   `Buchausleihe Admins` öffnen. Geht das nicht, geht auch das Programm nicht —
   das ist kein Fehler des Programms.
2. **Alle Fenster des Programms schließen und neu starten.** Das löst
   erstaunlich viel, besonders nach einem Verbindungsabbruch.
3. **Sagt das schwarze Fenster etwas?** Wenn dort eine Meldung im Klartext
   steht, ist sie für Sie geschrieben und meist die Antwort.
4. **`tools/diagnose.py` laufen lassen.** Das Werkzeug prüft die üblichen
   Ursachen der Reihe nach und schreibt einen Bericht, den man weitergeben kann.
   Wie: siehe [`schul-laptop-test.md`](schul-laptop-test.md).
5. **Bericht weitergeben.** Zuständig ist derzeit Niklas. Am hilfreichsten sind
   der Bericht aus Schritt 4 und der Text aus dem schwarzen Fenster.

Was Sie **nicht** tun müssen: nichts neu installieren, nichts in der
Excel-Datei reparieren, nichts löschen. Die Excel-Datei ist durch die Backups
und durch die Art, wie gespeichert wird, gegen Abstürze geschützt — ein Abbruch
mitten im Speichern lässt die alte Fassung unberührt.

---

## 9. Für den Fall, dass jemand Technisches übernimmt

- Der Quellcode liegt auf GitHub: `niklas-mlrr/sba-dashboard`, dazu die beiden
  Bibliotheken `niklas-mlrr/sba-bestand` und `niklas-mlrr/ausleihe-api`.
- Warum es so gebaut ist: [`architektur.md`](architektur.md).
- Wie es auf den Laptop kommt und wie man das zurückdreht:
  [`verteilung.md`](verteilung.md).
- Was noch offen ist: [`roadmap.md`](roadmap.md).
- Alle Tests laufen ohne Netz und ohne die echte Excel-Datei:
  `uv sync --all-groups && uv run pytest`.
