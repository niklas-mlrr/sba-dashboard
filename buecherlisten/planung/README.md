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
| `Buchreihen` | ISBN | Bemerkung; Titel, Verlag, Neupreis, Leihpreis (das Soll, ohne Kommentar) |
| `Fächer & Jahrgang` | (ISBN, Fach, Jahrgang, Einführung) | leihbar, Einführung, Ausmusterung nach Schuljahr, je Antrag Entscheidung/Kürzel/Datum, Begründung, Kürzel, Datum, Bemerkung |
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
  nur verglichen (`vergleich.py`). Drei Farben: **gelb** ein anderer Wert
  (Titel, Verlag, Preise, leihbar; der IServ-Wert steht beim Überfahren),
  **blau** eine Einführung (laut Datei in Fach und Jahrgang, in IServ noch
  nicht), **rot** eine Ausmusterung (in IServ noch, laut Datei nicht mehr -
  auch unter „Ausmusterungen zu diesem Schuljahr“). Die Zeile hat vorn einen
  Strich in der Farbe, die Zelle ist hell hinterlegt, der Wert farbig. Ist die
  ganze Buchreihe neu oder ganz ausgemustert, ist die ganze Zeile hinterlegt.
  Bei einer neuen Reihe entscheidet das IServ-Inventar (`GET /series`,
  `_mit_inventar` in `app/api/buecherliste.py`): gibt es die Buchreihe dort
  noch nicht, ist die ganze Zeile einheitlich kräftig blau; gibt es sie schon,
  ist die Zeile nicht hinterlegt - Fach und Jahrgang blau, und was die Datei
  bei Titel, Verlag und Preisen anders führt als die Buchreihe, gelb.
  Eine Zeile, die nur IServ führt, zeigt die Werte aus IServ und hat kein
  Planungsmenü. Die Übersichten markieren jede Gruppe, in der etwas abweicht.
  Ohne Datei zeigen die Seiten IServ wie vorher. Die PDFs bleiben beim Stand
  aus IServ, mit Titel, Verlag, Preisen und leihbar aus der Datei.
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
  ist eine Abweichung, kein Aufräumen. Die übrigen Bücher lässt der Abgleich,
  wie sie sind.
* **Wer in Excel einen Titel oder Preis überschreibt, ändert damit das
  Soll.** Der nächste Abgleich lässt den Wert stehen; was IServ sagt, zeigt
  der Vergleich beim Öffnen der Seite. Die Datei selbst nennt IServ nicht.

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

## Eine Fachliste ist ganz oder gar nicht bestätigt

Kürzel und Datum der Fachkonferenzleitung sind zwei Spalten auf
`Fächer & Jahrgang`. Gesetzt und gelöscht werden sie aber immer für **alle**
Zeilen des Fachs (Entscheidung 2026-10-30): „Liste bestätigen" schreibt sie in
jede Zeile, „Bestätigung zurückziehen" löscht sie überall. Eine Liste kennt
genau drei Stände (`fach_status`):

| Stand | wann |
|-------|------|
| `Antrag ausstehend` | ein Antrag auf Einführung **zum** laufenden oder Ausmusterung **nach dem** vorigen Schuljahr ist noch offen (`blockierende_antraege`) — angezeigt als „1 Antrag ausstehend" / „N Anträge ausstehend" |
| `bestätigt` | sonst, wenn jede Zeile des Fachs ein Kürzel trägt |
| `offen` | sonst |

Solange ein Antrag aussteht, lehnt `bestaetige_fach` ab. Ein abgelehnter Antrag
ist entschieden und hält nichts auf; eine spätere Einführung (2027/2028) auch
nicht.

### Wann eine Änderung die Bestätigung kostet

Nach jeder Eintragung prüft `halte_bestaetigung` jedes vorher bestätigte Fach
(`app/buchplanung.py::_aendere`, einmal für alle Eintragungen):

