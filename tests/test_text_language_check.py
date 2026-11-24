from pathlib import Path

from scripts.check_text_language import cyrillic_letters, files_to_scan


def test_finds_cyrillic_letters_including_mongolian_letters() -> None:
    barred_o = chr(0x04E9)
    zhe = chr(0x0436)

    assert cyrillic_letters(f"Lotin\n{barred_o}{zhe}") == [(2, barred_o), (2, zhe)]


def test_scans_only_the_configured_text_file_locations(tmp_path: Path) -> None:
    relative_paths = (
        "README.md",
        "docs/guide.md",
        ".github/workflows/ci.yml",
        "scripts/check.py",
        "scripts/run.sh",
    )
    expected = [tmp_path / relative_path for relative_path in relative_paths]
    for path in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Lotin matn", encoding="utf-8")

    expected.sort(key=lambda path: path.relative_to(tmp_path).as_posix())
    assert files_to_scan(tmp_path) == expected
