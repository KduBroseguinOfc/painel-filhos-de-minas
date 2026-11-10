from django.core.management.base import BaseCommand
from fm.coleta import executar

class Command(BaseCommand):
    help = "Le o extrator (somente leitura) e o DW e atualiza a foto das gestantes"
    def handle(self, *args, **opts):
        c = executar()
        self.stdout.write(f"coleta {c.id}: {c.mensagem} ({(c.fim - c.inicio).total_seconds():.0f} s)")
