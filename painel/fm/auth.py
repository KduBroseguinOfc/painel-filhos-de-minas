"""Login pelo SSO (OpenID Connect). O provedor do municipio decide quem entra; aqui conferimos DE NOVO as claims
(nunca confiar so no lado do cliente) e guardamos os grupos no perfil para definir o papel (administrador ou
visualizacao). Nome das claims e grupos: deploy/env.exemplo."""
from urllib.parse import urlencode

from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


def _grupos(claims):
    g = claims.get(settings.OIDC_CLAIM_GRUPOS) or []
    if isinstance(g, str):
        g = [x.strip() for x in g.split(",")]
    return [str(x) for x in g]


def pode_entrar(grupos):
    if not settings.SSO_GRUPOS_ACESSO and not settings.SSO_GRUPOS_ADMIN:
        return True
    return any(g in settings.SSO_GRUPOS_ACESSO or g in settings.SSO_GRUPOS_ADMIN for g in grupos)


class Backend(OIDCAuthenticationBackend):
    def verify_claims(self, claims):
        if not super().verify_claims(claims):
            return False
        return bool(claims.get(settings.OIDC_CLAIM_USUARIO)) and pode_entrar(_grupos(claims))

    def filter_users_by_claims(self, claims):
        login = claims.get(settings.OIDC_CLAIM_USUARIO)
        if not login:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(username__iexact=login)

    def _preencher(self, user, claims):
        user.username = claims.get(settings.OIDC_CLAIM_USUARIO, user.username)
        user.email = claims.get("email") or ""
        nome = (claims.get("name") or "").strip()
        user.first_name, _, user.last_name = nome.partition(" ")
        user.first_name, user.last_name = user.first_name[:150], user.last_name[:150]
        user.set_unusable_password()
        grupos = _grupos(claims)
        user.is_superuser = any(g in settings.SSO_GRUPOS_ADMIN for g in grupos)   # papel vem do SSO a cada login
        user.is_active = True
        user.save()
        from .models import Acesso, Perfil
        Perfil.objects.update_or_create(usuario=user, defaults={"grupos": grupos, "origem": "sso"})
        Acesso.objects.create(usuario=user, acao="login", detalhe=("sso " + ",".join(grupos))[:500])
        return user

    def create_user(self, claims):
        return self._preencher(self.UserModel(), claims)

    def update_user(self, user, claims):
        return self._preencher(user, claims)


def url_logout(request):
    """Logout unico: end-session do provedor com id_token_hint e volta ao painel. Provedor sem end-session (ou sessao
    sem id_token): so o logout local."""
    token = request.session.get("oidc_id_token")
    fim = settings.OIDC_OP_LOGOUT_ENDPOINT
    if not fim or not token:
        return "/"
    params = {"id_token_hint": token, "post_logout_redirect_uri": settings.URL_PUBLICA + "/"}
    return fim + "?" + urlencode(params)
