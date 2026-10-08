"""
Cliente Supabase único da aplicação (singleton).

O cliente guarda a sessão do usuário logado (JWT + refresh token) em memória
e a renova sozinho. Todas as chamadas feitas por ele (auth, tabelas, RPC)
usam automaticamente o token do usuário logado, então as políticas RLS do
banco (ver database/supabase_setup.sql) valem para o app inteiro.

IMPORTANTE: use apenas a chave 'publishable' (antiga anon). NUNCA coloque a
'secret'/'service_role' dentro do aplicativo.
"""
from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY não configurados em config.py")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client
