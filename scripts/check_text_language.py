"""Ruxsat etilgan matn fayllarida kirill harflarini qidirish."""

from __future__ import annotations

import unicodedata
from pathlib import Path

ALLOWED_SUFFIXES = frozenset({".md", ".yml", ".yaml", ".py", ".sh"})
SCANNED_DIRECTORIES = (".github", "docs", "scripts")


def files_to_scan(root: Path) -> list[Path]:
    """Faqat belgilangan papkalar va root dagi README.md matnlarini qaytarish."""
    files: set[Path] = set()
    readme = root / "README.md"
    if readme.is_file() and not readme.is_symlink():
        files.add(readme)

    for name in SCANNED_DIRECTORIES:
        directory = root / name
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in ALLOWED_SUFFIXES:
                files.add(path)

    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def cyrillic_letters(text: str) -> list[tuple[int, str]]:
    """Kirill Unicode harflari va ularning matndagi qatorlarini topish."""
    found = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for character in line:
            name = unicodedata.name(character, "")
            if unicodedata.category(character).startswith("L") and "CYRILLIC" in name:
                found.append((line_number, character))
    return found


def scan(root: Path) -> list[tuple[str, int, str]]:
    """Tekshiriladigan fayllardagi kirill harflarini nisbiy manzili bilan qaytarish."""
    found = []
    for path in files_to_scan(root):
        relative_path = path.relative_to(root).as_posix()
        for line_number, character in cyrillic_letters(path.read_text(encoding="utf-8")):
            found.append((relative_path, line_number, character))
    return found


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    found = scan(root)
    if found:
        for path, line_number, character in found:
            codepoint = f"U+{ord(character):04X}"
            print(f"Kirill harfi topildi: {path}:{line_number} ({codepoint})")
        return 1

    print("Matn fayllarida kirill harfi topilmadi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
