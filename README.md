# Painel Filhos de Minas

Painel para a Atenção Primária acompanhar o envio de gestantes ao programa **Filhos de Minas** (SES-MG) feito pelo
**Extrator PEC e-SUS**: quem foi aceita, quem está pendente e por quê (sem CNS, sem CPF, fora do Bolsa Família, erro da
API), por unidade e equipe, com lista nominal, fila de trabalho por UBS, desempenho, indicadores clínicos do pré-natal,
mapa, modo TV, conferência diária com a SES-MG e alertas por e-mail ou Telegram.

Nasceu na Prefeitura Municipal de Ipatinga/MG (2026) e é publicado para qualquer município usar. Licença MIT
(Prefeitura Municipal de Ipatinga, Gray Hat Sec e Karlos Broseguini). Código em português, sem dependência de serviço
pago ou nuvem.

## Como funciona

```
PEC e-SUS (PostgreSQL, DW) ──só leitura──▶ Extrator PEC e-SUS (SES-MG, Node) ──envia──▶ API Filhos de Minas (SES-MG)
            │                                       │ banco local (SQLite)
            └───────────só leitura──────────────────┴──────────▶ Painel (Django + SQLite) ──▶ nginx https:// na rede interna
```

- O painel **nunca escreve** no PEC nem no extrator; lê o DW com um papel só de SELECT e o SQLite do extrator em modo
  somente leitura, e monta a "foto" de cada gestante a cada hora (depois da rotina do extrator).
- Dados pessoais e de saúde ficam no servidor do município. Para o OpenStreetMap vai só o endereço (sem nome ou
  documento), para a SES-MG só o que o extrator já envia. O painel registra em trilha quem viu dado nominal, revelou CPF ou exportou (LGPD).
- Login: usuários locais (o instalador cria o administrador; a tela **Usuários** cria os demais, com papel
  *administrador* ou *visualização*; todos veem todas as unidades). Opcional: SSO do município por OpenID Connect.

Telas: Visão geral · Por UBS e equipe · Gestantes (filtros, CSV, ficha com histórico e conferência com a SES-MG) · Novas na
semana · Perto do parto · Fila de trabalho · Desempenho · Indicadores (funil, captação precoce, consultas, risco, exames
de sífilis/HIV/hepatite B/toxoplasmose) · Mapa (casa das gestantes e UBS, com foto e "como chegar") · Meus alertas ·
Situação do sistema (rotinas, coletas, conferência com a SES-MG, trilha de acesso) · Usuários · Modo TV.

## Antes de começar: o que você precisa ter

- **PEC e-SUS APS** funcionando, e alguém com a senha do `postgres` do banco dele (fica no `credenciais.txt` do PEC,
  ver o passo 1).
- **Uma máquina Ubuntu Server 24.04** para o painel, com acesso de root, IP fixo e saída para a internet (pacotes do
  Ubuntu, PyPI, nodejs.org, OpenStreetMap e a API da SES-MG). Bastam 2 vCPU, 4 GB de RAM e 40 GB de disco, com 20 GB livres
  para o banco do extrator crescer. **Não use a máquina do próprio PEC**: o PEC costuma ocupar as portas 80/443.
- **Rede**: a máquina do painel precisa alcançar o banco do PEC (porta 5433 no banco embutido do instalador do PEC, ou a
  porta do seu PostgreSQL, se ele for externo). Para testar: `nc -zv <ip-do-banco> <porta>`.
- **Um nome no DNS interno** para o painel (ex.: `filhosdeminas.saude.municipio.local`).
- Só no **cenário 2**: o pacote do extrator baixado do site da SES-MG e a **conta da API do Filhos de Minas** do
  município (usuário e senha fornecidos pela SES-MG).

## Qual é o seu cenário?

| Cenário | Quando | O que o instalador faz |
|---|---|---|
| **1. Já tem o extrator** | O Extrator PEC e-SUS (linha de comando, Linux) já roda e envia. **Rode o instalador nessa mesma máquina.** | Instala só o painel, dá a ele leitura (ACL) no banco do extrator e faz a primeira coleta. O extrator e a rotina dele ficam como estão. |
| **2. Não tem o extrator** | Nunca instalou, ou usa a versão Windows (com tela). | Instala o painel **e** o extrator oficial, aplica as correções (opcional), configura, faz a primeira importação e liga a rotina de hora em hora. |

