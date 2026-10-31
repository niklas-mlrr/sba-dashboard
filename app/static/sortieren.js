// Sortieren der Bücherlisten-Tabellen per Klick auf die Spaltenüberschrift.
//
// Zwei Arten, je nach Tabelle:
//
// 1. SORTIEREBENEN (Tabellen der Fach-Ansicht, `data-ebenen` an der Tabelle;
//    Entscheidung 2026-10-31). Die Tabelle ist nach einer Liste von Spalten
//    sortiert: die erste Ebene zuerst, bei Gleichstand die zweite, dann die
//    dritte. Zu Beginn: Jahrgang aufsteigend, dann ISBN aufsteigend
//    (`data-ebene="1"`, `"2"` an den Überschriften). Jeder Klick auf eine
//    Überschrift setzt ihre Spalte an die erste Stelle und schiebt alle
//    anderen um eine nach hinten - jede behält ihre Richtung. Die Spalte, die
//    schon vorn steht, kehrt beim Klick ihre Richtung um; sonst beginnt sie
//    aufsteigend.
//
// 2. KLICKVERLAUF (alle anderen Tabellen). Erster Klick: aufsteigend, jeder
//    weitere: Richtung umkehren. Bei gleichem Wert (zweimal "Mathematik")
//    bleibt die Reihenfolge der vorigen Sortierung stehen - so lässt sich nach
//    Verlag und innerhalb des Verlags nach Fach ordnen, indem man erst Fach
//    und dann Verlag anklickt.
//
//    Umgesetzt als KLICKVERLAUF statt als Umsortieren des gerade Angezeigten:
//    jede Tabelle wird aus ihrer Ausgangsreihenfolge neu aufgebaut, indem die
//    Klicks der Reihe nach mit einer stabilen Sortierung angewendet werden.
//    Das ergibt für eine einzelne Tabelle genau dasselbe, lässt sich aber auf
//    eine andere Tabelle ÜBERTRAGEN - das braucht die Paketansicht
//    (static/paketansicht.js): die Gesamttabelle (`data-gesamt`) wendet alle
//    Klicks der Seite an, eine Einzeltabelle ihre eigenen und die aus der
//    Gesamttabelle. Ohne Klicks bleibt die Ausgangsreihenfolge, in der
//    Gesamttabelle also Grundpaket und danach die Wahlbereiche.
//
// Wie in app.js liefert die Vorlage den Schlüssel: `data-sort` an der
// Überschrift ("text", "zahl" oder "liste"), `data-wert` an der Zelle, wo die
// Anzeige nicht selbst der Schlüssel ist (Preise, Daten, Häkchen). Leerer Wert
// sortiert in beiden Richtungen ans Ende.
//
// "liste" ist die Spalte Jahrgang der Fach-Ansicht: `data-wert="5,6|7"` nennt
// die leihbaren Jahrgänge vor dem Strich und die nicht leihbaren dahinter. Die
// beiden Listen bleiben getrennt; verglichen wird erst die der leihbaren
// Jahrgänge, bei Gleichstand die der anderen, jede Zahl für Zahl (zweiter bei
// gleichem ersten, dann dritter …). Wo eine Liste früher endet, kommt sie
// zuerst: kein zweiter Jahrgang steht vor einem zweiten.

// numeric: "Jahrgang 5" vor "Jahrgang 10", und "5, 6" vor "7, 8" vor "11".
const sortierTextVergleich = new Intl.Collator("de", { numeric: true }).compare;

function sortierZahlen(text) {
  return text === "" ? [] : text.split(",").map(Number);
}

// Vergleicht zwei Zahlenlisten Zahl für Zahl; die kürzere zuerst, wenn sie
// der Anfang der längeren ist.
function sortierListenVergleich(links, rechts) {
  const gemeinsam = Math.min(links.length, rechts.length);
  for (let i = 0; i < gemeinsam; i += 1) {
    if (links[i] !== rechts[i]) return links[i] < rechts[i] ? -1 : 1;
  }
  return links.length === rechts.length ? 0 : links.length < rechts.length ? -1 : 1;
}

// Der Wert einer "liste"-Zelle: erst die leihbaren, dann die anderen Jahrgänge.
function sortierDoppelliste(roh) {
  const [leihbar, sonst = ""] = roh.split("|");
  return [sortierZahlen(leihbar), sortierZahlen(sonst)];
}

function sortierSchluessel(roh, art) {
  const text = roh.trim();
  if (art === "liste") return sortierDoppelliste(text);
  if (text === "") return null;
  if (art === "zahl") {
    const zahl = Number(text);
    return Number.isNaN(zahl) ? null : zahl;
  }
  return text;
}

// Vergleicht zwei Schlüssel einer Art; ohne Wert (null) immer ans Ende.
function sortierVergleich(art, absteigend, links, rechts) {
  if ((links === null) !== (rechts === null)) return links === null ? 1 : -1;
  if (links === null) return 0;
  let folge;
  if (art === "liste") {
    folge = sortierListenVergleich(links[0], rechts[0]) || sortierListenVergleich(links[1], rechts[1]);
  } else if (art === "zahl") {
    folge = links < rechts ? -1 : links > rechts ? 1 : 0;
  } else {
    folge = sortierTextVergleich(links, rechts);
  }
  return absteigend ? -folge : folge;
}

