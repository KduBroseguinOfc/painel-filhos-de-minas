from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from .models import SITUACOES, Alerta, Unidade

EVENTOS = [
    ("nova_pendente", "Gestante nova entrou pendente no meu recorte"),
    ("resolvida", "Gestante pendente foi aceita pela SES-MG"),
    ("envio_zero", "Rotina terminou com 0 aceites havendo pendentes (no máximo 1 aviso por dia)"),
    ("rotina_falhou", "Rotina do extrator não rodou ou a coleta falhou (no máximo 1 aviso a cada 6 h)"),
    ("lote_pec", "Lote novo do PEC importado (gestantes novas a caminho)"),
]


class AlertaForm(forms.ModelForm):
    situacoes = forms.MultipleChoiceField(choices=SITUACOES, required=False, widget=forms.CheckboxSelectMultiple, label="Situações (vazio = todas)")
    eventos = forms.MultipleChoiceField(choices=EVENTOS, widget=forms.CheckboxSelectMultiple, label="Avisar quando")

    class Meta:
        model = Alerta
        fields = ["nome", "unidades", "situacoes", "eventos", "por_email", "destino", "por_telegram", "frequencia", "ativo"]
        widgets = {"unidades": forms.CheckboxSelectMultiple, "frequencia": forms.RadioSelect}
        labels = {"nome": "Nome do alerta", "unidades": "Unidades (vazio = todas que você pode ver)", "por_email": "E-mail",
                  "destino": "E-mail de destino", "por_telegram": "Telegram", "frequencia": "Frequência", "ativo": "Alerta ativo"}

    def __init__(self, *a, unidades_qs=None, usuario=None, **kw):
        super().__init__(*a, **kw)
        self.usuario = usuario
        qs = unidades_qs if unidades_qs is not None else Unidade.objects.all()
        ids = [u.id for u in sorted(qs, key=lambda u: u.chave_ordem)]
        self.fields["unidades"].queryset = Unidade.objects.filter(id__in=ids)
        self.fields["unidades"].label_from_instance = lambda u: u.nome
        # ordem por nome "limpo" (sem 'Unidade de Saude' e artigos)
        from django.db.models import Case, When, IntegerField
        self.fields["unidades"].queryset = self.fields["unidades"].queryset.order_by(Case(*[When(id=i, then=n) for n, i in enumerate(ids)], output_field=IntegerField()))
        self.fields["destino"].widget.attrs["placeholder"] = (usuario.email if usuario and usuario.email else ("nome@" + settings.EMAIL_DOMINIOS[0] if settings.EMAIL_DOMINIOS else "nome@exemplo.gov.br"))
        v = getattr(usuario, "telegram", None) if usuario else None
        self.telegram_vinculado = bool(v and v.chat_id)
        self.telegram_codigo = v.codigo if v and not v.chat_id else ""

    def clean(self):
        d = super().clean()
        if not d.get("por_email") and not d.get("por_telegram"):
            self.add_error("por_email", "Marque pelo menos um canal: e-mail ou Telegram.")
        if d.get("por_telegram") and not self.telegram_vinculado:
            self.add_error("por_telegram", "Seu Telegram ainda não está vinculado. Vincule (abaixo) e salve de novo.")
        dest = (d.get("destino") or "").strip()
        if d.get("por_email") and not dest and not (self.usuario and self.usuario.email):
            self.add_error("destino", "Informe o e-mail de destino.")
        if dest and settings.EMAIL_DOMINIOS and not any(dest.lower().endswith("@" + d.lower()) for d in settings.EMAIL_DOMINIOS):
            self.add_error("destino", "Só e-mail institucional (" + ", ".join("@" + d for d in settings.EMAIL_DOMINIOS) + ").")
        return d


PAPEIS = [("visualizacao", "Visualização (vê todas as telas)"), ("administrador", "Administrador (vê tudo, gerencia usuários e a trilha de acesso)")]


class UsuarioForm(forms.ModelForm):
    """Usuario local. A senha nao e digitada: o painel gera uma e mostra uma unica vez (criar ou redefinir)."""
    papel = forms.ChoiceField(choices=PAPEIS, widget=forms.RadioSelect, label="Papel", initial="visualizacao")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"username": "Usuário (login)", "first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail", "is_active": "Ativo"}
        help_texts = {"username": "Letras, números e . _ -"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:
            self.fields["papel"].initial = "administrador" if self.instance.is_superuser else "visualizacao"

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
