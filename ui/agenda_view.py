"""
Módulo 4: Agenda/Calendário e Gerador de Texto para WhatsApp.

O antigo seletor fixo ("Hoje" / "Amanhã" / "Esta Semana") foi substituído
por um seletor de INTERVALO de datas via calendário (DateEntry De/Até),
com atalhos rápidos para os períodos mais comuns. Datas/horas continuam
usando exclusivamente widgets de calendário e menus suspensos — nunca
texto livre.
"""
import datetime as dt

import customtkinter as ctk
from tkcalendar import DateEntry

from config import Marca
from models.cliente_dao import ClienteDAO
from models.empresa_dao import EmpresaDAO
from models.agenda_dao import AgendaDAO
from utils.whatsapp_generator import gerar_texto_whatsapp
from ui.components import (
    ModalWindow, criar_seletor_hora_minuto, mostrar_alerta, confirmar_exclusao,
    formatar_reais,
)


def _criar_seletor_intervalo(parent, on_mudar=None):
    """Cria um seletor De/Até (DateEntry) com atalhos Hoje/Amanhã/Semana.
    Retorna (frame, date_inicio, date_fim). `on_mudar` é chamado sempre
    que o intervalo muda (seleção manual ou atalho)."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")

    linha_datas = ctk.CTkFrame(frame, fg_color="transparent")
    linha_datas.pack(anchor="w")
    ctk.CTkLabel(linha_datas, text="De:", font=ctk.CTkFont(size=11)).pack(side="left")
    date_inicio = DateEntry(
        linha_datas, width=11, date_pattern="dd/mm/yyyy",
        background=Marca.ACCENT, foreground="white", borderwidth=1,
    )
    date_inicio.pack(side="left", padx=(4, 12), ipady=3)
    ctk.CTkLabel(linha_datas, text="Até:", font=ctk.CTkFont(size=11)).pack(side="left")
    date_fim = DateEntry(
        linha_datas, width=11, date_pattern="dd/mm/yyyy",
        background=Marca.ACCENT, foreground="white", borderwidth=1,
    )
    date_fim.pack(side="left", padx=(4, 0), ipady=3)

    def _disparar(*_):
        if on_mudar:
            on_mudar()

    date_inicio.bind("<<DateEntrySelected>>", _disparar)
    date_fim.bind("<<DateEntrySelected>>", _disparar)

    def aplicar_preset(dias_inicio, dias_fim):
        hoje = dt.date.today()
        date_inicio.set_date(hoje + dt.timedelta(days=dias_inicio))
        date_fim.set_date(hoje + dt.timedelta(days=dias_fim))
        _disparar()

    def dias_ate_domingo():
        hoje = dt.date.today()
        return 6 - hoje.weekday() if hoje.weekday() != 6 else 0

    atalhos = ctk.CTkFrame(frame, fg_color="transparent")
    atalhos.pack(anchor="w", pady=(6, 0))
    ctk.CTkButton(atalhos, text="Hoje", width=70, height=24, fg_color="gray40",
                  command=lambda: aplicar_preset(0, 0)).pack(side="left", padx=(0, 4))
    ctk.CTkButton(atalhos, text="Amanhã", width=70, height=24, fg_color="gray40",
                  command=lambda: aplicar_preset(1, 1)).pack(side="left", padx=4)
    ctk.CTkButton(atalhos, text="Esta Semana", width=90, height=24, fg_color="gray40",
                  command=lambda: aplicar_preset(0, dias_ate_domingo())).pack(side="left", padx=4)

    return frame, date_inicio, date_fim


class AgendaView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.cliente_dao = ClienteDAO()
        self.empresa_dao = EmpresaDAO()
        self.agenda_dao = AgendaDAO()
        self._empresas_map = {}
        self._clientes_map = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_painel_agendamento()
        self._construir_painel_lista()

    # --------------------------------------------------------------- UI --
    def _construir_painel_agendamento(self):
        frame = ctk.CTkFrame(self, corner_radius=14)
        frame.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=20)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Novo Agendamento",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(18, 10))

        ctk.CTkLabel(frame, text="Empresa Prestadora *", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.combo_empresa = ctk.CTkComboBox(
            frame, values=[], width=320, command=self._on_empresa_selecionada,
        )
        self.combo_empresa.set("")
        self.combo_empresa.pack(anchor="w", padx=18, pady=(2, 12), fill="x")

        ctk.CTkLabel(frame, text="Cliente *", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.combo_cliente = ctk.CTkComboBox(frame, values=[], width=320)
        self.combo_cliente.set("")
        self.combo_cliente.pack(anchor="w", padx=18, pady=(2, 12), fill="x")

        ctk.CTkLabel(frame, text="Data do Atendimento", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.date_entry = DateEntry(
            frame, width=18, date_pattern="yyyy-mm-dd",
            background=Marca.ACCENT, foreground="white", borderwidth=1,
        )
        self.date_entry.pack(anchor="w", padx=18, pady=(4, 14), ipady=4)

        ctk.CTkLabel(frame, text="Horário", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        hora_frame, self.menu_hora, self.menu_minuto = criar_seletor_hora_minuto(frame)
        hora_frame.pack(anchor="w", padx=18, pady=(4, 14))

        ctk.CTkLabel(frame, text="Ordem de Atendimento", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.menu_ordem = ctk.CTkOptionMenu(
            frame, values=[str(n) for n in range(1, 11)], width=100,
        )
        self.menu_ordem.set("1")
        self.menu_ordem.pack(anchor="w", padx=18, pady=(4, 14))

        ctk.CTkLabel(frame, text="Observações", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.entry_obs = ctk.CTkEntry(frame, width=320)
        self.entry_obs.pack(anchor="w", padx=18, pady=(2, 14), fill="x")

        ctk.CTkLabel(frame, text="Serviço a ser realizado", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.txt_descricao_servico = ctk.CTkTextbox(frame, height=60)
        self.txt_descricao_servico.pack(anchor="w", padx=18, pady=(2, 14), fill="x")

        ctk.CTkLabel(frame, text="Valor do Orçamento (R$)", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18
        )
        self.entry_valor_orcamento = ctk.CTkEntry(frame, width=180, placeholder_text="0,00")
        self.entry_valor_orcamento.pack(anchor="w", padx=18, pady=(2, 16))

        ctk.CTkButton(
            frame, text="Adicionar à Agenda", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._adicionar_agendamento,
        ).pack(anchor="w", padx=18, pady=(0, 18))

    def _construir_painel_lista(self):
        frame = ctk.CTkFrame(self, corner_radius=14)
        frame.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        topo = ctk.CTkFrame(frame, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 4))
        topo.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(topo, text="Atendimentos Agendados",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            topo, text="💬  Gerar Texto para Equipe", fg_color=Marca.PRIMARIA,
            hover_color=Marca.PRIMARIA_CLARA, command=self._abrir_modal_whatsapp,
        ).grid(row=0, column=1, sticky="e")

        seletor_frame, self.date_inicio_lista, self.date_fim_lista = _criar_seletor_intervalo(
            frame, on_mudar=self._carregar_lista,
        )
        seletor_frame.grid(row=1, column=0, sticky="w", padx=18, pady=(6, 8))

        self.lista_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self.lista_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 16))
        self.lista_scroll.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------ ações --
    def _on_empresa_selecionada(self, nome_empresa):
        empresa_id = self._empresas_map.get(nome_empresa)
        clientes = self.cliente_dao.listar(empresa_id=empresa_id) if empresa_id else []
        self._clientes_map = {c["nome_razao_social"]: c["id"] for c in clientes}
        if clientes:
            self.combo_cliente.configure(values=list(self._clientes_map.keys()))
        else:
            self.combo_cliente.configure(values=["Nenhum cliente para esta empresa"])
        self.combo_cliente.set("")

    def _adicionar_agendamento(self):
        nome_cliente = self.combo_cliente.get()
        cliente_id = self._clientes_map.get(nome_cliente) if hasattr(self, "_clientes_map") else None
        if not cliente_id:
            mostrar_alerta(self.winfo_toplevel(), "Campo obrigatório",
                            "Selecione um cliente.", "aviso")
            return

        data = self.date_entry.get_date().isoformat()
        hora = f"{self.menu_hora.get()}:{self.menu_minuto.get()}"
        ordem = int(self.menu_ordem.get())
        descricao_servico = self.txt_descricao_servico.get("1.0", "end").strip()

        texto_valor = self.entry_valor_orcamento.get().strip()
        valor_orcamento = None
        if texto_valor:
            try:
                valor_orcamento = float(
                    texto_valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
                )
            except ValueError:
                mostrar_alerta(self.winfo_toplevel(), "Valor inválido",
                                "Informe o Valor do Orçamento em formato numérico (ex: 1500,00).",
                                "erro")
                return

        self.agenda_dao.criar(
            cliente_id, data, hora, ordem, self.entry_obs.get().strip(),
            descricao_servico, valor_orcamento,
        )
        mostrar_alerta(
            self.winfo_toplevel(), "Agendamento criado",
            f"{nome_cliente} agendado para {data} às {hora}.", "sucesso",
        )
        self.entry_obs.delete(0, "end")
        self.txt_descricao_servico.delete("1.0", "end")
        self.entry_valor_orcamento.delete(0, "end")
        self._carregar_lista()

    def _excluir_agendamento(self, agenda_id):
        self.agenda_dao.excluir(agenda_id)
        # Recarrega a lista imediatamente — qualquer aba de Serviços
        # Realizados/gráfico financeiro aberta também relê do banco na
        # próxima exibição (ao_exibir), refletindo o orçamento excluído.
        self._carregar_lista()

    def _carregar_lista(self):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        inicio = self.date_inicio_lista.get_date().isoformat()
        fim = self.date_fim_lista.get_date().isoformat()
        if inicio > fim:
            inicio, fim = fim, inicio  # tolera o usuário invertendo De/Até
        agendamentos = self.agenda_dao.listar_por_periodo(inicio, fim)

        if not agendamentos:
            ctk.CTkLabel(self.lista_scroll, text="Nenhum atendimento agendado neste período.",
                         text_color="gray").pack(pady=20)
            return

        for ag in agendamentos:
            card = ctk.CTkFrame(self.lista_scroll, corner_radius=10)
            card.pack(fill="x", pady=4, padx=4)
            card.grid_columnconfigure(0, weight=1)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=0, sticky="w", padx=14, pady=10)
            ctk.CTkLabel(
                info, text=f"#{ag.get('ordem_atendimento', 1)}  •  {ag['cliente_nome']}",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(anchor="w")
            linha_sub = f"{ag['data']}"
            if ag.get("hora"):
                linha_sub += f"  às  {ag['hora']}"
            ctk.CTkLabel(info, text=linha_sub, text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            if ag.get("endereco"):
                ctk.CTkLabel(info, text=ag["endereco"], text_color="gray",
                             font=ctk.CTkFont(size=11)).pack(anchor="w")
            if ag.get("descricao_servico"):
                ctk.CTkLabel(info, text=ag["descricao_servico"], text_color="gray",
                             font=ctk.CTkFont(size=11), wraplength=280,
                             justify="left").pack(anchor="w", pady=(2, 0))
            if ag.get("valor_orcamento") is not None:
                ctk.CTkLabel(info, text=formatar_reais(ag["valor_orcamento"]),
                             text_color=Marca.SUCESSO_TEXTO,
                             font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(2, 0))

            ctk.CTkButton(
                card, text="Excluir", width=70, fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                command=lambda aid=ag["id"], nome=ag["cliente_nome"]: confirmar_exclusao(
                    self.winfo_toplevel(), f"agendamento de {nome}",
                    lambda: self._excluir_agendamento(aid),
                ),
            ).grid(row=0, column=1, sticky="e", padx=14)

    # ------------------------------------------------------ modal whats --
    def _abrir_modal_whatsapp(self):
        modal = ModalWindow(
            self.winfo_toplevel(), "Gerar Texto para Equipe", width=560, height=600
        )

        ctk.CTkLabel(modal.body, text="Período do Roteiro", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20, pady=(16, 0)
        )
        seletor_frame, date_inicio_modal, date_fim_modal = _criar_seletor_intervalo(modal.body)
        seletor_frame.pack(anchor="w", padx=20, pady=(4, 14))

        texto_resultado = ctk.CTkTextbox(modal.body, height=280)
        texto_resultado.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        def gerar():
            inicio = date_inicio_modal.get_date().isoformat()
            fim = date_fim_modal.get_date().isoformat()
            if inicio > fim:
                inicio, fim = fim, inicio
            agendamentos = self.agenda_dao.listar_por_periodo(inicio, fim)
            texto = gerar_texto_whatsapp(agendamentos)
            texto_resultado.delete("1.0", "end")
            texto_resultado.insert("1.0", texto)

        def copiar():
            texto = texto_resultado.get("1.0", "end").strip()
            if texto:
                modal.clipboard_clear()
                modal.clipboard_append(texto)
                mostrar_alerta(modal, "Copiado",
                                "Texto copiado para a área de transferência.", "sucesso")

        botoes = ctk.CTkFrame(modal.body, fg_color="transparent")
        botoes.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(botoes, text="Gerar", fg_color=Marca.PRIMARIA,
                      hover_color=Marca.PRIMARIA_CLARA, command=gerar).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(botoes, text="📋 Copiar Texto", fg_color=Marca.ACCENT,
                      hover_color=Marca.ACCENT_HOVER, command=copiar).pack(side="left")

        gerar()  # já gera o texto do período padrão (hoje) ao abrir

    def ao_exibir(self):
        self._empresas_map = {e["nome"]: e["id"] for e in self.empresa_dao.listar()}
        self.combo_empresa.configure(values=list(self._empresas_map.keys()))
        self._carregar_lista()
