"""
Serviço central de autenticação (Supabase): cadastro de conta, login com
fluxo de aprovação (pendente/aprovado/bloqueado), trava por HWID e conta
Master. Mantém ui/login_window.py e ui/dev_panel_view.py enxutas — toda a
regra de negócio de segurança vive aqui.

Fluxo:
  cadastro  -> sign_up no Supabase Auth; o trigger do banco cria o perfil com
               status 'pendente' (+ HWID/PC do cadastro); o app desloga na
               hora e avisa o desenvolvedor pelo Telegram.
  login     -> sign_in_with_password; carrega o perfil; só entra se
               status = 'aprovado' e o HWID bater (master ignora HWID).
  master    = conta Supabase com perfis.papel = 'master' e status 'aprovado'
               (definida manualmente via SQL, ver database/supabase_setup.sql).
"""
import logging
import re
from dataclasses import dataclass

from models.usuario_dao import (
    UsuarioDAO, STATUS_PENDENTE, STATUS_APROVADO, STATUS_BLOQUEADO, PAPEL_MASTER,
    normalizar_usuario, usuario_valido, USUARIO_MIN, USUARIO_MAX,
)
from services import session
from services.security_service import get_hwid, get_hwid_candidates, get_pc_name, get_win_user
from services.supabase_client import get_supabase
from services.telegram_service import notificar_novo_cadastro, alertar_uso_em_outro_pc

try:                                    # supabase-py recente
    from supabase_auth.errors import AuthApiError
except ImportError:                     # versões antigas
    from gotrue.errors import AuthApiError

_log = logging.getLogger(__name__)

# Motivos de falha de login, usados pela UI para escolher a mensagem certa.
MOTIVO_CREDENCIAIS_INVALIDAS = "credenciais_invalidas"
MOTIVO_PENDENTE = "pendente"
MOTIVO_BLOQUEADO = "bloqueado"
MOTIVO_HWID_DIVERGENTE = "hwid_divergente"
MOTIVO_USUARIO_EXISTENTE = "usuario_existente"
MOTIVO_CAMPOS_INVALIDOS = "campos_invalidos"
MOTIVO_EMAIL_NAO_CONFIRMADO = "email_nao_confirmado"
MOTIVO_ERRO_REDE = "erro_rede"
MOTIVO_PERFIL_AUSENTE = "perfil_ausente"

SENHA_MIN_CARACTERES = 6   # mínimo padrão do Supabase
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# código de erro do Supabase -> mensagem amigável
_ERROS_SUPABASE = {
    "invalid_credentials": "Usuário ou senha incorretos.",
    "email_not_confirmed": "Confirme seu e-mail antes de entrar (veja sua caixa de entrada).",
    "user_already_exists": "Este e-mail já está cadastrado.",
    "email_exists": "Este e-mail já está cadastrado.",
    "weak_password": f"Senha fraca. Use pelo menos {SENHA_MIN_CARACTERES} caracteres.",
    "email_address_invalid": "E-mail inválido.",
    "validation_failed": "E-mail ou senha em formato inválido.",
    "over_request_rate_limit": "Muitas tentativas. Aguarde um pouco e tente de novo.",
    "over_email_send_rate_limit": "Limite de e-mails atingido. Tente novamente mais tarde.",
    "signup_disabled": "Novos cadastros estão desativados no momento.",
    "unexpected_failure": "Não foi possível criar a conta. O nome de usuário pode já estar em uso.",
}
_MSG_REDE = "Falha de conexão com o servidor. Verifique sua internet e tente novamente."


@dataclass
class ResultadoAuth:
    sucesso: bool
    is_master: bool = False
    motivo: str = None
    usuario_dados: dict = None
    mensagem: str = ""          # se preenchida, a UI exibe esta em vez da padrão


@dataclass
class ResultadoCadastro:
    sucesso: bool
    motivo: str = None
    mensagem: str = ""


def _dao() -> UsuarioDAO:
    return UsuarioDAO()


def _traduzir_erro(exc: Exception) -> str:
    if isinstance(exc, AuthApiError):
        codigo = getattr(exc, "code", None)
        if codigo in _ERROS_SUPABASE:
            return _ERROS_SUPABASE[codigo]
        msg = (getattr(exc, "message", "") or str(exc)).lower()
        if "invalid login" in msg:
            return _ERROS_SUPABASE["invalid_credentials"]
        if "already registered" in msg:
            return _ERROS_SUPABASE["user_already_exists"]
        if "password" in msg:
            return _ERROS_SUPABASE["weak_password"]
        if "email" in msg:
            return _ERROS_SUPABASE["email_address_invalid"]
        return "Não foi possível concluir a operação."
    return _MSG_REDE


