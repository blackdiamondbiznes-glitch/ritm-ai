#!/bin/sh
set -eu

ok=0
i=0
while [ "$i" -lt 30 ]; do
  if alembic upgrade head; then
    ok=1
    break
  fi
  i=$((i + 1))
  sleep 2
done

if [ "$ok" -ne 1 ]; then
  echo "migration failed" >&2
  exit 1
fi

exec python -m app.main
