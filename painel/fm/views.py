"""Telas do painel. Toda tela exige login; o escopo por UBS e aplicado no servidor em todas as consultas
(nunca confiar em parametro vindo do navegador). Acessos a dado nominal ficam na trilha (Acesso)."""
import csv
import datetime as dt
import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .escopo import e_admin, filtra, unidades_permitidas
from .forms import AlertaForm
from . import indicadores as ind
from .models import SITUACOES, Acesso, Alerta, Coleta, ConferenciaSES, Equipe, Evento, Gestante, ResumoDiario, Rotina, SugestaoCNS, Unidade, VinculoTelegram, chave_nome_unidade

SIT = dict(SITUACOES)
PENDENTES = ["sem_cns", "fora_bolsa", "sem_cpf", "erro_api", "pendente"]


def _ip(request):
    return (request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "")[:45] or None


def _cadeia_ip(request):
    """IP visto pelo proxy + cadeia X-Forwarded-For (o IP local da estacao nao chega ao servidor: os navegadores bloqueiam)."""
    return f"ip={_ip(request)} xff={request.META.get('HTTP_X_FORWARDED_FOR', '')[:120]} ua={request.META.get('HTTP_USER_AGENT', '')[:120]}"


def _trilha(request, acao, detalhe=""):
    Acesso.objects.create(usuario=request.user if request.user.is_authenticated else None, acao=acao, detalhe=detalhe[:500], ip=_ip(request))


def _base(request):
    """Gestantes ativas dentro do escopo do usuario."""
    return filtra(Gestante.objects.filter(ativa=True).select_related("unidade", "equipe"), request.user)


def _contagem(qs):
    c = {s: 0 for s, _ in SITUACOES}
    for r in qs.values("situacao").annotate(n=Count("id")):
        c[r["situacao"]] = r["n"]
    c["total"] = sum(c[s] for s, _ in SITUACOES)
    c["pendentes"] = sum(c[s] for s in PENDENTES)
    c["no_recorte"] = c["total"] - c["fora_recorte"]
    # parto provavel: pendente com DUM ha mais de 42 semanas (ate 1 ano = ainda no recorte e ainda enviada); so apresentacao
    c["parto_provavel"] = qs.filter(situacao__in=PENDENTES, dum__lte=timezone.localdate() - dt.timedelta(days=294)).count()
    c["pendentes_curso"] = c["pendentes"] - c["parto_provavel"]
    return c


