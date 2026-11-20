#!/usr/bin/env python3
"""Container probe: HTTP first, then the heartbeat file. Exit 0 when healthy."""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    port = int(os.environ.get("HEALTH_PORT", "8080"))
    if port <= 0:
        # On Render health lives on the public port next to the Mini App.
        port = int(os.environ.get("PORT", "0") or 0)
    if port > 0:
        url = f"http://127.0.0.1:{port}/health"
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                if 200 <= response.status < 300:
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    path = Path(os.environ.get("HEALTH_FILE", "/tmp/ritm-health"))
    stale = int(os.environ.get("HEALTH_STALE_SECONDS", "120"))
    if not path.is_file():
        return 1
    age = time.time() - path.stat().st_mtime
    return 0 if age <= stale else 1


if __name__ == "__main__":
    sys.exit(main())
