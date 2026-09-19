"""Mehrjahresbände: welche Bücher am Schuljahreswechsel abzugeben sind.

Die Antwort steht schon in IServ - man muss die Jahrgangs-Bücherlisten des
abgelaufenen Schuljahres nur neben die des neuen legen. Dieses Paket tut das
und schreibt das Ergebnis in dieselbe Exceldatei, in der die Übersicht bisher
von Hand gepflegt wurde.

Die Arbeit steht in :mod:`mehrjahresbaende.core`;
``erzeuge_mehrjahresbaende.py`` ist die Kommandozeile darüber, und das
Dashboard (``app/mehrjahresbaende.py``) benutzt dieselben Funktionen.
"""
