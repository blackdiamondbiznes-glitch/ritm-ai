"""Shell and vertical i18n layers, plus typographic apostrophes in Uzbek packs."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/webapp/static"
LOCALES = ROOT / "app/locales"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_i18n_loader_exposes_shell_and_vertical_namespaces() -> None:
    text = _read("i18n.js")
    assert 'prefixed("shell."' in text
    assert 'prefixed("vertical.tutor."' in text
    assert "mergePacks(" in text


def test_nav_reads_the_tutor_vertical_pack() -> None:
    nav = _read("nav.js")
    vertical = _read("vertical.js")
    assert "currentVertical" in nav
    assert 'id: "tutor"' in vertical
    assert "teacherTabs" in vertical and "studentTabs" in vertical


def test_uzbek_o_and_g_use_the_typographic_apostrophe() -> None:
    """o‘/g‘ must be U+2018, not ASCII or a right quote, in both bot and Mini App copy."""
    files = [LOCALES / "uz.json", *STATIC.glob("i18n_*_uz.js")]
    bad: list[str] = []
    pattern = re.compile(r"([oOgG])['\u2019\u02BC`]")
    for path in files:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                bad.append(f"{path.name}:{i}:{line.strip()}")
    assert not bad, "use U+2018 after o/g:\n" + "\n".join(bad[:20])
