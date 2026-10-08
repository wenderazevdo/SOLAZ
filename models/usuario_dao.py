"""
DAO de usuários — agora sobre o Supabase.

* Credenciais (e-mail/senha) ficam no Supabase Auth.
* Dados de aprovação (status, papel, HWID, nome do PC) ficam na tabela
  public.perfis, protegida por RLS (ver database/supabase_setup.sql):
    - usuário comum: só LÊ o próprio perfil;
    - master: lê, aprova/bloqueia, reseta HWID e exclui qualquer usuário;
    - o usuário comum só consegue gravar o HWID uma vez, via RPC
      vincular_meu_hwid (que só atua se o HWID ainda estiver vazio).

Os nomes dos métodos foram mantidos para o Painel do Desenvolvedor continuar
funcionando. Diferenças: `id` agora é um UUID (str) e o dict devolvido traz
a chave 'usuario' (= e-mail) por compatibilidade, além de 'email' e 'nome'.
"""
import hashlib
import os
import re

from services import session
from services.supabase_client import get_supabase

STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_BLOQUEADO = "bloqueado"
_STATUS_VALIDOS = {STATUS_PENDENTE, STATUS_APROVADO, STATUS_BLOQUEADO}

PAPEL_USUARIO = "usuario"
PAPEL_MASTER = "master"

_TABELA = "perfis"

# ---- Nome de usuário -------------------------------------------------------
# O cliente entra com um nome de usuário. O e-mail REAL (informado no cadastro)
# fica em perfis.email e é descoberto por RPC (email_do_usuario) antes do login.
_USUARIO_RE = re.compile(r"^[a-z0-9]+([._-][a-z0-9]+)*$")
USUARIO_MIN, USUARIO_MAX = 3, 30


def normalizar_usuario(usuario: str) -> str:
    return (usuario or "").strip().lower()


def usuario_valido(usuario: str) -> bool:
    """3 a 30 caracteres: letras, números, ponto, hífen ou sublinhado (sem espaços)."""
    u = normalizar_usuario(usuario)
    return USUARIO_MIN <= len(u) <= USUARIO_MAX and bool(_USUARIO_RE.match(u))


