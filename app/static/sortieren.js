// Sortieren der Bücherlisten-Tabellen per Klick auf die Spaltenüberschrift.
//
// Erster Klick: aufsteigend, jeder weitere: Richtung umkehren. Bei gleichem
// Wert (zweimal "Mathematik") bleibt die Reihenfolge der vorigen Sortierung
// stehen - so lässt sich nach Verlag und innerhalb des Verlags nach Fach
// ordnen, indem man erst Fach und dann Verlag anklickt.
//
// Umgesetzt als KLICKVERLAUF statt als Umsortieren des gerade Angezeigten:
// jede Tabelle wird aus ihrer Ausgangsreihenfolge neu aufgebaut, indem die
// Klicks der Reihe nach mit einer stabilen Sortierung angewendet werden. Das
// ergibt für eine einzelne Tabelle genau dasselbe, lässt sich aber auf eine
// andere Tabelle ÜBERTRAGEN - das braucht die Paketansicht
// (static/paketansicht.js): die Gesamttabelle (`data-gesamt`) wendet alle
// Klicks der Seite an, eine Einzeltabelle ihre eigenen und die aus der
// Gesamttabelle. Ohne Klicks bleibt die Ausgangsreihenfolge, in der Gesamt-
// tabelle also Grundpaket und danach die Wahlbereiche.
//
// Wie in app.js liefert die Vorlage den Schlüssel: `data-sort` an der
// Überschrift ("text" oder "zahl"), `data-wert` an der Zelle, wo die Anzeige
// nicht selbst der Schlüssel ist (Preise, Daten, Häkchen). Leerer Wert
// sortiert in beiden Richtungen ans Ende.
(function () {
  // numeric: "Jahrgang 5" vor "Jahrgang 10", und "5, 6" vor "7, 8" vor "11".
  const textVergleich = new Intl.Collator("de", { numeric: true }).compare;

  function schluessel(zelle, art) {
    const roh = (zelle.dataset.wert ?? zelle.textContent).trim();
    if (roh === "") return null;
    return art === "zahl" ? Number(roh) : roh;
  }

  function vergleich({ index, art, absteigend }) {
    return (a, b) => {
      const links = schluessel(a.cells[index], art);
      const rechts = schluessel(b.cells[index], art);
      if ((links === null) !== (rechts === null)) return links === null ? 1 : -1;
      if (links === null) return 0;
      const folge = art === "zahl"
        ? (links < rechts ? -1 : links > rechts ? 1 : 0)
        : textVergleich(links, rechts);
      return absteigend ? -folge : folge;
    };
  }

  const tabellen = Array.from(document.querySelectorAll("table.sortierbar"));
  const ausgang = new Map(tabellen.map((t) => [t, Array.from(t.tBodies[0].rows)]));
  const verlauf = [];

  function gilt(klick, tabelle) {
    return tabelle.hasAttribute("data-gesamt")
      || klick.tabelle === tabelle
      || klick.tabelle.hasAttribute("data-gesamt");
  }

  function ordne(tabelle) {
    const zeilen = ausgang.get(tabelle).slice();
    let letzter = null;
    for (const klick of verlauf) {
      if (!gilt(klick, tabelle)) continue;
      zeilen.sort(vergleich(klick));
      letzter = klick;
    }
    const koerper = tabelle.tBodies[0];
    for (const zeile of zeilen) koerper.appendChild(zeile);
    const koepfe = tabelle.tHead.rows[0].cells;
    for (const kopf of koepfe) kopf.removeAttribute("aria-sort");
    if (letzter) {
      koepfe[letzter.index].setAttribute("aria-sort", letzter.absteigend ? "descending" : "ascending");
    }
  }

  for (const tabelle of tabellen) {
    tabelle.tHead.addEventListener("click", (ereignis) => {
      const kopf = ereignis.target.closest("th[data-sort]");
      if (!kopf) return;
      verlauf.push({
        tabelle,
        index: Array.from(kopf.parentNode.cells).indexOf(kopf),
        art: kopf.dataset.sort,
        absteigend: kopf.getAttribute("aria-sort") === "ascending",
      });
      for (const andere of tabellen) {
        if (andere === tabelle || gilt(verlauf[verlauf.length - 1], andere)) ordne(andere);
      }
    });
  }
})();
