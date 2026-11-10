from django.core.management.base import BaseCommand
from fm.telegram import configurar_bot, ouvir

class Command(BaseCommand):
    help = "Ouve o bot do Telegram (long polling) e trata /vincular e /parar"
    def handle(self, *a, **o):
        try:
            configurar_bot()
        except Exception as e:  # noqa: BLE001
            self.stderr.write(f"configurar_bot: {e}")
        ouvir()
