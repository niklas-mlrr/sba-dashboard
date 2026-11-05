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
| `Fächer & Jahrgang` | (ISBN, Fach, Jahrgang, Einführung) | leihbar, Einführung, Ausmusterung nach Schuljahr, je Antrag Entscheidung/Signatur/Datum, Begründung, Fachlistenbestätigung Kürzel/Datum, Bemerkung |
| `Rücklage` | (ISBN, Fach) | Anzahl, Kürzel, Datum, Status, Signatur, Bemerkung |
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
  nicht), **rot** eine Ausmusterung (in IServ noch, laut Datei nicht mehr).
  Die Zeile hat vorn einen
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
eingetragener Wert bleibt. Die Fach-Seite zeigt diese Jahrgänge in der
Bücherliste selbst, rot und durchgestrichen (siehe „Nach dem Vorjahr
ausgemustert“ unter „Farben der Fach-Ansicht“).

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
| `… Signatur`, `… Datum` | wer wann entschieden hat (bis 2026-11-04 `… Kürzel`) |
| `Begründung` | Freitext, **eine** für beide Anträge der Zeile |

* **Entschieden wird mit Signatur.** Die Signatur ist der IServ-Name dessen,
  der angemeldet ist, das Datum ist heute - beides kommt nicht aus dem Browser
  (`api_antrag`). „Zurücksetzen“ macht den Antrag wieder offen. Eine ältere
  Datei mit `… Kürzel` wird gelesen und bekommt beim nächsten Speichern die
  neuen Überschriften (`_ALTE_KOEPFE` in `mappe.py`), ebenso `Kürzel`/`Datum`
  der Fachkonferenzleitung, die seitdem `Fachlistenbestätigung Kürzel`/`…
  Datum` heißen. `Rücklage` hat eine Spalte `Signatur` für den, der den Status
  ändert; gesetzt wird sie noch nicht, was dort steht, bleibt.
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

Seit 2026-10-31 zeigt die Bücherliste eines Fachs Planung und IServ-Abgleich
zugleich (`farben.py`, ersetzt die Regeln vom 2026-10-30; am selben Tag
nachgeschärft). Jedes Mittel hat eine Bedeutung; Verlag und Jahrgang sollen
folgen und vergleichen bis dahin weiter wie oben beschrieben. „Dieses
Schuljahr“ ist das ausgewählte - vorerst das laufende (`stand.schuljahr`),
später in den Einstellungen wählbar.

| Mittel | zeigt | blau | rot | gelb |
|--------|-------|------|-----|------|
| Schrift (je Wert) | Planung, das nächste Ereignis, bis IServ es umgesetzt hat | Einführung zu diesem Schuljahr oder später | Ausmusterung nach dem Vorjahr oder später; durchgestrichen nur, wenn nach dem Vorjahr | — (grau: es gäbe das Buch nur wegen abgelehnter Einführungen) |
| Markierung (helle Hinterlegung, Strich darunter) | IServ, nur was dieses Schuljahr gilt | fehlt in der Bücherliste (je Eintrag, Strich unten) und/oder an der Buchreihe (Strich oben) | steht in der Bücherliste noch (Strich unten); geht die Buchreihe ganz, auch oben | Titel, Verlag, Preise lauten dort anders („Bisher: …“ im Tooltip) |
| Hintergrund | Ganzes, über alle Fächer, nur gezeigte Einträge | Zeile: jeder Jahrgang neu; Teilzeile: jeder Jahrgang mit diesem „leihbar“ neu | dasselbe für „geht“, und danach kommt keine Einführung (Zeile: jede, Teilzeile: mit ihrem „leihbar“) | — |
| Strich vorn | Fach: die Schriftfarben der Zeile | ein Abschnitt für Blau | ein Abschnitt für Rot (Grau: abgelehnter Antrag) | zweiter Strich rechts daneben, wenn ein Feld abweicht |

**Strich vorn:** ein gleich hoher Abschnitt je **vorkommender Farbe** (blau,
grau, rot), in der Reihenfolge, in der die Farben beim Lesen auftauchen:
Teilzeile für Teilzeile in der angezeigten Reihenfolge, Jahrgang für Jahrgang aufsteigend,
je Jahrgang erst die Jahrgangszahl, dann die Jahreszahlen des Zusatzes
(`Markierung.strich_planung`, `strich_stil()`). Grau hat eine graue
Jahrgangszahl oder eine abgelehnte Jahreszahl; ein
offener Antrag färbt den Strich nicht. Die IServ-Markierungen gehen nicht in
den Strich ein.

