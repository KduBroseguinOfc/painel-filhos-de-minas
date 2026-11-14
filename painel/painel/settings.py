"""Painel Filhos de Minas — configuracao. Tudo que muda de um municipio para outro vem do ambiente
(arquivo /etc/painel-filhosdeminas/env, 640 root:painelfm, modelo em deploy/env.exemplo)."""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
E = os.environ


def _lista(nome, padrao=""):
    return [x.strip() for x in E.get(nome, padrao).split(",") if x.strip()]


SECRET_KEY = E["DJANGO_SECRET_KEY"]
DEBUG = E.get("DJANGO_DEBUG") == "1"
NOME_DNS = E.get("NOME_DNS", "painel-filhosdeminas.local")       # nome interno pelo qual o painel e acessado
URL_PUBLICA = E.get("URL_PUBLICA", f"https://{NOME_DNS}")        # se houver proxy reverso na frente, a URL que o usuario digita
ALLOWED_HOSTS = [NOME_DNS, URL_PUBLICA.split("//")[1].split("/")[0], "127.0.0.1", "localhost"] + _lista("HOSTS_EXTRAS") + ([E["IP_APP"]] if E.get("IP_APP") else [])
CSRF_TRUSTED_ORIGINS = sorted({URL_PUBLICA, f"https://{NOME_DNS}"})

# Identidade do municipio (aparece nas telas, nos e-mails e no robo do Telegram)
MUNICIPIO = E.get("MUNICIPIO", "Municipio")
UF = E.get("UF", "MG")
ORGAO = E.get("ORGAO", "Secretaria Municipal de Saude")
PREFEITURA = E.get("PREFEITURA", f"Prefeitura Municipal de {MUNICIPIO}")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "mozilla_django_oidc",
    "fm",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "fm.middleware.CabecalhosSeguranca",
]
SSO_ATIVO = E.get("SSO_ATIVO", "0") == "1"
if SSO_ATIVO:
    MIDDLEWARE.append("fm.middleware.SemRefreshParaLoginLocal")
    MIDDLEWARE.append("mozilla_django_oidc.middleware.SessionRefresh")  # revalida a sessao no SSO a cada 15 min
ROOT_URLCONF = "painel.urls"
WSGI_APPLICATION = "painel.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "fm.context.global_ctx",
    ]},
}]

# Banco local do painel (usuarios, sessoes, fotos das gestantes, historico, alertas, trilha de acesso).
# SQLite de proposito: VM pequena que ja hospeda o extrator; nenhum servico novo.
DB_PAINEL = E.get("DB_PAINEL", "/var/lib/painel-filhosdeminas/painel.db")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": DB_PAINEL,
    "OPTIONS": {"timeout": 30},   # journal_mode=WAL e persistente no arquivo (definido pelo instalador)
}}

# Fontes SOMENTE LEITURA: banco local do extrator (SQLite) e DW do PEC e-SUS (PostgreSQL)
EXTRATOR_DB = E.get("EXTRATOR_DB", "/opt/extrator-esus/.extrator-pec-esus/data/extrator-local.db")
EXTRATOR_LOG = E.get("EXTRATOR_LOG", "/opt/extrator-esus/logs/filhos_de_minas_hourly.log")
DW = {
    "host": E.get("DW_HOST", "127.0.0.1"), "port": int(E.get("DW_PORT", "5432")),
    "dbname": E.get("DW_DB", "esus"), "user": E.get("DW_USER", ""), "password": E.get("DW_PASSWORD", ""),
    "options": f"-c default_transaction_read_only=on -c statement_timeout=120000 -c TimeZone={E.get('FUSO', 'America/Sao_Paulo')}",
    "application_name": "painel-filhosdeminas",
}

