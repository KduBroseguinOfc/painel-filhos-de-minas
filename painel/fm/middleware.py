from urllib.parse import urlsplit

from django.conf import settings


def _origem_sso():
    u = getattr(settings, "OIDC_OP_AUTHORIZATION_ENDPOINT", "") if settings.SSO_ATIVO else ""
    if not u:
        return ""
    p = urlsplit(u)
    return f" {p.scheme}://{p.netloc}"


class CabecalhosSeguranca:
    """CSP sem script inline (todo JS e CSS vem de /static), mais cabecalhos de endurecimento."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = ("default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org; style-src 'self'; script-src 'self'; font-src 'self'; "
                    f"connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'{_origem_sso()}")

    def __call__(self, request):
        r = self.get_response(request)
        r.headers.setdefault("Content-Security-Policy", self.csp)
        r.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        r.headers.setdefault("Cache-Control", "no-store")
        return r


class SemRefreshParaLoginLocal:
    """Sessao aberta pelo login local nao passa pelo SessionRefresh do OIDC."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get("login_local"):
            request.session["oidc_id_token_expiration"] = 4102444800   # ano 2100: o SessionRefresh nao dispara
        return self.get_response(request)
