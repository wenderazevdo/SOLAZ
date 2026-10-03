"""
Módulo 3: Construtor de Relatório Modular — Cards Visuais.

Cada seção do relatório é um card com Switch (ativo/inativo) e setas ▲▼
para reordenação. Inclui o construtor de Strings/medições elétricas com
seletor visual Conforme/Não Conforme (pílulas coloridas), o bloco opcional
do Circuito CA, busca rápida (lupa) de Empresa/Cliente e filtragem
dinâmica de clientes por empresa selecionada.
"""
import functools
import logging
import os
import re
import sys
from datetime import datetime

import customtkinter as ctk
from tkcalendar import DateEntry
from tkinter import filedialog

from config import (
    TEXTO_OBJETIVO_PADRAO, TEXTO_APLICACAO_PADRAO,
    TEXTO_NORMAS_PADRAO, Marca,
)
from models.empresa_dao import EmpresaDAO
from models.cliente_dao import ClienteDAO
from models.relatorio_dao import RelatorioDAO, STATUS_REL_PENDENTE
from services.telegram_service import notificar_relatorio_para_aprovacao
from models.configuracao_dao import ConfiguracaoDAO
from utils.image_utils import criar_pasta_temporaria, salvar_foto_temporaria, limpar_pasta_temporaria
from pdf.report_generator import gerar_relatorio_pdf, NOMES_SECOES
from ui.components import mostrar_alerta, criar_seletor_hora_minuto, abrir_busca_modal

_SECOES_FOTO = [
    "modulos_sujos", "modulos_limpos", "reaperto_parafusos",
    "teste_tensao_cc", "teste_tensao_ca", "geracao_energia",
    "sugestoes_melhorias",
]
_SECAO_TABELA = "tabela_conformidade"

_TITULOS_TOPO_FOTO = {
    "modulos_sujos": ("ANTERIOR À LIMPEZA (Módulos Sujos)", "#C2410C"),
    "modulos_limpos": ("POSTERIOR À LIMPEZA (Módulos Limpos)", "#15803D"),
}

# O número é só um marcador ("Figura X:"): _reindexar_figuras() troca pelo
# número sequencial real de acordo com a posição da foto no relatório.
_LEGENDAS_PADRAO_FOTO = {
    "modulos_sujos": "Figura X: Presença de poeira espessa e resíduos orgânicos.",
    "modulos_limpos": "Figura X: Superfície de captação limpa e desobstruída.",
    "reaperto_parafusos": "Figura X: Reaperto de parafusos e bornes no circuito CA.",
    "teste_tensao_cc": "Figura X: Medição e teste de tensão de circuito aberto (CC).",
    "teste_tensao_ca": "Figura X: Medição e teste de tensão de circuito de corrente alternada (CA).",
}

# Seções cujas fotos entram na numeração única "Figura 1, 2, 3..." (os
# gráficos de geração e as sugestões têm legenda própria, sem número).
_SECOES_NUMERADAS = {
    "modulos_sujos", "modulos_limpos", "reaperto_parafusos",
    "teste_tensao_cc", "teste_tensao_ca",
}
_RE_PREFIXO_FIGURA = re.compile(r"^\s*Figura\s+(?:\d+|X)\s*:\s*", re.IGNORECASE)

_VOLTAGENS_DISJUNTOR = ["127V", "220V", "380V", "Outra"]
_TIPOS_DISJUNTOR = ["Bifásico", "Trifásico"]

_STATUS_ROTULOS = {
    "tensao": "Tensão de Operação",
    "flut_pos": "Teste Flutuação (+) / Terra",
    "flut_neg": "Teste Flutuação (−) / Terra",
    "neutro": "Teste de Neutro",
}


class _ScrollSuave(ctk.CTkScrollableFrame):
    """CTkScrollableFrame com rolagem do mouse suave.

    O padrão do customtkinter rola ~20 'units' (centenas de px) por clique
    da roda e redesenha a cada evento — daí os "pulinhos". Aqui:
      * o canvas passa a rolar em PIXELS (yscrollincrement=1);
      * a roda é acumulada e aplicada em passos pequenos com easing, a
        cada ~10 ms, em vez de um redesenho por evento <MouseWheel>;
      * o handler original (`_mouse_wheel_all`) é neutralizado.
    """
    PIXELS_POR_CLIQUE = 55      # distância por "clique" da roda (Windows: delta 120)
    INTERVALO_MS = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pendente = 0.0
        self._animando = False
        self.contador_roda = 0   # sobe a cada gesto do usuário (cancela restaurações de scroll)
        self._parent_canvas.configure(yscrollincrement=1)
        self.bind_all("<MouseWheel>", self._ao_girar_roda, add="+")
        if sys.platform.startswith("linux"):
            self.bind_all("<Button-4>", lambda e: self._ao_girar_roda(e, +120), add="+")
            self.bind_all("<Button-5>", lambda e: self._ao_girar_roda(e, -120), add="+")

    def _mouse_wheel_all(self, event):      # neutraliza o handler original
        return

    def _evento_e_meu(self, event):
        w = event.widget
        if isinstance(w, str):
            try:
                w = self.nametowidget(w)
            except Exception:
                return False
        while w is not None:
            if w is self or w is self._parent_canvas:
                return True
            w = getattr(w, "master", None)
        return False

    def _ao_girar_roda(self, event, delta=None):
        if not self._evento_e_meu(event):
            return
        if self._parent_canvas.yview() == (0.0, 1.0):   # conteúdo cabe: nada a rolar
            return
        delta = event.delta if delta is None else delta
        if sys.platform == "darwin":
            px = -delta * 4
        else:
            px = -(delta / 120.0) * self.PIXELS_POR_CLIQUE
        self.contador_roda += 1
        self._pendente += px
        if not self._animando:
            self._animando = True
            self.after(self.INTERVALO_MS, self._passo)

    def _passo(self):
        pend = self._pendente
        if abs(pend) < 1:
            self._pendente, self._animando = 0.0, False
            return
        inteiro = int(pend * 0.35) or (1 if pend > 0 else -1)
        self._pendente -= inteiro
        topo, base = self._parent_canvas.yview()
        if (inteiro < 0 and topo <= 0.0) or (inteiro > 0 and base >= 1.0):
            self._pendente, self._animando = 0.0, False   # chegou na borda
            return
        self._parent_canvas.yview_scroll(inteiro, "units")
        self.after(self.INTERVALO_MS, self._passo)


def _mantem_scroll(metodo):
    """Decorador: executa o método e devolve a rolagem EXATAMENTE para onde
    estava (em pixels) — evita a tela "pular" quando o conteúdo é refeito."""
    @functools.wraps(metodo)
    def interno(self, *args, **kwargs):
        return self._com_scroll_preservado(metodo, self, *args, **kwargs)
    return interno


