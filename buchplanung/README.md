# Buchplanung — Preise prüfen, Listen freigeben, Einführung und Ausmusterung

Eine Bücherliste entsteht nicht an einem Tag. Über ein Schuljahr hinweg
passieren vier Dinge, und jedes gehört jemand anderem:

1. Der **Beauftragte für die Schulbuchausleihe** prüft die Preise gegen die
   Verlagslisten — Buch für Buch oder eine ganze Verlagsliste auf einmal.
2. Die **Fachkonferenzleitungen** prüfen die Liste ihres Fachs und geben sie
   mit Kürzel und Datum frei.
3. Dabei werden Bücher **neu eingeführt** oder **ausgemustert**, bei
   Mehrjahresbänden gestaffelt über mehrere Schuljahre und Jahrgänge.
4. Eine **Fachschaft** möchte von einem auslaufenden Buch Exemplare behalten,
   statt sie wegzuwerfen.

IServ hält nichts davon fest. Dieses Paket tut es — in **einer Exceldatei je
Schuljahr**, die im Ordner der Bestandsmappe liegt. Der Grund ist derselbe wie
bei den Mehrjahresbänden: fällt das Dashboard aus, etwa nach einem
IServ-Update, liegt der Stand weiter auf dem Gruppenlaufwerk und ist ohne
dieses Programm lesbar.

Rein lesend gegenüber IServ (nur GET).

## Die Datei: drei Arbeitsblätter, zwei kleine dazu

Die Bücher stehen **dreimal**, einmal je Arbeitsschritt und je Achse. Wer die
Datei ohne das Dashboard öffnet, findet drei Listen, die drei Personen
entsprechen:

| Blatt | Schlüssel | eintragbar |
|-------|-----------|------------|
| `Preise je Verlag` | ISBN | geprüfter Preis, Kürzel, Datum, Bemerkung |
| `Bücher je Fach` | (ISBN, Fach) | Rücklage-Anzahl und -Status, Kürzel, Datum, Bemerkung |
| `Bücher je Jahrgang` | (ISBN, Jahrgang) | eingeführt ab, ausgemustert nach, Beschluss, Bemerkung |
| `Fachbestätigung` | Fach | Kürzel, Datum, Bemerkung |
| `Info` | — | (nichts; Schuljahr, Stand und Legende) |

Jedes Buch hat genau **einen** Verlag, also genau eine Zeile im Preisblatt. Ein
Buch kann zu **mehreren Fächern** gehören und steht dann im Fachblatt mehrfach
— genau deshalb kann die Fachschaft Chemie eine Rücklage beantragen, ohne dass
die Fachschaft Biologie davon betroffen wäre.

### Die eine Regel, die das widerspruchsfrei hält

> Aus jedem Blatt wird nur seine **eigene** Eintragungs-Spalte zurückgelesen;
> alles andere wird bei jedem Schreiben neu gesetzt.

Wer im Fachblatt einen Titel überschreibt, ändert damit nichts: beim nächsten
Abgleich steht dort wieder, was IServ sagt. Die eintragbaren Spalten sind in
der Datei hell hinterlegt. Dieselbe Regel liegt schon `mehrjahresbaende/`
zugrunde, dessen Blatt ebenfalls immer vollständig neu geschrieben wird.

Gelesen wird über die **Spaltenüberschriften** in Zeile 1, nicht über feste
Buchstaben: wer in Excel eine Spalte einfügt, soll danach nicht stillschweigend
die falsche Spalte beschrieben bekommen.

## Welche Bücher in der Datei stehen

Das **laufende Schuljahr und sein Vorjahr**. Das Vorjahr gehört dazu, weil
gerade die Bücher interessant sind, die es nicht mehr gibt: sie sind
ausgemustert, und für sie wird eine Rücklage beantragt. Die Spalte `Herkunft`
sagt je Zeile, woher sie stammt — `Vorjahr`, `aktuell`, `beide` oder
`nur Planung`.

