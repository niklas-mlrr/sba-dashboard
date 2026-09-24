# Buchplanung — Listen freigeben, Einführung und Ausmusterung

Eine Bücherliste entsteht nicht an einem Tag. Über ein Schuljahr hinweg
passieren drei Dinge, und jedes gehört jemand anderem:

1. Die **Fachkonferenzleitungen** prüfen die Liste ihres Fachs und geben sie
   mit Kürzel und Datum frei.
2. Dabei werden Bücher **neu eingeführt** oder **ausgemustert**, bei
   Mehrjahresbänden gestaffelt über mehrere Schuljahre und Jahrgänge.
3. Eine **Fachschaft** möchte von einem auslaufenden Buch Exemplare behalten,
   statt sie wegzuwerfen.

IServ hält nichts davon fest. Dieses Paket tut es — in **einer Exceldatei je
Schuljahr**, die im Ordner der Bestandsmappe liegt. Der Grund ist derselbe wie
bei den Mehrjahresbänden: fällt das Dashboard aus, etwa nach einem
IServ-Update, liegt der Stand weiter auf dem Gruppenlaufwerk und ist ohne
dieses Programm lesbar.

Rein lesend gegenüber IServ (nur GET).

Das Paket liegt unter `buecherlisten/`, weil die Buchplanung **keinen eigenen
Reiter** hat: eingetragen wird in den Bücherlisten-Seiten selbst, und die
Bücher kommen aus `buecherlisten/core/daten.py`. Ein Paket der obersten Ebene
je Reiter im Kopf — `bestand/`, `buecherlisten/`, `mehrjahresbaende/` —, und
alles andere darunter.

## Die Datei: ein Bücher-Blatt, zwei Tabellen daneben

| Blatt | Schlüssel | eintragbar |
|-------|-----------|------------|
| `Buchreihen` | ISBN | Bemerkung |
| `Fächer & Jahrgang` | (ISBN, Fach, Jahrgang) | Einführung, Ausmusterung nach Schuljahr, Kürzel, Datum, Bemerkung (dazu `in der Bücherliste`, gesetzt) |
| `Rücklage` | (ISBN, Fach) | Anzahl, Kürzel, Datum, Status, Bemerkung |
| `Info` | — | (nichts; Schuljahr, Stand und Legende) |

Jeder Titel steht **einmal**, auf `Buchreihen`, mit Fach und Jahrgang als
Aufzählung, und den Preisen aus IServ daneben. Die beiden
anderen Blätter tragen nur ihren Schlüssel und das, was dazu eingetragen wird.

Bis 2026-09-20 standen die Bücher dreimal in der Mappe, einmal je Achse
(Verlag, Fach, Jahrgang), dazu ein eigenes Blatt `Fachbestätigung`.

### Die eine Regel, die das widerspruchsfrei hält

> Aus jedem Blatt wird nur seine **eigene** Eintragungs-Spalte zurückgelesen;
> alles andere wird bei jedem Schreiben neu gesetzt.

Wer auf `Buchreihen` einen Titel überschreibt, ändert damit nichts: beim
nächsten Abgleich steht dort wieder, was IServ sagt. Die eintragbaren Spalten
sind in der Datei hell hinterlegt. Dieselbe Regel liegt schon
`mehrjahresbaende/` zugrunde, dessen Blatt ebenfalls immer vollständig neu
geschrieben wird.

Gelesen wird über die **Spaltenüberschriften** in Zeile 1, nicht über feste
Buchstaben: wer in Excel eine Spalte einfügt, soll danach nicht stillschweigend
die falsche Spalte beschrieben bekommen.

## Welche Bücher in der Datei stehen

Aus dem **laufenden Schuljahr alle**, aus dem **Vorjahr die leihbaren**.

