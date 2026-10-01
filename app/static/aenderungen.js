// Die Änderungsliste - was nicht gespeichert wird.
//
// Entschieden wird über buchplanung.js (das Buchmenü, data-planung="antrag").
// Hier steht nur, was die Seite bequemer macht und nirgends ankommt:
//
//   1. Die Filter über der Tabelle: nach Entscheidung, nach Art und danach,
//      ob eine Ersetzung beide Seiten hat. Alle gelten zugleich; "" heißt alle.
//      Ein Buch, das nicht passt, wird gedimmt, nicht ausgeblendet - sonst
//      stimmten die verbundenen Zellen (rowspan) nicht mehr. Eine Ersetzung
//      ohne passendes Buch verschwindet ganz, ein Fach ohne sichtbare
//      Ersetzung ebenso.
//   2. Das Kürzel bleibt in diesem Browser stehen, damit es nicht bei jedem
//      Neuladen fehlt. Ohne Speicher (privates Fenster) ist das Feld leer.
(function () {
  const tabelle = document.getElementById("aenderungen");
  const filter = { status: "", art: "", partner: "" };

  function passt(zelle) {
    return (!filter.status || zelle.dataset.status === filter.status)
      && (!filter.art || zelle.dataset.antrag === filter.art);
  }

  function wendeAn() {
    if (!tabelle) return;
    let vorigeSichtbar = null;
    for (const teil of tabelle.tBodies) {
      if (teil.classList.contains("aenderungen-fach")) {
        vorigeSichtbar = null;
        continue;
      }
      let eine = false;
      for (const zelle of teil.querySelectorAll("td[data-antrag]")) {
        const ja = passt(zelle);
        zelle.classList.toggle("gedimmt", !ja);
        eine = eine || ja;
      }
      teil.hidden = !eine || Boolean(filter.partner && teil.dataset.partner !== filter.partner);
      // Der Strich über einem Buch gehört an seinen ersten sichtbaren
      // Abschnitt; der erste unter dem Fachnamen braucht keinen.
      if (!teil.hidden) {
        teil.classList.toggle("strich", vorigeSichtbar !== null
          && vorigeSichtbar.dataset.gruppeEnde !== teil.dataset.gruppeAnfang);
        vorigeSichtbar = teil;
      }
    }
    // Ein Fach ohne sichtbare Ersetzung verliert auch seine Kopfzeile.
    for (const kopf of tabelle.querySelectorAll("tbody.aenderungen-fach")) {
      const eigene = tabelle.querySelectorAll(
        'tbody.aenderungen-ersetzung[data-fach="' + CSS.escape(kopf.dataset.fach) + '"]');
      kopf.hidden = Array.from(eigene).every((teil) => teil.hidden);
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

  wendeAn();
})();
