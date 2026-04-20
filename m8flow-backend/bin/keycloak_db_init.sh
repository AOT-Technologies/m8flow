#!/bin/sh
set -e

echo "Waiting for Postgres..."
until pg_isready -h m8flow-db -p 5432 -U "$POSTGRES_USER" >/dev/null 2>&1; do
  sleep 1
done

export PGPASSWORD="$POSTGRES_PASSWORD"

exists="$(psql -h m8flow-db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='keycloak'")"
if [ "$exists" != "1" ]; then
  psql -h m8flow-db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE keycloak"
fi

echo "keycloak db ready"
