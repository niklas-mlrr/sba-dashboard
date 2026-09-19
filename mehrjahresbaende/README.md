# Mehrjahresbände — wer welches Buch abgeben muss

Am Schuljahreswechsel braucht jede Klasse eine Auskunft: Welche Bücher sind
abzugeben, und welche bleiben, weil sie im nächsten Jahrgang wieder auf der
Liste stehen (Mehrjahresbände)? Die Antwort steht schon in IServ — man muss die
Jahrgangs-Bücherlisten des abgelaufenen Schuljahres nur neben die des neuen
legen. Genau das tut dieses Paket.

Das Ergebnis ist eine Matrix **Jahrgang × Fach**, die als Exceldatei
(`Mehrjahresbände Schulbuchausleihe.xlsx`) im Ordner der Bestandsmappe liegt —
dieselbe Datei und dieselbe Struktur wie die Fassung, die bis 2026-09-19 von
Hand gepflegt wurde. Das ist Absicht: fällt das Dashboard aus, liegt die
Übersicht weiter dort, wo jede Kollegin sie sucht.

Rein lesend gegenüber IServ (nur GET).

## Die Regeln

Zeile „Jahrgang N" meint die Schülerinnen und Schüler, die im **abgelaufenen**
Schuljahr in N waren. Verglichen wird mit **Jahrgang N+1** des laufenden.
Betrachtet werden nur **leihbare** Bücher — ein Kaufbuch gehört ohnehin den
Schülern. Ein Jahrgang, der im Vorjahr **kein einziges** leihbares Buch hatte,
bekommt gar keine Zeile: dort ist nichts ausgeliehen worden, also ist auch
nichts abzugeben.

Je Buch ergibt sich einer von drei Ausgängen:

| Ausgang | wann |
|---------|------|
| behalten | das Buch steht im neuen Jahr in der Liste von Jg. N+1 |
| ausgemustert | das Buch steht im neuen Jahr in **keiner** Liste mehr |
| abgeben | alles andere |

Daraus die Marke der Zelle:

| Marke | Bedeutung |
|-------|-----------|
| `X` | muss abgegeben werden |
| *(leer)* | ist bei erneuter Teilnahme nicht abzugegeben |
| `---` | kein (physisches)/(ausleihbares) Buch in diesem Fach |
| `B` | darf behalten werden, die Reihe ist ausgemustert |
| `A`, `C`, `D`, … | mehrere Bücher mit **unterschiedlichem** Ausgang |

Der Regelfall ist ein leihbares Buch je Fach und Jahrgang. Gibt es mehrere mit
verschiedenem Ausgang, bekommt dieser Fall einen eigenen Buchstaben, und die
Legende schreibt ihn mit den Titeln aus:

```
A = nur „Deutschbuch 8“ muss abgegeben werden; „Duden“ ist bei erneuter
    Teilnahme nicht abzugegeben
```

Vergeben werden `A`, `C`, `D`, … (`B` und `X` sind belegt). Derselbe Fall —
dieselben Titel mit denselben Ausgängen — bekommt **einen** Buchstaben, auch
wenn er in mehreren Zellen steht.

Zwei Sonderfälle, in dieser Reihenfolge:

1. **Letzter Jahrgang** (für N+1 gibt es keine Liste mehr): alles `X`,
   ausgemusterte Reihen `B`. Gilt auch bei individueller Ausleihe.
2. **Individuelle Ausleihe** (`package = false`): statt einzelner Marken eine
   über alle Fachspalten verbundene Hinweiszeile — alle Bücher ohne erneute
   Anmeldung sind abzugeben, ausgenommen die namentlich genannten
   ausgemusterten Reihen.

## Bibliothek und Kommandozeile

Wie `bestand/core/` und `buecherlisten/core/`: die Arbeit steht in `core/`, das
Skript ist nur die Kommandozeile, und das Dashboard benutzt dieselben
Funktionen (`app/mehrjahresbaende.py`, Reiter „Mehrjahresbände").

| Modul | Inhalt |
|-------|--------|
| `core/modelle.py` | die Begriffe: `Marke`, `Zelle`, `Jahrgangszeile`, `Spalte`, `Sonderfall`, `Uebersicht` |
| `core/laden.py` | `lade_schuljahr(client, kennung)`, `vorjahr_kennung("2026/2027")` |
| `core/vergleich.py` | `vergleiche(alt, neu, …) -> Uebersicht` — ohne Netz und ohne Excel |
| `core/mappe.py` | `lies_uebersicht`, `schreibe_datei`, `schreibe_blatt`, `setze_marke` |

Die Fach → Aufgabenfeld-Zuordnung kommt von der Schulwebsite, über
`buecherlisten.core.erzeugen.aufgabenfeld_zuordnung` — dieselbe Quelle wie die
PDF-Sortierung „nach Aufgabenfeld". Ist sie nicht erreichbar, bleibt die
Spaltenfolge der vorhandenen Datei, neue Fächer kommen ans Ende. Fächer ohne
bekanntes Aufgabenfeld stehen unter `(ohne Aufgabenfeld)` ganz rechts.

## Schnellstart

```bash
cd mehrjahresbaende

# zeigen, was herauskäme, ohne zu schreiben:
python3 erzeuge_mehrjahresbaende.py --trocken

# erzeugen und in eine bestimmte Datei schreiben:
python3 erzeuge_mehrjahresbaende.py --datei "/Pfad/Mehrjahresbände Schulbuchausleihe.xlsx"

# ein bestimmtes Schuljahrespaar:
python3 erzeuge_mehrjahresbaende.py --schuljahr 2026/2027 --vorjahr 2025/2026
```

Die Zugangsdaten liegen in der `.env` des Geschwister-Repos `ausleihe-api`, wie
bei `buecherlisten/generate_booklists.py`.

## Was das Paket nicht tut

* **Zusammenführen.** „Erzeugen" überschreibt die ganze Datei, auch von Hand
  geänderte Zellen. Zwei Wahrheiten in einer Datei — hier die gerechnete, dort
  die nachgebesserte — wären nach einem Jahr nicht mehr auseinanderzuhalten.
* **Sperren und Sicherungen.** Das steht im Dashboard
  (`app/mehrjahresbaende.py`), weil es dort schon für die Bestandsmappe steht.
* **Die Bücher je Zelle merken.** Welche Titel hinter einer Marke stehen, weiß
  nur der Vergleich; die Datei trägt es nur für die Sonderfälle, dort dafür
  ausgeschrieben in der Legende.

## Tests

`tests/bibliothek/test_mehrjahresbaende_vergleich.py` (die Regeln einzeln) und
`tests/bibliothek/test_mehrjahresbaende_mappe.py` (Dateiaufbau, Rundlauf,
einzelne Zelle). Beide offline. Die Seite und die Routen prüft
`tests/test_mehrjahresbaende_http.py`.
