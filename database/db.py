"""
Camada de acesso ao banco de dados SQLite.

Todo o acesso a dados do sistema passa por get_connection(). Isso mantém a
lógica de persistência desacoplada da interface e das regras de negócio
(padrão Repository/DAO), facilitando uma futura migração para um banco de
dados em nuvem (PostgreSQL/MySQL) bastando trocar esta camada.
"""
import os
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_cursor(commit: bool = False):
    """Context manager que entrega um cursor e fecha a conexão ao final."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def init_db():
    """Cria as tabelas do sistema caso ainda não existam."""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        _migrar_colunas_extras(conn)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Migração aditiva: adiciona colunas novas em bancos já existentes sem
# apagar dados. SQLite não suporta "ADD COLUMN IF NOT EXISTS", então
# checamos via PRAGMA table_info antes de alterar cada tabela. Seguro
# rodar em toda inicialização (idempotente). Tabelas inteiramente novas
# (ex: relatorio_ca, configuracoes) não precisam entrar aqui — o
# executescript acima já as cria via CREATE TABLE IF NOT EXISTS.
# ---------------------------------------------------------------------
_COLUNAS_NOVAS = {
    "empresas": [
        ("assinatura_path", "TEXT"),
        ("codigo_empresa", "TEXT"),
    ],
    "clientes": [
        ("cpf_cnpj", "TEXT"),
        ("contato_nome", "TEXT"),
        ("telefone", "TEXT"),
        ("empresa_id", "INTEGER REFERENCES empresas(id)"),
        ("potencia_sistema_kwp", "REAL"),
        ("inversor_marca_modelo", "TEXT"),
        ("codigo_cliente", "TEXT"),
    ],
    "relatorios": [
        ("revisao", "TEXT DEFAULT '01'"),
    ],
    "relatorio_strings": [
        ("status_tensao", "TEXT DEFAULT 'CONFORME'"),
        ("status_flutuacao_positivo", "TEXT DEFAULT 'CONFORME'"),
        ("status_flutuacao_negativo", "TEXT DEFAULT 'CONFORME'"),
        ("neutro_valor", "REAL"),
        ("status_neutro", "TEXT DEFAULT 'CONFORME'"),
    ],
    "relatorio_ca_disjuntores": [
        ("corrente_injecao_valor", "REAL"),
        ("corrente_injecao_status", "TEXT DEFAULT 'CONFORME'"),
        ("neutro_valor", "REAL"),
        ("status_neutro", "TEXT DEFAULT 'CONFORME'"),
    ],
    "agenda": [
        ("descricao_servico", "TEXT"),
        ("valor_orcamento", "REAL"),
    ],
    "usuarios": [
        ("hwid_vinculado", "TEXT"),
        ("nome_pc", "TEXT"),
        ("win_user", "TEXT"),
        ("status", "TEXT DEFAULT 'aprovado'"),
    ],
}


def _migrar_colunas_extras(conn: sqlite3.Connection):
    for tabela, colunas in _COLUNAS_NOVAS.items():
        existe_tabela = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
        ).fetchone()
        if not existe_tabela:
            continue  # tabela ainda não existe neste banco; nada a migrar
        colunas_atuais = {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
        for nome_coluna, tipo_sql in colunas:
            if nome_coluna not in colunas_atuais:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo_sql}")


def seed_default_user():
    """Garante a conta padrão de fábrica ('solaz' / 'solaz123'). Roda em
    toda inicialização (não só em banco novo) para que instalações já
    existentes também ganhem a conta ao atualizar o sistema. A conta
    Master de Desenvolvedor NÃO fica no banco — é validada só contra
    config.MASTER_USUARIO/MASTER_SENHA_HASH (ver services/auth_service.py),
    então o hash da senha mestra nunca fica gravado no arquivo .db."""
    from models.usuario_dao import UsuarioDAO, STATUS_APROVADO

    dao = UsuarioDAO()
    if not dao.buscar_por_usuario("solaz"):
        dao.criar_usuario("solaz", "solaz123", status=STATUS_APROVADO)
