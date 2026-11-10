"""Indicadores da visao 'Indicadores' e dados do mapa. Tudo calculado sobre a foto do painel (fm_gestante),
dentro do escopo do usuario; nada aqui consulta o DW."""
import datetime as dt
from collections import defaultdict

from django.db.models import Count, Q
from django.utils import timezone

from .models import SITUACOES

PENDENTES = ["sem_cns", "fora_bolsa", "sem_cpf", "erro_api", "pendente"]
SIT = dict(SITUACOES)


def funil(qs):
    """Elegiveis -> com CPF -> com CNS -> enviadas (tentadas) -> aceitas."""
    total = qs.count()
    com_cpf = qs.exclude(cpf="").count()
    com_cns = qs.exclude(cpf="").exclude(cns="").count()
    tentadas = qs.exclude(situacao="pendente").count()
    aceitas = qs.filter(situacao="aceita").count()
    return [("Elegíveis no recorte", total), ("Com CPF no e-SUS", com_cpf), ("Com CPF e CNS", com_cns),
            ("Enviadas à SES-MG", tentadas), ("Aceitas", aceitas)]


def captacao(qs):
    """Captacao precoce: 1a consulta ate a 12a semana (indicador da Atencao Primaria)."""
    com = qs.exclude(semanas_na_captacao=None)
    precoce = com.filter(semanas_na_captacao__lte=12).count()
    n = com.count()
    por_ubs = []
    for r in com.values("unidade__nome").annotate(n=Count("id"), p=Count("id", filter=Q(semanas_na_captacao__lte=12))).order_by("-n")[:25]:
        por_ubs.append((r["unidade__nome"] or "(sem UBS)", r["n"], r["p"], round(100 * r["p"] / r["n"]) if r["n"] else 0))
    faixas = [("até 12 sem", com.filter(semanas_na_captacao__lte=12).count()), ("13 a 20", com.filter(semanas_na_captacao__range=(13, 20)).count()),
              ("21 a 28", com.filter(semanas_na_captacao__range=(21, 28)).count()), ("29 ou mais", com.filter(semanas_na_captacao__gte=29).count())]
    return {"n": n, "precoce": precoce, "pct": round(100 * precoce / n) if n else 0, "por_ubs": por_ubs, "faixas": faixas}


def consultas(qs):
    seis = qs.filter(consultas__gte=6).count()
    sem60 = qs.exclude(situacao__in=("aceita", "fora_recorte")).filter(dias_sem_consulta__gt=60).count()
    sem60_total = qs.filter(dias_sem_consulta__gt=60).count()
    dist = [(f"{k}", qs.filter(consultas=k).count()) for k in range(1, 6)] + [("6 ou mais", seis)]
    return {"seis": seis, "sem60": sem60, "sem60_total": sem60_total, "dist": dist, "total": qs.count()}


def risco(qs):
    return {"hipertensao": qs.filter(risco_hipertensao=True).count(), "diabetes": qs.filter(risco_diabetes=True).count(),
            "multipla": qs.filter(gestacao_multipla=True).count(),
            "risco_pendente": qs.filter(Q(risco_hipertensao=True) | Q(risco_diabetes=True) | Q(gestacao_multipla=True)).exclude(situacao__in=("aceita", "fora_recorte")).count()}


def mensal(qs):
    """Aceitas por mes (pela data do aceite) e entradas por mes (1a vista); tempo medio ate o aceite."""
    hoje = timezone.localdate()
    meses = []
    m = hoje.replace(day=1)
    for _ in range(12):
        meses.append(m)
        m = (m - dt.timedelta(days=1)).replace(day=1)
    meses.reverse()
    ace, ent = defaultdict(int), defaultdict(int)
    tempos = []
    for g in qs.values("aceita_em", "primeira_vista", "primeiro_atendimento"):
        if g["aceita_em"]:
            d = timezone.localtime(g["aceita_em"]).date().replace(day=1); ace[d] += 1
            if g["primeiro_atendimento"]:
                tempos.append((g["aceita_em"] - g["primeiro_atendimento"]).days)
        if g["primeira_vista"]:
            ent[timezone.localtime(g["primeira_vista"]).date().replace(day=1)] += 1
    return {"rotulos": [x.strftime("%m/%Y") for x in meses], "aceitas": [ace[x] for x in meses], "entradas": [ent[x] for x in meses],
            "tempo_medio": round(sum(tempos) / len(tempos)) if tempos else None, "n_tempo": len(tempos)}


