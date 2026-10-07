"""DAO da Agenda/Calendário de atendimentos e Serviços Realizados."""
from database.db import get_cursor


class AgendaDAO:
    # Colunas da tabela `agenda` que `atualizar()` aceita alterar.
    CAMPOS_ATUALIZAVEIS = frozenset({
        "data", "hora", "ordem_atendimento", "observacoes",
        "descricao_servico", "valor_orcamento",
    })

    def criar(self, cliente_id: int, data: str, hora: str,
              ordem_atendimento: int = 1, observacoes: str = "",
              descricao_servico: str = "", valor_orcamento: float = None):
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO agenda
                   (cliente_id, data, hora, ordem_atendimento, observacoes,
                    descricao_servico, valor_orcamento)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (cliente_id, data, hora, ordem_atendimento, observacoes,
                 descricao_servico, valor_orcamento),
            )
            return cur.lastrowid

    def listar_por_periodo(self, data_inicio: str, data_fim: str):
        with get_cursor() as cur:
            cur.execute(
                """SELECT a.*, c.nome_razao_social AS cliente_nome, c.endereco,
                          c.google_maps_link
                   FROM agenda a
                   JOIN clientes c ON c.id = a.cliente_id
                   WHERE a.data BETWEEN ? AND ?
                   ORDER BY a.data, a.ordem_atendimento, a.hora""",
                (data_inicio, data_fim),
            )
            return [dict(r) for r in cur.fetchall()]

    def listar_por_dia(self, data: str):
        return self.listar_por_periodo(data, data)

    def atualizar(self, agenda_id: int, **campos):
        if not campos:
            return
        invalidos = sorted(set(campos) - self.CAMPOS_ATUALIZAVEIS)
        if invalidos:
            raise ValueError(
                f"Campos inválidos para atualizar a agenda: {', '.join(invalidos)}. "
                f"Permitidos: {', '.join(sorted(self.CAMPOS_ATUALIZAVEIS))}.")
        set_clause = ", ".join([f"{k}=?" for k in campos])
        valores = list(campos.values()) + [agenda_id]
        with get_cursor(commit=True) as cur:
            cur.execute(f"UPDATE agenda SET {set_clause} WHERE id=?", valores)

    def excluir(self, agenda_id: int):
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM agenda WHERE id = ?", (agenda_id,))

    # ------------------------------------- Serviços Realizados / financeiro --
    def listar_servicos_realizados(self, empresa_id: int = None,
                                    data_inicio: str = None, data_fim: str = None):
        """Atendimentos com valor de orçamento preenchido, no período e
        empresa informados — base da aba 'Serviços Realizados'."""
        condicoes = ["a.valor_orcamento IS NOT NULL"]
        params = []
        if empresa_id:
            condicoes.append("c.empresa_id = ?")
            params.append(empresa_id)
        if data_inicio and data_fim:
            condicoes.append("a.data BETWEEN ? AND ?")
            params += [data_inicio, data_fim]
        where = " AND ".join(condicoes)
        with get_cursor() as cur:
            cur.execute(
                f"""SELECT a.*, c.nome_razao_social AS cliente_nome,
                           c.empresa_id, e.nome AS empresa_nome
                    FROM agenda a
                    JOIN clientes c ON c.id = a.cliente_id
                    LEFT JOIN empresas e ON e.id = c.empresa_id
                    WHERE {where}
                    ORDER BY a.data, a.ordem_atendimento""",
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def somar_total_periodo(self, empresa_id: int = None,
                             data_inicio: str = None, data_fim: str = None) -> float:
        servicos = self.listar_servicos_realizados(empresa_id, data_inicio, data_fim)
        return sum(s["valor_orcamento"] or 0 for s in servicos)

    def totais_por_empresa(self, data_inicio: str = None, data_fim: str = None):
        """Total de orçamento agrupado por empresa no período — dados para
        o gráfico financeiro da aba Serviços Realizados."""
        condicoes = ["a.valor_orcamento IS NOT NULL"]
        params = []
        if data_inicio and data_fim:
            condicoes.append("a.data BETWEEN ? AND ?")
            params += [data_inicio, data_fim]
        where = " AND ".join(condicoes)
        with get_cursor() as cur:
            cur.execute(
                f"""SELECT COALESCE(e.nome, 'Sem empresa') AS empresa_nome,
                           SUM(a.valor_orcamento) AS total
                    FROM agenda a
                    JOIN clientes c ON c.id = a.cliente_id
                    LEFT JOIN empresas e ON e.id = c.empresa_id
                    WHERE {where}
                    GROUP BY empresa_nome
                    ORDER BY total DESC""",
                params,
            )
            return [dict(r) for r in cur.fetchall()]
