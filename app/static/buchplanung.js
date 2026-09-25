// Die Buchplanung in den Bücherlisten-Seiten - drei Knöpfe und ein Menü.
//
// Dieselbe Regel wie in app.js und mehrjahresbaende.js: so dumm wie möglich.
// Das Skript rechnet keinen Status aus und entscheidet nichts;
// es schickt die Eingabe an den Server und trägt ein, was zurückkommt.
// Welche Status es gibt, steht in buecherlisten/planung/modelle.py - hier steht
// nirgends eine Liste davon.
//
//   1. Aktualisieren: beide Schuljahre aus IServ holen und die Datei anlegen.
//      Danach wird die Seite neu geladen - sie zeigt dann überall den Stand.
//   2. Liste bestätigen: die Freigabe der Fachkonferenzleitung (Fach-Ansicht),
//      die Kürzel und Datum in alle Zeilen dieses Fachs schreibt.
//   3. Das Planungsmenü: ein Klick auf eine Buchzeile öffnet den Dialog mit
//      der Buchreihe (Titel, Verlag, Preise - korrigiert wird nur in
//      der Datei, nicht in IServ), Einführung, Ausmusterung und Rücklage
//      dieses Buchs in diesem Fach.
//      Gespeichert wird alles auf einmal - ein Menü, ein Knopf, eine Anfrage
//      (POST /api/buchplanung/buch). Abbrechen verwirft.
//   4. „+ Buch hinzufügen“ unter der Fach-Liste: dasselbe Menü mit freier
//      ISBN, deren Vorschläge die Bücher anderer Fächer sind
//      (POST /api/buchplanung/buch/neu).
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

  // Gemeldet wird dort, wo gearbeitet wird: steht das Menü offen, im Menü -
  // die Seite dahinter ist abgedunkelt, und eine Meldung dort bliebe
  // ungelesen. Sonst über der Tabelle, wie bei den Knöpfen der Kopfzeile.
  function menuemeldung() {
    return menue && menue.open ? menue.querySelector("[data-planung-meldung]") : null;
  }

  function zeige(text, art) {
    const ziel = menuemeldung() || meldung;
    // Die jeweils andere Stelle leeren, sonst stünde dort noch der Satz von
    // vorhin - im Menü sichtbar, auf der Seite nach dem Schließen.
    for (const andere of [meldung, menuemeldung()]) {
      if (andere && andere !== ziel) {
        andere.textContent = "";
        andere.hidden = true;
      }
    }
    if (!ziel) return;
    ziel.textContent = text;
    // Nur die Fehlerklasse umschalten: welche Grundklassen die Stelle trägt,
    // sagt die Vorlage, nicht dieses Skript.
    ziel.classList.toggle("fehlerhaft", art === "fehlerhaft");
    ziel.hidden = !text;
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

  // ── Das Planungsmenü ──────────────────────────────────────────────────────

  function oeffne(zeile) {
    if (!menue) return;
    const vorlage = document.querySelector(
      '.planung-vorlage[data-isbn="' + CSS.escape(zeile.dataset.isbn) + '"]' +
      '[data-fach="' + CSS.escape(zeile.dataset.fach) + '"]');
    if (!vorlage) return;
    zeigeMenue(vorlage);
    menue.dataset.isbn = zeile.dataset.isbn;
    menue.dataset.fach = zeile.dataset.fach;
    delete menue.dataset.neu;
    menue.showModal();
    // Erst jetzt messen: in einem geschlossenen <dialog> hat nichts eine Höhe.
    messeBemerkungen(menue);
  }

  function zeigeMenue(vorlage) {
    menue.replaceChildren(vorlage.content.cloneNode(true));
    const titel = menue.querySelector(".modal-title");
    if (titel) titel.id = "planungsmenue-titel";
  }

  // „+ Buch hinzufügen“: dasselbe Menü, ohne Buch. Die ISBN kommt beim
  // Speichern aus dem Feld, nicht aus der Zeile; eine erste leere
  // Jahrgangszeile steht schon da, denn ohne Jahrgang gibt es nichts zu speichern.
  function oeffneNeu(knopf) {
    const vorlage = document.getElementById("planung-neu-vorlage");
    if (!menue || !vorlage) return;
    zeigeMenue(vorlage);
    delete menue.dataset.isbn;
    menue.dataset.fach = knopf.dataset.fach;
    menue.dataset.neu = "1";
    menue.showModal();
    const koerper = menue.querySelector("[data-planung-zeilen]");
    if (koerper && leerzeile) koerper.appendChild(leerzeile.content.cloneNode(true));
    messeBemerkungen(menue);
    menue.querySelector('[data-buchreihe-feld="isbn"]').focus();
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
  // `scrollHeight` ist Inhalt samt Innenabstand, aber ohne Rand; `offsetHeight
  // - clientHeight` ist genau dieser Rand. Ohne ihn bliebe das Feld zwei Pixel
  // zu kurz, und die letzte Zeile ließe sich um zwei Pixel scrollen.
  function passeHoeheAn(feld) {
    feld.style.height = "auto";
    const rand = feld.offsetHeight - feld.clientHeight;
    feld.style.height = feld.scrollHeight + rand + "px";
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
    const reihe = buchreihe();
    if (reihe === undefined) return;
    if (menue.dataset.neu) {
      if (!zeilen.length) {
        zeige("Bitte mindestens einen Jahrgang eintragen.", "fehlerhaft");
        return;
      }
      const isbn = reihe.isbn;
      delete reihe.isbn;
      sende("/api/buchplanung/buch/neu", {
        isbn: isbn,
        fach: menue.dataset.fach,
        zeilen: zeilen,
        buchreihe: reihe,
      }, () => "Das Buch wurde hinzugefügt.");
      return;
    }
    delete reihe.isbn;
    sende("/api/buchplanung/buch", {
      isbn: menue.dataset.isbn,
      fach: menue.dataset.fach,
      zeilen: zeilen,
      ruecklage: block === null ? null : {
        anzahl: werte.anzahl === "" ? null : Number(werte.anzahl),
        bemerkung: werte.bemerkung || "",
      },
      buchreihe: reihe,
    }, () => "Die Planung wurde gespeichert.");
  }

  // Der Block „Buchreihe“: Titel, Verlag und Preise so, wie sie dastehen - die
  // ISBN steht nur zum Lesen da und geht nicht mit. Ob etwas davon eine
  // Korrektur ist, entscheidet der Server; er kennt die IServ-Werte aus der
  // Datei. Hier wird nur geprüft, was IServ im selben Dialog als Pflichtfeld
  // führt. ``undefined`` heißt: nicht speichern, die Meldung steht schon da.
  function buchreihe() {
    const bereich = menue.querySelector("[data-buchreihe]");
    if (!bereich) return null;
    const werte = {};
    for (const feld of bereich.querySelectorAll("[data-buchreihe-feld]")) {
      // Ein Zahlenfeld mit unlesbarer Eingabe meldet sich als leer - und leer
      // hieße beim Preis "wie in IServ". Das darf nicht still passieren.
      if (feld.validity && feld.validity.badInput) {
        zeige("Bitte einen gültigen Betrag eintragen (" +
              feld.getAttribute("aria-label") + ").", "fehlerhaft");
        feld.focus();
        return undefined;
      }
      werte[feld.dataset.buchreiheFeld] = feld.value.trim();
    }
    const pflicht = [["titel", "den Titel"], ["verlag", "den Verlag"]];
    // Beim Hinzufügen ist die ISBN eine Eingabe; ob sie gültig ist, prüft der Server.
    if (menue.dataset.neu) pflicht.unshift(["isbn", "die ISBN"]);
    for (const [name, text] of pflicht) {
      if (!werte[name]) {
        zeige("Bitte " + text + " eintragen.", "fehlerhaft");
        return undefined;
      }
    }
    const preis = (text) => (text === "" ? null : Number(text));
    return {
      isbn: werte.isbn, titel: werte.titel, verlag: werte.verlag,
      neupreis: preis(werte.neupreis), leihgebuehr: preis(werte.leihgebuehr),
    };
  }

  // ── Vorschläge beim Tippen: Verlag, und beim Hinzufügen ISBN und Titel ────
  //
  // Wie das Typeahead in IServ: unter dem Feld stehen die Treffer, der
  // getippte Teil fett. Ein Klick (oder ↑/↓ und Enter) übernimmt einen; was es
  // noch nicht gibt, wird einfach eingetippt. Kein <datalist>: Chrome sucht
  // dort nach "enthält" statt "beginnt mit", und die Liste lässt sich nicht wie
  // IServ gestalten.
  //
  // Welche Liste ein Feld vorschlägt, sagt sein ``data-vorschlag``:
  //   verlag - die bekannten Verlage, die mit der Eingabe anfangen;
  //   isbn   - die Bücher anderer Fächer, deren ISBN so anfängt
  //            (Bindestriche zählen nicht);
  //   titel  - die Bücher anderer Fächer, deren Titel die Eingabe enthält.
  // Ein Buch zu übernehmen füllt ISBN, Titel, Verlag und Preise auf einmal.
  function liesJson(id) {
    const quelle = document.getElementById(id);
    try {
      return quelle ? JSON.parse(quelle.textContent) : [];
    } catch (fehler) {
      return [];
    }
  }
  const verlage = liesJson("planung-verlage");
  const buecher = liesJson("planung-buecher");

  function istVorschlagsfeld(ziel) {
    return ziel instanceof HTMLInputElement && Boolean(ziel.dataset.vorschlag);
  }

  function vorschlagsliste(feld) {
    return feld.parentElement.querySelector(".tt-menu");
  }

  function schliesseVorschlaege(feld) {
    const liste = vorschlagsliste(feld);
    if (liste) liste.remove();
    feld.setAttribute("aria-expanded", "false");
  }

  const klein = (text) => text.toLocaleLowerCase("de");
  const ziffern = (text) => text.replace(/[^0-9Xx]/g, "").toUpperCase();

  // Die Treffer eines Felds: je Treffer der Text, die fett gesetzte Stelle
  // darin, eine graue Zeile dazu und, bei einem Buch, seine Nummer in ``buecher``.
  function treffer(feld) {
    const art = feld.dataset.vorschlag;
    const eingabe = feld.value.trim();
    if (art === "verlag") {
      if (!eingabe) return [];
      return verlage
        .filter((name) => klein(name).startsWith(klein(eingabe)))
        .map((name) => ({ text: name, ab: 0, bis: eingabe.length }));
    }
    const liste = [];
    buecher.forEach((buch, nummer) => {
      const zusatz = [buch.faecher.join(", ")];
      if (art === "isbn") {
        const gesucht = ziffern(eingabe);
        if (!gesucht || !ziffern(buch.isbn).startsWith(gesucht)) return;
        liste.push({ text: buch.isbn_anzeige, ab: 0, bis: 0,
                     zusatz: [buch.titel].concat(zusatz), buch: nummer });
      } else if (art === "titel") {
        if (eingabe.length < 2) return;
        const ab = klein(buch.titel).indexOf(klein(eingabe));
        if (ab < 0) return;
        liste.push({ text: buch.titel, ab: ab, bis: ab + eingabe.length,
                     zusatz: [buch.isbn_anzeige].concat(zusatz), buch: nummer });
      }
    });
    return liste;
  }

  function zeigeVorschlaege(feld) {
    // Alle Treffer: die Liste ist höchstens 240 px hoch und rollt (.tt-menu in app.css).
    const gefunden = treffer(feld);
    schliesseVorschlaege(feld);
    if (!gefunden.length) return;
    const liste = document.createElement("div");
    liste.className = "tt-menu";
    liste.setAttribute("role", "listbox");
    for (const eins of gefunden) {
      const eintrag = document.createElement("div");
      eintrag.className = "tt-suggestion";
      eintrag.setAttribute("role", "option");
      eintrag.dataset.wert = eins.text;
      if (eins.buch !== undefined) eintrag.dataset.buch = eins.buch;
      const fett = document.createElement("strong");
      fett.textContent = eins.text.slice(eins.ab, eins.bis);
      eintrag.append(eins.text.slice(0, eins.ab), fett, eins.text.slice(eins.bis));
      if (eins.zusatz) {
        const grau = document.createElement("small");
        grau.className = "tt-zusatz";
        grau.textContent = eins.zusatz.filter(Boolean).join(" · ");
        eintrag.append(" ", grau);
      }
      liste.appendChild(eintrag);
    }
    feld.parentElement.appendChild(liste);
    feld.setAttribute("aria-expanded", "true");
  }

  function uebernimm(feld, eintrag) {
    schliesseVorschlaege(feld);
    if (eintrag.dataset.buch === undefined) {
      feld.value = eintrag.dataset.wert;
      feld.focus();
      return;
    }
    const buch = buecher[Number(eintrag.dataset.buch)];
    const bereich = feld.closest("[data-buchreihe]");
    const setze = (name, wert) => {
      const ziel = bereich.querySelector('[data-buchreihe-feld="' + name + '"]');
      if (ziel) ziel.value = wert;
    };
    const preis = (wert) => (wert === null || wert === undefined ? "" : Number(wert).toFixed(2));
    setze("isbn", buch.isbn_anzeige);
    setze("titel", buch.titel);
    setze("verlag", buch.verlag);
    setze("neupreis", preis(buch.neupreis));
    setze("leihgebuehr", preis(buch.leihgebuehr));
    // Weiter geht es mit den Jahrgängen - die Buchreihe ist vollständig.
    const jahrgang = menue.querySelector('[data-planung-zeile] [data-planung-feld="jahrgang"]');
    (jahrgang || feld).focus();
  }

  document.addEventListener("input", (ereignis) => {
    if (istVorschlagsfeld(ereignis.target)) zeigeVorschlaege(ereignis.target);
  });

  // mousedown statt click: sonst verliert das Feld zuerst den Fokus, die
  // Liste schließt sich (focusout unten), und der Klick ginge ins Leere.
  document.addEventListener("mousedown", (ereignis) => {
    const eintrag = ereignis.target.closest && ereignis.target.closest(".tt-suggestion");
    if (!eintrag) return;
    ereignis.preventDefault();
    const feld = eintrag.closest(".typeahead").querySelector("[data-vorschlag]");
    uebernimm(feld, eintrag);
  });

  document.addEventListener("focusout", (ereignis) => {
    if (istVorschlagsfeld(ereignis.target)) schliesseVorschlaege(ereignis.target);
  });

  document.addEventListener("keydown", (ereignis) => {
    const feld = ereignis.target;
    if (!istVorschlagsfeld(feld)) return;
    const liste = vorschlagsliste(feld);
    if (!liste) {
      if (ereignis.key === "ArrowDown") zeigeVorschlaege(feld);
      return;
    }
    const eintraege = [...liste.querySelectorAll(".tt-suggestion")];
    const jetzt = eintraege.findIndex((e) => e.classList.contains("tt-cursor"));
    if (ereignis.key === "ArrowDown" || ereignis.key === "ArrowUp") {
      ereignis.preventDefault();
      const schritt = ereignis.key === "ArrowDown" ? 1 : -1;
      const naechster = (jetzt + schritt + eintraege.length) % eintraege.length;
      eintraege.forEach((e, i) => e.classList.toggle("tt-cursor", i === naechster));
      eintraege[naechster].scrollIntoView({ block: "nearest" });
    } else if (ereignis.key === "Enter" && jetzt >= 0) {
      ereignis.preventDefault();
      uebernimm(feld, eintraege[jetzt]);
    } else if (ereignis.key === "Escape") {
      // Nur die Liste schließen, nicht das ganze Menü.
      ereignis.preventDefault();
      ereignis.stopPropagation();
      schliesseVorschlaege(feld);
    }
  });

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
    if (art === "buch-neu") { oeffneNeu(knopf); return; }
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