# --- Login -------------------------------------------------------------------------------------------------------
# Padrao: usuarios locais (tela Usuarios, so administradores). Dois papeis: administrador (cria usuarios, ve a trilha
# de acesso) e visualizacao. Todo usuario logado ve todas as unidades.
# Opcional: SSO por OpenID Connect (Authentik, Keycloak, Entra ID, ...). O SSO do municipio e configurado por eles;
# deste lado entram as URLs do provedor e o client (deploy/env.exemplo). Quem o provedor autenticar entra como
# visualizacao, salvo os grupos listados em SSO_GRUPOS_ADMIN (administrador) e, se SSO_GRUPOS_ACESSO estiver
# preenchido, so quem tiver um desses grupos entra.
OIDC_ISSUER = E.get("OIDC_ISSUER", "").rstrip("/")             # ex.: https://sso.exemplo.gov.br/application/o/filhos-de-minas/
OIDC_RP_CLIENT_ID = E.get("OIDC_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = E.get("OIDC_CLIENT_SECRET", "")
OIDC_RP_SIGN_ALGO = E.get("OIDC_SIGN_ALGO", "RS256")
OIDC_RP_SCOPES = E.get("OIDC_SCOPES", "openid email profile")
OIDC_CLAIM_USUARIO = E.get("OIDC_CLAIM_USUARIO", "preferred_username")
OIDC_CLAIM_GRUPOS = E.get("OIDC_CLAIM_GRUPOS", "groups")
SSO_GRUPOS_ACESSO = _lista("SSO_GRUPOS_ACESSO")
SSO_GRUPOS_ADMIN = _lista("SSO_GRUPOS_ADMIN")
SSO_NOME = E.get("SSO_NOME", "login único")                      # como o botao e as mensagens chamam o SSO


def _descoberta():
    """Endpoints do provedor: explicitos no ambiente ou pelo documento .well-known do emissor (guardado em cache ao
    lado do banco do painel, para nao depender do SSO a cada reinicio)."""
    chaves = {"authorization_endpoint": "OIDC_AUTHORIZATION_ENDPOINT", "token_endpoint": "OIDC_TOKEN_ENDPOINT",
              "userinfo_endpoint": "OIDC_USERINFO_ENDPOINT", "jwks_uri": "OIDC_JWKS_ENDPOINT", "end_session_endpoint": "OIDC_END_SESSION_ENDPOINT"}
    d = {k: E.get(v, "") for k, v in chaves.items()}
    if all(d[k] for k in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri")) or not OIDC_ISSUER:
        return d
    cache = Path(DB_PAINEL).with_name("oidc-descoberta.json")
    doc = {}
    try:
        doc = json.loads(cache.read_text())
        if doc.get("issuer", "").rstrip("/") != OIDC_ISSUER:
            doc = {}
    except (OSError, ValueError):
        doc = {}
    if not doc:
        import requests
        try:
            doc = requests.get(f"{OIDC_ISSUER}/.well-known/openid-configuration", timeout=10).json()
            cache.write_text(json.dumps(doc))
        except Exception:  # noqa: BLE001 — sem SSO alcancavel, o painel sobe mesmo assim (login local continua)
            doc = {}
    return {k: d[k] or doc.get(k, "") for k in chaves}


if SSO_ATIVO:
    _ep = _descoberta()
    OIDC_OP_AUTHORIZATION_ENDPOINT = _ep["authorization_endpoint"]
    OIDC_OP_TOKEN_ENDPOINT = _ep["token_endpoint"]
    OIDC_OP_USER_ENDPOINT = _ep["userinfo_endpoint"]
    OIDC_OP_JWKS_ENDPOINT = _ep["jwks_uri"]
    OIDC_OP_LOGOUT_ENDPOINT = _ep["end_session_endpoint"]
    OIDC_OP_LOGOUT_URL_METHOD = "fm.auth.url_logout"
    OIDC_STORE_ID_TOKEN = True
    OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 15 * 60
    OIDC_USE_NONCE = True
    OIDC_EXEMPT_URLS = ["sair", "sem_acesso", "saude", "entrar_local", "entrar"]   # o SessionRefresh nao forca re-login nestas rotas
    AUTHENTICATION_BACKENDS = ["fm.auth.Backend", "django.contrib.auth.backends.ModelBackend"]
    LOGIN_URL = "/entrar/"
else:
    AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
    LOGIN_URL = "/entrar-local/"
# Com SSO ativo, o login local continua aceito (usuarios criados na tela Usuarios) so a partir destas origens.
# Vazio = de qualquer origem. Ex.: 127.0.0.1,10.0.0.0/8
LOGIN_LOCAL_IPS = _lista("LOGIN_LOCAL_IPS")
LOGIN_REDIRECT_URL = "/"
LOGIN_REDIRECT_URL_FAILURE = "/sem-acesso/"
LOGOUT_REDIRECT_URL = "/"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 365 * 24 * 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"   # o OSM exige a origem no Referer dos tiles (403 sem ela)

LANGUAGE_CODE = "pt-br"
TIME_ZONE = E.get("FUSO", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FOTOS_UBS = E.get("FOTOS_UBS", "/var/lib/painel-filhosdeminas/fotos-ubs")   # <cnes>.jpg, servida por /ubs/foto/<cnes>/ (so logado)
LOGO = E.get("LOGO", "/var/lib/painel-filhosdeminas/logo.png")               # brasao/logotipo do municipio (opcional; sem ele, o padrao)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
# Geocodificacao (OpenStreetMap/Nominatim): identificacao obrigatoria pela politica de uso; caixa opcional
# (lat_sul,lat_norte,lon_oeste,lon_leste) — vazia = descoberta pelo nome do municipio e guardada em cache
GEO_CONTATO = E.get("GEO_CONTATO", "")
GEO_CAIXA = E.get("GEO_CAIXA", "")
# Alertas: remetente de e-mail e robo do Telegram (opcionais)
EMAIL_HOST = E.get("EMAIL_HOST", "")
EMAIL_PORT = int(E.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = E.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_HOST_USER = E.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = E.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = E.get("EMAIL_FROM", EMAIL_HOST_USER)
EMAIL_SUBJECT_PREFIX = "[Filhos de Minas] "
EMAIL_DOMINIOS = _lista("EMAIL_DOMINIOS")      # dominios aceitos nos alertas por e-mail (vazio = qualquer)
TELEGRAM_BOT_TOKEN = E.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_NOME = E.get("TELEGRAM_BOT_NOME", "")
# API do Filhos de Minas (SES-MG), so leitura na conferencia diaria: mesma conta do extrator
SES_API_URL = E.get("SES_API_URL", "https://filhosdeminas.saude.mg.gov.br/api")
SES_API_USER = E.get("SES_API_USER", "")
SES_API_PASSWORD = E.get("SES_API_PASSWORD", "")
CPF_COMPLETO_PADRAO = E.get("CPF_COMPLETO_PADRAO", "0") == "1"   # 0 = mascarado, revelar sob clique (registrado)
