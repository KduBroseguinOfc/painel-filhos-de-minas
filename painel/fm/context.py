import datetime as dt

from django.conf import settings
from django.utils import timezone


def estado_sistema():
    """ok | alerta | erro — para o favicon e o cabecalho. Consulta leve (2 linhas), em toda pagina."""
    from .models import Coleta, Rotina
    agora = timezone.now()
    rotina = Rotina.objects.first()
    coleta = Coleta.objects.first()
    if rotina is None or (agora - rotina.inicio) > dt.timedelta(hours=2) or (coleta is not None and not coleta.ok):
        return "erro"
    if coleta is None or (coleta.fim and (agora - coleta.fim) > dt.timedelta(hours=2)):
        return "alerta"
    return "ok"


def global_ctx(request):
    try:
        estado = estado_sistema()
    except Exception:  # noqa: BLE001 (banco ainda sem tabelas, por exemplo)
        estado = "alerta"
    return {"SSO_ATIVO": settings.SSO_ATIVO, "SSO_NOME": settings.SSO_NOME, "APP_NOME": "Filhos de Minas",
            "MUNICIPIO": settings.MUNICIPIO, "UF": settings.UF, "ORGAO": settings.ORGAO, "PREFEITURA": settings.PREFEITURA,
            "CPF_COMPLETO_PADRAO": settings.CPF_COMPLETO_PADRAO, "ESTADO_SISTEMA": estado,
            "E_ADMIN": bool(request.user.is_authenticated and request.user.is_superuser)}
