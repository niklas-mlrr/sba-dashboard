"""Version der laufenden Anwendung.

Eine Konstante und nicht ``importlib.metadata``: ``[tool.uv] package = false``
installiert ``sba-dashboard`` selbst nicht - es gibt also keine Distribution,
deren Metadaten man abfragen könnte. Die Antwort muss aber gerade dann kommen,
wenn sie am meisten zählt: im Diagnosebericht eines fremden Geräts und im
Startfenster, das die Lehrkraft sieht. ``pyproject.toml`` führt dieselbe Zahl;
ein Test hält beide Stellen zusammen (``tests/test_version.py``).
"""
__version__ = "0.1.0"