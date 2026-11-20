"""Database URL normalisation for hosts that hand out plain postgres:// URLs (Render, Heroku)."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PLAIN = ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg")
_SSL_ON = {"require", "verify-ca", "verify-full", "prefer", "allow"}


def normalize_database_url(raw: str) -> str:
    """Return an asyncpg SQLAlchemy URL.

    - ``postgres://`` and ``postgresql://`` become ``postgresql+asyncpg://``.
    - libpq ``sslmode=...`` (which asyncpg rejects) becomes ``ssl=...``; ``disable`` is dropped.
    Other query parameters and the credentials are kept as they are.
    """
    url = (raw or "").strip()
    if not url:
        return url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in _PLAIN:
        scheme = "postgresql+asyncpg"
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode" and scheme == "postgresql+asyncpg":
            mode = value.lower()
            if mode in _SSL_ON:
                query.append(("ssl", "require" if mode in {"prefer", "allow"} else mode))
            continue
        query.append((key, value))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