def calor_ubs_motivo(qs):
    linhas = {}
    for r in qs.values("unidade__nome", "situacao").annotate(n=Count("id")):
        l = linhas.setdefault(r["unidade__nome"] or "(sem UBS)", {s: 0 for s, _ in SITUACOES})
        l[r["situacao"]] = r["n"]
    cols = ["sem_cns", "fora_bolsa", "sem_cpf", "erro_api", "pendente", "aceita", "fora_recorte"]
    maxv = max([l[c] for l in linhas.values() for c in cols] + [1])
    out = []
    for nome in sorted(linhas, key=lambda n: -sum(linhas[n][c] for c in PENDENTES)):
        out.append((nome, [(c, SIT[c], linhas[nome][c], round(linhas[nome][c] / maxv, 2)) for c in cols]))
    return {"colunas": [(c, SIT[c]) for c in cols], "linhas": out}


def idade_anos(nasc, ref):
    return ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))


def faixa_etaria(qs):
    hoje = timezone.localdate()
    fx = {"< 20 (adolescente)": [0, 0], "20 a 34": [0, 0], "35 ou mais": [0, 0], "sem data de nascimento": [0, 0]}
    for nasc, sit in qs.values_list("nascimento", "situacao"):
        if not nasc:
            k = "sem data de nascimento"
        else:
            i = idade_anos(nasc, hoje)
            k = "< 20 (adolescente)" if i < 20 else "35 ou mais" if i >= 35 else "20 a 34"
        fx[k][0] += 1
        if sit not in ("aceita", "fora_recorte"):
            fx[k][1] += 1
    return [(k, v[0], v[1]) for k, v in fx.items()]


def trimestre(qs):
    hoje = timezone.localdate()
    tr = {"1º trimestre (até 13 sem)": [0, 0], "2º trimestre (14 a 27)": [0, 0], "3º trimestre (28 a 42)": [0, 0], "provável parto já ocorrido (> 42 sem)": [0, 0], "sem DUM": [0, 0]}
    for dum, sit in qs.values_list("dum", "situacao"):
        if not dum:
            k = "sem DUM"
        else:
            s = (hoje - dum).days // 7
            k = "1º trimestre (até 13 sem)" if s <= 13 else "2º trimestre (14 a 27)" if s <= 27 else "3º trimestre (28 a 42)" if s <= 42 else "provável parto já ocorrido (> 42 sem)"
        tr[k][0] += 1
        if sit not in ("aceita", "fora_recorte"):
            tr[k][1] += 1
    return [(k, v[0], v[1]) for k, v in tr.items()]


def tempo_na_situacao(qs):
    agora = timezone.now()
    b = {"até 7 dias": 0, "8 a 30 dias": 0, "31 a 90 dias": 0, "mais de 90 dias": 0}
    for desde in qs.exclude(situacao__in=("aceita", "fora_recorte")).values_list("situacao_desde", flat=True):
        d = (agora - desde).days
        k = "até 7 dias" if d <= 7 else "8 a 30 dias" if d <= 30 else "31 a 90 dias" if d <= 90 else "mais de 90 dias"
        b[k] += 1
    return list(b.items())


def profissionais(qs, n=12):
    out = []
    # por profissional E unidade: o mesmo nome pode atender em mais de uma UBS, e quem le precisa saber onde procurar
    for r in (qs.exclude(profissional="").values("profissional", "unidade_id", "unidade__nome")
              .annotate(t=Count("id"), p=Count("id", filter=~Q(situacao__in=("aceita", "fora_recorte")))).order_by("-p", "-t")[:n]):
        out.append((r["profissional"], r["unidade__nome"] or "sem unidade", r["unidade_id"] or "", r["t"], r["p"]))
    return out


