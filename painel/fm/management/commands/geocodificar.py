from django.core.management.base import BaseCommand
from fm.geo import rodar

class Command(BaseCommand):
    help = "Geocodifica UBS e gestantes com endereco (Nominatim, 1 consulta/s, cache local)"
    def add_arguments(self, p):
        p.add_argument("--limite", type=int, default=300)
    def handle(self, *a, **o):
        f, ok = rodar(o["limite"])
        self.stdout.write(f"geocodificados: {ok}/{f}")
