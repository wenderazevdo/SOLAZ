"""
Sessão do usuário logado, mantida só em memória (some ao fechar o app).

Os tokens (JWT/refresh) ficam dentro do cliente Supabase, que os renova
automaticamente; aqui guardamos apenas os dados de perfil para a interface.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SessaoUsuario:
    user_id: str
    email: str
    nome: str = ""
    usuario: str = ""           # nome de usuário usado no login
    papel: str = "usuario"      # 'usuario' | 'master'

    @property
    def is_master(self) -> bool:
        return self.papel == "master"


_sessao: Optional[SessaoUsuario] = None


def iniciar_sessao(sessao: SessaoUsuario) -> None:
    global _sessao
    _sessao = sessao


def sessao_atual() -> Optional[SessaoUsuario]:
    return _sessao


def encerrar_sessao() -> None:
    global _sessao
    _sessao = None
