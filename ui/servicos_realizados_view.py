"""
Módulo 6: Serviços Realizados — Dashboard financeiro.

Filtros por Empresa Prestadora e intervalo de datas; gráfico de barras
(matplotlib) com o total de orçamentos por empresa no período; tabela
lateral com o detalhamento dos atendimentos. Gera o Relatório de
Cobrança em PDF para a empresa selecionada.
"""
import os

import customtkinter as ctk
from tkcalendar import DateEntry
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from config import Marca
from models.empresa_dao import EmpresaDAO
from models.agenda_dao import AgendaDAO
from models.configuracao_dao import ConfiguracaoDAO
from pdf.relatorio_cobranca import gerar_relatorio_cobranca_pdf
from ui.components import mostrar_alerta, formatar_reais


def _sanitizar(nome: str) -> str:
    invalidos = '<>:"/\\|?*'
    for c in invalidos:
        nome = nome.replace(c, "-")
    return nome.strip() or "sem_nome"


class ServicosRealizadosView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.empresa_dao = EmpresaDAO()
        self.agenda_dao = AgendaDAO()
        self.config_dao = ConfiguracaoDAO()
        self._empresas_map = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_cabecalho()
        self._construir_corpo()

    # --------------------------------------------------------------- UI --
    def _construir_cabecalho(self):
        cabecalho = ctk.CTkFrame(self, corner_radius=14)
        cabecalho.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        ctk.CTkLabel(cabecalho, text="Serviços Realizados", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(16, 8))

        filtros = ctk.CTkFrame(cabecalho, fg_color="transparent")
        filtros.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(filtros, text="Empresa Prestadora", font=ctk.CTkFont(size=11)).grid(
            row=0, column=0, sticky="w"
        )
        self.combo_empresa = ctk.CTkComboBox(
            filtros, values=["Todas as Empresas"], width=220, command=lambda _: self._atualizar(),
        )
        self.combo_empresa.set("Todas as Empresas")
        self.combo_empresa.grid(row=1, column=0, sticky="w", padx=(0, 16))

        ctk.CTkLabel(filtros, text="Data Inicial", font=ctk.CTkFont(size=11)).grid(
            row=0, column=1, sticky="w"
        )
        self.date_inicio = DateEntry(
            filtros, width=12, date_pattern="dd/mm/yyyy",
            background=Marca.ACCENT, foreground="white", borderwidth=1,
        )
        self.date_inicio.grid(row=1, column=1, sticky="w", padx=(0, 16), ipady=3)
        self.date_inicio.bind("<<DateEntrySelected>>", lambda e: self._atualizar())

        ctk.CTkLabel(filtros, text="Data Final", font=ctk.CTkFont(size=11)).grid(
            row=0, column=2, sticky="w"
        )
        self.date_fim = DateEntry(
            filtros, width=12, date_pattern="dd/mm/yyyy",
            background=Marca.ACCENT, foreground="white", borderwidth=1,
        )
        self.date_fim.grid(row=1, column=2, sticky="w", padx=(0, 16), ipady=3)
        self.date_fim.bind("<<DateEntrySelected>>", lambda e: self._atualizar())

        ctk.CTkButton(
            filtros, text="📄 Gerar Relatório de Cobrança", fg_color=Marca.PRIMARIA,
            hover_color=Marca.PRIMARIA_CLARA, command=self._gerar_relatorio_cobranca,
        ).grid(row=1, column=3, sticky="w")

        self.label_total = ctk.CTkLabel(
            cabecalho, text="Total no período: R$ 0,00",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=Marca.SUCESSO_TEXTO,
        )
        self.label_total.pack(anchor="w", padx=18, pady=(0, 16))

    def _construir_corpo(self):
        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        corpo.grid_columnconfigure(0, weight=3)
        corpo.grid_columnconfigure(1, weight=2)
        corpo.grid_rowconfigure(0, weight=1)

        # ---- Gráfico (matplotlib embutido) ----
        self.frame_grafico = ctk.CTkFrame(corpo, corner_radius=14)
        self.frame_grafico.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(self.frame_grafico, text="Orçamentos por Empresa (R$)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=16, pady=(14, 4))
        self._canvas_grafico = None
        self._grafico_container = ctk.CTkFrame(self.frame_grafico, fg_color="transparent")
        self._grafico_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ---- Tabela lateral ----
        frame_tabela = ctk.CTkFrame(corpo, corner_radius=14)
        frame_tabela.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(frame_tabela, text="Serviços Realizados no Período",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=16, pady=(14, 8))
        self.lista_scroll = ctk.CTkScrollableFrame(frame_tabela, fg_color="transparent")
        self.lista_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 12))

    # ------------------------------------------------------------ dados --
    def _intervalo(self):
        inicio = self.date_inicio.get_date().isoformat()
        fim = self.date_fim.get_date().isoformat()
        if inicio > fim:
            inicio, fim = fim, inicio
        return inicio, fim

    def _empresa_selecionada_id(self):
        nome = self.combo_empresa.get()
        return self._empresas_map.get(nome)  # None quando "Todas as Empresas"

    def _atualizar(self):
        inicio, fim = self._intervalo()
        empresa_id = self._empresa_selecionada_id()

        servicos = self.agenda_dao.listar_servicos_realizados(empresa_id, inicio, fim)
        total = sum(s["valor_orcamento"] or 0 for s in servicos)
        self.label_total.configure(text=f"Total no período: {formatar_reais(total)}")

        self._atualizar_tabela(servicos)
        self._atualizar_grafico(inicio, fim)

    def _atualizar_tabela(self, servicos):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        if not servicos:
            ctk.CTkLabel(self.lista_scroll, text="Nenhum serviço no período selecionado.",
                         text_color="gray").pack(pady=20)
            return

        for s in servicos:
            card = ctk.CTkFrame(self.lista_scroll, corner_radius=8, fg_color=Marca.CINZA_TECNICO)
            card.pack(fill="x", pady=3, padx=2)
            ctk.CTkLabel(card, text=f"{s['data']}  •  {s['cliente_nome']}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Marca.PRIMARIA).pack(anchor="w", padx=10, pady=(8, 0))
            if s.get("descricao_servico"):
                ctk.CTkLabel(card, text=s["descricao_servico"], text_color="gray",
                             font=ctk.CTkFont(size=11), wraplength=220,
                             justify="left").pack(anchor="w", padx=10, pady=(2, 0))
            ctk.CTkLabel(card, text=formatar_reais(s["valor_orcamento"]),
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Marca.SUCESSO_TEXTO).pack(anchor="w", padx=10, pady=(2, 8))

    def _atualizar_grafico(self, inicio, fim):
        for w in self._grafico_container.winfo_children():
            w.destroy()

        totais = self.agenda_dao.totais_por_empresa(inicio, fim)

        fig = Figure(figsize=(5, 3.6), dpi=95)
        fig.patch.set_facecolor("#FFFFFF")
        ax = fig.add_subplot(111)

        if totais:
            nomes = [t["empresa_nome"] for t in totais]
            valores = [t["total"] or 0 for t in totais]
            barras = ax.bar(nomes, valores, color=Marca.ACCENT)
            ax.set_ylabel("R$", fontsize=9)
            ax.tick_params(axis="x", labelsize=8, rotation=15)
            ax.tick_params(axis="y", labelsize=8)
            for barra, valor in zip(barras, valores):
                ax.annotate(f"{valor:,.0f}", (barra.get_x() + barra.get_width() / 2,
                            barra.get_height()), ha="center", va="bottom", fontsize=8)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
        else:
            ax.text(0.5, 0.5, "Sem dados no período", ha="center", va="center",
                     fontsize=10, color="gray", transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])

        fig.tight_layout()

        self._canvas_grafico = FigureCanvasTkAgg(fig, master=self._grafico_container)
        self._canvas_grafico.draw()
        self._canvas_grafico.get_tk_widget().pack(fill="both", expand=True)

    # ------------------------------------------------------ relatório --
    def _gerar_relatorio_cobranca(self):
        empresa_id = self._empresa_selecionada_id()
        if not empresa_id:
            mostrar_alerta(
                self.winfo_toplevel(), "Selecione uma empresa",
                "Escolha uma Empresa Prestadora específica (não 'Todas as Empresas') "
                "para gerar o Relatório de Cobrança.", "aviso",
            )
            return

        empresa = self.empresa_dao.buscar_por_id(empresa_id)
        inicio, fim = self._intervalo()
        servicos = self.agenda_dao.listar_servicos_realizados(empresa_id, inicio, fim)
        total = sum(s["valor_orcamento"] or 0 for s in servicos)

        def fmt_data_br(iso):
            try:
                a, m, d = iso.split("-")
                return f"{d}/{m}/{a}"
            except Exception:
                return iso

        servicos_fmt = [{**s, "data": fmt_data_br(s["data"])} for s in servicos]

        pasta_raiz = self.config_dao.obter_pasta_relatorios()
        nome_pasta_empresa = f"{self.empresa_dao.codigo_exibicao(empresa)} - {empresa['nome']}"
        pasta_destino = os.path.join(
            pasta_raiz, _sanitizar(nome_pasta_empresa), "Serviços Realizados"
        )
        os.makedirs(pasta_destino, exist_ok=True)
        nome_arquivo = f"Cobranca_{fmt_data_br(inicio).replace('/', '')}_a_{fmt_data_br(fim).replace('/', '')}.pdf"
        caminho_pdf = os.path.join(pasta_destino, nome_arquivo)

        try:
            gerar_relatorio_cobranca_pdf(
                caminho_pdf, empresa["nome"], fmt_data_br(inicio), fmt_data_br(fim),
                servicos_fmt, total,
            )
        except Exception as exc:
            mostrar_alerta(self.winfo_toplevel(), "Erro ao gerar PDF", str(exc), "erro")
            return

        mostrar_alerta(
            self.winfo_toplevel(), "Relatório gerado",
            f"Relatório de Cobrança gerado com sucesso em:\n{caminho_pdf}", "sucesso",
        )

    def ao_exibir(self):
        empresas = self.empresa_dao.listar()
        self._empresas_map = {e["nome"]: e["id"] for e in empresas}
        self.combo_empresa.configure(values=["Todas as Empresas"] + list(self._empresas_map.keys()))
        self._atualizar()
