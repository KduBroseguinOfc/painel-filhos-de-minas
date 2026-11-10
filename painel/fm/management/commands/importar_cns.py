"""Importa a lista de CNS encontrados em outra fonte (arquivo separado por ; gerado pelo cruzamento
com outro sistema do municipio) como SUGESTAO para a UBS conferir no CadSUS. O painel nunca se liga a esse outro sistema. Uso: manage.py importar_cns <arquivo.txt>
Formato: cabecalho livre ate a linha que comeca com 'UBS;Equipe;'; colunas: UBS;Equipe;Nome (PEC);CPF;Nascimento (PEC);DUM;
Situacao;CNS (fonte);Nome (fonte);Nascimento (fonte);Status."""
import datetime as dt, re, time
from django.core.management.base import BaseCommand
from django.db import OperationalError, transaction
from fm.models import SugestaoCNS


def cns_ok(c): return bool(c) and len(c) == 15 and c.isdigit() and sum(int(c[i]) * (15 - i) for i in range(15)) % 11 == 0


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("arquivo"); p.add_argument("--fonte", default="outra fonte")

    def handle(self, *a, **o):
        n = novos = atualizados = ignorados = 0; cab = None; registros = []
        for l in open(o["arquivo"], encoding="utf-8"):
            l = l.rstrip("\n")
            if cab is None:
                if l.startswith("UBS;Equipe;"): cab = l.split(";")
                continue
            c = l.split(";")
            if len(c) < 11: continue
            n += 1
            # a coluna "Situacao" pode conter ';' no texto: localiza o CNS pela validade, a partir da 8a coluna
            cpf = re.sub(r"\D", "", c[3])
            i = next((k for k in range(7, len(c)) if cns_ok(c[k].strip())), None)
            if len(cpf) != 11 or i is None:
                ignorados += 1; continue
            cns = c[i].strip(); nome = c[i + 1][:150] if i + 1 < len(c) else ""; status = c[-1][:40]
            nasc = None
            try: nasc = dt.date.fromisoformat(c[i + 2][:10])
            except (ValueError, IndexError): pass
            registros.append((cpf, {"cns": cns, "nome_fonte": nome, "nascimento_fonte": nasc, "status": status, "fonte": o["fonte"]}))
        # grava tudo numa transacao so (uma unica espera pelo bloqueio do SQLite), com repeticao se o banco estiver ocupado
        for tentativa in range(6):
            try:
                with transaction.atomic():
                    for cpf, campos in registros:
                        obj = SugestaoCNS.objects.filter(cpf=cpf).first()
                        if obj:
                            for k, v in campos.items(): setattr(obj, k, v)
                            obj.save(); atualizados += 1
                        else:
                            SugestaoCNS.objects.create(cpf=cpf, **campos); novos += 1
                break
            except OperationalError as e:
                novos = atualizados = 0
                if "locked" not in str(e) or tentativa == 5: raise
                time.sleep(10)
        self.stdout.write(f"linhas {n}: {novos} novas, {atualizados} atualizadas, {ignorados} ignoradas (CPF/CNS invalido)")
