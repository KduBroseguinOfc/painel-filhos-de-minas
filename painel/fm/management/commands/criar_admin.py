"""Cria (ou redefine a senha de) um administrador local com senha aleatoria, impressa UMA vez na saida.
Uso: manage.py criar_admin [--usuario admin] [--redefinir]. Usado pelo instalador; sem --redefinir, usuario existente e mantido."""
import secrets
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from fm.models import Perfil


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("--usuario", default="admin")
        p.add_argument("--redefinir", action="store_true")

    def handle(self, *a, **o):
        nome = o["usuario"].strip().lower()
        u = User.objects.filter(username=nome).first()
        if u and not o["redefinir"]:
            self.stdout.write(f"usuario {nome} ja existe (senha mantida; use --redefinir para gerar outra)")
            return
        senha = secrets.token_urlsafe(14)
        if not u:
            u = User(username=nome, first_name="Administrador", is_active=True)
        u.is_superuser = True; u.is_staff = False; u.is_active = True
        u.set_password(senha); u.save()
        Perfil.objects.update_or_create(usuario=u, defaults={"origem": "local"})
        self.stdout.write(f"USUARIO={nome}\nSENHA={senha}")
