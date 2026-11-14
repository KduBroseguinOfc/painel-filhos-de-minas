#!/usr/bin/env bash
# Remove o Painel Filhos de Minas desta maquina. Com --extrator, remove tambem o Extrator PEC e-SUS que o instalar.sh
# instalou (/opt/extrator-esus, inclusive o banco local dele). Extrator instalado por conta propria (cenario 1) nunca e tocado:
# so se retiram as permissoes que o instalar.sh deu ao painel na pasta dele.
# Uso, como root:   ./remover.sh [--extrator]
# Antes, se quiser guardar: /var/lib/painel-filhosdeminas (banco do painel) e /etc/painel-filhosdeminas (env e certificado).
# O banco do PEC nao e alterado: la, rode  DROP OWNED BY painelfm_ro; DROP ROLE painelfm_ro;  e tire as linhas do pg_hba.conf.
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo "rode como root (sudo ./remover.sh)" >&2; exit 1; }
EXTRATOR=0
for a in "$@"; do case "$a" in --extrator) EXTRATOR=1 ;; *) echo "opcao desconhecida: $a (uso: ./remover.sh [--extrator])" >&2; exit 2 ;; esac; done

DB=$(grep -E '^EXTRATOR_DB=' /etc/painel-filhosdeminas/env 2>/dev/null | tail -1 | cut -d= -f2-)
PAINEL_UNITS="painel-filhosdeminas.service painel-filhosdeminas-telegram.service
  painel-filhosdeminas-coleta.timer painel-filhosdeminas-coleta.service painel-filhosdeminas-conferir-ses.timer painel-filhosdeminas-conferir-ses.service
  painel-filhosdeminas-geo.timer painel-filhosdeminas-geo.service painel-filhosdeminas-alertas-dia.timer painel-filhosdeminas-alertas-dia.service"
for u in $PAINEL_UNITS; do systemctl disable --now "$u" >/dev/null 2>&1; done
rm -rf /etc/systemd/system/painel-filhosdeminas*.service /etc/systemd/system/painel-filhosdeminas*.timer /etc/systemd/system/painel-filhosdeminas*.service.d
systemctl daemon-reload; systemctl reset-failed >/dev/null 2>&1
pkill -u painelfm >/dev/null 2>&1; sleep 1
echo "servicos do painel removidos"

rm -f /etc/nginx/sites-enabled/painel-filhosdeminas /etc/nginx/sites-available/painel-filhosdeminas
if command -v nginx >/dev/null; then nginx -t >/dev/null 2>&1 && systemctl reload nginx && echo "site do nginx removido"; fi

if [ -n "$DB" ] && id painelfm >/dev/null 2>&1; then          # permissoes que o instalar.sh deu ao painel (ACL)
  setfacl -x u:painelfm "$DB" 2>/dev/null; setfacl -d -x u:painelfm "$(dirname "$DB")" 2>/dev/null
  d="$(dirname "$DB")"; while [ "$d" != "/" ]; do setfacl -x u:painelfm "$d" 2>/dev/null; d="$(dirname "$d")"; done
  echo "permissoes do painel em $(dirname "$DB") retiradas"
fi

rm -rf /opt/painel-filhosdeminas /var/lib/painel-filhosdeminas /etc/painel-filhosdeminas /usr/local/bin/painel-filhosdeminas
shred -u /var/log/painel-filhosdeminas-instalacao.log 2>/dev/null; rm -f /var/log/painel-filhosdeminas-instalacao.log
userdel painelfm >/dev/null 2>&1 && echo "usuario painelfm removido"
echo "painel removido"

if [ "$EXTRATOR" = 1 ]; then
  for u in filhos-de-minas-hourly cleanup-filhos-log limpa-logs-banco-filhos; do systemctl disable --now "$u.timer" "$u.service" >/dev/null 2>&1; rm -f "/etc/systemd/system/$u.timer" "/etc/systemd/system/$u.service"; done
  systemctl daemon-reload
  pkill -u extrator >/dev/null 2>&1; sleep 1
  command -v npm >/dev/null && npm rm -g extrator-pec-esus >/dev/null 2>&1
  rm -f /usr/local/bin/extrator-esus
  rm -rf /opt/extrator-esus
  userdel extrator >/dev/null 2>&1
  echo "extrator removido (o Node.js em /usr/local/lib/nodejs ficou; para tirar: rm -rf /usr/local/lib/nodejs /usr/local/bin/{node,npm,npx})"
fi
echo "pronto. O nginx e os pacotes do sistema ficaram instalados."