**Mit IServ verglichen** wird nur, was in diesem Schuljahr gilt (eingeführt zu
diesem Schuljahr oder vorher, ausgemustert nach diesem oder später): eine
Einführung „ab 2027/2028“ ist blau geschrieben, aber nicht markiert; eine
Ausmusterung nach diesem Schuljahr oder später ist rot geschrieben, IServ muss
den Jahrgang aber noch führen.

**Markiert wird gegen den entschiedenen Stand** (Entscheidung 2026-11-05,
ersetzt die vom 2026-11-04, nach der ein Jahrgang mit offenem Antrag gar nicht
markiert wurde): solange die **Ausmusterung** nach dem Vorjahr nicht genehmigt
ist, **läuft das Buch noch** - führt IServ den Jahrgang, ist nichts markiert,
hat IServ ihn schon entfernt, ist er blau. Solange die **Einführung** zu diesem
Schuljahr nicht genehmigt ist, ist das Buch **noch nicht eingeführt** - fehlt
es in IServ, ist nichts markiert, führt IServ es schon, ist es rot; plant die
Datei die Buchreihe nur so, ist die ganze Zeile rot. Abgelehnt gilt ein Antrag
nie: eine abgelehnte Ausmusterung lässt das Buch bleiben, eine abgelehnte
Einführung zählt nicht. Anträge zu anderen Schuljahren ändern nichts (frühere
Zeilen gelten als entschieden, spätere werden noch nicht verglichen). Die
Fach-Ansicht vergleicht dafür mit `entschiedener_stand` (`farben.py`); die
Schrift (Farbe, Durchstreichen) und der Zusatz zeigen weiter die Planung mit
ihren Anträgen.

**Buchreihe:** In IServ muss die Buchreihe einem Jahrgang zugewiesen sein,
bevor das Buch in dessen Bücherliste kommt. Fehlt an ihr ein Jahrgang, den ein
Fach dieses Schuljahr führt, ist der Jahrgang blau markiert, mit einem Strich
**oben** (`Abweichung.buchreihe_fehlt`, `Wert.reihe_fehlt`); fehlt er in der
Bücherliste, mit dem Strich **unten** (`Wert.liste_fehlt`) - beides zugleich
geht (Entscheidung 2026-11-04). Zu viele Jahrgänge an der Buchreihe schaden
nicht und werden nie angezeigt - außer die Buchreihe geht ganz (Entscheidung
2026-11-05): führt sie dieses Schuljahr nach dem entschiedenen Stand kein
Fach mehr und ist keine Einführung offen oder genehmigt, hat jeder rot
markierte Jahrgang auch den Strich **oben** („Jahrgang N ist aus der Buchreihe
zu entfernen“, `Wert.reihe_weg`); sonst hat Rot nur den Strich unten. Die Zuweisung kommt aus
`series_data.gradesFlat` der Bücherlisten; für Bücher ohne sie (etwa in keiner
Liste) holt die Fach-Ansicht einmal das Inventar (`client.series.get_all()`);
ist es nicht zu bekommen, wird die Buchreihe nicht verglichen.

**ISBN nur auf einer Seite:** Steht das Buch dieses Schuljahr in keiner
IServ-Liste und **gibt es die Buchreihe im Inventar nicht**
(`Abweichung.buchreihe_angelegt`), ist jedes Feld der Zeile blau markiert und
jeder Jahrgang hat beide Striche. Gibt es die Buchreihe schon, ist die Zeile
nicht ganz markiert: die Jahrgänge zeigen, was fehlt, und was die Datei bei
Titel, Verlag und Preisen anders führt als die Buchreihe, ist gelb
(Variante B, Entscheidung 2026-11-04). Ist das Inventar nicht zu bekommen,
gilt die Zeile als neu. Steht die ISBN nur in IServ, ist jedes Feld rot, die
Jahrgänge je Jahrgang. Führt nur IServ es in einem Fach, ist es aber anderswo
geplant, sind nur die Jahrgänge rot markiert. Den Zusatz **„nur in IServ“**
(ohne Menü) trägt der Titel nur, wenn die ISBN in einer IServ-Bücherliste
steht und **in der ganzen Datei nicht** (Entscheidung 2026-11-04). Ein Buch,
das die Datei kennt - etwa nach dem Vorjahr ausgemustert, IServ führt es noch
-, ist rot markiert, hat aber keinen Zusatz und behält sein Menü.

