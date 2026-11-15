"""Macht tests/bibliothek/ zum Paket - nicht aus Ordnungsliebe, sondern nötig.

Ohne diese Datei legt pytest JEDEN Testordner ohne ``__init__.py`` selbst auf
den ``sys.path``, also auch diesen. Dann liegen zwei Module namens ``conftest``
darauf, und es entscheidet die Einlesereihenfolge, welches ein
``from conftest import ...`` trifft: ``tests/bibliothek/`` kommt alphabetisch
vor den Dateien in ``tests/``, verdeckte also ``tests/conftest.py`` - zehn
Dashboard-Testmodule brachen sofort mit "cannot import name TEST_BASIS_URL"
(2026-09-18, beim Zusammenlegen von sba-bestand).

Mit ``__init__.py`` ist der eingehängte Pfad ``tests/`` und die Module heißen
``bibliothek.test_*``. ``from conftest import ...`` trifft damit wieder
eindeutig ``tests/conftest.py``; die Fixtures von ``bibliothek/conftest.py``
findet pytest weiterhin über die Ordnerhierarchie, nicht über den Importpfad.
"""