def _proxima_importacao(ultimo_lote):
    """Lote mensal chega 6-10 dias depois de fechar o mes (padrao observado em 2026)."""
    hoje = timezone.localdate()
    ref = (ultimo_lote.date() if ultimo_lote else hoje)
    mes = (ref.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    if ref.day >= 6 and ref.month == hoje.month:          # lote do mes anterior ja chegou neste mes
        mes = (hoje.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return mes.replace(day=6), mes.replace(day=10)


@login_required
def visao_geral(request):
    qs = _base(request)
    c = _contagem(qs)
    rotina = Rotina.objects.first()
    coleta = Coleta.objects.filter(ok=True).first()
    coleta_qualquer = Coleta.objects.first()
    agora = timezone.now()
    alertas = []
    if rotina is None or (agora - rotina.inicio) > dt.timedelta(hours=2):
        alertas.append(("vermelho", "A rotina do extrator não roda há mais de 2 horas."))
    elif rotina.total and rotina.enviados == 0 and c["pendentes"]:
        ult = Rotina.objects.filter(inicio__gte=agora - dt.timedelta(hours=24))
        if ult.exists() and not ult.filter(enviados__gt=0).exists():
            alertas.append(("amarelo", "Nenhum aceite nas últimas 24 h, com gestantes pendentes. Normal se não houve cadastro corrigido nem lote novo; se persistir dias, verificar a API."))
    if coleta_qualquer and not coleta_qualquer.ok:
        alertas.append(("vermelho", f"A última coleta do painel falhou: {coleta_qualquer.mensagem[:120]}"))
    if coleta and (agora - coleta.fim) > dt.timedelta(hours=2):
        alertas.append(("amarelo", "Os dados do painel têm mais de 2 horas."))
    semana = agora - dt.timedelta(days=7)
    ini, fim = _proxima_importacao(coleta.ultimo_lote_pec if coleta else None)
    resumo = list(ResumoDiario.objects.filter(data__gte=timezone.localdate() - dt.timedelta(days=90)))
    rotinas = list(Rotina.objects.filter(inicio__gte=agora - dt.timedelta(hours=48)).order_by("inicio"))
    ubs_top = (qs.filter(situacao__in=PENDENTES).values("unidade__nome").annotate(n=Count("id")).order_by("-n")[:8])
    graficos = {
        "dias": [r.data.strftime("%d/%m") for r in resumo],
        "aceitas": [r.aceitas for r in resumo], "sem_cns": [r.sem_cns for r in resumo],
        "fora_bolsa": [r.fora_bolsa for r in resumo], "sem_cpf": [r.sem_cpf for r in resumo],
        "aceitas_dia": [r.aceitas_no_dia for r in resumo],
        "rotinas_h": [timezone.localtime(r.inicio).strftime("%d/%m %Hh") for r in rotinas],
        "rotinas_env": [r.enviados for r in rotinas],
        "ubs_nomes": [u["unidade__nome"] or "(sem UBS)" for u in ubs_top], "ubs_pend": [u["n"] for u in ubs_top],
        "rosca": [c["sem_cns"], c["fora_bolsa"], c["sem_cpf"], c["erro_api"] + c["pendente"]],
    }
    return render(request, "fm/visao.html", {
        "c": c, "rotina": rotina, "coleta": coleta, "alertas": alertas,
        "novas": qs.filter(primeira_vista__gte=semana).exclude(situacao__in=("aceita", "fora_recorte")).count(),
        "aceitas_semana": qs.filter(aceita_em__gte=semana).count(),
        "perto_parto": qs.exclude(situacao__in=("aceita", "fora_recorte")).filter(dum__lte=timezone.localdate() - dt.timedelta(days=230), dum__gte=timezone.localdate() - dt.timedelta(days=294)).count(),
        "imp_ini": ini, "imp_fim": fim, "graficos": json.dumps(graficos),
    })


@login_required
def ubs(request):
    qs = _base(request)
    linhas = {}
    for r in qs.values("unidade_id", "unidade__nome", "situacao").annotate(n=Count("id")):
        l = linhas.setdefault(r["unidade_id"], {"id": r["unidade_id"], "nome": r["unidade__nome"] or "(sem UBS)", **{s: 0 for s, _ in SITUACOES}})
        l[r["situacao"]] = r["n"]
    sem_end = {r["unidade_id"]: r["n"] for r in qs.filter(cep="", logradouro="", bairro_end="").values("unidade_id").annotate(n=Count("id"))}
    pp = {r["unidade_id"]: r["n"] for r in qs.filter(situacao__in=PENDENTES, dum__lt=timezone.localdate() - dt.timedelta(days=294)).values("unidade_id").annotate(n=Count("id"))}
    for l in linhas.values():
        l["total"] = sum(l[s] for s, _ in SITUACOES)
        l["pendentes"] = sum(l[s] for s in PENDENTES)
        l["parto_provavel"] = pp.get(l["id"], 0)
        l["pendentes_curso"] = l["pendentes"] - l["parto_provavel"]
        l["pct"] = round(100 * l["aceita"] / l["total"]) if l["total"] else 0
        l["sem_end"] = sem_end.get(l["id"], 0)
    ordem = request.GET.get("o", "pendentes")
    if ordem not in ("pendentes", "pendentes_curso", "total", "aceita", "sem_cns", "fora_bolsa", "sem_cpf", "fora_recorte", "pct", "nome"):
        ordem = "pendentes"
    if ordem == "nome":
        lista = sorted(linhas.values(), key=lambda l: chave_nome_unidade(l["nome"]))
    else:
        lista = sorted(linhas.values(), key=lambda l: (-l[ordem], chave_nome_unidade(l["nome"])))
    return render(request, "fm/ubs.html", {"linhas": lista, "ordem": ordem, "tot": _contagem(qs)})


@login_required
def ubs_detalhe(request, pk):
    perm = unidades_permitidas(request.user)
    u = get_object_or_404(Unidade if perm is None else perm, pk=pk)
    qs = _base(request).filter(unidade=u)
    equipes = {}
    for r in qs.values("equipe_id", "equipe__nome", "situacao").annotate(n=Count("id")):
        l = equipes.setdefault(r["equipe_id"], {"id": r["equipe_id"], "nome": r["equipe__nome"] or "(sem equipe)", **{s: 0 for s, _ in SITUACOES}})
        l[r["situacao"]] = r["n"]
    for l in equipes.values():
        l["total"] = sum(l[s] for s, _ in SITUACOES)
        l["pendentes"] = sum(l[s] for s in PENDENTES)
    return render(request, "fm/ubs_detalhe.html", {"u": u, "equipes": sorted(equipes.values(), key=lambda l: -l["pendentes"]), "c": _contagem(qs)})


def _filtrar(request):
    qs = _base(request)
    g = request.GET
    f = {k: (g.get(k) or "").strip() for k in ("risco", "unidade", "equipe", "situacao", "cns", "dum_de", "dum_ate", "atd_de", "atd_ate", "prof", "q", "novas", "parto", "o", "recorte", "end")}
    # recorte = novas | parto (campo visivel do filtro); novas=1 / parto=1 continuam aceitos (links antigos)
    if f["recorte"] not in ("novas", "parto", "parto_provavel", "curso"):
        f["recorte"] = "novas" if f["novas"] == "1" else "parto" if f["parto"] == "1" else ""
    f["novas"] = "1" if f["recorte"] == "novas" else ""
    f["parto"] = "1" if f["recorte"] == "parto" else ""
    if f["unidade"].isdigit():
        qs = qs.filter(unidade_id=int(f["unidade"]))
    if f["equipe"].isdigit():
        qs = qs.filter(equipe_id=int(f["equipe"]))
    if f["situacao"] == "pendentes":
        qs = qs.filter(situacao__in=PENDENTES)
    elif f["situacao"] in SIT:
        qs = qs.filter(situacao=f["situacao"])
    if f["end"] == "nao":      # sem endereco em nenhuma ficha do e-SUS (para a UBS completar o cadastro)
        qs = qs.filter(cep="", logradouro="", bairro_end="")
    elif f["end"] == "sim":
        qs = qs.exclude(cep="", logradouro="", bairro_end="")
    elif f["end"] == "mapa":
        qs = qs.exclude(lat=None)
    if f["cns"] == "sim":
        qs = qs.filter(tem_cns_cadastro=True)
    elif f["cns"] == "nao":
        qs = qs.filter(tem_cns_cadastro=False)
    for campo, chave in (("dum__gte", "dum_de"), ("dum__lte", "dum_ate"), ("ultimo_atendimento__date__gte", "atd_de"), ("ultimo_atendimento__date__lte", "atd_ate")):
        try:
            if f[chave]:
                qs = qs.filter(**{campo: dt.date.fromisoformat(f[chave])})
        except ValueError:
            f[chave] = ""
    if f["prof"]:
        qs = qs.filter(profissional__icontains=f["prof"][:100])
    if f["q"]:
        q = f["q"][:100]
        dig = "".join(ch for ch in q if ch.isdigit())
        cond = Q(nome__icontains=q) | Q(nome_mae__icontains=q)
        if len(dig) >= 4:
            cond |= Q(cpf__startswith=dig) | Q(cns__startswith=dig)
        qs = qs.filter(cond)
    if f["novas"] == "1":   # entrou no painel nos ultimos 7 dias; sem situacao escolhida, so as nao aceitas
        qs = qs.filter(primeira_vista__gte=timezone.now() - dt.timedelta(days=7))
        if not f["situacao"]:
            qs = qs.exclude(situacao="aceita")
    if f["parto"] == "1":   # 33 a 42 semanas de DUM; sem situacao escolhida, so as nao aceitas
        qs = qs.filter(dum__lte=timezone.localdate() - dt.timedelta(days=230), dum__gte=timezone.localdate() - dt.timedelta(days=294))
        if not f["situacao"]:
            qs = qs.exclude(situacao="aceita")
    if f["recorte"] == "parto_provavel":   # mais de 42 semanas de DUM (ate 1 ano): gestacao provavelmente encerrada, ainda enviada
        qs = qs.filter(dum__lt=timezone.localdate() - dt.timedelta(days=294))
        if not f["situacao"]:
            qs = qs.exclude(situacao__in=("aceita", "fora_recorte"))
    if f["risco"] == "1":
        qs = qs.filter(Q(risco_hipertensao=True) | Q(risco_diabetes=True) | Q(gestacao_multipla=True))
    if f["recorte"] == "curso":   # pendentes com gestacao em curso: ate 42 semanas de DUM (ou sem DUM)
        qs = qs.filter(Q(dum__gte=timezone.localdate() - dt.timedelta(days=294)) | Q(dum=None))
        if not f["situacao"]:
            qs = qs.exclude(situacao__in=("aceita", "fora_recorte"))
    ordem = {"nome": "nome", "ubs": "unidade__nome", "dum": "dum", "atd": "-ultimo_atendimento", "sit": "situacao", "desde": "situacao_desde"}.get(f["o"], "nome")
    return qs.order_by(ordem, "nome"), f


@login_required
def gestantes(request):
    qs, f = _filtrar(request)
    if request.GET.get("exportar") == "1":
        completo = settings.CPF_COMPLETO_PADRAO or request.GET.get("cpf") == "completo"
        _trilha(request, "exportar_completo" if completo else "exportar", json.dumps({k: v for k, v in f.items() if v}) + f" n={qs.count()} {_cadeia_ip(request)}")
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="gestantes-filhos-de-minas-{timezone.localdate():%Y-%m-%d}{"-cpf-completo" if completo else ""}.csv"'
        resp.write("﻿")
        w = csv.writer(resp, delimiter=";")
        w.writerow(["Situação", "Motivo", "O que fazer", "Unidade", "CNES", "Equipe", "INE", "Nome", "CPF", "CNS", "Nascimento", "Nome da mãe",
                    "Telefone", "Bairro", "DUM", "Último atendimento", "Profissional", "Atendimentos", "Nesta situação desde", "Aceita em"])
        mostra_cpf = completo
        for g in qs.iterator():
            w.writerow([SIT.get(g.situacao), g.motivo, g.orientacao, g.unidade.nome if g.unidade else "", g.unidade.cnes if g.unidade else "",
                        g.equipe.nome if g.equipe else "", g.equipe.ine if g.equipe else "", g.nome, g.cpf if mostra_cpf else g.cpf_mascarado, g.cns,
                        g.nascimento.strftime("%d/%m/%Y") if g.nascimento else "", g.nome_mae, g.telefone, g.bairro,
                        g.dum.strftime("%d/%m/%Y") if g.dum else "", timezone.localtime(g.ultimo_atendimento).strftime("%d/%m/%Y %H:%M") if g.ultimo_atendimento else "",
                        g.profissional, g.atendimentos, timezone.localtime(g.situacao_desde).strftime("%d/%m/%Y"),
                        timezone.localtime(g.aceita_em).strftime("%d/%m/%Y") if g.aceita_em else ""])
        return resp
    total = qs.count()
    pagina = max(int(request.GET.get("p", "1") or 1), 1)
    por = 50
    itens = list(qs[(pagina - 1) * por: pagina * por])
    _trilha(request, "lista", json.dumps({k: v for k, v in f.items() if v}) + f" p={pagina} n={total}")
    perm = unidades_permitidas(request.user)
    unidades = sorted(Unidade.objects.all() if perm is None else perm, key=lambda u: u.chave_ordem)
    equipes = Equipe.objects.filter(unidade_id=int(f["unidade"])) if f["unidade"].isdigit() else Equipe.objects.none()
    titulo = {"novas": "Gestantes · novas na semana", "parto": "Gestantes · perto do parto", "parto_provavel": "Gestantes · parto provável (mais de 42 semanas)", "curso": "Gestantes · pendentes com gestação em curso"}.get(f["recorte"], "Gestantes")
    return render(request, "fm/gestantes.html", {
        "itens": itens, "total": total, "pagina": pagina, "paginas": max((total + por - 1) // por, 1), "f": f, "titulo": titulo,
        "unidades": unidades, "equipes": equipes, "situacoes": SITUACOES, "hoje": timezone.localdate(),
        "query": request.GET.urlencode(),
    })


@login_required
def gestante(request, pk):
    g = get_object_or_404(_base(request), pk=pk)
    _trilha(request, "detalhe", f"gestante={pk}")
    ig = None
    if g.dum:
        dias = (timezone.localdate() - g.dum).days
        ig = {"semanas": dias // 7, "dias": dias % 7, "dpp": g.dum + dt.timedelta(days=280)}
    conf = ConferenciaSES.objects.filter(gestante=g).first()
    sug = SugestaoCNS.objects.filter(cpf=g.cpf).first() if (g.cpf and not g.cns) else None
    return render(request, "fm/gestante.html", {"g": g, "eventos": g.eventos.all()[:50], "sit": SIT, "ig": ig, "conf": conf, "sug": sug})


@login_required
@require_POST
def revelar_cpf(request, pk):
    g = get_object_or_404(_base(request), pk=pk)
    _trilha(request, "revelar_cpf", f"gestante={pk} {_cadeia_ip(request)}")
    return JsonResponse({"cpf": g.cpf, "registrado": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"), "usuario": request.user.username})


@login_required
def alertas(request):
    return render(request, "fm/alertas.html", {"alertas": request.user.alertas.prefetch_related("unidades"),
                                                "telegram": getattr(request.user, "telegram", None), "bot": settings.TELEGRAM_BOT_NOME})


@login_required
def alerta_form(request, pk=None):
    obj = get_object_or_404(Alerta, pk=pk, usuario=request.user) if pk else None
    perm = unidades_permitidas(request.user)
    form = AlertaForm(request.POST or None, instance=obj, unidades_qs=Unidade.objects.all() if perm is None else perm, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        a = form.save(commit=False)
        a.usuario = request.user
        a.save()
        form.save_m2m()
        _trilha(request, "alerta", f"{'editou' if pk else 'criou'} {a.id} {a.nome}")
        # confirmacao imediata pelos canais marcados: quem cadastra ja ve que o caminho funciona
        from .alertas import confirmar
        try:
            canais = confirmar(a, novo=not pk)
            messages.success(request, f"Alerta salvo. Confirmação enviada por {' e '.join(canais)}." if canais else "Alerta salvo, mas nenhuma confirmação pôde ser enviada: confira os canais.")
        except Exception as e:  # noqa: BLE001
            messages.warning(request, f"Alerta salvo, mas a confirmação falhou: {str(e)[:120]}")
        return redirect("alertas")
    return render(request, "fm/alerta_form.html", {"form": form, "obj": obj, "bot": settings.TELEGRAM_BOT_NOME})


@login_required
@require_POST
def alerta_apagar(request, pk):
    a = get_object_or_404(Alerta, pk=pk, usuario=request.user)
    _trilha(request, "alerta", f"apagou {a.id} {a.nome}")
    a.delete()
    messages.success(request, "Alerta apagado.")
    return redirect("alertas")


@login_required
def telegram(request):
    v, novo = VinculoTelegram.objects.get_or_create(usuario=request.user, defaults={"codigo": secrets.token_hex(4).upper()})
    if request.method == "POST":
        if request.POST.get("acao") == "novo_codigo":
            v.codigo, v.chat_id, v.verificado_em = secrets.token_hex(4).upper(), "", None
            v.save()
        elif request.POST.get("acao") == "desvincular":
            v.chat_id, v.verificado_em = "", None
            v.save()
        return redirect("telegram")
    return render(request, "fm/telegram.html", {"v": v, "bot": settings.TELEGRAM_BOT_NOME})


@login_required
def situacao(request):
    confs = ConferenciaSES.objects.filter(gestante__ativa=True)
    ultima = confs.order_by("-verificado_em").values_list("verificado_em", flat=True).first()
    conferencia = {"quando": ultima, "n": confs.count(), "cadastradas": confs.filter(cadastrada=True).count(),
                   "divergencias": confs.exclude(divergencia="").count(), "erros": confs.exclude(erro="").count(),
                   "kits": confs.exclude(data_entrega_kit=None).count()} if ultima else None
    divergentes = filtra(confs.exclude(divergencia="").select_related("gestante", "gestante__unidade"), request.user, "gestante__unidade").order_by("gestante__unidade__nome", "gestante__nome")[:60]
    return render(request, "fm/situacao.html", {"coletas": Coleta.objects.all()[:30], "rotinas": Rotina.objects.all()[:48], "graficos": json.dumps(ind.rotinas_duracao()),
                                                 "acessos": Acesso.objects.select_related("usuario")[:30] if e_admin(request.user) else None,
                                                 "conferencia": conferencia, "divergentes": divergentes})


def sem_acesso(request):
    return render(request, "fm/sem_acesso.html", status=403)


def sair(request):
    """Encerra a sessao local e, com SSO e sessao vinda dele, tambem a do provedor (end-session com id_token_hint)."""
    if settings.SSO_ATIVO and not request.session.get("login_local"):
        from .auth import url_logout
        destino = url_logout(request)      # calcula ANTES do logout local (precisa do id_token da sessao)
        _trilha(request, "logout", "sso")
        logout(request)
        return redirect(destino)
    _trilha(request, "logout", "local")
    logout(request)
    return redirect("/")


def _ip_permitido(ip):
    """LOGIN_LOCAL_IPS vazio = qualquer origem; senao, IP ou rede (CIDR) da lista."""
    import ipaddress
    if not settings.LOGIN_LOCAL_IPS:
        return True
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for r in settings.LOGIN_LOCAL_IPS:
        try:
            if a in ipaddress.ip_network(r, strict=False):
                return True
        except ValueError:
            continue
    return False


def entrar(request):
    """Porta de entrada com SSO ativo: botao do login unico e link do login local (usuarios criados no painel)."""
    if request.user.is_authenticated:
        return redirect("/")
    if not settings.SSO_ATIVO:
        return redirect("entrar_local")
    return render(request, "fm/entrar.html", {"local_ok": _ip_permitido(_ip(request))})


def entrar_local(request):
    """Login local (usuarios da tela Usuarios). Com SSO ativo, so a partir das origens em LOGIN_LOCAL_IPS. Fica na trilha."""
    if request.user.is_authenticated:
        return redirect("/")
    if settings.SSO_ATIVO and not _ip_permitido(_ip(request)):
        raise Http404
    erro = ""
    if request.method == "POST":
        u = authenticate(request, username=(request.POST.get("usuario", "") or "").strip().lower(), password=request.POST.get("senha", ""))
        if u:
            login(request, u, backend="django.contrib.auth.backends.ModelBackend")
            request.session["login_local"] = True
            _trilha(request, "login", f"local {_cadeia_ip(request)}")
            destino = request.GET.get("next") or "/"
            return redirect(destino if destino.startswith("/") and not destino.startswith("//") else "/")
        _trilha(request, "login_falhou", f"local usuario={request.POST.get('usuario', '')[:60]} {_cadeia_ip(request)}")
        erro = "Usuário ou senha inválidos."
    return render(request, "fm/entrar_local.html", {"erro": erro})


def logo(request):
    """Logotipo do municipio (LOGO no ambiente); sem arquivo, o padrao do painel."""
    import mimetypes, os
    from django.http import FileResponse
    from django.contrib.staticfiles import finders
    caminho = settings.LOGO if settings.LOGO and os.path.isfile(settings.LOGO) else finders.find("fm/logo.svg")
    r = FileResponse(open(caminho, "rb"), content_type=mimetypes.guess_type(caminho)[0] or "image/png")
    r.headers["Cache-Control"] = "public, max-age=3600"
    return r


def _so_admin(request):
    if not e_admin(request.user):
        raise Http404


@login_required
def usuarios(request):
    _so_admin(request)
    from django.contrib.auth.models import User
    lista = User.objects.select_related("perfil").order_by("-is_superuser", "username")
    return render(request, "fm/usuarios.html", {"usuarios": lista})


@login_required
def usuario_form(request, pk=None):
    """Cria ou edita usuario local. A senha e gerada pelo painel e mostrada uma unica vez (criacao ou 'redefinir senha')."""
    _so_admin(request)
    from django.contrib.auth.models import User
    from .forms import UsuarioForm
    from .models import Perfil
    obj = get_object_or_404(User, pk=pk) if pk else None
    if obj and getattr(obj, "perfil", None) and obj.perfil.origem == "sso":
        messages.error(request, "Usuário do SSO: nome, e-mail e papel vêm do provedor a cada login. Para bloquear, remova-o lá.")
        return redirect("usuarios")
    senha_nova = None
    if request.method == "POST" and request.POST.get("acao") == "redefinir" and obj:
        senha_nova = secrets.token_urlsafe(12)
        obj.set_password(senha_nova); obj.save(update_fields=["password"])
        _trilha(request, "usuario", f"senha redefinida: {obj.username}")
        form = UsuarioForm(instance=obj)
    else:
        form = UsuarioForm(request.POST or None, instance=obj)
        if request.method == "POST" and form.is_valid():
            u = form.save(commit=False)
            admin = form.cleaned_data["papel"] == "administrador"
            if obj and obj.pk == request.user.pk and (not admin or not u.is_active):
                form.add_error(None, "Você não pode tirar o seu próprio acesso de administrador nem se desativar.")
            else:
                u.is_superuser = admin; u.is_staff = False
                if not obj:
                    senha_nova = secrets.token_urlsafe(12); u.set_password(senha_nova)
                u.save()
                Perfil.objects.update_or_create(usuario=u, defaults={"origem": "local"})
                _trilha(request, "usuario", f"{'criado' if not obj else 'editado'}: {u.username} papel={form.cleaned_data['papel']} ativo={u.is_active}")
                if not senha_nova:
                    messages.success(request, f"Usuário {u.username} salvo.")
                    return redirect("usuarios")
                obj = u
    return render(request, "fm/usuario_form.html", {"form": form, "obj": obj, "senha_nova": senha_nova})


def saude(request):
    c = Coleta.objects.filter(ok=True).first()
    ok = bool(c and (timezone.now() - c.fim) < dt.timedelta(hours=3))
    return JsonResponse({"ok": ok, "ultima_coleta": timezone.localtime(c.fim).isoformat() if c else None}, status=200 if ok else 503)


@login_required
def indicadores(request):
    qs = _base(request)
    f = {k: (request.GET.get(k) or "").strip() for k in ("unidade",)}
    if f["unidade"].isdigit():
        qs = qs.filter(unidade_id=int(f["unidade"]))
    perm = unidades_permitidas(request.user)
    unidades = sorted(Unidade.objects.all() if perm is None else perm, key=lambda u: u.chave_ordem)
    fora_recorte = qs.filter(situacao="fora_recorte").count()
    cal = ind.calor_ubs_motivo(qs)
    qs = qs.exclude(situacao="fora_recorte")   # indicadores do programa: so gestacoes no recorte
    fun = ind.funil(qs); cap = ind.captacao(qs); con = ind.consultas(qs); ris = ind.risco(qs); men = ind.mensal(qs)
    fx = ind.faixa_etaria(qs); tri = ind.trimestre(qs); tempo = ind.tempo_na_situacao(qs); prof = ind.profissionais(qs); pre = ind.prenatal(qs)
    graficos = {"funil_rotulos": [a for a, _ in fun], "funil": [b for _, b in fun],
                "fx_rotulos": [a for a, _, _ in fx], "fx_total": [b for _, b, _ in fx], "fx_pend": [c for _, _, c in fx],
                "tri_rotulos": [a for a, _, _ in tri], "tri_total": [b for _, b, _ in tri], "tri_pend": [c for _, _, c in tri],
                "tempo_rotulos": [a for a, _ in tempo], "tempo": [b for _, b in tempo],
                "capt_rotulos": [a for a, _ in cap["faixas"]], "capt": [b for _, b in cap["faixas"]],
                "cons_rotulos": [a for a, _ in con["dist"]], "cons": [b for _, b in con["dist"]],
                "mes_rotulos": men["rotulos"], "mes_aceitas": men["aceitas"], "mes_entradas": men["entradas"]}
    _trilha(request, "indicadores", json.dumps({k: v for k, v in f.items() if v}))
    return render(request, "fm/indicadores.html", {"fora_recorte": fora_recorte, "pre": pre, "f": f, "unidades": unidades, "funil": fun, "cap": cap, "con": con, "ris": ris, "men": men, "cal": cal,
                                                   "fx": fx, "tri": tri, "tempo": tempo, "prof": prof,
                                                   "graficos": json.dumps(graficos), "total": qs.count()})


@login_required
def mapa(request):
    qs = _base(request)
    perm = unidades_permitidas(request.user)
    unidades = sorted(Unidade.objects.all() if perm is None else perm, key=lambda u: u.chave_ordem)
    geo = qs.exclude(lat=None).count()
    _trilha(request, "mapa", f"n={qs.count()} geo={geo}")
    return render(request, "fm/mapa.html", {"unidades": unidades, "total": qs.count(), "geo": geo, "situacoes": SITUACOES,
                                            "ubs_geo": Unidade.objects.exclude(lat=None).count(), "ubs_total": Unidade.objects.count()})


@login_required
def ubs_foto(request, cnes):
    """Foto da fachada da UBS (arquivo <cnes>.jpg em FOTOS_UBS). Sem foto: 404. So digitos no nome."""
    import os
    from django.http import FileResponse
    caminho = os.path.join(settings.FOTOS_UBS, f"{cnes}.jpg")
    if not cnes.isdigit() or not os.path.isfile(caminho):
        raise Http404
    r = FileResponse(open(caminho, "rb"), content_type="image/jpeg")
    r.headers["Cache-Control"] = "private, max-age=86400"
    return r


@login_required
def mapa_pontos(request):
    """JSON dos pontos, sempre dentro do escopo do usuario (nunca confiar em parametro do cliente)."""
    qs = _base(request)
    g = request.GET
    if (g.get("unidade") or "").isdigit():
        qs = qs.filter(unidade_id=int(g["unidade"]))
    if g.get("situacao") == "pendentes":
        qs = qs.filter(situacao__in=PENDENTES)
    elif g.get("situacao") in SIT:
        qs = qs.filter(situacao=g["situacao"])
    return JsonResponse(ind.pontos_mapa(qs))


def _semanas(g, hoje):
    return (hoje - g.dum).days // 7 if g.dum else None


@login_required
def fila(request):
    """Fila de trabalho da UBS: blocos por urgencia, so gestacoes em curso (ate 42 semanas)."""
    qs = _base(request)
    perm = unidades_permitidas(request.user)
    unidades = sorted(Unidade.objects.all() if perm is None else perm, key=lambda u: u.chave_ordem)
    f = {"unidade": (request.GET.get("unidade") or "").strip()}
    if not f["unidade"] and perm is not None and len(unidades) == 1:
        f["unidade"] = str(unidades[0].id)
    if f["unidade"].isdigit():
        qs = qs.filter(unidade_id=int(f["unidade"]))
    hoje = timezone.localdate(); agora = timezone.now(); limite = 15
    u = f"&unidade={f['unidade']}" if f["unidade"].isdigit() else ""
    em_curso = qs.filter(situacao__in=PENDENTES).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None))
    risco = Q(risco_hipertensao=True) | Q(risco_diabetes=True) | Q(gestacao_multipla=True)
    defs = [
        ("risco", "Gestação de risco ainda pendente", "erro", em_curso.filter(risco).order_by("dum"), "Prioridade máxima: resolver o cadastro hoje (CNS/CPF) e garantir a consulta. Hipertensão, diabetes ou gestação múltipla registradas no atendimento.", f"/gestantes/?recorte=curso&risco=1{u}"),
        ("parto", "Perto do parto (33 a 42 semanas) e pendente", "alerta", em_curso.filter(dum__lte=hoje - dt.timedelta(days=230)).order_by("dum"), "Pouco tempo para entrar no programa: corrigir o cadastro antes do parto.", f"/gestantes/?recorte=parto{u}"),
        ("sem_consulta", "Sem consulta há mais de 60 dias (gestação em curso)", "alerta", qs.exclude(situacao__in=("aceita", "fora_recorte")).filter(dias_sem_consulta__gt=60).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None)).order_by("-dias_sem_consulta"), "Busca ativa: agendar a consulta de pré-natal. Aceitas pela SES-MG também aparecem aqui se estiverem sem consulta.", f"/gestantes/?recorte=curso{u}&o=atd"),
        ("sem_cns", "Sem CNS no cadastro", "alerta", em_curso.filter(situacao="sem_cns").order_by("dum"), "No PEC, abrir o cadastro do cidadão pelo CPF, consultar o CadSUS e gravar o CNS. O envio sai sozinho na hora seguinte.", f"/gestantes/?situacao=sem_cns&recorte=curso{u}"),
        ("sem_cpf", "Sem CPF no e-SUS", "alerta", em_curso.filter(situacao="sem_cpf").order_by("dum"), "Cadastrar o CPF da gestante no PEC (a SES-MG exige CPF).", f"/gestantes/?situacao=sem_cpf&recorte=curso{u}"),
        ("fora_bolsa", "Fora do Bolsa Família", "neutro", em_curso.filter(situacao="fora_bolsa").order_by("dum"), "Conferir se o CPF do cadastro é o da gestante. Se for, a recusa é do CadÚnico: orientar sobre o CRAS. O extrator tenta de novo uma vez por dia.", f"/gestantes/?situacao=fora_bolsa&recorte=curso{u}"),
        ("novas", "Novas na semana, ainda pendentes", "", em_curso.filter(primeira_vista__gte=agora - dt.timedelta(days=7)).order_by("-primeira_vista"), "Entraram no painel nos últimos 7 dias: conferir o cadastro logo na primeira consulta.", f"/gestantes/?recorte=novas{u}"),
        ("parto_registrado", "Parto registrado no PEC e ainda pendente", "neutro", qs.filter(parto_registrado=True).exclude(situacao__in=("aceita", "fora_recorte")).order_by("-ultimo_atendimento"), "O atendimento registrou parto ou puerpério: a gestação encerrou. Nada a fazer para o Filhos de Minas; sai da fila quando a DUM passar de 1 ano.", f"/gestantes/?recorte=parto_provavel{u}"),
        ("sem_exame", "Sem teste de sífilis ou HIV registrado", "alerta", qs.exclude(situacao="fora_recorte").filter(consultas__gte=1).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None)).filter(Q(exame_sifilis=False) | Q(exame_hiv=False)).order_by("dum"), "Gestação em curso com consulta e sem VDRL/teste rápido de sífilis ou anti-HIV registrado no PEC: solicitar ou registrar o resultado (inclui aceitas pela SES-MG).", f"/gestantes/?recorte=curso{u}"),
        ("sem_end", "Sem endereço no e-SUS", "neutro", qs.exclude(situacao="fora_recorte").filter(cep="", logradouro="", bairro_end="").order_by("nome"), "Completar o cadastro domiciliar (ficha do ACS) para a gestante aparecer no mapa.", f"/gestantes/?end=nao{u}"),
    ]
    blocos = []
    for chave, titulo, cor, q, acao, link in defs:
        itens = list(q.select_related("unidade", "equipe")[:limite])
        sugs = {s.cpf: s for s in SugestaoCNS.objects.filter(cpf__in=[g.cpf for g in itens if g.cpf and not g.cns])} if chave in ("sem_cns", "risco", "parto", "novas") else {}
        for g in itens:
            g.semanas = _semanas(g, hoje); g.sugestao = sugs.get(g.cpf)
        blocos.append({"chave": chave, "titulo": titulo, "cor": cor, "total": q.count(), "itens": itens, "acao": acao, "link": link})
    _trilha(request, "fila", f"unidade={f['unidade']}")
    return render(request, "fm/fila.html", {"blocos": blocos, "unidades": unidades, "f": f, "limite": limite})


@login_required
def desempenho(request):
    """Ranking de resolucao por UBS: resolvidas (pendente -> aceita) em 7 e 30 dias, novas pendentes, tempo ate o aceite."""
    qs = _base(request)
    agora = timezone.now(); hoje = timezone.localdate()
    d7, d30 = agora - dt.timedelta(days=7), agora - dt.timedelta(days=30)
    linhas = {}
    def linha(uid, nome):
        return linhas.setdefault(uid, {"id": uid, "nome": nome or "(sem UBS)", "total": 0, "aceita": 0, "curso": 0, "res7": 0, "res30": 0, "novas30": 0, "tempos": []})
    for r in qs.values("unidade_id", "unidade__nome", "situacao").annotate(n=Count("id")):
        l = linha(r["unidade_id"], r["unidade__nome"]); l["total"] += r["n"]
        if r["situacao"] == "aceita":
            l["aceita"] += r["n"]
    for r in qs.filter(situacao__in=PENDENTES).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None)).values("unidade_id", "unidade__nome").annotate(n=Count("id")):
        linha(r["unidade_id"], r["unidade__nome"])["curso"] = r["n"]
    ev = Evento.objects.filter(para="aceita", quando__gte=d30, gestante__in=qs).exclude(de="").values("gestante__unidade_id", "gestante__unidade__nome", "quando")
    for e in ev:
        l = linha(e["gestante__unidade_id"], e["gestante__unidade__nome"]); l["res30"] += 1
        if e["quando"] >= d7:
            l["res7"] += 1
    for r in qs.filter(primeira_vista__gte=d30).exclude(situacao__in=("aceita", "fora_recorte")).values("unidade_id", "unidade__nome").annotate(n=Count("id")):
        linha(r["unidade_id"], r["unidade__nome"])["novas30"] = r["n"]
    for g in qs.filter(aceita_em__gte=d30).exclude(primeira_vista=None).values("unidade_id", "unidade__nome", "aceita_em", "primeira_vista"):
        linha(g["unidade_id"], g["unidade__nome"])["tempos"].append((g["aceita_em"] - g["primeira_vista"]).total_seconds() / 86400)
    tot = {"res7": 0, "res30": 0, "novas30": 0, "curso": 0, "tempos": []}
    for l in linhas.values():
        l["tempo"] = round(sum(l["tempos"]) / len(l["tempos"])) if l["tempos"] else None
        l["pct"] = round(100 * l["aceita"] / (l["aceita"] + l["curso"])) if (l["aceita"] + l["curso"]) else 0
        for k in ("res7", "res30", "novas30", "curso"):
            tot[k] += l[k]
        tot["tempos"] += l["tempos"]
    tot["tempo"] = round(sum(tot["tempos"]) / len(tot["tempos"])) if tot["tempos"] else None
    lista = sorted(linhas.values(), key=lambda l: (-l["res30"], -l["res7"], l["curso"], chave_nome_unidade(l["nome"])))
    graficos = {"nomes": [l["nome"].replace("Unidade de Saude ", "").replace("Unidade Basica de Saude ", "") for l in lista], "res30": [l["res30"] for l in lista], "curso": [l["curso"] for l in lista]}
    _trilha(request, "desempenho", "")
    return render(request, "fm/desempenho.html", {"linhas": lista, "tot": tot, "hoje": hoje, "graficos": json.dumps(graficos)})


@login_required
def tv(request):
    """Modo TV: cartoes principais em tela cheia, atualizando sozinho (meta refresh)."""
    qs = _base(request)
    c = _contagem(qs); agora = timezone.now(); hoje = timezone.localdate()
    ubs_top = [{"nome": (u["unidade__nome"] or "(sem UBS)").replace("Unidade de Saude ", "").replace("Unidade Basica de Saude ", ""), "n": u["n"]}
               for u in qs.filter(situacao__in=PENDENTES).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None)).values("unidade__nome").annotate(n=Count("id")).order_by("-n")[:10]]
    return render(request, "fm/tv.html", {"c": c, "rotina": Rotina.objects.first(), "coleta": Coleta.objects.filter(ok=True).first(),
                                          "aceitas_semana": qs.filter(aceita_em__gte=agora - dt.timedelta(days=7)).count(), "ubs_top": ubs_top})
