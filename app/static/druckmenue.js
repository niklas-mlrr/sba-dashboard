// Druckmenü der Bücherlisten nach Fach (Vorlage: templates/_druckmenue.html).
//
// Regeln, die hier und nirgends sonst stehen:
//   * Ohne "Bestätigungsaufforderung" sind die Rückgabe-Felder gesperrt, und
//     ohne "Für doppelseitigen Druck optimieren" das Häkchen "falls nötig".
//     Gesperrte Felder schickt der Browser nicht mit.
//   * "Fächer" steht bei jedem Öffnen auf "Alle".
//   * Wechsel auf "Individuell": die Häkchen zeigen die Fächer der zuletzt
//     gewählten Option. "veränderte" und "nicht bestätigte" sind Platzhalter
//     und stehen für alle Fächer (data-faecher="alle").
//   * Ohne ein einziges angehaktes Fach lässt sich kein PDF öffnen.
// Alle anderen Felder behalten ihren Wert, bis die Seite neu geladen wird.
(function () {
  const dialog = document.getElementById("druckmenue");
  const oeffnen = document.getElementById("druck-oeffnen");
  const formular = document.getElementById("druckformular");
  const bestaetigung = document.getElementById("druck-bestaetigung");
  const rueckgabeBis = document.getElementById("druck-rueckgabe-bis");
  const rueckgabeAn = document.getElementById("druck-rueckgabe-an");
  const rueckgabe = document.getElementById("druck-rueckgabe");
  const doppelseitig = document.getElementById("druck-doppelseitig");
  const fallsNoetig = document.getElementById("druck-falls-noetig");
  const fallsNoetigZeile = document.getElementById("druck-falls-noetig-zeile");
  const starten = document.getElementById("druck-starten");

  function sperren() {
    for (const feld of [rueckgabeBis, rueckgabeAn]) feld.disabled = !bestaetigung.checked;
    rueckgabe.classList.toggle("gesperrt", !bestaetigung.checked);
    fallsNoetig.disabled = !doppelseitig.checked;
    fallsNoetigZeile.classList.toggle("disabled", !doppelseitig.checked);
  }
  bestaetigung.addEventListener("change", sperren);
  doppelseitig.addEventListener("change", sperren);

  // ── Fächer (nur auf der Gesamtseite) ──────────────────────────────────────
  const individuell = document.getElementById("druck-individuell");
  let faecherZuruecksetzen = () => {};
  let faecherPruefen = () => {};
  if (individuell) {
    const liste = document.getElementById("druck-faecherliste");
    const listenKnopf = document.getElementById("druck-faecherliste-knopf");
    const listenText = document.getElementById("druck-faecherliste-text");
    const optionen = Array.from(formular.querySelectorAll('input[name="faecher_auswahl"]'));
    const haekchen = Array.from(liste.querySelectorAll('input[name="faecher"]'));
    let zuletzt = optionen[0];

    faecherPruefen = () => {
      const angehakt = haekchen.filter((h) => h.checked).length;
      listenText.textContent = `${angehakt} von ${haekchen.length}`;
      starten.disabled = individuell.checked && angehakt === 0;
    };

    function listeOffen(offen) {
      liste.classList.toggle("open", offen);
      listenKnopf.setAttribute("aria-expanded", String(offen));
    }

    function uebernimm(option) {
      // Heute steht jede Option außer "Individuell" für alle Fächer.
      if (option.dataset.faecher === "alle") for (const h of haekchen) h.checked = true;
    }

    for (const option of optionen) {
      option.addEventListener("change", () => {
        const eigene = option === individuell;
        if (eigene) uebernimm(zuletzt);
        else zuletzt = option;
        listenKnopf.disabled = !eigene;
        for (const h of haekchen) h.disabled = !eigene;
        if (!eigene) listeOffen(false);
        faecherPruefen();
      });
    }
    for (const h of haekchen) h.addEventListener("change", faecherPruefen);
    listenKnopf.addEventListener("click", () => listeOffen(!liste.classList.contains("open")));
    dialog.addEventListener("click", (ereignis) => {
      if (!liste.contains(ereignis.target)) listeOffen(false);
    });

    faecherZuruecksetzen = () => {
      optionen[0].checked = true;
      optionen[0].dispatchEvent(new Event("change"));
    };
  }

  oeffnen.addEventListener("click", () => {
    faecherZuruecksetzen();
    sperren();
    faecherPruefen();
    dialog.showModal();
  });
  document.getElementById("druck-abbrechen").addEventListener("click", () => dialog.close());
  // Das PDF öffnet sich über target="_blank" im neuen Tab; das Menü ist dann fertig.
  formular.addEventListener("submit", () => window.setTimeout(() => dialog.close(), 0));
})();
