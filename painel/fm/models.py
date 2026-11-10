"""Fotos (snapshots) do que o extrator e o DW dizem sobre cada gestante, historico, alertas e trilha de acesso.
O painel nunca escreve no banco do extrator nem no DW: tudo aqui e copia derivada, refeita a cada coleta."""
from django.conf import settings
from django.db import models

SITUACOES = [
    ("aceita", "Aceita pela SES-MG"),
    ("sem_cns", "Sem CNS no atendimento (erro 500)"),
    ("fora_bolsa", "Fora do Bolsa Família (erro 400)"),
    ("sem_cpf", "Sem CPF no e-SUS (erro 422)"),
    ("erro_api", "Erro da API"),
    ("pendente", "Aguardando envio"),
    ("fora_recorte", "Fora do recorte (DUM há mais de 1 ano)"),
]
ORIENTACAO = {
    "aceita": "Nenhuma ação. A gestante está no Filhos de Minas.",
    "fora_recorte": "DUM há mais de um ano: gestação fora do recorte do programa, provavelmente já encerrada. O extrator deixou de enviar e nada muda na SES-MG. Se a gestação continua, corrigir a DUM no PEC: a gestante volta ao envio em até 1 hora.",
    "sem_cns": "UBS: completar o CNS no cadastro do cidadão no PEC e-SUS (consultar o CadSUS pelo CPF; se não houver cartão, gerar o CNS). Depois do cadastro corrigido, a rotina automática reenvia em até 1 hora.",
    "fora_bolsa": "Regra do programa: a gestante não consta no Bolsa Família pelo CPF enviado. UBS: conferir o CPF no cadastro; se estiver certo, não há ação técnica (ela não é elegível ao Filhos de Minas).",
    "sem_cpf": "UBS: cadastrar o CPF da gestante no PEC e-SUS. A API exige CPF; só o CNS não basta.",
    "erro_api": "Falha temporária na API da SES-MG. A rotina tenta de novo a cada hora; se persistir por mais de 1 dia, acionar a TI.",
    "pendente": "Ainda não foi enviada. Aguardar a próxima rotina (de hora em hora).",
}


