// Oberfläche des Dashboards - Vanilla, kein Build-Schritt.
//
// Die Regel für diese Datei: **so dumm wie möglich**. Sie rechnet nichts aus,
// was der Server schon ausgerechnet hat, und sie liest nichts aus dem
// angezeigten Text, was auch als Datenattribut danebenstehen kann. Das ist
// keine Stilfrage, sondern die Folge davon, dass es hier bewusst weder einen
// Build-Schritt noch eine JS-Testumgebung gibt: was in dieser Datei steht,
// prüft niemand automatisch. Was dagegen in der Vorlage steht, prüft
// `tests/test_oberflaeche.py` bei jedem Lauf - bis hin zu der Frage, ob jede
// ID, die dieses Skript nachschlägt, im gerenderten HTML überhaupt vorkommt.
//
// Konkret heißt das an zwei Stellen etwas:
//   * Sortiert wird über `data-wert` an jeder Zelle, nicht über ihren Text.
//   * Nach einer Änderung setzt `/api/cell` die fertige Zeile zurück; das
//     Skript trägt sie ein, statt "zu bestellen" selbst nachzurechnen.
//
// Vier Teile, die sich nichts teilen außer der Tabelle:
//   1. Filtern und Sortieren - rein im Browser, die Tabelle ist vollständig
//      gerendert und eine Serverrunde je Tastendruck wäre auf dem Netzlaufwerk
//      spürbar.
//   2. Zellen ändern - eine Zahl pro Anfrage, mit der zuletzt gesehenen
//      Änderungszeit. Antwortet der Server mit 409, hat jemand anderes die
//      Mappe angefasst; dann wird nicht überschrieben, sondern nachgeladen.
//   3. Abruf aus IServ - Formular, dann Fortschritt pollen.
//   4. Beenden.
//
// Ab etwa 400 Zeilen Code lässt sich das ohne Build in Module trennen
// (`<script type="module">` lädt echte ES-Module direkt aus dem Ordner); bei
// den heutigen 235 Codezeilen wäre das mehr Gerüst als Inhalt.
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

  // Das Zeichen für "kein Wert" steht in der Vorlage (data-leer), damit es
  // nicht an zwei Orten gepflegt werden muss.
  const LEER = tabelle.dataset.leer || "";

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

  // Der Sortierschlüssel einer Zelle. `data-wert` liefert die Vorlage (und
  // nach einer Änderung `zeileAktualisieren`); leerer String heißt "kein Wert".
  //
  // "Kein Wert" wird eigens markiert und NICHT auf einen Ersatzwert abgebildet:
  // ein Sentinel wie NEGATIVE_INFINITY verschiebt die Leerzeilen nur an ein
  // Ende der Zahlengeraden und wirft sie beim Umschalten der Richtung nach
  // vorn. Unten sortieren sie deshalb in beiden Richtungen ans Ende.
  function zellwert(zeile, index, art) {
    const roh = zeile.cells[index].dataset.wert ?? "";
    if (roh === "") return { leer: true, wert: null };
    return { leer: false, wert: art === "zahl" ? Number(roh) : roh };
  }

  // Textzellen werden mit deutscher Sortierordnung verglichen, nicht über
  // `<`/`>`: die Codepunkt-Ordnung legt "ö" hinter "z", sodass ein Fachname
  // wie "Französisch" falsch einsortieren würde. Intl.Collator ist eingebaut,
  // ein Build-Schritt fällt dafür keiner an.
  const textVergleich = new Intl.Collator("de").compare;

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
      if (links.leer !== rechts.leer) return links.leer ? 1 : -1;
      if (links.leer) return 0;
      const folge = art === "zahl"
        ? (links.wert < rechts.wert ? -1 : links.wert > rechts.wert ? 1 : 0)
        : textVergleich(links.wert, rechts.wert);
      return absteigend ? -folge : folge;
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

  // Setzt Anzeige UND Sortierschlüssel einer Zelle aus einem Wert der Antwort.
  // Beides an einer Stelle, damit die Tabelle nach einer Änderung nicht anders
  // sortiert als direkt nach dem Laden.
  function setzeZelle(zelle, wert) {
    const text = wert === null || wert === undefined ? "" : String(wert);
    zelle.dataset.wert = text;
    const feld = zelle.querySelector(".zellwert");
    if (feld) {
      feld.value = text;
      feld.dataset.gespeichert = text;
    } else {
      zelle.textContent = text === "" ? LEER : text;
    }
  }

  function bedarfNeuZeichnen() {
    let summe = 0;
    for (const zeile of zeilen) {
      // Über die Klasse greifen statt über den Spaltenindex: der Index verschiebt
      // sich lautlos, wenn im Template eine Spalte eingefügt oder umsortiert wird.
      const wert = Number(zeile.querySelector(".bedarfszelle").dataset.wert);
      if (Number.isFinite(wert) && wert > 0) summe += wert;
    }
    bedarfGesamt.textContent = summe;
  }

  function zeileAktualisieren(zeile, daten) {
    const bedarfszelle = zeile.querySelector(".bedarfszelle");
    setzeZelle(bedarfszelle, daten.zu_bestellen);
    const bedarf = (daten.zu_bestellen || 0) > 0;
    bedarfszelle.classList.toggle("bedarf", bedarf);
    zeile.dataset.bedarf = bedarf ? "1" : "0";
    for (const feld of zeile.querySelectorAll(".zellwert")) {
      setzeZelle(feld.closest("td"), daten[feld.dataset.spalte]);
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

  // Verlorene Anfragen in Folge, die der Fortschrittsdialog still toleriert.
  // Ein einziges fehlgeschlagenes fetch - ein WLAN-Blink, ein kurz belegter
  // Server - würde die Schleife sonst stillschweigend abbrechen: das Dialog-
  // fenster bliebe stehen, ohne Meldung und ohne Fortschritt, und niemand
  // erführe, dass nur die Verbindung kurz weg war. Erst wenn auch Wiederholungen
  // nichts bringen, wird abgebrochen - mit einer Meldung statt eines
  // eingefrorenen Dialogs.
  const MAX_VERLOREN = 5;
  let verloren = 0;

  async function pollen() {
    let stand;
    try {
      const antwort = await fetch("/api/refresh/status");
      stand = await antwort.json();
      verloren = 0;
    } catch (fehler) {
      verloren++;
      if (verloren >= MAX_VERLOREN) {
        fortschritt.classList.add("fehlgeschlagen");
        fortschrittText.textContent =
          "Der Server antwortet nicht mehr. Läuft das schwarze Fenster noch? " +
          "Falls ja, kann diese Meldung einfach geschlossen und die Seite neu geladen werden.";
        return;
      }
      fortschrittText.textContent =
        "Verbindung unterbrochen - es wird weiter versucht.";
      setTimeout(pollen, 1000);
      return;
    }
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
})();
