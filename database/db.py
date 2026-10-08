"""
Camada de acesso ao banco de dados SQLite.

Todo o acesso a dados do sistema passa por get_connection(). Isso mantém a
lógica de persistência desacoplada da interface e das regras de negócio
(padrão Repository/DAO), facilitando uma futura migração para um banco de
dados em nuvem (PostgreSQL/MySQL) bastando trocar esta camada.
"""
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from config import DB_PATH

_log = logging.getLogger(__name__)

# Backup automático (ver rotina_backup_banco): um arquivo por dia em
# data/backups/, mantendo só os últimos BACKUP_DIAS_RETENCAO dias.
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")
BACKUP_PREFIXO = "sistema_backup"
BACKUP_DIAS_RETENCAO = 7
_TIMEOUT_CONEXAO = 30.0   # segundos esperando outro processo soltar o banco



def resource_path(relative_path: str) -> str:
    """Caminho de um arquivo ESTÁTICO empacotado com o app (somente leitura).

    * Executável do PyInstaller: usa sys._MEIPASS (pasta onde o PyInstaller
      extrai/guarda os arquivos incluídos com --add-data; em builds onedir
      recentes é dist/<App>/_internal).
    * Desenvolvimento (python main.py): usa a raiz do projeto.

    Use para schema.sql, assets, fontes etc. NÃO use para dados gravados
    pelo usuário (banco, logos, assinaturas, PDFs) — esses ficam em
    config.DATA_DIR / DB_PATH."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *relative_path.replace("\\", "/").split("/"))


def _resolver_schema() -> str:
    candidatos = [
        resource_path("database/schema.sql"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"),
        os.path.join(os.path.dirname(sys.executable), "database", "schema.sql"),
    ]
    for caminho in candidatos:
        if os.path.isfile(caminho):
            return caminho
    return candidatos[0]


_SCHEMA_PATH = _resolver_schema()


def get_connection() -> sqlite3.Connection:
    # Garante que a pasta do banco exista antes de conectar.
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=_TIMEOUT_CONEXAO)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # WAL: leitores e escritor não se bloqueiam; NORMAL: fsync só nos
        # checkpoints (rápido e seguro contra queda de energia em WAL).
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.DatabaseError:
        # Ex.: pasta em rede/somente leitura sem suporte a WAL: segue no modo padrão.
        _log.warning("Não foi possível ativar o modo WAL; usando o modo padrão.", exc_info=True)
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


def _limpar_backups_antigos(hoje: date):
    """Apaga backups com mais de BACKUP_DIAS_RETENCAO dias (hoje + 6 anteriores
    = 7 dias ficam). Só mexe em arquivos no padrão sistema_backup_AAAA-MM-DD.db."""
    limite = hoje - timedelta(days=BACKUP_DIAS_RETENCAO)
    padrao = re.compile(rf"{re.escape(BACKUP_PREFIXO)}_(\d{{4}}-\d{{2}}-\d{{2}})\.db")
    for nome in os.listdir(BACKUP_DIR):
        achado = padrao.fullmatch(nome)
        if not achado:
            continue
        try:
            data = datetime.strptime(achado.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if data <= limite:
            try:
                os.remove(os.path.join(BACKUP_DIR, nome))
            except OSError:
                _log.warning("Não foi possível apagar o backup antigo %s", nome, exc_info=True)


def rotina_backup_banco() -> Optional[str]:
    """Backup automático do banco via API nativa do SQLite (conn.backup), que
    gera uma cópia consistente mesmo com o banco em uso/WAL.

    Chame ANTES de init_db(). Se o banco ainda não existe (primeira execução),
    não faz nada. Grava data/backups/sistema_backup_AAAA-MM-DD.db (um por dia;
    rodar de novo no mesmo dia só atualiza o do dia) e mantém só os últimos 7
    dias. Escreve num arquivo .tmp e só então troca o definitivo, então uma
    falha no meio nunca estraga um backup bom. Nunca levanta exceção: se o
    backup falhar, registra no log e o app abre normalmente.
    Devolve o caminho do backup, ou None se não houve/falhou."""
    if not os.path.isfile(DB_PATH):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        hoje = date.today()
        destino = os.path.join(BACKUP_DIR, f"{BACKUP_PREFIXO}_{hoje:%Y-%m-%d}.db")
        temporario = destino + ".tmp"
        if os.path.exists(temporario):
            os.remove(temporario)

        origem = sqlite3.connect(DB_PATH, timeout=_TIMEOUT_CONEXAO)
        try:
            copia = sqlite3.connect(temporario)
            try:
                origem.backup(copia)
            finally:
                copia.close()
        finally:
            origem.close()

        os.replace(temporario, destino)
        _limpar_backups_antigos(hoje)
        return destino
    except Exception:
        _log.exception("Falha ao fazer o backup automático do banco de dados")
        return None


def init_db():
    """Cria as tabelas do sistema caso ainda não existam."""
    if not os.path.isfile(_SCHEMA_PATH):
        raise FileNotFoundError(
            f"schema.sql não encontrado em: {_SCHEMA_PATH}\n"
            "Ao compilar com o PyInstaller, inclua o arquivo com:\n"
            '  --add-data "database/schema.sql;database"'
        )
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
    # LEGADO: os usuários agora vivem no Supabase (tabela perfis). Esta
    # migração fica só para bancos locais antigos não darem erro.
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
