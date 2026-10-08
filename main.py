"""
Ponto de entrada da aplicação.

Fluxo: trava de instância única -> backup automático do banco -> inicializa o
banco de dados SQLite -> inicia o bot do Telegram em segundo plano -> exibe a
tela de Login (com cadastro de conta e trava por HWID) -> ao autenticar com
sucesso, abre a Janela Principal — em modo normal ou, se a conta for a Master
(dev_master), com o Painel do Desenvolvedor liberado.

Resiliência: todos os erros/avisos vão para data/solaz_app.log (com rotação) e
qualquer erro não tratado — inclusive em botões/callbacks da interface — vira
um aviso amigável em vez de fechar o programa abruptamente.
"""
import atexit
import logging
import os
import socket
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler

from config import DATA_DIR

# ---------------------------------------------------------------------------
# Logs globais
# ---------------------------------------------------------------------------
LOG_PATH = os.path.join(DATA_DIR, "solaz_app.log")
_LOG_MAX_BYTES = 1_000_000     # ~1 MB por arquivo
_LOG_BACKUPS = 3               # solaz_app.log.1 ... .3

_log = logging.getLogger("solaz")


def _configurar_logging():
    """Grava erros e avisos (WARNING ou mais) em data/solaz_app.log, com
    rotação básica para o arquivo nunca crescer sem limite."""
    os.makedirs(DATA_DIR, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
    )
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.WARNING)
    raiz.addHandler(handler)


# ---------------------------------------------------------------------------
# Tratamento global de exceções
# ---------------------------------------------------------------------------
_exibindo_erro = False   # evita empilhar vários diálogos se os erros se repetirem


