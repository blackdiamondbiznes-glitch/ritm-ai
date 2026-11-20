"""Neon and libpq query parameters must be safe for asyncpg and pg_dump."""

from app.db.url import normalize_database_url
from app.ops.backup import dump_dsn, pg_env

_NEON = (
    "postgresql://u:p@ep-x.c-8.eu-central-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)
_NORMALISED = "postgresql+asyncpg://u:p@ep-x.c-8.eu-central-1.aws.neon.tech/neondb?ssl=require"


def test_neon_url_drops_channel_binding_and_maps_sslmode() -> None:
    assert normalize_database_url(_NEON) == _NORMALISED
    already = _NORMALISED + "&channel_binding=require"
    assert normalize_database_url(already) == _NORMALISED


def test_dump_dsn_restores_libpq_sslmode() -> None:
    libpq = dump_dsn(_NORMALISED)
    assert libpq.startswith("postgresql://u:p@ep-x.c-8.eu-central-1.aws.neon.tech/neondb")
    assert "sslmode=require" in libpq
    assert "ssl=" not in libpq.replace("sslmode=", "")
    raw = dump_dsn(_NEON)
    assert "sslmode=require" in raw
    assert "channel_binding=require" in raw


def test_pg_env_sets_ssl_for_neon_urls() -> None:
    for url in (_NEON, _NORMALISED, normalize_database_url(_NEON)):
        env = pg_env(url)
        assert env["PGHOST"] == "ep-x.c-8.eu-central-1.aws.neon.tech"
        assert env["PGDATABASE"] == "neondb"
        assert env["PGSSLMODE"] == "require"
        assert env["PGPASSWORD"] == "p"
    # Raw Neon URLs keep channel_binding for libpq; the asyncpg form has dropped it.
    assert pg_env(_NEON)["PGCHANNELBINDING"] == "require"
    assert "PGCHANNELBINDING" not in pg_env(_NORMALISED)
    bare = "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb"
    assert pg_env(bare)["PGSSLMODE"] == "require"
