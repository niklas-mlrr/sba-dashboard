// Druckmenü der Bücherlisten (Vorlage: templates/_druckmenue.html).
//
// Dieselbe Datei für Fach, Verlag und Jahrgang: Stand, Bestätigung, Rückgabe,
// Anträge und Reihenfolge gibt es nur bei Fach, die Schülerliste nur bei
// Jahrgang, die Auswahl und "Doppelseitig" nur auf der Übersicht. Was fehlt, wird hier
// übersprungen.
//
// Regeln, die hier und nirgends sonst stehen:
//   * Mit "IServ-Stand benutzen" sind Bestätigung, Rückgabe und Anträge
//     gesperrt: sie gibt es nur ohne. Ohne "Bestätigungsaufforderung" sind
//     die Rückgabe-Felder gesperrt, ohne "Antragsinformationen" die
//     Häkchen darunter und ohne "Für doppelseitigen Druck optimieren" das
//     Häkchen "falls nötig". Gesperrte Felder schickt der Browser nicht mit.
//   * Die Auswahl steht bei jedem Öffnen auf "Alle".
//   * Wechsel auf "Individuell": die Häkchen zeigen die Gruppen der zuletzt
//     gewählten Option. "alle" heißt alle; sonst steht in data-gruppen die
//     Liste der Namen (JSON), die der Server ausgerechnet hat. Eine solche
//     Option schaltet selbst auf "Individuell": nur so steht die fertige
//     Auswahl in der PDF-URL, und F5 im PDF-Tab zeigt dieselben Fächer.
//     "nicht versendete" ist noch gesperrt (Stand "Gesendet" fehlt).
//   * Fächer: mit "IServ-Stand benutzen" stehen nur die aus IServ zur Wahl,
//     ohne nur die der Planungsdatei (data-quellen am Listeneintrag). Die
//     übrigen sind ausgeblendet und gesperrt, also nicht in der PDF-URL, und
//     zählen in "n von m" nicht mit.
//   * Ohne einen einzigen angehakten Eintrag lässt sich kein PDF öffnen.
// Alle anderen Felder behalten ihren Wert, bis die Seite neu geladen wird.
(function () {
  const dialog = document.getElementById("druckmenue");
  const oeffnen = document.getElementById("druck-oeffnen");
  const formular = document.getElementById("druckformular");
  const iservStand = document.getElementById("druck-iserv-stand");
  const bestaetigung = document.getElementById("druck-bestaetigung");
  const bestaetigungZeile = document.getElementById("druck-bestaetigung-zeile");
  const rueckgabeBis = document.getElementById("druck-rueckgabe-bis");
  const rueckgabeAn = document.getElementById("druck-rueckgabe-an");
  const rueckgabe = document.getElementById("druck-rueckgabe");
  const antraege = document.getElementById("druck-antraege");
  const antragsinfo = document.getElementById("druck-antragsinfo");
  const antragDetails = ["datum", "bearbeiter", "begruendung"].map((name) => ({
    haekchen: document.getElementById(`druck-antrag-${name}`),
    zeile: document.getElementById(`druck-antrag-${name}-zeile`),
  }));
  const doppelseitig = document.getElementById("druck-doppelseitig");
  const fallsNoetig = document.getElementById("druck-falls-noetig");
  const fallsNoetigZeile = document.getElementById("druck-falls-noetig-zeile");
  const starten = document.getElementById("druck-starten");

  function sperren() {
    if (iservStand) {
      const ohneIserv = !iservStand.checked;
      bestaetigung.disabled = !ohneIserv;
      bestaetigungZeile.classList.toggle("gesperrt", !ohneIserv);
      const mitBestaetigung = ohneIserv && bestaetigung.checked;
      for (const feld of [rueckgabeBis, rueckgabeAn]) feld.disabled = !mitBestaetigung;
      rueckgabe.classList.toggle("gesperrt", !mitBestaetigung);
      antragsinfo.disabled = !ohneIserv;
      antraege.classList.toggle("gesperrt", !ohneIserv);
      const mitAntraegen = ohneIserv && antragsinfo.checked;
      for (const { haekchen, zeile } of antragDetails) {
        haekchen.disabled = !mitAntraegen;
        zeile.classList.toggle("disabled", !mitAntraegen);
      }
    }
    if (doppelseitig) {
      fallsNoetig.disabled = !doppelseitig.checked;
      fallsNoetigZeile.classList.toggle("disabled", !doppelseitig.checked);
    }
  }
  if (iservStand) {
    for (const feld of [iservStand, bestaetigung, antragsinfo]) feld.addEventListener("change", sperren);
  }
  if (doppelseitig) doppelseitig.addEventListener("change", sperren);

  // ── Auswahl (nur auf der Übersicht) ───────────────────────────────────────
  const individuell = document.getElementById("druck-individuell");
  let auswahlZuruecksetzen = () => {};
  let auswahlPruefen = () => {};
  if (individuell) {
    const liste = document.getElementById("druck-gruppenliste");
    const listenKnopf = document.getElementById("druck-gruppenliste-knopf");
    const listenText = document.getElementById("druck-gruppenliste-text");
    const optionen = Array.from(formular.querySelectorAll('input[type="radio"][data-gruppen], #druck-individuell'));
    const haekchen = Array.from(liste.querySelectorAll('input[type="checkbox"]'));
    let zuletzt = optionen[0];

    // Steht das Fach in der Quelle, die gedruckt wird? Ohne data-quellen
    // (Verlag, Jahrgang) immer.
    function inQuelle(h) {
      const quellen = h.closest("li").dataset.quellen;
      if (quellen === undefined) return true;
      const quelle = iservStand && iservStand.checked ? "iserv" : "planung";
      return quellen.split(" ").includes(quelle);
    }
    const sichtbare = () => haekchen.filter(inQuelle);

    function quelleAnwenden() {
      for (const h of haekchen) {
        const da = inQuelle(h);
        h.closest("li").hidden = !da;
        h.disabled = !da || !individuell.checked;
      }
    }

    auswahlPruefen = () => {
      quelleAnwenden();
      const liste = sichtbare();
      const angehakt = liste.filter((h) => h.checked).length;
      listenText.textContent = `${angehakt} von ${liste.length}`;
      starten.disabled = liste.length === 0 || (individuell.checked && angehakt === 0);
    };
    if (iservStand) iservStand.addEventListener("change", () => auswahlPruefen());

    function listeOffen(offen) {
      liste.classList.toggle("open", offen);
      listenKnopf.setAttribute("aria-expanded", String(offen));
    }

    function uebernimm(option) {
      const gruppen = option.dataset.gruppen;
      if (gruppen === undefined) return;
      if (gruppen === "alle") {
        for (const h of haekchen) h.checked = true;
        return;
      }
      let namen;
      try {
        namen = new Set(JSON.parse(gruppen));
      } catch (fehler) {
        for (const h of haekchen) h.checked = true;
        return;
      }
      for (const h of haekchen) h.checked = namen.has(h.value);
    }

    for (const option of optionen) {
      option.addEventListener("change", () => {
        const eigene = option === individuell;
        if (eigene) uebernimm(zuletzt);
        else zuletzt = option;
        // Eine Option mit fertiger Namensliste wählt sie selbst aus und gibt
        // an "Individuell" ab - sonst stünde in der URL wieder "alle".
        if (!eigene && option.dataset.gruppen && option.dataset.gruppen !== "alle") {
          uebernimm(option);
          individuell.checked = true;
          listenKnopf.disabled = false;
          auswahlPruefen();
          return;
        }
        listenKnopf.disabled = !eigene;
        if (!eigene) listeOffen(false);
        auswahlPruefen();
      });
    }
    for (const h of haekchen) h.addEventListener("change", auswahlPruefen);
    listenKnopf.addEventListener("click", () => listeOffen(!liste.classList.contains("open")));
    dialog.addEventListener("click", (ereignis) => {
      if (!liste.contains(ereignis.target)) listeOffen(false);
    });

    auswahlZuruecksetzen = () => {
      optionen[0].checked = true;
      optionen[0].dispatchEvent(new Event("change"));
    };
  }

  oeffnen.addEventListener("click", () => {
    auswahlZuruecksetzen();
    sperren();
    auswahlPruefen();
    dialog.showModal();
  });
  document.getElementById("druck-abbrechen").addEventListener("click", () => dialog.close());
  // Das PDF öffnet sich über target="_blank" im neuen Tab; das Menü ist dann fertig.
  formular.addEventListener("submit", () => window.setTimeout(() => dialog.close(), 0));
})();
