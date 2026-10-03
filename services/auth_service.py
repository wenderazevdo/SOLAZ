"""
Serviço central de autenticação: cadastro de conta, login com trava por
HWID e bypass total da conta Master de Desenvolvedor. Mantém
ui/login_window.py e ui/dev_panel_view.py enxutas — toda a regra de
negócio de segurança vive aqui.
"""
from dataclasses import dataclass

import config
from models.usuario_dao import (
    UsuarioDAO, STATUS_PENDENTE, STATUS_APROVADO, STATUS_BLOQUEADO,
    verificar_senha_com_salt_embutido,
)
from services.security_service import get_hwid, get_hwid_candidates, get_pc_name, get_win_user
from services.telegram_service import notificar_novo_cadastro, alertar_uso_em_outro_pc

# Motivos de falha de login, usados pela UI para escolher a mensagem certa.
MOTIVO_CREDENCIAIS_INVALIDAS = "credenciais_invalidas"
MOTIVO_PENDENTE = "pendente"
MOTIVO_BLOQUEADO = "bloqueado"
MOTIVO_HWID_DIVERGENTE = "hwid_divergente"
MOTIVO_USUARIO_EXISTENTE = "usuario_existente"
MOTIVO_CAMPOS_INVALIDOS = "campos_invalidos"


@dataclass
class ResultadoAuth:
    sucesso: bool
    is_master: bool = False
    motivo: str = None
    usuario_dados: dict = None


@dataclass
class ResultadoCadastro:
    sucesso: bool
    motivo: str = None
    mensagem: str = ""


def _dao() -> UsuarioDAO:
    return UsuarioDAO()


def autenticar(usuario: str, senha: str) -> ResultadoAuth:
    usuario = (usuario or "").strip()

    # ---- Conta Master: bypass total, nunca passa pelo banco de dados ----
    if usuario and usuario.lower() == config.MASTER_USUARIO.lower():
        if config.MASTER_SENHA_HASH and verificar_senha_com_salt_embutido(senha, config.MASTER_SENHA_HASH):
            return ResultadoAuth(sucesso=True, is_master=True)
        return ResultadoAuth(sucesso=False, motivo=MOTIVO_CREDENCIAIS_INVALIDAS)

    # ---- Contas comuns ----
    dao = _dao()
    linha = dao.buscar_por_usuario(usuario)
    if not linha or not dao.validar_login(usuario, senha):
        return ResultadoAuth(sucesso=False, motivo=MOTIVO_CREDENCIAIS_INVALIDAS)

    if linha["status"] == STATUS_PENDENTE:
        return ResultadoAuth(sucesso=False, motivo=MOTIVO_PENDENTE, usuario_dados=linha)
    if linha["status"] == STATUS_BLOQUEADO:
        return ResultadoAuth(sucesso=False, motivo=MOTIVO_BLOQUEADO, usuario_dados=linha)

    hwid_atual = get_hwid()
    nome_pc_atual = get_pc_name()
    win_user_atual = get_win_user()

    if not linha["hwid_vinculado"]:
        # Primeiro login aprovado (ou HWID resetado pelo dev) — vincula
        # este PC automaticamente.
        dao.vincular_hwid(linha["id"], hwid_atual, nome_pc_atual, win_user_atual)
        linha["hwid_vinculado"] = hwid_atual
        return ResultadoAuth(sucesso=True, usuario_dados=linha)

    if linha["hwid_vinculado"] in get_hwid_candidates():
        # Bate com o HWID gravado (considerando os métodos alternativos de
        # captura, para não bloquear por falso positivo).
        return ResultadoAuth(sucesso=True, usuario_dados=linha)

    # HWID divergente: tentativa de uso em outro PC / cópia do sistema.
    alertar_uso_em_outro_pc(
        usuario, linha.get("nome_pc") or "—", nome_pc_atual, win_user_atual, hwid_atual,
    )
    return ResultadoAuth(sucesso=False, motivo=MOTIVO_HWID_DIVERGENTE, usuario_dados=linha)


def registrar_conta(usuario: str, senha: str) -> ResultadoCadastro:
    usuario = (usuario or "").strip()
    senha = senha or ""

    if not usuario or not senha:
        return ResultadoCadastro(False, MOTIVO_CAMPOS_INVALIDOS, "Preencha usuário e senha.")
    if len(senha) < 4:
        return ResultadoCadastro(
            False, MOTIVO_CAMPOS_INVALIDOS, "A senha deve ter ao menos 4 caracteres."
        )
    if usuario.lower() == config.MASTER_USUARIO.lower():
        return ResultadoCadastro(False, MOTIVO_USUARIO_EXISTENTE, "Este nome de usuário é reservado.")

    dao = _dao()
    if dao.buscar_por_usuario(usuario):
        return ResultadoCadastro(
            False, MOTIVO_USUARIO_EXISTENTE, "Este usuário já está cadastrado."
        )

    hwid = get_hwid()
    nome_pc = get_pc_name()
    win_user = get_win_user()

    dao.criar_usuario(
        usuario, senha, status=STATUS_PENDENTE,
        hwid_vinculado=hwid, nome_pc=nome_pc, win_user=win_user,
    )
    notificar_novo_cadastro(usuario, nome_pc, win_user, hwid)

    return ResultadoCadastro(
        True, None,
        "Cadastro realizado! Aguarde a liberação do desenvolvedor para este computador.",
    )
