// Die Änderungsliste - was nicht gespeichert wird.
//
// Entschieden wird über buchplanung.js (data-planung="antrag"). Hier steht nur,
// was die Seite bequemer macht und nirgends ankommt:
//
//   1. Die Filter über der Tabelle blenden Zeilen nach Entscheidung und Art
//      aus. Beide gelten zugleich; "" heißt alle. Die verbundenen Zellen
//      eines Buchs gehen dabei mit.
//   2. Das Kürzel bleibt in diesem Browser stehen, damit es nicht bei jedem
//      Neuladen fehlt. Ohne Speicher (privates Fenster) ist das Feld leer.
//   3. Wer eine Begründung ändert, bekommt daneben den Knopf „Speichern“.
(function () {
  const tabelle = document.getElementById("aenderungen");
  const filter = { status: "", art: "" };

  // Je Fach ein <tbody>. Das Fach steht als verbundene Zelle (.fach-zelle)
  // vorn in seiner ersten Zeile, Titel, Verlag und ISBN (.buch-zelle) vorn in
  // der ersten Zeile jedes Buchs. Fällt eine solche Zeile weg, wandern die
  // Zellen in die erste sichtbare, und rowspan zählt nur die sichtbaren
  // Zeilen - sonst verschöbe sich jede Zeile darunter.
  //
  // Erst die Buchzellen, dann die Fachzelle voranstellen: so steht das Fach
  // immer ganz vorn, auch wenn beide in dieselbe Zeile wandern.
  function verbinde(zeilen, zellen) {
    const sichtbar = zeilen.filter((zeile) => !zeile.hidden);
    if (!sichtbar.length) return;
    sichtbar[0].prepend(...zellen);
    for (const zelle of zellen) zelle.rowSpan = sichtbar.length;
  }

  function wendeAn() {
    if (!tabelle) return;
    for (const fach of tabelle.tBodies) {
      const zeilen = Array.from(fach.rows);
      for (const zeile of zeilen) {
        zeile.hidden = Boolean((filter.status && zeile.dataset.status !== filter.status)
          || (filter.art && zeile.dataset.antrag !== filter.art));
      }
      fach.hidden = zeilen.every((zeile) => zeile.hidden);
      const buecher = new Map();
      for (const zeile of zeilen) {
        if (!buecher.has(zeile.dataset.isbn)) buecher.set(zeile.dataset.isbn, []);
        buecher.get(zeile.dataset.isbn).push(zeile);
      }
      for (const buch of buecher.values()) {
        verbinde(buch, Array.from(fach.querySelectorAll(".buch-zelle"))
          .filter((zelle) => zelle.parentElement.dataset.isbn === buch[0].dataset.isbn));
      }
      verbinde(zeilen, Array.from(fach.querySelectorAll(".fach-zelle")));
      // Der Strich über einem Buch gehört an seine erste sichtbare Zeile.
      let vorige = null;
      for (const zeile of zeilen.filter((z) => !z.hidden)) {
        zeile.classList.toggle("buch-anfang",
          vorige !== null && vorige !== zeile.dataset.isbn);
        vorige = zeile.dataset.isbn;
      }
    }
  }

  document.addEventListener("click", (ereignis) => {
    const knopf = ereignis.target.closest("[data-filter]");
    if (!knopf) return;
    const art = knopf.dataset.filter;
    filter[art] = knopf.dataset.wert;
    for (const anderer of document.querySelectorAll('[data-filter="' + art + '"]')) {
      anderer.setAttribute("aria-pressed", String(anderer === knopf));
    }
    wendeAn();
  });

  const kuerzel = document.getElementById("antrag-kuerzel");
  const SCHLUESSEL = "sba-antrag-kuerzel";
  if (kuerzel) {
    try {
      if (!kuerzel.value) kuerzel.value = localStorage.getItem(SCHLUESSEL) || "";
    } catch (fehler) { /* ohne Speicher bleibt das Feld leer */ }
    kuerzel.addEventListener("change", () => {
      try { localStorage.setItem(SCHLUESSEL, kuerzel.value.trim()); } catch (fehler) { /* s. o. */ }
    });
  }

  document.addEventListener("input", (ereignis) => {
    if (!ereignis.target.matches('[data-antrag-feld="begruendung"]')) return;
    const knopf = ereignis.target.closest("td").querySelector("[data-antrag-speichern]");
    if (knopf) knopf.hidden = false;
  });
})();