O extrator na versão Windows não serve: o painel lê o banco do extrator no disco da própria máquina. Quem usa o
Windows vai pelo cenário 2 e **desliga o extrator do Windows** quando a rotina nova estiver ligada, senão as gestantes
são enviadas duas vezes.

## Passo 1 — No servidor do banco do PEC: usuário só de leitura e acesso pela rede

Feito uma vez, por quem administra o PEC. **Reiniciar o PostgreSQL derruba o PEC por alguns segundos: faça fora do
expediente.**

1. **Ache o banco e as senhas.** Na pasta de configuração do PEC (Linux: `/opt/e-SUS/webserver/config/`; Windows,
   normalmente: `C:\Program Files\e-SUS\webserver\config\`):
   - `application.properties`, linha `spring.datasource.url`: host, porta e nome do banco (ex.: `localhost:5433/esus`);
   - `credenciais.txt`: senhas do `postgres` (completo) e do `esus_leitura` (leitura, criado pelo instalador do PEC).
2. **Crie o usuário do painel** (`painelfm_ro`, só SELECT nas 23 tabelas que o painel lê). Gere uma senha forte e
   guarde-a; ela vai no `DW_PASSWORD` do passo 2. Copie `deploy/dw-papel-somente-leitura.sql` para o servidor do PEC
   (ou baixe em `https://raw.githubusercontent.com/KduBroseguinOfc/painel-filhos-de-minas/main/deploy/dw-papel-somente-leitura.sql`)
   e rode com o `psql` do próprio PEC:
   ```bash
   # Linux (banco embutido do PEC)
   /opt/e-SUS/database/postgresql-9.6.13-1-linux-x64/bin/psql -h localhost -p 5433 -U postgres -d esus \
       -v senha='<senha-nova>' -f dw-papel-somente-leitura.sql
   # Windows: o mesmo, com o psql.exe da pasta database\<versão>\bin da instalação do e-SUS
   ```
   Saída esperada: `CREATE ROLE`, `ALTER ROLE` (3) e `GRANT` (3). Rodar de novo só troca a senha.
3. **Libere o acesso da máquina do painel.** Na pasta `data` do PostgreSQL do PEC (Linux:
   `/opt/e-SUS/database/current/data/`; Windows: `database\<versão>\data`):
   - `postgresql.conf`: se estiver `listen_addresses = 'localhost'`, troque por
     `listen_addresses = 'localhost,<ip-do-servidor-do-pec>'`;
   - `pg_hba.conf`: acrescente no fim, com o mesmo método das outras linhas (no banco embutido do PEC, `md5`):
     ```
     host  esus  painelfm_ro   <ip-do-painel>/32  md5
     host  esus  esus_leitura  <ip-do-painel>/32  md5     # só no cenário 2: usuário que o extrator usa
     ```
   - reinicie o PostgreSQL (Linux: `systemctl restart e-SUS-AB-PostgreSQL`; Windows: o serviço do PostgreSQL do e-SUS
     em `services.msc`). Só o `pg_hba.conf` mudou? Basta `SELECT pg_reload_conf();`.
   - Windows com firewall ligado: libere a porta do banco para o IP do painel.
4. **Teste da máquina do painel:** `nc -zv <ip-do-servidor-do-pec> <porta>` tem de responder `succeeded`. O instalador
   testa o resto (login e SELECT em cada tabela) e para com a explicação se algo faltar.

No cenário 1 o extrator já tem o acesso dele: só o `painelfm_ro` é novo.

## Passo 2 — Na máquina do painel: baixar e preencher o arquivo de variáveis

```bash
sudo -i
apt-get install -y git
git clone https://github.com/KduBroseguinOfc/painel-filhos-de-minas.git /opt/painel-filhos-de-minas-src
cd /opt/painel-filhos-de-minas-src
cp deploy/env.exemplo /root/meu-municipio.env
chmod 600 /root/meu-municipio.env          # vai ter senhas
nano /root/meu-municipio.env
```

Cada variável está comentada no arquivo. O que preencher em cada caso:

| Variável | Cenário 1 | Cenário 2 | O que é |
|---|---|---|---|
| `MUNICIPIO`, `UF`, `PREFEITURA`, `ORGAO` | sim | sim | aparecem nas telas, no certificado e nos avisos |
| `NOME_DNS`, `IP_APP` | sim | sim | nome interno do painel e IP desta máquina |
| `DW_HOST`, `DW_PORT`, `DW_DB` | sim | sim | banco do PEC (passo 1.1; embutido: porta `5433`) |
| `DW_USER`, `DW_PASSWORD` | sim | sim | `painelfm_ro` e a senha do passo 1.2 |
| `SES_API_USER`, `SES_API_PASSWORD` | opcional | **sim** | conta da API do Filhos de Minas. No cenário 1, a mesma do extrator, para a conferência diária (vazia = conferência desligada) |
| `EXTRATOR_INSTALAR` | `0` | `1` | instala o extrator junto? |
| `EXTRATOR_DB` | se não for o padrão | — | onde o extrator de vocês grava o banco (ver abaixo). Pode ficar em `/root` ou `/home`: o instalador ajusta as permissões e o isolamento dos serviços |
| `EXTRATOR_PACOTE` | — | **sim** | caminho do `.tgz` baixado da SES-MG (ex.: `/root/extrator-pec-esus-1.0.0.tgz`) |
| `EXTRATOR_DW_USER`, `EXTRATOR_DW_PASSWORD` | — | **sim** | usuário de leitura do DW para o extrator: o `esus_leitura` do `credenciais.txt` |
| `EXTRATOR_RESP_NOME`, `_EMAIL`, `_TELEFONE`, `_CARGO` | — | **sim** | responsável no município (exigido pela SES-MG na configuração do extrator) |
| `EXTRATOR_CORRECOES` | — | `1` ou `0` | aplica as 4 correções (`extrator/README.md`) ou deixa o extrator oficial puro |
| `EXTRATOR_ROTINA` | — | `0` primeiro, depois `1` | `1` liga o envio de hora em hora à SES-MG; `0` instala e importa sem enviar |
| `GEO_CONTATO` | recomendado | recomendado | e-mail de contato exigido pela política do OpenStreetMap |
| `EMAIL_*`, `TELEGRAM_*`, `SSO_*`/`OIDC_*`, `URL_PUBLICA`, `LOGO` | opcional | opcional | alertas, login único, proxy externo, logotipo (ver "Depois de instalar") |

**Cenário 1, onde está o banco do extrator?** No `.extrator-pec-esus/data/extrator-local.db` dentro do *home* do usuário
que roda o extrator (padrão deste projeto: `/opt/extrator-esus/...`). Para achar: `find / -name extrator-local.db 2>/dev/null`.
Confira também a que horas a rotina de vocês roda: a coleta do painel é aos **50 minutos** de cada hora, pensada para uma
rotina que começa na hora cheia e dura até ~40 min. Se for diferente, ajuste depois com
`systemctl edit painel-filhosdeminas-coleta.timer`.

**Cenário 2, sobre os termos da SES-MG:** com `EXTRATOR_INSTALAR=1` o instalador grava `termsAccepted=true` na
configuração do extrator, como faria quem aceita na tela. Leia os termos de uso no site da SES-MG antes.

## Passo 3 — Rodar o instalador

```bash
cd /opt/painel-filhos-de-minas-src
./instalar.sh /root/meu-municipio.env
```

Leva de 5 a 15 minutos (a primeira importação do extrator é a parte demorada). Ele mostra cada etapa; se parar, diz a
linha e o motivo, e o log completo fica em `/var/log/painel-filhosdeminas-instalacao.log`. Corrigiu o arquivo? Rode de
novo com ele: o instalador continua de onde dá e não apaga nada.

**Depois que a instalação terminar, a configuração passa a ser o `/etc/painel-filhosdeminas/env`.** Para mudar algo, edite
esse arquivo e rode `./instalar.sh` **sem argumento** (com o arquivo do `/root`, ele substitui o `/etc` pelo do `/root` e
guarda uma cópia do anterior ao lado). O `/root/meu-municipio.env` pode ser apagado: `shred -u /root/meu-municipio.env`.

**Anote a senha do administrador** que aparece na etapa "administrador local" (ela só é mostrada uma vez). Perdeu?
`painel-filhosdeminas criar_admin --redefinir`.

O que ele faz, na ordem: pacotes do sistema → usuário `painelfm` → `/etc/painel-filhosdeminas/env` (gera a
`DJANGO_SECRET_KEY`) → aplicação em `/opt/painel-filhosdeminas/app` + venv → **testa o DW** (conexão e SELECT em cada
tabela) → banco do painel (SQLite WAL em `/var/lib/painel-filhosdeminas`), estáticos, administrador → certificado + nginx →
serviços e timers (painel, coleta `:50`, conferência SES-MG 05:30, geocodificação 02:10, resumo de alertas 08:00, robô do
Telegram se houver token) → extrator, no cenário 2 (Node por tarball com SHA conferido, `npm i -g` do pacote, correções,
configuração, primeira importação, rotina horária, limpezas) → no cenário 1, leitura do banco do extrator → primeira
coleta → resumo.

## Passo 4 — DNS, certificado e firewall

1. No DNS interno, crie o registro A `NOME_DNS → IP_APP`.
2. O certificado é autoassinado, de 100 anos, em `/etc/painel-filhosdeminas/tls/painel.crt`. Para o navegador não
   avisar, distribua esse arquivo como confiável nas estações (GPO do Active Directory, em "Autoridades de certificação
   raiz confiáveis", ou importando no navegador). É um certificado próprio, não uma CA.
3. Se o UFW estiver ligado nesta máquina (no Ubuntu ele vem desligado), libere o painel: `ufw allow 80,443/tcp`.

## Passo 5 — Conferir

1. Abra `https://<NOME_DNS>` e entre com `admin` e a senha anotada.
2. A **Visão geral** deve mostrar as gestantes. Vazia? Ver "Problemas comuns".
3. Em **Situação do sistema**: a última coleta e as rotinas do extrator. Logo depois da instalação é normal aparecer
   "a rotina do extrator não roda há mais de 2 horas" no cenário 2 com `EXTRATOR_ROTINA=0`, ou até a próxima hora cheia.
4. `systemctl list-timers 'painel-filhosdeminas*' 'filhos-de-minas*'` mostra os próximos horários.
5. Cenário 2: tudo certo com `EXTRATOR_ROTINA=0`? Troque para `1` no `/etc/painel-filhosdeminas/env` e rode
   `./instalar.sh` sem argumento. Na hora seguinte, o log
   `/opt/extrator-esus/logs/filhos_de_minas_hourly.log` deve terminar com `Envio concluído (...): X/Y`, com X maior que zero.
6. Crie os usuários em **Usuários → Novo usuário** (administrador ou visualização).

## Acesso de fora da rede interna (opcional)

É por conta do município. Aponte o proxy reverso para `https://<NOME_DNS>` (aceitando o certificado autoassinado no proxy),
repasse `X-Real-IP`, `X-Forwarded-For` e `X-Forwarded-Proto`, coloque a URL externa em `URL_PUBLICA` e o IP do proxy em
`PROXY_REVERSO_IP` (para a trilha de acesso registrar o IP do usuário, não o do proxy) no `/etc/painel-filhosdeminas/env`
e rode `./instalar.sh` de novo, sem argumento.

## Depois de instalar

| Quero… | Como |
|---|---|
| Criar usuários | Entrar como admin → **Usuários** → Novo. A senha é gerada e mostrada uma vez. |
| Trocar a senha do admin | `painel-filhosdeminas criar_admin --redefinir` |
| Mudar uma variável | Editar `/etc/painel-filhosdeminas/env` e `systemctl restart painel-filhosdeminas` (variável do nginx, do extrator ou do Telegram: `./instalar.sh` sem argumento) |
| Ligar o SSO do município | `SSO_ATIVO=1`, `OIDC_ISSUER`, `OIDC_CLIENT_ID/SECRET` (e grupos, se quiser) no env; `systemctl restart painel-filhosdeminas`. Ver a seção SSO. |
| Alertas por e-mail | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM` (SMTP do município), `systemctl restart painel-filhosdeminas`. Teste: `painel-filhosdeminas testar_email voce@municipio.gov.br` |
| Alertas por Telegram | Criar um bot no @BotFather, `TELEGRAM_BOT_TOKEN` e `TELEGRAM_BOT_NOME` no env e rodar `./instalar.sh` sem argumento (ele liga o serviço do robô). Cada usuário vincula o próprio Telegram pelo código em **Meus alertas → Telegram** |
| Logotipo/brasão | Copiar um PNG/SVG para `/var/lib/painel-filhosdeminas/logo.png` (`chown painelfm: ` e `chmod 640`) |
| Foto da UBS no mapa | `/var/lib/painel-filhosdeminas/fotos-ubs/<cnes>.jpg` (`chown painelfm: ` e `chmod 640`) |
| Pino da UBS no lugar certo | Copiar `deploy/ubs-coordenadas.exemplo.json` para `/etc/painel-filhosdeminas/ubs-coordenadas.json`, preencher e rodar `./instalar.sh` sem argumento (ou `painel-filhosdeminas fixar_ubs /etc/painel-filhosdeminas/ubs-coordenadas.json`) |
| Correções no extrator do cenário 1 | `extrator/aplicar-correcoes.sh` na máquina do extrator, fora do horário da rotina ([extrator/README.md](extrator/README.md)) |
| Sugerir CNS achado em outro sistema | Gerar o arquivo `;` (formato no `importar_cns.py`) e `painel-filhosdeminas importar_cns arquivo.txt`: só sugestão para a UBS conferir no CadSUS |
| Atualizar | `cd /opt/painel-filhos-de-minas-src && git pull && ./instalar.sh` (sem argumento: banco, usuários, configuração e certificado são mantidos) |
| Rodar um comando de manutenção | `painel-filhosdeminas <comando>` como root (lê as variáveis como os serviços; `painel-filhosdeminas help` lista os comandos). Não rode `manage.py` direto: sem as variáveis ele falha com `KeyError: 'DJANGO_SECRET_KEY'` |
| Ver se está tudo bem | Tela **Situação do sistema**, ou `curl -k https://<NOME_DNS>/saude` (200 = coleta recente; 503 = sem coleta há 3 h) |

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Instalador: `nao conectou ao DW ... Connection refused` ou tempo esgotado | PostgreSQL escutando só em `localhost`, porta errada ou firewall | Passo 1.3 (`listen_addresses`, porta 5433 no banco embutido, firewall do Windows) |
| `no pg_hba.conf entry for host` | Falta a linha do IP do painel | Passo 1.3 (`pg_hba.conf` + `SELECT pg_reload_conf();`) |
| `password authentication failed` | Senha diferente da do passo 1.2, ou método do `pg_hba` incompatível | Rodar o SQL de novo com a senha do env (ele troca a senha); usar o mesmo método das outras linhas |
| `sem SELECT nestas tabelas` | O SQL do passo 1.2 não rodou, ou rodou em outro banco | Rodar `dw-papel-somente-leitura.sql` no banco `esus` |
| Painel abre mas sem gestantes | Cenário 1: `EXTRATOR_DB` errado; cenário 2: extrator sem importar | `find / -name extrator-local.db`; `journalctl -u painel-filhosdeminas-coleta`; rodar o instalador de novo |
| Painel com dados, mas "os dados do painel têm mais de 2 horas" | A coleta de hora em hora falha (`journalctl -u painel-filhosdeminas-coleta`); com `unable to open database file`, o banco do extrator mudou de lugar | Ajustar `EXTRATOR_DB` no `/etc/painel-filhosdeminas/env` e rodar `./instalar.sh` sem argumento |
| Extrator: `missing_required_settings` | Alguma `EXTRATOR_*` ou `SES_API_*` vazia | Preencher e rodar o instalador de novo |
| Log da rotina: `Envio concluído: 0/N` todas as horas | Recusas da API (CNS, CPF, Bolsa Família) ou conta da API errada | Ver os motivos na tela **Gestantes**; conferir a conta com a SES-MG |
| Navegador: "conexão não é particular" | Certificado autoassinado ainda não distribuído | Passo 4.2 |
| Página não abre pelo nome, só pelo IP | Falta o registro no DNS interno | Passo 4.1 |

## Backup e remoção

Backup do painel: `/var/lib/painel-filhosdeminas/` (banco com usuários, histórico e alertas) e `/etc/painel-filhosdeminas/`
(env com as senhas e o certificado). Para copiar o banco com o painel no ar:
`sqlite3 /var/lib/painel-filhosdeminas/painel.db ".backup /root/painel-$(date +%F).db"`. O resto o instalador refaz.
No cenário 2 inclua também `/opt/extrator-esus/.extrator-pec-esus/` (configuração e banco do extrator).

Remover o painel: `systemctl disable --now 'painel-filhosdeminas*'`, apagar as units `painel-filhosdeminas*` de
`/etc/systemd/system/`, o site `painel-filhosdeminas` do nginx, `/opt/painel-filhosdeminas`, `/var/lib/painel-filhosdeminas`
e `/etc/painel-filhosdeminas`; no banco do PEC, `DROP OWNED BY painelfm_ro; DROP ROLE painelfm_ro;` e as linhas do
`pg_hba.conf`. O extrator (cenário 2) tem as units `filhos-de-minas-hourly`, `cleanup-filhos-log` e `limpa-logs-banco-filhos`.

## SSO (OpenID Connect) — o que o painel oferece

O painel é um *client* OIDC comum (Authorization Code + PKCE não é exigido; `RS256`). Do lado do provedor do município
(Authentik, Keycloak, Entra ID, etc.) cadastre uma aplicação com:

- redirect URI: `https://<URL_PUBLICA>/oidc/callback/`
- post-logout redirect URI: `https://<URL_PUBLICA>/`
- escopos `openid email profile`; claim de usuário (`preferred_username`) e, se quiser papéis pelo SSO, uma claim com os grupos (`groups`).

Do lado do painel (env): `SSO_ATIVO=1`, `OIDC_ISSUER` (o painel lê `/.well-known/openid-configuration`; sem ele,
informe os `OIDC_*_ENDPOINT`), `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_CLAIM_USUARIO`, `OIDC_CLAIM_GRUPOS`,
`SSO_GRUPOS_ADMIN` (grupos que entram como administrador), `SSO_GRUPOS_ACESSO` (vazio = todo usuário autenticado entra
como visualização), `SSO_NOME` (texto do botão). O login local continua existindo (`/entrar-local/`), restrito às
origens de `LOGIN_LOCAL_IPS` se você preencher. Sair encerra também a sessão no provedor (end-session com `id_token_hint`).

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| `instalar.sh` | instalador idempotente (ver acima) |
| `deploy/env.exemplo` | todas as variáveis, comentadas |
| `deploy/` | nginx, certificado, SQL do papel só leitura, units do systemd, coordenadas de exemplo, rotina/limpezas do extrator |
| `painel/` | aplicação Django (`fm/`: coleta, indicadores, telas, alertas, geocodificação; `painel/`: settings) |
| `extrator/` | `diff` com as 4 correções do Extrator PEC e-SUS 1.0.0 e o aplicador ([extrator/README.md](extrator/README.md)) |

## Situações e regras (resumo)

| Situação | De onde vem | Orientação na tela |
|---|---|---|
| aceita | extrator `queued=1` | nenhuma ação |
| sem CNS | API 500 `NotNull cns` | UBS completa o CNS no cadastro do cidadão (CadSUS) |
| fora do Bolsa Família | API 400 | regra do programa; conferir o CPF |
| sem CPF | API 422 | UBS cadastra o CPF |
| erro da API | outra resposta | temporário; a rotina tenta de novo |
| aguardando envio | sem resposta ainda | aguardar a próxima rotina |
| fora do recorte | DUM há mais de 1 ano (correção 3 do extrator) | não é enviada; corrigir a DUM no PEC se a gestação continua |

*Parto provável* (só apresentação): pendente com DUM há mais de 42 semanas; sai da lista de ação da UBS.
*Parto registrado*: CID O80–O84, Z37 ou Z39 depois da DUM.

## Segurança

HTTPS obrigatório; cookies `Secure`/`HttpOnly`/`SameSite`; CSP sem script inline; `X-Frame-Options: DENY`; CSRF em todo
POST; serviços com `ProtectSystem=strict`, `NoNewPrivileges`, usuário sem shell; DW em transação somente leitura com
`statement_timeout`; CPF mascarado por padrão (revelar é registrado); senhas geradas pelo painel, nunca digitadas pelo
administrador. Avisos de segurança: abra uma *issue* sem detalhes e peça contato.

## O que já foi testado

O instalador foi validado de ponta a ponta numa máquina Ubuntu Server 24.04.4 limpa, no **cenário 2**, contra um PEC com
o banco embutido (PostgreSQL 9.6, porta 5433): teste do DW, painel, certificado, timers, extrator 1.0.0 com as correções,
primeira importação e coleta, todas as telas, criação de usuários e geocodificação. O envio à SES-MG ficou desligado no
teste (`EXTRATOR_ROTINA=0`). O painel e as correções do extrator estão em produção em Ipatinga desde 2026.
Ainda **não** testados nesta versão: o cenário 1 (extrator já instalado), o SSO por OpenID Connect genérico, e os
alertas por e-mail e Telegram (o código veio da versão de Ipatinga, onde funcionam). Se você testar, conte numa *issue*.
