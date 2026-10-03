"""
Ponto de entrada da aplicação.

Fluxo: inicializa o banco de dados SQLite -> inicia o bot do Telegram em
segundo plano -> exibe a tela de Login (com cadastro de conta e trava por
HWID) -> ao autenticar com sucesso, abre a Janela Principal — em modo normal
ou, se a conta for a Master (dev_master), com o Painel do Desenvolvedor
liberado.
"""
from database.db import init_db, seed_default_user
from services.telegram_service import bot, iniciar_bot_polling
from ui.login_window import LoginWindow
from ui.main_window import MainWindow


def _encerrar(app):
    """Encerramento limpo: para o polling do bot (best-effort) e fecha a
    janela sem deixar recursos pendentes no terminal."""
    try:
        bot.stop_polling()
    except Exception:
        pass
    try:
        app.quit()
    finally:
        app.destroy()


def abrir_janela_principal(is_master: bool = False):
    app = MainWindow(is_master=is_master)
    app.protocol("WM_DELETE_WINDOW", lambda: _encerrar(app))
    app.mainloop()


def main():
    init_db()
    seed_default_user()

    # Daemon Thread: não bloqueia a UI nem impede o app de fechar, mesmo
    # sem internet (o polling reconecta sozinho quando a rede voltar).
    iniciar_bot_polling()

    login = LoginWindow(on_login_success=abrir_janela_principal)
    login.mainloop()


if __name__ == "__main__":
    main()
