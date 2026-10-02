// Die Mittelspalte der Änderungsliste - die Werte senkrecht ausrichten.
//
// Eine Gruppe (mehrere Abschnitte mit gleichem Jahrgang bzw. Jahr) hat in der
// Mitte EINE Zelle: fett der Wert der Gruppe, grau je Teil das andere
// Kriterium. Fett gehört mittig über die ganze Gruppe, jedes Grau mittig
// über seinen Teil. Wo genau das ist, weiß erst der Browser - deshalb steht
// das hier und nicht in der Vorlage. Bei nur einem Teil (`.paar`) stehen
// beide im Fluss untereinander, hier gibt es dann nichts zu tun.
//
// verteile() ist eine reine Funktion und wird über node getestet
// (tests/test_mittelspalte_js.py). platziereMitte() misst und setzt.
(function (global) {
  // Abstand von Mitte zu Mitte, ab dem sich zwei Werte nicht berühren (px).
  const ABSTAND = 18;

  // Jeder Wert hat einen Wunschplatz und einen erlaubten Bereich [min, max]
  // (gemeint ist jeweils seine Mitte); `fett` markiert den Gruppenwert.
  // Von oben nach unten wird jeder Wert als eigener Block auf einen Stapel
  // gelegt; berührt er den Block darüber, werden beide ein Block, dessen
  // Werte im festen Abstand untereinander stehen. Ein Block sitzt auf dem
  // Durchschnitt der Wunschplätze - zwei Werte weichen also je zur Hälfte
  // aus - und wird so weit verschoben, dass jedes Mitglied in seinem Bereich
  // bleibt (stößt einer an, geht der andere den Rest). Passt ein Block gar
  // nicht, steht in `fehlt`, wie viel Höhe fehlt, und in `engster`, wessen
  // unterer Rand ihn begrenzt.
  function verteile(werte, abstand) {
    // Bei gleichem Wunschplatz zuerst das Fett: das Grau weicht nach unten aus.
    const folge = werte.map((w, i) => Object.assign({}, w, { i }))
      .sort((a, b) => a.wunsch - b.wunsch || (a.fett ? -1 : 0) - (b.fett ? -1 : 0));
    const lege = (b) => {
      const n = b.glieder.length;
      const mittel = b.glieder.reduce((x, w, k) => x + w.wunsch - k * abstand, 0) / n;
      const unten = Math.max(...b.glieder.map((w, k) => w.min - k * abstand));
      const grenzen = b.glieder.map((w, k) => w.max - k * abstand);
      const oben = Math.min(...grenzen);
      b.fehlt = Math.max(0, unten - oben);
      b.engster = b.glieder[grenzen.indexOf(oben)];
      b.p = b.fehlt ? unten : Math.min(Math.max(mittel, unten), oben);
    };
    const bloecke = [];
    for (const w of folge) {
      bloecke.push({ glieder: [w] });
      lege(bloecke[bloecke.length - 1]);
      // Solange der oberste Block den darunterliegenden berührt: zusammenlegen.
      while (bloecke.length > 1) {
        const b = bloecke[bloecke.length - 1];
        const v = bloecke[bloecke.length - 2];
        if (v.p + v.glieder.length * abstand <= b.p + 0.01) break;
        v.glieder.push(...b.glieder);
        bloecke.pop();
        lege(v);
      }
    }
    const y = [];
    let fehlt = 0;
    let engster = null;
    for (const b of bloecke) {
      b.glieder.forEach((w, k) => { y[w.i] = b.p + k * abstand; });
      if (b.fehlt > fehlt) { fehlt = b.fehlt; engster = b.engster; }
    }
    return { y, fehlt, engster };
  }

  // Misst eine Mittelzelle, verteilt ihre Werte und streckt höchstens
  // einmal, genau um die fehlende Höhe: den Teil, dessen unterer Rand den
  // Block begrenzt (beim Fett den untersten - dann ist die Zelle zu kurz).
  function platziereMitte(wurzel) {
    for (const td of (wurzel || document).querySelectorAll("td.mitte-wert:not(.paar)")) {
      const zeilen = Array.from(td.closest("tbody").rows);
      for (const tr of zeilen) {
        if (tr.dataset.gestreckt) { tr.style.height = ""; delete tr.dataset.gestreckt; }
      }
      const graue = Array.from(td.querySelectorAll(".neben"));
      const miss = () => {
        const oben = td.getBoundingClientRect().top;
        const hoehe = td.offsetHeight;
        return [{ fett: true, wunsch: hoehe / 2, min: ABSTAND / 2, max: hoehe - ABSTAND / 2 }]
          .concat(graue.map((el) => {
            const eigene = zeilen.filter((tr) => tr.dataset.teil === el.dataset.teil);
            const von = eigene[0].getBoundingClientRect().top - oben;
            const bis = eigene[eigene.length - 1].getBoundingClientRect().bottom - oben;
            return { wunsch: (von + bis) / 2, min: von + ABSTAND / 2, max: bis - ABSTAND / 2,
                     letzte: eigene[eigene.length - 1] };
          }));
      };
      let werte = miss();
      let ergebnis = verteile(werte, ABSTAND);
      if (ergebnis.fehlt > 0) {
        const letzte = ergebnis.engster.letzte || werte[werte.length - 1].letzte;
        letzte.style.height = (letzte.offsetHeight + Math.ceil(ergebnis.fehlt)) + "px";
        letzte.dataset.gestreckt = "1";
        werte = miss();
        ergebnis = verteile(werte, ABSTAND);
      }
      td.querySelector(".haupt").style.top = ergebnis.y[0] + "px";
      graue.forEach((el, i) => { el.style.top = ergebnis.y[i + 1] + "px"; });
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { verteile, ABSTAND };
  } else {
    global.platziereMitte = platziereMitte;
    document.addEventListener("DOMContentLoaded", () => platziereMitte());
    if (document.readyState !== "loading") platziereMitte();
    window.addEventListener("resize", () => platziereMitte());
  }
})(this);
