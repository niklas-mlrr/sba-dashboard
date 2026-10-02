// Die Änderungsliste - was nicht gespeichert wird.
//
// Entschieden wird über buchplanung.js (das Buchmenü, data-planung="antrag"),
// sortiert auf dem Server (die Köpfe „Jg.“ und „Jahr“ sind Links). Hier
// steht nur, was die Seite bequemer macht und nirgends ankommt:
//
//   1. Die Filter über der Tabelle: nach Entscheidung, nach Art und danach,
//      ob eine Gruppe beide Seiten hat. Alle gelten zugleich; "" heißt alle.
//      Eine Jahrgangszeile, die nicht passt, wird gedimmt, nicht ausgeblendet
//      - sonst stimmten die verbundenen Zellen (rowspan) nicht mehr. Eine
//      Gruppe ohne passende Zeile verschwindet ganz, ein Fach ohne sichtbare
//      Gruppe ebenso.
//   2. Dasselbe Buch an allen Stellen hervorheben (data-buch): unter der
//      Maus, mit dem Tastaturfokus und solange sein Menü offen ist.
(function () {
  const tabelle = document.getElementById("aenderungen");
  const filter = { status: "", art: "", partner: "" };

  function passt(zeile) {
    return (!filter.status || zeile.dataset.status === filter.status)
      && (!filter.art || zeile.dataset.antrag === filter.art);
  }

  function wendeAn() {
    if (!tabelle) return;
    for (const gruppe of tabelle.querySelectorAll("tbody.aenderungen-gruppe")) {
      let eine = false;
      for (const zeile of gruppe.querySelectorAll(".jgzeile")) {
        const ja = passt(zeile);
        zeile.classList.toggle("gedimmt", !ja);
        eine = eine || ja;
      }
      gruppe.hidden = !eine || Boolean(filter.partner && gruppe.dataset.partner !== filter.partner);
    }
    for (const kopf of tabelle.querySelectorAll("tbody.aenderungen-fach")) {
      const eigene = tabelle.querySelectorAll(
        'tbody.aenderungen-gruppe[data-fach="' + CSS.escape(kopf.dataset.fach) + '"]');
      kopf.hidden = Array.from(eigene).every((gruppe) => gruppe.hidden);
    }
    // Ausgeblendetes misst keine Höhe; was wieder erscheint, neu ausrichten.
    if (window.platziereMitte) window.platziereMitte(tabelle);
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

  // ── Dasselbe Buch hervorheben ───────────────────────────────────────────
  const menue = document.getElementById("planungsmenue");
  function verknuepfe(buch) {
    if (!tabelle) return;
    for (const kasten of tabelle.querySelectorAll(".kasten")) {
      kasten.classList.toggle("verknuepft", Boolean(buch) && kasten.dataset.buch === buch);
    }
  }
  if (tabelle) {
    for (const art of ["mouseover", "focusin"]) {
      tabelle.addEventListener(art, (ereignis) => {
        if (menue && menue.open) return;
        const kasten = ereignis.target.closest(".kasten");
        verknuepfe(kasten ? kasten.dataset.buch : null);
      });
    }
    tabelle.addEventListener("mouseleave", () => { if (!menue || !menue.open) verknuepfe(null); });
  }
  // Ein Klick auf eine Jahrgangszeile öffnet das Menü; solange es offen ist,
  // bleibt sein Buch auf der Seite dahinter markiert - auch nach dem Sprung
  // zum Partner („Ersetzt durch …“ im Menü verweist auf dieselbe Vorlage).
  document.addEventListener("click", (ereignis) => {
    const knopf = ereignis.target.closest('[data-planung="antrag-menue"]');
    if (!knopf || !tabelle) return;
    const zeile = tabelle.querySelector('.jgzeile[data-vorlage="' + CSS.escape(knopf.dataset.vorlage) + '"]');
    if (zeile) verknuepfe(zeile.closest(".kasten").dataset.buch);
  });
  if (menue) menue.addEventListener("close", () => verknuepfe(null));
})();
