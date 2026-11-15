"""``wheels/`` muss zu ``requirements.txt`` passen.

Die Schulrechner erreichen PyPI nicht direkt; ``START.bat`` installiert deshalb
zuerst aus ``wheels/``. Ein vergessenes ``tools/wheelhouse.py`` nach einer
Änderung an ``requirements.txt`` fiele sonst erst in der Schule auf, und dort
nur als langsamer Umweg übers Internet, der genau dort nicht geht.
"""
from __future__ import annotations

import importlib.util
import zipfile
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


ZIELE = [
    (plattform, version)
    for plattform, versionen in wheelhouse.ZIELE.items()
    for version in versionen
]


def _passende_tags(python_version: str, plattform_name: str = "win_amd64") -> set:
    version = tuple(int(teil) for teil in python_version.split("."))
    plattform = [plattform_name]
    return set(cpython_tags(version, platforms=plattform)) | set(
        compatible_tags(version, interpreter=f"cp{version[0]}{version[1]}",
                        platforms=plattform)
    )


@pytest.mark.parametrize(("plattform", "python_version"), ZIELE)
def test_jeder_pin_hat_ein_passendes_rad(plattform, python_version):
    """Fehlt ein Rad, kompiliert pip - und scheitert ohne Visual C++.

    So geschehen am 2026-11-15 auf einem ARM-Laptop mit Python 3.15: die
    Räder waren nur für x64 und bis 3.14 da, httptools, pyyaml, watchfiles
    und pydantic-core endeten mit "Microsoft Visual C++ 14.0 is required".
    """
    tags = _passende_tags(python_version, plattform)
    for anforderung in wheelhouse.anforderungen(python_version, plattform=plattform):
        (pin,) = anforderung.specifier
        treffer = [
            rad for rad in RAEDER
            if rad[0] == canonicalize_name(anforderung.name)
            and str(rad[1]) == pin.version
            and rad[3] & tags
        ]
        assert treffer, (
            f"{anforderung.name}=={pin.version} fehlt für {plattform}, Python {python_version}"
        )


def test_die_werkzeuge_liegen_bei():
    namen = {rad[0] for rad in RAEDER}
    for werkzeug in wheelhouse.WERKZEUGE:
        assert canonicalize_name(werkzeug) in namen, werkzeug


def test_keine_raeder_alter_pins():
    """Ein Rad, das keinem aktuellen Pin entspricht, ist toter Ballast im Repo."""
    gebraucht = {
        (canonicalize_name(a.name), next(iter(a.specifier)).version)
        for plattform, version in ZIELE
        for a in wheelhouse.anforderungen(version, plattform=plattform)
    }
    werkzeuge = {canonicalize_name(w) for w in wheelhouse.WERKZEUGE}
    werkzeuge.add(canonicalize_name(wheelhouse.AUSLEIHE_NAME))
    for name, version, *_ in RAEDER:
        assert name in werkzeuge or (name, str(version)) in gebraucht, f"{name} {version}"


def test_ausleihe_api_liegt_als_genau_ein_rad_bei():
    """Ohne den Client endet die Einrichtung mit "No module named 'ausleihe'".

    Der Programmordner auf dem Rechner der Lehrkraft ist nur dieses Repo, ein
    Nachbarordner ``ausleihe-api`` existiert dort nicht. ``START.bat`` nimmt
    das Rad über ein Muster; zwei Räder machten die Wahl zufällig.
    """
    raeder = wheelhouse.ausleihe_raeder()
    assert len(raeder) == 1, raeder
    for plattform, version in ZIELE:
        assert parse_wheel_filename(raeder[0].name)[3] & _passende_tags(version, plattform)


def test_ausleihe_rad_enthaelt_nur_das_paket():
    """Im Quellbaum von ausleihe-api liegt die ``.env`` mit IServ-Zugangsdaten."""
    (rad,) = wheelhouse.ausleihe_raeder()
    with zipfile.ZipFile(rad) as archiv:
        namen = archiv.namelist()
    fremd = [n for n in namen if not n.startswith(("ausleihe/", "iserv_ausleihe_api-"))]
    assert fremd == []
    assert not any(".env" in n.lower() for n in namen)


@pytest.mark.skipif(
    not (wheelhouse.AUSLEIHE_QUELLE / "ausleihe").is_dir(),
    reason="ausleihe-api liegt nicht als Geschwister-Repo daneben",
)
def test_ausleihe_rad_entspricht_dem_quellbaum():
    """Ein vergessener Neubau fiele sonst erst in der Schule auf.

    Entwickelt wird gegen den Quellbaum daneben (editable), ausgeliefert wird
    das Rad. Weichen beide ab, liefe auf dem Schul-Rechner ein anderer Client
    als in jedem Test hier.
    """
    (rad,) = wheelhouse.ausleihe_raeder()
    quelle = wheelhouse.AUSLEIHE_QUELLE / "ausleihe"
    with zipfile.ZipFile(rad) as archiv:
        im_rad = {
            n: archiv.read(n) for n in archiv.namelist()
            if n.startswith("ausleihe/") and not n.endswith("/")
        }
    im_quellbaum = {
        f"ausleihe/{p.relative_to(quelle).as_posix()}": p.read_bytes()
        for p in quelle.rglob("*")
        if p.is_file() and p.suffix in {".py", ".typed"} and "__pycache__" not in p.parts
    }
    # Zeilenenden zählen nicht: ein Windows-Checkout (core.autocrlf, so auch
    # in der CI) hat CRLF im Quellbaum, das Rad wurde aus einem LF-Baum gebaut.
    def _lf(dateien: dict[str, bytes]) -> dict[str, bytes]:
        return {name: inhalt.replace(b"\r\n", b"\n") for name, inhalt in dateien.items()}

    assert _lf(im_rad) == _lf(im_quellbaum), (
        "wheels/ ist veraltet: uv run python tools/wheelhouse.py --nur-ausleihe"
    )


def test_marker_werden_fuer_das_ziel_ausgewertet(tmp_path):
    """pip download wertet Marker gegen sein eigenes Python aus, nicht gegen das Ziel."""
    datei = tmp_path / "requirements.txt"
    datei.write_text(
        "exceptiongroup==1.3.1 ; python_full_version < '3.11'\n"
        "uvloop==0.22.1 ; sys_platform != 'win32'\n"
        "nurarm==1.0 ; platform_machine == 'ARM64'\n",
        encoding="utf-8",
    )
    alt = {a.name for a in wheelhouse.anforderungen("3.10", datei)}
    neu = {a.name for a in wheelhouse.anforderungen("3.15", datei)}
    arm = {a.name for a in wheelhouse.anforderungen("3.15", datei, plattform="win_arm64")}
    assert alt == {"exceptiongroup"}
    assert neu == set()
    assert arm == {"nurarm"}