Im Preisblatt steht nur das **laufende** Jahr: geprüft werden Preise von
Büchern, die auch verliehen werden.

## Die Planung: (ISBN, Jahrgang) mit zwei Schuljahren

Eine Planungszeile sagt für **ein Buch in einem Jahrgang**, ab wann es dort
geführt wird und nach welchem Schuljahr es dort ausläuft. Eine gestaffelte
Einführung eines Mehrjahresbands sind damit mehrere Zeilen:

| ISBN | Jg. | eingeführt ab | ausgemustert nach |
|------|-----|---------------|-------------------|
| 978-3-12-… | 7 | 2027/2028 | |
| 978-3-12-… | 8 | 2028/2029 | |
| 978-3-50-… | 9 | | 2027/2028 |

Der Jahrgang muss kein heutiges Vorkommen sein — „wird ab 2028/29 auch in
Jahrgang 9 eingeführt" ist gerade der Fall, für den es diese Zeile gibt. Solche
Zeilen tragen die Herkunft `nur Planung`.

## Status werden gerechnet, nie eingetragen

Kein Status wird gespeichert; jeder folgt aus den eingetragenen Werten
(`core/modelle.py`). Ein gespeicherter Status könnte den Werten widersprechen,
aus denen er stammt — und niemand wüsste, welcher von beiden recht hat.

| Status | wann |
|--------|------|
| `offen` | zu diesem Buch ist kein geprüfter Preis eingetragen |
| `bestätigt` | geprüfter Preis = Preis in IServ |
| `abweichend` | geprüfter Preis ≠ Preis in IServ |
| `bestätigt` (Fach) | die freigegebenen ISBNs sind genau die heutigen |
| `veraltet` (Fach) | seither kam ein Buch dazu oder fiel weg — mit Angabe, welches |
| `geplant` / `im Einsatz` / `läuft aus` / `ausgemustert` | aus den beiden Schuljahren gegen das Schuljahr der Datei |

Daraus fällt zweierlei von selbst:

* Ein **neu eingeführtes Buch** hat keinen geprüften Preis und steht damit
  automatisch auf `offen`. Niemand muss daran denken, nach einer Fachkonferenz
  die Preise erneut prüfen zu lassen.
* Ändert IServ einen Preis nach der Prüfung, kippt die Zeile auf `abweichend`.
  Deshalb wird der **Betrag** gespeichert und nicht nur ein Haken.

## Warum die Preise nicht automatisch geprüft werden

Geprüft, am 2026-09-19:

* **VLB** (Verzeichnis lieferbarer Bücher) hat tagesaktuelle, an die
  Buchpreisbindung gebundene Preise und eine REST-API — aber nur mit
  kostenpflichtigem Abo, Mindestlaufzeit ein Jahr.
* **DNB-SRU** ist kostenlos, liefert aber nur den Preis zum
  Erscheinungszeitpunkt, oft gar keinen. Für „stimmt der Preis noch?" wertlos.
* **Verlagsseiten abgreifen** bricht bei jedem Relaunch und ist über Jahre
  nicht verlässlich.

Deshalb bleibt die Prüfung eine menschliche Entscheidung. Eine Preisquelle
ließe sich später einhängen, ohne das Datenmodell zu ändern — am ehesten als
Import der Preislisten, die die Verlage ohnehin schicken.

## Aufbau des Pakets

| Modul | Inhalt |
|-------|--------|
| `core/modelle.py` | die Begriffe und die gerechneten Status |
| `core/mappe.py` | die Arbeitsmappe lesen und schreiben (openpyxl) |
| `core/laden.py` | beide Schuljahre aus IServ, über `buecherlisten.core` |
| `core/abgleich.py` | zusammenführen und die einzelnen Eintragungen |

Kein HTTP, keine Einstellungen, keine Sperren — das steht im Dashboard
(`app/buchplanung.py`, `app/api/buchplanung.py`). Eingetragen wird in den
Bücherlisten-Seiten selbst, nicht auf einem eigenen Reiter.
