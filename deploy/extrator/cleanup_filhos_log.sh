#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE="/opt/extrator-esus/logs/filhos_de_minas_hourly.log"
LIMIT_BYTES=104857600

if [ ! -f "$LOG_FILE" ]; then
  exit 0
fi

CURRENT_SIZE=$(stat -c%s "$LOG_FILE")

if [ "$CURRENT_SIZE" -ge "$LIMIT_BYTES" ]; then
  : > "$LOG_FILE"
fi
