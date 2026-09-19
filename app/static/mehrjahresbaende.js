// Der Reiter "Mehrjahresbände" - zwei Dinge, sonst nichts.
//
// Dieselbe Regel wie in app.js: so dumm wie möglich. Das Skript rechnet keine
// Marke aus und leitet keine ab; es schickt die gewählte an den Server und
// trägt ein, was zurückkommt. Welche Marken es gibt, steht in der Vorlage
// (der Server hat sie aus der Legende der Datei gelesen) - hier steht nirgends
// eine Liste davon.
//
//   1. Eine Zelle ändern: ein <select> je Zelle, mit der beim Laden gesehenen
//      mtime. Antwortet der Server mit 409, hat jemand anderes die Datei
//      angefasst; dann wird nicht überschrieben, sondern nachgeladen.
//   2. Neu erzeugen: Rückfrage im Dialog (es überschreibt alles), dann warten -
//      der Abruf zweier Schuljahre dauert, deshalb die Überlagerung.
(function () {
  const meldung = document.getElementById("meldung");
  const seiteLaedt = document.getElementById("seite-laedt");
  const seiteLaedtText = document.getElementById("seite-laedt-text");
  const matrix = document.getElementById("matrix");

  function zeige(text, art) {
    meldung.textContent = text;
    meldung.className = "hinweis meldung" + (art ? " " + art : "");
    meldung.hidden = !text;
  }

  function warte(text) {
    seiteLaedtText.textContent = text;
    seiteLaedt.hidden = false;
  }

  function fertig() {
    seiteLaedt.hidden = true;
  }

  function neuLaden(text, verzoegerung) {
    warte(text);
    setTimeout(() => window.location.reload(), verzoegerung);
  }

  // ── 1. Eine Marke ändern ───────────────────────────────────────────────────

  async function speichern(feld) {
    const zeile = feld.closest("tr");
    const vorher = feld.dataset.gespeichert ?? "";
    if (feld.value === vorher) return;

    feld.disabled = true;
    feld.classList.remove("fehlerhaft");
    feld.classList.add("speichert");
    try {
      const antwort = await fetch("/api/mehrjahresbaende/marke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jahrgang: Number(zeile.dataset.jahrgang),
          fach: feld.dataset.fach,
          marke: feld.value,
          mtime: parseFloat(matrix.dataset.mtime),
        }),
      });
      const koerper = await antwort.json().catch(() => ({}));

      if (antwort.ok) {
        matrix.dataset.mtime = koerper.mtime;
        feld.dataset.gespeichert = feld.value;
        zeige("");
        feld.classList.add("gespeichert");
        setTimeout(() => feld.classList.remove("gespeichert"), 1200);
        return;
      }

      // Zurück auf den zuletzt bestätigten Wert: die Datei hat gewonnen.
      feld.value = vorher;
      feld.classList.add("fehlerhaft");
      if (antwort.status === 409) {
        zeige(koerper.fehler + " (Die Seite lädt gleich neu.)", "warnung");
        neuLaden("Die Datei wurde inzwischen geändert - die Seite lädt neu …", 2500);
      } else {
        zeige(koerper.fehler || "Die Änderung ließ sich nicht speichern.", "warnung");
      }
    } catch (fehler) {
      feld.value = vorher;
      feld.classList.add("fehlerhaft");
      zeige("Der Server antwortet nicht. Läuft das schwarze Fenster noch?", "warnung");
    } finally {
      feld.disabled = false;
      feld.classList.remove("speichert");
    }
  }

  if (matrix) {
    for (const feld of matrix.querySelectorAll(".marke")) {
      feld.dataset.gespeichert = feld.value;
      feld.addEventListener("change", () => speichern(feld));
    }
  }

  // ── 2. Neu erzeugen ────────────────────────────────────────────────────────

  const knopf = document.getElementById("erzeugen");
  const dialog = document.getElementById("erzeugen-dialog");

  async function erzeugen() {
    warte("Die Bücherlisten beider Schuljahre werden geholt - das dauert einen Moment …");
    try {
      const antwort = await fetch("/api/mehrjahresbaende/erzeugen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const koerper = await antwort.json().catch(() => ({}));
      if (antwort.ok) {
        // Neu laden statt die Tabelle im Browser nachzubauen: Spalten und
        // Legende können sich geändert haben, und die Vorlage kann das schon.
        neuLaden("Die Übersicht ist erzeugt - die Seite lädt neu …", 400);
        return;
      }
      fertig();
      zeige(koerper.fehler || "Die Übersicht ließ sich nicht erzeugen.", "warnung");
    } catch (fehler) {
      fertig();
      zeige("Der Server antwortet nicht. Läuft das schwarze Fenster noch?", "warnung");
    }
  }

  knopf.addEventListener("click", () => dialog.showModal());
  dialog.addEventListener("close", () => {
    if (dialog.returnValue === "los") erzeugen();
  });
})();