def _mostrar_aviso(titulo: str, mensagem: str, erro: bool = True):
    """messagebox que funciona com ou sem janela Tk aberta. Nunca levanta."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        temporaria = None
        if getattr(tk, "_default_root", None) is None:
            temporaria = tk.Tk()
            temporaria.withdraw()
        try:
            (messagebox.showerror if erro else messagebox.showwarning)(titulo, mensagem)
        finally:
            if temporaria is not None:
                temporaria.destroy()
    except Exception:
        pass


def _tratar_excecao(tipo, valor, tb):
    """Registra no log e avisa o usuário, sem derrubar o programa."""
    global _exibindo_erro
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, tb)
        return
    try:
        _log.critical("Erro não tratado", exc_info=(tipo, valor, tb))
    except Exception:
        traceback.print_exception(tipo, valor, tb)
    if _exibindo_erro:
        return
    _exibindo_erro = True
    try:
        resumo = f"{tipo.__name__}: {valor}"
        if len(resumo) > 300:
            resumo = resumo[:300] + "…"
        _mostrar_aviso(
            "Solaz — Erro inesperado",
            "Ocorreu um erro inesperado, mas o programa continua aberto.\n\n"
            f"{resumo}\n\n"
            "O erro foi registrado em:\n"
            f"{LOG_PATH}\n\n"
            "Se o problema se repetir, envie esse arquivo ao suporte.",
        )
    finally:
        _exibindo_erro = False


def _tratar_excecao_thread(args):
    # Threads (ex.: bot do Telegram): só registra — nunca abre janela fora da thread da UI.
    if args.exc_type is SystemExit:
        return
    _log.critical(
        "Erro não tratado em thread (%s)", getattr(args.thread, "name", "?"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _tratar_excecao_tk(self, tipo, valor, tb):
    """O Tkinter captura exceções de botões/callbacks por conta própria (elas
    NÃO chegam ao sys.excepthook), então este método as redireciona."""
    _tratar_excecao(tipo, valor, tb)


def _instalar_tratamento_de_erros():
    import tkinter as tk

    sys.excepthook = _tratar_excecao
    threading.excepthook = _tratar_excecao_thread
    tk.Tk.report_callback_exception = _tratar_excecao_tk   # vale também para ctk.CTk


# Logs e tratamento de erros entram ANTES dos demais imports do projeto: assim
# até uma falha de importação (módulo ausente, etc.) é registrada e avisada.
_configurar_logging()
_instalar_tratamento_de_erros()

from database.db import init_db, rotina_backup_banco  # noqa: E402
from services.telegram_service import bot, iniciar_bot_polling  # noqa: E402
import services.auth_service as auth_service  # noqa: E402
from ui.login_window import LoginWindow  # noqa: E402
from ui.main_window import MainWindow, cancelar_afters_pendentes  # noqa: E402


# ---------------------------------------------------------------------------
# Trava de instância única (socket local)
# ---------------------------------------------------------------------------
_PORTA_INSTANCIA_UNICA = 65432
_trava_socket = None   # referência global: se o socket for coletado, a trava some


def _liberar_instancia():
    global _trava_socket
    if _trava_socket is not None:
        try:
            _trava_socket.close()
        except OSError:
            pass
        _trava_socket = None


def _adquirir_instancia_unica() -> bool:
    """True se esta é a única instância; False se já há outra aberta neste PC.
    Sem SO_REUSEADDR de propósito: um segundo bind na mesma porta tem de falhar."""
    global _trava_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", _PORTA_INSTANCIA_UNICA))
        sock.listen(1)
    except OSError:
        sock.close()
        return False
    _trava_socket = sock
    atexit.register(_liberar_instancia)
    return True


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
def _encerrar(app):
    """Encerramento limpo: para o polling do bot (best-effort) e fecha a
    janela sem deixar recursos pendentes no terminal."""
    try:
        bot.stop_polling()
    except Exception:
        pass
    auth_service.encerrar_sessao()   # sai do Supabase e limpa a sessão em memória
    cancelar_afters_pendentes(app)   # evita 'invalid command name' no terminal
    try:
        app.quit()
    finally:
        app.destroy()


_logout_solicitado = False   # ligado por MainWindow.fazer_logout()
_login_atual = None          # LoginWindow em exibição (para garantir que feche no logout)


def _solicitar_logout():
    global _logout_solicitado
    _logout_solicitado = True
    auth_service.encerrar_sessao()   # logout também encerra a sessão na nuvem


def abrir_janela_principal(is_master: bool = False):
    app = MainWindow(is_master=is_master, on_logout=_solicitar_logout)
    app.protocol("WM_DELETE_WINDOW", lambda: _encerrar(app))
    app.mainloop()
    # Logout: garante que a janela de login antiga não fique viva (oculta),
    # senão o mainloop externo não terminaria e o main() não reabriria o Login.
    if _logout_solicitado and _login_atual is not None:
        cancelar_afters_pendentes(_login_atual)
        try:
            _login_atual.destroy()
        except Exception:
            pass


def main():
    if not _adquirir_instancia_unica():
        _mostrar_aviso(
            "Solaz já está aberto",
            "O Solaz já está em execução neste computador.\n"
            "Feche a janela existente (ou verifique a barra de tarefas) antes de abrir de novo.",
            erro=False,
        )
        return

    # Backup ANTES de mexer no banco (init_db pode migrar colunas). Nunca
    # levanta exceção: se falhar, só registra no log.
    rotina_backup_banco()
    init_db()

    # Daemon Thread: não bloqueia a UI nem impede o app de fechar, mesmo
    # sem internet (o polling reconecta sozinho quando a rede voltar).
    iniciar_bot_polling()

    # Um ciclo por sessão: Login -> janela principal -> (logout) -> Login...
    # Fechar a janela pelo X não aciona o logout, então o programa encerra.
    global _logout_solicitado, _login_atual
    while True:
        _logout_solicitado = False
        _login_atual = LoginWindow(on_login_success=abrir_janela_principal)
        _login_atual.mainloop()
        if not _logout_solicitado:
            break


if __name__ == "__main__":
    main()
