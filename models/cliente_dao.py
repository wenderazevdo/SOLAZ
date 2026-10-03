"""DAO de Clientes (Módulo 'Cadastro de Clientes')."""
import sqlite3

from database.db import get_cursor

_CAMPOS = [
    "nome_razao_social", "foto_local_path", "qtd_modulos", "modulo_marca",
    "modulo_potencia_wp", "modulo_foto_etiqueta_path", "acesso_telhado_facil",
    "acesso_telhado_obs", "ponto_agua_local", "ponto_agua_pressao",
    "ponto_agua_foto_path", "inversores_qtd", "inversores_foto_etiqueta_path",
    "endereco", "google_maps_link",
    # -- vínculo com empresa prestadora e dados cadastrais/comerciais --
    "cpf_cnpj", "contato_nome", "telefone", "empresa_id",
    "potencia_sistema_kwp", "inversor_marca_modelo",
    # -- código exibido no cabeçalho do relatório PDF (ex: '020101') --
    "codigo_cliente",
]


class ClienteDAO:
    def listar(self, empresa_id: int = None):
        """Lista clientes ordenados por nome. Quando `empresa_id` é
        informado, filtra apenas os vinculados àquela empresa prestadora
        (suporte ao filtro por empresa da tela de Clientes e do Gerador
        de Relatório)."""
        with get_cursor() as cur:
            if empresa_id:
                cur.execute(
                    """SELECT * FROM clientes WHERE empresa_id = ?
                       ORDER BY nome_razao_social COLLATE NOCASE""",
                    (empresa_id,),
                )
            else:
                cur.execute(
                    "SELECT * FROM clientes ORDER BY nome_razao_social COLLATE NOCASE"
                )
            return [dict(r) for r in cur.fetchall()]

    def listar_com_empresa(self, empresa_id: int = None):
        """Igual a `listar`, mas já traz o nome da empresa prestadora
        vinculada (LEFT JOIN), útil para exibição na lista/drawer."""
        with get_cursor() as cur:
            base = """SELECT c.*, e.nome AS empresa_nome
                       FROM clientes c
                       LEFT JOIN empresas e ON e.id = c.empresa_id"""
            if empresa_id:
                cur.execute(
                    base + " WHERE c.empresa_id = ? ORDER BY c.nome_razao_social COLLATE NOCASE",
                    (empresa_id,),
                )
            else:
                cur.execute(base + " ORDER BY c.nome_razao_social COLLATE NOCASE")
            return [dict(r) for r in cur.fetchall()]

    def contar_total(self, empresa_id: int = None) -> int:
        """Total de clientes cadastrados — geral, ou filtrado por empresa
        quando `empresa_id` é informado (usado pelos badges do cabeçalho)."""
        with get_cursor() as cur:
            if empresa_id:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM clientes WHERE empresa_id = ?",
                    (empresa_id,),
                )
            else:
                cur.execute("SELECT COUNT(*) AS total FROM clientes")
            return cur.fetchone()["total"]

    def buscar_por_id(self, cliente_id: int):
        with get_cursor() as cur:
            cur.execute(
                """SELECT c.*, e.nome AS empresa_nome
                   FROM clientes c
                   LEFT JOIN empresas e ON e.id = c.empresa_id
                   WHERE c.id = ?""",
                (cliente_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def criar(self, dados: dict) -> int:
        valores = [dados.get(c) for c in _CAMPOS]
        placeholders = ", ".join(["?"] * len(_CAMPOS))
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"INSERT INTO clientes ({', '.join(_CAMPOS)}) VALUES ({placeholders})",
                valores,
            )
            return cur.lastrowid

    def atualizar(self, cliente_id: int, dados: dict):
        set_clause = ", ".join([f"{c}=?" for c in _CAMPOS])
        valores = [dados.get(c) for c in _CAMPOS] + [cliente_id]
        with get_cursor(commit=True) as cur:
            cur.execute(
                f"UPDATE clientes SET {set_clause} WHERE id=?", valores
            )

    def excluir(self, cliente_id: int):
        """Remove o cliente. Levanta ValueError com mensagem amigável caso
        existam relatórios ou agendamentos vinculados a ele (violação de
        chave estrangeira) — parte da correção do bug de exclusão."""
        try:
            with get_cursor(commit=True) as cur:
                cur.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        except sqlite3.IntegrityError:
            raise ValueError(
                "Não é possível excluir este cliente: existem relatórios ou "
                "agendamentos vinculados a ele."
            )

    @staticmethod
    def codigo_exibicao(cliente: dict) -> str:
        """Código do cliente para exibir no cabeçalho do PDF: usa o
        `codigo_cliente` cadastrado manualmente ou, se vazio, gera um
        fallback a partir do ID interno (ex: id=101 -> '000101')."""
        codigo = (cliente or {}).get("codigo_cliente")
        if codigo:
            return codigo
        cliente_id = (cliente or {}).get("id")
        return str(cliente_id).zfill(6) if cliente_id else "—"
