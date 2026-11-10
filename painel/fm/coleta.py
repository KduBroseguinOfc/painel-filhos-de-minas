"""Coleta: le o banco do extrator (SQLite, somente leitura) e o DW do e-SUS (PostgreSQL, transacao somente leitura),
monta a foto de cada gestante, grava eventos de mudanca de situacao, as rotinas horarias e o resumo do dia.
Roda depois de cada rotina do extrator (timer :50). Nao escreve em nenhuma das fontes."""
import datetime as dt
import logging
import re
import sqlite3
from collections import defaultdict
from zoneinfo import ZoneInfo

import psycopg
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Coleta, Equipe, Evento, Gestante, ResumoDiario, Rotina, Unidade

log = logging.getLogger(__name__)
UTC = ZoneInfo("UTC")
BRT = ZoneInfo("America/Sao_Paulo")
RE_SUMMARY = re.compile(r"(\d+)/(\d+) com (\d+) falhas")


def _utc(s):
    """created_at/updated_at do SQLite sao CURRENT_TIMESTAMP (UTC, 'YYYY-MM-DD HH:MM:SS')."""
    if not s:
        return None
    return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def situacao_item(row):
    if row["queued"] == 1:
        return "aceita", ""
    msg = row["message_response"] or ""
    st = row["status_response"]
    if st == "fora_recorte":
        return "fora_recorte", "DUM há mais de 365 dias: fora do recorte do programa; o extrator não envia"
    if st is None and not msg:
        return "pendente", ""
    m = msg.lower()
    if "notnull" in m and "cns" in m:
        return "sem_cns", "API: CNS obrigatório (erro 500)"
    if "bolsa" in m:
        return "fora_bolsa", "API: CPF não faz parte do Bolsa Família (erro 400)"
    if "cpf" in m and ("422" in m or "valid string" in m or "ausente" in m):
        return "sem_cpf", "Sem CPF no e-SUS (erro 422)"
    return "erro_api", re.sub(r"\s+", " ", msg)[:300]


def ler_extrator():
    uri = f"file:{settings.EXTRATOR_DB}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    try:
        itens = con.execute(
            "SELECT item_id, co_fat_cidadao, cpf, cns, queued, status_response, message_response, "
            "dt_inicial_atendimento, dum, professional_name, qtd_filhos, created_at, updated_at FROM module_items "
            "WHERE module_id='filhos_de_minas'").fetchall()
        rotinas = con.execute(
            "SELECT attempt_id, MIN(created_at) ini, MAX(created_at) fim, "
            "MAX(CASE WHEN action='send.summary' THEN message END) resumo "
            "FROM module_logs WHERE module_id='filhos_de_minas' GROUP BY attempt_id "
            "ORDER BY ini DESC LIMIT 400").fetchall()
        return [dict(r) for r in itens], [dict(r) for r in rotinas]
    finally:
        con.close()


