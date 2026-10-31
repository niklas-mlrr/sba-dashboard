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
//   2. Liste bestätigen / Bestätigung zurückziehen: zwei Menüs im Kopf der
//      Fach-Ansicht (Kürzel und Datum bzw. nur die Rückfrage). Ob bestätigt
//      werden darf, entscheidet der Server.
//   3. Das Planungsmenü: ein Klick auf eine Buchzeile öffnet den Dialog mit
//      der Buchreihe (Titel, Verlag, Preise - korrigiert wird nur in
//      der Datei, nicht in IServ), Einführung, Ausmusterung und Rücklage
//      dieses Buchs in diesem Fach.
//      Gespeichert wird alles auf einmal - ein Menü, ein Knopf, eine Anfrage
//      (POST /api/buchplanung/buch). Abbrechen verwirft.
//   4. „+ Buch hinzufügen“ unter der Fach-Liste: dasselbe Menü mit freier
//      ISBN, deren Vorschläge die Bücher anderer Fächer sind
//      (POST /api/buchplanung/buch/neu).
//   5. Die Änderungsliste: ein Klick auf eine Jahrgangszeile öffnet ihr Buchmenü
//      (<template id="antrag-N">); darin Genehmigen, Ablehnen, Zurücksetzen
//      und die Begründung (POST /api/buchplanung/antrag). Kürzel und Datum
//      setzt der Server aus der IServ-Anmeldung. „Ersetzt durch …“ im Menü wechselt
//      zum Menü des Partners, ohne den Dialog zu schließen.
//
// Der Menü-Inhalt wird NICHT hier gebaut: er steht je Buch fertig gerendert in
// einem <template class="planung-vorlage"> (templates/_buchplanung.html) und
// wird beim Öffnen in den einen Dialog der Seite geklont. Eine zweite Fassung
// der Darstellung in JavaScript wäre genau die Doppelung, die mit der Vorlage
// auseinanderläuft.
//
// Die Menüs der Fach-Seite schicken den Eintrag mit, wie sie ihn beim Öffnen
// gesehen haben (``vorher``). Hat ihn inzwischen jemand anderes geändert,
// antwortet der Server mit 409 und dem neuen Stand, und das Menü
// „Unterschiede“ legt beide nebeneinander (``dreiwege``). Ein 409 ohne neuen
// Stand (die Anträge-Seite vergleicht noch die ganze Datei) lädt nach.
//
// Eine Ausnahme von "rechnet nichts": was ein Klick auf „Leihbar“ in einer
// Zeile des Menüs bewirkt (leihbarSchritt). Das ist Formularbearbeitung - es
// entsteht eine Zeile oder fällt weg -, und man soll sie vor dem Speichern
// sehen. Ob das Ergebnis zulässig ist (keine zwei Zeilen zur selben Zeit),
// prüft trotzdem der Server.

// „leihbar“ gilt je Zeile. Ein Klick auf das Häkchen der Zeile ``nummer``:
//
//   teilen     - die Zeile galt schon vor diesem Schuljahr (``alt``): sie
//                bleibt, wie sie war, endet aber mit dem Vorjahr; darunter
//                beginnt mit dem Schuljahr eine neue mit umgeschaltetem Häkchen.
//   zurueck    - die Zeile beginnt mit diesem oder einem künftigen Schuljahr,
//                und es gibt ihre Vorgängerin (gleicher Jahrgang, endet genau
//                im Jahr vor ihrer Einführung, schon mit dem gewünschten
//                Häkchen): die Zeile fällt weg, und die Vorgängerin läuft weiter.
//   umschalten - sonst (eine künftige oder neue Zeile): nur das Häkchen.
//
// ``zeilen`` stehen da, wie vor dem Klick: {jahrgang, eingefuehrt_ab,
// ausgemustert_nach, leihbar, alt}. Rein, ohne DOM - geprüft mit node
// (tests/test_buchplanung_js.py).
const leihbarSchritt = (function () {
  function jahr(text) {
    const treffer = /^\s*(\d{4})/.exec(text || "");
    return treffer ? Number(treffer[1]) : null;
  }
  return function (zeilen, nummer, schuljahr) {
    const zeile = zeilen[nummer];
    if (zeile.alt) return { art: "teilen" };
    const jetzt = jahr(schuljahr);
    const gewuenscht = !zeile.leihbar;
    const beginn = jahr(zeile.eingefuehrt_ab);
    if (jetzt !== null && beginn !== null && beginn >= jetzt) {
      const vorgaenger = zeilen.findIndex((andere, i) => i !== nummer
        && andere.jahrgang === zeile.jahrgang && andere.leihbar === gewuenscht
        && jahr(andere.ausgemustert_nach) === beginn - 1);
      if (vorgaenger >= 0) return { art: "zurueck", vorgaenger: vorgaenger };
    }
    return { art: "umschalten" };
  };
})();