// Die Ebenen nach einem Klick auf die Spalte `index`: sie rückt nach vorn,
// alle anderen um eine nach hinten, jede mit ihrer Richtung. War sie schon
// vorn, kehrt sich ihre Richtung um; sonst beginnt sie aufsteigend.
function sortierNeueEbenen(ebenen, index, art) {
  const vorn = ebenen[0];
  const absteigend = vorn !== undefined && vorn.index === index ? !vorn.absteigend : false;
  return [{ index, art, absteigend }, ...ebenen.filter((ebene) => ebene.index !== index)];
}

// Die Zeilen, ordnet nach den Ebenen (stabil: bei Gleichstand bleibt die Reihenfolge).
// `schluessel(zeile, ebene)` liefert den Schlüssel der Zeile in dieser Ebene.
function sortierNachEbenen(zeilen, ebenen, schluessel) {
  const mitSchluessel = zeilen.map((zeile) => ({
    zeile, schluessel: ebenen.map((ebene) => schluessel(zeile, ebene)),
  }));
  mitSchluessel.sort((a, b) => {
    for (let i = 0; i < ebenen.length; i += 1) {
      const folge = sortierVergleich(ebenen[i].art, ebenen[i].absteigend,
                                     a.schluessel[i], b.schluessel[i]);
      if (folge !== 0) return folge;
    }
    return 0;
  });
  return mitSchluessel.map((eintrag) => eintrag.zeile);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { sortierListenVergleich, sortierNeueEbenen, sortierNachEbenen,
                     sortierSchluessel, sortierVergleich };
}

if (typeof document !== "undefined") {
  (function () {
    function schluessel(zelle, art) {
      return sortierSchluessel(zelle.dataset.wert ?? zelle.textContent, art);
    }

    function vergleich({ index, art, absteigend }) {
      return (a, b) => sortierVergleich(
        art, absteigend, schluessel(a.cells[index], art), schluessel(b.cells[index], art));
    }

    const tabellen = Array.from(document.querySelectorAll("table.sortierbar"));
    const ausgang = new Map(tabellen.map((t) => [t, Array.from(t.tBodies[0].rows)]));
    const verlauf = [];
    // Je Tabelle mit Sortierebenen: die Ebenen, die erste zuerst.
    const ebenen = new Map();

    function gilt(klick, tabelle) {
      return tabelle.hasAttribute("data-gesamt")
        || klick.tabelle === tabelle
        || klick.tabelle.hasAttribute("data-gesamt");
    }

    function zeigeRichtung(tabelle, kopf) {
      const koepfe = tabelle.tHead.rows[0].cells;
      for (const andere of koepfe) andere.removeAttribute("aria-sort");
      if (kopf) {
        koepfe[kopf.index].setAttribute("aria-sort", kopf.absteigend ? "descending" : "ascending");
      }
    }

    function ordne(tabelle) {
      const koerper = tabelle.tBodies[0];
      if (ebenen.has(tabelle)) {
        const folge = ebenen.get(tabelle);
        const zeilen = sortierNachEbenen(ausgang.get(tabelle), folge,
                                         (zeile, ebene) => schluessel(zeile.cells[ebene.index], ebene.art));
        for (const zeile of zeilen) koerper.appendChild(zeile);
        zeigeRichtung(tabelle, folge[0]);
        return;
      }
      const zeilen = ausgang.get(tabelle).slice();
      let letzter = null;
      for (const klick of verlauf) {
        if (!gilt(klick, tabelle)) continue;
        zeilen.sort(vergleich(klick));
        letzter = klick;
      }
      for (const zeile of zeilen) koerper.appendChild(zeile);
      zeigeRichtung(tabelle, letzter);
    }

    // Die Anfangsebenen einer Tabelle aus `data-ebene` an den Überschriften.
    function anfangsebenen(tabelle) {
      return Array.from(tabelle.tHead.rows[0].cells)
        .map((kopf, index) => ({ index, art: kopf.dataset.sort, nummer: Number(kopf.dataset.ebene) }))
        .filter((kopf) => kopf.nummer > 0)
        .sort((a, b) => a.nummer - b.nummer)
        .map(({ index, art }) => ({ index, art, absteigend: false }));
    }

    for (const tabelle of tabellen) {
      if (tabelle.hasAttribute("data-ebenen")) {
        ebenen.set(tabelle, anfangsebenen(tabelle));
        ordne(tabelle);
      }
      tabelle.tHead.addEventListener("click", (ereignis) => {
        const kopf = ereignis.target.closest("th[data-sort]");
        if (!kopf) return;
        const index = Array.from(kopf.parentNode.cells).indexOf(kopf);
        if (ebenen.has(tabelle)) {
          ebenen.set(tabelle, sortierNeueEbenen(ebenen.get(tabelle), index, kopf.dataset.sort));
          ordne(tabelle);
          return;
        }
        verlauf.push({
          tabelle,
          index,
          art: kopf.dataset.sort,
          absteigend: kopf.getAttribute("aria-sort") === "ascending",
        });
        for (const andere of tabellen) {
          if (andere === tabelle || gilt(verlauf[verlauf.length - 1], andere)) ordne(andere);
        }
      });
    }
  })();
}