**Tooltips** (Entscheidung 2026-11-04; „Buchreihe“ steht wörtlich da, nicht
der Titel): die Zeile „Buchreihe bearbeiten“. Titel, Verlag, ISBN und Preise
(Rücklagen werden nie markiert, Entscheidung 2026-11-05): gelb „Bisher: <IServ-Wert>“, blau „Buchreihe muss in IServ angelegt
werden“, rot mit „nur in IServ“ „Buchreihe existiert nur in IServ“, rot ohne
„Buchreihe wird ausgemustert“ - oder, wenn die Datei sie nur mit einer noch
nicht genehmigten Einführung plant, „IServ führt Buchreihe bereits, obwohl die
Einführung noch nicht genehmigt ist.“ (Entscheidung 2026-11-05,
`Markierung.einfuehrung_offen`). Eine entschiedene Jahreszahl im Zusatz:
„<Einführung/Ausmusterung> der Buchreihe in Jahrgang N <genehmigt/abgelehnt>“,
darunter „am …“ und „durch <Signatur>“; eine offene hat keinen. Der Jahrgang
(`farben.py`: `_schrift_hinweis`, `_iserv_hinweise`), je Aussage eine Zeile,
erst die Schrift, dann IServ:

| was | Tooltip |
|-----|---------|
| rot durchgestrichen | „Ausmusterung der Buchreihe in Jahrgang N[ beantragt]“ |
| blau | „Einführung der Buchreihe in Jahrgang N[ für ESJ][ beantragt]“ - „für ESJ“ nur, wenn ESJ nach dem ausgewählten Schuljahr liegt |
| rot | „Ausmusterung der Buchreihe in Jahrgang N nach ASJ[ beantragt]“ |
| grau | „Einführung der Buchreihe in Jahrgang N[ für ESJ] abgelehnt“, „am …“, „durch …“ - die zeitlich nächste abgelehnte |
| Zeile ganz blau | „Buchreihe muss in IServ angelegt werden“ |
| blau oben | „Jahrgang N ist der Buchreihe hinzuzufügen“ |
| blau unten | „Buchreihe ist Bücherliste für Jahrgang N hinzuzufügen“ |
| rot markiert | „Buchreihe ist aus Bücherliste für Jahrgang N in IServ zu entfernen“ |
| rot oben (Buchreihe geht ganz) | dazu „Jahrgang N ist aus der Buchreihe zu entfernen“ |
| rot in der einen, blau unten in der anderen Teilzeile | statt aller drei: „Buchreihe ist in Bücherliste für Jahrgang N auf <leihbar/nicht leihbar> zu setzen“ |

„beantragt“ hängt an, solange der Antrag, der die Farbe gibt, offen ist.

**Verkehrt herum:** Eine Ausmusterung vor der Einführung (ASJ < ESJ) lässt
sich im Menü nicht eintragen. Steht sie in Excel, nennt die Seite die Stellen
beim Laden im Fehlermenü (`verkehrte_zeitraeume` in `app/planungsansicht.py`).

**Sortierung der Fach-Ansicht** (`static/sortieren.js`, Tabellen mit
`data-ebenen`): eine Liste von Sortierebenen, zu Beginn Jahrgang aufsteigend,
dann ISBN aufsteigend. Ein Klick auf eine Überschrift setzt ihre Spalte an die
erste Stelle, die übrigen rücken um eine nach hinten und behalten ihre Richtung;
die vorderste kehrt beim Klick ihre Richtung um, eine weiter hinten behält
ihre letzte (Entscheidung 2026-11-04). Titel und Verlag sortieren
alphabetisch, ISBN, Neupreis und Leihgebühr nach Zahl (bei der ISBN zählt ein
„X“ am Ende als 10, ein Platzhalter steht am Ende), „Leihbar“ aufsteigend
als nur leihbar, beides, nur Kaufbuch. „Jahrgang“ nimmt von jedem Buch **alle
Jahrgänge, die in der Zeile stehen** - leihbar oder nicht, egal was mit ihnen
geplant ist - und vergleicht Zahl für Zahl: der kleinste gegen den kleinsten,
bei Gleichstand der zweitkleinste; wer keinen zweiten hat, steht vor einem mit
zweitem.

**Zwei Teilzeilen im Buch** (leihbar und Kaufbuch) ordnet dieselbe Sortierung
auch innerhalb des Buches, nach der Spalte, die von Leihbar und Jahrgang vorn
steht: nach Jahrgang die Teilzeile mit den kleineren Jahrgängen zuerst (nach
derselben Regel, absteigend umgekehrt), nach Leihbar die leihbare (absteigend
das Kaufbuch); bei Gleichstand leihbar zuerst. Der Server liefert sie schon so
(`Markierung.teilzeilen`, Jahrgang aufsteigend), das Skript ordnet sie bei jedem
Klick neu - Leihbar- und Jahrgang-Zelle gleich - und setzt den Strich vorn nach
`data-farben` der Teilzeilen in der neuen Reihenfolge.

