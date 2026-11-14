#!/usr/bin/env bash
# Instalador do Painel Filhos de Minas (e, opcionalmente, do Extrator PEC e-SUS da SES-MG) num Ubuntu Server 24.04 limpo.
# Uso, como root:   ./instalar.sh meu-municipio.env
# Le o arquivo de variaveis (modelo: deploy/env.exemplo), instala tudo e publica o painel em https://NOME_DNS na rede
# interna, com certificado autoassinado. Pode ser executado de novo (atualizacao): mantem banco, usuarios e certificado.
set -Eeuo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
ENV_ORIGEM="${1:-}"
ENV_DEST=/etc/painel-filhosdeminas/env
APP=/opt/painel-filhosdeminas/app
VENV=/opt/painel-filhosdeminas/venv
DADOS=/var/lib/painel-filhosdeminas
EXT_HOME=/opt/extrator-esus
LOG=/var/log/painel-filhosdeminas-instalacao.log

carregar_env(){   # exporta CHAVE=valor do arquivo sem passar pelo shell (valor com espaco ou aspas entra como esta)
  local l k v
  while IFS= read -r l || [ -n "$l" ]; do
    l="${l%$'\r'}"; [[ "$l" =~ ^[[:space:]]*# || -z "${l//[[:space:]]/}" ]] && continue
    [[ "$l" == *=* ]] || continue
    k="${l%%=*}"; v="${l#*=}"; k="${k//[[:space:]]/}"
    [[ "$k" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
    v="${v%"${v##*[![:space:]]}"}"; v="${v#"${v%%[![:space:]]*}"}"
    if [[ "$v" == \"*\" || "$v" == \'*\' ]]; then v="${v:1:${#v}-2}"; fi
    export "$k=$v"
  done < "$1"
}
azul(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
erro(){ printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'printf "\033[1;31mFalhou na linha $LINENO. Log completo: $LOG\033[0m\n" >&2; rm -f /opt/extrator-esus/tmp.*.json' ERR

[ "$(id -u)" = 0 ] || erro "rode como root (sudo ./instalar.sh arquivo.env)"
grep -qs 'Ubuntu' /etc/os-release || erro "feito para Ubuntu Server 24.04"
if [ -n "$ENV_ORIGEM" ]; then
  [ -f "$ENV_ORIGEM" ] || erro "arquivo de variaveis nao encontrado: $ENV_ORIGEM"
elif [ -f "$ENV_DEST" ]; then
  ENV_ORIGEM=$ENV_DEST
else
  erro "informe o arquivo de variaveis: ./instalar.sh meu-municipio.env (modelo em deploy/env.exemplo)"
fi
[ -e "$LOG" ] || install -m 600 /dev/null "$LOG"; chmod 600 "$LOG"   # o log guarda a senha do admin criado: so root le
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] instalacao iniciada ($ENV_ORIGEM)"

# ---------------------------------------------------------------- variaveis
carregar_env "$ENV_ORIGEM"
for v in MUNICIPIO UF NOME_DNS IP_APP DW_HOST DW_PORT DW_DB DW_USER DW_PASSWORD; do
  [ -n "${!v:-}" ] || erro "variavel obrigatoria vazia: $v"
done
: "${PREFEITURA:=Prefeitura Municipal de $MUNICIPIO}"; : "${ORGAO:=Secretaria Municipal de Saude}"
: "${URL_PUBLICA:=https://$NOME_DNS}"; : "${DB_PAINEL:=$DADOS/painel.db}"
: "${EXTRATOR_DB:=$EXT_HOME/.extrator-pec-esus/data/extrator-local.db}"; : "${EXTRATOR_LOG:=$EXT_HOME/logs/filhos_de_minas_hourly.log}"
: "${EXTRATOR_INSTALAR:=0}"; : "${EXTRATOR_CORRECOES:=1}"; : "${EXTRATOR_ROTINA:=1}"; : "${NODE_VERSAO:=24.22.1}"
if [ "$EXTRATOR_INSTALAR" = 1 ]; then
  [ -f "${EXTRATOR_PACOTE:-}" ] || erro "EXTRATOR_INSTALAR=1 mas EXTRATOR_PACOTE nao aponta para o .tgz do extrator"
  for v in EXTRATOR_DW_USER EXTRATOR_DW_PASSWORD SES_API_USER SES_API_PASSWORD EXTRATOR_RESP_NOME EXTRATOR_RESP_EMAIL EXTRATOR_RESP_TELEFONE EXTRATOR_RESP_CARGO; do
    [ -n "${!v:-}" ] || erro "extrator: variavel obrigatoria vazia: $v"
  done
fi
export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------- pacotes do sistema
azul "Pacotes do sistema"
apt-get update -q
apt-get install -y -q nginx python3 python3-venv python3-pip sqlite3 openssl curl patch xz-utils ca-certificates acl rsync >/dev/null
echo "nginx $(nginx -v 2>&1 | cut -d/ -f2), python $(python3 -V | cut -d' ' -f2)"

# ---------------------------------------------------------------- usuarios e pastas
azul "Usuario de servico e pastas"
id painelfm >/dev/null 2>&1 || useradd --system --home-dir $DADOS --no-create-home --shell /usr/sbin/nologin painelfm
install -d -o root -g painelfm -m 750 /etc/painel-filhosdeminas
install -d -o root -g painelfm -m 755 /opt/painel-filhosdeminas
install -d -o painelfm -g painelfm -m 750 $DADOS $DADOS/fotos-ubs

# ---------------------------------------------------------------- arquivo de ambiente
azul "Arquivo de ambiente ($ENV_DEST)"
if [ "$(readlink -f "$ENV_ORIGEM")" != "$(readlink -f "$ENV_DEST")" ]; then
  CHAVE_ANTIGA=""
  if [ -f $ENV_DEST ]; then
    CHAVE_ANTIGA=$(grep -E '^DJANGO_SECRET_KEY=.{20,}' $ENV_DEST | head -1 || true)
    cp -p $ENV_DEST "$ENV_DEST.anterior-$(date +%Y%m%d-%H%M%S)"
    echo "AVISO: $ENV_DEST foi substituido por $ENV_ORIGEM (copia do anterior ao lado). Depois da primeira instalacao, edite $ENV_DEST e rode ./instalar.sh sem argumento."
  fi
  install -o root -g painelfm -m 640 "$ENV_ORIGEM" $ENV_DEST
  if [ -n "$CHAVE_ANTIGA" ] && ! grep -qE '^DJANGO_SECRET_KEY=.{20,}' $ENV_DEST; then   # mantem a chave (sessoes continuam validas)
    sed -i '/^DJANGO_SECRET_KEY=/d' $ENV_DEST; echo "$CHAVE_ANTIGA" >> $ENV_DEST
  fi
fi
if ! grep -qE '^DJANGO_SECRET_KEY=.{20,}' $ENV_DEST; then
  CHAVE=$(openssl rand -base64 48 | tr -d '\n')
  if grep -q '^DJANGO_SECRET_KEY=' $ENV_DEST; then sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$CHAVE|" $ENV_DEST; else echo "DJANGO_SECRET_KEY=$CHAVE" >> $ENV_DEST; fi
  echo "DJANGO_SECRET_KEY gerada"
fi
for par in "URL_PUBLICA=$URL_PUBLICA" "DB_PAINEL=$DB_PAINEL" "EXTRATOR_DB=$EXTRATOR_DB" "EXTRATOR_LOG=$EXTRATOR_LOG" "PREFEITURA=$PREFEITURA" "ORGAO=$ORGAO"; do
  k=${par%%=*}; grep -qE "^$k=." $ENV_DEST || { sed -i "/^$k=/d" $ENV_DEST; echo "$par" >> $ENV_DEST; }
done
chown root:painelfm $ENV_DEST; chmod 640 $ENV_DEST
carregar_env $ENV_DEST

# ---------------------------------------------------------------- aplicacao
azul "Aplicacao em $APP"
install -d -o root -g painelfm -m 750 $APP
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' --exclude staticfiles "$AQUI/painel/" $APP/
install -d -o painelfm -g painelfm -m 750 $APP/staticfiles
chown -R root:painelfm $APP; chown -R painelfm:painelfm $APP/staticfiles
chmod -R g+rX,g-w,o-rwx $APP; chmod -R u+w $APP/staticfiles
chmod o+rx /opt/painel-filhosdeminas $APP $APP/staticfiles; chmod -R o+rX $APP/staticfiles   # /static servido pelo nginx
[ -x $VENV/bin/python ] || python3 -m venv $VENV
$VENV/bin/pip install -q --upgrade pip
$VENV/bin/pip install -q -r $APP/requirements.txt
$VENV/bin/pip check >/dev/null && echo "dependencias Python ok ($($VENV/bin/pip list 2>/dev/null | grep -c . ) pacotes)"

install -o root -g root -m 755 "$AQUI/deploy/painel-filhosdeminas" /usr/local/bin/painel-filhosdeminas   # comandos de manutencao

# ---------------------------------------------------------------- DW: conexao e permissoes
azul "Teste do DW do PEC e-SUS ($DW_HOST:$DW_PORT/$DW_DB como $DW_USER)"
$VENV/bin/python - <<'PY'
import os, sys, psycopg
E = os.environ
try:
    con = psycopg.connect(host=E["DW_HOST"], port=int(E["DW_PORT"]), dbname=E["DW_DB"], user=E["DW_USER"], password=E["DW_PASSWORD"], connect_timeout=10,
                          options="-c default_transaction_read_only=on")
except Exception as e:
    print(f"nao conectou ao DW: {e}\n  confira DW_* no arquivo de variaveis, o pg_hba.conf do servidor do banco e a rede (porta {E['DW_PORT']})"); sys.exit(1)
faltam = []
for t in ["tb_cds_cad_domiciliar", "tb_cds_cad_individual", "tb_cds_domicilio_familia", "tb_cidadao", "tb_dim_ciap", "tb_dim_cid", "tb_dim_dose_imunobiologico", "tb_dim_equipe", "tb_dim_imunobiologico", "tb_dim_procedimento", "tb_dim_profissional", "tb_dim_tempo", "tb_dim_tipo_logradouro", "tb_dim_unidade_saude", "tb_fat_atd_ind_problemas", "tb_fat_atd_ind_procedimentos", "tb_fat_atendimento_individual", "tb_fat_cidadao_pec", "tb_fat_rel_op_gestante", "tb_fat_vacinacao", "tb_fat_vacinacao_vacina", "tb_localidade", "tb_unidade_saude"]:
    try:
        con.execute(f"select 1 from {t} limit 1").fetchone()
    except Exception as e:
        faltam.append(t); con.rollback()
if faltam:
    print("sem SELECT nestas tabelas: " + ", ".join(faltam) + "\n  rode deploy/dw-papel-somente-leitura.sql no servidor do banco"); sys.exit(1)
n = con.execute("select count(*) from tb_dim_unidade_saude").fetchone()[0]
print(f"DW ok: {n} unidades de saude; versao {con.execute('show server_version').fetchone()[0]}")
PY

# ---------------------------------------------------------------- banco do painel e admin
azul "Banco do painel, arquivos estaticos e administrador"
cd $APP
sudo -E -u painelfm $VENV/bin/python manage.py migrate --noinput | tail -1
sudo -u painelfm sqlite3 "$DB_PAINEL" "PRAGMA journal_mode=WAL;" >/dev/null
sudo -E -u painelfm $VENV/bin/python manage.py collectstatic --noinput -v 0
ADMIN_SAIDA=$(sudo -E -u painelfm $VENV/bin/python manage.py criar_admin)
if echo "$ADMIN_SAIDA" | grep -q "^SENHA="; then echo "administrador local: $(echo "$ADMIN_SAIDA" | tr '\n' ' ')  <- anote agora (se a instalacao falhar mais adiante, isto nao e repetido)"; else echo "administrador local: $ADMIN_SAIDA"; fi
if [ -f /etc/painel-filhosdeminas/ubs-coordenadas.json ]; then
  sudo -E -u painelfm $VENV/bin/python manage.py fixar_ubs /etc/painel-filhosdeminas/ubs-coordenadas.json | tail -1 || true
fi
sudo -E -u painelfm $VENV/bin/python manage.py check --deploy 2>&1 | tail -1

# ---------------------------------------------------------------- certificado e nginx
azul "Certificado autoassinado e nginx (https://$NOME_DNS)"
bash "$AQUI/deploy/gera-certificado.sh" $ENV_DEST | tail -2
REAL_IP=""
for ip in ${PROXY_REVERSO_IP//,/ }; do REAL_IP="${REAL_IP}set_real_ip_from $ip;\n"; done
[ -n "$REAL_IP" ] && REAL_IP="${REAL_IP}real_ip_header X-Real-IP;"
sed -e "s/__NOME_DNS__/$NOME_DNS/g" -e "s/__IP_APP__/$IP_APP/g" -e "s/^__REAL_IP__$/$REAL_IP/" "$AQUI/deploy/nginx-painel-filhosdeminas.conf" > /etc/nginx/sites-available/painel-filhosdeminas
ln -sfn /etc/nginx/sites-available/painel-filhosdeminas /etc/nginx/sites-enabled/painel-filhosdeminas
if [ -L /etc/nginx/sites-enabled/default ] && grep -q 'listen 80 default_server' /etc/nginx/sites-enabled/default; then
  rm -f /etc/nginx/sites-enabled/default      # a pagina de boas-vindas do nginx disputaria a porta 80
fi
nginx -t 2>&1 | tail -1
systemctl enable --now nginx >/dev/null 2>&1; systemctl reload nginx

# ---------------------------------------------------------------- servicos do painel
azul "Servicos do painel (systemd)"
install -o root -g root -m 644 "$AQUI"/deploy/systemd/*.service "$AQUI"/deploy/systemd/*.timer /etc/systemd/system/
# o painel e a coleta leem o banco do extrator: a pasta dele precisa existir dentro do sandbox das units (ProtectSystem/ProtectHome).
# Extrator instalado por outro usuario, com o banco em /root ou /home (cenario 1): ProtectHome passa a read-only.
for u in painel-filhosdeminas painel-filhosdeminas-coleta; do
  install -d -m 755 /etc/systemd/system/$u.service.d
  { echo "# gerado pelo instalar.sh a partir de EXTRATOR_DB"; echo "[Service]"
    case "$EXTRATOR_DB" in /root/*|/home/*) echo "ProtectHome=read-only";; esac
    echo "ReadOnlyPaths=-$(dirname "$EXTRATOR_DB")"; } > /etc/systemd/system/$u.service.d/extrator.conf
done
systemctl daemon-reload
systemctl enable --now painel-filhosdeminas.service painel-filhosdeminas-coleta.timer painel-filhosdeminas-conferir-ses.timer painel-filhosdeminas-geo.timer painel-filhosdeminas-alertas-dia.timer >/dev/null 2>&1
systemctl restart painel-filhosdeminas.service
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then systemctl enable --now painel-filhosdeminas-telegram.service >/dev/null 2>&1; systemctl restart painel-filhosdeminas-telegram.service; else systemctl disable --now painel-filhosdeminas-telegram.service >/dev/null 2>&1 || true; fi
sleep 2; systemctl is-active painel-filhosdeminas.service
curl -sk -o /dev/null -w "painel responde: HTTP %{http_code} em https://$NOME_DNS/saude (503 = ainda sem coleta, normal agora)\n" --resolve "$NOME_DNS:443:127.0.0.1" "https://$NOME_DNS/saude"

# ---------------------------------------------------------------- extrator (opcional)
if [ "$EXTRATOR_INSTALAR" = 1 ]; then
  azul "Extrator PEC e-SUS (SES-MG): Node.js $NODE_VERSAO e pacote $(basename "$EXTRATOR_PACOTE")"
  id extrator >/dev/null 2>&1 || useradd --system --home-dir $EXT_HOME --create-home --shell /bin/bash extrator
  install -d -o extrator -g extrator -m 755 $EXT_HOME/bin $EXT_HOME/logs $EXT_HOME/locks $EXT_HOME/packages; chmod 750 $EXT_HOME
  if [ ! -x /usr/local/lib/nodejs/node-v$NODE_VERSAO-linux-x64/bin/node ]; then
    T=$(mktemp -d); ( cd "$T" && curl -fsSLO "https://nodejs.org/dist/v$NODE_VERSAO/node-v$NODE_VERSAO-linux-x64.tar.xz" \
      && curl -fsSLO "https://nodejs.org/dist/v$NODE_VERSAO/SHASUMS256.txt" && grep " node-v$NODE_VERSAO-linux-x64.tar.xz" SHASUMS256.txt | sha256sum -c - >/dev/null \
      && mkdir -p /usr/local/lib/nodejs && tar -xJf "node-v$NODE_VERSAO-linux-x64.tar.xz" -C /usr/local/lib/nodejs ); rm -rf "$T"
  fi
  for b in node npm npx; do ln -sfn /usr/local/lib/nodejs/node-v$NODE_VERSAO-linux-x64/bin/$b /usr/local/bin/$b; done
  echo "node $(node -v)"
  cp -f "$EXTRATOR_PACOTE" $EXT_HOME/packages/; chown extrator:extrator $EXT_HOME/packages/*
  echo "sha256 do pacote: $(sha256sum "$EXTRATOR_PACOTE" | cut -c1-64)  (confira com o publicado pela SES-MG)"
  EXTRATOR_SKIP_POSTINSTALL=true npm i -g --no-fund --no-audit "$EXT_HOME/packages/$(basename "$EXTRATOR_PACOTE")" >/dev/null
  ln -sfn "/usr/local/lib/nodejs/node-v$NODE_VERSAO-linux-x64/bin/extrator-esus" /usr/local/bin/extrator-esus
  if [ "$EXTRATOR_CORRECOES" = 1 ]; then bash "$AQUI/extrator/aplicar-correcoes.sh"; fi
  E="sudo -u extrator -H /usr/local/bin/extrator-esus"
  $E config-set --module filhos_de_minas --set dw.type=postgres --set dw.host="$DW_HOST" --set dw.port="$DW_PORT" --set dw.database="$DW_DB" --set dw.user="$EXTRATOR_DW_USER" >/dev/null
  $E config-set --module filhos_de_minas --set "user.name=$EXTRATOR_RESP_NOME" --set "user.email=$EXTRATOR_RESP_EMAIL" --set "user.phone=$EXTRATOR_RESP_TELEFONE" --set "user.city=$MUNICIPIO" --set "user.role=$EXTRATOR_RESP_CARGO" >/dev/null
  $E config-set --module filhos_de_minas --set "api.user=$SES_API_USER" --set termsAccepted=true --set "baseUrl=${SES_API_URL:-https://filhosdeminas.saude.mg.gov.br/api}" >/dev/null
  SEG=$(mktemp -p $EXT_HOME --suffix=.json); chown extrator "$SEG"; chmod 600 "$SEG"   # o CLI carrega o arquivo com require(): precisa terminar em .json
  $VENV/bin/python -c 'import json,os,sys; json.dump({"dw.password": os.environ["EXTRATOR_DW_PASSWORD"], "api.password": os.environ["SES_API_PASSWORD"]}, open(sys.argv[1], "w"))' "$SEG"
  $E config-set --module filhos_de_minas --json "$SEG" >/dev/null; shred -u "$SEG"
  chmod 600 $EXT_HOME/.extrator-pec-esus/config/modules-config.json
  $E list-modules 2>&1 | grep -i filhos || true
  install -o extrator -g extrator -m 750 "$AQUI"/deploy/extrator/*.sh $EXT_HOME/bin/
  install -o root -g root -m 644 "$AQUI"/deploy/extrator/*.service "$AQUI"/deploy/extrator/*.timer /etc/systemd/system/
  systemctl daemon-reload
  echo "primeira importacao do DW (pode levar alguns minutos)..."
  ( cd $EXT_HOME && $E run --module filhos_de_minas 2>&1 | tail -3 )
  # o painel le o banco e o log do extrator: so leitura, por ACL
  setfacl -m u:painelfm:x $EXT_HOME; setfacl -m u:painelfm:rx $EXT_HOME/.extrator-pec-esus $EXT_HOME/.extrator-pec-esus/data $EXT_HOME/logs
  setfacl -d -m u:painelfm:r $EXT_HOME/.extrator-pec-esus/data $EXT_HOME/logs
  [ -f "$EXTRATOR_DB" ] && setfacl -m u:painelfm:r "$EXTRATOR_DB"; [ -f "$EXTRATOR_LOG" ] && setfacl -m u:painelfm:r "$EXTRATOR_LOG" || true
  systemctl enable --now cleanup-filhos-log.timer limpa-logs-banco-filhos.timer >/dev/null 2>&1
  if [ "$EXTRATOR_ROTINA" = 1 ]; then
    systemctl enable --now filhos-de-minas-hourly.timer >/dev/null 2>&1; echo "rotina horaria do extrator LIGADA (importa e envia a SES-MG a cada hora)"
  else
    systemctl disable --now filhos-de-minas-hourly.timer >/dev/null 2>&1 || true; echo "rotina horaria do extrator DESLIGADA (EXTRATOR_ROTINA=0): nada e enviado a SES-MG"
  fi
fi

# ---------------------------------------------------------------- extrator ja existente nesta maquina (cenario 1): leitura por ACL
if [ "$EXTRATOR_INSTALAR" != 1 ] && [ -f "$EXTRATOR_DB" ] && ! sudo -u painelfm test -r "$EXTRATOR_DB"; then
  azul "Extrator ja instalado: liberando leitura do banco e do log para o painel (ACL, so leitura)"
  d="$(dirname "$EXTRATOR_DB")"; while [ "$d" != "/" ]; do setfacl -m u:painelfm:x "$d"; d="$(dirname "$d")"; done
  setfacl -m u:painelfm:rx "$(dirname "$EXTRATOR_DB")"; setfacl -m u:painelfm:r "$EXTRATOR_DB"; setfacl -d -m u:painelfm:r "$(dirname "$EXTRATOR_DB")"
  sudo -u painelfm test -r "$EXTRATOR_DB" && echo "painel le $EXTRATOR_DB"
fi

# ---------------------------------------------------------------- primeira coleta do painel
if [ -r "$EXTRATOR_DB" ] || sudo -u painelfm test -r "$EXTRATOR_DB"; then
  azul "Primeira coleta do painel"
  ( cd $APP && sudo -E -u painelfm $VENV/bin/python manage.py coletar 2>&1 | tail -2 ) || echo "coleta falhou agora; o timer tenta de novo aos 50 min de cada hora (journalctl -u painel-filhosdeminas-coleta)"
else
  echo "banco do extrator nao encontrado em $EXTRATOR_DB: o painel sobe vazio. Extrator ja instalado em outro caminho? Ajuste EXTRATOR_DB no env e rode de novo."
fi

# ---------------------------------------------------------------- resumo
azul "Pronto"
cat <<FIM
Painel:        https://$NOME_DNS  (tambem https://$IP_APP)  — crie o registro DNS interno $NOME_DNS -> $IP_APP
Certificado:   /etc/painel-filhosdeminas/tls/painel.crt (autoassinado, 100 anos): distribua como confiavel nas estacoes
Administrador: $(echo "$ADMIN_SAIDA" | tr '\n' ' ')
               (a senha so aparece quando o admin e criado; para gerar outra: painel-filhosdeminas criar_admin --redefinir)
Comandos:      painel-filhosdeminas <comando>  (ex.: testar_email voce@municipio.gov.br, coletar, criar_admin --redefinir)
Configuracao:  $ENV_DEST  (depois de mudar: systemctl restart painel-filhosdeminas)
Servicos:      systemctl status painel-filhosdeminas painel-filhosdeminas-coleta.timer$([ "$EXTRATOR_INSTALAR" = 1 ] && echo " filhos-de-minas-hourly.timer")
Logs:          journalctl -u painel-filhosdeminas -u painel-filhosdeminas-coleta$([ "$EXTRATOR_INSTALAR" = 1 ] && echo "; $EXTRATOR_LOG")
Proximos:      publicar fora da rede interna (proxy reverso do municipio), SSO (SSO_ATIVO=1 + OIDC_* no env), fotos e coordenadas das UBS (README).
FIM
echo "[$(date '+%F %T')] instalacao concluida"
