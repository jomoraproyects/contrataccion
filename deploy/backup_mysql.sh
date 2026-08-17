#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${MYSQL_DATABASE:?Debe indicar MYSQL_DATABASE}"
: "${MYSQL_DEFAULTS_FILE:?Debe indicar MYSQL_DEFAULTS_FILE}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/seleccion}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
DESTINO="$BACKUP_DIR/seleccion-$STAMP.sql.gz"
mysqldump --defaults-extra-file="$MYSQL_DEFAULTS_FILE" --single-transaction --routines --events \
  --no-tablespaces --databases "$MYSQL_DATABASE" | gzip -9 > "$DESTINO"
test -s "$DESTINO"
gzip -t "$DESTINO"
sha256sum "$DESTINO" > "$DESTINO.sha256"
find "$BACKUP_DIR" -type f \( -name 'seleccion-*.sql.gz' -o -name 'seleccion-*.sql.gz.sha256' \) -mtime +30 -delete
