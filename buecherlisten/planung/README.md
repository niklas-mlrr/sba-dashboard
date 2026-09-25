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
| `Buchreihen` | ISBN | Bemerkung; Titel, Verlag, Neupreis, Leihpreis, leihbar als Korrektur (mit Kommentar) |
| `Fächer & Jahrgang` | (ISBN, Fach, Jahrgang) | Einführung, Ausmusterung nach Schuljahr, Kürzel, Datum, Bemerkung (dazu `in der Bücherliste`, gesetzt) |
| `Rücklage` | (ISBN, Fach) | Anzahl, Kürzel, Datum, Status, Bemerkung |
| `Info` | — | (nichts; Schuljahr, Stand und Legende) |

Jeder Titel steht **einmal**, auf `Buchreihen`, mit Fach und Jahrgang als
Aufzählung, und den Preisen aus IServ daneben. Die beiden
anderen Blätter tragen nur ihren Schlüssel und das, was dazu eingetragen wird.

Bis 2026-09-20 standen die Bücher dreimal in der Mappe, einmal je Achse
(Verlag, Fach, Jahrgang), dazu ein eigenes Blatt `Fachbestätigung`.

### Die Datei ist das Soll, IServ wird verglichen

> Was in der Datei steht, gilt. Der Abgleich nimmt nur **neue** Bücher aus
> IServ auf; alles, was die Datei schon kennt, bleibt, wie es dort steht.

Bis 2026-09-25 zog jeder Abgleich Titel, Verlag, Preise, Fächer und Jahrgänge
auf IServ nach. Danach war jede Abweichung verschwunden, bevor sie jemand
gesehen hatte. Seitdem ist es umgekehrt:

* **Die Bücherlisten-Seiten zeigen die Datei.** IServ wird live geholt und
  nur verglichen (`vergleich.py`). Ist ein Wert in IServ anders, wird die Zelle
  gelb und nennt den IServ-Wert beim Überfahren. Steht ein Buch laut Datei in
  einer Gruppe, in IServ aber nicht, trägt die Zeile „fehlt in IServ“; im
  umgekehrten Fall „nur in IServ“, mit den Werten aus IServ und ohne
  Planungsmenü. Die Übersichten markieren jede Gruppe, in der etwas abweicht.
  Ohne Datei zeigen die Seiten IServ wie vorher. Die PDFs bleiben beim Stand
  aus IServ mit den Korrekturen der Datei.
* **Gleich** ist ein Buch, wenn es in der Datei und in einer Bücherliste
  dieses Schuljahrs steht, Titel, Verlag, Neupreis, Leihgebühr und leihbar
  übereinstimmen und seine (Fach, Jahrgang)-Paare in IServ genau die sind, in
  denen die Datei es **dieses Schuljahr** führt: eingeführt in diesem
  Schuljahr oder vorher, ausgemustert nach diesem Schuljahr oder später
  (`wirkt_im_schuljahr`). Ein Buch in zwei Fächern muss in beiden stimmen, ein
  Mehrjahresband in jedem Jahrgang.
* **Der Abgleich** legt die Datei an und nimmt danach neue ISBNs auf, samt
  der Ausmusterung nach dem Vorjahr für ihre weggefallenen Paare. Ein Buch,
  das aus IServ verschwindet, bleibt mit allem, was dazu eingetragen ist; es
  ist eine Abweichung, kein Aufräumen. Bei den übrigen Büchern schreibt der
  Abgleich nur den frischen IServ-Wert als Kommentar an jede abweichende Zelle.
* **Wer in Excel einen Titel oder Preis überschreibt, ändert damit das
  Soll.** Der nächste Abgleich lässt den Wert stehen und hängt den IServ-Wert
  als Kommentar daran.

Die eintragbaren Spalten sind in der Datei hell hinterlegt. Die übrigen Blätter
(`Info`, die Zusammenfassung `Fach`/`Jahrgang` auf `Buchreihen`) werden bei
jedem Schreiben neu gesetzt.

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

Jedes (Fach, Jahrgang)-Paar, in dem ein leihbares Buch im Vorjahr stand und
heuer nicht mehr, bekommt beim Abgleich auf `Fächer & Jahrgang` die
`Ausmusterung nach Schuljahr` = Kennung des Vorjahres. Ein von Hand
eingetragener Wert bleibt. Die Fach-Seite listet diese Zeilen unter der
Bücherliste in der Tabelle „Ausmusterungen zu diesem Schuljahr“.

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
jede Zeile als Vorkommen.

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
ist die Spalte `Bemerkung` je Buch.

## Korrekturen an den Angaben aus IServ

Seit 2026-09-24 lassen sich Titel, Verlag, Neupreis und Leihgebühr eines
Buchs im Planungsmenü korrigieren, im Block „Buchreihe“ vor Einführung und
Ausmusterung. Der Block ist dem IServ-Dialog „Buchreihe bearbeiten“
nachgebaut. Die ISBN steht dort nur zum Lesen, grau hinterlegt: sie ist der
Schlüssel des Buchs. **Gespeichert wird in dieser Datei, nicht in IServ**: das
Dashboard bleibt dort nur-lesend.

