#!/usr/bin/env bash
# Limpeza da tabela module_logs do banco local do Extrator PEC e-SUS (Filhos de Minas).
# Apaga as linhas de log com mais de RETENCAO_DIAS dias e compacta o arquivo (VACUUM).
# NUNCA toca em module_items (historico de envio) nem em module_syncs.
# Usa o mesmo lock da rotina horaria: se ela estiver rodando, espera ate 10 min; se este script
# estiver rodando, a rotina horaria pula a vez (flock -n dela) e volta na hora seguinte.
# Uso: limpa_logs_banco.sh [dias]   (padrao 30). Roda como usuario extrator.
set -Eeuo pipefail

RETENCAO_DIAS="${1:-30}"
DB="/opt/extrator-esus/.extrator-pec-esus/data/extrator-local.db"
LOCK_FILE="/opt/extrator-esus/locks/filhos_de_minas_hourly.lock"
LOG_FILE="/opt/extrator-esus/logs/limpa_logs_banco.log"

case "$RETENCAO_DIAS" in ''|*[!0-9]*) echo "retencao invalida: $RETENCAO_DIAS" >&2; exit 2;; esac

mkdir -p /opt/extrator-esus/logs /opt/extrator-esus/locks
exec 9>"$LOCK_FILE"
if ! flock -w 600 9; then
  echo "[$(date '+%F %T')] Rotina horaria em andamento ha mais de 10 min. Saindo sem limpar." >> "$LOG_FILE"
  exit 0
fi
exec >> "$LOG_FILE" 2>&1

ini=$(date +%s)
bytes_antes=$(stat -c %s "$DB")
linhas_antes=$(sqlite3 -cmd ".timeout 60000" "$DB" "SELECT count(*) FROM module_logs;")
sqlite3 -cmd ".timeout 60000" "$DB" "DELETE FROM module_logs WHERE created_at < datetime('now', '-${RETENCAO_DIAS} days');"
linhas_depois=$(sqlite3 -cmd ".timeout 60000" "$DB" "SELECT count(*) FROM module_logs;")
sqlite3 -cmd ".timeout 60000" "$DB" "VACUUM;"
bytes_depois=$(stat -c %s "$DB")
itens=$(sqlite3 -readonly "$DB" "SELECT count(*) || ' itens, ' || sum(queued) || ' enviados' FROM module_items;")
echo "[$(date '+%F %T')] module_logs: ${linhas_antes} -> ${linhas_depois} linhas (retencao ${RETENCAO_DIAS} dias); banco: $((bytes_antes/1048576)) MB -> $((bytes_depois/1048576)) MB; module_items intacta: ${itens}; duracao $(( $(date +%s) - ini )) s"
