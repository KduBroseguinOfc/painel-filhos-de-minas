#!/usr/bin/env bash
# Aplica as correcoes do modulo Filhos de Minas (extrator/README.md) sobre o Extrator PEC e-SUS 1.0.0 ja instalado
# com `npm i -g` (pasta lib/node_modules/extrator-pec-esus do Node em uso). Idempotente: se ja estiver aplicado, nada muda.
# Uso: aplicar-correcoes.sh [pasta-do-pacote]   (padrao: descobre pelo `node` do PATH)
set -euo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
DEST="${1:-$(dirname "$(dirname "$(readlink -f "$(command -v node)")")")/lib/node_modules/extrator-pec-esus}"
[ -f "$DEST/package.json" ] || { echo "pacote nao encontrado em $DEST" >&2; exit 1; }
VER=$(python3 -c "import json;print(json.load(open('$DEST/package.json'))['version'])")
[ "$VER" = "1.0.0" ] || { echo "este diff foi feito para a 1.0.0; instalada: $VER. Conferir o diff antes de aplicar." >&2; exit 2; }
if grep -q 'CORRECAO CNS' "$DEST/app/core/storage.js" && grep -q 'fora_recorte' "$DEST/modules/filhos_de_minas/sender.js"; then
  echo "correcoes ja aplicadas em $DEST"; exit 0
fi
patch -d "$DEST" -p1 --dry-run < "$AQUI/correcoes-1.0.0.diff" >/dev/null
patch -d "$DEST" -p1 -s < "$AQUI/correcoes-1.0.0.diff"
node --check "$DEST/app/core/storage.js" "$DEST/modules/filhos_de_minas/index.js" "$DEST/modules/filhos_de_minas/sender.js"
echo "correcoes aplicadas em $DEST (storage.js, filhos_de_minas/index.js, filhos_de_minas/sender.js)"