def _sair_silencioso():
    """Encerra a sessão no Supabase e na memória, sem nunca levantar erro."""
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    session.encerrar_sessao()


def encerrar_sessao():
    """Chamar no logout e ao fechar o app."""
    _sair_silencioso()


# ------------------------------------------------------------------ login --
def autenticar(usuario: str, senha: str) -> ResultadoAuth:
    usuario = normalizar_usuario(usuario)
    if not usuario or not senha:
        return ResultadoAuth(False, motivo=MOTIVO_CAMPOS_INVALIDOS,
                             mensagem="Preencha usuário e senha.")

    # Nome de usuário -> e-mail real do cadastro (o cliente nunca digita e-mail).
    try:
        email = _dao().resolver_email(usuario)
    except Exception:
        _log.exception("Falha ao resolver o usuário")
        return ResultadoAuth(False, motivo=MOTIVO_ERRO_REDE, mensagem=_MSG_REDE)
    if not email:   # mesma mensagem de senha errada: não revela se o usuário existe
        return ResultadoAuth(False, motivo=MOTIVO_CREDENCIAIS_INVALIDAS,
                             mensagem=_ERROS_SUPABASE["invalid_credentials"])

    sb = get_supabase()
    try:
        resp = sb.auth.sign_in_with_password({"email": email, "password": senha})
    except AuthApiError as exc:
        motivo = (MOTIVO_EMAIL_NAO_CONFIRMADO
                  if getattr(exc, "code", "") == "email_not_confirmed"
                  else MOTIVO_CREDENCIAIS_INVALIDAS)
        return ResultadoAuth(False, motivo=motivo, mensagem=_traduzir_erro(exc))
    except Exception:
        _log.exception("Falha de rede/inesperada no sign_in_with_password")
        return ResultadoAuth(False, motivo=MOTIVO_ERRO_REDE, mensagem=_MSG_REDE)

    user = resp.user
    try:
        perfil = _dao().buscar_meu_perfil(user.id)
        if perfil is None:
            _sair_silencioso()
            return ResultadoAuth(
                False, motivo=MOTIVO_PERFIL_AUSENTE,
                mensagem="Perfil não encontrado. Fale com o administrador.")

        # ---- Conta Master: sem trava de HWID/status pendente ----
        if perfil["papel"] == PAPEL_MASTER and perfil["status"] == STATUS_APROVADO:
            _iniciar_sessao(user, perfil)
            return ResultadoAuth(True, is_master=True, usuario_dados=perfil)

        # ---- Contas comuns: fluxo de aprovação ----
        if perfil["status"] == STATUS_PENDENTE:
            _sair_silencioso()
            return ResultadoAuth(False, motivo=MOTIVO_PENDENTE, usuario_dados=perfil)
        if perfil["status"] == STATUS_BLOQUEADO:
            _sair_silencioso()
            return ResultadoAuth(False, motivo=MOTIVO_BLOQUEADO, usuario_dados=perfil)

        hwid_atual = get_hwid()
        nome_pc_atual = get_pc_name()
        win_user_atual = get_win_user()

        if not perfil["hwid_vinculado"]:
            # Primeiro login aprovado (ou HWID resetado pelo master): vincula este PC.
            _dao().vincular_meu_hwid(hwid_atual, nome_pc_atual, win_user_atual)
            perfil["hwid_vinculado"] = hwid_atual
            _iniciar_sessao(user, perfil)
            return ResultadoAuth(True, usuario_dados=perfil)

        if perfil["hwid_vinculado"] in get_hwid_candidates():
            _iniciar_sessao(user, perfil)
            return ResultadoAuth(True, usuario_dados=perfil)

        # HWID divergente: tentativa de uso em outro PC / cópia do sistema.
        try:
            alertar_uso_em_outro_pc(
                usuario, perfil.get("nome_pc") or "—", nome_pc_atual, win_user_atual, hwid_atual,
            )
        except Exception:
            _log.warning("Falha ao enviar alerta de uso em outro PC", exc_info=True)
        _sair_silencioso()
        return ResultadoAuth(False, motivo=MOTIVO_HWID_DIVERGENTE, usuario_dados=perfil)

    except Exception:
        _log.exception("Erro ao validar perfil/HWID após o login")
        _sair_silencioso()
        return ResultadoAuth(False, motivo=MOTIVO_ERRO_REDE, mensagem=_MSG_REDE)


