#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BACKUP_DIR="/var/backups/seleccion"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
pg_dump --format=custom --no-owner --file="$BACKUP_DIR/seleccion-$STAMP.dump" "$DATABASE_URL"
find "$BACKUP_DIR" -type f -name 'seleccion-*.dump' -mtime +30 -delete
