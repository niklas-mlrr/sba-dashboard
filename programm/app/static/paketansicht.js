// Umschalter "Paketansicht" auf der Seite einer Paket-Bücherliste.
//
// Angehakt: Grundpaket und Wahlbereiche getrennt (#paketteile). Nicht
// angehakt: alle Bücher in einer Tabelle (#gesamtansicht). Beide stehen
// fertig im HTML; hier wird nur umgeblendet. Die Sortierung überträgt
// sortieren.js, das jede Tabelle aus demselben Klickverlauf aufbaut.
(function () {
  const kaestchen = document.getElementById("paketansicht");
  const teile = document.getElementById("paketteile");
  const gesamt = document.getElementById("gesamtansicht");

  function zeige() {
    teile.hidden = !kaestchen.checked;
    gesamt.hidden = kaestchen.checked;
  }
  kaestchen.addEventListener("change", zeige);
  // Der Browser stellt ein abgewähltes Häkchen nach "Zurück" wieder her.
  zeige();
})();