SQL_DW = """
SELECT a.co_seq_fat_atd_ind AS item_id,
       c.co_seq_cidadao AS co_cidadao, c.no_cidadao AS nome,
       COALESCE(NULLIF(TRIM(c.nu_cpf),''), NULLIF(TRIM(fcp.nu_cpf_cidadao),''), NULLIF(TRIM(a.nu_cpf_cidadao),'')) AS cpf_cad,
       COALESCE(NULLIF(TRIM(c.nu_cns),''), NULLIF(TRIM(fcp.nu_cns),'')) AS cns_cad,
       c.dt_nascimento AS nascimento, c.no_mae AS nome_mae,
       COALESCE(NULLIF(TRIM(c.nu_telefone_celular),''), NULLIF(TRIM(fcp.nu_telefone_celular),''), NULLIF(TRIM(c.nu_telefone_residencial),'')) AS telefone,
       c.no_bairro AS bairro,
       a.dt_inicial_atendimento,
       u.nu_cnes, u.no_unidade_saude, u.no_bairro AS bairro_ubs,
       e.nu_ine, e.no_equipe,
       COALESCE(dp1.no_profissional, dp2.no_profissional) AS profissional
FROM tb_fat_atendimento_individual a
LEFT JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = a.co_fat_cidadao_pec
LEFT JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
LEFT JOIN tb_dim_unidade_saude u ON u.co_seq_dim_unidade_saude = a.co_dim_unidade_saude_1
LEFT JOIN tb_dim_equipe e ON e.co_seq_dim_equipe = a.co_dim_equipe_1
LEFT JOIN tb_dim_profissional dp1 ON dp1.co_seq_dim_profissional = a.co_dim_profissional_1
LEFT JOIN tb_dim_profissional dp2 ON dp2.co_seq_dim_profissional = a.co_dim_profissional_2
WHERE a.co_seq_fat_atd_ind = ANY(%s)
"""
SQL_LOTE = "SELECT MAX(dt_inicial_atendimento) FROM tb_fat_atendimento_individual"
SQL_UBS = """
SELECT u.nu_cnes, NULLIF(TRIM(u.ds_cep),'') AS cep, NULLIF(TRIM(u.no_bairro),'') AS bairro,
       TRIM(COALESCE(tl.ds_tipo_logradouro,'') || ' ' || COALESCE(u.ds_logradouro,'') || CASE WHEN COALESCE(u.nu_numero,'')<>'' THEN ', ' || u.nu_numero ELSE '' END) AS endereco
FROM tb_unidade_saude u LEFT JOIN tb_dim_tipo_logradouro tl ON tl.co_seq_dim_tipo_logradouro = u.tp_logradouro
WHERE u.nu_cnes = ANY(%s)
"""

