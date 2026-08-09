#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${MYSQL_DATABASE:?Debe indicar MYSQL_DATABASE}"
: "${MYSQL_DEFAULTS_FILE:?Debe indicar MYSQL_DEFAULTS_FILE}"

BACKUP_DIR="/var/backups/seleccion"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
mysqldump --defaults-extra-file="$MYSQL_DEFAULTS_FILE" --single-transaction --routines --events \
  --databases "$MYSQL_DATABASE" | gzip > "$BACKUP_DIR/seleccion-$STAMP.sql.gz"
find "$BACKUP_DIR" -type f -name 'seleccion-*.sql.gz' -mtime +30 -delete
