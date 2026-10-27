#!/bin/sh
# Nightly logical backup of the Osiris database (schema `public`) to Cloudflare R2.
# The dump is encrypted before it leaves the container, so R2 only ever holds ciphertext.
# Runs as the Render cron job `osiris-db-backup` (render.yaml). Restore: docs/deployment/production.md.
set -eu
set -o pipefail

: "${OSIRIS_DATABASE_URL:?OSIRIS_DATABASE_URL is required}"
: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required}"
: "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required}"
: "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required}"

# The API's URL names the SQLAlchemy driver (postgresql+psycopg://); pg_dump wants plain libpq form.
url=$(printf '%s' "$OSIRIS_DATABASE_URL" | sed -e 's#^postgresql+[a-z0-9]*://#postgresql://#' -e 's#^postgres://#postgresql://#')
stamp=$(date -u +%Y%m%dT%H%M%SZ)
key="osiris/$(date -u +%Y/%m)/osiris-${stamp}.dump.enc"

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION=auto

pg_dump --format=custom --no-owner --no-privileges --schema=public "$url" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE \
  | aws s3 cp - "s3://${R2_BUCKET}/${key}" \
      --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com" --only-show-errors

echo "backup uploaded: s3://${R2_BUCKET}/${key}"