# Extensao (precisa de GRANT em tb_fat_atd_ind_problemas, tb_dim_cid, tb_dim_tipo_logradouro): endereco do cidadao
# e CIDs do atendimento. Se o papel nao tiver permissao, a coleta segue sem estes dados (log de aviso).
SQL_DW_EXT = """
WITH atd AS (
  SELECT a.co_seq_fat_atd_ind AS item_id, c.co_seq_cidadao,
         COALESCE(NULLIF(TRIM(c.nu_cpf),''), NULLIF(TRIM(fcp.nu_cpf_cidadao),''), NULLIF(TRIM(a.nu_cpf_cidadao),'')) AS cpf,
         COALESCE(NULLIF(TRIM(c.nu_cns),''), NULLIF(TRIM(fcp.nu_cns),''), NULLIF(TRIM(a.nu_cns),'')) AS cns,
         NULLIF(TRIM(c.ds_cep),'') AS cep_cid,
         TRIM(COALESCE(tl.ds_tipo_logradouro,'') || ' ' || COALESCE(c.ds_logradouro,'')) AS log_cid,
         NULLIF(TRIM(c.nu_numero),'') AS num_cid, NULLIF(TRIM(c.no_bairro),'') AS bairro_cid
  FROM tb_fat_atendimento_individual a
  LEFT JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = a.co_fat_cidadao_pec
  LEFT JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
  LEFT JOIN tb_dim_tipo_logradouro tl ON tl.co_seq_dim_tipo_logradouro = c.tp_logradouro
  WHERE a.co_seq_fat_atd_ind = ANY(%s)
),
ind AS (  -- ficha individual (por CPF ou CNS da gestante): quem e o responsavel pela familia (CPF; se so houver CNS, resolve o CPF pela ficha do responsavel)
  SELECT atd.item_id,
         COALESCE(
           CASE WHEN COALESCE(ci.st_responsavel_familiar,0)=1 THEN atd.cpf
                WHEN ci.nu_cpf_responsavel IS NOT NULL THEN ci.nu_cpf_responsavel
                WHEN ci.nu_cartao_sus_responsavel IS NOT NULL THEN (SELECT r.nu_cpf_cidadao FROM tb_cds_cad_individual r WHERE r.nu_cns_cidadao = ci.nu_cartao_sus_responsavel AND r.nu_cpf_cidadao IS NOT NULL ORDER BY COALESCE(r.st_versao_atual,0) DESC LIMIT 1)
           END, atd.cpf) AS cpf_resp
  FROM atd LEFT JOIN LATERAL (
    SELECT st_responsavel_familiar, nu_cpf_responsavel, nu_cartao_sus_responsavel FROM tb_cds_cad_individual x
    WHERE (atd.cpf IS NOT NULL AND x.nu_cpf_cidadao = atd.cpf) OR (atd.cns IS NOT NULL AND x.nu_cns_cidadao = atd.cns)
    ORDER BY COALESCE(x.st_versao_atual,0) DESC, COALESCE(x.st_ficha_inativa,0) ASC, x.dt_cad_individual DESC NULLS LAST LIMIT 1) ci ON TRUE
),
dom AS (  -- domicilio: pelo CPF do responsavel da familia; se nao houver, pelo CPF da propria gestante no cadastro domiciliar
  SELECT ind.item_id, d.nu_cep, TRIM(COALESCE(tl.ds_tipo_logradouro,'') || ' ' || COALESCE(d.no_logradouro,'')) AS logradouro, d.no_bairro
  FROM ind JOIN atd ON atd.item_id = ind.item_id LEFT JOIN LATERAL (
    SELECT dd.nu_cep, dd.no_logradouro, dd.no_bairro, dd.tp_logradouro,
           CASE WHEN df.nu_cpf_cidadao = ind.cpf_resp THEN 0 ELSE 1 END AS ordem
    FROM tb_cds_domicilio_familia df
    JOIN tb_cds_cad_domiciliar dd ON dd.co_seq_cds_cad_domiciliar = df.co_cds_cad_domiciliar
    WHERE df.nu_cpf_cidadao IN (ind.cpf_resp, atd.cpf) AND COALESCE(dd.no_logradouro,'') <> ''
    ORDER BY 5, COALESCE(dd.st_versao_atual,0) DESC, dd.dt_cad_domiciliar DESC NULLS LAST LIMIT 1) d ON TRUE
  LEFT JOIN tb_dim_tipo_logradouro tl ON tl.co_seq_dim_tipo_logradouro = d.tp_logradouro
),
cids AS (
  SELECT p.co_fat_atd_ind AS item_id, string_agg(DISTINCT cid.nu_cid, ',') AS cids
  FROM tb_fat_atd_ind_problemas p JOIN tb_dim_cid cid ON cid.co_seq_dim_cid = p.co_dim_cid
  WHERE p.co_fat_atd_ind = ANY(%s) GROUP BY 1
)
SELECT atd.item_id,
       COALESCE(NULLIF(dom.nu_cep,''), atd.cep_cid) AS cep,
       COALESCE(NULLIF(dom.logradouro,''), NULLIF(atd.log_cid,'')) AS logradouro,
       CASE WHEN NULLIF(dom.logradouro,'') IS NULL THEN atd.num_cid END AS numero,
       COALESCE(NULLIF(dom.no_bairro,''), atd.bairro_cid) AS bairro_end,
       cids.cids
FROM atd LEFT JOIN dom ON dom.item_id = atd.item_id LEFT JOIN cids ON cids.item_id = atd.item_id
"""


SQL_EXAMES = """
SELECT p.co_cidadao, d.ds_proced, pr.dt_inicial_atendimento::date AS dia
FROM tb_fat_atd_ind_procedimentos pr
JOIN tb_fat_cidadao_pec p ON p.co_seq_fat_cidadao_pec = pr.co_fat_cidadao_pec
JOIN tb_dim_procedimento d ON d.co_seq_dim_procedimento IN (pr.co_dim_procedimento_avaliado, pr.co_dim_procedimento_solicitado)
WHERE p.co_cidadao = ANY(%s) AND pr.dt_inicial_atendimento >= CURRENT_DATE - 400
  AND d.ds_proced ~* 'VDRL|S[IÍ]FILIS|HIV|HBSAG|HEPATITE B|TOXOPLASM'
"""