class RelatorioView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.empresa_dao = EmpresaDAO()
        self.cliente_dao = ClienteDAO()
        self.relatorio_dao = RelatorioDAO()
        self.config_dao = ConfiguracaoDAO()

        self.ordem_secoes = list(_SECOES_FOTO) + [_SECAO_TABELA]
        self.secoes_ativas_vars = {s: ctk.BooleanVar(value=False) for s in self.ordem_secoes}
        self.fotos_por_secao = {s: [] for s in _SECOES_FOTO}
        self.strings_rows = []
        self.disjuntores_rows = []
        # id do relatório carregado para edição (None = relatório novo).
        self._relatorio_editando_id = None

        # Teste de Neutro: opcional, aplicável a Strings e disjuntores do
        # Circuito CA quando a usina possui condutor neutro. Um único
        # switch controla a visibilidade do 4º campo em ambos os blocos.
        self.possui_neutro_var = ctk.BooleanVar(value=False)

        self._empresas_cache = []
        self._empresas_map = {}
        self._clientes_map = {}
        self._clientes_atuais = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_ui()
        self._sem_foco_por_tab(self)

    # --------------------------------------------------------------- UI --
    def _construir_ui(self):
        scroll = _ScrollSuave(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scroll.grid_columnconfigure(0, weight=1)
        self.scroll = scroll

        cabecalho = ctk.CTkFrame(scroll, corner_radius=14)
        cabecalho.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(cabecalho, text="Dados do Relatório",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(16, 10))

        linha1 = ctk.CTkFrame(cabecalho, fg_color="transparent")
        linha1.pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(linha1, text="Empresa Prestadora *", width=200, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(linha1, text="Cliente *", width=200, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(20, 0)
        )

        bloco_empresa = ctk.CTkFrame(linha1, fg_color="transparent")
        bloco_empresa.grid(row=1, column=0, sticky="w")
        self.combo_empresa = ctk.CTkComboBox(
            bloco_empresa, values=[], width=250, command=self._on_empresa_selecionada,
        )
        self.combo_empresa.set("")
        self.combo_empresa.pack(side="left")
        ctk.CTkButton(
            bloco_empresa, text="🔍", width=34, fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._abrir_busca_empresa,
        ).pack(side="left", padx=(6, 0))

        bloco_cliente = ctk.CTkFrame(linha1, fg_color="transparent")
        bloco_cliente.grid(row=1, column=1, sticky="w", padx=(20, 0))
        self.combo_cliente = ctk.CTkComboBox(
            bloco_cliente, values=[], width=250, command=self._recalcular_codigo,
        )
        self.combo_cliente.set("")
        self.combo_cliente.pack(side="left")
        ctk.CTkButton(
            bloco_cliente, text="🔍", width=34, fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._abrir_busca_cliente,
        ).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            linha1, text="A lista de clientes é filtrada pela empresa escolhida.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=2, column=1, sticky="w", padx=(20, 0), pady=(3, 0))

        linha2 = ctk.CTkFrame(cabecalho, fg_color="transparent")
        linha2.pack(fill="x", padx=18, pady=(10, 4))
        ctk.CTkLabel(linha2, text="Data do Serviço", width=200, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(linha2, text="Responsável Técnico", width=200, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(20, 0)
        )
        self.data_servico_entry = DateEntry(
            linha2, width=17, date_pattern="dd/mm/yyyy",
            background=Marca.ACCENT, foreground="white", borderwidth=1,
        )
        self.data_servico_entry.grid(row=1, column=0, sticky="w", ipady=3)
        self.data_servico_entry.bind("<<DateEntrySelected>>", self._recalcular_codigo)
        self.data_servico_entry.bind("<FocusOut>", self._recalcular_codigo)
        self.entry_responsavel = ctk.CTkEntry(linha2, width=300)
        self.entry_responsavel.grid(row=1, column=1, sticky="w", padx=(20, 0))

        rodape_cabecalho = ctk.CTkFrame(cabecalho, fg_color="transparent")
        rodape_cabecalho.pack(fill="x", padx=18, pady=(12, 16))
        ctk.CTkLabel(rodape_cabecalho, text="Código do Relatório:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        # Somente leitura: o código é sempre gerado pelo sistema (próximo
        # número livre do dia), evitando códigos repetidos digitados à mão.
        self.entry_codigo = ctk.CTkEntry(
            rodape_cabecalho, width=190, justify="center",
            text_color=Marca.ACCENT, font=ctk.CTkFont(weight="bold"),
        )
        self.entry_codigo.pack(side="left", padx=(8, 24))
        self._definir_codigo(
            self.relatorio_dao.obter_proximo_codigo_relatorio(self.data_servico_entry.get())
        )

        ctk.CTkLabel(rodape_cabecalho, text="Revisão (REV):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.entry_revisao = ctk.CTkEntry(rodape_cabecalho, width=60)
        self.entry_revisao.insert(0, "01")
        self.entry_revisao.pack(side="left", padx=(8, 0))

        textos_frame = ctk.CTkFrame(scroll, corner_radius=14)
        textos_frame.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(textos_frame, text="Objetivo, Aplicação e Normas de Referência",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(16, 8))
        self.txt_objetivo = self._textbox_com_rotulo(
            textos_frame, "Objetivo", TEXTO_OBJETIVO_PADRAO
        )
        self.txt_aplicacao = self._textbox_com_rotulo(
            textos_frame, "Aplicação", TEXTO_APLICACAO_PADRAO
        )
        self.txt_normas = self._textbox_com_rotulo(
            textos_frame, "Normas de Referência", TEXTO_NORMAS_PADRAO, ultimo=True
        )

        secoes_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        secoes_frame.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(secoes_frame, text="Seções do Relatório",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            secoes_frame, text="Ative apenas as etapas realizadas e use ▲▼ para reordenar.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=4, pady=(0, 10))
        self.secoes_container = ctk.CTkFrame(secoes_frame, fg_color="transparent")
        self.secoes_container.pack(fill="x")
        self._renderizar_secoes()

        ctk.CTkButton(
            scroll, text="📄  Gerar Relatório em PDF", height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
            command=self._gerar_relatorio,
        ).pack(fill="x", pady=(4, 30))

    def _textbox_com_rotulo(self, parent, rotulo, texto_padrao, ultimo=False):
        ctk.CTkLabel(parent, text=rotulo, font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18, pady=(6, 0)
        )
        box = ctk.CTkTextbox(parent, height=70)
        box.pack(fill="x", padx=18, pady=(2, 16 if ultimo else 4))
        box.insert("1.0", texto_padrao)
        return box

    # ------------------------------------------ scroll / foco (estabilidade) --
    _CLASSES_DE_TEXTO = {"Entry", "Text", "TEntry", "TCombobox", "Spinbox"}

    def _canvas_scroll(self):
        scroll = getattr(self, "scroll", None)
        return getattr(scroll, "_parent_canvas", None)

    def _com_scroll_preservado(self, fn, *args, **kwargs):
        """Roda `fn` e restaura a posição de rolagem (em pixels)."""
        canvas = self._canvas_scroll()
        topo = canvas.canvasy(0) if canvas is not None else None
        try:
            return fn(*args, **kwargs)
        finally:
            if canvas is not None:
                self._restaurar_scroll(topo)

    def _preservar_scroll(self, fn):
        """Versão para closures (listas internas dos cards)."""
        @functools.wraps(fn)
        def interno(*args, **kwargs):
            return self._com_scroll_preservado(fn, *args, **kwargs)
        return interno

    def _restaurar_scroll(self, topo):
        canvas = self._canvas_scroll()
        if canvas is None or topo is None:
            return
        gesto = self.scroll.contador_roda

        def aplicar(checar=False):
            # se o usuário girou a roda nesse meio-tempo, não briga com ele
            if checar and self.scroll.contador_roda != gesto:
                return
            try:
                bbox = canvas.bbox("all")
                if not bbox:
                    return
                canvas.configure(scrollregion=bbox)
                total = bbox[3] - bbox[1]
                visivel = canvas.winfo_height()
                if total <= visivel:
                    canvas.yview_moveto(0)
                    return
                alvo = min(max(topo, bbox[1]), bbox[3] - visivel)
                canvas.yview_moveto((alvo - bbox[1]) / total)
            except Exception:
                pass

        try:
            canvas.update_idletasks()
        except Exception:
            pass
        aplicar()
        canvas.after_idle(lambda: aplicar(True))
        canvas.after(40, lambda: aplicar(True))

    def _reconstruir_lista(self, pai, criar_itens):
        """Reconstrói uma lista dinâmica sem piscar nem pular.

        `criar_itens()` cria os frames-item NOVOS como filhos de `pai`, SEM
        empacotá-los, e devolve [(widget, kwargs_do_pack), ...]. Aqui:
          1. os itens novos recebem tamanho/cores finais (update_idletasks)
             enquanto os antigos ainda estão na tela;
          2. os antigos são destruídos e os novos exibidos no mesmo ciclo.
        Nenhum `see()`/foco é chamado: a rolagem fica sob controle do
        usuário (a posição é preservada por `_preservar_scroll`)."""
        antigos = list(pai.winfo_children())
        novos = criar_itens()
        if pai.winfo_ismapped():
            self.update_idletasks()
        for w in antigos:
            w.destroy()
        for w, kw in novos:
            w.pack(**kw)

    def _sem_foco_por_tab(self, raiz):
        """takefocus=0 (direto no Tk) em botões, switches, combos e demais
        widgets de seleção. Campos de digitação ficam de fora, para o Tab
        e o clique continuarem funcionando neles."""
        try:
            filhos = raiz.winfo_children()
        except Exception:
            return
        for w in filhos:
            try:
                if w.winfo_class() not in self._CLASSES_DE_TEXTO:
                    w.tk.call(w._w, "configure", "-takefocus", 0)
            except Exception:
                pass
            self._sem_foco_por_tab(w)

    # --------------------------------------------------- busca / filtro --
    def _abrir_busca_empresa(self):
        itens = [
            {"id": e["id"], "label": e["nome"], "sublabel": e.get("cnpj") or ""}
            for e in self._empresas_cache
        ]
        abrir_busca_modal(
            self.winfo_toplevel(), "Buscar Empresa", itens, self._selecionar_empresa,
            placeholder="Buscar por nome da empresa...",
        )

    @_mantem_scroll
    def _selecionar_empresa(self, item):
        self.combo_empresa.set(item["label"])
        self._on_empresa_selecionada(item["label"])

    def _abrir_busca_cliente(self):
        if not self._clientes_atuais:
            mostrar_alerta(
                self.winfo_toplevel(), "Selecione a empresa primeiro",
                "Escolha uma Empresa Prestadora para ver os clientes vinculados a ela.",
                "aviso",
            )
            return
        itens = [
            {"id": c["id"], "label": c["nome_razao_social"], "sublabel": c.get("endereco") or ""}
            for c in self._clientes_atuais
        ]
        abrir_busca_modal(
            self.winfo_toplevel(), "Buscar Cliente", itens, self._selecionar_cliente,
            placeholder="Buscar por nome do cliente...",
        )

    @_mantem_scroll
    def _selecionar_cliente(self, item):
        self.combo_cliente.set(item["label"])
        self._recalcular_codigo()

    @_mantem_scroll
    def _on_empresa_selecionada(self, valor):
        self._atualizar_clientes_por_empresa(valor)
        self.combo_cliente.set("")
        self._recalcular_codigo()

    def _definir_codigo(self, texto):
        """Grava o texto no campo de código (que fica desabilitado)."""
        self.entry_codigo.configure(state="normal")
        self.entry_codigo.delete(0, "end")
        self.entry_codigo.insert(0, texto)
        self.entry_codigo.configure(state="disabled")

    def _recalcular_codigo(self, *_):
        """Preenche o Código do Relatório com o próximo código livre do dia
        da Data do Serviço (RMP-AAAAMMDD-NNN). Ao EDITAR um relatório
        existente o código original é mantido e nunca recalculado."""
        if self._relatorio_editando_id is not None:
            return
        self._definir_codigo(
            self.relatorio_dao.obter_proximo_codigo_relatorio(self.data_servico_entry.get())
        )

    @staticmethod
    def _proxima_revisao(revisao):
        """'01' -> '02', '09' -> '10'. Valor inválido -> '02'."""
        try:
            return f"{int(str(revisao).strip()) + 1:02d}"
        except (ValueError, TypeError):
            return "02"

    def _atualizar_clientes_por_empresa(self, nome_empresa):
        empresa_id = self._empresas_map.get(nome_empresa)
        if empresa_id:
            self._clientes_atuais = self.cliente_dao.listar(empresa_id=empresa_id)
        else:
            self._clientes_atuais = []

        self._clientes_map = {c["nome_razao_social"]: c["id"] for c in self._clientes_atuais}
        if self._clientes_atuais:
            self.combo_cliente.configure(values=list(self._clientes_map.keys()))
        else:
            placeholder = (
                "Nenhum cliente cadastrado para esta empresa" if empresa_id
                else "Selecione uma empresa primeiro"
            )
            self.combo_cliente.configure(values=[placeholder])

    # ------------------------------------------------------- seções UI --
    @_mantem_scroll
    def _renderizar_secoes(self):
        """Recria a lista de seções sem tremor:
          1) OCULTA o container (pack_forget) — nada é pintado enquanto os
             cards são destruídos/recriados;
          2) congela a geometria (pack_propagate(False)) na altura atual
             durante a montagem, evitando reflow a cada widget criado;
          3) ao terminar: devolve a propagação, processa o layout em memória
             (update_idletasks), EXIBE o container de novo e o decorador
             @_mantem_scroll restaura a rolagem exata do usuário.
        O try/finally garante que o container nunca fique escondido, mesmo
        se a montagem falhar."""
        container = self.secoes_container
        self.update_idletasks()  # fecha eventos pendentes ANTES de ocultar
        altura = max(container.winfo_height(), 1)
        container.pack_forget()
        container.configure(height=altura)
        container.pack_propagate(False)
        try:
            self._montar_secoes()
        finally:
            container.pack_propagate(True)
            self.update_idletasks()      # layout final calculado em memória
            container.pack(fill="x")     # só agora a lista reaparece

    def _montar_secoes(self):
        # Monta os cards NOVOS fora da tela (sem pack) e só troca pelos
        # antigos quando estiverem prontos — sem "esqueleto" nem piscada.
        # A posição de rolagem é salva/restaurada (em pixels) pelo decorador
        # @_mantem_scroll, via self.scroll._parent_canvas.
        self.update_idletasks()  # fecha eventos pendentes ANTES de recriar
        # Toda re-renderização (ativar/desativar seção, ▲/▼, adicionar ou
        # remover foto) renumera as figuras antes de desenhar as legendas.
        self._reindexar_figuras()
        antigos = list(self.secoes_container.winfo_children())
        novos = []

        for i, chave in enumerate(self.ordem_secoes):
            ativo = self.secoes_ativas_vars[chave].get()

            # Ao ativar pela primeira vez, alguns módulos já vêm com
            # conteúdo padrão pronto (evita o card nascer vazio):
            if ativo and chave == "geracao_energia" and not self.fotos_por_secao[chave]:
                self.fotos_por_secao[chave] = [
                    {"origem": None,
                     "legenda_var": ctk.StringVar(value="Gráfico de geração — Antes da limpeza.")},
                    {"origem": None,
                     "legenda_var": ctk.StringVar(value="Gráfico de geração — Depois da limpeza.")},
                ]
            if ativo and chave == _SECAO_TABELA and not self.strings_rows:
                self.strings_rows.append(self._criar_string_padrao())

            # height=1 aqui é proposital: evita que o CTkFrame reserve a
            # altura padrão (200px) do customtkinter antes de ter
            # conteúdo — o card nasce compacto e só cresce conforme o
            # usuário adiciona fotos/strings/sugestões.
            card = ctk.CTkFrame(
                self.secoes_container,
                corner_radius=14, height=54,   # altura mínima fixa: título nunca é cortado
                border_width=2 if ativo else 0,
                border_color=Marca.ACCENT if ativo else ("#DBDBDB", "#2B2B2B")
            )
            novos.append((card, dict(fill="x", pady=6)))

            # Linha do item com altura FIXA (48px) e sem propagação: o
            # tamanho não depende do conteúdo, então nada é cortado nem
            # sobreposto durante a reconstrução.
            cabecalho = ctk.CTkFrame(card, fg_color="transparent", height=48)
            cabecalho.pack(fill="x", padx=14, pady=(4, 4))
            cabecalho.pack_propagate(False)

            # width=0: o CTkLabel usa a largura do texto (o padrão de 140px
            # era o que truncava "Comparativo de Geraç...").
            ctk.CTkLabel(
                cabecalho,
                text=NOMES_SECOES[chave],
                font=ctk.CTkFont(size=13, weight="bold"),
                width=0, anchor="w",
            ).pack(side="left")

            botoes_frame = ctk.CTkFrame(cabecalho, fg_color="transparent")
            botoes_frame.pack(side="right")

            if i > 0:
                ctk.CTkButton(
                    botoes_frame, text="▲", width=28, height=24,
                    command=lambda pos=i: self._mover_secao(pos, pos - 1)
                ).pack(side="left", padx=2)

            if i < len(self.ordem_secoes) - 1:
                ctk.CTkButton(
                    botoes_frame, text="▼", width=28, height=24,
                    command=lambda pos=i: self._mover_secao(pos, pos + 1)
                ).pack(side="left", padx=2)

            switch = ctk.CTkSwitch(
                botoes_frame,
                text="",
                variable=self.secoes_ativas_vars[chave],
                command=self._renderizar_secoes
            )
            switch.pack(side="left", padx=(8, 0))

            if ativo:
                corpo_secao = ctk.CTkFrame(card, fg_color="transparent", height=1)
                corpo_secao.pack(fill="x", padx=14, pady=(0, 12))
                self._renderizar_conteudo_secao(chave, corpo_secao)

        # O container está oculto (ver _renderizar_secoes): troca direta,
        # sem nenhum quadro intermediário visível.
        for w in antigos:
            w.destroy()
        for w, kw in novos:
            w.pack(**kw)

        self._sem_foco_por_tab(self.secoes_container)

    def _renderizar_conteudo_secao(self, chave, bloco):
        if chave == "geracao_energia":
            self._construir_bloco_geracao_energia(bloco)
        elif chave == "sugestoes_melhorias":
            self._construir_bloco_sugestoes(bloco)
        elif chave in _SECOES_FOTO:
            self._construir_bloco_fotos(bloco, chave)
        elif chave == _SECAO_TABELA:
            self._construir_bloco_tabela(bloco)

    def _reindexar_figuras(self):
        """Renumera "Figura X:" de todas as fotos das seções ATIVAS, na ordem
        em que aparecem no relatório (ordem_secoes), de forma contínua:
        Figura 1, 2, 3... somando todas as seções. Preserva o texto que o
        usuário escreveu depois do prefixo."""
        n = 0
        for chave in self.ordem_secoes:
            if chave not in _SECOES_NUMERADAS or not self.secoes_ativas_vars[chave].get():
                continue
            for foto in self.fotos_por_secao[chave]:
                if not foto.get("origem"):
                    continue
                n += 1
                resto = _RE_PREFIXO_FIGURA.sub("", foto["legenda_var"].get()).strip()
                foto["legenda_var"].set(f"Figura {n}: {resto}" if resto else f"Figura {n}:")

    @_mantem_scroll
    def _mover_secao(self, origem, destino):
        self.update_idletasks()
        self.ordem_secoes[origem], self.ordem_secoes[destino] = (
            self.ordem_secoes[destino], self.ordem_secoes[origem]
        )
        self._renderizar_secoes()

    def _construir_bloco_fotos(self, bloco, chave):
        if chave in _TITULOS_TOPO_FOTO:
            texto_topo, cor_topo = _TITULOS_TOPO_FOTO[chave]
            ctk.CTkLabel(
                bloco, text=texto_topo, text_color=cor_topo,
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(anchor="w", padx=14, pady=(0, 8))

        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx, foto in enumerate(self.fotos_por_secao[chave]):
                    linha = ctk.CTkFrame(lista_frame, fg_color="transparent")
                    itens.append((linha, dict(fill="x", pady=2)))
                    nome_arquivo = os.path.basename(foto["origem"])
                    ctk.CTkLabel(linha, text=nome_arquivo, width=180, anchor="w").pack(
                        side="left"
                    )
                    entry_legenda = ctk.CTkEntry(linha, placeholder_text="Legenda (opcional)",
                                                  width=280)
                    entry_legenda.insert(0, foto["legenda_var"].get())
                    entry_legenda.bind(
                        "<KeyRelease>",
                        lambda e, v=foto["legenda_var"], en=entry_legenda:
                        v.set(en.get()),
                    )
                    entry_legenda.pack(side="left", padx=8)
                    ctk.CTkButton(
                        linha, text="Remover", width=80, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.fotos_por_secao[chave].pop(i), self._renderizar_secoes()
                        ),
                    ).pack(side="left")
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_fotos():
            caminhos = filedialog.askopenfilenames(
                title="Selecionar fotos", filetypes=[("Imagens", "*.png *.jpg *.jpeg")]
            )
            legenda_padrao = _LEGENDAS_PADRAO_FOTO.get(chave, "")
            for c in caminhos:
                self.fotos_por_secao[chave].append(
                    {"origem": c, "legenda_var": ctk.StringVar(value=legenda_padrao)}
                )
            if caminhos:
                self._renderizar_secoes()  # reindexa e redesenha todas as legendas

        ctk.CTkButton(bloco, text="+ Adicionar Fotos", width=140,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_fotos).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

    # ---------------------------------------------- comparativo geração --
    def _construir_bloco_geracao_energia(self, bloco):
        """2 slots fixos ('Gráfico Anterior' / 'Gráfico Posterior'), já
        prontos com título e legenda padrão assim que a seção é ativada —
        o usuário só precisa selecionar as duas imagens."""
        slots = self.fotos_por_secao["geracao_energia"]
        rotulos_slot = ["Gráfico Anterior (antes da limpeza)",
                         "Gráfico Posterior (depois da limpeza)"]

        container = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        container.pack(fill="x", padx=14, pady=(0, 6))

        for idx, slot in enumerate(slots):
            rotulo_slot = rotulos_slot[idx] if idx < len(rotulos_slot) else f"Gráfico {idx + 1}"
            grupo = ctk.CTkFrame(container, fg_color="transparent", height=1,
                                  border_width=1, border_color=Marca.CINZA_BORDA,
                                  corner_radius=8)
            grupo.pack(fill="x", pady=4, ipady=6)

            ctk.CTkLabel(grupo, text=rotulo_slot, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Marca.PRIMARIA).pack(anchor="w", padx=10, pady=(4, 2))

            linha = ctk.CTkFrame(grupo, fg_color="transparent")
            linha.pack(fill="x", padx=10, pady=2)
            nome_arquivo = os.path.basename(slot["origem"]) if slot.get("origem") else \
                "Nenhuma imagem selecionada"
            label_arquivo = ctk.CTkLabel(linha, text=nome_arquivo, text_color="gray", width=200,
                                         anchor="w")
            label_arquivo.pack(side="left")

            def selecionar(i=idx, label=label_arquivo):
                caminho = filedialog.askopenfilename(
                    title="Selecionar imagem do gráfico",
                    filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
                )
                if caminho:
                    self.fotos_por_secao["geracao_energia"][i]["origem"] = caminho
                    label.configure(text=os.path.basename(caminho))

            ctk.CTkButton(linha, text="Selecionar...", width=110,
                          fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                          command=selecionar).pack(side="left", padx=8)

            entry_legenda = ctk.CTkEntry(grupo, width=380)
            entry_legenda.insert(0, slot["legenda_var"].get())
            entry_legenda.bind(
                "<KeyRelease>",
                lambda e, v=slot["legenda_var"], en=entry_legenda: v.set(en.get()),
            )
            entry_legenda.pack(fill="x", padx=10, pady=(4, 2))

    # ------------------------------------------------ sugestões dinâmicas --
    def _construir_bloco_sugestoes(self, bloco):
        """Lista dinâmica de sugestões — cada uma é um texto (obrigatório)
        com foto opcional anexada. '+ Adicionar Nova Sugestão' cria uma
        nova entrada em branco; nada é exigido até o usuário preencher."""
        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx, item in enumerate(self.fotos_por_secao["sugestoes_melhorias"]):
                    grupo = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                          border_width=1, border_color=Marca.CINZA_BORDA,
                                          corner_radius=8)
                    itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                    entry_texto = ctk.CTkEntry(
                        grupo, placeholder_text="Descreva a sugestão de melhoria...", width=380,
                    )
                    entry_texto.insert(0, item["legenda_var"].get())
                    entry_texto.bind(
                        "<KeyRelease>",
                        lambda e, v=item["legenda_var"], en=entry_texto: v.set(en.get()),
                    )
                    entry_texto.pack(fill="x", padx=10, pady=(6, 4))

                    linha_foto = ctk.CTkFrame(grupo, fg_color="transparent")
                    linha_foto.pack(fill="x", padx=10, pady=(0, 6))
                    nome_arquivo = os.path.basename(item["origem"]) if item.get("origem") else \
                        "Nenhuma foto anexada"
                    label_arquivo = ctk.CTkLabel(linha_foto, text=nome_arquivo, text_color="gray")
                    label_arquivo.pack(side="left")

                    def anexar(i=idx, label=label_arquivo):
                        caminho = filedialog.askopenfilename(
                            title="Anexar foto (opcional)",
                            filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
                        )
                        if caminho:
                            self.fotos_por_secao["sugestoes_melhorias"][i]["origem"] = caminho
                            label.configure(text=os.path.basename(caminho))

                    ctk.CTkButton(linha_foto, text="📎 Anexar Foto (opcional)", width=170,
                                  fg_color="gray40", command=anexar).pack(side="left", padx=8)
                    ctk.CTkButton(
                        linha_foto, text="Remover", width=80, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.fotos_por_secao["sugestoes_melhorias"].pop(i), atualizar_lista()
                        ),
                    ).pack(side="right")
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_sugestao():
            self.fotos_por_secao["sugestoes_melhorias"].append(
                {"origem": None, "legenda_var": ctk.StringVar(value="")}
            )
            atualizar_lista()

        ctk.CTkButton(bloco, text="+ Adicionar Nova Sugestão", width=170,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_sugestao).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

    def _criar_string_padrao(self):
        """Retorna um novo bloco de String com os 3 testes vazios prontos
        para preenchimento — usado tanto pelo botão '+ Adicionar String'
        quanto para pré-popular a tabela com 1 bloco ao ativar a seção."""
        n = len(self.strings_rows) + 1
        return {
            "nome_var": ctk.StringVar(value=f"String {n:02d}"),
            "vcc_var": ctk.StringVar(value=""),
            "pos_var": ctk.StringVar(value=""),
            "neg_var": ctk.StringVar(value=""),
            "neutro_var": ctk.StringVar(value=""),
            "status_tensao_var": ctk.StringVar(value="CONFORME"),
            "status_flut_pos_var": ctk.StringVar(value="CONFORME"),
            "status_flut_neg_var": ctk.StringVar(value="CONFORME"),
            "status_neutro_var": ctk.StringVar(value="CONFORME"),
        }

    def _construir_bloco_tabela(self, bloco):
        switch_neutro = ctk.CTkSwitch(
            bloco, text="⚡ Usina possui condutor Neutro (habilita Teste de Neutro)",
            variable=self.possui_neutro_var, progress_color=Marca.ACCENT,
            font=ctk.CTkFont(size=12), command=self._renderizar_secoes,
        )
        switch_neutro.pack(anchor="w", padx=14, pady=(0, 10))

        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx, s in enumerate(self.strings_rows):
                    grupo = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                          border_width=1, border_color=Marca.CINZA_BORDA,
                                          corner_radius=8)
                    itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                    cabecalho_grupo = ctk.CTkFrame(grupo, fg_color="transparent")
                    cabecalho_grupo.pack(fill="x", padx=8, pady=(4, 6))
                    ctk.CTkEntry(cabecalho_grupo, textvariable=s["nome_var"], width=160,
                                 font=ctk.CTkFont(weight="bold")).pack(side="left")
                    ctk.CTkButton(
                        cabecalho_grupo, text="Remover String", width=110, height=26,
                        fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (self.strings_rows.pop(i), atualizar_lista()),
                    ).pack(side="right")

                    parametros = [
                        ("tensao", s["vcc_var"]), ("flut_pos", s["pos_var"]),
                        ("flut_neg", s["neg_var"]),
                    ]
                    if self.possui_neutro_var.get():
                        parametros.append(("neutro", s["neutro_var"]))

                    for chave_param, var_valor in parametros:
                        sub_linha = ctk.CTkFrame(grupo, fg_color="transparent")
                        sub_linha.pack(fill="x", padx=8, pady=2)
                        ctk.CTkLabel(sub_linha, text=_STATUS_ROTULOS[chave_param], width=190,
                                     anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
                        ctk.CTkEntry(sub_linha, textvariable=var_valor, width=90,
                                     placeholder_text="Vcc").pack(side="left", padx=6)
                        self._seletor_status(sub_linha, s[f"status_{chave_param}_var"])
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_string():
            self.strings_rows.append(self._criar_string_padrao())
            atualizar_lista()

        ctk.CTkButton(bloco, text="+ Adicionar String", width=140,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_string).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

        # ---- Circuito de Corrente Alternada (CA): disjuntores ----
        # Cada disjuntor traz sua própria Corrente de Injeção (A) — o
        # campo global "Corrente de Injeção Total" foi removido.
        ctk.CTkLabel(
            bloco, text="Circuito de Corrente Alternada (CA) — opcional",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=Marca.PRIMARIA,
        ).pack(anchor="w", padx=14, pady=(4, 6))

        disjuntores_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        disjuntores_frame.pack(fill="x", padx=14, pady=(0, 4))

        @self._preservar_scroll
        def atualizar_disjuntores():
            def criar():
                itens = []
                for idx, d in enumerate(self.disjuntores_rows):
                    grupo = ctk.CTkFrame(disjuntores_frame, fg_color="transparent", height=1,
                                          border_width=1, border_color=Marca.CINZA_BORDA,
                                          corner_radius=8)
                    itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                    # Topo: identificação + voltagem nominal + excluir — igual
                    # ao cabeçalho do bloco de String.
                    cabecalho_grupo = ctk.CTkFrame(grupo, fg_color="transparent")
                    cabecalho_grupo.pack(fill="x", padx=8, pady=(4, 6))
                    ctk.CTkEntry(cabecalho_grupo, textvariable=d["nome_var"], width=130,
                                 font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
                    ctk.CTkOptionMenu(cabecalho_grupo, values=_VOLTAGENS_DISJUNTOR, width=90,
                                      variable=d["voltagem_var"]).pack(side="left")
                    ctk.CTkComboBox(cabecalho_grupo, values=_TIPOS_DISJUNTOR, width=110,
                                    variable=d["tipo_var"], state="readonly"
                                    ).pack(side="left", padx=(6, 0))
                    ctk.CTkButton(
                        cabecalho_grupo, text="X", width=30, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.disjuntores_rows.pop(i), atualizar_disjuntores()
                        ),
                    ).pack(side="right")

                    # 3 linhas individuais de medição, cada uma com seu próprio
                    # seletor Conforme/Não Conforme — mesmo padrão vertical do
                    # bloco de String (String Box CC).
                    medicoes = [
                        ("Tensão de Linha (V)", d["valor_var"], d["status_tensao_var"], "V"),
                        ("Tensão de Fase (V)", d["fase_var"], d["status_fase_var"], "V"),
                        ("Corrente de Injeção (A)", d["corrente_var"], d["status_corrente_var"], "A"),
                    ]

                    for rotulo_medicao, var_valor, var_status, unidade in medicoes:
                        sub_linha = ctk.CTkFrame(grupo, fg_color="transparent")
                        sub_linha.pack(fill="x", padx=8, pady=2)
                        ctk.CTkLabel(sub_linha, text=rotulo_medicao, width=190,
                                     anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
                        ctk.CTkEntry(sub_linha, textvariable=var_valor, width=90,
                                     placeholder_text=unidade).pack(side="left", padx=6)
                        self._seletor_status(sub_linha, var_status)
                return itens
            self._reconstruir_lista(disjuntores_frame, criar)

        def adicionar_disjuntor():
            n = len(self.disjuntores_rows) + 1
            self.disjuntores_rows.append({
                "nome_var": ctk.StringVar(value=f"Disjuntor {n:02d}"),
                "voltagem_var": ctk.StringVar(value="220V"),
                "tipo_var": ctk.StringVar(value=_TIPOS_DISJUNTOR[0]),
                "valor_var": ctk.StringVar(value=""),
                "corrente_var": ctk.StringVar(value=""),
                "fase_var": ctk.StringVar(value=""),
                "status_tensao_var": ctk.StringVar(value="CONFORME"),
                "status_corrente_var": ctk.StringVar(value="CONFORME"),
                "status_fase_var": ctk.StringVar(value="CONFORME"),
            })
            atualizar_disjuntores()

        ctk.CTkButton(bloco, text="+ Adicionar Disjuntor", width=150,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_disjuntor).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_disjuntores()

    def _seletor_status(self, parent, status_var):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=2)

        def escolher(valor):
            status_var.set(valor)
            atualizar_cores()

        btn_conforme = ctk.CTkButton(
            frame, text="Conforme", width=90, height=26,
            command=lambda: escolher("CONFORME"),
        )
        btn_nao = ctk.CTkButton(
            frame, text="Não Conforme", width=95, height=26,
            command=lambda: escolher("NAO_CONFORME"),
        )
        btn_conforme.pack(side="left", padx=(0, 3))
        btn_nao.pack(side="left")

        def atualizar_cores():
            if status_var.get() == "CONFORME":
                btn_conforme.configure(fg_color=Marca.SUCESSO_TEXTO, text_color="white")
                btn_nao.configure(fg_color="gray75", text_color="gray30")
            else:
                btn_nao.configure(fg_color=Marca.ERRO, text_color="white")
                btn_conforme.configure(fg_color="gray75", text_color="gray30")

        atualizar_cores()

    # -------------------------------------------------------- ao exibir --
    def ao_exibir(self):
        self._empresas_cache = self.empresa_dao.listar()
        self._empresas_map = {e["nome"]: e["id"] for e in self._empresas_cache}
        self.combo_empresa.configure(values=list(self._empresas_map.keys()))
        self._atualizar_clientes_por_empresa(self.combo_empresa.get())
        self._recalcular_codigo()

    # ------------------------------------------------- editar existente --
    def carregar_relatorio_existente(self, relatorio_id) -> bool:
        """Carrega um relatório salvo no formulário para EDIÇÃO: mantém o
        código original e já sobe a Revisão (01 -> 02). As fotos não são
        guardadas no banco (ficam só em pasta temporária), então precisam
        ser anexadas de novo. Chame a partir da tela de histórico/lista."""
        rel = self.relatorio_dao.buscar_por_id(relatorio_id)
        if not rel:
            mostrar_alerta(self.winfo_toplevel(), "Relatório não encontrado",
                           "Não foi possível carregar o relatório selecionado.", "erro")
            return False

        self._resetar_formulario()   # limpa o formulário e sai do modo edição

        self._empresas_cache = self.empresa_dao.listar()
        self._empresas_map = {e["nome"]: e["id"] for e in self._empresas_cache}
        self.combo_empresa.configure(values=list(self._empresas_map.keys()))
        empresa = self.empresa_dao.buscar_por_id(rel["empresa_id"])
        cliente = self.cliente_dao.buscar_por_id(rel["cliente_id"])
        nome_empresa = empresa["nome"] if empresa else ""
        self.combo_empresa.set(nome_empresa)
        self._atualizar_clientes_por_empresa(nome_empresa)
        self.combo_cliente.set(cliente["nome_razao_social"] if cliente else "")

        try:
            self.data_servico_entry.set_date(
                datetime.strptime(rel.get("data_servico") or "", "%d/%m/%Y").date()
            )
        except ValueError:
            pass

        self.entry_responsavel.delete(0, "end")
        self.entry_responsavel.insert(0, rel.get("responsavel_tecnico") or "")
        for caixa, campo in ((self.txt_objetivo, "texto_objetivo"),
                             (self.txt_aplicacao, "texto_aplicacao"),
                             (self.txt_normas, "texto_normas")):
            caixa.delete("1.0", "end")
            caixa.insert("1.0", rel.get(campo) or "")

        secoes = [s for s in rel.get("secoes", []) if s in self.secoes_ativas_vars]
        self.ordem_secoes = secoes + [s for s in self.ordem_secoes if s not in secoes]
        for s in secoes:
            self.secoes_ativas_vars[s].set(True)

        strings = self.relatorio_dao.listar_strings(relatorio_id)
        disjuntores = self.relatorio_dao.listar_disjuntores(relatorio_id)
        self.strings_rows = [self._string_de_registro(r) for r in strings]
        self.disjuntores_rows = [self._disjuntor_de_registro(r) for r in disjuntores]
        self.possui_neutro_var.set(
            any(r.get("neutro_valor") is not None for r in strings)
        )

        # Modo edição: código original travado + REV incrementada.
        self._relatorio_editando_id = rel["id"]
        self._definir_codigo(rel["codigo"])
        self.entry_revisao.delete(0, "end")
        self.entry_revisao.insert(0, self._proxima_revisao(rel.get("revisao")))

        self._renderizar_secoes()
        return True

    @staticmethod
    def _string_de_registro(r):
        legado = r.get("status") or "CONFORME"
        return {
            "nome_var": ctk.StringVar(value=r.get("string_nome") or ""),
            "vcc_var": ctk.StringVar(value=_fmt_num(r.get("tensao_vcc"))),
            "pos_var": ctk.StringVar(value=_fmt_num(r.get("flutuacao_positivo"))),
            "neg_var": ctk.StringVar(value=_fmt_num(r.get("flutuacao_negativo"))),
            "neutro_var": ctk.StringVar(value=_fmt_num(r.get("neutro_valor"))),
            "status_tensao_var": ctk.StringVar(value=r.get("status_tensao") or legado),
            "status_flut_pos_var": ctk.StringVar(
                value=r.get("status_flutuacao_positivo") or legado),
            "status_flut_neg_var": ctk.StringVar(
                value=r.get("status_flutuacao_negativo") or legado),
            "status_neutro_var": ctk.StringVar(value=r.get("status_neutro") or "CONFORME"),
        }

    @staticmethod
    def _disjuntor_de_registro(r):
        return {
            "nome_var": ctk.StringVar(value=r.get("nome") or ""),
            "voltagem_var": ctk.StringVar(value=r.get("voltagem") or "220V"),
            "tipo_var": ctk.StringVar(value=r.get("tipo") or _TIPOS_DISJUNTOR[0]),
            "valor_var": ctk.StringVar(value=_fmt_num(r.get("valor_medido"))),
            "corrente_var": ctk.StringVar(value=_fmt_num(r.get("corrente_injecao_valor"))),
            "fase_var": ctk.StringVar(value=_fmt_num(r.get("neutro_valor"))),
            "status_tensao_var": ctk.StringVar(value=r.get("status") or "CONFORME"),
            "status_corrente_var": ctk.StringVar(
                value=r.get("corrente_injecao_status") or "CONFORME"),
            "status_fase_var": ctk.StringVar(value=r.get("status_neutro") or "CONFORME"),
        }

    # ------------------------------------------------------------ gerar --
    def _gerar_relatorio(self):
        nome_empresa = self.combo_empresa.get()
        nome_cliente = self.combo_cliente.get()
        empresa_id = self._empresas_map.get(nome_empresa)
        cliente_id = self._clientes_map.get(nome_cliente)

        if not empresa_id or not cliente_id:
            mostrar_alerta(self.winfo_toplevel(), "Campos obrigatórios",
                            "Selecione a Empresa e o Cliente do relatório.", "aviso")
            return

        secoes_selecionadas = [
            s for s in self.ordem_secoes if self.secoes_ativas_vars[s].get()
        ]
        if not secoes_selecionadas:
            mostrar_alerta(self.winfo_toplevel(), "Nenhuma seção selecionada",
                            "Ative ao menos uma seção para incluir no relatório.", "aviso")
            return

        empresa = self.empresa_dao.buscar_por_id(empresa_id)
        cliente = self.cliente_dao.buscar_por_id(cliente_id)
        codigo = self.entry_codigo.get().strip()
        if self._relatorio_editando_id is None:
            # Relatório novo: garante um código livre no momento de gravar.
            # (Se o código já pertence a um relatório com PDF gerado, pega o
            # próximo; se for sobra de uma tentativa que falhou, reaproveita.)
            existente = self.relatorio_dao.buscar_por_codigo(codigo) if codigo else None
            if not codigo or (existente and existente.get("pdf_path")):
                codigo = self.relatorio_dao.obter_proximo_codigo_relatorio(
                    self.data_servico_entry.get()
                )
                self._definir_codigo(codigo)

        dados_relatorio = {
            "codigo": codigo,
            "empresa_id": empresa_id,
            "cliente_id": cliente_id,
            "data_servico": self.data_servico_entry.get(),
            "responsavel_tecnico": self.entry_responsavel.get().strip() or empresa.get(
                "responsavel_tecnico", ""
            ),
            "revisao": self.entry_revisao.get().strip() or "01",
            "texto_objetivo": self.txt_objetivo.get("1.0", "end").strip(),
            "texto_aplicacao": self.txt_aplicacao.get("1.0", "end").strip(),
            "texto_normas": self.txt_normas.get("1.0", "end").strip(),
            "secoes": secoes_selecionadas,
        }

        # INSERT se o código é novo; UPDATE (com a nova REV) se já existe.
        relatorio_id = self.relatorio_dao.salvar(dados_relatorio)

        # Armazenamento leve: as fotos do relatório são processadas em uma
        # pasta TEMPORÁRIA (fora de data/fotos) e são apagadas assim que o
        # PDF é compilado — nenhuma cópia permanente fica no disco, e os
        # caminhos não são persistidos em relatorio_fotos (só o .pdf final
        # sobrevive na pasta do cliente).
        pasta_temp = criar_pasta_temporaria()

        # Garante que as legendas do PDF == as da tela (numeração sequencial).
        self._reindexar_figuras()

        fotos_por_secao_final = {}
        for chave in _SECOES_FOTO:
            if chave not in secoes_selecionadas:
                continue
            registros = []
            for ordem, foto in enumerate(self.fotos_por_secao[chave]):
                legenda = foto["legenda_var"].get()
                origem = foto.get("origem")
                if not origem:
                    # Sugestões de Melhorias aceita entradas só-texto (sem
                    # foto); outras seções simplesmente ignoram o slot
                    # vazio (ex.: gráfico do comparativo não selecionado).
                    if chave == "sugestoes_melhorias" and legenda.strip():
                        registros.append({"foto_path": None, "legenda": legenda})
                    continue
                caminho_temp = salvar_foto_temporaria(origem, pasta_temp)
                registros.append({"foto_path": caminho_temp, "legenda": legenda})
            fotos_por_secao_final[chave] = registros

        strings_data = []
        disjuntores_data = []
        possui_neutro = self.possui_neutro_var.get()
        if _SECAO_TABELA in secoes_selecionadas:
            for ordem, s in enumerate(self.strings_rows):
                vcc = _to_float(s["vcc_var"].get())
                pos = _to_float(s["pos_var"].get())
                neg = _to_float(s["neg_var"].get())
                status_tensao = s["status_tensao_var"].get()
                status_flut_pos = s["status_flut_pos_var"].get()
                status_flut_neg = s["status_flut_neg_var"].get()
                neutro = _to_float(s["neutro_var"].get()) if possui_neutro else None
                status_neutro = s["status_neutro_var"].get()
                self.relatorio_dao.adicionar_string(
                    relatorio_id, s["nome_var"].get(), vcc, pos, neg,
                    status_tensao, status_flut_pos, status_flut_neg, ordem,
                    neutro, status_neutro,
                )
                strings_data.append({
                    "string_nome": s["nome_var"].get(), "tensao_vcc": vcc,
                    "flutuacao_positivo": pos, "flutuacao_negativo": neg,
                    "status_tensao": status_tensao,
                    "status_flutuacao_positivo": status_flut_pos,
                    "status_flutuacao_negativo": status_flut_neg,
                    "neutro_valor": neutro, "status_neutro": status_neutro,
                })

            for ordem, d in enumerate(self.disjuntores_rows):
                valor = _to_float(d["valor_var"].get())
                fase = _to_float(d["fase_var"].get())
                corrente = _to_float(d["corrente_var"].get())
                if valor is None and fase is None and corrente is None:
                    continue  # disjuntor totalmente vazio, ignora
                nome = d["nome_var"].get()
                voltagem = d["voltagem_var"].get()
                status_tensao_disj = d["status_tensao_var"].get()
                status_corrente_disj = d["status_corrente_var"].get()
                tipo = d["tipo_var"].get() or _TIPOS_DISJUNTOR[0]
                status_fase_disj = d["status_fase_var"].get()
                self.relatorio_dao.adicionar_disjuntor(
                    relatorio_id, nome, voltagem, valor, status_tensao_disj, ordem,
                    corrente, status_corrente_disj, fase, status_fase_disj, tipo,
                )
                disjuntores_data.append({
                    "nome": nome, "voltagem": voltagem,
                    "valor_medido": valor, "status": status_tensao_disj,
                    "corrente_injecao_valor": corrente,
                    "corrente_injecao_status": status_corrente_disj,
                    "neutro_valor": fase, "status_neutro": status_fase_disj,
                    "tipo": tipo,
                    # aliases legíveis para o gerador de PDF
                    "tensao_linha_valor": valor, "tensao_linha_status": status_tensao_disj,
                    "tensao_fase_valor": fase, "tensao_fase_status": status_fase_disj,
                })

        pasta_raiz = self.config_dao.obter_pasta_relatorios()
        # Estrutura de pastas padronizada: [COD_EMPRESA] - [NOME_EMPRESA] /
        # [COD_CLIENTE] - [NOME_CLIENTE] / Relatórios /, usando a mesma
        # máscara de código exibida no cabeçalho do PDF.
        nome_pasta_empresa = f"{EmpresaDAO.codigo_exibicao(empresa)} - {empresa['nome']}"
        nome_pasta_cliente = f"{ClienteDAO.codigo_exibicao(cliente)} - {cliente['nome_razao_social']}"
        pasta_destino = os.path.join(
            pasta_raiz, _sanitizar(nome_pasta_empresa), _sanitizar(nome_pasta_cliente),
            "Relatórios",
        )
        os.makedirs(pasta_destino, exist_ok=True)
        caminho_pdf = os.path.join(pasta_destino, f"{codigo}.pdf")

        try:
            gerar_relatorio_pdf(
                caminho_pdf, empresa, cliente, dados_relatorio,
                secoes_selecionadas, fotos_por_secao_final, strings_data,
                disjuntores_data,
            )
            self.relatorio_dao.atualizar_pdf_path(relatorio_id, caminho_pdf)
        except Exception as exc:
            mostrar_alerta(self.winfo_toplevel(), "Erro ao gerar PDF", str(exc), "erro")
            return
        finally:
            # As fotos temporárias somem do disco aqui, sucesso ou falha —
            # só o .pdf final (se gerado) permanece na pasta do cliente.
            limpar_pasta_temporaria(pasta_temp)

        # Envia ao Telegram com os botões Aprovar/Reprovar (falha silenciosa:
        # offline/indisponível nunca impede a geração do relatório).
        try:
            self.relatorio_dao.atualizar_status(codigo, STATUS_REL_PENDENTE)
        except Exception:
            logging.getLogger("telegram").exception("Falha ao marcar status Pendente")
        try:
            notificar_relatorio_para_aprovacao(
                codigo,
                f"Empresa: {empresa['nome']}\nCliente: {cliente['nome_razao_social']}",
            )
        except Exception:
            logging.getLogger("telegram").exception("Falha ao notificar relatório")

        mostrar_alerta(
            self.winfo_toplevel(), "Relatório gerado",
            f"Relatório {codigo} gerado com sucesso em:\n{caminho_pdf}", "sucesso",
        )
        self._resetar_formulario()

    def _resetar_formulario(self):
        self.fotos_por_secao = {s: [] for s in _SECOES_FOTO}
        self.strings_rows = []
        self.disjuntores_rows = []
        self.possui_neutro_var.set(False)
        for var in self.secoes_ativas_vars.values():
            var.set(False)
        self.entry_responsavel.delete(0, "end")
        self.entry_revisao.delete(0, "end")
        self.entry_revisao.insert(0, "01")
        self._renderizar_secoes()
        self._relatorio_editando_id = None
        self._recalcular_codigo()


def _fmt_num(valor):
    """Número do banco -> texto do campo (None -> vazio; 281.0 -> '281')."""
    if valor is None:
        return ""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(f)) if f == int(f) else str(f).replace(".", ",")


def _to_float(valor):
    try:
        return float(str(valor).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _sanitizar(nome: str) -> str:
    """Remove caracteres inválidos para nomes de pasta em Windows/Linux/Mac."""
    invalidos = '<>:"/\\|?*'
    for c in invalidos:
        nome = nome.replace(c, "-")
    return nome.strip() or "sem_nome"
