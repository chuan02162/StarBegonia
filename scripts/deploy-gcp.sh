#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILES=(
  -f "$ROOT_DIR/docker-compose.yml"
  -f "$ROOT_DIR/docker-compose.https.yml"
)
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ROOT_DIR/docker-compose.yml" || ! -f "$ROOT_DIR/Caddyfile" ]]; then
  echo "Run this script from a StarBegonia checkout containing the HTTPS files." >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Create the server's production .env first; this script will not copy local secrets." >&2
  exit 1
fi
if ! grep -qx 'APP_PUBLIC_URL=https://1cchome1.duckdns.org' "$ENV_FILE"; then
  echo "Set APP_PUBLIC_URL=https://1cchome1.duckdns.org in the server .env first." >&2
  exit 1
fi
if ! grep -Eq '^CORS_ORIGINS=https://1cchome1[.]duckdns[.]org(,|$)' "$ENV_FILE"; then
  echo "Set CORS_ORIGINS=https://1cchome1.duckdns.org in the server .env first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required on this VM." >&2
  exit 1
fi

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "Cannot access Docker. Add this user to the docker group or install sudo." >&2
    exit 1
  fi
  echo "Requesting sudo access to Docker..."
  sudo -v
  DOCKER=(sudo docker)
fi
if ! "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required on this VM." >&2
  exit 1
fi

cd "$ROOT_DIR"
echo "Checking the production Compose configuration..."
"${DOCKER[@]}" compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" config --quiet

echo "Building and starting StarBegonia with HTTPS..."
"${DOCKER[@]}" compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d --build
"${DOCKER[@]}" compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" ps

echo "Deploy command completed. Caddy certificate logs:"
"${DOCKER[@]}" compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" logs --tail=80 caddy
echo "Site: https://1cchome1.duckdns.org"
