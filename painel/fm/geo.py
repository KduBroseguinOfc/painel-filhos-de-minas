"""Geocodificacao: casa da gestante (rua + bairro + CEP) e ponto da UBS (bairro), pelo Nominatim do OpenStreetMap,
com cache local (GeoCache) e no maximo 1 consulta por segundo (politica de uso do Nominatim). Roda em lotes por um
timer noturno; nunca na hora da pagina. O que vai para fora e so o endereco (sem nome, sem CPF)."""
import logging
import re
import time

import requests
from django.conf import settings
from django.utils import timezone

from django.db import OperationalError

from .models import GeoCache, Gestante, Unidade


def _salvar(obj, campos, tentativas=6):
    """O banco do painel e SQLite: se a coleta estiver escrevendo (transacao de ~30 s), espera e tenta de novo."""
    for i in range(tentativas):
        try:
            obj.save(update_fields=campos)
            return
        except OperationalError as e:
            if "locked" not in str(e) or i == tentativas - 1:
                raise
            time.sleep(10)

log = logging.getLogger(__name__)
UA = f"PainelFilhosDeMinas/1.0 ({settings.MUNICIPIO}-{settings.UF}; contato: {settings.GEO_CONTATO or 'nao informado'})"
LOCAL = f"{settings.MUNICIPIO}, {settings.UF}"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
VIACEP = "https://viacep.com.br/ws/{cep}/json/"
# caixa do municipio (lat sul/norte, lon oeste/leste): descarta resultado fora da regiao. Vem de GEO_CAIXA ou e
# descoberta uma vez pelo proprio Nominatim (limites do municipio + 0,05 grau) e guardada ao lado do banco do painel.
CAIXA = None


def _caixa():
    global CAIXA
    if CAIXA:
        return CAIXA
    if settings.GEO_CAIXA:
        CAIXA = tuple(float(x) for x in settings.GEO_CAIXA.split(","))
        return CAIXA
    import json
    from pathlib import Path
    arq = Path(settings.DB_PAINEL).with_name("caixa-municipio.json")
    try:
        d = json.loads(arq.read_text())
        if d.get("local") == LOCAL:
            CAIXA = tuple(d["caixa"]); return CAIXA
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(1.05)
    r = requests.get(NOMINATIM, params={"q": f"{LOCAL}, Brasil", "format": "json", "limit": 1, "countrycodes": "br"}, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    b = [float(x) for x in r.json()[0]["boundingbox"]]      # sul, norte, oeste, leste
    CAIXA = (b[0] - 0.05, b[1] + 0.05, b[2] - 0.05, b[3] + 0.05)
    try:
        arq.write_text(json.dumps({"local": LOCAL, "caixa": CAIXA}))
    except OSError as e:
        log.warning("caixa do municipio nao gravada: %s", e)
    return CAIXA


def _dentro(lat, lon):
    c = _caixa()
    return c[0] <= lat <= c[1] and c[2] <= lon <= c[3]


def _nominatim(q):
    time.sleep(1.05)
    r = requests.get(NOMINATIM, params={"q": q, "format": "json", "limit": 1, "countrycodes": "br"}, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    d = r.json()
    if d:
        lat, lon = float(d[0]["lat"]), float(d[0]["lon"])
        if _dentro(lat, lon):
            return lat, lon
    return None


def _viacep(cep):
    r = requests.get(VIACEP.format(cep=cep), headers={"User-Agent": UA}, timeout=15)
    if r.ok:
        d = r.json()
        if not d.get("erro"):
            return d.get("logradouro") or "", d.get("bairro") or "", d.get("localidade") or ""
    return None


def _cache(chave, fn):
    c = GeoCache.objects.filter(chave=chave).first()
    if c and (c.lat or (timezone.now() - c.atualizado_em).days < 30):
        return c
    lat = lon = None; prec = fonte = ""
    try:
        res = fn()
        if res:
            lat, lon, prec, fonte = res
    except Exception as e:  # noqa: BLE001
        log.warning("geo %s: %s", chave[:40], e)
    for i in range(6):
        try:
            c, _ = GeoCache.objects.update_or_create(chave=chave, defaults={"lat": lat, "lon": lon, "precisao": prec, "fonte": fonte})
            return c
        except OperationalError as e:
            if "locked" not in str(e) or i == 5:
                raise
            time.sleep(10)


def geocodificar_gestante(g):
    def busca():
        cep = re.sub(r"\D", "", g.cep or "")
        rua = (g.logradouro or "").strip()
        bairro = (g.bairro_end or "").strip()
        if cep and not rua:
            v = _viacep(cep)
            if v:
                rua, bairro = v[0] or rua, v[1] or bairro
        if rua:
            q = f"{rua}{(', ' + g.numero) if g.numero else ''}, {bairro + ', ' if bairro else ''}{LOCAL}, {cep[:5] + '-' + cep[5:] if cep else ''}"
            r = _nominatim(q)
            if r:
                return r[0], r[1], "endereco", "nominatim"
        if cep:
            r = _nominatim(f"{cep[:5]}-{cep[5:]}, {LOCAL}")
            if r:
                return r[0], r[1], "cep", "nominatim"
        if bairro:
            r = _nominatim(f"{bairro}, {LOCAL}")
            if r:
                return r[0], r[1], "bairro", "nominatim"
        return None
    chave = f"g:{g.cep}|{(g.logradouro or '')[:80]}|{g.numero}|{(g.bairro_end or '')[:40]}".lower()
    c = _cache(chave, busca)
    g.lat, g.lon, g.geo_precisao, g.geo_em = c.lat, c.lon, c.precisao if c.lat else "", timezone.now()
    _salvar(g, ["lat", "lon", "geo_precisao", "geo_em"])
    return bool(c.lat)


def geocodificar_unidade(u):
    """Ponto da UBS: pelo endereco do cadastro da unidade no PEC; sem endereco, pelo bairro."""
    def busca():
        if u.endereco:
            cep = u.cep
            r = _nominatim(f"{u.endereco}, {u.bairro + ', ' if u.bairro else ''}{LOCAL}{', ' + cep[:5] + '-' + cep[5:] if cep else ''}")
            if r:
                return r[0], r[1], "endereco", "nominatim"
        for termo in [u.bairro, u.nome_curto, u.nome]:
            if termo:
                r = _nominatim(f"{termo}, {LOCAL}")
                if r:
                    return r[0], r[1], "bairro", "nominatim"
        return None
    c = _cache(f"u:{u.cnes}|{(u.endereco or '')[:60]}".lower(), busca)
    u.lat, u.lon, u.geo_em = c.lat, c.lon, timezone.now()
    _salvar(u, ["lat", "lon", "geo_em"])
    return bool(c.lat)


def rodar(limite=300):
    """Lote: unidades sem ponto, depois gestantes ativas com endereco e sem ponto (ou com ponto velho > 30 d)."""
    feitos = ok = 0
    from django.db.models import Q
    for u in Unidade.objects.filter(geo_fonte="").filter(Q(lat=None) | Q(geo_em=None) | Q(geo_em__lt=timezone.now() - timezone.timedelta(days=30))):
        ok += geocodificar_unidade(u); feitos += 1
    corte = timezone.now() - timezone.timedelta(days=30)
    qs = Gestante.objects.filter(ativa=True).exclude(cep="", logradouro="", bairro_end="").filter(models_q_sem_ponto(corte))
    for g in qs.order_by("geo_em")[:limite]:
        ok += geocodificar_gestante(g); feitos += 1
    return feitos, ok


def models_q_sem_ponto(corte):
    from django.db.models import Q
    return Q(geo_em=None) | Q(geo_em__lt=corte)