def _iniciar_sessao(user, perfil: dict):
    meta = user.user_metadata or {}
    session.iniciar_sessao(session.SessaoUsuario(
        user_id=user.id,
        email=user.email or perfil.get("email", ""),
        nome=perfil.get("nome") or meta.get("nome", ""),
        usuario=perfil.get("usuario") or "",
        papel=perfil.get("papel", "usuario"),
    ))


# --------------------------------------------------------------- cadastro --
def registrar_conta(nome: str, usuario: str, email: str, senha: str) -> ResultadoCadastro:
    nome = (nome or "").strip()
    usuario = normalizar_usuario(usuario)
    email = (email or "").strip().lower()
    senha = senha or ""

    if not nome or not usuario or not email or not senha:
        return ResultadoCadastro(False, MOTIVO_CAMPOS_INVALIDOS,
                                 "Preencha nome, usuário, e-mail e senha.")
    if not usuario_valido(usuario):
        return ResultadoCadastro(
            False, MOTIVO_CAMPOS_INVALIDOS,
            f"Usuário inválido. Use {USUARIO_MIN} a {USUARIO_MAX} caracteres: letras, números, "
            "ponto, hífen ou sublinhado (sem espaços ou acentos).")
    if not _EMAIL_RE.match(email):
        return ResultadoCadastro(False, MOTIVO_CAMPOS_INVALIDOS, "E-mail inválido.")
    try:
        if not _dao().usuario_disponivel(usuario):
            return ResultadoCadastro(False, MOTIVO_USUARIO_EXISTENTE,
                                     "Este nome de usuário já está em uso.")
    except Exception:
        _log.exception("Falha ao checar disponibilidade do usuário")
        return ResultadoCadastro(False, MOTIVO_ERRO_REDE, _MSG_REDE)
    if len(senha) < SENHA_MIN_CARACTERES:
        return ResultadoCadastro(
            False, MOTIVO_CAMPOS_INVALIDOS,
            f"A senha deve ter ao menos {SENHA_MIN_CARACTERES} caracteres.")

    hwid = get_hwid()
    nome_pc = get_pc_name()
    win_user = get_win_user()

    sb = get_supabase()
    try:
        resp = sb.auth.sign_up({
            "email": email,
            "password": senha,
            # Vai para raw_user_meta_data; o trigger do banco copia para perfis.
            # O status inicial é SEMPRE 'pendente' (definido no banco, não aqui).
            "options": {"data": {
                "nome": nome, "usuario": usuario, "hwid": hwid,
                "nome_pc": nome_pc, "win_user": win_user,
            }},
        })
    except AuthApiError as exc:
        return ResultadoCadastro(False, MOTIVO_USUARIO_EXISTENTE
                                 if getattr(exc, "code", "") in ("user_already_exists", "email_exists")
                                 else MOTIVO_CAMPOS_INVALIDOS, _traduzir_erro(exc))
    except Exception:
        _log.exception("Falha de rede/inesperada no sign_up")
        return ResultadoCadastro(False, MOTIVO_ERRO_REDE, _MSG_REDE)

    # Com "Confirm email" ligado, e-mail já existente NÃO gera erro: o Supabase
    # devolve um usuário "falso" com a lista de identities vazia.
    if resp.user is not None and resp.user.identities is not None and len(resp.user.identities) == 0:
        return ResultadoCadastro(False, MOTIVO_USUARIO_EXISTENTE, _ERROS_SUPABASE["user_already_exists"])

    # Com "Confirm email" desligado o sign_up já devolve sessão: deslogamos,
    # porque a conta ainda está PENDENTE de aprovação.
    precisa_confirmar_email = resp.session is None
    if resp.session is not None:
        _sair_silencioso()

    try:
        notificar_novo_cadastro(
            usuario, nome_pc, win_user, hwid,
            email=email, user_id=resp.user.id if resp.user else None,
        )
    except Exception:
        _log.warning("Falha ao notificar novo cadastro no Telegram", exc_info=True)

    msg = "Cadastro realizado! Aguarde a liberação do desenvolvedor para este computador."
    if precisa_confirmar_email:
        msg += "\nEnviamos também um e-mail de confirmação: confirme-o antes de entrar."
    return ResultadoCadastro(True, None, msg)