def chave_nome_unidade(nome):
    """Chave de ordenacao: tira 'Unidade de Saude', artigos (da/de/do/das/dos) e acentos; ignora maiusculas.
    Sem isso, 'Vila Militar' (V maiusculo) vinha antes de 'da Vila Celeste' e 'do Bethania'."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^(unidade (basica )?de saude|ubs|usf|esf)\s+", "", s.strip())
    s = re.sub(r"^(da|de|do|das|dos)\s+", "", s)
    return s


class Unidade(models.Model):
    cnes = models.CharField(max_length=10, unique=True)
    nome = models.CharField(max_length=150)
    bairro = models.CharField(max_length=100, blank=True)
    endereco = models.CharField(max_length=250, blank=True)     # do cadastro da unidade no PEC (tb_unidade_saude)
    cep = models.CharField(max_length=8, blank=True)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)
    geo_em = models.DateTimeField(null=True)
    geo_fonte = models.CharField(max_length=250, blank=True, default="")   # preenchido = ponto conferido (deploy/ubs-coordenadas.json); a rotina de geocodificacao nao mexe

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def nome_curto(self):
        """'Unidade de Saude do Bethania' -> 'Bethania' (para listas compactas); o nome oficial fica em `nome`."""
        import re
        s = re.sub(r"^(Unidade (B[aá]sica )?de Sa[uú]de|UBS|USF|ESF)\s+", "", (self.nome or "").strip(), flags=re.I)
        return re.sub(r"^(da|de|do|das|dos)\s+", "", s, flags=re.I) or self.nome

    @property
    def chave_ordem(self):
        return chave_nome_unidade(self.nome)


class Equipe(models.Model):
    ine = models.CharField(max_length=12, unique=True)
    nome = models.CharField(max_length=150)
    unidade = models.ForeignKey(Unidade, null=True, on_delete=models.SET_NULL, related_name="equipes")

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Gestante(models.Model):
    chave = models.CharField(max_length=40, unique=True)          # co_cidadao do DW (ou cpf/cns quando faltar)
    co_cidadao = models.BigIntegerField(null=True, db_index=True)
    nome = models.CharField(max_length=150)
    cpf = models.CharField(max_length=11, blank=True, db_index=True)
    cns = models.CharField(max_length=15, blank=True, db_index=True)
    nascimento = models.DateField(null=True)
    nome_mae = models.CharField(max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    tem_cns_cadastro = models.BooleanField(default=False)
    tem_cpf_cadastro = models.BooleanField(default=False)
    dum = models.DateField(null=True, db_index=True)
    ultimo_atendimento = models.DateTimeField(null=True, db_index=True)
    primeiro_atendimento = models.DateTimeField(null=True)
    profissional = models.CharField(max_length=150, blank=True)
    unidade = models.ForeignKey(Unidade, null=True, on_delete=models.SET_NULL, related_name="gestantes")
    equipe = models.ForeignKey(Equipe, null=True, on_delete=models.SET_NULL, related_name="gestantes")
    atendimentos = models.IntegerField(default=0)
    atendimentos_aceitos = models.IntegerField(default=0)
    situacao = models.CharField(max_length=12, choices=SITUACOES, db_index=True)
    motivo = models.CharField(max_length=300, blank=True)         # resumo da ultima resposta da API
    primeira_vista = models.DateTimeField(db_index=True)            # quando o painel viu a gestante pela 1a vez
    situacao_desde = models.DateTimeField()
    aceita_em = models.DateTimeField(null=True, db_index=True)
    ativa = models.BooleanField(default=True, db_index=True)        # sumiu do extrator (DUM > 365 d) -> False
    atualizado_em = models.DateTimeField(auto_now=True)
    # --- indicadores clinicos (do DW; so o que o extrator ja le, mais os problemas/CID do atendimento)
    primeira_consulta = models.DateTimeField(null=True)          # 1o atendimento de pre-natal registrado
    semanas_na_captacao = models.IntegerField(null=True)         # idade gestacional na 1a consulta (DUM -> 1a consulta)
    consultas = models.IntegerField(default=0)                   # atendimentos de pre-natal no recorte
    dias_sem_consulta = models.IntegerField(null=True)           # hoje - ultimo atendimento
    risco_hipertensao = models.BooleanField(default=False)       # CID O10-O16
    risco_diabetes = models.BooleanField(default=False)          # CID O24
    gestacao_multipla = models.BooleanField(default=False)       # O30x / qtd_filhos > 1
    parto_registrado = models.BooleanField(default=False)        # CID O80-O84 (parto) ou Z37/Z39 em atendimento posterior a DUM
    # --- exames do pre-natal registrados no PEC (procedimentos solicitados/avaliados a partir de 30 dias antes da DUM)
    exame_sifilis = models.BooleanField(default=False)           # VDRL ou teste rapido de sifilis
    exame_hiv = models.BooleanField(default=False)               # anti-HIV ou teste rapido de HIV
    exame_hepb = models.BooleanField(default=False)              # HBsAg
    exame_toxo = models.BooleanField(default=False)              # toxoplasmose IgG/IgM
    exames_prenatal = models.IntegerField(default=0)             # procedimentos distintos de exame no periodo
    # --- endereco (so do cadastro do cidadao; o cadastro domiciliar do DW e ofuscado) e geolocalizacao
    cep = models.CharField(max_length=8, blank=True)
    logradouro = models.CharField(max_length=200, blank=True)
    numero = models.CharField(max_length=10, blank=True)
    bairro_end = models.CharField(max_length=100, blank=True)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)
    geo_precisao = models.CharField(max_length=12, blank=True)   # endereco | cep | bairro | (vazio = sem)
    geo_em = models.DateTimeField(null=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def orientacao(self):
        return ORIENTACAO.get(self.situacao, "")

    @property
    def cpf_mascarado(self):
        return f"***.{self.cpf[3:6]}.{self.cpf[6:9]}-**" if len(self.cpf) == 11 else ""


class Evento(models.Model):
    """Mudanca de situacao de uma gestante (historico vivo, independente dos logs do extrator)."""
    gestante = models.ForeignKey(Gestante, on_delete=models.CASCADE, related_name="eventos")
    quando = models.DateTimeField(db_index=True)
    de = models.CharField(max_length=12, blank=True)
    para = models.CharField(max_length=12)
    detalhe = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-quando"]


class ConferenciaSES(models.Model):
    """Resultado da conferencia diaria (somente leitura) na API do Filhos de Minas: o que a SES-MG tem desta gestante."""
    gestante = models.OneToOneField(Gestante, on_delete=models.CASCADE, related_name="conferencia")
    verificado_em = models.DateTimeField(null=True, db_index=True)
    cadastrada = models.BooleanField(default=False)
    habilitada = models.BooleanField(default=False)
    gravidezes = models.IntegerField(default=0)
    status_gravidez = models.CharField(max_length=40, blank=True)
    dum_ses = models.DateField(null=True)
    consultas_ses = models.IntegerField(default=0)
    status_kit = models.CharField(max_length=40, blank=True)
    data_entrega_kit = models.DateField(null=True)
    divergencia = models.CharField(max_length=200, blank=True, db_index=True)
    erro = models.CharField(max_length=200, blank=True)


class SugestaoCNS(models.Model):
    """CNS encontrado em outra fonte municipal (lista importada de arquivo pelo importar_cns; o painel nunca se liga a esse
    sistema).
    E so uma dica para a UBS conferir no CadSUS e gravar no PEC; o painel nao envia nada com ele."""
    cpf = models.CharField(max_length=11, unique=True)
    cns = models.CharField(max_length=15)
    nome_fonte = models.CharField(max_length=150, blank=True)
    nascimento_fonte = models.DateField(null=True)
    status = models.CharField(max_length=40, blank=True)        # confere | conferir manualmente
    fonte = models.CharField(max_length=40, default="outra fonte")
    importado_em = models.DateTimeField(auto_now=True)

    @property
    def confere(self):
        return self.status.startswith("confere") and "manual" not in self.status


class Rotina(models.Model):
    """Uma execucao da rotina horaria do extrator (lida de module_logs por attempt_id)."""
    attempt_id = models.CharField(max_length=80, unique=True)
    inicio = models.DateTimeField(db_index=True)
    fim = models.DateTimeField(null=True)
    total = models.IntegerField(default=0)
    enviados = models.IntegerField(default=0)
    erros = models.IntegerField(default=0)

    class Meta:
        ordering = ["-inicio"]


class ResumoDiario(models.Model):
    """Foto por dia para os graficos de evolucao (gravada pela coleta, uma linha por dia, sobrescrita ate virar o dia)."""
    data = models.DateField(unique=True)
    elegiveis = models.IntegerField(default=0)
    aceitas = models.IntegerField(default=0)
    sem_cns = models.IntegerField(default=0)
    fora_bolsa = models.IntegerField(default=0)
    sem_cpf = models.IntegerField(default=0)
    erro_api = models.IntegerField(default=0)
    pendente = models.IntegerField(default=0)
    aceitas_no_dia = models.IntegerField(default=0)

    class Meta:
        ordering = ["data"]


class Coleta(models.Model):
    """Registro de cada coleta do painel (para a tela de situacao e para o alarme de 'coleta parada')."""
    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True)
    ok = models.BooleanField(default=False)
    mensagem = models.TextField(blank=True)
    gestantes = models.IntegerField(default=0)
    eventos = models.IntegerField(default=0)
    ultimo_lote_pec = models.DateTimeField(null=True)   # dt_inicial_atendimento mais recente no DW (chegada de lote)

    class Meta:
        ordering = ["-inicio"]


class Alerta(models.Model):
    """Alerta personalizado por usuario: filtro + eventos + canal. Avaliado depois de cada coleta."""
    FREQ = [("hora", "Na hora (após cada coleta, de hora em hora)"), ("dia", "Resumo diário às 08:00")]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alertas")
    nome = models.CharField(max_length=100)
    unidades = models.ManyToManyField(Unidade, blank=True)
    situacoes = models.JSONField(default=list)       # ex.: ["sem_cns", "sem_cpf"]
    eventos = models.JSONField(default=list)         # "nova_pendente", "resolvida", "rotina_falhou", "lote_pec", "envio_zero"
    por_email = models.BooleanField(default=True)
    por_telegram = models.BooleanField(default=False)
    destino = models.CharField(max_length=200, blank=True)   # e-mail; vazio = e-mail do usuario no SSO. Telegram vem do vinculo
    frequencia = models.CharField(max_length=5, choices=FREQ, default="hora")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_envio = models.DateTimeField(null=True)
    estado = models.JSONField(default=dict)          # memoria do avaliador: ultimo lote visto, ultimo aviso de rotina/zero

    class Meta:
        ordering = ["nome"]


class VinculoTelegram(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram")
    codigo = models.CharField(max_length=12, db_index=True)
    chat_id = models.CharField(max_length=30, blank=True)
    verificado_em = models.DateTimeField(null=True)
    criado_em = models.DateTimeField(auto_now_add=True)


class Acesso(models.Model):
    """Trilha: quem viu dado nominal, revelou CPF, exportou (LGPD)."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    quando = models.DateTimeField(auto_now_add=True, db_index=True)
    acao = models.CharField(max_length=30, db_index=True)   # lista, detalhe, revelar_cpf, exportar, login, alerta
    detalhe = models.CharField(max_length=500, blank=True)
    ip = models.GenericIPAddressField(null=True)

    class Meta:
        ordering = ["-quando"]


class Perfil(models.Model):
    """Origem do usuario (local ou sso) e grupos recebidos do SSO no ultimo login (definem o papel)."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    grupos = models.JSONField(default=list)
    origem = models.CharField(max_length=10, default="local")
    atualizado_em = models.DateTimeField(auto_now=True)


class GeoCache(models.Model):
    """Resultado de geocodificacao por chave (cep+numero, ou nome da UBS), para nao repetir consultas externas."""
    chave = models.CharField(max_length=200, unique=True)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)
    precisao = models.CharField(max_length=12, blank=True)
    fonte = models.CharField(max_length=20, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
