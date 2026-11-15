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
//    schon vorn steht, kehrt beim Klick ihre Richtung um; eine, die weiter
//    hinten stand, behält ihre letzte Richtung; eine neue beginnt aufsteigend.
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
// Überschrift ("text", "zahl", "isbn" oder "liste"), `data-wert` an der Zelle, wo die
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
// Sortierung sie auch innerhalb des Buches - nach Leihbar und Jahrgang in der
// Reihenfolge und Richtung, die beide in den Sortierebenen haben (Entscheidung
// 2026-11-06; bis dahin entschied nur die vordere, bei Gleichstand immer
// leihbar zuerst). Ohne eigene Ebene zählt Leihbar aufsteigend (leihbar
// zuerst). Nach Jahrgang steht die mit den kleineren Jahrgängen zuerst
// (absteigend umgekehrt). Die Teilzeilen tragen dafür `data-leihbar`
// (0 leihbar, 1 Kaufbuch) und `data-jahrgaenge`.
//
// Danach die Jahrgänge in jeder Zelle (`.jahrgangswert` mit `data-jahrgang`):
// sie folgen der Richtung der Jahrgangsebene, absteigend also „9, 7, 5“
// (Entscheidung 2026-11-06). Jeder Wert trägt `data-farben`, seine
// Schriftfarben in Lesefolge; der Strich vorn folgt den Farben in der
// Reihenfolge, in der man sie nun liest, und wird bei jedem Klick neu gesetzt.

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

// Eine ISBN als Zahl: die Ziffern, ein „X“ am Ende zählt als 10 (Entscheidung
// 2026-11-04). Ein Platzhalter ohne ISBN hat keinen Wert und steht am Ende.
// 13 Ziffern liegen weit unter 2^53, Number rechnet sie also exakt.
function sortierIsbn(text) {
  const ziffern = text.replace(/[-\s]/g, "").toUpperCase();
  if (!/^\d*X?$/.test(ziffern) || ziffern === "" || ziffern === "X") return null;
  return ziffern.endsWith("X") ? Number(ziffern.slice(0, -1)) * 10 + 10 : Number(ziffern);
}

function sortierSchluessel(roh, art) {
  const text = roh.trim();
  if (art === "liste") return sortierZahlen(text);
  if (text === "") return null;
  if (art === "isbn") return sortierIsbn(text);
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
  } else if (art === "zahl" || art === "isbn") {
    folge = links < rechts ? -1 : links > rechts ? 1 : 0;
  } else {
    folge = sortierTextVergleich(links, rechts);
  }
  return absteigend ? -folge : folge;
}

