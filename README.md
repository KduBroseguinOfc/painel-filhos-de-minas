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

## Dois cenários (o PEC e-SUS APS o município já tem nos dois)

| Cenário | O que o instalador faz | No `.env` |
|---|---|---|
| **1. Já tem o Extrator PEC e-SUS (CLI Linux) rodando** | Instala só o painel na mesma máquina do extrator, dá ao painel leitura (ACL) no banco e no log do extrator, e faz a primeira coleta. O extrator e a rotina dele ficam como estão. Quer as correções no extrator deles? `extrator/aplicar-correcoes.sh`, à parte. | `EXTRATOR_INSTALAR=0`; `EXTRATOR_DB` e `EXTRATOR_LOG` apontando para onde o extrator deles grava (padrão `/opt/extrator-esus/...`) |
| **2. Não tem o extrator** | Instala o painel **e** o extrator oficial (baixado do site da SES-MG pelo município), aplica as correções, configura (DW, conta da API, responsável), faz a primeira importação e liga a rotina de hora em hora. | `EXTRATOR_INSTALAR=1`, `EXTRATOR_PACOTE=/root/extrator-pec-esus-1.0.0.tgz`, `EXTRATOR_DW_*`, `SES_API_*`, `EXTRATOR_RESP_*` |

O extrator em versão Windows (com tela) em outra máquina **não** serve para o painel: ele lê o banco SQLite do extrator no
disco local. Nesse caso é o cenário 2 (o extrator CLI Linux passa a rodar junto com o painel, e o Windows é desligado para
não enviar em dobro).

Nos dois casos as variáveis vão num arquivo **antes** de rodar; o instalador para na primeira obrigatória vazia e diz qual.
Depois, mudou algo? Edita `/etc/painel-filhosdeminas/env` e `systemctl restart painel-filhosdeminas` (ou roda o instalador de novo).

## Instalar (Ubuntu Server 24.04, rede interna)

O instalador sobe tudo numa máquina limpa (2 vCPU, 4 GB, 40 GB bastam; o SQLite do extrator cresce com o tempo —
reserve 20 GB livres). Ele instala nginx, Python, o painel, os serviços e, se você quiser, o próprio Extrator PEC e-SUS,
e publica em `https://<NOME_DNS>` com certificado autoassinado. Pode ser rodado de novo para atualizar.

1. **No servidor do banco do PEC**, crie o papel só de leitura (gera uma senha forte e guarde-a):
   ```bash
   psql -h <host-do-pec> -p 5432 -U postgres -d esus -v senha='<senha>' -f deploy/dw-papel-somente-leitura.sql
   ```
   e libere o IP do painel no `pg_hba.conf` (`host esus painelfm_ro <ip-do-painel>/32 scram-sha-256`, `pg_ctl reload`).
   O extrator também precisa de um usuário de leitura no DW (pode ser outro papel já existente).
2. **Cenário 2:** baixe o Extrator PEC e-SUS (pacote CLI `.tgz`) em <https://atualizacoes-extrator-pec-esus.saude.mg.gov.br> e
   tenha a conta da API do Filhos de Minas do seu município (fornecida pela SES-MG).
3. **Na máquina do painel**, como root:
   ```bash
   git clone https://github.com/KduBroseguinOfc/painel-filhos-de-minas.git /opt/painel-filhos-de-minas-src
   cd /opt/painel-filhos-de-minas-src
   cp deploy/env.exemplo /root/meu-municipio.env && nano /root/meu-municipio.env    # preencha MUNICIPIO, UF, NOME_DNS, IP_APP, DW_*, SES_API_*, EXTRATOR_*
   ./instalar.sh /root/meu-municipio.env
   ```
   No fim ele mostra o usuário **admin** e a senha gerada (uma vez só) e o endereço do painel.
4. **DNS e certificado**: crie o registro A `NOME_DNS → IP_APP` no DNS interno e distribua
   `/etc/painel-filhosdeminas/tls/painel.crt` como confiável nas estações (GPO do AD ou perfil do navegador), para o
   navegador não avisar. É um certificado próprio, não uma CA.
5. **Acesso de fora da rede interna** (opcional) é por conta do município: aponte o proxy reverso para
   `https://<NOME_DNS>` (aceite o certificado autoassinado no proxy), repasse `X-Real-IP`/`X-Forwarded-For`/`X-Forwarded-Proto`
   e coloque a URL externa em `URL_PUBLICA`. Nada mais muda.

O que o instalador faz, na ordem: pacotes do sistema → usuário `painelfm` → `/etc/painel-filhosdeminas/env` (gera a
`DJANGO_SECRET_KEY`) → aplicação em `/opt/painel-filhosdeminas/app` + venv → **testa o DW** (conexão e SELECT em cada tabela) →
banco do painel (SQLite WAL em `/var/lib/painel-filhosdeminas`), estáticos, administrador → certificado + nginx →
serviços e timers (painel, coleta `:50`, conferência SES-MG 05:30, geocodificação 02:10, resumo de alertas 08:00, robô do
Telegram se houver token) → extrator (Node por tarball com SHA conferido, `npm i -g` do pacote, correções, configuração,
primeira importação, rotina horária, limpezas) → primeira coleta → resumo. Log: `/var/log/painel-filhosdeminas-instalacao.log`.

## Depois de instalar

| Quero… | Como |
|---|---|
| Criar usuários | Entrar como admin → **Usuários** → Novo. A senha é gerada e mostrada uma vez. |
| Trocar a senha do admin | `cd /opt/painel-filhosdeminas/app && sudo -E -u painelfm ../venv/bin/python manage.py criar_admin --redefinir` |
| Ligar o SSO do município | `SSO_ATIVO=1`, `OIDC_ISSUER`, `OIDC_CLIENT_ID/SECRET` (e grupos, se quiser) no env; `systemctl restart painel-filhosdeminas`. Ver abaixo. |
| Logotipo/brasão | Copiar um PNG/SVG para `/var/lib/painel-filhosdeminas/logo.png` (painelfm:painelfm 640) |
| Foto da UBS no mapa | `/var/lib/painel-filhosdeminas/fotos-ubs/<cnes>.jpg` (painelfm:painelfm 640) |
| Pino da UBS no lugar certo | Editar `deploy/ubs-coordenadas.exemplo.json`, salvar em `/etc/painel-filhosdeminas/ubs-coordenadas.json` e rodar `manage.py fixar_ubs` (o instalador aplica sozinho na próxima execução) |
| Alertas por e-mail | `EMAIL_*` no env (SMTP do município) |
| Alertas por Telegram | Criar um bot no @BotFather, `TELEGRAM_BOT_TOKEN` e `TELEGRAM_BOT_NOME` no env; cada usuário vincula pelo código na tela Meus alertas |
| Sugerir CNS achado em outro sistema | Gerar o arquivo `;` (formato no `importar_cns.py`) e `manage.py importar_cns arquivo.txt` — só sugestão para a UBS conferir no CadSUS |
| Atualizar | `git pull` na pasta do código e `./instalar.sh` de novo (banco, usuários e certificado são mantidos) |
| Ver se está tudo bem | Tela **Situação do sistema**, ou `curl -k https://<NOME_DNS>/saude` (200 = coleta recente) |

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