def atualizar_exames():
    """Exames do pre-natal por gestante ativa: procedimento solicitado ou avaliado no PEC de 30 dias antes da DUM em diante
    (sem DUM: tudo nos ultimos 400 dias). So leitura no DW; grava os 5 campos de exame na gestante."""
    gest = {g.co_cidadao: g for g in Gestante.objects.filter(ativa=True).exclude(co_cidadao=None)}
    if not gest:
        return
    por = {}
    ids = list(gest)
    with psycopg.connect(**settings.DW, connect_timeout=15) as con:
        con.read_only = True
        with con.cursor() as cur:
            for i in range(0, len(ids), 2000):
                cur.execute(SQL_EXAMES, (ids[i:i + 2000],))
                for cid, proced, dia in cur.fetchall():
                    por.setdefault(cid, []).append((proced.upper(), dia))
    import re as _re
    for cid, g in gest.items():
        ini = (g.dum - dt.timedelta(days=30)) if g.dum else None
        procs = {p for p, dia in por.get(cid, []) if ini is None or dia >= ini}
        campos = dict(
            exame_sifilis=any(_re.search(r"VDRL|S[IÍ]FILIS", p) for p in procs),
            exame_hiv=any("HIV" in p for p in procs),
            exame_hepb=any("HBSAG" in p or "HEPATITE B" in p for p in procs),
            exame_toxo=any("TOXOPLASM" in p for p in procs),
            exames_prenatal=len(procs))
        if any(getattr(g, k) != v for k, v in campos.items()):
            Gestante.objects.filter(pk=g.pk).update(**campos)


def ler_dw(ids):
    out = {}
    lote = None
    with psycopg.connect(**settings.DW, connect_timeout=15) as con:
        con.read_only = True
        with con.cursor() as cur:
            for i in range(0, len(ids), 2000):
                cur.execute(SQL_DW, (ids[i:i + 2000],))
                cols = [d.name for d in cur.description]
                for r in cur.fetchall():
                    d = dict(zip(cols, r))
                    out[d["item_id"]] = d
            cur.execute(SQL_LOTE)
            lote = cur.fetchone()[0]
        try:
            with con.cursor() as cur:
                for i in range(0, len(ids), 2000):
                    cur.execute(SQL_DW_EXT, (ids[i:i + 2000], ids[i:i + 2000]))
                    cols = [d.name for d in cur.description]
                    for r in cur.fetchall():
                        d = dict(zip(cols, r))
                        if d["item_id"] in out:
                            out[d["item_id"]].update(d)
        except psycopg.Error as e:
            con.rollback()
            log.warning("extensao do DW indisponivel (endereco/CID): %s", str(e).splitlines()[0])
        ubs = {}
        try:
            cnes = sorted({d["nu_cnes"] for d in out.values() if d.get("nu_cnes")})
            with con.cursor() as cur:
                cur.execute(SQL_UBS, (cnes,))
                for r in cur.fetchall():
                    ubs[r[0]] = {"cep": r[1] or "", "bairro": r[2] or "", "endereco": r[3] or ""}
        except psycopg.Error as e:
            con.rollback()
            log.warning("endereco das UBS indisponivel (tb_unidade_saude): %s", str(e).splitlines()[0])
    return out, lote, ubs


def _limpa_doc(v, n):
    v = re.sub(r"\D", "", v or "")
    return v if len(v) == n else ""


