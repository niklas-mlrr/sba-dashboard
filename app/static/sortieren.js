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
// "liste" ist die Spalte Jahrgang der Fach-Ansicht: `data-wert="5,6,7"` nennt
// alle Jahrgänge, die in der Zeile stehen - egal, was mit ihnen geplant ist,
// leihbar oder nicht. Verglichen wird Zahl für Zahl: der kleinste gegen den
// kleinsten, bei Gleichstand der zweitkleinste gegen den zweitkleinsten. Wer
// keinen zweiten hat, steht vor einem, der einen hat.
//
// Hat ein Buch zwei Teilzeilen (leihbar und Kaufbuch), ordnet dieselbe
// Sortierung sie auch innerhalb des Buches - nach der Spalte, die von Leihbar
// und Jahrgang vorn steht: nach Jahrgang die mit den kleineren Jahrgängen
// zuerst (absteigend umgekehrt), nach Leihbar die leihbare zuerst. Die
// Teilzeilen tragen dafür `data-leihbar` (0 leihbar, 1 Kaufbuch),
// `data-jahrgaenge` und `data-farben` (für den Strich vorn, der den Farben
// in der Reihenfolge folgt, in der man sie liest).

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

function sortierSchluessel(roh, art) {
  const text = roh.trim();
  if (art === "liste") return sortierZahlen(text);
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
    folge = sortierListenVergleich(links, rechts);
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

// Die Reihenfolge der Teilzeilen eines Buches: ihre Indizes, wie sie stehen sollen.
// `teile` sind { leihbar: 0|1, jahrgaenge: [..] }, `kriterium` ist
// { art: "jahrgang" | "leihbar", absteigend }. Bei Gleichstand steht die
// leihbare Teilzeile zuerst, in beiden Richtungen.
function sortierTeilzeilenFolge(teile, kriterium) {
  const vorzeichen = kriterium.absteigend ? -1 : 1;
  const reihenfolge = teile.map((_, i) => i);
  reihenfolge.sort((a, b) => {
    const jahrgang = sortierListenVergleich(teile[a].jahrgaenge, teile[b].jahrgaenge);
    const leihbar = teile[a].leihbar - teile[b].leihbar;
    const erst = kriterium.art === "leihbar" ? leihbar : jahrgang;
    return vorzeichen * erst || leihbar || jahrgang || a - b;
  });
  return reihenfolge;
}

// Der Strich vorn als CSS-Wert aus den Farben der Teilzeilen in Lesefolge: ein
// gleich hoher Abschnitt je vorkommender Farbe (wie Markierung.strich_stil).
function sortierStrichStil(farbenFolge) {
  const farben = [];
  for (const teil of farbenFolge) {
    for (const farbe of teil) if (!farben.includes(farbe)) farben.push(farbe);
  }
  if (farben.length === 0) return "";
  if (farben.length === 1) return `var(--${farben[0]}-strich)`;
  const prozent = (zahl) => `${Math.round(zahl * 1000) / 1000}%`;
  return "linear-gradient(" + farben.map((farbe, i) => (
    `var(--${farbe}-strich) ${prozent((100 * i) / farben.length)} ${prozent((100 * (i + 1)) / farben.length)}`
  )).join(", ") + ")";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { sortierListenVergleich, sortierNeueEbenen, sortierNachEbenen,
                     sortierSchluessel, sortierVergleich, sortierTeilzeilenFolge,
                     sortierStrichStil };
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

    // Hat ein Buch zwei Teilzeilen, ordnet die vorderste der Spalten Leihbar
    // und Jahrgang sie auch innerhalb des Buches (und setzt den Strich vorn neu).
    function ordneTeilzeilen(tabelle, folge) {
      const koepfe = Array.from(tabelle.tHead.rows[0].cells);
      const vorn = folge.find((ebene) => koepfe[ebene.index].dataset.teilspalte);
      const jahrgangIndex = koepfe.findIndex((kopf) => kopf.dataset.teilspalte === "jahrgang");
      if (!vorn || jahrgangIndex < 0) return;
      const kriterium = { art: koepfe[vorn.index].dataset.teilspalte, absteigend: vorn.absteigend };
      for (const zeile of tabelle.tBodies[0].rows) {
        const zellen = Array.from(zeile.querySelectorAll(":scope > td.teilzeilen"));
        const teile = Array.from(zeile.cells[jahrgangIndex].querySelectorAll(":scope > .teilzeile"));
        if (zellen.length === 0 || teile.length < 2) continue;
        const reihenfolge = sortierTeilzeilenFolge(teile.map((teil) => ({
          leihbar: Number(teil.dataset.leihbar),
          jahrgaenge: sortierZahlen(teil.dataset.jahrgaenge ?? ""),
        })), kriterium);
        for (const zelle of zellen) {
          const jede = Array.from(zelle.querySelectorAll(":scope > .teilzeile"));
          for (const i of reihenfolge) zelle.appendChild(jede[i]);
        }
        const stil = sortierStrichStil(reihenfolge.map(
          (i) => (teile[i].dataset.farben ?? "").split(" ").filter(Boolean)));
        if (stil) zeile.style.setProperty("--strich", stil);
      }
      // Die Teilzeilen sind neu gestapelt: ihre Höhen neu angleichen (buchplanung.js).
      if (typeof gleicheTeilzeilenAn === "function") gleicheTeilzeilenAn();
    }

    function ordne(tabelle) {
      const koerper = tabelle.tBodies[0];
      if (ebenen.has(tabelle)) {
        const folge = ebenen.get(tabelle);
        const zeilen = sortierNachEbenen(ausgang.get(tabelle), folge,
                                         (zeile, ebene) => schluessel(zeile.cells[ebene.index], ebene.art));
        for (const zeile of zeilen) koerper.appendChild(zeile);
        ordneTeilzeilen(tabelle, folge);
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