// Die Ebenen nach einem Klick auf die Spalte `index`: sie rückt nach vorn,
// alle anderen um eine nach hinten, jede mit ihrer Richtung. War sie schon
// vorn, kehrt sich ihre Richtung um; stand sie weiter hinten, behält sie ihre
// letzte Richtung (Entscheidung 2026-11-04); war sie noch keine Ebene, beginnt
// sie aufsteigend.
function sortierNeueEbenen(ebenen, index, art) {
  const vorn = ebenen[0];
  const bisher = ebenen.find((ebene) => ebene.index === index);
  const absteigend = vorn !== undefined && vorn.index === index
    ? !vorn.absteigend : bisher !== undefined && bisher.absteigend;
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
// `teile` sind { leihbar: 0|1, jahrgaenge: [..] }, `kriterien` die Ebenen
// Leihbar und Jahrgang in ihrer Reihenfolge: [{ art: "jahrgang" | "leihbar",
// absteigend }, …]. Fehlt eine, zählt sie zuletzt aufsteigend.
function sortierTeilzeilenFolge(teile, kriterien) {
  const alle = [...kriterien];
  for (const art of ["leihbar", "jahrgang"]) {
    if (!alle.some((kriterium) => kriterium.art === art)) alle.push({ art, absteigend: false });
  }
  const reihenfolge = teile.map((_, i) => i);
  reihenfolge.sort((a, b) => {
    for (const { art, absteigend } of alle) {
      const folge = art === "leihbar" ? teile[a].leihbar - teile[b].leihbar
        : sortierListenVergleich(teile[a].jahrgaenge, teile[b].jahrgaenge);
      if (folge !== 0) return absteigend ? -folge : folge;
    }
    return a - b;
  });
  return reihenfolge;
}

// Die Reihenfolge der Jahrgänge einer Zelle: ihre Indizes, aufsteigend oder
// absteigend nach der Zahl, bei Gleichstand wie sie standen.
function sortierWerteFolge(jahrgaenge, absteigend) {
  const reihenfolge = jahrgaenge.map((_, i) => i);
  reihenfolge.sort((a, b) => {
    const folge = jahrgaenge[a] - jahrgaenge[b];
    return (absteigend ? -folge : folge) || a - b;
  });
  return reihenfolge;
}

// Der Strich vorn als CSS-Wert aus den Farben der Werte in Lesefolge (je Wert
// eine Liste): ein gleich hoher Abschnitt je vorkommender Farbe (wie
// Markierung.strich_stil).
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
  module.exports = { sortierIsbn, sortierListenVergleich, sortierNeueEbenen, sortierNachEbenen,
                     sortierSchluessel, sortierVergleich, sortierTeilzeilenFolge,
                     sortierWerteFolge, sortierStrichStil };
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

    // Innerhalb jedes Buches: die Teilzeilen nach Leihbar und Jahrgang, die
    // Jahrgänge jeder Zelle nach der Jahrgangsebene - und der Strich vorn neu,
    // in der Lesefolge, die daraus entsteht.
    function ordneTeilzeilen(tabelle, folge) {
      const koepfe = Array.from(tabelle.tHead.rows[0].cells);
      const jahrgangIndex = koepfe.findIndex((kopf) => kopf.dataset.teilspalte === "jahrgang");
      if (jahrgangIndex < 0) return;
      const kriterien = folge
        .filter((ebene) => koepfe[ebene.index].dataset.teilspalte)
        .map((ebene) => ({ art: koepfe[ebene.index].dataset.teilspalte, absteigend: ebene.absteigend }));
      const jahrgang = kriterien.find((kriterium) => kriterium.art === "jahrgang");
      const absteigend = jahrgang !== undefined && jahrgang.absteigend;
      for (const zeile of tabelle.tBodies[0].rows) {
        const zelle = zeile.cells[jahrgangIndex];
        if (!zelle) continue;
        const zellen = Array.from(zeile.querySelectorAll(":scope > td.teilzeilen"));
        const teile = Array.from(zelle.querySelectorAll(":scope > .teilzeile"));
        if (zellen.length > 0 && teile.length > 1) {
          const reihenfolge = sortierTeilzeilenFolge(teile.map((teil) => ({
            leihbar: Number(teil.dataset.leihbar),
            jahrgaenge: sortierZahlen(teil.dataset.jahrgaenge ?? ""),
          })), kriterien);
          for (const andere of zellen) {
            const jede = Array.from(andere.querySelectorAll(":scope > .teilzeile"));
            for (const i of reihenfolge) andere.appendChild(jede[i]);
          }
        }
        for (const liste of zelle.querySelectorAll(".jahrgangswerte")) {
          const werte = Array.from(liste.querySelectorAll(":scope > .jahrgangswert"));
          const reihenfolge = sortierWerteFolge(
            werte.map((wert) => Number(wert.dataset.jahrgang)), absteigend);
          liste.replaceChildren();
          reihenfolge.forEach((i, stelle) => {
            if (stelle > 0) liste.append(", ");
            liste.append(werte[i]);
          });
        }
        if (!zeile.classList.contains("strich")) continue;
        const stil = sortierStrichStil(Array.from(zelle.querySelectorAll(".jahrgangswert"))
          .map((wert) => (wert.dataset.farben ?? "").split(" ").filter(Boolean)));
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
