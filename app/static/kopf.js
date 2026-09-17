// Der Kopf aus base.html - steht auf jeder Seite, auch auf Einrichtung und
// Fehlerseite, und deshalb nicht in app.js, das ohne Tabelle sofort aufhört.
(function () {
  const dialog = document.getElementById("einstellungen");
  document.getElementById("einstellungen-oeffnen").addEventListener("click", () => {
    dialog.showModal();
  });
})();
