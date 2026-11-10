from django.core.management.base import BaseCommand
from fm.alertas import rodar

class Command(BaseCommand):
    help = "Avalia os alertas dos usuarios e envia e-mails (modo hora | dia)"
    def add_arguments(self, p):
        p.add_argument("modo", choices=["hora", "dia"])
    def handle(self, *a, **o):
        self.stdout.write(f"alertas ({o['modo']}): {rodar(o['modo'])} enviado(s)")
