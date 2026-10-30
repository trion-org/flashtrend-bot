#!/usr/bin/env bash
# Throwaway Postgres (pgvector) + PostgREST, the sql/*.sql files, then the integration test.
set -euo pipefail
cd "$(dirname "$0")/../.."
SECRET="integration-test-secret-integration-test-secret"
PG=ft-it-pg; REST=ft-it-rest; PGPORT=55433; RESTPORT=3001
cleanup() { docker rm -f "$PG" "$REST" >/dev/null 2>&1 || true; }
trap cleanup EXIT; cleanup

docker run -d --name "$PG" -e POSTGRES_PASSWORD=pw -p "$PGPORT:5432" pgvector/pgvector:pg16 >/dev/null
until docker exec "$PG" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
sleep 2
psql_() { docker exec -i "$PG" psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }
psql_ -c "create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;"
for f in sql/01_core.sql sql/02_media.sql sql/03_functions.sql sql/05_search_tuning.sql sql/06_bilibili.sql sql/07_analysis.sql sql/04_seed_app_config.sql; do psql_ < "$f"; done
# Supabase grants these by default; a plain Postgres does not
psql_ -c "grant usage on schema public to anon, authenticated, service_role;
          grant all on all tables in schema public to service_role;
          grant all on all sequences in schema public to service_role;"

docker run -d --name "$REST" --network host -e PGRST_DB_URI="postgres://postgres:pw@localhost:$PGPORT/postgres" \
  -e PGRST_DB_SCHEMAS=public -e PGRST_DB_ANON_ROLE=anon -e PGRST_JWT_SECRET="$SECRET" \
  -e PGRST_SERVER_PORT="$RESTPORT" postgrest/postgrest:latest >/dev/null
JWT=$(python3 - "$SECRET" <<'PY'
import base64, hashlib, hmac, json, sys
b = lambda d: base64.urlsafe_b64encode(d).rstrip(b"=")
head = b(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
body = b(json.dumps({"role": "service_role"}).encode())
sig = b(hmac.new(sys.argv[1].encode(), head + b"." + body, hashlib.sha256).digest())
print((head + b"." + body + b"." + sig).decode())
PY
)
until curl -fs "http://localhost:$RESTPORT/" -H "Authorization: Bearer $JWT" >/dev/null 2>&1; do sleep 1; done
FLASHTREND_TEST_REST_URL="http://localhost:$RESTPORT" FLASHTREND_TEST_JWT="$JWT" \
  uv run pytest tests/integration -v "$@"
