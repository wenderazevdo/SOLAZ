"""
DAO de usuários — autenticação local, trava por HWID e conta Master.
Senhas nunca são armazenadas em texto puro: usamos hash salgado (PBKDF2).
"""
import hashlib
import os

from database.db import get_cursor

STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_BLOQUEADO = "bloqueado"


def _hash_senha(senha: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def hash_senha_com_salt_embutido(senha: str) -> str:
    """Gera um hash autocontido no formato 'salt$hash' — usado para a
    Senha Mestra (config.MASTER_SENHA_HASH), que fica fora do banco de
    dados (em config.py / variável de ambiente)."""
    salt = os.urandom(16).hex()
    return f"{salt}${_hash_senha(senha, salt)}"


def verificar_senha_com_salt_embutido(senha: str, combinado: str) -> bool:
    if not combinado or "$" not in combinado:
        return False
    salt, esperado = combinado.split("$", 1)
    return _hash_senha(senha, salt) == esperado


class UsuarioDAO:
    def existe_algum_usuario(self) -> bool:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM usuarios")
            return cur.fetchone()["n"] > 0

    def buscar_por_usuario(self, usuario: str):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
            row = cur.fetchone()
            return dict(row) if row else None

    def listar_todos(self):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM usuarios ORDER BY criado_em DESC")
            return [dict(r) for r in cur.fetchall()]

    def criar_usuario(self, usuario: str, senha: str, status: str = STATUS_APROVADO,
                       hwid_vinculado: str = None, nome_pc: str = None,
                       win_user: str = None) -> int:
        salt = os.urandom(16).hex()
        senha_hash = _hash_senha(senha, salt)
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO usuarios
                   (usuario, senha_hash, salt, hwid_vinculado, nome_pc, win_user, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (usuario, senha_hash, salt, hwid_vinculado, nome_pc, win_user, status),
            )
            return cur.lastrowid

    def validar_login(self, usuario: str, senha: str) -> bool:
        """Verifica só a senha (sem checar status/HWID) — usada em telas
        internas como 'Alterar Senha'. O fluxo completo de login mora em
        services/auth_service.py."""
        with get_cursor() as cur:
            cur.execute(
                "SELECT senha_hash, salt FROM usuarios WHERE usuario = ?",
                (usuario,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            return _hash_senha(senha, row["salt"]) == row["senha_hash"]

    def alterar_senha(self, usuario: str, nova_senha: str):
        salt = os.urandom(16).hex()
        senha_hash = _hash_senha(nova_senha, salt)
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE usuarios SET senha_hash = ?, salt = ? WHERE usuario = ?",
                (senha_hash, salt, usuario),
            )

    # ------------------------------------------- Painel do Desenvolvedor --
    def atualizar_status(self, usuario_id: int, status: str):
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE usuarios SET status = ? WHERE id = ?", (status, usuario_id))

    def deletar(self, usuario_id: int):
        """Remove definitivamente o registro da tabela `usuarios`."""
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))

    def resetar_hwid(self, usuario_id: int):
        """Limpa o HWID vinculado — o próximo login bem-sucedido desta
        conta vincula automaticamente o novo PC (autoriza a troca)."""
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE usuarios SET hwid_vinculado = NULL WHERE id = ?", (usuario_id,))

    def vincular_hwid(self, usuario_id: int, hwid: str, nome_pc: str, win_user: str):
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE usuarios SET hwid_vinculado = ?, nome_pc = ?, win_user = ? WHERE id = ?",
                (hwid, nome_pc, win_user, usuario_id),
            )