@transaction.atomic
def executar():
    col = Coleta.objects.create()
    try:
        itens, rotinas = ler_extrator()
        ids = [int(i["item_id"]) for i in itens]
        dw, lote, ubs_end = ler_dw(ids)
        agora = timezone.now()

        # --- unidades e equipes
        unid = {}
        for d in dw.values():
            if d["nu_cnes"]:
                ue = ubs_end.get(d["nu_cnes"], {})
                defaults = {"nome": d["no_unidade_saude"] or d["nu_cnes"], "bairro": ue.get("bairro") or d["bairro_ubs"] or ""}
                if ue.get("endereco"):
                    defaults["endereco"] = ue["endereco"][:250]; defaults["cep"] = _limpa_doc(ue.get("cep"), 8)
                u, _ = Unidade.objects.update_or_create(cnes=d["nu_cnes"], defaults=defaults)
                unid[d["nu_cnes"]] = u
        eqp = {}
        for d in dw.values():
            if d["nu_ine"]:
                e, _ = Equipe.objects.update_or_create(ine=d["nu_ine"], defaults={"nome": d["no_equipe"] or d["nu_ine"], "unidade": unid.get(d["nu_cnes"])})
                eqp[d["nu_ine"]] = e

        # --- agrupa os atendimentos por gestante
        grupos = defaultdict(list)
        for it in itens:
            d = dw.get(int(it["item_id"]))
            if d and d["co_cidadao"]:
                chave = f"c{d['co_cidadao']}"
            else:
                chave = "p" + (_limpa_doc(it["cpf"], 11) or _limpa_doc(it["cns"], 15) or f"i{it['item_id']}")
            grupos[chave].append((it, d))

        existentes = {g.chave: g for g in Gestante.objects.all()}
        vistos = set()
        n_eventos = 0
        for chave, lst in grupos.items():
            lst.sort(key=lambda x: (x[1] or {}).get("dt_inicial_atendimento") or _iso(x[0]["dt_inicial_atendimento"]) or dt.datetime.min.replace(tzinfo=UTC))
            ult_it, ult_d = lst[-1]
            d_ref = next((d for _, d in reversed(lst) if d), None) or {}
            sits = [situacao_item(it) for it, _ in lst]
            aceitos = [it for (it, _), s in zip(lst, sits) if s[0] == "aceita"]
            if aceitos:
                situacao, motivo = "aceita", ""
                aceita_em = min(_utc(it["updated_at"]) for it in aceitos)
            else:
                situacao, motivo = sits[-1]
                aceita_em = None
            cpf = _limpa_doc(d_ref.get("cpf_cad") or ult_it["cpf"], 11) or _limpa_doc(ult_it["cpf"], 11)
            cns = _limpa_doc(d_ref.get("cns_cad") or ult_it["cns"], 15) or _limpa_doc(ult_it["cns"], 15)
            dum = _iso(ult_it["dum"])
            dum = dum.astimezone(BRT).date() if dum else None
            datas = [d["dt_inicial_atendimento"] for _, d in lst if d and d["dt_inicial_atendimento"]]
            datas = [x if x.tzinfo else x.replace(tzinfo=BRT) for x in datas]
            cids = set()
            for _, d in lst:
                if d and d.get("cids"):
                    cids.update(x.strip().upper() for x in d["cids"].split(",") if x.strip())
            hiper = any(c[:3] in ("O10", "O11", "O12", "O13", "O14", "O15", "O16") for c in cids)
            diab = any(c[:3] == "O24" for c in cids)
            multipla = any(c[:3] == "O30" for c in cids) or any((it["qtd_filhos"] or 1) > 1 for it, _ in lst)
            parto = any(c[:3] in ("O80", "O81", "O82", "O83", "O84", "Z37", "Z39") for c in cids)
            primeira = min(datas) if datas else None
            sem_capt = ((primeira.astimezone(BRT).date() - dum).days // 7) if (primeira and dum) else None
            if sem_capt is not None and not (0 <= sem_capt <= 45):
                sem_capt = None
            d_end = next((d for _, d in reversed(lst) if d and (d.get("cep") or d.get("logradouro"))), None) or {}
            campos = dict(
                co_cidadao=d_ref.get("co_cidadao"), nome=(d_ref.get("nome") or "")[:150] or "(sem nome no DW)",
                cpf=cpf, cns=cns, nascimento=d_ref.get("nascimento"),
                nome_mae=(d_ref.get("nome_mae") or "")[:150], telefone=(d_ref.get("telefone") or "")[:30],
                bairro=(d_ref.get("bairro") or "")[:100],
                tem_cns_cadastro=bool(_limpa_doc(d_ref.get("cns_cad"), 15)), tem_cpf_cadastro=bool(_limpa_doc(d_ref.get("cpf_cad"), 11)),
                dum=dum, ultimo_atendimento=max(datas) if datas else None, primeiro_atendimento=min(datas) if datas else None,
                profissional=(d_ref.get("profissional") or ult_it["professional_name"] or "")[:150],
                unidade=unid.get(d_ref.get("nu_cnes")), equipe=eqp.get(d_ref.get("nu_ine")),
                atendimentos=len(lst), atendimentos_aceitos=len(aceitos),
                situacao=situacao, motivo=motivo[:300], aceita_em=aceita_em, ativa=True,
                primeira_consulta=primeira, semanas_na_captacao=sem_capt, consultas=len(datas),
                dias_sem_consulta=(timezone.localdate() - max(datas).astimezone(BRT).date()).days if datas else None,
                risco_hipertensao=hiper, risco_diabetes=diab, gestacao_multipla=multipla, parto_registrado=parto,
                cep=_limpa_doc(d_end.get("cep"), 8), logradouro=(d_end.get("logradouro") or "")[:200].strip(), numero=(d_end.get("numero") or "")[:10],
                bairro_end=(d_end.get("bairro_end") or "")[:100],
            )
            g = existentes.get(chave)
            if g is None:
                # entrada = quando o extrator gravou o 1o atendimento dela (created_at), nao a data desta coleta
                entrada = min(_utc(it["created_at"]) for it, _ in lst) or agora
                g = Gestante(chave=chave, primeira_vista=entrada, situacao_desde=aceita_em or entrada, **campos)
                g.save()
                Evento.objects.create(gestante=g, quando=aceita_em or entrada, de="", para=situacao, detalhe=motivo[:300])
                n_eventos += 1
            else:
                anterior = g.situacao
                for k, v in campos.items():
                    setattr(g, k, v)
                if anterior != situacao:
                    Evento.objects.create(gestante=g, quando=agora, de=anterior, para=situacao, detalhe=motivo[:300])
                    g.situacao_desde = aceita_em or agora
                    n_eventos += 1
                g.save()
            vistos.add(chave)
        # gestante que saiu do recorte do extrator (DUM > 365 dias): inativa, historico preservado
        Gestante.objects.filter(ativa=True).exclude(chave__in=vistos).update(ativa=False)
        # exames do pre-natal (sifilis, HIV, hepatite B, toxoplasmose) registrados no PEC
        try:
            atualizar_exames()
        except Exception as e:  # nunca derruba a coleta
            log.warning("exames do pre-natal indisponiveis: %s", str(e).splitlines()[0])

        # --- rotinas horarias
        for r in rotinas:
            m = RE_SUMMARY.search(r["resumo"] or "")
            Rotina.objects.update_or_create(attempt_id=r["attempt_id"], defaults=dict(
                inicio=_utc(r["ini"]), fim=_utc(r["fim"]),
                enviados=int(m.group(1)) if m else 0, total=int(m.group(2)) if m else 0, erros=int(m.group(3)) if m else 0))

        # --- resumo do dia
        hoje = timezone.localdate()
        qs = Gestante.objects.filter(ativa=True)
        cont = {s: qs.filter(situacao=s).count() for s, _ in Gestante._meta.get_field("situacao").choices}
        ResumoDiario.objects.update_or_create(data=hoje, defaults=dict(
            elegiveis=qs.count(), aceitas=cont["aceita"], sem_cns=cont["sem_cns"], fora_bolsa=cont["fora_bolsa"],
            sem_cpf=cont["sem_cpf"], erro_api=cont["erro_api"], pendente=cont["pendente"],
            aceitas_no_dia=qs.filter(aceita_em__date=hoje).count()))

        col.ok, col.gestantes, col.eventos = True, len(grupos), n_eventos
        col.ultimo_lote_pec = (lote.replace(tzinfo=BRT) if lote and not lote.tzinfo else lote)
        col.mensagem = f"{len(itens)} atendimentos, {len(grupos)} gestantes, {n_eventos} eventos, {len(rotinas)} rotinas"
    except Exception as e:  # noqa: BLE001
        log.exception("coleta falhou")
        col.ok, col.mensagem = False, f"{type(e).__name__}: {e}"[:2000]
        col.fim = timezone.now()
        col.save()
        raise
    col.fim = timezone.now()
    col.save()
    return col
