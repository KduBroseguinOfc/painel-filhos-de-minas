"""Aplica as coordenadas conferidas das UBS (deploy/ubs-coordenadas.json, instalado em /etc/painel-filhosdeminas/ pelo deploy.sh) e as protege da geocodificacao automatica.
Uso: manage.py fixar_ubs [caminho.json]. Unidade do arquivo que nao existe no painel e apenas avisada."""
import json, os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from fm.models import Unidade


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("arquivo", nargs="?", default="/etc/painel-filhosdeminas/ubs-coordenadas.json")

    def handle(self, *a, **o):
        d = json.load(open(o["arquivo"], encoding="utf-8"))
        n = 0
        for u in d["unidades"]:
            q = Unidade.objects.filter(cnes=u["cnes"])
            if not q.exists():
                self.stdout.write(f"  sem unidade no painel: {u['cnes']} {u['nome']}"); continue
            fonte = u["fonte"] + (f" | CONFERIR: {u['conferir']}" if u.get("conferir") else "")
            q.update(lat=u["lat"], lon=u["lon"], geo_em=timezone.now(), geo_fonte=fonte[:250]); n += 1
        self.stdout.write(f"{n} unidades com coordenada conferida")
