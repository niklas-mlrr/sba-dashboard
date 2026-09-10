"""Die Widgets des Programmfensters - und sonst nichts.

Getrennt von ``app/fenster.py``, weil dort die Logik steht und hier der Teil, der
einen Bildschirm braucht. Die Trennung ist keine Förmlichkeit: ``import tkinter``
scheitert auf dem Entwicklungs-VPS und in der CI, und ein Modul, das beim Import
scheitert, lässt sich nicht teilweise testen. ``app/fenster.py`` importiert diese
Datei deshalb erst innerhalb von ``starte()``.

Entscheidungen trifft hier nichts. Jeder Knopf ruft eine Methode von
``Fenstersteuerung`` und zeigt deren Rückgabe oder deren ``FensterFehler`` an;
welche Texte das sind, steht dort und ist dort geprüft.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .fenster import STATUS_TAKT_MS, FensterFehler, Fenstersteuerung

_RAND = 12


class Hauptfenster:
    """Ein Fenster mit zwei Ansichten: Bedienung und (hinterm Zahnrad) Einstellungen."""

    def __init__(self, steuerung: Fenstersteuerung, *, version: str = "") -> None:
        self.steuerung = steuerung
        self.wurzel = tk.Tk()
        self.wurzel.title("Schulbuchausleihe — Bestand")
        self.wurzel.minsize(520, 360)
        self.wurzel.protocol("WM_DELETE_WINDOW", self._beenden)

        self._version = version
        self._benutzer = tk.StringVar()
        self._passwort = tk.StringVar()
        self._server = tk.StringVar()
        self._ordner = tk.StringVar()
        self._angemeldet = False
        self._timer: str | None = None

        self._bedienung = ttk.Frame(self.wurzel, padding=_RAND)
        self._einstellungen = ttk.Frame(self.wurzel, padding=_RAND)
        self._baue_bedienung()
        self._baue_einstellungen()
        self._zeige(self._bedienung)

        self._lade_einstellungen()
        self._aktualisiere_status()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _baue_bedienung(self) -> None:
        rahmen = self._bedienung
        rahmen.columnconfigure(1, weight=1)

        kopf = ttk.Label(rahmen, text="Schulbuchausleihe — Bestand",
                         font=("TkDefaultFont", 12, "bold"))
        kopf.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(rahmen, text="⚙", width=3, command=self._zeige_einstellungen).grid(
            row=0, column=2, sticky="e")

        self._zeile_server = ttk.Label(rahmen, text="Server: —")
        self._zeile_server.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._zeile_ordner = ttk.Label(rahmen, text="Ordner: —", wraplength=460, justify="left")
        self._zeile_ordner.grid(row=2, column=0, columnspan=3, sticky="w")
        self._zeile_mappe = ttk.Label(rahmen, text="Mappe: —", wraplength=460, justify="left")
        self._zeile_mappe.grid(row=3, column=0, columnspan=3, sticky="w")

        ttk.Separator(rahmen).grid(row=4, column=0, columnspan=3, sticky="ew", pady=_RAND)

        ttk.Label(rahmen, text="IServ-Benutzername").grid(row=5, column=0, sticky="w")
        self._feld_benutzer = ttk.Entry(rahmen, textvariable=self._benutzer)
        self._feld_benutzer.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Label(rahmen, text="Passwort").grid(row=6, column=0, sticky="w", pady=(4, 0))
        self._feld_passwort = ttk.Entry(rahmen, textvariable=self._passwort, show="•")
        self._feld_passwort.grid(row=6, column=1, columnspan=2, sticky="ew",
                                 padx=(8, 0), pady=(4, 0))
        self._feld_passwort.bind("<Return>", lambda _ereignis: self._anmelden())

        self._knopf_anmelden = ttk.Button(rahmen, text="Anmelden", command=self._anmelden)
        self._knopf_anmelden.grid(row=7, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        self._zeile_status = ttk.Label(rahmen, text="", wraplength=460, justify="left")
        self._zeile_status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._zeile_meldung = ttk.Label(rahmen, text="", wraplength=460, justify="left",
                                        foreground="#a11")
        self._zeile_meldung.grid(row=9, column=0, columnspan=3, sticky="w")

        rahmen.rowconfigure(10, weight=1)
        fuss = ttk.Frame(rahmen)
        fuss.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(_RAND, 0))
        fuss.columnconfigure(0, weight=1)
        ttk.Button(fuss, text="Seite öffnen", command=self._seite_oeffnen).grid(
            row=0, column=0, sticky="w")
        ttk.Button(fuss, text="Beenden", command=self._beenden).grid(row=0, column=1, sticky="e")
        if self._version:
            ttk.Label(fuss, text=f"Version {self._version}", foreground="#777").grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _baue_einstellungen(self) -> None:
        rahmen = self._einstellungen
        rahmen.columnconfigure(1, weight=1)

        ttk.Label(rahmen, text="Einstellungen",
                  font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=3,
                                                           sticky="w")
        ttk.Label(rahmen, text="IServ-Server").grid(row=1, column=0, sticky="w", pady=(_RAND, 0))
        ttk.Entry(rahmen, textvariable=self._server).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(_RAND, 0))
        ttk.Label(rahmen, text="ohne https://, zum Beispiel meine-schule.de",
                  foreground="#777").grid(row=2, column=1, columnspan=2, sticky="w", padx=(8, 0))

        ttk.Label(rahmen, text="Ordner der Mappe").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(rahmen, textvariable=self._ordner).grid(
            row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Button(rahmen, text="Durchsuchen…", command=self._waehle_ordner).grid(
            row=3, column=2, sticky="e", padx=(8, 0), pady=(8, 0))
        ttk.Label(rahmen, text="Die Excel-Datei darin findet das Programm selbst.",
                  foreground="#777").grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0))

        self._zeile_einstellungsmeldung = ttk.Label(rahmen, text="", wraplength=460,
                                                    justify="left")
        self._zeile_einstellungsmeldung.grid(row=5, column=0, columnspan=3, sticky="w",
                                            pady=(_RAND, 0))

        rahmen.rowconfigure(6, weight=1)
        fuss = ttk.Frame(rahmen)
        fuss.grid(row=7, column=0, columnspan=3, sticky="ew")
        fuss.columnconfigure(0, weight=1)
        ttk.Button(fuss, text="Speichern", command=self._speichere_einstellungen).grid(
            row=0, column=0, sticky="w")
        ttk.Button(fuss, text="Zurück", command=self._zeige_bedienung).grid(
            row=0, column=1, sticky="e")

    def _zeige(self, rahmen: ttk.Frame) -> None:
        self._bedienung.pack_forget()
        self._einstellungen.pack_forget()
        rahmen.pack(fill="both", expand=True)

    # ── Knöpfe ───────────────────────────────────────────────────────────────

    def _melde(self, text: str, *, fehler: bool) -> None:
        self._zeile_meldung.configure(text=text, foreground="#a11" if fehler else "#161")

    def _versuch(self, aufgabe: Callable[[], str]) -> None:
        """Führt eine Steuerungsmethode aus und zeigt Text oder Fehler in derselben Zeile."""
        try:
            self._melde(aufgabe(), fehler=False)
        except FensterFehler as exc:
            self._melde(str(exc), fehler=True)

    def _anmelden(self) -> None:
        if self._angemeldet:
            self._versuch(self.steuerung.abmelden)
            self._aktualisiere_status()
            return
        benutzer, passwort = self._benutzer.get(), self._passwort.get()
        try:
            zeile = self.steuerung.anmelden(benutzer, passwort)
        except FensterFehler as exc:
            self._melde(str(exc), fehler=True)
            return
        finally:
            # Das Passwort verlässt das Fenster nach dieser einen Anfrage: Feld
            # leeren *und* die Variable überschreiben. Gehalten wird es nur im
            # IServ-Client im Server, siehe app/sitzung.py.
            self._passwort.set("")
            self._feld_passwort.delete(0, "end")
            del passwort
        self._melde("", fehler=False)
        self._setze_status(zeile, angemeldet=True)
        self._aktualisiere_status()

    def _seite_oeffnen(self) -> None:
        self.steuerung.seite_oeffnen()
        self._melde("Die Seite wurde im Browser geöffnet.", fehler=False)

    def _beenden(self) -> None:
        if not messagebox.askokcancel(
            "Beenden",
            "Das Dashboard beenden? Gespeicherte Änderungen bleiben erhalten.",
            parent=self.wurzel,
        ):
            return
        try:
            self.steuerung.beenden()
        except FensterFehler:
            # Der Server antwortet nicht mehr - dann ist er auch nicht mehr da.
            # Das Fenster offen zu lassen, wäre die falsche Folgerung.
            pass
        if self._timer is not None:
            self.wurzel.after_cancel(self._timer)
            self._timer = None
        self.wurzel.destroy()

    def _waehle_ordner(self) -> None:
        gewaehlt = filedialog.askdirectory(
            parent=self.wurzel,
            title="Ordner der Bestandsliste wählen",
            initialdir=self._ordner.get() or None,
            mustexist=True,
        )
        if gewaehlt:
            self._ordner.set(gewaehlt)

    def _speichere_einstellungen(self) -> None:
        try:
            zeile = self.steuerung.speichere_einstellungen(
                self._server.get(), self._ordner.get())
        except FensterFehler as exc:
            self._zeile_einstellungsmeldung.configure(text=str(exc), foreground="#a11")
            return
        self._zeile_einstellungsmeldung.configure(text=zeile, foreground="#161")
        self._lade_einstellungen()

    def _zeige_einstellungen(self) -> None:
        self._zeile_einstellungsmeldung.configure(text="")
        self._zeige(self._einstellungen)

    def _zeige_bedienung(self) -> None:
        self._zeige(self._bedienung)

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def _lade_einstellungen(self) -> None:
        """Holt Server, Ordner und gefundene Mappe und belegt beide Ansichten vor."""
        try:
            werte: dict[str, Any] = self.steuerung.einstellungen()
        except FensterFehler as exc:
            self._melde(str(exc), fehler=True)
            return
        self._server.set(str(werte.get("server") or ""))
        self._ordner.set(str(werte.get("ordner") or ""))
        self._zeile_server.configure(text=f"Server: {werte.get('server') or '—'}")
        self._zeile_ordner.configure(text=f"Ordner: {werte.get('ordner') or '— nicht eingestellt'}")
        self._zeile_mappe.configure(text=f"Mappe: {self.steuerung.mappenzeile(werte)}")

    def _setze_status(self, zeile: str, *, angemeldet: bool) -> None:
        self._angemeldet = angemeldet
        self._zeile_status.configure(text=zeile)
        self._knopf_anmelden.configure(text="Abmelden" if angemeldet else "Anmelden")
        zustand = "disabled" if angemeldet else "normal"
        self._feld_benutzer.configure(state=zustand)
        self._feld_passwort.configure(state=zustand)

    def _aktualisiere_status(self) -> None:
        """Fragt den Anmeldestand und plant die nächste Abfrage.

        Der Takt macht das Verfallen sichtbar, ohne es zu verhindern:
        ``GET /api/anmeldung`` gilt ausdrücklich nicht als Benutzung (siehe
        ``app/api/abruf.py``), sonst liefe das Zeitschloss nie ab.
        """
        try:
            status = self.steuerung.anmeldestatus()
        except FensterFehler as exc:
            self._melde(str(exc), fehler=True)
        else:
            self._setze_status(
                self.steuerung.statuszeile(status), angemeldet=bool(status.get("angemeldet")),
            )
        self._timer = self.wurzel.after(STATUS_TAKT_MS, self._aktualisiere_status)

    def laufen(self) -> None:
        self.wurzel.mainloop()
