"""
Envio de alertas via Telegram Bot API — novo cadastro pendente (com botões
Aprovar/Reprovar), tentativa de uso em outro PC (cópia). Toda requisição roda em thread separada com timeout curto: se o PC
estiver offline ou o Telegram fora do ar, a interface NUNCA trava — a
mensagem simplesmente não sai (falha silenciosa).
"""
import json
import logging
import os
import threading
import time

import requests
import telebot  # pip install pyTelegramBotAPI

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR
from models.usuario_dao import UsuarioDAO, STATUS_APROVADO, STATUS_BLOQUEADO

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
_URL_ENVIO = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

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
                # Ex.: '_' em nomes (dev_master) quebra o Markdown -> reenvia como texto puro.
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
    base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    me = requests.get(f"{base}/getMe", timeout=10).json()
    print("BOT:", me)
    chat = requests.get(f"{base}/getChat", params={"chat_id": TELEGRAM_CHAT_ID},
                        timeout=10).json()
    print("CHAT_ID configurado:", TELEGRAM_CHAT_ID)
    print("CHAT destino:", chat)


@bot.message_handler(func=lambda m: True)
def _responder_chat_id(message):
    """Qualquer mensagem enviada ao bot devolve o chat_id correto."""
    _log.info("Mensagem recebida do chat_id=%s", message.chat.id)
    try:
        bot.reply_to(message, f"Seu chat_id é: {message.chat.id}")
    except Exception as e:
        _log.error("Falha ao responder chat_id: %r", e)


def notificar_novo_cadastro(usuario: str, nome_pc: str, win_user: str, hwid: str):
    texto = (
        "🆕 *NOVO CADASTRO SOLAZ APP*\n"
        f"• *Usuário:* {usuario}\n"
        f"• *Nome do PC:* {nome_pc}\n"
        f"• *Usuário Win:* {win_user}\n"
        f"• *HWID:* {hwid}\n"
        f"• *Status:* Aguardando Aprovação"
    )
    teclado = None
    # callback_data tem limite de 64 bytes; usuários longos demais ficam sem botão.
    if len(f"cad_reprovar_{usuario}".encode("utf-8")) <= 64:
        teclado = {"inline_keyboard": [[
            {"text": "✅ Aprovar", "callback_data": f"cad_aprovar_{usuario}"},
            {"text": "❌ Reprovar", "callback_data": f"cad_reprovar_{usuario}"},
        ]]}
    _enviar_em_thread(texto, teclado)


def alertar_uso_em_outro_pc(usuario: str, nome_pc_original: str, nome_pc_atual: str,
                             win_user_atual: str, hwid_atual: str):
    texto = (
        "🚨 *ALERTA DE SEGURANÇA: USO EM OUTRO PC DETECTADO!*\n"
        f"• *Usuário Tentando Logar:* {usuario}\n"
        f"• *PC Original Cadastrado:* {nome_pc_original}\n"
        f"• *PC Atual Detectado:* {nome_pc_atual}\n"
        f"• *Usuário Win Atual:* {win_user_atual}\n"
        f"• *HWID Atual:* {hwid_atual}\n"
        f"• *Ação Tomada:* Acesso bloqueado automaticamente pelo sistema."
    )
    _enviar_em_thread(texto)


_ACOES_CADASTRO = {
    "aprovar": (STATUS_APROVADO, "✅", "APROVADO"),
    "reprovar": (STATUS_BLOQUEADO, "❌", "REPROVADO (bloqueado)"),
}


@bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("cad_"))
def _callback_cadastro(call):
    bot.answer_callback_query(call.id, text="Processando...")
    _log.info("Clique recebido: %s", call.data)

    chat_id = call.message.chat.id
    message_id = call.message.message_id
    try:
        if str(chat_id) != str(TELEGRAM_CHAT_ID):
            return
        _, acao, usuario = call.data.split("_", 2)
        status, icone, rotulo = _ACOES_CADASTRO[acao]

        dao = UsuarioDAO()
        registro = dao.buscar_por_usuario(usuario)
        if registro:
            dao.atualizar_status(registro["id"], status)
            decisao = f"{icone} Acesso de '{usuario}' {rotulo}"
        else:
            decisao = f"⚠️ Usuário '{usuario}' não encontrado (já excluído?)"

        # Mantém os dados originais e troca os botões pela decisão.
        bot.edit_message_text(f"{call.message.text}\n\n{decisao}", chat_id, message_id)
    except Exception:
        _log.exception("Erro ao processar clique %s", call.data)
        try:
            bot.edit_message_text("⚠️ Erro ao processar a solicitação. Tente novamente.",
                                  chat_id, message_id)
        except Exception:
            pass


_polling_thread = None


def iniciar_bot_polling():
    """Inicia (uma única vez) o recebimento de cliques em thread daemon.
    Chamar na inicialização do app. Falhas de rede são tratadas pelo
    infinite_polling (reconecta sozinho) e nunca travam a interface."""
    global _polling_thread
    if _polling_thread and _polling_thread.is_alive():
        return

    _log.info("Iniciando polling do bot...")

    def worker():
        # infinite_polling só existe em versões recentes do pyTelegramBotAPI;
        # em versões antigas usamos polling() dentro de um loop de reconexão.
        if hasattr(bot, "infinite_polling"):
            try:
                bot.infinite_polling(timeout=10, long_polling_timeout=10, skip_pending=True)
            except Exception as e:
                _log.error("Polling do Telegram encerrou: %r", e)
            return
        while True:
            try:
                bot.polling(none_stop=True, timeout=10)
            except Exception as e:
                _log.error("Polling do Telegram caiu (reconectando em 5s): %r", e)
            time.sleep(5)

    _polling_thread = threading.Thread(target=worker, daemon=True)
    _polling_thread.start()
