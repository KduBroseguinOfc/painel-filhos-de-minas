#!/usr/bin/env bash
# Certificado autoassinado de 100 anos do painel, para o nome interno (NOME_DNS) e o IP (IP_APP) do arquivo de ambiente.
# Idempotente: nao sobrescreve. Para os navegadores do municipio nao avisarem, distribua /etc/painel-filhosdeminas/tls/painel.crt
# como certificado confiavel (GPO do AD, perfil do navegador): e um certificado proprio, nao uma CA.
set -euo pipefail
ENV_ARQ="${1:-/etc/painel-filhosdeminas/env}"
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
carregar_env "$ENV_ARQ"
D=/etc/painel-filhosdeminas/tls
[ -s $D/painel.crt ] && { echo "ja existe: $D/painel.crt"; openssl x509 -in $D/painel.crt -noout -subject -dates; exit 0; }
install -d -o root -g www-data -m 750 $D
umask 077
openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 36500 \
  -keyout $D/painel.key -out $D/painel.crt \
  -subj "/C=BR/ST=${UF}/L=${MUNICIPIO}/O=${PREFEITURA}/OU=${ORGAO}/CN=${NOME_DNS}" \
  -addext "subjectAltName=DNS:${NOME_DNS},DNS:$(hostname -s),IP:${IP_APP}" \
  -addext "basicConstraints=CA:FALSE" -addext "keyUsage=digitalSignature,keyEncipherment" -addext "extendedKeyUsage=serverAuth"
chown root:www-data $D/painel.key $D/painel.crt; chmod 640 $D/painel.key; chmod 644 $D/painel.crt
openssl x509 -in $D/painel.crt -noout -subject -dates -ext subjectAltName
