"""Avaliador dos alertas personalizados. Roda depois de cada coleta ('hora') e as 08:00 ('dia').
Regra LGPD: as mensagens NAO levam nome nem documento de gestante; levam contagens e o link da lista filtrada no
painel (que exige login). Cada alerta respeita o escopo do dono (unidades permitidas no ultimo login).

Formato unico das mensagens (e-mail e Telegram): cabecalho, blocos com titulo + linhas curtas + link, rodape."""
import datetime as dt
import html
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .escopo import unidades_permitidas
from .models import SITUACOES, Alerta, Coleta, Evento, Gestante, Rotina

log = logging.getLogger(__name__)
SIT = dict(SITUACOES)
PENDENTES = ["sem_cns", "fora_bolsa", "sem_cpf", "erro_api", "pendente"]
EVENTO_NOME = {
    "nova_pendente": "gestante nova entrar pendente",
    "resolvida": "gestante pendente for aceita pela SES-MG",
    "envio_zero": "a rotina terminar com 0 aceites havendo pendentes (1 aviso por dia)",
    "rotina_falhou": "a rotina do extrator parar ou a coleta falhar (1 aviso a cada 6 h)",
    "lote_pec": "chegar lote novo do PEC",
}


class Bloco:
    """Um assunto da mensagem: titulo, linhas curtas e um link."""
    def __init__(self, titulo, linhas, link, rotulo="Ver no painel"):
        self.titulo, self.linhas, self.link, self.rotulo = titulo, list(linhas), link, rotulo


def _base(alerta):
    qs = Gestante.objects.filter(ativa=True)
    perm = unidades_permitidas(alerta.usuario)
    if perm is not None:
        qs = qs.filter(unidade__in=perm)
    unidades = list(alerta.unidades.all())
    if unidades:
        qs = qs.filter(unidade__in=unidades)
    if alerta.situacoes:
        qs = qs.filter(situacao__in=alerta.situacoes)
    return qs, unidades


def _link(alerta, **extra):
    p = {}
    unidades = list(alerta.unidades.all())
    if len(unidades) == 1:
        p["unidade"] = unidades[0].id
    if len(alerta.situacoes) == 1:
        p["situacao"] = alerta.situacoes[0]
    elif not alerta.situacoes:
        p["situacao"] = "pendentes"
    p.update(extra)
    return f"{settings.URL_PUBLICA}/gestantes/?{urlencode(p)}"


def _recorte(alerta):
    unidades = ", ".join(u.nome for u in alerta.unidades.all()) or "todas as unidades que você pode ver"
    situacoes = ", ".join(SIT.get(s, s) for s in alerta.situacoes) or "todas"
    return unidades, situacoes


def avaliar(alerta, modo, agora):
    """Devolve lista de Bloco, ou [] se nada a avisar."""
    desde = alerta.ultimo_envio or (agora - dt.timedelta(hours=1 if modo == "hora" else 24))
    qs, _ = _base(alerta)
    blocos = []
    est = dict(alerta.estado or {})
    ev = set(alerta.eventos or [])
    if modo == "dia":
        c = {s: qs.filter(situacao=s).count() for s, _ in SITUACOES}
        pend = sum(c[s] for s in PENDENTES)
        blocos.append(Bloco("Resumo do dia", [
            f"Gestantes no seu recorte: {qs.count()}",
            f"Aceitas pela SES-MG: {c['aceita']} (+{qs.filter(aceita_em__gte=agora - dt.timedelta(hours=24)).count()} nas últimas 24 h)",
            f"Pendentes: {pend}",
            f"  • sem CNS: {c['sem_cns']}",
            f"  • fora do Bolsa Família: {c['fora_bolsa']}",
            f"  • sem CPF: {c['sem_cpf']}",
            f"  • fora do recorte (DUM há mais de 1 ano, não enviadas): {c['fora_recorte']}",
            f"  • erro da API / aguardando: {c['erro_api'] + c['pendente']}",
        ], _link(alerta)))
    if "nova_pendente" in ev:
        n = qs.filter(primeira_vista__gte=desde).exclude(situacao__in=("aceita", "fora_recorte")).count()
        if n:
            blocos.append(Bloco("Gestantes novas pendentes", [f"{n} gestante(s) entraram no painel desde {timezone.localtime(desde):%d/%m %H:%M} e estão pendentes.",
                                                              "A UBS precisa corrigir o cadastro (CNS ou CPF) para a rotina reenviar."], _link(alerta, recorte="novas")))
    if "resolvida" in ev:
        n = Evento.objects.filter(gestante__in=qs, para="aceita", quando__gte=desde).count()
        if n:
            blocos.append(Bloco("Gestantes aceitas", [f"{n} gestante(s) do seu recorte foram aceitas pela SES-MG desde {timezone.localtime(desde):%d/%m %H:%M}."],
                                _link(alerta, situacao="aceita", o="desde")))
    if "envio_zero" in ev and modo == "hora":
        ult = Rotina.objects.filter(inicio__gte=agora - dt.timedelta(hours=24))
        pend = Gestante.objects.filter(ativa=True, situacao__in=PENDENTES).exists()
        if ult.exists() and not ult.filter(enviados__gt=0).exists() and pend and (agora - dt.datetime.fromisoformat(est.get("zero", "2000-01-01T00:00:00+00:00"))) > dt.timedelta(hours=24):
            blocos.append(Bloco("Nenhum aceite em 24 h", ["Todas as rotinas das últimas 24 h terminaram com 0 aceites, e há gestantes pendentes.",
                                                          "Normal se não houve cadastro corrigido nem lote novo do PEC.", "Se persistir por vários dias, acionar a TI."],
                                f"{settings.URL_PUBLICA}/situacao/", "Ver situação do sistema"))
            est["zero"] = agora.isoformat()
    if "rotina_falhou" in ev and modo == "hora":
        r = Rotina.objects.first()
        c = Coleta.objects.first()
        parada = r is None or (agora - r.inicio) > dt.timedelta(hours=2) or (c is not None and not c.ok)
        if parada and (agora - dt.datetime.fromisoformat(est.get("falha", "2000-01-01T00:00:00+00:00"))) > dt.timedelta(hours=6):
            blocos.append(Bloco("Rotina do extrator parada ou coleta com falha", ["A rotina horária não rodou nas últimas 2 h, ou a coleta do painel falhou.",
                                                                                 "Os dados do painel podem estar desatualizados até a TI verificar."],
                                f"{settings.URL_PUBLICA}/situacao/", "Ver situação do sistema"))
            est["falha"] = agora.isoformat()
    if "lote_pec" in ev:
        c = Coleta.objects.filter(ok=True).first()
        lote = c.ultimo_lote_pec.isoformat() if c and c.ultimo_lote_pec else ""
        if est.get("lote") and lote and lote != est["lote"]:
            blocos.append(Bloco("Lote novo do PEC", [f"O e-SUS recebeu atendimentos novos (atendimento mais recente: {timezone.localtime(c.ultimo_lote_pec):%d/%m/%Y}).",
                                                     "As gestantes novas aparecem no painel depois da próxima rotina (até 1 h)."], _link(alerta, recorte="novas")))
        est["lote"] = lote
    alerta.estado = est
    return blocos