**Zusatz hinter dem Jahrgang** (`zusatz.py`, Entscheidung 2026-10-31): je
Planungszeile des Eintrags (Fach, Jahrgang, „leihbar“) ein Ergebnis in
Klammern, mehrere mit „, “ getrennt (bis 2026-11-04 „; “). Mit dem ausgewählten Schuljahr SJ, dem
Einführungsjahr ESJ und dem Ausmusterungsjahr ASJ der Zeile:

| Bedingung | Zusatz |
|-----------|--------|
| ESJ ≤ SJ ≤ ASJ (ohne ESJ: längst eingeführt) | `bis ASJ` |
| SJ < ESJ = ASJ | `ESJ` - aber `von ESJ bis ASJ`, bis **beide** Anträge genehmigt sind |
| SJ < ESJ < ASJ | `von ESJ bis ASJ` |
| SJ < ESJ, ohne ASJ | `ab ESJ` |
| sonst | nichts |

Zwei Ausnahmen, damit jeder Antrag, über den noch zu entscheiden ist (oder der
abgelehnt wurde), ein Jahr mit Kasten hat: Ist die Einführung zum **laufenden**
Schuljahr (ESJ = SJ) nicht genehmigt, steht `von ESJ bis ASJ` (ohne ASJ: `ab
ESJ`) statt `bis ASJ`. Ist die Ausmusterung **nach dem Vorjahr** (ASJ = SJ-1)
nicht genehmigt, steht `bis ASJ` statt nichts. Genehmigt, gilt wieder die
Tabelle.

An jeder Jahreszahl, deren Antrag noch offen oder abgelehnt ist, hängt ein
Kasten (`zusatzantrag` in `app.css`): ein Rahmen in der Farbe des Status (grau
offen, rot abgelehnt), unten „offen“/„abgelehnt“, oben die Art
(„Einführung“/„Ausmusterung“). Ein genehmigter Antrag hat keinen Kasten; ein
Antrag, über den nicht zu entscheiden ist (`zu_entscheidende_antraege`), auch
nicht. Der Rahmen ist 2 px dick (ganze Pixel sind scharf); die beiden kleinen
Kästen reichen bis an seine Außenkante und haben außen denselben Radius, ihre
Ecken liegen also genau auf denen des Rahmens. Zwischen zwei Kästen nach
einem Umbruch bleiben 4 px; ebenso weit steht ein Kasten von der Zeilengrenze
(bzw. der gestrichelten Linie zwischen zwei Teilzeilen) ab: Zelle und Teilzeile
mit Kasten tragen `mit-antrag` und haben dort 2 px statt 8 px Zellrand.

**Abgelehnte Anträge** gelten in der Fach-Ansicht nicht
(`ohne_abgelehnte_ausmusterungen`, `Vergleich.original`): eine abgelehnte
**Ausmusterung** lässt das Buch bleiben (der Vergleich mit IServ und die Liste
rechnen ohne sie), eine abgelehnte **Einführung** zählt für Farbe,
Durchstreichen und Vergleich nicht. Ihre Jahreszahl bleibt im Zusatz stehen,
grau, mit rotem Kasten. Gibt es das Buch in der Zeile (bzw. Teilzeile) nur
wegen abgelehnter Einführungen, also gar nicht, ist die Jahrgangszahl grau,
der Strich vorn hat dafür einen grauen Abschnitt, und die Zeile ist grau
hinterlegt (`ganz-grau`); bei einer abgelehnten Ausmusterung nie.

**Unlogisches darf gefärbt werden** (Entscheidung 2026-11-05): Es fällt nur
der abgelehnte Antrag selbst weg, alles andere zählt weiter - auch wenn es
nach der Ablehnung keinen Sinn mehr ergibt. Läuft ein Jahrgang nach einer
abgelehnten Ausmusterung weiter, ist eine Wiedereinführung danach trotzdem
blau; wird beim Wechsel die Ausmusterung als Leihbuch abgelehnt, zählt die
Einführung als Kaufbuch trotzdem. Wird eine Einführung abgelehnt, läuft das
Buch dort nicht, aber die Ausmusterung derselben Zeile färbt trotzdem: rot,
„Ausmusterung … nach ASJ[ beantragt]“, und dann nicht grau
(`_Zeilen.nur_ausmusterung`). Das richtet später das Mit-Ablehnen
zusammengehöriger Anträge (`docs/roadmap.md`).

