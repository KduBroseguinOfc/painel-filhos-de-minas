#!/usr/bin/env bash
set -Eeuo pipefail

LOCK_FILE="/opt/extrator-esus/locks/filhos_de_minas_hourly.lock"
LOG_FILE="/opt/extrator-esus/logs/filhos_de_minas_hourly.log"
EXTRATOR_BIN="/usr/local/bin/extrator-esus"

mkdir -p /opt/extrator-esus/logs /opt/extrator-esus/locks

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date "+%F %T")] Outra execução já está em andamento. Saindo."
  exit 0
fi

exec >> "$LOG_FILE" 2>&1

echo "============================================================"
echo "[$(date "+%F %T")] Iniciando rotina Filhos de Minas"

echo "[$(date "+%F %T")] Rodando importação..."
"$EXTRATOR_BIN" run --module filhos_de_minas

echo "[$(date "+%F %T")] Rodando envio..."
"$EXTRATOR_BIN" send-filhos

echo "[$(date "+%F %T")] Rotina concluída com sucesso"