def _texto_telegram(alerta, cabecalho, blocos, rodape):
    e = html.escape
    partes = [f"<b>Painel Filhos de Minas</b>\n{e(cabecalho)}"]
    for b in blocos:
        partes.append(f"<b>{e(b.titulo)}</b>\n" + "\n".join(e(l) for l in b.linhas) + f"\n<a href=\"{b.link}\">{e(b.rotulo)}</a>")
    partes.append(f"<i>{e(rodape)}</i>")
    return "\n\n".join(partes)[:3900]


def despachar(alerta, cabecalho, blocos, rodape, assunto, agora):
    """Envia pelos canais marcados; devolve os que receberam."""
    canais = []
    if alerta.por_telegram:
        v = getattr(alerta.usuario, "telegram", None)
        if v and v.chat_id:
            from . import telegram
            telegram.enviar(v.chat_id, _texto_telegram(alerta, cabecalho, blocos, rodape))
            canais.append("Telegram")
    if alerta.por_email:
        destino = alerta.destino or alerta.usuario.email
        if destino:
            ctx = {"alerta": alerta, "cabecalho": cabecalho, "blocos": blocos, "rodape": rodape, "agora": timezone.localtime(agora), "url": settings.URL_PUBLICA}
            m = EmailMultiAlternatives(subject=f"{settings.EMAIL_SUBJECT_PREFIX}{assunto}"[:150], body=render_to_string("fm/email_alerta.txt", ctx),
                                       to=[destino], headers={"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"})
            m.attach_alternative(render_to_string("fm/email_alerta.html", ctx), "text/html")
            m.send()
            canais.append("e-mail")
    return canais


def enviar(alerta, blocos, agora):
    cab = f"Alerta \"{alerta.nome}\" · {timezone.localtime(agora):%d/%m/%Y %H:%M}"
    rod = "Mensagem automática, sem dados de gestantes. Para alterar ou desligar este alerta: Meus alertas, no painel."
    return bool(despachar(alerta, cab, blocos, rod, f"{alerta.nome}: " + "; ".join(b.titulo for b in blocos), agora))


def confirmar(alerta, novo=True):
    """Confirmacao logo apos salvar: resume o que foi cadastrado, no mesmo formato dos avisos."""
    agora = timezone.now()
    unidades, situacoes = _recorte(alerta)
    quando = "na hora, depois de cada coleta (de hora em hora)" if alerta.frequencia == "hora" else "resumo diário às 08:00"
    canais = " e ".join(c for c, ok in (("e-mail", alerta.por_email), ("Telegram", alerta.por_telegram)) if ok)
    blocos = [
        Bloco("O que você vai acompanhar", [f"Unidades: {unidades}", f"Situações: {situacoes}"], _link(alerta), "Ver essas gestantes no painel"),
        Bloco("Quando avisar", [f"• {EVENTO_NOME.get(e, e)}" for e in alerta.eventos] + [f"Frequência: {quando}", f"Canais: {canais}"],
              f"{settings.URL_PUBLICA}/alertas/", "Meus alertas"),
    ]
    verbo = "cadastrado" if novo else "alterado"
    return despachar(alerta, f"Alerta \"{alerta.nome}\" {verbo} com sucesso. Se esta mensagem chegou, os avisos chegarão por aqui.",
                     blocos, "Mensagem automática de confirmação.", f"alerta \"{alerta.nome}\" {verbo}", agora)


def rodar(modo):
    agora = timezone.now()
    enviados = 0
    for a in Alerta.objects.filter(ativo=True).select_related("usuario"):
        if (a.frequencia == "dia") != (modo == "dia"):
            continue
        try:
            blocos = avaliar(a, modo, agora)
            if blocos and enviar(a, blocos, agora):
                a.ultimo_envio = agora
                enviados += 1
            a.save(update_fields=["estado", "ultimo_envio"])
        except Exception:  # noqa: BLE001
            log.exception("alerta %s falhou", a.id)
    return enviados
