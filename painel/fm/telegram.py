"""Telegram dos alertas: robo do municipio (TELEGRAM_BOT_TOKEN/TELEGRAM_BOT_NOME no ambiente). Vinculo por codigo: o usuario pega o codigo na tela
'Meus alertas > Telegram' e manda `/vincular CODIGO` ao bot; o painel grava o chat_id e confirma. Envio: sendMessage.
Sem webhook: long polling (getUpdates) num servico systemd, porque o servidor nao recebe conexao da internet."""
import html
import logging
import time

import requests
from django.conf import settings
from django.utils import timezone

from .models import Acesso, VinculoTelegram

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{metodo}"


def _chamar(metodo, **params):
    r = requests.post(API.format(token=settings.TELEGRAM_BOT_TOKEN, metodo=metodo), json=params, timeout=35)
    d = r.json()
    if not d.get("ok"):
        raise RuntimeError(f"telegram {metodo}: {d.get('description')}")
    return d["result"]


def enviar(chat_id, texto_html):
    return _chamar("sendMessage", chat_id=chat_id, text=texto_html, parse_mode="HTML", disable_web_page_preview=True)


AJUDA = (f"Sou o robô de avisos do <b>Painel Filhos de Minas</b> ({settings.ORGAO} de {settings.MUNICIPIO}).\n"
         "Para receber alertas aqui: no painel, abra <b>Meus alertas → Telegram</b>, copie o código e envie\n<code>/vincular CODIGO</code>\n"
         "Para parar: <code>/parar</code>")


def tratar(msg):
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id"))
    texto = (msg.get("text") or "").strip()
    partes = texto.split()
    cmd = partes[0].lower().split("@")[0] if partes else ""
    if cmd == "/vincular" and len(partes) >= 2:
        cod = partes[1].strip().upper()
        v = VinculoTelegram.objects.filter(codigo=cod, chat_id="").select_related("usuario").first()
        if not v:
            enviar(chat_id, "Código inválido ou já usado. Gere outro na tela <b>Meus alertas → Telegram</b> do painel.")
            return
        VinculoTelegram.objects.filter(chat_id=chat_id).exclude(pk=v.pk).update(chat_id="", verificado_em=None)
        v.chat_id, v.verificado_em = chat_id, timezone.now()
        v.save()
        Acesso.objects.create(usuario=v.usuario, acao="telegram", detalhe=f"vinculado chat={chat_id} nome={html.escape(chat.get('first_name', ''))[:60]}")
        enviar(chat_id, f"Pronto, <b>{html.escape(v.usuario.get_full_name() or v.usuario.username)}</b>: este Telegram está vinculado ao seu usuário do painel. "
                        "Os alertas que você cadastrar com canal Telegram chegarão aqui.")
    elif cmd == "/parar":
        n = VinculoTelegram.objects.filter(chat_id=chat_id).update(chat_id="", verificado_em=None)
        enviar(chat_id, "Vínculo removido. Você não receberá mais alertas aqui." if n else "Este Telegram não estava vinculado.")
    else:
        enviar(chat_id, AJUDA)


def ouvir():
    """Long polling. Roda como servico; cada ciclo espera ate 30 s por mensagens novas."""
    offset = None
    log.info("telegram: ouvindo como %s", settings.TELEGRAM_BOT_NOME)
    while True:
        try:
            for upd in _chamar("getUpdates", timeout=30, offset=offset, allowed_updates=["message"]):
                offset = upd["update_id"] + 1
                if "message" in upd:
                    try:
                        tratar(upd["message"])
                    except Exception:  # noqa: BLE001
                        log.exception("telegram: falha ao tratar mensagem")
        except Exception as e:  # noqa: BLE001
            log.warning("telegram: %s", e)
            time.sleep(10)


def configurar_bot():
    _chamar("setMyCommands", commands=[{"command": "vincular", "description": "Vincular este Telegram ao painel (envie: /vincular CODIGO)"},
                                       {"command": "parar", "description": "Parar de receber alertas aqui"},
                                       {"command": "ajuda", "description": "Como funciona"}])
    _chamar("setMyDescription", description=f"Avisos do Painel Filhos de Minas ({settings.ORGAO} de {settings.MUNICIPIO}). Vincule pelo código da tela Meus alertas → Telegram.")
    _chamar("setMyShortDescription", short_description=f"Avisos do Painel Filhos de Minas — {settings.MUNICIPIO}")
