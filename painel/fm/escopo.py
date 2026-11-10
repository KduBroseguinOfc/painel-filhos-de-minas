"""Permissoes: todo usuario logado ve todas as unidades (sem recorte por UBS). Administrador = superusuario (criado na
tela Usuarios ou, com SSO, quem tem um dos grupos de SSO_GRUPOS_ADMIN)."""


def unidades_permitidas(user):
    """None = todas (mantido como funcao para as consultas continuarem iguais)."""
    return None


def filtra(qs, user, campo="unidade"):
    return qs


def e_admin(user):
    return bool(user.is_authenticated and user.is_superuser)
