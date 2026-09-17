// Umschalter "Paketansicht" auf der Seite einer Paket-Bücherliste.
//
// An: Grundpaket und Wahlbereiche getrennt (#paketteile). Aus: alle Bücher in
// einer Tabelle (#gesamtansicht). Beide stehen fertig im HTML; hier wird nur
// umgeblendet. Die Sortierung überträgt sortieren.js, das jede Tabelle aus
// demselben Klickverlauf aufbaut.
(function () {
  const knopf = document.getElementById("paketansicht");
  const teile = document.getElementById("paketteile");
  const gesamt = document.getElementById("gesamtansicht");
  const symbol = knopf.querySelector(".glyphicon");

  knopf.addEventListener("click", () => {
    const an = knopf.getAttribute("aria-pressed") !== "true";
    knopf.setAttribute("aria-pressed", String(an));
    knopf.classList.toggle("aktiv", an);
    symbol.classList.toggle("glyphicon-check", an);
    symbol.classList.toggle("glyphicon-unchecked", !an);
    teile.hidden = !an;
    gesamt.hidden = an;
  });
})();