# --- LEGADO -----------------------------------------------------------------
# Hash de senha local. Não é mais usado no login (a conta Master agora é uma
# conta Supabase com perfis.papel = 'master'); mantido só para não quebrar
# scripts antigos (ex.: gerar_hash_master.py).
def _hash_senha(senha: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def hash_senha_com_salt_embutido(senha: str) -> str:
    salt = os.urandom(16).hex()
    return f"{salt}${_hash_senha(senha, salt)}"


def verificar_senha_com_salt_embutido(senha: str, combinado: str) -> bool:
    if not combinado or "$" not in combinado:
        return False
    salt, esperado = combinado.split("$", 1)
    return _hash_senha(senha, salt) == esperado
# ---------------------------------------------------------------------------


def _normalizar(row: dict) -> dict:
    d = dict(row)
    d["usuario"] = d.get("usuario") or d.get("email")   # nome de login (ou e-mail, p/ contas antigas)
    return d


class UsuarioDAO:
    def _sb(self):
        return get_supabase()

    # ------------------------------------------------------- consultas --
    def existe_algum_usuario(self) -> bool:
        resp = self._sb().table(_TABELA).select("id", count="exact").limit(1).execute()
        return (resp.count or 0) > 0

    def buscar_meu_perfil(self, user_id: str):
        """Perfil do próprio usuário logado (RLS permite)."""
        resp = (self._sb().table(_TABELA).select("*").eq("id", user_id).limit(1).execute())
        return _normalizar(resp.data[0]) if resp.data else None

    def buscar_por_usuario(self, usuario: str):
        """Busca por usuário (ou e-mail). Usuário comum só enxerga o próprio perfil; o
        master enxerga todos."""
        chave = normalizar_usuario(usuario)
        coluna = "email" if "@" in chave else "usuario"
        resp = self._sb().table(_TABELA).select("*").eq(coluna, chave).limit(1).execute()
        return _normalizar(resp.data[0]) if resp.data else None

    def listar_todos(self):
        """Só retorna todos os perfis se quem chama for master (RLS)."""
        resp = self._sb().table(_TABELA).select("*").order("criado_em", desc=True).execute()
        return [_normalizar(r) for r in (resp.data or [])]

    # ------------------------------------------- resolução de login --
    def resolver_email(self, usuario: str):
        """Nome de usuário -> e-mail real do cadastro (ou None se não existir).
        Se vier um e-mail (contém @), devolve ele mesmo: serve de plano B para
        contas antigas sem nome de usuário. Roda ANTES do login (usa RPC pública)."""
        chave = normalizar_usuario(usuario)
        if not chave:
            return None
        if "@" in chave:
            return chave
        resp = self._sb().rpc("email_do_usuario", {"p_usuario": chave}).execute()
        return resp.data or None

    def usuario_disponivel(self, usuario: str) -> bool:
        resp = self._sb().rpc("usuario_disponivel", {"p_usuario": normalizar_usuario(usuario)}).execute()
        return bool(resp.data)

    # --------------------------------------------------------- criação --
    def criar_usuario(self, *args, **kwargs):
        raise NotImplementedError(
            "Contas são criadas no Supabase Auth: use auth_service.registrar_conta()."
        )

    # ----------------------------------------------- senha (usuário atual) --
    def validar_login(self, usuario: str, senha: str) -> bool:
        """Confere usuário+senha no Supabase (usado em telas internas como
        'Alterar Senha'). Refaz o login do mesmo usuário, sem efeitos
        colaterais além de renovar o token."""
        try:
            self._sb().auth.sign_in_with_password(
                {"email": self.resolver_email(usuario) or "", "password": senha}
            )
            return True
        except Exception:
            return False

    def alterar_senha(self, usuario: str, nova_senha: str):
        """Altera a senha do usuário LOGADO. (Alterar a senha de outra conta
        exige a chave service_role e não é feito pelo app.)"""
        atual = session.sessao_atual()
        if atual is None or normalizar_usuario(usuario) not in {
            (atual.usuario or "").lower(), (atual.email or "").lower()}:
            raise PermissionError("Só é possível alterar a senha da conta logada.")
        self._sb().auth.update_user({"password": nova_senha})

    # ------------------------------------------- Painel do Desenvolvedor --
    def atualizar_status(self, usuario_id: str, status: str):
        if status not in _STATUS_VALIDOS:
            raise ValueError(f"Status inválido: {status}")
        resp = (self._sb().table(_TABELA).update({"status": status}).eq("id", usuario_id).execute())
        # RLS não gera erro: sem permissão, simplesmente 0 linhas são alteradas.
        if not resp.data:
            raise PermissionError("Sem permissão (apenas master) ou usuário não encontrado.")

    def deletar(self, usuario_id: str):
        """Exclui a conta de verdade (Auth + perfil) via RPC exclusiva do master."""
        self._sb().rpc("excluir_usuario", {"p_id": usuario_id}).execute()

    def resetar_hwid(self, usuario_id: str):
        """Limpa o HWID: o próximo login aprovado desta conta vincula o novo PC."""
        resp = (self._sb().table(_TABELA).update({"hwid_vinculado": None}).eq("id", usuario_id).execute())
        if not resp.data:
            raise PermissionError("Sem permissão (apenas master) ou usuário não encontrado.")

    def vincular_hwid(self, usuario_id: str, hwid: str, nome_pc: str, win_user: str):
        """Versão do master: grava HWID de qualquer usuário."""
        resp = (self._sb().table(_TABELA)
                .update({"hwid_vinculado": hwid, "nome_pc": nome_pc, "win_user": win_user})
                .eq("id", usuario_id).execute())
        if not resp.data:
            raise PermissionError("Sem permissão (apenas master) ou usuário não encontrado.")

    def vincular_meu_hwid(self, hwid: str, nome_pc: str, win_user: str):
        """Versão do usuário comum: só funciona se o HWID ainda estiver vazio."""
        self._sb().rpc(
            "vincular_meu_hwid",
            {"p_hwid": hwid, "p_nome_pc": nome_pc, "p_win_user": win_user},
        ).execute()
