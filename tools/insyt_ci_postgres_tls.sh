#!/usr/bin/env bash
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" ]]; then
  echo "STOP: PostgreSQL fixture is CI-only."
  exit 2
fi

NAME="insyt-ci-postgres-tls"

if docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "STOP: Existing test container found."
  exit 2
fi

docker run -d   --name "$NAME"   --publish 127.0.0.1:5432:5432   --env POSTGRES_USER=insyt_ci   --env POSTGRES_PASSWORD=synthetic_ci_only_password   --env POSTGRES_DB=insyt_release_validation   postgres:16 >/dev/null

ready=0
for attempt in $(seq 1 30); do
  if docker exec "$NAME"     pg_isready -U insyt_ci -d insyt_release_validation     >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" != "1" ]]; then
  echo "STOP: Test PostgreSQL did not start."
  exit 2
fi

docker exec -u postgres "$NAME" sh -c '
set -eu
cd "$PGDATA"
openssl req -new -x509 -nodes -days 1   -subj "/CN=localhost"   -keyout server.key -out server.crt >/dev/null 2>&1
chmod 600 server.key
chmod 644 server.crt
'

docker exec "$NAME" psql   -U insyt_ci -d insyt_release_validation   -v ON_ERROR_STOP=1   -c "ALTER SYSTEM SET ssl = 'on';" >/dev/null

docker restart "$NAME" >/dev/null

ready=0
for attempt in $(seq 1 30); do
  if docker exec "$NAME" psql     -U insyt_ci -d insyt_release_validation     -tAc "SHOW ssl;" 2>/dev/null | grep -qx "on"; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" != "1" ]]; then
  echo "STOP: Test PostgreSQL TLS failed."
  exit 2
fi

echo "PASS: Disposable PostgreSQL TLS enabled."
