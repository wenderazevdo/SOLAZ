"""DAO de Relatórios: cabeçalho, fotos por seção, tabela de strings e bloco CA."""
import json
from datetime import date, datetime

from database.db import get_cursor


STATUS_REL_PENDENTE = "Pendente"
STATUS_REL_APROVADO = "Aprovado"
STATUS_REL_REPROVADO = "Reprovado"


class RelatorioDAO:
    # ---------- Status de aprovação (usado pelo bot do Telegram) ----------
    @staticmethod
    def _garantir_coluna_status(cur):
        """Cria a coluna `status` em `relatorios` se ainda não existir
        (migração idempotente — bancos antigos continuam funcionando)."""
        cur.execute("PRAGMA table_info(relatorios)")
        if "status" not in [r["name"] for r in cur.fetchall()]:
            cur.execute("ALTER TABLE relatorios ADD COLUMN status TEXT DEFAULT 'Pendente'")

    def atualizar_status(self, codigo: str, status: str) -> bool:
        """Atualiza o status ('Aprovado'/'Reprovado'/'Pendente') pelo código
        do relatório. Retorna True se algum relatório foi alterado."""
        with get_cursor(commit=True) as cur:
            self._garantir_coluna_status(cur)
            cur.execute("UPDATE relatorios SET status = ? WHERE codigo = ?",
                        (status, codigo))
            return cur.rowcount > 0

    # ---------- Código único do relatório ----------
    @staticmethod
    def _formatar_data_codigo(data_servico) -> str:
        """Converte a data do serviço para AAAAMMDD. Aceita 'dd/mm/aaaa'
        (formato do DateEntry), 'aaaa-mm-dd', 'dd-mm-aaaa', 'aaaaMMdd' ou
        objetos date/datetime. Data vazia/inválida cai para a data de hoje."""
        if isinstance(data_servico, datetime):
            d = data_servico.date()
        elif isinstance(data_servico, date):
            d = data_servico
        else:
            d = None
            texto = str(data_servico or "").strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"):
                try:
                    d = datetime.strptime(texto, fmt).date()
                    break
                except ValueError:
                    continue
            if d is None:
                d = date.today()
        return d.strftime("%Y%m%d")

    def obter_proximo_codigo_relatorio(self, data_servico_str=None) -> str:
        """Próximo código livre do dia: RMP-AAAAMMDD-NNN. Busca TODOS os
        códigos 'RMP-AAAAMMDD-%', pega o maior sufixo numérico e soma 1
        (001, 002, 003...). Sem nenhum no dia, retorna RMP-AAAAMMDD-001."""
        prefixo = f"RMP-{self._formatar_data_codigo(data_servico_str)}-"
        with get_cursor() as cur:
            cur.execute("SELECT codigo FROM relatorios WHERE codigo LIKE ?",
                        (prefixo + "%",))
            codigos = [row["codigo"] for row in cur.fetchall()]
        maior = 0
        for cod in codigos:
            sufixo = cod[len(prefixo):]
            if sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{prefixo}{maior + 1:03d}"

    def gerar_proximo_codigo(self) -> str:
        """Compatibilidade: próximo código livre para a data de hoje."""
        return self.obter_proximo_codigo_relatorio(date.today())

    # ---------- CRUD relatório ----------
    def buscar_por_codigo(self, codigo: str):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM relatorios WHERE codigo = ?", (codigo,))
            row = cur.fetchone()
            return dict(row) if row else None

    def buscar_por_id(self, relatorio_id: int):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM relatorios WHERE id = ?", (relatorio_id,))
            row = cur.fetchone()
        if not row:
            return None
        rel = dict(row)
        try:
            rel["secoes"] = json.loads(rel.get("secoes_json") or "[]")
        except (ValueError, TypeError):
            rel["secoes"] = []
        return rel

    def salvar(self, dados: dict) -> int:
        """UPSERT do relatório. Como `codigo` é UNIQUE no banco, um mesmo
        código nunca pode virar uma segunda linha (nem com outra REV):
          * código já existe -> UPDATE (inclui a nova revisão) e as tabelas
            filhas (fotos/strings/disjuntores/CA) são limpas para serem
            regravadas sem duplicar;
          * código não existe -> INSERT.
        Retorna o id do relatório."""
        existente = self.buscar_por_codigo(dados["codigo"])
        revisao = dados.get("revisao") or "01"
        secoes_json = json.dumps(dados.get("secoes", []))

        if existente:
            rid = existente["id"]
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """UPDATE relatorios SET
                       empresa_id = ?, cliente_id = ?, data_servico = ?,
                       responsavel_tecnico = ?, revisao = ?, texto_objetivo = ?,
                       texto_aplicacao = ?, texto_normas = ?, secoes_json = ?
                       WHERE id = ?""",
                    (dados["empresa_id"], dados["cliente_id"], dados.get("data_servico"),
                     dados.get("responsavel_tecnico"), revisao,
                     dados.get("texto_objetivo"), dados.get("texto_aplicacao"),
                     dados.get("texto_normas"), secoes_json, rid),
                )
                if dados.get("pdf_path"):
                    cur.execute("UPDATE relatorios SET pdf_path = ? WHERE id = ?",
                                (dados["pdf_path"], rid))
                for tabela in ("relatorio_fotos", "relatorio_strings",
                               "relatorio_ca_disjuntores", "relatorio_ca"):
                    cur.execute(f"DELETE FROM {tabela} WHERE relatorio_id = ?", (rid,))
            return rid

        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO relatorios
                   (codigo, empresa_id, cliente_id, data_servico, responsavel_tecnico,
                    revisao, texto_objetivo, texto_aplicacao, texto_normas,
                    secoes_json, pdf_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (dados["codigo"], dados["empresa_id"], dados["cliente_id"],
                 dados.get("data_servico"), dados.get("responsavel_tecnico"), revisao,
                 dados.get("texto_objetivo"), dados.get("texto_aplicacao"),
                 dados.get("texto_normas"), secoes_json, dados.get("pdf_path")),
            )
            return cur.lastrowid

    def criar(self, dados: dict) -> int:
        """Mantido por compatibilidade: delega para salvar() (INSERT/UPDATE)."""
        return self.salvar(dados)

    def atualizar_pdf_path(self, relatorio_id: int, pdf_path: str):
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE relatorios SET pdf_path = ? WHERE id = ?",
                (pdf_path, relatorio_id),
            )

    def listar(self):
        with get_cursor() as cur:
            cur.execute(
                """SELECT r.*, e.nome AS empresa_nome, c.nome_razao_social AS cliente_nome
                   FROM relatorios r
                   JOIN empresas e ON e.id = r.empresa_id
                   JOIN clientes c ON c.id = r.cliente_id
                   ORDER BY r.criado_em DESC"""
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- Fotos por seção ----------
    def adicionar_foto(self, relatorio_id: int, secao: str, foto_path: str,
                        legenda: str = "", ordem: int = 0):
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO relatorio_fotos
                   (relatorio_id, secao, foto_path, legenda, ordem)
                   VALUES (?, ?, ?, ?, ?)""",
                (relatorio_id, secao, foto_path, legenda, ordem),
            )

    def listar_fotos(self, relatorio_id: int, secao: str = None):
        with get_cursor() as cur:
            if secao:
                cur.execute(
                    """SELECT * FROM relatorio_fotos
                       WHERE relatorio_id = ? AND secao = ? ORDER BY ordem""",
                    (relatorio_id, secao),
                )
            else:
                cur.execute(
                    "SELECT * FROM relatorio_fotos WHERE relatorio_id = ? ORDER BY secao, ordem",
                    (relatorio_id,),
                )
            return [dict(r) for r in cur.fetchall()]

    # ---------- Tabela de Strings (conformidade elétrica) ----------
    def adicionar_string(self, relatorio_id: int, string_nome: str,
                          tensao_vcc: float, flut_pos: float, flut_neg: float,
                          status_tensao: str, status_flut_pos: str,
                          status_flut_neg: str, ordem: int = 0,
                          neutro_valor: float = None, status_neutro: str = "CONFORME"):
        """Cada parâmetro (Tensão de Operação, Flutuação +, Flutuação -) tem
        seu próprio status CONFORME/NAO_CONFORME, permitindo status mistos
        dentro da mesma String. O Teste de Neutro é opcional (só gravado
        quando a usina possui condutor neutro). A coluna legada `status` é
        preenchida com o status geral (CONFORME apenas se os parâmetros
        preenchidos estiverem CONFORME), mantida por compatibilidade."""
        parametros = [status_tensao, status_flut_pos, status_flut_neg]
        if neutro_valor is not None:
            parametros.append(status_neutro)
        status_geral = "CONFORME" if "NAO_CONFORME" not in parametros else "NAO_CONFORME"
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO relatorio_strings
                   (relatorio_id, string_nome, tensao_vcc, flutuacao_positivo,
                    flutuacao_negativo, status, status_tensao,
                    status_flutuacao_positivo, status_flutuacao_negativo,
                    neutro_valor, status_neutro, ordem)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (relatorio_id, string_nome, tensao_vcc, flut_pos, flut_neg,
                 status_geral, status_tensao, status_flut_pos, status_flut_neg,
                 neutro_valor, status_neutro, ordem),
            )

    def listar_strings(self, relatorio_id: int):
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM relatorio_strings WHERE relatorio_id = ? ORDER BY ordem",
                (relatorio_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- Bloco do Circuito de Corrente Alternada (CA) ----------
    def salvar_ca(self, relatorio_id: int, tensao_linha_valor, tensao_linha_status,
                  corrente_injecao_valor, corrente_injecao_status):
        """Salva (ou substitui) o único bloco CA do relatório. Chamar apenas
        quando ao menos um dos dois valores foi preenchido pelo usuário —
        o bloco CA é opcional na tabela de conformidade."""
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM relatorio_ca WHERE relatorio_id = ?", (relatorio_id,))
            cur.execute(
                """INSERT INTO relatorio_ca
                   (relatorio_id, tensao_linha_valor, tensao_linha_status,
                    corrente_injecao_valor, corrente_injecao_status)
                   VALUES (?, ?, ?, ?, ?)""",
                (relatorio_id, tensao_linha_valor, tensao_linha_status,
                 corrente_injecao_valor, corrente_injecao_status),
            )

    def buscar_ca(self, relatorio_id: int):
        with get_cursor() as cur:
            cur.execute("SELECT * FROM relatorio_ca WHERE relatorio_id = ?", (relatorio_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # ---------- Disjuntores do Circuito CA (múltiplos, com voltagem) ----------
    def adicionar_disjuntor(self, relatorio_id: int, nome: str, voltagem: str,
                             valor_medido, status: str, ordem: int = 0,
                             corrente_injecao_valor: float = None,
                             corrente_injecao_status: str = "CONFORME",
                             neutro_valor: float = None,
                             status_neutro: str = "CONFORME",
                             tipo: str = "Bifásico"):
        """Cada disjuntor tem o tipo (Bifásico/Trifásico) e exatamente 3
        medições, cada uma com seu status CONFORME/NAO_CONFORME:
          * Tensão de Linha (V)      -> valor_medido / status
          * Tensão de Fase (V)       -> neutro_valor / status_neutro
                                        (colunas reaproveitadas)
          * Corrente de Injeção (A)  -> corrente_injecao_valor / _status"""
        with get_cursor(commit=True) as cur:
            self._garantir_coluna_tipo_disjuntor(cur)
            cur.execute(
                """INSERT INTO relatorio_ca_disjuntores
                   (relatorio_id, nome, voltagem, valor_medido, status, ordem,
                    corrente_injecao_valor, corrente_injecao_status,
                    neutro_valor, status_neutro, tipo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (relatorio_id, nome, voltagem, valor_medido, status, ordem,
                 corrente_injecao_valor, corrente_injecao_status,
                 neutro_valor, status_neutro, tipo),
            )

    @staticmethod
    def _garantir_coluna_tipo_disjuntor(cur):
        """Migração idempotente: cria a coluna `tipo` (Bifásico/Trifásico)
        em relatorio_ca_disjuntores se o banco ainda não a tiver."""
        cur.execute("PRAGMA table_info(relatorio_ca_disjuntores)")
        if "tipo" not in [r["name"] for r in cur.fetchall()]:
            cur.execute("ALTER TABLE relatorio_ca_disjuntores "
                        "ADD COLUMN tipo TEXT DEFAULT 'Bifásico'")

    def listar_disjuntores(self, relatorio_id: int):
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM relatorio_ca_disjuntores WHERE relatorio_id = ? ORDER BY ordem",
                (relatorio_id,),
            )
            return [dict(r) for r in cur.fetchall()]