Seit 2026-09-25 gehört auch „Leihbar“ dazu, als Häkchen unter den Preisen und
vor Einführung und Ausmusterung. In IServ ist das kein Feld der Buchreihe,
sondern eines jeden Listeneintrags (`borrowable`). Die Korrektur gilt für das
Buch in allen Listen, und `korrigiere_eintrag` setzt sie auf den Eintrag. Der
Kommentar lautet „in IServ: ja“ oder „in IServ: nein“. Ein korrigiertes
„leihbar“ entscheidet auch, ob eine Rücklage möglich ist.

* **Die Korrektur steht in der Zeile des Buchs.** Auf `Buchreihen` trägt die
  Zelle den korrigierten Wert, hell hinterlegt, und als Kommentar den Wert aus
  IServ („in IServ: 22,50 €“). Ein eigenes Blatt dafür gab es nur am
  2026-09-24 für einige Stunden; seit die ISBN nicht mehr änderbar ist, hat
  jede Korrektur ihre Zeile schon.
* **Der Kommentar nennt IServ.** Beim Abgleich behält jede Zelle ihren Wert
  (die Datei ist das Soll, siehe oben). Weicht IServ davon ab, bekommt sie
  als Kommentar den frischen IServ-Wert; nennt IServ selbst den Wert der
  Datei, fällt der Kommentar weg. Bis 2026-09-25 bekam eine Zelle **ohne**
  Kommentar beim Abgleich den Wert aus IServ.
* **Die Korrektur wirkt überall.** Die Seiten zeigen ohnehin die Datei. Für
  das PDF legt `wende_korrekturen_an` in `../core/daten.py` die Korrekturen
  auf die Rohdaten jeder Bücherliste, bevor sie ausgewertet werden.
* **Zurück auf IServ.** Die Datei kennt zu jedem korrigierten Feld den
  IServ-Wert (`Buch.iserv`), zu jedem anderen ist der heutige Wert der aus
  IServ. `setze_buchreihe` entscheidet daran: gleicht die Eingabe dem
  IServ-Wert, fällt die Korrektur weg. Ein leerer Preis heißt ebenfalls
  „wie in IServ“.

Fächer und Jahrgänge, die IServ im selben Dialog führt, lassen sich hier nicht
ändern: sie kommen aus den Bücherlisten, nicht aus der Buchreihe.

Die Datei gilt je Schuljahr. Eine neue Datei für das nächste Schuljahr bringt
die Korrekturen des Vorjahrs **nicht** mit (`docs/roadmap.md`).

## Ein Buch hinzufügen

Unter der Fach-Liste steht „+ Buch hinzufügen“: dasselbe Menü, aber die ISBN
ist frei. ISBN und Titel schlagen die Bücher der Datei vor, die zu diesem Fach
noch nicht gehören. `fuege_buch_hinzu` nimmt das Buch über seine Jahrgänge auf,
und jeder Jahrgang braucht ein Schuljahr der Einführung, weil eine leere
Planungszeile verschwindet.

* **Bekannte ISBN** (anderes Fach, Vorjahr): Es bleibt dasselbe Buch. Weicht
  die Buchreihe ab, ist das eine Korrektur wie oben.
* **Neue ISBN**: Sie muss eine gültige ISBN-10 oder -13 sein und wird als
  ISBN-13 gespeichert. Das Buch wird von Hand angelegt (`Buch.von_hand`, auf
  `Buchreihen` die Spalte `in IServ` = „nein“). Titel, Verlag und Preise sind
  dann keine Korrektur, sondern die einzige Quelle. Der Abgleich behält das
  Buch, solange es eine Planungszeile hat. Führt IServ die ISBN selbst, ist es
  nicht mehr „von Hand“; seine Werte und die Planung bleiben die der Datei,
  Abweichungen zu IServ werden markiert. Werden im Menü alle Jahrgänge
  entfernt, fällt das Buch aus der Datei.

Die Fach-Seite zeigt solche Bücher in ihrer Liste, weil sie aus der Datei
kommt (`gruppen_nach_fach_aus_datei` in `app/buecherlisten.py`); ein erst
künftig eingeführtes Buch steht dort mit „(ab …)“. Das PDF bleibt beim Stand
aus IServ.

## Aufbau des Pakets

| Modul | Inhalt |
|-------|--------|
| `modelle.py` | die Begriffe und die gerechneten Status |
| `mappe.py` | die Arbeitsmappe lesen und schreiben (openpyxl) |
| `laden.py` | beide Schuljahre aus IServ, über `../core/daten.py` |
| `abgleich.py` | zusammenführen und die einzelnen Eintragungen |
| `vergleich.py` | die Datei mit IServ vergleichen, je Buch |

Kein HTTP, keine Einstellungen, keine Sperren — das steht im Dashboard
(`app/buchplanung.py`, `app/api/buchplanung.py`). Eingetragen wird in den
Bücherlisten-Seiten selbst, nicht auf einem eigenen Reiter.
