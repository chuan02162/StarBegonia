#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-${DEPLOY_SSH_TARGET:-}}"
REMOTE_DIR="${2:-${DEPLOY_REMOTE_DIR:-StarBegonia}}"

if [[ -z "$TARGET" || "$TARGET" == -* ]]; then
  echo "Usage: $0 SSH_TARGET [REMOTE_DIR]" >&2
  echo "Example: $0 hyc@1cchome1.duckdns.org StarBegonia" >&2
  echo "SSH_TARGET may also be an alias from ~/.ssh/config." >&2
  exit 2
fi
if [[ ! "$REMOTE_DIR" =~ ^[A-Za-z0-9._/-]+$ || "$REMOTE_DIR" == /* || "$REMOTE_DIR" == *..* ]]; then
  echo "REMOTE_DIR must be a safe relative path under the remote user's home." >&2
  exit 2
fi
for command_name in ssh rsync; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

echo "Checking SSH target and remote deployment prerequisites..."
if ! ssh "$TARGET" "command -v docker >/dev/null && docker compose version >/dev/null && command -v rsync >/dev/null && test -f '$REMOTE_DIR/.env'"; then
  echo "Remote setup is incomplete. Ensure Docker Compose v2 and rsync are installed," >&2
  echo "and that ~/$REMOTE_DIR/.env exists. The script never copies local .env." >&2
  exit 1
fi

echo "Syncing project files to $TARGET:~/$REMOTE_DIR (remote .env is preserved)..."
# --delete removes stale code files from the dedicated deployment directory;
# excluded environment and secret files are protected from deletion by rsync.
rsync -az --delete --human-readable \
  --exclude='/.env' \
  --exclude='/.env.*' \
  --exclude='/.git/' \
  --exclude='/backend/secrets/' \
  --exclude='*.pem' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.DS_Store' \
  "$ROOT_DIR/" "$TARGET:$REMOTE_DIR/"

echo "Checking the remote HTTPS settings..."
if ! ssh "$TARGET" "cd '$REMOTE_DIR' && grep -qx 'APP_PUBLIC_URL=https://1cchome1.duckdns.org' .env && grep -Eq '^CORS_ORIGINS=https://1cchome1[.]duckdns[.]org(,|$)' .env"; then
  echo "Set these values in ~/$REMOTE_DIR/.env before deploying:" >&2
  echo "  APP_PUBLIC_URL=https://1cchome1.duckdns.org" >&2
  echo "  CORS_ORIGINS=https://1cchome1.duckdns.org" >&2
  exit 1
fi

echo "Building and deploying the HTTPS stack..."
ssh "$TARGET" "cd '$REMOTE_DIR' && docker compose -f docker-compose.yml -f docker-compose.https.yml --env-file .env up -d --build && docker compose -f docker-compose.yml -f docker-compose.https.yml --env-file .env ps"

echo "Deployment command completed. Check the certificate with:"
echo "  ssh $TARGET 'cd $REMOTE_DIR && docker compose -f docker-compose.yml -f docker-compose.https.yml logs --tail=100 caddy'"
echo "Site: https://1cchome1.duckdns.org"
