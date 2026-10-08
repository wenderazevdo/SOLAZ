"""
Envio de alertas via Telegram Bot API — novo cadastro pendente (com botões
Aprovar/Reprovar), tentativa de uso em outro PC (cópia). Toda requisição roda
em thread separada com timeout curto: se o PC estiver offline ou o Telegram
fora do ar, a interface NUNCA trava — a mensagem simplesmente não sai
(falha silenciosa).

IMPORTANTE: o clique nos botões Aprovar/Reprovar NÃO é mais tratado aqui. As
contas agora ficam no Supabase e só o master (ou o servidor) pode alterar o
status, então o clique chega por webhook a uma Edge Function
(supabase/functions/telegram-aprovacao/index.ts), que atualiza o perfil com
permissão de servidor. Por isso o app não faz mais polling do bot.
"""
import json
import logging
import os
import threading

import requests
import telebot  # pip install pyTelegramBotAPI

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR

_log = logging.getLogger("telegram")
_log.setLevel(logging.INFO)
if not _log.handlers:
    # Log em arquivo na pasta de dados da aplicação (DATA_DIR) + console.
    # Se a pasta não for gravável, segue só com o console (nunca derruba o app).
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        _arq = logging.FileHandler(os.path.join(DATA_DIR, "telegram_log.txt"),
                                   encoding="utf-8")
        _arq.setFormatter(_fmt)
        _log.addHandler(_arq)
    except OSError:
        pass
    _con = logging.StreamHandler()
    _con.setFormatter(_fmt)
    _log.addHandler(_con)
_TIMEOUT_SEGUNDOS = 3
_BASE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_URL_ENVIO = f"{_BASE_API}/sendMessage"

# Mantido só por compatibilidade com main.py (bot.stop_polling() ao fechar).
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)


def _md(valor) -> str:
    """Escapa caracteres especiais do Markdown (legado) do Telegram, para que
    nomes como 'dev_master' ou e-mails não quebrem a mensagem."""
    texto = str(valor) if valor not in (None, "") else "—"
    for ch in ("_", "*", "`", "["):
        texto = texto.replace(ch, "\\" + ch)
    return texto


def _enviar_em_thread(texto: str, teclado: dict = None):
    _log.info("Enviando alerta: %s", texto.splitlines()[0])

    def worker():
        try:
            dados = {"chat_id": TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "Markdown"}
            if teclado:
                dados["reply_markup"] = json.dumps(teclado)
            r = requests.post(_URL_ENVIO, data=dados, timeout=_TIMEOUT_SEGUNDOS)
            if r.status_code != 200:
                _log.warning("Telegram recusou (Markdown): %s %s", r.status_code, r.text)
                # Último recurso: reenvia como texto puro.
                dados.pop("parse_mode")
                r = requests.post(_URL_ENVIO, data=dados, timeout=_TIMEOUT_SEGUNDOS)
                if r.status_code != 200:
                    _log.error("Telegram recusou (texto puro): %s %s", r.status_code, r.text)
                    return
            _log.info("Alerta enviado com sucesso.")
        except Exception as e:
            _log.error("Falha ao enviar mensagem ao Telegram: %r", e)  # UI nunca trava

    threading.Thread(target=worker, daemon=True).start()


def testar_envio():
    """Diagnóstico: chama no terminal (python -c) e mostra o erro real."""
    r = requests.post(_URL_ENVIO, data={"chat_id": TELEGRAM_CHAT_ID, "text": "teste Solaz"},
                      timeout=10)
    print(r.status_code, r.text)


def diagnosticar():
    """Mostra QUAL bot e QUAL chat estão configurados (rodar no terminal)."""
    me = requests.get(f"{_BASE_API}/getMe", timeout=10).json()
    print("BOT:", me)
    chat = requests.get(f"{_BASE_API}/getChat", params={"chat_id": TELEGRAM_CHAT_ID},
                        timeout=10).json()
    print("CHAT_ID configurado:", TELEGRAM_CHAT_ID)
    print("CHAT destino:", chat)
    print("WEBHOOK:", requests.get(f"{_BASE_API}/getWebhookInfo", timeout=10).json())


def configurar_webhook(url: str, secret: str):
    """Liga o webhook do bot na Edge Function (rodar UMA vez, no terminal).
    `secret` precisa ser igual ao segredo TELEGRAM_WEBHOOK_SECRET da função."""
    r = requests.post(
        f"{_BASE_API}/setWebhook",
        data={"url": url, "secret_token": secret, "allowed_updates": json.dumps(["callback_query"]),
              "drop_pending_updates": "true"},
        timeout=15,
    )
    print(r.status_code, r.text)


def remover_webhook():
    r = requests.post(f"{_BASE_API}/deleteWebhook", timeout=15)
    print(r.status_code, r.text)


def notificar_novo_cadastro(usuario: str, nome_pc: str, win_user: str, hwid: str,
                            email: str = "", user_id: str = None):
    """Avisa o dev de um cadastro pendente. Os botões carregam o UUID da conta
    (callback_data tem limite de 64 bytes: 'cad_reprovar_' + 36 = 49)."""
    linhas = [
        "🆕 *NOVO CADASTRO SOLAZ APP*",
        f"• *Usuário:* {_md(usuario)}",
    ]
    if email:
        linhas.append(f"• *E-mail:* {_md(email)}")
    linhas += [
        f"• *Nome do PC:* {_md(nome_pc)}",
        f"• *Usuário Win:* {_md(win_user)}",
        f"• *HWID:* {_md(hwid)}",
        "• *Status:* Aguardando Aprovação",
    ]
    teclado = None
    if user_id:
        teclado = {"inline_keyboard": [[
            {"text": "✅ Aprovar", "callback_data": f"cad_aprovar_{user_id}"},
            {"text": "❌ Reprovar", "callback_data": f"cad_reprovar_{user_id}"},
        ]]}
    _enviar_em_thread("\n".join(linhas), teclado)


def alertar_uso_em_outro_pc(usuario: str, nome_pc_original: str, nome_pc_atual: str,
                             win_user_atual: str, hwid_atual: str):
    texto = (
        "🚨 *ALERTA DE SEGURANÇA: USO EM OUTRO PC DETECTADO!*\n"
        f"• *Usuário Tentando Logar:* {_md(usuario)}\n"
        f"• *PC Original Cadastrado:* {_md(nome_pc_original)}\n"
        f"• *PC Atual Detectado:* {_md(nome_pc_atual)}\n"
        f"• *Usuário Win Atual:* {_md(win_user_atual)}\n"
        f"• *HWID Atual:* {_md(hwid_atual)}\n"
        "• *Ação Tomada:* Acesso bloqueado automaticamente pelo sistema."
    )
    _enviar_em_thread(texto)


def iniciar_bot_polling():
    """Mantida só para main.py continuar funcionando. O app NÃO faz mais
    polling: com webhook ativo o Telegram recusa getUpdates, e o clique nos
    botões é tratado pela Edge Function 'telegram-aprovacao'."""
    _log.info("Aprovação pelo Telegram via webhook (Edge Function); sem polling no app.")
