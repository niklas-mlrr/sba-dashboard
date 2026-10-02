"""``wheels/`` muss zu ``requirements.txt`` passen.

Die Schulrechner erreichen PyPI nicht direkt; ``START.bat`` installiert deshalb
zuerst aus ``wheels/``. Ein vergessenes ``tools/wheelhouse.py`` nach einer
Änderung an ``requirements.txt`` fiele sonst erst in der Schule auf, und dort
nur als langsamer Umweg übers Internet, der genau dort nicht geht.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

WURZEL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "wheelhouse", WURZEL / "tools" / "wheelhouse.py"
)
assert _spec and _spec.loader
wheelhouse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wheelhouse)

RAEDER = [parse_wheel_filename(p.name) for p in wheelhouse.ZIEL.glob("*.whl")]


def _passende_tags(python_version: str) -> set:
    version = tuple(int(teil) for teil in python_version.split("."))
    plattform = [wheelhouse.PLATTFORM]
    return set(cpython_tags(version, platforms=plattform)) | set(
        compatible_tags(version, interpreter=f"cp{version[0]}{version[1]}",
                        platforms=plattform)
    )


@pytest.mark.parametrize("python_version", wheelhouse.PYTHON_VERSIONEN)
def test_jeder_pin_hat_ein_passendes_rad(python_version):
    tags = _passende_tags(python_version)
    for anforderung in wheelhouse.anforderungen(python_version):
        (pin,) = anforderung.specifier
        treffer = [
            rad for rad in RAEDER
            if rad[0] == canonicalize_name(anforderung.name)
            and str(rad[1]) == pin.version
            and rad[3] & tags
        ]
        assert treffer, f"{anforderung.name}=={pin.version} fehlt für Python {python_version}"


def test_die_werkzeuge_liegen_bei():
    namen = {rad[0] for rad in RAEDER}
    for werkzeug in wheelhouse.WERKZEUGE:
        assert canonicalize_name(werkzeug) in namen, werkzeug


def test_keine_raeder_alter_pins():
    """Ein Rad, das keinem aktuellen Pin entspricht, ist toter Ballast im Repo."""
    gebraucht = {
        (canonicalize_name(a.name), next(iter(a.specifier)).version)
        for version in wheelhouse.PYTHON_VERSIONEN
        for a in wheelhouse.anforderungen(version)
    }
    werkzeuge = {canonicalize_name(w) for w in wheelhouse.WERKZEUGE}
    for name, version, *_ in RAEDER:
        assert name in werkzeuge or (name, str(version)) in gebraucht, f"{name} {version}"


def test_marker_werden_fuer_windows_ausgewertet():
    """uvloop gibt es unter Windows nicht; pip download sähe das nicht."""
    namen = {a.name for a in wheelhouse.anforderungen("3.14")}
    assert "uvloop" not in namen
    alt = {str(a.specifier) for a in wheelhouse.anforderungen("3.10") if a.name == "websockets"}
    neu = {str(a.specifier) for a in wheelhouse.anforderungen("3.14") if a.name == "websockets"}
    assert alt != neu
