"""DAO de Relatórios: cabeçalho, fotos por seção, tabela de strings e bloco CA."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

from database.db import get_cursor
from utils.retry import com_retry, pular_se_cursor_externo


STATUS_REL_PENDENTE = "Pendente"
STATUS_REL_APROVADO = "Aprovado"
STATUS_REL_REPROVADO = "Reprovado"


TIPO_REL_LIMPEZA = "limpeza"
TIPO_REL_TROCA = "troca_microinversor"

_TABELAS_FILHAS = ("relatorio_fotos", "relatorio_strings",
                   "relatorio_ca_disjuntores", "relatorio_ca")


class RelatorioDAO:
    # ---------- Transação atômica ----------
    @staticmethod
    @contextmanager
    def _transacao():
        """UMA conexão, UM commit no final. Qualquer exceção dentro do bloco
        dispara rollback explícito e é relançada: nada fica gravado pela metade
        (sem relatório sem filhos, strings órfãs etc.)."""
        with get_cursor(commit=True) as cur:
            try:
                yield cur
            except Exception:
                try:
                    cur.connection.rollback()
                except Exception:
                    pass   # conexão morta (ex.: pós-hibernação): o erro original é o que importa
                raise

    @classmethod
    @contextmanager
    def _usar_cursor(cls, cur=None):
        """Usa o cursor recebido (faz parte de uma transação maior, quem abriu
        é quem comita) ou abre uma transação própria."""
        if cur is not None:
            yield cur
        else:
            with cls._transacao() as novo:
                yield novo

    # ---------- Status de aprovação (usado pelo bot do Telegram) ----------
    @staticmethod
    def _garantir_coluna_status(cur):
        """Cria a coluna `status` em `relatorios` se ainda não existir
        (migração idempotente — bancos antigos continuam funcionando)."""
        cur.execute("PRAGMA table_info(relatorios)")
        if "status" not in [r["name"] for r in cur.fetchall()]:
            cur.execute("ALTER TABLE relatorios ADD COLUMN status TEXT DEFAULT 'Pendente'")

    @com_retry()
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

    def _upsert_relatorio(self, cur, dados: dict, tipo: str = None,
                          extras: dict = None) -> int:
        """UPSERT do cabeçalho usando o cursor da transação em curso.
        `codigo` é UNIQUE: mesmo código nunca vira 2ª linha (nem com outra REV).
          * já existe -> UPDATE (inclui a nova revisão) e limpa as tabelas
            filhas para serem regravadas sem duplicar;
          * não existe -> INSERT.
        `tipo` grava `tipo_relatorio`; `extras` ({coluna: valor}) grava colunas
        adicionais já existentes (ex.: dados_troca_json). O código do relatório
        NUNCA é alterado aqui. Retorna o id."""
        revisao = dados.get("revisao") or "01"
        secoes_json = json.dumps(dados.get("secoes", []))
        if tipo or extras:
            self._garantir_colunas_troca(cur)

        cur.execute("SELECT id FROM relatorios WHERE codigo = ?", (dados["codigo"],))
        row = cur.fetchone()
        if row:
            rid = row["id"]
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
            for tabela in _TABELAS_FILHAS:
                cur.execute(f"DELETE FROM {tabela} WHERE relatorio_id = ?", (rid,))
        else:
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
            rid = cur.lastrowid

        if tipo:
            cur.execute("UPDATE relatorios SET tipo_relatorio = ? WHERE id = ?", (tipo, rid))
        for coluna, valor in (extras or {}).items():      # nomes fixos, definidos aqui
            cur.execute(f"UPDATE relatorios SET {coluna} = ? WHERE id = ?", (valor, rid))
        return rid

    @com_retry()
    def salvar(self, dados: dict) -> int:
        """UPSERT atômico do relatório (ver _upsert_relatorio). Uma conexão,
        um commit; erro => rollback e a exceção sobe para quem chamou."""
        with self._transacao() as cur:
            return self._upsert_relatorio(cur, dados)

    @com_retry()
    def salvar_completo(self, dados: dict, fotos=(), strings=(), disjuntores=(),
                        ca=None, troca: dict = None) -> int:
        """Grava cabeçalho + filhas numa ÚNICA transação (tudo ou nada).
        Cada item é um dict com os mesmos nomes de argumento dos métodos
        adicionar_*:
          fotos:       [{secao, foto_path, legenda?, ordem?}]
          strings:     [{string_nome, tensao_vcc, flut_pos, flut_neg, status_tensao,
                         status_flut_pos, status_flut_neg, ordem?, neutro_valor?,
                         status_neutro?}]
          disjuntores: [{nome, voltagem, valor_medido, status, ordem?, ...}]
          ca:          {tensao_linha_valor, tensao_linha_status,
                        corrente_injecao_valor, corrente_injecao_status} | None
          troca:       dict do relatório de troca (grava dados_troca_json)
        Falhou em qualquer item => rollback de tudo; nada fica órfão."""
        with self._transacao() as cur:
            if troca is not None:
                rid = self._salvar_troca_cur(cur, dados, troca)
            else:
                rid = self._upsert_relatorio(cur, dados)
            for f in fotos:
                self.adicionar_foto(rid, cur=cur, **f)
            for s in strings:
                self.adicionar_string(rid, cur=cur, **s)
            for d in disjuntores:
                self.adicionar_disjuntor(rid, cur=cur, **d)
            if ca:
                self.salvar_ca(rid, cur=cur, **ca)
            return rid

    # ---------- Relatório de Troca de Microinversor ----------
    @staticmethod
    def _garantir_colunas_troca(cur):
        """Migração idempotente: `tipo_relatorio` e `dados_troca_json`."""
        cur.execute("PRAGMA table_info(relatorios)")
        existentes = {r["name"] for r in cur.fetchall()}
        if "tipo_relatorio" not in existentes:
            cur.execute("ALTER TABLE relatorios ADD COLUMN tipo_relatorio "
                        "TEXT DEFAULT 'limpeza'")
        if "dados_troca_json" not in existentes:
            cur.execute("ALTER TABLE relatorios ADD COLUMN dados_troca_json TEXT")

    def _salvar_troca_cur(self, cur, dados_relatorio: dict, dados_troca: dict) -> int:
        return self._upsert_relatorio(
            cur, dados_relatorio, tipo=TIPO_REL_TROCA,
            extras={"dados_troca_json": json.dumps(dados_troca or {},
                                                   ensure_ascii=False)})

    @com_retry()
    def salvar_troca(self, dados_relatorio: dict, dados_troca: dict) -> int:
        """Salva/atualiza o relatório (tipo 'troca_microinversor') e grava
        `dados_troca` serializado em `dados_troca_json`, tudo atômico.
        Retorna o id do relatório."""
        with self._transacao() as cur:
            return self._salvar_troca_cur(cur, dados_relatorio, dados_troca)

    def carregar_troca(self, relatorio_id: int) -> dict:
        """Dicionário salvo em `dados_troca_json`; {} se o relatório não
        existir, o campo estiver nulo/vazio ou o JSON for inválido."""
        try:
            with get_cursor() as cur:
                cur.execute("SELECT * FROM relatorios WHERE id = ?", (relatorio_id,))
                row = cur.fetchone()
        except sqlite3.Error:
            return {}
        if not row:
            return {}
        bruto = dict(row).get("dados_troca_json")
        if not bruto:
            return {}
        try:
            dados = json.loads(bruto)
        except (ValueError, TypeError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def criar(self, dados: dict) -> int:
        """Mantido por compatibilidade: delega para salvar() (INSERT/UPDATE)."""
        return self.salvar(dados)

    @com_retry()
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
    @com_retry(pular_se=pular_se_cursor_externo)
    def adicionar_foto(self, relatorio_id: int, secao: str, foto_path: str,
                        legenda: str = "", ordem: int = 0, cur=None):
        with self._usar_cursor(cur) as cur:
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
    @com_retry(pular_se=pular_se_cursor_externo)
    def adicionar_string(self, relatorio_id: int, string_nome: str,
                          tensao_vcc: float, flut_pos: float, flut_neg: float,
                          status_tensao: str, status_flut_pos: str,
                          status_flut_neg: str, ordem: int = 0,
                          neutro_valor: float = None, status_neutro: str = "CONFORME",
                          inversor_nome: str = None, inversor_foto_path: str = None,
                          cur=None):
        """Cada parâmetro (Tensão de Operação, Flutuação +, Flutuação -) tem
        seu próprio status CONFORME/NAO_CONFORME, permitindo status mistos
        dentro da mesma String. O Teste de Neutro é opcional (só gravado
        quando a usina possui condutor neutro). A coluna legada `status` é
        preenchida com o status geral (CONFORME apenas se os parâmetros
        preenchidos estiverem CONFORME), mantida por compatibilidade.

        `inversor_nome` ('Inversor 01'...) associa a string ao inversor e
        `inversor_foto_path` guarda o caminho da foto da etiqueta desse
        inversor (repetido nas strings do mesmo inversor)."""
        parametros = [status_tensao, status_flut_pos, status_flut_neg]
        if neutro_valor is not None:
            parametros.append(status_neutro)
        status_geral = "CONFORME" if "NAO_CONFORME" not in parametros else "NAO_CONFORME"
        with self._usar_cursor(cur) as cur:
            self._garantir_colunas_inversor(cur)
            cur.execute(
                """INSERT INTO relatorio_strings
                   (relatorio_id, string_nome, tensao_vcc, flutuacao_positivo,
                    flutuacao_negativo, status, status_tensao,
                    status_flutuacao_positivo, status_flutuacao_negativo,
                    neutro_valor, status_neutro, ordem,
                    inversor_nome, inversor_foto_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (relatorio_id, string_nome, tensao_vcc, flut_pos, flut_neg,
                 status_geral, status_tensao, status_flut_pos, status_flut_neg,
                 neutro_valor, status_neutro, ordem,
                 inversor_nome, inversor_foto_path),
            )

    @staticmethod
    def _garantir_colunas_inversor(cur):
        """Migração idempotente: `inversor_nome` e `inversor_foto_path` em
        relatorio_strings (bancos antigos continuam funcionando)."""
        cur.execute("PRAGMA table_info(relatorio_strings)")
        existentes = {r["name"] for r in cur.fetchall()}
        for coluna in ("inversor_nome", "inversor_foto_path"):
            if coluna not in existentes:
                cur.execute(f"ALTER TABLE relatorio_strings ADD COLUMN {coluna} TEXT")

    def listar_strings(self, relatorio_id: int):
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM relatorio_strings WHERE relatorio_id = ? ORDER BY ordem",
                (relatorio_id,),
            )
            linhas = [dict(r) for r in cur.fetchall()]
        # Sempre traz as chaves do inversor (None em relatórios antigos).
        for linha in linhas:
            linha.setdefault("inversor_nome", None)
            linha.setdefault("inversor_foto_path", None)
        return linhas

    # ---------- Bloco do Circuito de Corrente Alternada (CA) ----------
    @com_retry(pular_se=pular_se_cursor_externo)
    def salvar_ca(self, relatorio_id: int, tensao_linha_valor, tensao_linha_status,
                  corrente_injecao_valor, corrente_injecao_status, cur=None):
        """Salva (ou substitui) o único bloco CA do relatório. Chamar apenas
        quando ao menos um dos dois valores foi preenchido pelo usuário —
        o bloco CA é opcional na tabela de conformidade."""
        with self._usar_cursor(cur) as cur:
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
    @com_retry(pular_se=pular_se_cursor_externo)
    def adicionar_disjuntor(self, relatorio_id: int, nome: str, voltagem: str,
                             valor_medido, status: str, ordem: int = 0,
                             corrente_injecao_valor: float = None,
                             corrente_injecao_status: str = "CONFORME",
                             neutro_valor: float = None,
                             status_neutro: str = "CONFORME",
                             tipo: str = "Bifásico", cur=None):
        """Cada disjuntor tem o tipo (Bifásico/Trifásico) e exatamente 3
        medições, cada uma com seu status CONFORME/NAO_CONFORME:
          * Tensão de Linha (V)      -> valor_medido / status
          * Tensão de Fase (V)       -> neutro_valor / status_neutro
                                        (colunas reaproveitadas)
          * Corrente de Injeção (A)  -> corrente_injecao_valor / _status"""
        with self._usar_cursor(cur) as cur:
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