Das Vorjahr gehört dazu, weil gerade die Bücher interessant sind, die es nicht
mehr gibt: sie sind ausgemustert, und für sie wird eine Rücklage beantragt. Das
gilt aber nur für Leihbücher — ein Buch, das die Familien selbst kaufen, liegt
in keinem Regal der Schule. Verschwindet es aus der Bücherliste, gibt es daran
nichts mehr zu planen.

Dasselbe `leihbar` entscheidet, ob sich eine **Rücklage** eintragen lässt: nur
was die Schule verleiht oder im Vorjahr verliehen hat, hat sie im Regal und kann
sie zurücklegen. Bei einem Kaufbuch fehlt der Block im Menü, und der Server
weist eine Rücklage dazu mit einem Satz ab. Eine leere Eintragung bleibt
erlaubt — sonst ließe sich ein Wunsch von vor dieser Regel nie wieder löschen.

**Nicht** daran hängt die Ausmusterung. Bis 2026-09-20 nahm die Spalte
`Ausmusterung nach Schuljahr` nur bei `leihbar = ja` einen Wert an; das
verwechselte zwei Dinge. Ausgemustert wird eine **Bücherliste**, nicht ein
Bestand: auch ein Kaufbuch steht bis zu einem Schuljahr auf der Liste und
danach nicht mehr, und genau das hält die Spalte fest. Einführung und
Ausmusterung gelten deshalb für jedes Buch.

## Die Planung: (ISBN, Fach, Jahrgang)

Eine Zeile sagt für **ein Buch in einem Fach und einem Jahrgang**, ab wann es
dort geführt wird und nach welchem Schuljahr es dort ausläuft. Eine gestaffelte
Einführung eines Mehrjahresbands sind damit mehrere Zeilen:

| ISBN | Fach | Jg. | Einführung | Ausmusterung nach Schuljahr |
|------|------|-----|------------|------------------------------|
| 978-3-12-… | Erdkunde | 7 | 2027/2028 | |
| 978-3-12-… | Erdkunde | 8 | 2028/2029 | |
| 978-3-50-… | Chemie | 9 | | 2027/2028 |

Das Fach gehört zum Schlüssel, weil ein Buch zu mehreren gehören kann: die
Fachschaft Chemie kann ein Buch auslaufen lassen, ohne dass Biologie davon
betroffen wäre — dieselbe Überlegung wie bei der Rücklage.

Der Jahrgang muss kein heutiges Vorkommen sein: „wird ab 2028/29 auch in
Jahrgang 9 eingeführt" ist gerade der Fall, für den es diese Zeile gibt.

Die Paare kommen aus den Bücherlisten selbst (`collect_entries` in
`../core/daten.py`), nicht aus dem Kreuzprodukt von Fächern und Jahrgängen: ein
Band, der in Jahrgang 7 zu Mathematik und in Jahrgang 8 zu Informatik gehört,
hat zwei Zeilen, nicht vier.

## Die Bestätigung steht in der Zeile, die sie bestätigt

Kürzel und Datum der Fachkonferenzleitung sind zwei Spalten auf
`Fächer & Jahrgang`. Der Knopf „Liste bestätigen" setzt sie in **alle** Zeilen
des Fachs — eine Sammelgeste wie „Preise bestätigen" beim Verlag.

Damit braucht es keinen gespeicherten „bestätigten Stand" mehr, gegen den zu
prüfen wäre, ob sich die Liste seither geändert hat: kommt ein Buch dazu,
bringt es eine Zeile ohne Kürzel mit, und das Fach steht von allein wieder auf
`teilweise`.

### Wann eine Änderung die Bestätigung kostet

Eingetragen wird die Bestätigung nur über „Liste bestätigen"; das Planungsmenü
eines Buchs kennt weder Kürzel noch Datum. Ändert `setze_buchplanung` eine
schon bestätigte Zeile, entscheidet das **laufende** Schuljahr, ob sie stehen
bleibt — `wirkt_im_schuljahr` fragt dazu nur eines: steht das Buch dieses Jahr
in diesem Fach und Jahrgang im Regal?

