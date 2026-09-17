// Der Kopf aus base.html - steht auf jeder Seite, auch auf Einrichtung und
// Fehlerseite, und deshalb nicht in app.js, das ohne Tabelle sofort aufhört.
(function () {
  const dialog = document.getElementById("einstellungen");
  document.getElementById("einstellungen-oeffnen").addEventListener("click", (ereignis) => {
    ereignis.preventDefault();
    dialog.showModal();
  });
  // Aufklappmenü "Bücherliste": Klick öffnet und schließt, ein Klick daneben
  // oder Escape schließt. Die Einträge sind gewöhnliche Links.
  const menue = document.getElementById("buecherliste");
  const menueKnopf = document.getElementById("buecherliste-oeffnen");
  function setzeMenue(offen) {
    menue.classList.toggle("open", offen);
    menueKnopf.setAttribute("aria-expanded", String(offen));
  }
  menueKnopf.addEventListener("click", (ereignis) => {
    ereignis.preventDefault();
    setzeMenue(!menue.classList.contains("open"));
  });
  document.addEventListener("click", (ereignis) => {
    if (!menue.contains(ereignis.target)) setzeMenue(false);
  });
  document.addEventListener("keydown", (ereignis) => {
    if (ereignis.key === "Escape") setzeMenue(false);
  });
  // Platzhalter, bis es eine Hilfeseite gibt: "#" soll nicht nach oben springen.
  document.getElementById("hilfe").addEventListener("click", (ereignis) => {
    ereignis.preventDefault();
  });
})();