def prenatal(qs):
    """Exames do pre-natal registrados no PEC (sifilis, HIV, hepatite B, toxoplasmose) entre as gestantes em curso com
    pelo menos uma consulta. Vacinacao nao entra (em muitos municipios e registrada fora do PEC)."""
    hoje = timezone.localdate()
    base = qs.exclude(situacao="fora_recorte").filter(consultas__gte=1).filter(Q(dum__gte=hoje - dt.timedelta(days=294)) | Q(dum=None))
    n = base.count()
    def pct(k): return round(100 * k / n) if n else 0
    itens = [("Sífilis (VDRL ou teste rápido)", base.filter(exame_sifilis=True).count()), ("HIV (anti-HIV ou teste rápido)", base.filter(exame_hiv=True).count()),
             ("Hepatite B (HBsAg)", base.filter(exame_hepb=True).count()), ("Toxoplasmose (IgG/IgM)", base.filter(exame_toxo=True).count())]
    completo = base.filter(exame_sifilis=True, exame_hiv=True, exame_hepb=True).count()
    por_ubs = []
    for r in base.values("unidade__nome").annotate(n=Count("id"), s=Count("id", filter=Q(exame_sifilis=True)), h=Count("id", filter=Q(exame_hiv=True)),
                                                    b=Count("id", filter=Q(exame_hepb=True)), t=Count("id", filter=Q(exame_toxo=True))).order_by("unidade__nome"):
        por_ubs.append((r["unidade__nome"] or "(sem UBS)", r["n"], round(100 * r["s"] / r["n"]), round(100 * r["h"] / r["n"]), round(100 * r["b"] / r["n"]), round(100 * r["t"] / r["n"])))
    return {"n": n, "itens": [(a, b, pct(b)) for a, b in itens], "completo": completo, "pct_completo": pct(completo), "por_ubs": por_ubs}


def rotinas_duracao(n=48):
    from .models import Rotina
    rs = list(Rotina.objects.exclude(fim=None).order_by("-inicio")[:n])
    rs.reverse()
    return {"rotulos": [timezone.localtime(r.inicio).strftime("%d/%m %Hh") for r in rs],
            "minutos": [round((r.fim - r.inicio).total_seconds() / 60, 1) for r in rs],
            "enviados": [r.enviados for r in rs], "erros": [r.erros for r in rs]}


def _tem_foto(cnes):
    import os
    from django.conf import settings
    return os.path.exists(os.path.join(settings.FOTOS_UBS, f"{cnes}.jpg"))


def pontos_mapa(qs):
    """Pontos para o mapa: casa (quando geocodificada) e, por UBS, o total da unidade com o detalhe (no mapa / sem endereco /
    por situacao). Sem nome: so id, situacao e UBS."""
    casas, por_ubs = [], {}
    for g in qs.select_related("unidade"):
        if g.unidade and g.unidade.lat and g.unidade.lon:
            u = por_ubs.setdefault(g.unidade_id, {"nome": g.unidade.nome, "lat": g.unidade.lat, "lon": g.unidade.lon, "cnes": g.unidade.cnes, "id": g.unidade_id,
                                                  "end": g.unidade.endereco, "foto": _tem_foto(g.unidade.cnes), "n": 0, "no_mapa": 0, "sem_end": 0, **{s: 0 for s, _ in SITUACOES}})
            u["n"] += 1; u[g.situacao] += 1
            if g.lat and g.lon:
                u["no_mapa"] += 1
            elif not (g.cep or g.logradouro or g.bairro_end):
                u["sem_end"] += 1
        if g.lat and g.lon:
            casas.append({"id": g.id, "lat": g.lat, "lon": g.lon, "s": g.situacao, "p": g.geo_precisao, "u": g.unidade.nome if g.unidade else "",
                          "r": 1 if (g.risco_hipertensao or g.risco_diabetes or g.gestacao_multipla) else 0})
    return {"casas": casas, "ubs": list(por_ubs.values())}
