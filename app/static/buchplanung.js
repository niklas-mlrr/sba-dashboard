// Die Buchplanung in den Bücherlisten-Seiten - vier Knöpfe und ein Menü.
//
// Dieselbe Regel wie in app.js und mehrjahresbaende.js: so dumm wie möglich.
// Das Skript rechnet keinen Status aus und entscheidet nicht, ob ein Preis
// stimmt; es schickt die Eingabe an den Server und trägt ein, was zurückkommt.
// Welche Status es gibt, steht in buecherlisten/planung/modelle.py - hier steht
// nirgends eine Liste davon.
//
//   1. Aktualisieren: beide Schuljahre aus IServ holen und die Datei anlegen.
//      Danach wird die Seite neu geladen - sie zeigt dann überall den Stand.
//   2. Preis prüfen: je Buch (Verlags-Ansicht) oder als ganze Verlagsliste.
//   3. Liste bestätigen: die Freigabe der Fachkonferenzleitung (Fach-Ansicht),
//      die Kürzel und Datum in alle Zeilen dieses Fachs schreibt.
//   4. Das Planungsmenü: ein Klick auf eine Buchzeile öffnet den Dialog mit
//      Einführung, Ausmusterung und Rücklage dieses Buchs in diesem Fach.
//      Gespeichert wird alles auf einmal - ein Menü, ein Knopf, eine Anfrage
//      (POST /api/buchplanung/buch). Abbrechen verwirft.
//
// Der Menü-Inhalt wird NICHT hier gebaut: er steht je Buch fertig gerendert in
// einem <template class="planung-vorlage"> (templates/_buchplanung.html) und
// wird beim Öffnen in den einen Dialog der Seite geklont. Eine zweite Fassung
// der Darstellung in JavaScript wäre genau die Doppelung, die mit der Vorlage
// auseinanderläuft.
//
// Antwortet der Server mit 409, hat jemand anderes die Datei angefasst; dann
// wird nicht überschrieben, sondern nachgeladen.
(function () {
  const wurzel = document.getElementById("buchplanung");
  if (!wurzel) return;
  const meldung = document.getElementById("planung-meldung");
  const schuljahr = wurzel.dataset.schuljahr;
  const menue = document.getElementById("planungsmenue");
  const leerzeile = document.getElementById("planung-leerzeile");

  function zeige(text, art) {
    if (!meldung) return;
    meldung.textContent = text;
    meldung.className = "hinweis meldung" + (art ? " " + art : "");
    meldung.hidden = !text;
  }

  function mtime() {
    const wert = parseFloat(wurzel.dataset.mtime);
    return Number.isFinite(wert) ? wert : null;
  }

  function neuLaden(text) {
    zeige(text, "");
    setTimeout(() => window.location.reload(), 400);
  }

  // Der Server schickt den ganzen neuen Stand zurück. Statt ihn hier Zelle für
  // Zelle einzubauen - Statuslabel, Jahrgang-Spalte, Übersichtszähler -, wird
  // die Seite neu geladen: sie kommt ohnehin live aus IServ, und der eine
  // zusätzliche Aufruf ist billiger als eine zweite Fassung der Darstellung,
  // die mit der Vorlage auseinanderlaufen kann.
  async function sende(pfad, koerper, erfolg) {
    const stand = mtime();
    if (stand === null && pfad !== "/api/buchplanung/abgleich") {
      zeige("Für dieses Schuljahr ist noch nichts gespeichert. Bitte zuerst " +
            "„Aus IServ aktualisieren“.", "fehlerhaft");
      return;
    }
    zeige("Wird gespeichert…", "");
    try {
      const antwort = await fetch(pfad, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ schuljahr: schuljahr, mtime: stand }, koerper)),
      });
      const daten = await antwort.json().catch(() => ({}));
      if (antwort.status === 409) {
        neuLaden("Die Datei wurde inzwischen geändert. Die Seite wird neu geladen.");
        return;
      }
      if (!antwort.ok) {
        zeige(daten.fehler || "Das Speichern ist fehlgeschlagen.", "fehlerhaft");
        return;
      }
      wurzel.dataset.mtime = daten.mtime;
      neuLaden(erfolg(daten));
    } catch (fehler) {
      zeige("Der Server ist nicht erreichbar: " + fehler, "fehlerhaft");
    }
  }

  // ── Werte aus einer Gruppe von Feldern einsammeln ─────────────────────────

  function felder(bereich) {
    const werte = {};
    for (const feld of bereich.querySelectorAll("[data-planung-feld]")) {
      werte[feld.dataset.planungFeld] = feld.value.trim();
    }
    return werte;
  }

  function zahl(text) {
    if (!text) return null;
    const wert = Number(text.replace(",", "."));
    return Number.isFinite(wert) ? wert : null;
  }

  // ── Das Planungsmenü ──────────────────────────────────────────────────────

  function oeffne(zeile) {
    if (!menue) return;
    const vorlage = document.querySelector(
      '.planung-vorlage[data-isbn="' + CSS.escape(zeile.dataset.isbn) + '"]' +
      '[data-fach="' + CSS.escape(zeile.dataset.fach) + '"]');
    if (!vorlage) return;
    menue.replaceChildren(vorlage.content.cloneNode(true));
    menue.dataset.isbn = zeile.dataset.isbn;
    menue.dataset.fach = zeile.dataset.fach;
    const titel = menue.querySelector(".modal-title");
    if (titel) titel.id = "planungsmenue-titel";
    menue.showModal();
    // Erst jetzt messen: in einem geschlossenen <dialog> hat nichts eine Höhe.
    messeBemerkungen(menue);
  }

  function fuegeJahrgangAn(knopf) {
    const koerper = knopf.closest(".planung-block").querySelector("[data-planung-zeilen]");
    if (!koerper || !leerzeile) return;
    koerper.appendChild(leerzeile.content.cloneNode(true));
    const zeile = koerper.lastElementChild;
    messeBemerkungen(zeile);
    zeile.querySelector('[data-planung-feld="jahrgang"]').focus();
  }

  // ── Die Bemerkung: eine Zeile hoch, beim Tippen so hoch wie ihr Text ──────
  //
  // Eingeklappt ist sie eine Zeile hoch und endet mit "…", wenn mehr darin
  // steht (die Klasse setzt das CSS um). Beim Anklicken wächst sie nach unten,
  // damit man den ganzen Text liest; beim Verlassen klappt sie wieder ein.
  // Ohne das wäre eine lange Bemerkung von einer kurzen nicht zu unterscheiden.
  function passeHoeheAn(feld) {
    feld.style.height = "auto";
    feld.style.height = feld.scrollHeight + "px";
  }

  function klappeEin(feld) {
    feld.style.height = "";
    const rahmen = feld.closest(".planung-bemerkung-rahmen");
    if (rahmen) rahmen.classList.toggle("hat-mehr", feld.scrollHeight > feld.clientHeight + 1);
  }

  function messeBemerkungen(bereich) {
    for (const feld of bereich.querySelectorAll(".planung-bemerkung")) klappeEin(feld);
  }

  // Gesperrte Felder liest felder() als leeren Text - genau richtig: ein
  // Kaufbuch wird nicht ausgemustert, und der Server weist es ohnehin ab.
  function speichere() {
    const zeilen = [];
    for (const zeile of menue.querySelectorAll("[data-planung-zeile]")) {
      const werte = felder(zeile);
      const jahrgang = Number(werte.jahrgang);
      // Eine Leerzeile, in die niemand etwas eingetragen hat, wird still
      // verworfen - "+ Jahrgang" einmal zu oft gedrückt ist kein Fehler.
      if (!werte.jahrgang) {
        if (werte.eingefuehrt_ab || werte.ausgemustert_nach || werte.bemerkung) {
          zeige("Bitte zu jeder Zeile den Jahrgang eintragen.", "fehlerhaft");
          return;
        }
        continue;
      }
      zeilen.push({
        jahrgang: jahrgang,
        eingefuehrt_ab: werte.eingefuehrt_ab || "",
        ausgemustert_nach: werte.ausgemustert_nach || "",
        bemerkung: werte.bemerkung || "",
      });
    }
    // Den Rücklage-Block gibt es nur bei leihbaren Büchern; fehlt er, wird
    // auch nichts über Rücklagen behauptet (``ruecklage: null``).
    const anzahlfeld = menue.querySelector(".planung-ruecklage");
    const block = anzahlfeld ? anzahlfeld.closest(".planung-block") : null;
    const werte = block ? felder(block) : {};
    sende("/api/buchplanung/buch", {
      isbn: menue.dataset.isbn,
      fach: menue.dataset.fach,
      zeilen: zeilen,
      ruecklage: block === null ? null : {
        anzahl: werte.anzahl === "" ? null : Number(werte.anzahl),
        bemerkung: werte.bemerkung || "",
      },
    }, () => "Die Planung wurde gespeichert.");
  }

  // ── Die Knöpfe ────────────────────────────────────────────────────────────

  document.addEventListener("click", (ereignis) => {
    const knopf = ereignis.target.closest("[data-planung]");
    if (!knopf) return;
    const art = knopf.dataset.planung;

    if (art === "aufklappen") {
      // Die ganze Zeile ist der Knopf. Was in ihr selbst bedienbar ist -
      // das Häkchen "Leihbar", ein Link -, behält seinen eigenen Klick.
      if (ereignis.target.closest("a, button, input, select, label")) return;
      oeffne(knopf);
      return;
    }
    if (art === "jahrgang-anfuegen") { fuegeJahrgangAn(knopf); return; }
    if (art === "jahrgang-entfernen") { knopf.closest("[data-planung-zeile]").remove(); return; }
    if (art === "abbrechen") { menue.close(); return; }
    if (art === "speichern") { speichere(); return; }

    if (art === "abgleich") {
      zeige("Beide Schuljahre werden aus IServ geholt. Das dauert einen Moment…", "");
      sende("/api/buchplanung/abgleich", {},
            () => "Der Stand wurde aus IServ übernommen.");
      return;
    }

    const kopf = knopf.closest(".planung-formular");

    if (art === "preise") {
      const werte = kopf ? felder(kopf) : {};
      if (!werte.kuerzel) {
        zeige("Bitte das Kürzel eintragen, mit dem bestätigt wird.", "fehlerhaft");
        return;
      }
      sende("/api/buchplanung/preise", {
        verlag: knopf.dataset.verlag, kuerzel: werte.kuerzel, datum: werte.datum || null,
      }, (daten) => daten.bestaetigt + " Preis(e) als geprüft eingetragen.");
      return;
    }

    if (art === "preis") {
      const eingabe = document.querySelector('.planung-formular [data-planung-feld="kuerzel"]');
      sende("/api/buchplanung/preis", {
        isbn: knopf.dataset.isbn,
        preis: zahl(knopf.dataset.preis),
        kuerzel: eingabe ? eingabe.value.trim() : "",
        datum: null,
      }, () => "Der Preis wurde als geprüft eingetragen.");
      return;
    }

    if (art === "fach") {
      const werte = kopf ? felder(kopf) : {};
      sende("/api/buchplanung/fach", {
        fach: knopf.dataset.fach, kuerzel: werte.kuerzel || "",
        datum: werte.datum || null,
      }, (daten) => werte.kuerzel
          ? daten.bestaetigt + " Zeile(n) dieses Fachs bestätigt."
          : "Die Bestätigung wurde zurückgenommen.");
    }
  });

  // Die Bemerkung wächst beim Bearbeiten und klappt danach wieder ein.
  // "focusin"/"focusout" statt focus/blur: die steigen auf und kommen deshalb
  // auch an Feldern an, die erst später im Dialog stehen.
  document.addEventListener("focusin", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) {
      ereignis.target.closest(".planung-bemerkung-rahmen").classList.remove("hat-mehr");
      passeHoeheAn(ereignis.target);
    }
  });
  document.addEventListener("focusout", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) klappeEin(ereignis.target);
  });
  document.addEventListener("input", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) passeHoeheAn(ereignis.target);
  });

  // Die Zeile ist ein Knopf (role="button"), also öffnet sie auch mit der
  // Tastatur. Die Leertaste würde sonst die Seite scrollen.
  document.addEventListener("keydown", (ereignis) => {
    if (ereignis.key !== "Enter" && ereignis.key !== " ") return;
    const zeile = ereignis.target.closest('[data-planung="aufklappen"]');
    if (!zeile || zeile !== ereignis.target) return;
    ereignis.preventDefault();
    oeffne(zeile);
  });
})();