// Hat jemand anderes einen Eintrag geändert, während sein Menü hier offen war,
// liegen drei Stände vor: ``vorher`` (was das Menü beim Öffnen gesehen hat),
// ``aktuell`` (was jetzt in der Datei steht) und ``eingabe`` (was hier
// eingetragen wurde). Alle drei sind Schnappschüsse derselben Form
// (``eintrag_stand``/``fach_stand`` in app/planungsansicht.py): Feldgruppen
// (``buchreihe``, ``ruecklage``, ``fach``) und ``zeilen``, geschlüsselt nach
// „Jahrgang|Einführung“.
//
// Je Feld - und je Zeile, wenn eine Seite sie gar nicht hat:
//   gleich in aktuell und eingabe   -> das gilt,
//   nur hier geändert               -> die Eingabe gilt,
//   nur dort geändert               -> der neue Stand gilt,
//   beide geändert, verschieden     -> ein Konflikt: das Menü „Unterschiede“
//                                      fragt, vorgewählt ist die Eingabe.
// ``mitWahl`` setzt die Antworten ein. Rein, ohne DOM - geprüft mit node
// (tests/test_buchplanung_js.py).
const dreiwege = (function () {
  function stabil(wert) {
    if (wert === undefined || wert === null) return "null";
    if (typeof wert !== "object") return JSON.stringify(wert);
    return "{" + Object.keys(wert).sort()
      .filter((k) => wert[k] !== undefined)
      .map((k) => JSON.stringify(k) + ":" + stabil(wert[k])).join(",") + "}";
  }
  const gleich = (a, b) => stabil(a) === stabil(b);
  // ``{wert}`` - so ist es entschieden; ``null`` - ein Konflikt.
  function entscheide(v, a, e) {
    if (gleich(a, e)) return { wert: a };
    if (gleich(v, a)) return { wert: e };
    if (gleich(v, e)) return { wert: a };
    return null;
  }
  const alle = (...teile) => [...new Set(teile.flatMap((t) => Object.keys(t || {})))];

  return function (vorher, aktuell, eingabe) {
    vorher = vorher || {};
    aktuell = aktuell || {};
    eingabe = eingabe || {};
    const ergebnis = {};
    const konflikte = [];
    for (const gruppe of alle(vorher, aktuell, eingabe)) {
      const v = vorher[gruppe];
      const a = aktuell[gruppe];
      const e = eingabe[gruppe];
      if (gruppe === "zeilen") {
        ergebnis.zeilen = {};
        for (const schluessel of alle(v, a, e)) {
          const zv = (v || {})[schluessel];
          const za = (a || {})[schluessel];
          const ze = (e || {})[schluessel];
          const ganz = entscheide(zv, za, ze);
          if (ganz) {
            if (ganz.wert !== undefined && ganz.wert !== null) ergebnis.zeilen[schluessel] = ganz.wert;
            continue;
          }
          if (zv && za && ze) {
            const zeile = {};
            for (const feld of alle(zv, za, ze)) {
              const eins = entscheide(zv[feld], za[feld], ze[feld]);
              if (eins) {
                zeile[feld] = eins.wert;
              } else {
                zeile[feld] = ze[feld];
                konflikte.push({ pfad: ["zeilen", schluessel, feld], neu: za[feld], deins: ze[feld], zeile: za });
              }
            }
            ergebnis.zeilen[schluessel] = zeile;
          } else {
            if (ze) ergebnis.zeilen[schluessel] = ze;
            konflikte.push({ pfad: ["zeilen", schluessel], neu: za, deins: ze, zeile: za || ze });
          }
        }
        continue;
      }
      if ((a === null || a === undefined) && (e === null || e === undefined)) {
        ergebnis[gruppe] = null;
        continue;
      }
      const felder = {};
      for (const feld of alle(v, a, e)) {
        const vv = (v || {})[feld];
        const aa = (a || {})[feld];
        const ee = (e || {})[feld];
        const eins = entscheide(vv, aa, ee);
        if (eins) {
          felder[feld] = eins.wert;
        } else {
          felder[feld] = ee;
          konflikte.push({ pfad: [gruppe, feld], neu: aa, deins: ee });
        }
      }
      ergebnis[gruppe] = felder;
    }
    return { ergebnis: ergebnis, konflikte: konflikte };
  };
})();

// ``wahl[i]`` ist "neu" oder "deins" für ``konflikte[i]``.
function mitWahl(ergebnis, konflikte, wahl) {
  const stand = JSON.parse(JSON.stringify(ergebnis));
  konflikte.forEach((konflikt, i) => {
    if (wahl[i] !== "neu") return;
    let ziel = stand;
    for (const teil of konflikt.pfad.slice(0, -1)) {
      if (ziel[teil] === undefined || ziel[teil] === null) ziel[teil] = {};
      ziel = ziel[teil];
    }
    const letzter = konflikt.pfad[konflikt.pfad.length - 1];
    if (konflikt.neu === undefined) delete ziel[letzter];
    else ziel[letzter] = konflikt.neu;
  });
  return stand;
}

