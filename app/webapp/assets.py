"""Static Mini App files served from memory: versioned URLs, gzip and cache headers.

Assets are read once at startup. The version is a short hash of every file, and
index.html is rewritten so `/s/x.js` becomes `/s/<version>/x.js`. Relative ES
module imports then resolve inside the same versioned folder, so the browser can
cache every asset for a year and a new deploy simply changes the folder.
"""

from __future__ import annotations

import gzip
import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from aiohttp import web

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
TYPES = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}


@dataclass(frozen=True)
class Asset:
    body: bytes
    gz: bytes
    content_type: str
    etag: str


class AssetStore:
    """Every static file in memory, plus the rewritten shell."""

    def __init__(self, root: Path) -> None:
        self.files: dict[str, Asset] = {}
        digest = hashlib.sha256()
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            data = path.read_bytes()
            digest.update(path.name.encode())
            digest.update(data)
            self.files[path.name] = _asset(path.name, data)
        self.version = digest.hexdigest()[:10]
        shell = self.files["index.html"].body.decode()
        shell = shell.replace('"/s/', f'"/s/{self.version}/')
        self.index = _asset("index.html", shell.encode())

    def response(self, request: web.Request, asset: Asset, cache: str) -> web.StreamResponse:
        headers = {"Cache-Control": cache, "ETag": asset.etag, "Vary": "Accept-Encoding"}
        if request.headers.get("If-None-Match") == asset.etag:
            return web.Response(status=304, headers=headers)
        body = asset.body
        if "gzip" in request.headers.get("Accept-Encoding", "") and len(asset.gz) < len(body):
            body = asset.gz
            headers["Content-Encoding"] = "gzip"
        return web.Response(
            body=body, headers=headers, content_type=asset.content_type, charset="utf-8"
        )


def _asset(name: str, data: bytes) -> Asset:
    suffix = Path(name).suffix
    kind = TYPES.get(suffix) or mimetypes.guess_type(name)[0] or "application/octet-stream"
    tag = '"' + hashlib.sha256(data).hexdigest()[:16] + '"'
    return Asset(data, gzip.compress(data, compresslevel=9, mtime=0), kind, tag)


def setup_assets(app: web.Application, root: Path) -> AssetStore:
    """Register `/`, `/s/<version>/<file>` and the legacy `/s/<file>` routes."""
    store = AssetStore(root)
    app["assets"] = store

    async def index(request: web.Request) -> web.StreamResponse:
        return store.response(request, store.index, REVALIDATE)

    async def versioned(request: web.Request) -> web.StreamResponse:
        asset = store.files.get(request.match_info["name"])
        if asset is None:
            raise web.HTTPNotFound()
        current = request.match_info["version"] == store.version
        return store.response(request, asset, IMMUTABLE if current else REVALIDATE)

    async def plain(request: web.Request) -> web.StreamResponse:
        asset = store.files.get(request.match_info["name"])
        if asset is None:
            raise web.HTTPNotFound()
        return store.response(request, asset, REVALIDATE)

    app.router.add_get("/", index)
    app.router.add_get(r"/s/{version:[0-9a-f]{6,16}}/{name:[A-Za-z0-9_.-]+}", versioned)
    app.router.add_get(r"/s/{name:[A-Za-z0-9_.-]+}", plain)
    return store
