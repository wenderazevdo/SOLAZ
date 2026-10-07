"""Retry para operações sensíveis a hibernação/suspensão do Windows.

Logo após o PC acordar, o disco, a subpasta de relatórios ou o arquivo
SQLite podem demorar alguns instantes para voltar. Em vez de mostrar erro,
tentamos de novo (até 3 vezes, com 500 ms entre as tentativas).
"""
import functools
import logging
import sqlite3
import time

log = logging.getLogger(__name__)

TENTATIVAS = 3
INTERVALO_S = 0.5

# Mensagens do SQLite que indicam problema TRANSITÓRIO. Erros de lógica
# ("no such column", "syntax error"...) NÃO entram aqui: não adianta repetir.
_MARCAS_SQLITE = (
    "disk i/o error",
    "unable to open database",
    "database is locked",
    "database table is locked",
    "readonly database",
    "cannot commit",
)


def erro_transitorio(exc: BaseException) -> bool:
    """True se vale a pena esperar e tentar de novo."""
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        return any(m in msg for m in _MARCAS_SQLITE)
    # PermissionError, FileNotFoundError, "Input/output error" etc.
    return isinstance(exc, OSError)


def _resetar_conexoes():
    """Pede ao database.db para descartar conexões possivelmente mortas.
    Silencioso se a função ainda não existir (db.py não atualizado)."""
    try:
        from database.db import resetar_conexao
    except ImportError:
        return
    try:
        resetar_conexao()
    except Exception:
        log.exception("Falha ao resetar conexão SQLite durante o retry")


def executar_com_retry(func, *args, **kwargs):
    """Executa func(*args, **kwargs) com até TENTATIVAS tentativas.
    Só repete erros transitórios; qualquer outro erro sobe na hora."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if tentativa >= TENTATIVAS or not erro_transitorio(exc):
                raise
            log.warning("Tentativa %d/%d falhou (%s: %s); nova tentativa em %.0f ms",
                        tentativa, TENTATIVAS, type(exc).__name__, exc,
                        INTERVALO_S * 1000)
            if isinstance(exc, sqlite3.Error):
                _resetar_conexoes()
            time.sleep(INTERVALO_S)


def pular_se_cursor_externo(args, kwargs) -> bool:
    """Para métodos do DAO que aceitam `cur=`: se o cursor veio de fora, a
    transação é de quem chamou (conexão única) e o retry fica com ele."""
    return kwargs.get("cur") is not None


def com_retry(pular_se=None):
    """Decorator: @com_retry() ou @com_retry(pular_se=pular_se_cursor_externo)."""
    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if pular_se is not None and pular_se(args, kwargs):
                return func(*args, **kwargs)
            return executar_com_retry(func, *args, **kwargs)
        return wrapper
    return decorador