* **Sie verfällt** — in allen Zeilen des Fachs —, wenn `verfallsgruende` etwas
  nennt: eine Einführung zum laufenden oder eine Ausmusterung nach dem vorigen
  Schuljahr kommt dazu, fällt weg oder verschiebt sich (auch nur in „leihbar"),
  oder die Liste dieses Schuljahrs führt sonst ein Buch mehr oder weniger.
  Ebenso, wenn danach ein Antrag aussteht (etwa nach „Zurücksetzen" auf der
  Änderungsliste).
* **Sie bleibt** bei allem anderen — eine Bemerkung, eine Ausmusterung nach
  2029/2030, eine Einführung ab 2028/2029 für einen neuen Jahrgang. Eine Zeile,
  die es vorher nicht gab, übernimmt dann Kürzel und Datum des Fachs.

| Änderung | Bestätigung |
|----------|-------------|
| Ausmusterung nach 2029/2030 eingetragen | bleibt |
| Ausmusterung nach 2025/2026 eingetragen | verfällt, Antrag steht aus |
| laufendes Buch erst ab 2028/2029 | verfällt |
| neuer Jahrgang ab 2027/2028 | bleibt, die Zeile übernimmt sie |
| Bemerkung geändert | bleibt |

Der Gedanke dahinter: die Fachkonferenzleitung hat eine Liste bestätigt. Was
erst in drei Jahren greift, ändert diese Liste nicht. Was das laufende Jahr
betrifft, schon — und diese Liste hat sie nie gesehen.

Ein Abgleich, der ein Buch aus IServ mitbringt, geht nicht durch
`halte_bestaetigung`: die neue Zeile hat kein Kürzel, und die Liste ist damit
`offen`, bis sie neu bestätigt wird.

### Eingeführt oder geplant

`Fächer & Jahrgang` trägt beide Arten von Zeile nebeneinander: die (Fach,
Jahrgang)-Paare, in denen das Buch schon eingeführt ist, und die, für die eine
Einführung geplant ist. Unterschieden werden sie an der **Einführung**: eine
Zeile ohne ist eingeführt (so kommen die Paare aus den Bücherlisten an), eine
Zeile mit ist geplant — auch dann, wenn ihr Schuljahr schon erreicht ist.
Daran hängen zwei Dinge:

* Das Planungsmenü lässt die Einführung eines eingeführten Jahrgangs nicht
  ändern und ihn nicht entfernen — offen ist nur die Ausmusterung. Ein
  geplanter Jahrgang ist ganz offen, braucht aber eine Einführung: ein
  geleertes Feld würde ihn sonst still zu einem eingeführten machen.
* Ein entfernter geplanter Jahrgang verschwindet wirklich, statt beim nächsten
  Lesen als leere Zeile zurückzukommen.

Ob ein Buch zu Recht in einem Jahrgang steht, sagt nicht die Datei, sondern
der Vergleich mit IServ (`vergleich.py`).

Bis 2026-09-25 hielt eine Spalte `in der Bücherliste` (`ja`/`nein`) fest,
welche Zeile aus IServ stammt, und auf `Buchreihen` eine Spalte `in IServ`,
welches Buch von Hand angelegt ist. Die erste folgt aus der Einführung, die
zweite braucht es nicht mehr, seit die Datei IServ nicht mehr nennt; eine
ältere Datei wird gelesen, als hätte sie sie nicht, und verliert sie beim
nächsten Speichern.

## Anträge: Einführung und Ausmusterung genehmigen

Seit 2026-09-30 ist jede Einführung und jede Ausmusterung ein **Antrag**, über
den entschieden wird. Die Seite „Änderungen“ im Menü „Bücherlisten“
(`GET /buecherliste/aenderungen`) listet dazu je (Buch, Fach, Jahrgang) auf:

* jede **Einführung** ab dem laufenden Schuljahr oder später,
* jede **Ausmusterung** nach dem Vorjahr oder später - nach dem Vorjahr heißt,
  das Buch fehlt schon in der Liste dieses Schuljahrs.

Eine Zeile mit beidem (ein Buch nur für ein Schuljahr) ergibt zwei Anträge.
Gerechnet wird das in `aenderungen_im_schuljahr` (`aenderungen.py`), entschieden
in `entscheide_antrag` (`abgleich.py`).

Seit 2026-10-02 ordnet `aenderungsliste` (bzw. die reine `ordne_aenderungen`)
jeden Antrag für sich ein: nach **Fach**, dann nach der **Rangfolge** aus
Jahrgang und Wechseljahr (`?sortierung=jg,wechsel`, je `-ab` für absteigend;
die Köpfe „Jg.“ und „Jahr“ stellen sie um wie bei den Bücherlisten,
`naechster_rang`). Das **Wechseljahr** ist bei „ab X“ das Jahr X, bei „nach Y“
das Jahr Y+1. Was in Fach, Jahrgang und Wechseljahr gleich ist, bildet einen
**Abschnitt** und steht auf gleicher Höhe: links die Ausmusterungen, rechts
die Einführungen. Innerhalb einer Seite zuerst nach der **Reichweite**
(`reichweite`): Bücher, deren nächster anderer Jahrgang darüber liegt
(Abstand 1, 2 …), dann Bücher nur für diesen Jahrgang, dann Bücher, die nach
unten weiterreichen (größter Abstand zuerst); reicht ein Buch in beide
Richtungen, zählt der kleinere Abstand, bei Gleichstand der nach oben. Danach
Leihbuch vor Kaufbuch, dann Titel.

Das Raster der Seite baut `baue_tabelle` in `app/aenderungsliste.py`: Titel
nur an der obersten Stelle eines Buchs im Fach, je Buch eine Zelle über
seine Zeilen (die kürzere Seite gestreckt), Kästen desselben Buchs hängen
über Abschnitte zusammen, Einrückung je Fach und Spalte nur dort, wo ein Buch
getrennt steht, und Gruppen aus Abschnitten mit gleichem Wert im vorderen
Kriterium (die Mitte zeigt ihn fett, das andere Kriterium grau; ausgerichtet
von `verteile` in `app/static/mittelspalte.js`). Entschieden wird jeder
Antrag für sich, im Buchmenü, das ein Klick auf seine Jahrgangszeile öffnet.

Auf `Fächer & Jahrgang` stehen dafür hinter „Einführung“ und hinter
„Ausmusterung nach Schuljahr“ je drei Spalten, dahinter eine gemeinsame:

| Spalte | Inhalt |
|--------|--------|
| `Antrag Einführung` / `Antrag Ausmusterung` | `genehmigt` oder `abgelehnt`; leer ist offen |
| `… Kürzel`, `… Datum` | wer wann entschieden hat |
| `Begründung` | Freitext, **eine** für beide Anträge der Zeile |

* **Entschieden wird mit Kürzel.** Kürzel und Datum stehen einmal oben auf der
  Seite und gelten für jeden Klick; ohne Datum gilt heute. „Zurücksetzen“
  macht den Antrag wieder offen.
* **Die Entscheidung gilt dem, worüber entschieden wurde.** Ändert sich das
  Schuljahr oder „leihbar“ der Zeile (seit 2026-10-30) - im Planungsmenü oder
  in Excel -, fällt sie beim nächsten Speichern weg (`_neue_zeile`), die
  Begründung bleibt. Ein anderer Jahrgang ist ohnehin eine andere Zeile. Jede
  andere Eintragung (Bemerkung, „Liste bestätigen“, Abgleich) lässt sie
  stehen. „2027/28“ und „2027/2028“ sind dasselbe Schuljahr.
* **„Abgelehnt“ ändert nichts von selbst.** Das Buch bleibt geplant, bis
  jemand die Planung im Menü ändert; die Entscheidung ist ein Vermerk, keine
  Löschung. Die Bücherlisten und PDFs bleiben, wie sie sind.
* Was in `Antrag …` weder `genehmigt` noch `abgelehnt` heißt, bleibt in der
  Datei stehen und gilt als offen. Eine Datei ohne die Spalten liest sich als
  „alles offen“ und bekommt sie beim nächsten Speichern.

Das Planungsmenü zeigt die Entscheidungen unter der Zeile, über die ganze
Breite und nur zum Lesen: „Einführung [genehmigt] durch MÜ am 12.10.2026.
Begründung: …“. Die Zeile ist in zwei Hälften hinterlegt - oben nach dem
Antrag auf Einführung, unten nach dem auf Ausmusterung: genehmigt in der Farbe
ihres Status, offen weiß, abgelehnt grau überdeckt.

## Farben der Fach-Ansicht

Seit 2026-10-30 färbt die Bücherliste eines Fachs nach der Planung, nicht nach
dem Vergleich mit IServ (`farben.py`; Verlag und Jahrgang vergleichen weiter
mit IServ):

| Farbe | wann | ganze Zeile | sonst | Jahrgangszahl |
|-------|------|-------------|-------|---------------|
| rot | Ausmusterung nach dem Vorjahr oder später | das Buch steht danach in keinem Fach und Jahrgang mehr | Zelle „Jahrgang“ | rot und durchgestrichen bei „nach dem Vorjahr“ |
| gelb | Wechsel von „leihbar“ (eine Zeile endet, im selben Jahrgang beginnt eine mit dem anderen Häkchen) | — | Zelle „Leihbar“ | — |
| gelb | Titel, Verlag, Preise weichen von IServ ab | — | die Zelle | — |
| blau | Einführung zum laufenden Schuljahr oder später | das Buch wird zum ersten Mal überhaupt eingeführt | Zelle „Jahrgang“ | blau bei „zum laufenden Schuljahr“ |

Ein Wechsel zählt nur gelb, nicht zugleich rot und blau. Mehrere Farben teilen
den Strich vorn und jede Zelle in gleich hohe Bänder, rot über gelb über blau.

„Ausmusterungen zu diesem Schuljahr“ (`in_ausmusterungen`) führt ein Buch, wenn
jeder Jahrgang, in dem es im Fach leihbar war, spätestens nach dem Vorjahr
ausgemustert ist (der letzte genau dann) und es im Fach nicht wieder eingeführt
wird. Läuft es als Kaufbuch weiter, steht es in beiden Listen, mit derselben
Jahrgang-Spalte. Dort ist es ganz rot, wenn es danach nirgends mehr steht, sonst
sind Jahrgang und Leihbar rot.

## Status werden gerechnet, nie eingetragen

Kein Status wird gespeichert; jeder folgt aus den eingetragenen Werten
(`modelle.py`). Ein gespeicherter Status könnte den Werten widersprechen, aus
denen er stammt — und niemand wüsste, welcher von beiden recht hat.

| Status | wann |
|--------|------|
| `offen` / `Antrag ausstehend` / `bestätigt` (Fach) | siehe „Eine Fachliste ist ganz oder gar nicht bestätigt" |
| `geplant` / `im Einsatz` / `läuft aus` / `ausgemustert` | aus den beiden Schuljahren der Zeile gegen das Schuljahr der Datei |

## Preise werden nicht bestätigt

Bis 2026-09-24 gab es auf `Buchreihen` die Spalten `geprüfter Preis`, `Kürzel`
und `Datum` und in der Verlags-Ansicht die Knöpfe „prüfen" und „Preise
bestätigen". Sie sind entfernt: der Preis gilt, wie er in IServ steht. Übrig
ist die Spalte `Bemerkung` je Buch.

## Die Angaben der Buchreihe ändern

Seit 2026-09-24 lassen sich Titel, Verlag, Neupreis und Leihgebühr eines
Buchs im Planungsmenü ändern, im Block „Buchreihe“ vor Einführung und
Ausmusterung. Der Block ist dem IServ-Dialog „Buchreihe bearbeiten“
nachgebaut. Die ISBN steht dort nur zum Lesen, grau hinterlegt: sie ist der
Schlüssel des Buchs. **Gespeichert wird in dieser Datei, nicht in IServ**: das
Dashboard bleibt dort nur-lesend.

Von 2026-09-25 bis 2026-10-10 gehörte auch „Leihbar“ dazu, als Häkchen unter
den Preisen. Seitdem steht es je Zeile (siehe „Leihbar je Fach und Jahrgang“).

* **Die Eingabe gilt, wie sie ist.** Auf `Buchreihen` steht der eingegebene
  Wert, ohne Kommentar. Ein leerer Preis ist leer.
* **IServ nennt der Vergleich, nicht die Datei.** Weicht IServ ab, markiert
  die Seite die Zelle gelb, und im Menü steht klein darunter „in IServ: …“ -
  beides live beim Öffnen gerechnet (`app/buecherlisten.py`).
* **Die Werte wirken überall.** Die Seiten zeigen ohnehin die Datei. Für das
  PDF legt `wende_korrekturen_an` in `../core/daten.py` die Werte der Datei
  auf die Rohdaten jeder Bücherliste, für jedes Buch, das die Datei kennt.

Bis 2026-09-25 trug eine im Menü geänderte Zelle den IServ-Wert als
Kommentar („in IServ: 22,50 €“), nur diese Zellen wirkten im PDF, und ein
leerer Preis hieß „wie in IServ“. Ein alter Kommentar wird nicht mehr gelesen
und fällt beim nächsten Speichern weg.

Fächer und Jahrgänge, die IServ im selben Dialog führt, lassen sich hier nicht
ändern: sie kommen aus den Bücherlisten, nicht aus der Buchreihe.

Die Datei gilt je Schuljahr. Eine neue Datei für das nächste Schuljahr bringt
die geänderten Angaben des Vorjahrs **nicht** mit (`docs/roadmap.md`).

## Leihbar je Fach und Jahrgang

Seit 2026-10-10 steht „leihbar“ nicht mehr je Buchreihe auf `Buchreihen`,
sondern je Zeile auf `Fächer & Jahrgang`, direkt hinter `Jahrgang`. So führt
es auch IServ: `borrowable` gehört zum Eintrag einer Jahrgangsliste, nicht
zur Buchreihe. Ein Buch kann in Jahrgang 7 leihbar und in Jahrgang 8 ein
Kaufbuch sein.

Im Planungsmenü ist es die Spalte „Leihbar“ der Tabelle „Einführung und
Ausmusterung“. Umgeschaltet wird so (`leihbarSchritt` in
`app/static/buchplanung.js`, sichtbar vor dem Speichern):

* **Die Zeile galt schon vor diesem Schuljahr** (keine Einführung oder eine
  ältere): sie bleibt, wie sie war, bekommt aber die Ausmusterung nach dem
  Vorjahr, und ihr Häkchen wird grau. Darunter beginnt eine neue Zeile mit
  Einführung = Schuljahr der Datei, dem umgeschalteten Häkchen und der
  bisherigen Ausmusterung.
* **Klick auf das Häkchen der neuen Zeile**, solange darüber die
  Vorgängerin steht: der Wechsel wird zurückgenommen - die neue Zeile fällt
  weg, die alte bekommt ihre Ausmusterung zurück (meist leer).
* **Sonst** (eine Zeile ab diesem Schuljahr ohne Vorgängerin, eine künftige
  oder neue): nur das Häkchen wechselt.
* Eine **ausgemusterte** Zeile hat ein graues Häkchen und lässt sich nicht
  umschalten.

Ein Jahrgang hat damit mehrere Zeilen, unterschieden an der Einführung. Ihre
Zeiträume dürfen sich nicht überschneiden (`_pruefe_zeitraeume`); das prüft
der Server auch für Eintragungen ohne das Menü. Welche Zeile das Menü meint,
sagt `bisher_ab` (die Einführung beim Öffnen) bzw. `neu`. Für Status, Zusatz
„(ab …)“/„(bis …)“ und Vergleich zählt die Zeile, die dieses Schuljahr wirkt
(`massgebliche_zeile`).

**Vor jedem Speichern** (jede Eintragung und der Abgleich, `app/buchplanung.py`)
verbindet `verbinde_fortlaufende` zwei Zeilen eines Jahrgangs, die lückenlos
aneinander anschließen (ausgemustert nach X, eingeführt ab X+1) und gleich
leihbar sind: das ist kein Wechsel, sondern ein Buch, das durchgehend im
Regal steht. Gespeichert wird eine fortlaufende Zeile mit der Einführung der
früheren und der Ausmusterung der späteren; die beiden Anträge zum Wechsel
fallen weg, Bemerkungen und Begründungen bleiben. Ist „leihbar“ verschieden
oder liegt ein Jahr dazwischen, bleiben es zwei Zeilen.

Ein Wechsel ist eine Ausmusterung und eine Einführung - beide stehen als
Antrag auf der Änderungsliste, „ganz neu“ oder „ganz weg“ ist das Buch dabei
nicht (`verbleib_der_buecher`). Die Bücherlisten-Seiten zeigen ein halbes
Häkchen, wenn ein Buch in den Jahrgängen einer Zeile teils leihbar ist; der
Vergleich mit IServ geht je Paar (`leihbar_anders`), und das PDF bekommt
„leihbar“ je Jahrgang (`korrekturen_fuer_iserv`). Eine Rücklage ist möglich,
sobald irgendeine Zeile des Buchs leihbar ist.

Eine ältere Datei (mit `leihbar` auf `Buchreihen`) wird gelesen, als stünde
der Wert in jeder Zeile des Buchs, und beim nächsten Speichern umgestellt.

## Ein Buch hinzufügen

Unter der Fach-Liste steht „+ Buch hinzufügen“: dasselbe Menü, aber die ISBN
ist frei. ISBN und Titel schlagen die Bücher der Datei vor, die zu diesem Fach
noch nicht gehören. `fuege_buch_hinzu` nimmt das Buch über seine Jahrgänge auf,
und jeder Jahrgang braucht ein Schuljahr der Einführung, weil eine leere
Planungszeile verschwindet.

* **Bekannte ISBN** (anderes Fach, Vorjahr): Es bleibt dasselbe Buch. Weicht
  die Buchreihe ab, gilt die Eingabe wie oben.
* **Neue ISBN**: Sie muss eine gültige ISBN-10 oder -13 sein und wird als
  ISBN-13 gespeichert. Das Buch steht dann nur in der Datei. Der Abgleich
  behält es, solange es einen Jahrgang hat. Führt IServ die ISBN selbst,
  bleiben seine Werte und die Planung die der Datei, und Abweichungen zu IServ
  werden markiert. Den Hinweis „nicht in IServ“ auf den Seiten prüft das
  Dashboard live.
* **Keine ISBN** (seit 2026-10-30): Das Buch kommt erst kurz vor den Ferien,
  und noch kennt niemand seine ISBN. Es bekommt einen Platzhalter
  (`OHNE-ISBN-1`, `-2`, …), der nie eine echte ISBN sein kann, und steht
  überall als „ISBN folgt“. In seinem Menü ist das ISBN-Feld dann offen:
  dort eingetragen, prüft `ersetze_isbn` sie wie eine neue ISBN, lehnt eine
  ab, die schon zu einem Buch der Datei gehört, und zieht Jahrgänge,
  Anträge, Bestätigung, Rücklagen und Bemerkung auf die echte ISBN um. Eine
  echte ISBN lässt sich so nicht ändern.

Werden im Menü alle Jahrgänge eines Buchs entfernt, fällt es aus der Datei -
das gilt für jedes Buch ohne Jahrgang. Ein Buch aus IServ trifft das nur, wenn
all seine Jahrgänge eine Einführung tragen; eingeführte lassen sich im Menü
nicht entfernen.

Die Fach-Seite zeigt solche Bücher in ihrer Liste, weil sie aus der Datei
kommt (`gruppen_nach_fach_aus_datei` in `app/buecherlisten.py`); ein erst
künftig eingeführtes Buch steht dort mit „(ab …)“. Das PDF bleibt beim Stand
aus IServ.

## Aufbau des Pakets

| Modul | Inhalt |
|-------|--------|
| `modelle.py` | die Begriffe und die gerechneten Status |
| `aenderungen.py` | die Änderungsliste: Anträge, Abschnitte, Reihenfolge |
| `mappe.py` | die Arbeitsmappe lesen und schreiben (openpyxl) |
| `laden.py` | beide Schuljahre aus IServ, über `../core/daten.py` |
| `abgleich.py` | zusammenführen und die einzelnen Eintragungen |
| `vergleich.py` | die Datei mit IServ vergleichen, je Buch |

Kein HTTP, keine Einstellungen, keine Sperren — das steht im Dashboard
(`app/buchplanung.py`, `app/api/buchplanung.py`). Eingetragen wird in den
Bücherlisten-Seiten selbst, nicht auf einem eigenen Reiter.
