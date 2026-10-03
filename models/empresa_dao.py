"""DAO de Empresas prestadoras de serviço (Módulo 'Minhas Empresas')."""
import sqlite3

from database.db import get_cursor


class EmpresaDAO:
    def listar(self):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM empresas ORDER BY nome COLLATE NOCASE")
            return [dict(r) for r in cur.fetchall()]

    def buscar_por_id(self, empresa_id: int):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def criar(self, dados: dict) -> int:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO empresas
                   (nome, cnpj, telefone, email, responsavel_tecnico,
                    responsavel_registro, logo_path, assinatura_path, codigo_empresa)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dados.get("nome"),
                    dados.get("cnpj"),
                    dados.get("telefone"),
                    dados.get("email"),
                    dados.get("responsavel_tecnico"),
                    dados.get("responsavel_registro"),
                    dados.get("logo_path"),
                    dados.get("assinatura_path"),
                    dados.get("codigo_empresa"),
                ),
            )
            return cur.lastrowid

    def atualizar(self, empresa_id: int, dados: dict):
        with get_cursor(commit=True) as cur:
            cur.execute(
                """UPDATE empresas SET nome=?, cnpj=?, telefone=?, email=?,
                   responsavel_tecnico=?, responsavel_registro=?, logo_path=?,
                   assinatura_path=?, codigo_empresa=?
                   WHERE id=?""",
                (
                    dados.get("nome"),
                    dados.get("cnpj"),
                    dados.get("telefone"),
                    dados.get("email"),
                    dados.get("responsavel_tecnico"),
                    dados.get("responsavel_registro"),
                    dados.get("logo_path"),
                    dados.get("assinatura_path"),
                    dados.get("codigo_empresa"),
                    empresa_id,
                ),
            )

    def excluir(self, empresa_id: int):
        """Remove a empresa. Levanta ValueError com mensagem amigável caso
        existam relatórios vinculados a ela (violação de chave estrangeira)."""
        try:
            with get_cursor(commit=True) as cur:
                cur.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        except sqlite3.IntegrityError:
            raise ValueError(
                "Não é possível excluir esta empresa: existem relatórios já "
                "gerados vinculados a ela."
            )

    def contar_total(self) -> int:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM empresas")
            return cur.fetchone()["total"]

    @staticmethod
    def codigo_exibicao(empresa: dict) -> str:
        """Código curto da empresa para compor a estrutura de pastas e a
        máscara do relatório: usa `codigo_empresa` cadastrado ou, se
        vazio, cai no fallback do ID interno (ex: id=3 -> '03')."""
        codigo = (empresa or {}).get("codigo_empresa")
        if codigo:
            return codigo
        empresa_id = (empresa or {}).get("id")
        return str(empresa_id).zfill(2) if empresa_id else "—"
