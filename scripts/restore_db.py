"""PostgreSQL zaxirasini mavjud bo‘lmagan yoki bo‘sh bazaga tiklash."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from app.ops.backup import dump_dsn, parse_dsn, pg_env

_EMPTY_TARGET_SQL = """
SELECT
    (SELECT count(*)
     FROM pg_class AS c
     JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
       AND n.nspname NOT LIKE 'pg_toast%'
       AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f'))
    + (SELECT count(*)
       FROM pg_namespace
       WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'public')
         AND nspname NOT LIKE 'pg_toast%');
"""


def _connection(database_url: str) -> tuple[str, dict[str, str]]:
    dsn = dump_dsn(database_url)
    parsed = urlsplit(dsn)
    fields = parse_dsn(database_url)
    if parsed.scheme != "postgresql" or not parsed.path.strip("/"):
        raise ValueError("PostgreSQL manzili noto‘g‘ri")
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("RESTORE_DATABASE_URL", None)
    environment.update(pg_env(database_url))
    return fields["database"], environment


def _show_error(result: subprocess.CompletedProcess[str], password: str = "") -> None:
    detail = result.stderr.strip()
    if password:
        detail = detail.replace(password, "***")
    print(detail or f"Buyruq {result.returncode} kodi bilan tugadi", file=sys.stderr)


def restore_dump(dump: Path, database_url: str, *, confirm_empty_target: bool) -> int:
    """Arxivni faqat bo‘sh bazaga, hammasini qaytaradigan tranzaksiya bilan yozish."""
    if not confirm_empty_target:
        print("Ishga tushirish uchun --confirm-empty-target parametri kerak.", file=sys.stderr)
        return 2
    if not dump.is_file():
        print("Zaxira fayli topilmadi.", file=sys.stderr)
        return 2
    if not database_url:
        print("RESTORE_DATABASE_URL o‘zgaruvchisi kiritilmagan.", file=sys.stderr)
        return 2

    pg_restore = shutil.which("pg_restore")
    psql = shutil.which("psql")
    if pg_restore is None or psql is None:
        print("pg_restore va psql dasturlari o‘rnatilgan bo‘lishi kerak.", file=sys.stderr)
        return 2

    archive_environment = os.environ.copy()
    for key in ("DATABASE_URL", "RESTORE_DATABASE_URL", "PGPASSWORD"):
        archive_environment.pop(key, None)
    archive = subprocess.run(
        [pg_restore, "--list", str(dump)],
        check=False,
        capture_output=True,
        text=True,
        env=archive_environment,
    )
    if archive.returncode:
        _show_error(archive)
        return archive.returncode

    try:
        database, environment = _connection(database_url)
    except ValueError:
        print("RESTORE_DATABASE_URL noto‘g‘ri PostgreSQL manzili.", file=sys.stderr)
        return 2

    password = environment.get("PGPASSWORD", "")
    target = subprocess.run(
        [
            psql,
            "--no-psqlrc",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={database}",
            "--command",
            _EMPTY_TARGET_SQL,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if target.returncode:
        _show_error(target, password)
        return target.returncode
    if target.stdout.strip() != "0":
        print("Maqsad baza bo‘sh emas; tiklash to‘xtatildi.", file=sys.stderr)
        return 2

    restored = subprocess.run(
        [
            pg_restore,
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            f"--dbname={database}",
            str(dump),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if restored.returncode:
        _show_error(restored, password)
        return restored.returncode
    print("Zaxira nusxasi bo‘sh bazaga tiklandi.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL zaxirasini tiklash")
    parser.add_argument("dump", type=Path, help="custom formatdagi pg_dump fayli")
    parser.add_argument(
        "--confirm-empty-target",
        action="store_true",
        help="bo‘sh maqsad bazaga tiklashni tasdiqlash",
    )
    args = parser.parse_args()
    return restore_dump(
        args.dump,
        os.environ.get("RESTORE_DATABASE_URL", ""),
        confirm_empty_target=args.confirm_empty_target,
    )


if __name__ == "__main__":
    raise SystemExit(main())
