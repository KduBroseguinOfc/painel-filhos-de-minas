from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Envia um e-mail de teste do painel (confere SMTP/credencial)"
    def add_arguments(self, p):
        p.add_argument("destino")
    def handle(self, *a, **o):
        n = send_mail(f"{settings.EMAIL_SUBJECT_PREFIX}teste de envio", "Este é um teste de envio do Painel Filhos de Minas. Se chegou, o remetente dos alertas está funcionando.\n\n" + settings.URL_PUBLICA, None, [o["destino"]])
        self.stdout.write(f"enviado: {n}")
