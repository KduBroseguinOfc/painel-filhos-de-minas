"""Conferencia diaria com a API do Filhos de Minas (SES-MG), SOMENTE LEITURA: para cada gestante aceita ou pendente
com gestacao em curso, consulta o cadastro (GET /gestante/{cpf}/list) e as gravidezes (GET /gestante/{cpf}/consultas)
com a conta do municipio (a mesma do extrator) e guarda o resultado em ConferenciaSES: cadastrada, habilitada,
situacao da gravidez, consultas registradas la, kit. Divergencias (painel diz uma coisa, SES-MG outra) ficam marcadas.
Ritmo: 1 gestante por segundo (duas chamadas), para nao pesar na API deles. Uso: manage.py conferir_ses [--max N] [--so-aceitas]"""
import datetime as dt, json, time, urllib.error, urllib.parse, urllib.request
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from fm.models import ConferenciaSES, Gestante
from fm.indicadores import PENDENTES


def _data(s):
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime((s or "")[:10], f).date()
        except ValueError:
            pass
    return None


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("--max", type=int, default=0, help="limita a N gestantes (teste)")
        p.add_argument("--so-aceitas", action="store_true")

    def handle(self, *a, **o):
        base = (settings.SES_API_URL or "").rstrip("/")
        if not (base and settings.SES_API_USER and settings.SES_API_PASSWORD):
            self.stderr.write("SES_API_URL/USER/PASSWORD nao configurados"); return
        corpo = urllib.parse.urlencode({"username": settings.SES_API_USER, "password": settings.SES_API_PASSWORD}).encode()
        tok = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/auth/token", data=corpo, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=30).read())
        cab = {"Authorization": "Bearer " + (tok.get("access_token") or tok.get("token") or ""), "Accept": "application/json"}

        def get(rota):
            try:
                with urllib.request.urlopen(urllib.request.Request(base + rota, headers=cab), timeout=30) as r:
                    return r.status, json.loads(r.read() or b"null")
            except urllib.error.HTTPError as e:
                return e.code, None
            except Exception as e:  # rede
                return 0, str(e)[:120]

        hoje = timezone.localdate(); agora = timezone.now()
        qs = Gestante.objects.filter(ativa=True).exclude(cpf="")
        if o["so_aceitas"]:
            qs = qs.filter(situacao="aceita")
        else:
            qs = qs.filter(Q(situacao="aceita") | Q(situacao__in=PENDENTES, dum__gte=hoje - dt.timedelta(days=294)) | Q(situacao__in=PENDENTES, dum=None))
        qs = qs.order_by("-aceita_em", "id")
        if o["max"]:
            qs = qs[:o["max"]]
        n = cad = div = err = 0
        for g in qs:
            n += 1
            st, dados = get(f"/gestante/{g.cpf}/list")
            c, _ = ConferenciaSES.objects.get_or_create(gestante=g)
            c.verificado_em = agora; c.erro = ""; c.divergencia = ""
            if st == 200 and isinstance(dados, dict):
                c.cadastrada = True; c.habilitada = bool(dados.get("habilitado"))
                st2, grav = get(f"/gestante/{g.cpf}/consultas")
                c.gravidezes = len(grav) if isinstance(grav, list) else 0
                atual = None
                if isinstance(grav, list) and grav:
                    em_and = [x for x in grav if (x.get("status_gravidez") or "").lower().startswith("em and")]
                    atual = (em_and or grav)[-1]
                if atual:
                    c.status_gravidez = (atual.get("status_gravidez") or "")[:40]
                    c.dum_ses = _data(atual.get("dum")); c.consultas_ses = len(atual.get("consultas") or [])
                    c.status_kit = (atual.get("status_kit") or "")[:40]; c.data_entrega_kit = _data(atual.get("data_entrega_kits"))
                else:
                    c.status_gravidez = ""; c.dum_ses = None; c.consultas_ses = 0; c.status_kit = ""; c.data_entrega_kit = None
                cad += 1
            elif st == 404:
                c.cadastrada = False; c.habilitada = False; c.gravidezes = 0; c.consultas_ses = 0
                c.status_gravidez = ""; c.status_kit = ""; c.dum_ses = None; c.data_entrega_kit = None
            else:
                c.erro = f"HTTP {st} {dados if isinstance(dados, str) else ''}"[:200]; err += 1
            if not c.erro:
                if g.situacao == "aceita" and not c.cadastrada:
                    c.divergencia = "painel: aceita; SES-MG: sem cadastro"
                elif g.situacao != "aceita" and c.cadastrada:
                    c.divergencia = "painel: pendente; SES-MG: cadastrada"
                elif c.cadastrada and c.dum_ses and g.dum and c.dum_ses != g.dum:
                    c.divergencia = f"DUM difere: painel {g.dum:%d/%m/%Y}, SES-MG {c.dum_ses:%d/%m/%Y}"
                elif c.cadastrada and c.consultas_ses < g.atendimentos_aceitos:
                    c.divergencia = f"consultas: {g.atendimentos_aceitos} aceitas no envio, {c.consultas_ses} na SES-MG"
                if c.divergencia:
                    div += 1
            c.save()
            time.sleep(1.0)
        self.stdout.write(f"conferencia SES-MG: {n} gestantes, {cad} cadastradas la, {div} divergencias, {err} erros de consulta")
