// Filtern und Sortieren passieren im Browser: die Tabelle ist vollständig
// gerendert, eine Serverrunde je Tastendruck wäre auf dem Netzlaufwerk spürbar.
(function () {
  const tabelle = document.getElementById("tabelle");
  if (!tabelle) return;
  const koerper = tabelle.tBodies[0];
  const zeilen = Array.from(koerper.rows);
  const nurBedarf = document.getElementById("nur-bedarf");
  const suche = document.getElementById("suche");
  const sichtbar = document.getElementById("sichtbar");

  function anwenden() {
    const begriff = (suche.value || "").trim().toLowerCase();
    let anzahl = 0;
    for (const zeile of zeilen) {
      const passtBedarf = !nurBedarf.checked || zeile.dataset.bedarf === "1";
      const passtSuche = !begriff || zeile.dataset.suche.includes(begriff);
      const zeigen = passtBedarf && passtSuche;
      zeile.hidden = !zeigen;
      if (zeigen) anzahl++;
    }
    sichtbar.textContent = anzahl;
  }

  function zellwert(zeile, index, art) {
    const text = zeile.cells[index].textContent.trim();
    if (art !== "zahl") return text.toLowerCase();
    // "—" steht für "kein Wert" und soll immer ans Ende sortieren.
    const zahl = parseInt(text, 10);
    return Number.isNaN(zahl) ? Number.NEGATIVE_INFINITY : zahl;
  }

  tabelle.tHead.addEventListener("click", (ereignis) => {
    const kopf = ereignis.target.closest("th");
    if (!kopf) return;
    const index = Array.from(kopf.parentNode.cells).indexOf(kopf);
    const art = kopf.dataset.sort;
    const absteigend = kopf.getAttribute("aria-sort") === "ascending";
    for (const anderer of kopf.parentNode.cells) anderer.removeAttribute("aria-sort");
    kopf.setAttribute("aria-sort", absteigend ? "descending" : "ascending");

    const sortiert = zeilen.slice().sort((a, b) => {
      const links = zellwert(a, index, art);
      const rechts = zellwert(b, index, art);
      if (links < rechts) return absteigend ? 1 : -1;
      if (links > rechts) return absteigend ? -1 : 1;
      return 0;
    });
    for (const zeile of sortiert) koerper.appendChild(zeile);
  });

  nurBedarf.addEventListener("change", anwenden);
  suche.addEventListener("input", anwenden);
  anwenden();
})();