| Änderung | Status vorher → nachher | Kürzel |
|----------|------------------------|--------|
| Ausmusterung nach 2029/2030 eingetragen | `im Einsatz` → `läuft aus` | bleibt |
| Ausmusterung nach 2025/2026 eingetragen | `im Einsatz` → `ausgemustert` | fällt weg |
| Einführung ab 2028/2029 eingetragen | `im Einsatz` → `geplant` | fällt weg |
| geplante Einführung vorgezogen | `geplant` → `im Einsatz` | fällt weg |

Der Gedanke dahinter: die Fachkonferenzleitung hat eine Liste bestätigt. Was
erst in drei Jahren greift, ändert diese Liste nicht. Was das laufende Jahr
betrifft, schon — und diese Liste hat sie nie gesehen.

### Welche Zeilen aus IServ stammen

`Fächer & Jahrgang` trägt beide Arten von Zeile nebeneinander: die (Fach,
Jahrgang)-Paare aus den Bücherlisten und die, für die nur etwas geplant ist.
Die Spalte `in der Bücherliste` (`ja`/`nein`) hält fest, welche welche ist —
beim Lesen sähen sie sonst gleich aus, und der Unterschied wäre nach dem ersten
Speichern verloren. Daran hängen zwei Dinge:

* Das Planungsmenü lässt die **Einführung** eines Jahrgangs, in dem das Buch
  schon geführt wird, nicht ändern — daran ist nichts mehr zu entscheiden,
  offen ist nur die Ausmusterung.
* Eine geleerte Planungszeile verschwindet wirklich, statt beim nächsten Lesen
  als leere Zeile zurückzukommen.

Eine Datei aus der Zeit vor dieser Spalte hat sie nicht; dort zählt wie früher
jede Zeile als Vorkommen. Der nächste Abgleich stellt die Wahrheit aus IServ
ohnehin wieder her.

## Status werden gerechnet, nie eingetragen

Kein Status wird gespeichert; jeder folgt aus den eingetragenen Werten
(`modelle.py`). Ein gespeicherter Status könnte den Werten widersprechen, aus
denen er stammt — und niemand wüsste, welcher von beiden recht hat.

| Status | wann |
|--------|------|
| `bestätigt` (Fach) | jede Zeile des Fachs trägt ein Kürzel |
| `teilweise` (Fach) | einzelne Zeilen sind noch ohne Kürzel — mit Angabe, welche |
| `geplant` / `im Einsatz` / `läuft aus` / `ausgemustert` | aus den beiden Schuljahren der Zeile gegen das Schuljahr der Datei |

Ein **neu eingeführtes Buch** bringt eine Zeile ohne Kürzel mit; das Fach fällt
damit von selbst auf `teilweise` zurück.

## Preise werden nicht bestätigt

Bis 2026-09-24 gab es auf `Buchreihen` die Spalten `geprüfter Preis`, `Kürzel`
und `Datum` und in der Verlags-Ansicht die Knöpfe „prüfen" und „Preise
bestätigen". Sie sind entfernt: der Preis gilt, wie er in IServ steht. Übrig
ist die Spalte `Bemerkung` je Buch. Eine ältere Datei mit den alten Spalten
bleibt lesbar; beim nächsten Speichern fallen sie weg.

## Aufbau des Pakets

| Modul | Inhalt |
|-------|--------|
| `modelle.py` | die Begriffe und die gerechneten Status |
| `mappe.py` | die Arbeitsmappe lesen und schreiben (openpyxl) |
| `laden.py` | beide Schuljahre aus IServ, über `../core/daten.py` |
| `abgleich.py` | zusammenführen und die einzelnen Eintragungen |

Kein HTTP, keine Einstellungen, keine Sperren — das steht im Dashboard
(`app/buchplanung.py`, `app/api/buchplanung.py`). Eingetragen wird in den
Bücherlisten-Seiten selbst, nicht auf einem eigenen Reiter.
