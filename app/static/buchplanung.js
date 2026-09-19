// Die Buchplanung in den Bücherlisten-Seiten - fünf Knöpfe, sonst nichts.
//
// Dieselbe Regel wie in app.js und mehrjahresbaende.js: so dumm wie möglich.
// Das Skript rechnet keinen Status aus und entscheidet nicht, ob ein Preis
// stimmt; es schickt die Eingabe an den Server und trägt ein, was zurückkommt.
// Welche Status es gibt, steht in buchplanung/core/modelle.py - hier steht
// nirgends eine Liste davon.
//
//   1. Aktualisieren: beide Schuljahre aus IServ holen und die Datei anlegen.
//      Danach wird die Seite neu geladen - sie zeigt dann überall den Stand.
//   2. Preis prüfen: je Buch (Verlags-Ansicht) oder als ganze Verlagsliste.
//   3. Liste bestätigen: die Freigabe der Fachkonferenzleitung (Fach-Ansicht).
//   4. Planung: Einführung und Ausmusterung je Jahrgang, im Aufklapper.
//   5. Rücklage: wie viele Exemplare die Fachschaft behalten möchte.
//
// Antwortet der Server mit 409, hat jemand anderes die Datei angefasst; dann
// wird nicht überschrieben, sondern nachgeladen.
(function () {
  const wurzel = document.getElementById("buchplanung");
  if (!wurzel) return;
  const meldung = document.getElementById("planung-meldung");
  const schuljahr = wurzel.dataset.schuljahr;

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
  // Zelle einzubauen - Statuslabel, Aufklapper, Übersichtszähler -, wird die
  // Seite neu geladen: sie kommt ohnehin live aus IServ, und der eine
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

  // ── Die Knöpfe ────────────────────────────────────────────────────────────

  document.addEventListener("click", (ereignis) => {
    const knopf = ereignis.target.closest("[data-planung]");
    if (!knopf) return;
    const art = knopf.dataset.planung;

    if (art === "aufklappen") {
      const zeile = document.querySelector(
        '.planung-details[data-isbn="' + CSS.escape(knopf.dataset.isbn) + '"]');
      if (!zeile) return;
      zeile.hidden = !zeile.hidden;
      knopf.setAttribute("aria-expanded", String(!zeile.hidden));
      return;
    }

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
      }, () => werte.kuerzel ? "Die Bücherliste wurde bestätigt."
                             : "Die Bestätigung wurde zurückgenommen.");
      return;
    }

    if (art === "ruecklage") {
      const block = knopf.closest(".planung-block");
      const werte = felder(block);
      sende("/api/buchplanung/ruecklage", {
        isbn: knopf.dataset.isbn, fach: knopf.dataset.fach,
        anzahl: werte.anzahl === "" ? null : Number(werte.anzahl),
        status: werte.status || "", bemerkung: werte.bemerkung || "",
      }, () => "Die Rücklage wurde gespeichert.");
    }
  });

  // ── Planung: beim Verlassen eines Feldes speichern ────────────────────────
  //
  // Kein eigener Knopf je Jahrgang: die beiden Felder gehören zusammen, und
  // "change" feuert erst, wenn sich der Wert wirklich geändert hat.
  document.addEventListener("change", (ereignis) => {
    const feld = ereignis.target.closest('.planung-tabelle [data-planung-feld]');
    if (!feld) return;
    const zeile = feld.closest("tr");
    const details = feld.closest(".planung-details");
    const werte = felder(zeile);
    const jahrgang = zeile.dataset.jahrgang || werte.jahrgang;
    if (!jahrgang) {
      zeige("Bitte zuerst den Jahrgang eintragen.", "fehlerhaft");
      return;
    }
    sende("/api/buchplanung/planung", {
      isbn: details.dataset.isbn,
      jahrgang: Number(jahrgang),
      eingefuehrt_ab: werte.eingefuehrt_ab || "",
      ausgemustert_nach: werte.ausgemustert_nach || "",
      beschluss: werte.beschluss || "",
    }, () => "Die Planung wurde gespeichert.");
  });
})();