// Wie ein Konflikt im Menü „Unterschiede“ dasteht: was, und beide Werte als Text.
const beschreibe = (function () {
  const namen = {
    "buchreihe.titel": "Titel", "buchreihe.verlag": "Verlag",
    "buchreihe.neupreis": "Neupreis", "buchreihe.leihgebuehr": "Leihgebühr",
    "buchreihe.bemerkung": "Bemerkung zum Buch",
    "ruecklage.anzahl": "Rücklage: Exemplare", "ruecklage.bemerkung": "Rücklage: Bemerkung",
    "fach.kuerzel": "Kürzel", "fach.datum": "Datum",
  };
  const zeilenfelder = {
    jahrgang: "Jahrgang", leihbar: "Leihbar", eingefuehrt_ab: "Einführung",
    ausgemustert_nach: "Ausmusterung", bemerkung: "Bemerkung",
  };
  function wert(feld, inhalt) {
    if (inhalt === undefined || inhalt === null || inhalt === "") return "–";
    if (inhalt === true) return "ja";
    if (inhalt === false) return "nein";
    if (feld === "neupreis" || feld === "leihgebuehr") {
      return Number(inhalt).toFixed(2).replace(".", ",") + " €";
    }
    if (feld === "datum") {
      const teile = /^(\d{4})-(\d{2})-(\d{2})$/.exec(inhalt);
      if (teile) return teile[3] + "." + teile[2] + "." + teile[1];
    }
    return String(inhalt);
  }
  function zeilenname(zeile) {
    if (!zeile) return "Jahrgang";
    return "Jg. " + zeile.jahrgang + (zeile.eingefuehrt_ab ? " (ab " + zeile.eingefuehrt_ab + ")" : "");
  }
  function zeilentext(zeile) {
    if (!zeile) return "nicht vorhanden";
    const teile = ["Jg. " + zeile.jahrgang];
    if (zeile.eingefuehrt_ab) teile.push("ab " + zeile.eingefuehrt_ab);
    if (zeile.ausgemustert_nach) teile.push("bis " + zeile.ausgemustert_nach);
    teile.push(zeile.leihbar ? "leihbar" : "Kaufbuch");
    if (zeile.bemerkung) teile.push(zeile.bemerkung);
    return teile.join(", ");
  }
  return function (konflikt) {
    const pfad = konflikt.pfad;
    if (pfad[0] === "zeilen" && pfad.length === 2) {
      return { feld: zeilenname(konflikt.zeile), neu: zeilentext(konflikt.neu),
               deins: zeilentext(konflikt.deins) };
    }
    if (pfad[0] === "zeilen") {
      return { feld: zeilenname(konflikt.zeile) + ": " + (zeilenfelder[pfad[2]] || pfad[2]),
               neu: wert(pfad[2], konflikt.neu), deins: wert(pfad[2], konflikt.deins) };
    }
    return { feld: namen[pfad.join(".")] || pfad.join("."),
             neu: wert(pfad[1], konflikt.neu), deins: wert(pfad[1], konflikt.deins) };
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = { leihbarSchritt, dreiwege, mitWahl, beschreibe, teilungInProzent };
}

// In der Bücherliste steht „Leihbar“ halb, wenn das Buch in den Jahrgängen
// einer Zeile teils leihbar ist, teils nicht. Halb gibt es nur als
// Eigenschaft, nicht als Attribut - die Vorlage setzt ``data-teilweise``.
if (typeof document !== "undefined") {
  for (const feld of document.querySelectorAll("input.nur-lesen[data-teilweise]")) {
    feld.indeterminate = true;
  }
}

// Ist ein Buch teils leihbar, teils nicht, stehen in „Leihbar“ und „Jahrgang“
// je zwei Teilzeilen (.teilzeile in buecherliste_gruppe.html). Die beiden
// Teilzeilen einer Gruppe sind gleich hoch - die Gruppen untereinander nicht
// (Entscheidung 2026-10-31). Das kann CSS über zwei Zellen hinweg nicht, also
// misst es dieses Skript: beim Laden und wenn sich die Breite ändert. Die
// letzte Gruppe reicht bis zum Boden der Zeile, falls die höher ist (etwa
// durch einen umgebrochenen Titel).
function gleicheTeilzeilenAn() {
  for (const zeile of document.querySelectorAll("tr")) {
    const zellen = [...zeile.querySelectorAll(":scope > td.teilzeilen")];
    if (zellen.length < 2) continue;
    const spalten = zellen.map((zelle) => [...zelle.querySelectorAll(":scope > .teilzeile")]);
    for (const teile of spalten) for (const teil of teile) teil.style.minHeight = "";
    const anzahl = Math.min(...spalten.map((teile) => teile.length));
    let summe = 0;
    for (let i = 0; i < anzahl; i += 1) {
      const hoehe = Math.max(...spalten.map((teile) => teile[i].getBoundingClientRect().height));
      for (const teile of spalten) teile[i].style.minHeight = hoehe + "px";
      summe += hoehe;
    }
    const rest = zellen[0].getBoundingClientRect().height - summe;
    if (rest > 0 && anzahl) {
      for (const teile of spalten) {
        teile[anzahl - 1].style.minHeight = parseFloat(teile[anzahl - 1].style.minHeight) + rest + "px";
      }
    }
  }
  teileStricheAn();
}

// Haben die beiden Teilzeilen einer Zeile je genau eine, verschiedene Farbe,
// teilt sich der Strich vorn an ihrer Grenze (``data-strich-teile``, gesetzt
// von der Vorlage nach ``Markierung.strich_teile``): ``--teilung`` ist die
// Höhe der oberen Teilzeile in Prozent der Zeile. Ohne dieses Skript 50 %.
function teilungInProzent(oben, gesamt) {
  if (typeof oben !== "number" || !(gesamt > 0) || !(oben >= 0)) return 50;
  return Math.round(Math.min(100, (oben / gesamt) * 100) * 1000) / 1000;
}

function teileStricheAn() {
  for (const zeile of document.querySelectorAll("tr[data-strich-teile]")) {
    const oben = zeile.querySelector(":scope > td.teilzeilen > .teilzeile");
    if (!oben) continue;
    const prozent = teilungInProzent(oben.getBoundingClientRect().height,
                                     zeile.getBoundingClientRect().height);
    zeile.style.setProperty("--teilung", prozent + "%");
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  gleicheTeilzeilenAn();
  let geplant = false;
  window.addEventListener("resize", () => {
    if (geplant) return;
    geplant = true;
    window.requestAnimationFrame(() => {
      geplant = false;
      gleicheTeilzeilenAn();
    });
  });
}

(function () {
  if (typeof document === "undefined") return;
  const wurzel = document.getElementById("buchplanung");
  if (!wurzel) return;
  const schuljahr = wurzel.dataset.schuljahr;
  const menue = document.getElementById("planungsmenue");
  const leerzeile = document.getElementById("planung-leerzeile");
  const fehlermenue = document.getElementById("fehlermenue");

  // ── Meldungen ─────────────────────────────────────────────────────────────
  //
  // Eine Zeile mit Meldungen unter dem Kopf gibt es nicht (Entscheidung
  // 2026-10-30). Was ein Menü meldet - eine fehlende Eingabe, eine Ablehnung
  // durch den Server -, steht rot in dessen Fuß, über den Knöpfen. Alles
  // andere (Server nicht erreichbar, Datei geändert, Abgleich gescheitert)
  // öffnet das Fehlermenü; ``danach`` läuft, wenn es geschlossen wird.

  function meldeImMenue(dialog, text) {
    const ziel = dialog && dialog.querySelector("[data-planung-meldung]");
    if (!ziel) {
      if (text) zeigeFehler(text);
      return;
    }
    nimmWarnungZurueck(dialog);
    ziel.textContent = text;
    // Nur die Fehlerklasse setzen: welche Grundklassen die Stelle trägt, sagt
    // die Vorlage, nicht dieses Skript.
    ziel.classList.add("fehlerhaft");
    ziel.hidden = !text;
  }

  // Würde das Speichern die Bestätigung der Liste kosten, schreibt der Server
  // nicht, sondern nennt die Gründe. Dann steht über den Knöpfen gelb, woran
  // es liegt, und „Speichern“ heißt „Trotzdem speichern“. Jede Änderung im
  // Menü nimmt das zurück; beim nächsten Speichern fragt der Server neu.
  function zeigeWarnung(dialog, gruende) {
    const ziel = dialog.querySelector("[data-planung-meldung]");
    const knopf = dialog.querySelector(".modal-footer .btn-primary");
    ziel.textContent = "Die Bestätigung der Liste verfällt durch: " + gruende.join("; ") +
      ". Trotzdem speichern?";
    ziel.classList.remove("fehlerhaft");
    ziel.classList.add("warnung");
    ziel.hidden = false;
    if (!knopf.dataset.text) knopf.dataset.text = knopf.textContent;
    knopf.textContent = "Trotzdem speichern";
    dialog.dataset.verfallOk = "1";
  }

  function nimmWarnungZurueck(dialog) {
    if (!dialog || !dialog.dataset.verfallOk) return;
    delete dialog.dataset.verfallOk;
    const ziel = dialog.querySelector("[data-planung-meldung]");
    const knopf = dialog.querySelector(".modal-footer .btn-primary");
    ziel.classList.remove("warnung");
    ziel.textContent = "";
    ziel.hidden = true;
    if (knopf.dataset.text) knopf.textContent = knopf.dataset.text;
  }

  for (const art of ["input", "change"]) {
    document.addEventListener(art, (ereignis) => {
      const dialog = ereignis.target.closest && ereignis.target.closest("dialog");
      if (dialog && !dialog.dataset.speichert) nimmWarnungZurueck(dialog);
    }, true);
  }

  let nachDemFehler = null;
  function zeigeFehler(text, danach) {
    if (!fehlermenue) {
      window.alert(text);
      if (danach) danach();
      return;
    }
    fehlermenue.querySelector("[data-fehlermenue-text]").textContent = text;
    nachDemFehler = danach || null;
    if (!fehlermenue.open) fehlermenue.showModal();
  }

  if (fehlermenue) {
    fehlermenue.addEventListener("close", () => {
      const danach = nachDemFehler;
      nachDemFehler = null;
      if (danach) danach();
    });
    if (fehlermenue.hasAttribute("data-sofort")) fehlermenue.showModal();
  }

  // Während gespeichert wird, liegt über dem Menü ein grauer Schleier mit
  // „Wird gespeichert…“ in der Mitte; darunter lässt sich nichts ändern. Ohne
  // Menü (der Abgleich aus der Kopfzeile) deckt er die ganze Seite ab.
  function verschleiere(dialog, text) {
    const schleier = document.createElement("div");
    schleier.className = dialog ? "speicher-schleier" : "speicher-schleier seiten-schleier";
    schleier.setAttribute("role", "status");
    const satz = document.createElement("span");
    satz.textContent = text;
    schleier.appendChild(satz);
    const gesperrt = dialog ? [...dialog.children] : [];
    for (const teil of gesperrt) teil.inert = true;
    if (dialog) dialog.dataset.speichert = "1";
    (dialog || document.body).appendChild(schleier);
    return {
      text(neu) { satz.textContent = neu; },
      weg() {
        schleier.remove();
        for (const teil of gesperrt) teil.inert = false;
        if (dialog) delete dialog.dataset.speichert;
      },
    };
  }

  // Escape schließt ein Menü - aber nicht, während es speichert.
  document.addEventListener("cancel", (ereignis) => {
    if (ereignis.target.dataset && ereignis.target.dataset.speichert) ereignis.preventDefault();
  }, true);

  function mtime() {
    const wert = parseFloat(wurzel.dataset.mtime);
    return Number.isFinite(wert) ? wert : null;
  }

  // Der Server schickt den ganzen neuen Stand zurück. Statt ihn hier Zelle für
  // Zelle einzubauen - Statuslabel, Jahrgang-Spalte, Übersichtszähler -, wird
  // die Seite neu geladen: sie liest ohnehin Datei und IServ neu, und der eine
  // zusätzliche Aufruf ist billiger als eine zweite Fassung der Darstellung,
  // die mit der Vorlage auseinanderlaufen kann.
  //
  // ``dialog`` ist das Menü, aus dem gespeichert wird (oder ``null``): dort
  // liegt der Schleier, dort stehen Eingabefehler (400). Alles andere geht ins
  // Fehlermenü - außer zwei Antworten, nach denen das Menü fragt:
  //   ``warnung``  - die Bestätigung der Liste würde verfallen (zeigeWarnung);
  //   ``konflikt`` - der Eintrag wurde inzwischen geändert: ``beiKonflikt``
  //                  bekommt den neuen Stand und legt ihn neben die Eingabe.
  async function sende(pfad, koerper, dialog, beiKonflikt) {
    if (dialog && dialog.dataset.verfallOk) koerper = Object.assign({ verfall_ok: true }, koerper);
    const stand = mtime();
    if (stand === null && pfad !== "/api/buchplanung/abgleich") {
      meldeImMenue(dialog, "Für dieses Schuljahr ist noch nichts gespeichert. Bitte zuerst " +
                           "„Aus IServ aktualisieren“.");
      return;
    }
    meldeImMenue(dialog, "");
    const schleier = verschleiere(dialog, dialog ? "Wird gespeichert…" : "Wird aus IServ aktualisiert…");
    let antwort;
    let daten;
    try {
      antwort = await fetch(pfad, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ schuljahr: schuljahr, mtime: stand }, koerper)),
      });
      daten = await antwort.json().catch(() => ({}));
    } catch (fehler) {
      schleier.weg();
      zeigeFehler("Der Server ist nicht erreichbar: " + fehler);
      return;
    }
    if (antwort.status === 409 && "konflikt" in daten && beiKonflikt) {
      schleier.weg();
      beiKonflikt(daten.konflikt);
      return;
    }
    if (antwort.status === 409) {
      schleier.weg();
      zeigeFehler("Die Datei wurde inzwischen geändert. Die Seite wird neu geladen.",
                  () => window.location.reload());
      return;
    }
    if (!antwort.ok) {
      schleier.weg();
      const text = daten.fehler || "Das Speichern ist fehlgeschlagen.";
      if (antwort.status === 400 && dialog) meldeImMenue(dialog, text);
      else zeigeFehler(text);
      return;
    }
    if (daten.warnung && dialog) {
      schleier.weg();
      zeigeWarnung(dialog, daten.warnung);
      return;
    }
    wurzel.dataset.mtime = daten.mtime;
    schleier.text(dialog ? "Gespeichert" : "Aus IServ übernommen");
    setTimeout(() => window.location.reload(), 600);
  }

  function heute() {
    const jetzt = new Date();
    return jetzt.getFullYear() + "-" + String(jetzt.getMonth() + 1).padStart(2, "0") + "-" +
      String(jetzt.getDate()).padStart(2, "0");
  }

  // ── Werte aus einer Gruppe von Feldern einsammeln ─────────────────────────

  function felder(bereich) {
    const werte = {};
    for (const feld of bereich.querySelectorAll("[data-planung-feld]")) {
      werte[feld.dataset.planungFeld] = feld.type === "checkbox" ? feld.checked : feld.value.trim();
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
    // Der Eintrag, wie das Menü ihn jetzt zeigt - er geht beim Speichern mit.
    menue.dataset.vorher = vorlage.dataset.vorher || "null";
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

  // Das Buchmenü der Änderungsliste. Steht der Dialog schon offen (Sprung zum
  // Partner), wird nur sein Inhalt getauscht - showModal() auf einen offenen
  // Dialog wirft.
  function oeffneAntrag(knopf) {
    const vorlage = document.getElementById(knopf.dataset.vorlage);
    if (!menue || !vorlage) return;
    zeigeMenue(vorlage);
    if (!menue.open) menue.showModal();
  }

  // „+ Buch hinzufügen“: dasselbe Menü, ohne Buch. Die ISBN kommt beim
  // Speichern aus dem Feld, nicht aus der Zeile; eine erste leere
  // Jahrgangszeile steht schon da, denn ohne Jahrgang gibt es nichts zu speichern.
  function oeffneNeu(knopf) {
    const vorlage = document.getElementById("planung-neu-vorlage");
    if (!menue || !vorlage) return;
    zeigeMenue(vorlage);
    delete menue.dataset.isbn;
    delete menue.dataset.vorher;
    menue.dataset.fach = knopf.dataset.fach;
    menue.dataset.neu = "1";
    menue.showModal();
    const koerper = menue.querySelector("[data-planung-zeilen]");
    if (koerper && leerzeile) koerper.appendChild(leerzeile.content.cloneNode(true));
    messeBemerkungen(menue);
    menue.querySelector('[data-buchreihe-feld="isbn"]').focus();
  }

  // Eine neue Zeile übernimmt „leihbar“ von der letzten der Tabelle - meist
  // ist ein Buch in allen Jahrgängen gleich.
  function fuegeJahrgangAn(knopf) {
    const koerper = knopf.closest(".planung-block").querySelector("[data-planung-zeilen]");
    if (!koerper || !leerzeile) return;
    const vorige = [...koerper.querySelectorAll("[data-planung-zeile]")].pop();
    koerper.appendChild(leerzeile.content.cloneNode(true));
    const zeile = koerper.lastElementChild;
    if (vorige) {
      zeile.querySelector('[data-planung-feld="leihbar"]').checked =
        vorige.querySelector('[data-planung-feld="leihbar"]').checked;
    }
    messeBemerkungen(zeile);
    zeile.querySelector('[data-planung-feld="jahrgang"]').focus();
  }

  // ── „Leihbar“ je Zeile (Regel oben: leihbarSchritt) ───────────────────────

  function vorjahrText() {
    if (wurzel.dataset.vorjahr) return wurzel.dataset.vorjahr;
    const jahr = parseInt(wurzel.dataset.planungsjahr, 10);
    return Number.isFinite(jahr) ? (jahr - 1) + "/" + jahr : "";
  }

  function feldIn(zeile, name) {
    return zeile.querySelector('[data-planung-feld="' + name + '"]');
  }

  function schalteLeihbar(feld) {
    const zeile = feld.closest("[data-planung-zeile]");
    const koerper = zeile.closest("[data-planung-zeilen]");
    const alle = [...koerper.querySelectorAll("[data-planung-zeile]")];
    const daten = alle.map((tr) => {
      const werte = felder(tr);
      return {
        jahrgang: Number(werte.jahrgang), eingefuehrt_ab: werte.eingefuehrt_ab || "",
        ausgemustert_nach: werte.ausgemustert_nach || "",
        // Das angeklickte Häkchen steht schon um; gefragt ist der Stand davor.
        leihbar: tr === zeile ? !feld.checked : Boolean(werte.leihbar),
        alt: "alt" in tr.dataset,
      };
    });
    const schritt = leihbarSchritt(daten, alle.indexOf(zeile), wurzel.dataset.planungsjahr);
    const ausmusterung = feldIn(zeile, "ausgemustert_nach");

    if (schritt.art === "teilen" && leerzeile) {
      const gewuenscht = feld.checked;
      const bisher = ausmusterung.value;
      feld.checked = !gewuenscht;
      feld.disabled = true;
      feld.title = "ausgemustert - nicht mehr umschaltbar";
      ausmusterung.value = vorjahrText();
      const neue = leerzeile.content.firstElementChild.cloneNode(true);
      feldIn(neue, "jahrgang").value = daten[alle.indexOf(zeile)].jahrgang;
      feldIn(neue, "leihbar").checked = gewuenscht;
      feldIn(neue, "eingefuehrt_ab").value = wurzel.dataset.planungsjahr || "";
      feldIn(neue, "ausgemustert_nach").value = bisher;
      zeile.after(neue);
      messeBemerkungen(neue);
    } else if (schritt.art === "zurueck") {
      const vorgaenger = alle[schritt.vorgaenger];
      feldIn(vorgaenger, "ausgemustert_nach").value = ausmusterung.value;
      const haekchen = feldIn(vorgaenger, "leihbar");
      haekchen.disabled = false;
      haekchen.removeAttribute("title");
      zeile.remove();
    }
  }

  document.addEventListener("change", (ereignis) => {
    const feld = ereignis.target;
    if (menue && menue.contains(feld) && feld.dataset && feld.dataset.planungFeld === "leihbar") {
      schalteLeihbar(feld);
    }
  });

  // ── Die Bemerkung: eine Zeile hoch, beim Tippen so hoch wie ihr Text ──────
  //
  // Eingeklappt ist sie eine Zeile hoch und zeigt eine Vorschau: den Text ohne
  // Umbrüche, mit "…", wenn er nicht in die Zeile passt (das CSS legt sie über
  // das Feld). Beim Anklicken wächst sie nach unten, damit man den ganzen Text
  // liest; beim Verlassen klappt sie wieder ein. Ohne das "…" wäre eine lange
  // Bemerkung von einer kurzen nicht zu unterscheiden.
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
    if (!rahmen) return;
    let vorschau = rahmen.querySelector(".planung-bemerkung-vorschau");
    if (!vorschau) {
      vorschau = document.createElement("span");
      vorschau.className = "planung-bemerkung-vorschau";
      vorschau.setAttribute("aria-hidden", "true");
      rahmen.appendChild(vorschau);
      rahmen.classList.add("mit-vorschau");
    }
    // Nur die Anzeige: gespeichert wird der Wert des Feldes, samt Umbrüchen.
    vorschau.textContent = feld.value.replace(/\s+/g, " ").trim();
  }

  function messeBemerkungen(bereich) {
    for (const feld of bereich.querySelectorAll(".planung-bemerkung")) klappeEin(feld);
  }

  // Gesperrte Felder liest felder() als leeren Text - genau richtig: ein
  // Kaufbuch wird nicht ausgemustert, und der Server weist es ohnehin ab.
  //
  // Neben dem Körper der Anfrage kommt die Eingabe als Schnappschuss zurück -
  // in derselben Form wie ``vorher`` (``eintrag_stand``), für den Abgleich,
  // falls jemand anderes den Eintrag inzwischen geändert hat. Eine Zeile ist
  // darin über die Zeile der Datei geschlüsselt, aus der sie kam
  // (``data-bisher-jahrgang``/``-ab``); eine neue bekommt einen eigenen Schlüssel.
  function sammle() {
    const zeilen = [];
    const eingabeZeilen = {};
    let nummer = 0;
    for (const zeile of menue.querySelectorAll("[data-planung-zeile]")) {
      const werte = felder(zeile);
      const jahrgang = Number(werte.jahrgang);
      // Eine Leerzeile, in die niemand etwas eingetragen hat, wird still
      // verworfen - "+ Jahrgang" einmal zu oft gedrückt ist kein Fehler.
      if (!werte.jahrgang) {
        if (werte.eingefuehrt_ab || werte.ausgemustert_nach || werte.bemerkung) {
          meldeImMenue(menue, "Bitte zu jeder Zeile den Jahrgang eintragen.");
          return undefined;
        }
        continue;
      }
      const bekannt = "bisherAb" in zeile.dataset;
      const eintrag = {
        jahrgang: jahrgang,
        leihbar: Boolean(werte.leihbar),
        eingefuehrt_ab: werte.eingefuehrt_ab || "",
        ausgemustert_nach: werte.ausgemustert_nach || "",
        bemerkung: werte.bemerkung || "",
      };
      zeilen.push(Object.assign({
        // Welche Zeile das war: ihre Einführung beim Öffnen. Eine neue Zeile
        // hat keine (``neu``) - ein Jahrgang kann mehrere Zeilen haben.
        bisher_ab: bekannt ? zeile.dataset.bisherAb : null,
        neu: !bekannt,
      }, eintrag));
      const schluessel = bekannt ? zeile.dataset.bisherJahrgang + "|" + zeile.dataset.bisherAb
        : "neu:" + (nummer += 1);
      eingabeZeilen[schluessel] = eintrag;
    }
    // Den Rücklage-Block gibt es nur bei leihbaren Büchern; fehlt er, wird
    // auch nichts über Rücklagen behauptet (``ruecklage: null``).
    const anzahlfeld = menue.querySelector(".planung-ruecklage");
    const block = anzahlfeld ? anzahlfeld.closest(".planung-block") : null;
    const werte = block ? felder(block) : {};
    const reihe = buchreihe();
    if (reihe === undefined) return undefined;
    const ruecklage = block === null ? null : {
      anzahl: werte.anzahl === "" ? null : Number(werte.anzahl),
      bemerkung: werte.bemerkung || "",
    };
    // Die ISBN gehört nicht zur Buchreihe, die verglichen wird: beim
    // Hinzufügen ist sie die Wahl des Buchs, bei „ISBN folgt“ wird sie
    // nachgetragen (``nachgetragen``), sonst steht sie gesperrt da.
    const isbn = reihe.isbn || "";
    delete reihe.isbn;
    return {
      zeilen: zeilen, buchreihe: reihe, ruecklage: ruecklage, isbn: isbn,
      nachgetragen: menue.dataset.neu ? "" : isbn,
      eingabe: { buchreihe: reihe, zeilen: eingabeZeilen, ruecklage: ruecklage },
    };
  }

  function speichere() {
    const gesammelt = sammle();
    if (gesammelt === undefined) return;
    if (menue.dataset.neu) {
      if (!gesammelt.zeilen.length) {
        meldeImMenue(menue, "Bitte mindestens einen Jahrgang eintragen.");
        return;
      }
      // Ohne mtime: das Menü ändert keinen bestehenden Eintrag, also stört
      // es nicht, was andere inzwischen an anderen Büchern gespeichert haben.
      sende("/api/buchplanung/buch/neu", {
        isbn: gesammelt.isbn, fach: menue.dataset.fach, mtime: null,
        zeilen: gesammelt.zeilen, buchreihe: gesammelt.buchreihe,
      }, menue);
      return;
    }
    const vorher = JSON.parse(menue.dataset.vorher || "null");
    const pfad = "/api/buchplanung/buch";
    const grundlage = { isbn: menue.dataset.isbn, fach: menue.dataset.fach };
    sende(pfad, buchkoerper(gesammelt.eingabe, vorher, grundlage, gesammelt.zeilen,
                            gesammelt.nachgetragen), menue,
          (aktuell) => zeigeUnterschiede({
            pfad: pfad, vorher: vorher, aktuell: aktuell, eingabe: gesammelt.eingabe,
            koerper: (stand, basis) => buchkoerper(stand, basis, grundlage, null,
                                                   gesammelt.nachgetragen),
          }));
  }

  // Aus einem Stand (der Eingabe oder dem zusammengeführten) eine Anfrage. Die
  // Zeilen tragen als ``bisher_ab`` die Einführung, mit der sie in ``basis``
  // (dem Stand der Datei) stehen; was es dort nicht gibt, ist neu. ``zeilen``
  // gibt die Zeilen schon fertig vor - so, wie das Menü sie gesammelt hat.
  function buchkoerper(stand, basis, grundlage, zeilen, nachgetragen) {
    const buchreihe = Object.assign({}, stand.buchreihe, nachgetragen ? { isbn: nachgetragen } : {});
    if (zeilen) {
      return Object.assign({
        zeilen: zeilen, buchreihe: buchreihe, ruecklage: stand.ruecklage || null, vorher: basis,
      }, grundlage);
    }
    const bekannt = (basis && basis.zeilen) || {};
    const zusammengefuehrt = Object.entries(stand.zeilen || {}).map(([schluessel, zeile]) => ({
      jahrgang: zeile.jahrgang, leihbar: Boolean(zeile.leihbar),
      eingefuehrt_ab: zeile.eingefuehrt_ab || "", ausgemustert_nach: zeile.ausgemustert_nach || "",
      bemerkung: zeile.bemerkung || "",
      bisher_ab: schluessel in bekannt ? bekannt[schluessel].eingefuehrt_ab : null,
      neu: !(schluessel in bekannt),
    }));
    return Object.assign({
      zeilen: zusammengefuehrt, buchreihe: buchreihe, ruecklage: stand.ruecklage || null,
      vorher: basis,
    }, grundlage);
  }

  // ── Das Menü „Unterschiede“ ───────────────────────────────────────────────
  //
  // Hat jemand anderes den Eintrag inzwischen geändert, legt es den neuen
  // Stand (links) und die Eingabe (rechts) nebeneinander - nur dort, wo beide
  // ihn verschieden geändert haben; alles andere wird still zusammengeführt
  // (``dreiwege`` oben). „Übernehmen und speichern“ schickt das Ergebnis mit
  // dem neuen Stand als ``vorher``. Ändert ihn derweil wieder jemand, beginnt
  // es von vorn - mit dem eben Gewählten als Eingabe.
  const unterschiede = document.getElementById("unterschiede-menue");
  let abgleich = null;

  function zeigeUnterschiede(fall) {
    if (!unterschiede) {
      zeigeFehler("Dieser Eintrag wurde inzwischen geändert. Die Seite wird neu geladen.",
                  () => window.location.reload());
      return;
    }
    const { ergebnis, konflikte } = dreiwege(fall.vorher, fall.aktuell, fall.eingabe);
    abgleich = Object.assign({ ergebnis: ergebnis, konflikte: konflikte }, fall);
    unterschiede.querySelector("[data-unterschiede-text]").textContent = konflikte.length
      ? "Während dieses Menü offen war, wurde der Eintrag geändert. Bitte je Zeile " +
        "anhaken, was bleiben soll; alles andere wird zusammengeführt."
      : "Während dieses Menü offen war, wurde der Eintrag geändert. Die Änderungen " +
        "widersprechen sich nicht und werden zusammengeführt.";
    const koerper = unterschiede.querySelector("[data-unterschiede]");
    koerper.replaceChildren();
    konflikte.forEach((konflikt, i) => {
      const text = beschreibe(konflikt);
      const zeile = document.createElement("tr");
      const feld = document.createElement("td");
      feld.textContent = text.feld;
      zeile.appendChild(feld);
      for (const seite of ["neu", "deins"]) {
        const zelle = document.createElement("td");
        const label = document.createElement("label");
        const haken = document.createElement("input");
        haken.type = "checkbox";
        haken.dataset.konflikt = i;
        haken.dataset.seite = seite;
        haken.checked = seite === "deins";
        const wert = document.createElement("span");
        wert.textContent = text[seite];
        label.append(haken, wert);
        zelle.appendChild(label);
        zeile.appendChild(zelle);
      }
      koerper.appendChild(zeile);
    });
    unterschiede.querySelector("table").hidden = !konflikte.length;
    meldeImMenue(unterschiede, "");
    if (!unterschiede.open) unterschiede.showModal();
  }

  if (unterschiede) {
    // Je Unterschied genau ein Haken: der andere geht aus, und abwählen lässt
    // sich nur, indem man die andere Seite wählt.
    unterschiede.addEventListener("change", (ereignis) => {
      const haken = ereignis.target;
      if (!haken.dataset || haken.dataset.konflikt === undefined) return;
      if (!haken.checked) {
        haken.checked = true;
        return;
      }
      for (const anderer of unterschiede.querySelectorAll(
        '[data-konflikt="' + haken.dataset.konflikt + '"]')) {
        if (anderer !== haken) anderer.checked = false;
      }
    });
  }

  function speichereUnterschiede() {
    if (!abgleich) return;
    const wahl = abgleich.konflikte.map((_, i) => {
      const neu = unterschiede.querySelector('[data-konflikt="' + i + '"][data-seite="neu"]');
      return neu && neu.checked ? "neu" : "deins";
    });
    const stand = mitWahl(abgleich.ergebnis, abgleich.konflikte, wahl);
    const fall = abgleich;
    sende(fall.pfad, fall.koerper(stand, fall.aktuell), unterschiede, (aktuell) =>
      zeigeUnterschiede(Object.assign({}, fall, {
        vorher: fall.aktuell, aktuell: aktuell, eingabe: stand,
      })));
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
        meldeImMenue(menue, "Bitte einen gültigen Betrag eintragen (" +
                            feld.getAttribute("aria-label") + ").");
        feld.focus();
        return undefined;
      }
      // Die gesperrte ISBN eines Buchs geht nicht mit; nur die offene - beim
      // Hinzufügen und bei „ISBN folgt“. Ob sie gültig ist, prüft der Server.
      if (feld.disabled) continue;
      werte[feld.dataset.buchreiheFeld] = feld.value.trim();
    }
    // Die ISBN ist kein Pflichtfeld: ohne steht ein Buch unter „ISBN folgt“.
    const pflicht = [["titel", "den Titel"], ["verlag", "den Verlag"]];
    for (const [name, text] of pflicht) {
      if (!werte[name]) {
        meldeImMenue(menue, "Bitte " + text + " eintragen.");
        return undefined;
      }
    }
    const preis = (text) => (text === "" ? null : Number(text));
    return {
      isbn: werte.isbn, titel: werte.titel, verlag: werte.verlag,
      neupreis: preis(werte.neupreis), leihgebuehr: preis(werte.leihgebuehr),
      bemerkung: werte.bemerkung || "",
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
        if (buch.platzhalter || !gesucht || !ziffern(buch.isbn).startsWith(gesucht)) return;
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
    // Ein Buch unter „ISBN folgt“ wird über seinen Platzhalter gewählt - sonst
    // legte das Speichern ein zweites an.
    setze("isbn", buch.platzhalter ? buch.isbn : buch.isbn_anzeige);
    setze("titel", buch.titel);
    setze("verlag", buch.verlag);
    setze("neupreis", preis(buch.neupreis));
    setze("leihgebuehr", preis(buch.leihgebuehr));
    setze("bemerkung", buch.bemerkung || "");
    messeBemerkungen(bereich);
    // „Leihbar“ steht je Jahrgang: die Zeilen übernehmen, was das Buch sonst ist.
    for (const leihbar of menue.querySelectorAll('[data-planung-zeile] [data-planung-feld="leihbar"]')) {
      leihbar.checked = Boolean(buch.leihbar);
    }
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
    if (art === "antrag-menue") { oeffneAntrag(knopf); return; }
    if (art === "jahrgang-anfuegen") { fuegeJahrgangAn(knopf); return; }
    if (art === "jahrgang-entfernen") { knopf.closest("[data-planung-zeile]").remove(); return; }
    if (art === "abbrechen") { knopf.closest("dialog").close(); return; }
    if (art === "meldung-schliessen") { knopf.closest("dialog").close(); return; }
    if (art === "speichern") { speichere(); return; }

    if (art === "abgleich") {
      sende("/api/buchplanung/abgleich", {}, null);
      return;
    }

    // „Liste bestätigen“ und „Bestätigung zurückziehen“ im Kopf einer Fachliste.
    if (art === "menue-oeffnen") {
      const dialog = document.getElementById(knopf.dataset.menue);
      if (!dialog) return;
      meldeImMenue(dialog, "");
      const datum = dialog.querySelector('[data-planung-feld="datum"]');
      if (datum) datum.value = heute();
      dialog.showModal();
      const erstes = dialog.querySelector("input");
      if (erstes) erstes.focus();
      return;
    }
    if (art === "bestaetigen" || art === "zurueckziehen") {
      const dialog = knopf.closest("dialog");
      const werte = art === "bestaetigen" ? felder(dialog) : { kuerzel: "", datum: "" };
      if (art === "bestaetigen" && !werte.kuerzel) {
        meldeImMenue(dialog, "Bitte das Kürzel der Fachkonferenzleitung eintragen.");
        return;
      }
      if (art === "bestaetigen" && !werte.datum) {
        meldeImMenue(dialog, "Bitte das Datum der Bestätigung eintragen.");
        return;
      }
      const vorher = JSON.parse(dialog.dataset.vorher || "null");
      const pfad = "/api/buchplanung/fach";
      const fachkoerper = (stand, basis) => ({
        fach: dialog.dataset.fach, kuerzel: stand.fach.kuerzel || "",
        datum: stand.fach.datum || null, vorher: basis,
      });
      const eingabe = { fach: { kuerzel: werte.kuerzel, datum: werte.datum || null } };
      sende(pfad, fachkoerper(eingabe, vorher), dialog, (aktuell) => zeigeUnterschiede({
        pfad: pfad, vorher: vorher, aktuell: aktuell, eingabe: eingabe, koerper: fachkoerper,
      }));
      return;
    }
    if (art === "unterschiede-speichern") { speichereUnterschiede(); return; }

    if (art === "antrag") {
      const zeile = knopf.closest("[data-antrag]");
      const begruendung = zeile.querySelector('[data-antrag-feld="begruendung"]');
      // Ohne data-ergebnis (der Knopf „Speichern“ an der Begründung) bleibt
      // die Entscheidung, wie sie ist: null statt "".
      const ergebnis = "ergebnis" in knopf.dataset ? knopf.dataset.ergebnis : null;
      sende("/api/buchplanung/antrag", {
        isbn: zeile.dataset.isbn, fach: zeile.dataset.fach,
        jahrgang: Number(zeile.dataset.jahrgang), art: zeile.dataset.antrag,
        // Welche Zeile des Jahrgangs - nach einem Wechsel von „leihbar“ hat er zwei.
        eingefuehrt_ab: zeile.dataset.eingefuehrtAb === undefined ? null
          : zeile.dataset.eingefuehrtAb,
        ergebnis: ergebnis,
        begruendung: begruendung ? begruendung.value.trim() : null,
      }, knopf.closest("dialog"));
    }
  });

  // Die Bemerkung wächst beim Bearbeiten und klappt danach wieder ein.
  // "focusin"/"focusout" statt focus/blur: die steigen auf und kommen deshalb
  // auch an Feldern an, die erst später im Dialog stehen.
  document.addEventListener("focusin", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) passeHoeheAn(ereignis.target);
  });
  document.addEventListener("focusout", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) klappeEin(ereignis.target);
  });
  document.addEventListener("input", (ereignis) => {
    if (ereignis.target.classList.contains("planung-bemerkung")) passeHoeheAn(ereignis.target);
  });

  // Bemerkungen, die gleich auf der Seite stehen (die Begründungen der
  // Änderungsliste), bekommen ihre Vorschau schon beim Laden. Die in den
  // Menü-Vorlagen sind inert und werden hier nicht gefunden.
  messeBemerkungen(document);

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
