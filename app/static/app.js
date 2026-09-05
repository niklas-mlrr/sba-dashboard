// Oberfläche des Dashboards - Vanilla, kein Build-Schritt.
//
// Drei Teile, die sich nichts teilen außer der Tabelle:
//   1. Filtern und Sortieren - rein im Browser, die Tabelle ist vollständig
//      gerendert und eine Serverrunde je Tastendruck wäre auf dem Netzlaufwerk
//      spürbar.
//   2. Zellen ändern - eine Zahl pro Anfrage, mit der zuletzt gesehenen
//      Änderungszeit. Antwortet der Server mit 409, hat jemand anderes die
//      Mappe angefasst; dann wird nicht überschrieben, sondern nachgeladen.
//   3. Abruf aus IServ - Formular, dann Fortschritt pollen.
(function () {
  const tabelle = document.getElementById("tabelle");
  if (!tabelle) return;
  const koerper = tabelle.tBodies[0];
  const zeilen = Array.from(koerper.rows);
  const nurBedarf = document.getElementById("nur-bedarf");
  const suche = document.getElementById("suche");
  const sichtbar = document.getElementById("sichtbar");
  const bedarfGesamt = document.getElementById("bedarf-gesamt");
  const meldung = document.getElementById("meldung");

  // ── 1. Filtern und Sortieren ───────────────────────────────────────────────

  function anwenden() {
    const begriff = (suche.value || "").trim().toLowerCase();
    let anzahl = 0;
    for (const zeile of zeilen) {
      const passtBedarf = !nurBedarf.checked || zeile.dataset.bedarf === "1";
      const passtSuche = !begriff || zeile.dataset.suche.includes(begriff);
      const zeigen = passtBedarf && passtSuche;
      zeile.hidden = !zeigen;
      if (zeigen) anzahl++;
    }
    sichtbar.textContent = anzahl;
  }

  function zellwert(zeile, index, art) {
    const zelle = zeile.cells[index];
    const feld = zelle.querySelector("input");
    const text = (feld ? feld.value : zelle.textContent).trim();
    // Leer und "—" stehen für "kein Wert". Das gilt für Zahlen- wie für
    // Textspalten (Titel/ISBN rendern fehlende Werte ebenfalls als "—").
    // Ein einzelner Sentinelwert (z. B. NEGATIVE_INFINITY) reicht dafür nicht:
    // er verschiebt "kein Wert" nur an ein Ende der Zahlengeraden und springt
    // beim Umschalten der Richtung auf die andere Seite. Deshalb wird "leer"
    // separat markiert und im Vergleich unten fest ans Ende sortiert.
    if (art !== "zahl") {
      return { wert: text.toLowerCase(), leer: text === "" || text === "—" };
    }
    const zahl = parseInt(text, 10);
    return { wert: zahl, leer: Number.isNaN(zahl) };
  }

  tabelle.tHead.addEventListener("click", (ereignis) => {
    const kopf = ereignis.target.closest("th");
    if (!kopf) return;
    const index = Array.from(kopf.parentNode.cells).indexOf(kopf);
    const art = kopf.dataset.sort;
    const absteigend = kopf.getAttribute("aria-sort") === "ascending";
    for (const anderer of kopf.parentNode.cells) anderer.removeAttribute("aria-sort");
    kopf.setAttribute("aria-sort", absteigend ? "descending" : "ascending");

    const sortiert = zeilen.slice().sort((a, b) => {
      const links = zellwert(a, index, art);
      const rechts = zellwert(b, index, art);
      // "Kein Wert" bleibt in beiden Richtungen am Ende - unabhängig von
      // absteigend, damit ein Klick auf die Spalte die Leerzeilen nie nach
      // vorn wirft.
      if (links.leer !== rechts.leer) return links.leer ? 1 : -1;
      if (links.leer) return 0;
      if (links.wert < rechts.wert) return absteigend ? 1 : -1;
      if (links.wert > rechts.wert) return absteigend ? -1 : 1;
      return 0;
    });
    for (const zeile of sortiert) koerper.appendChild(zeile);
  });

  nurBedarf.addEventListener("change", anwenden);
  suche.addEventListener("input", anwenden);
  anwenden();

  // ── Meldungen ──────────────────────────────────────────────────────────────

  function zeige(text, art) {
    meldung.textContent = text;
    meldung.className = "hinweis meldung" + (art ? " " + art : "");
    meldung.hidden = !text;
  }

  function verstecke() {
    meldung.hidden = true;
  }

  // ── 2. Zellen ändern ───────────────────────────────────────────────────────

  function bedarfNeuZeichnen() {
    let summe = 0;
    for (const zeile of zeilen) {
      // Über die Klasse greifen statt über den Spaltenindex: der Index verschiebt
      // sich lautlos, wenn im Template eine Spalte eingefügt oder umsortiert wird.
      const wert = parseInt(zeile.querySelector(".bedarfszelle").textContent.trim(), 10);
      if (!Number.isNaN(wert) && wert > 0) summe += wert;
    }
    bedarfGesamt.textContent = summe;
  }

  function zeileAktualisieren(zeile, daten) {
    const bedarfszelle = zeile.querySelector(".bedarfszelle");
    bedarfszelle.textContent = daten.zu_bestellen === null ? "—" : daten.zu_bestellen;
    const bedarf = (daten.zu_bestellen || 0) > 0;
    bedarfszelle.classList.toggle("bedarf", bedarf);
    zeile.dataset.bedarf = bedarf ? "1" : "0";
    for (const feld of zeile.querySelectorAll(".zellwert")) {
      const wert = daten[feld.dataset.spalte];
      feld.value = wert === null || wert === undefined ? "" : wert;
      feld.dataset.gespeichert = feld.value;
    }
    bedarfNeuZeichnen();
    anwenden();
  }

  async function speichern(feld) {
    const zeile = feld.closest("tr");
    const vorher = feld.dataset.gespeichert ?? "";
    if (feld.value === vorher) return;

    feld.disabled = true;
    feld.classList.remove("fehlerhaft");
    try {
      const antwort = await fetch("/api/cell", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: zeile.dataset.key,
          spalte: feld.dataset.spalte,
          wert: feld.value,
          mtime: parseFloat(tabelle.dataset.mtime),
        }),
      });
      const koerper = await antwort.json().catch(() => ({}));

      if (antwort.ok) {
        tabelle.dataset.mtime = koerper.mtime;
        document.getElementById("geaendert").textContent = koerper.geaendert
          .replace("T", " ").slice(0, 16);
        zeileAktualisieren(zeile, koerper.zeile);
        verstecke();
        feld.classList.add("gespeichert");
        setTimeout(() => feld.classList.remove("gespeichert"), 1200);
        return;
      }

      // Zurück auf den zuletzt bestätigten Wert: die Mappe hat gewonnen.
      feld.value = vorher;
      feld.classList.add("fehlerhaft");
      if (antwort.status === 409) {
        zeige(koerper.fehler + " (Die Seite lädt gleich neu.)", "warnung");
        setTimeout(() => window.location.reload(), 2500);
      } else {
        zeige(koerper.fehler || "Die Änderung ließ sich nicht speichern.", "warnung");
      }
    } catch (fehler) {
      feld.value = vorher;
      feld.classList.add("fehlerhaft");
      zeige("Der Server antwortet nicht. Läuft das schwarze Fenster noch?", "warnung");
    } finally {
      feld.disabled = false;
    }
  }

  for (const feld of koerper.querySelectorAll(".zellwert")) {
    feld.dataset.gespeichert = feld.value;
    feld.addEventListener("change", () => speichern(feld));
    feld.addEventListener("keydown", (ereignis) => {
      if (ereignis.key === "Enter") feld.blur();
      if (ereignis.key === "Escape") {
        feld.value = feld.dataset.gespeichert ?? "";
        feld.blur();
      }
    });
  }

  // ── 3. Abruf aus IServ ─────────────────────────────────────────────────────

  const dialog = document.getElementById("abruf");
  const oeffnen = document.getElementById("abruf-oeffnen");
  const formular = document.getElementById("abruf-formular");
  const abbrechen = document.getElementById("abruf-abbrechen");
  const abrufFehler = document.getElementById("abruf-fehler");
  const starten = document.getElementById("abruf-starten");
  const fortschritt = document.getElementById("fortschritt");
  const fuellung = document.getElementById("fortschritt-fuellung");
  const fortschrittText = document.getElementById("fortschritt-text");
  const diagnosen = document.getElementById("diagnosen");

  oeffnen.addEventListener("click", () => {
    abrufFehler.hidden = true;
    dialog.showModal();
    document.getElementById("benutzer").focus();
  });
  abbrechen.addEventListener("click", () => dialog.close());

  function zeichneFortschritt(stand) {
    fortschritt.hidden = false;
    fuellung.style.width = (stand.fortschritt || 0) + "%";
    fortschrittText.textContent = stand.text || "";
    fortschritt.classList.toggle("fehlgeschlagen", Boolean(stand.fehler));

    diagnosen.innerHTML = "";
    const zeilenText = (stand.diagnosen || []).concat(stand.warnungen || []);
    for (const eintrag of zeilenText) {
      const li = document.createElement("li");
      li.textContent = eintrag;
      diagnosen.appendChild(li);
    }
    diagnosen.hidden = zeilenText.length === 0;
  }

  async function pollen() {
    const antwort = await fetch("/api/refresh/status");
    const stand = await antwort.json();
    zeichneFortschritt(stand);
    if (!stand.fertig) {
      setTimeout(pollen, 1000);
      return;
    }
    if (stand.fehler) {
      zeige(stand.fehler, "warnung");
      return;
    }
    const z = stand.zusammenfassung || {};
    fortschrittText.textContent =
      `Fertig: ${z.geaendert} Zellen aktualisiert, ${z.nachbestellungen} Titel nachzubestellen ` +
      `(${z.stueckzahl} Exemplare). Die Seite lädt gleich neu.`;
    setTimeout(() => window.location.reload(), 2000);
  }

  // ── 4. Beenden ─────────────────────────────────────────────────────────────

  document.getElementById("beenden").addEventListener("click", async () => {
    if (!window.confirm("Das Dashboard beenden? Gespeicherte Änderungen bleiben erhalten.")) {
      return;
    }
    try {
      const antwort = await fetch("/api/beenden", { method: "POST" });
      const koerper = await antwort.json().catch(() => ({}));
      zeige(koerper.text || koerper.fehler || "Beendet.", antwort.ok ? "" : "warnung");
    } catch (fehler) {
      // Der Server hat abgeschaltet, bevor er antworten konnte - genau richtig.
      zeige("Das Dashboard ist beendet. Sie können das Fenster schließen.", "");
    }
  });

  formular.addEventListener("submit", async (ereignis) => {
    ereignis.preventDefault();
    const benutzer = document.getElementById("benutzer");
    const passwort = document.getElementById("passwort");
    starten.disabled = true;
    abrufFehler.hidden = true;
    try {
      const antwort = await fetch("/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benutzer: benutzer.value, passwort: passwort.value }),
      });
      const koerper = await antwort.json().catch(() => ({}));
      if (antwort.status !== 202) {
        abrufFehler.textContent = koerper.fehler || "Der Abruf ließ sich nicht starten.";
        abrufFehler.hidden = false;
        return;
      }
      // Das Passwort war nur für diese eine Anfrage da.
      passwort.value = "";
      dialog.close();
      oeffnen.disabled = true;
      zeichneFortschritt(koerper.status || { fortschritt: 5, text: "Abruf gestartet" });
      pollen();
    } catch (fehler) {
      abrufFehler.textContent = "Der Server antwortet nicht.";
      abrufFehler.hidden = false;
    } finally {
      starten.disabled = false;
    }
  });
})();
