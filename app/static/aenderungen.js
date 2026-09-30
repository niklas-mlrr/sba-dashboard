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

  // Je Buch ein <tbody>; Titel, Verlag und ISBN stehen als verbundene Zellen
  // (.buch-zelle) vorn in seiner ersten Zeile. Fällt die weg, wandern sie in
  // die erste sichtbare, und rowspan zählt nur die sichtbaren Zeilen - sonst
  // verschöbe sich jede Zeile darunter um drei Spalten.
  function wendeAn() {
    if (!tabelle) return;
    for (const buch of tabelle.tBodies) {
      const zeilen = Array.from(buch.rows);
      for (const zeile of zeilen) {
        zeile.hidden = Boolean((filter.status && zeile.dataset.status !== filter.status)
          || (filter.art && zeile.dataset.antrag !== filter.art));
      }
      const sichtbar = zeilen.filter((zeile) => !zeile.hidden);
      buch.hidden = sichtbar.length === 0;
      if (!sichtbar.length) continue;
      const zellen = Array.from(buch.querySelectorAll(".buch-zelle"));
      sichtbar[0].prepend(...zellen);
      for (const zelle of zellen) zelle.rowSpan = sichtbar.length;
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