**Das nächste Ereignis färbt, bis IServ es umgesetzt hat** (Entscheidung
2026-11-05). Nach dem Vorjahr ausgemustert und später wieder eingeführt: rot
und durchgestrichen, solange IServ den Jahrgang noch führt; führt er ihn nicht
mehr, ist die Wiedereinführung das Nächste und der Jahrgang blau. Ohne
Wiedereinführung bleibt er rot und durchgestrichen. Läuft ein Jahrgang noch
und kommt nach einer späteren Ausmusterung wieder, ist er rot, auch wenn
IServ ihn gerade nicht führt - erst die Ausmusterung, dann die
Wiedereinführung.

**Roter Hintergrund** (Entscheidung 2026-11-05), wie Blau und Grau auf drei
Ebenen, je über alle Fächer: die ganze Buchreihe, ihr Leihbuch, ihr Kaufbuch.
Rot, wenn geplant ist (offen oder genehmigt), sie bzw. ihr Leih- oder
Kaufbuch ganz auszumustern, ohne spätere Einführung:

| Ebene | rot, wenn … | eine spätere Einführung (offen oder genehmigt) im selben Fach und Jahrgang hält es auf, wenn … |
|-------|-------------|------------------------------------------------------------------------------------------------|
| Zeile (ganze Buchreihe) | jede Zahl rot | sie leihbar oder nicht ist |
| Teilzeile leihbar | jede leihbare Zahl rot | sie leihbar ist |
| Teilzeile Kaufbuch | jede nicht leihbare Zahl rot | sie nicht leihbar ist |

„Später“ heißt nach der Ausmusterung, die die Zahl rot färbt
(`_Plan.beginne`); eine abgelehnte Einführung zählt nicht. Beim Wechsel ist
die Leihbuch-Teilzeile rot hinterlegt (das Leihbuch geht ganz), die Zeile
nicht (das Buch kommt als Kaufbuch wieder).

**Einführung und Ausmusterung zugleich** (etwa eingeführt zu diesem Schuljahr,
ausgemustert nach einem späteren, oder einjährig): Der Jahrgang ist blau,
solange IServ ihn noch nicht führt - er fehlt in der Bücherliste oder an der
Buchreihe - oder er noch nicht verglichen wird (eine spätere Einführung).
Liefert der Vergleich am Jahrgang keine Differenz mehr, wird er rot (läuft aus).
Strich und Hintergrund folgen der Schrift.

„Leihbar“ hängt am Jahrgang: gefärbt und verglichen wird je **Eintrag**
(Fach, Jahrgang, leihbar; `aktive_eintraege`, `Abweichung.eintraege_fehlen` /
`eintraege_nur_iserv`). „Leihbar“ steht vor „Jahrgang“; ein Buch mit Leih- und
Kaufbuch-Jahrgängen hat in beiden Spalten zwei Teilzeilen (oben leihbar). Ein
Wechsel ist eine Ausmusterung in der einen und eine Einführung in der anderen
Teilzeile; das Häkchen wird nie gefärbt. Führt IServ einen Jahrgang mit dem
anderen Häkchen, fehlt der Eintrag dort in der einen Teilzeile und steht noch in
der anderen.

`markierung(stand, buch, abweichung, im=…, nach=…)` ist für Verlag und Jahrgang
vorbereitet: `im` wählt die Einträge der Zeile, `nach` die Wertspalte
(`jahrgang` oder `fach`); `strich("iserv")` gibt den Strich einer Ansicht mit
Schwerpunkt IServ.

**Was in der Liste eines Fachs steht** (`Vergleich.gezeigte_paare` in
`app/buecherlisten.py`, Entscheidung 2026-11-04): jedes (Fach, Jahrgang)-Paar,
das dieses Schuljahr gilt oder erst noch kommt, und jedes, das **genau nach dem
Vorjahr** ausgemustert ist - leihbar oder Kaufbuch. Ein ganz ausgemustertes
Buch steht damit rot und durchgestrichen in der Liste, mit Antragskasten,
Planungsmenü und Rücklage. Was vor dem Vorjahr endete, steht nicht mehr da;
eine abgelehnte Ausmusterung gilt nicht. Bis 2026-11-04 standen ganz
ausgemusterte Leihbücher in einer eigenen Tabelle „Ausmusterungen zu diesem
Schuljahr“ unter der Liste; die gibt es nicht mehr.

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
| `zusatz.py`, `farben.py` | Zusatz hinter dem Jahrgang und die Farben der Fach-Ansicht |

Kein HTTP, keine Einstellungen, keine Sperren — das steht im Dashboard
(`app/buchplanung.py`, `app/api/buchplanung.py`). Eingetragen wird in den
Bücherlisten-Seiten selbst, nicht auf einem eigenen Reiter.
