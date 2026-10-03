"""
Módulo 1: Cadastro/Gerenciamento de Empresas prestadoras de serviço.

Redesenhado seguindo heurísticas de Nielsen: a tela inicial mostra apenas
uma lista limpa com busca; o formulário só aparece em um Modal ("+ Novo
Cadastro" ou "Editar"); clicar em uma empresa abre um Drawer lateral com
todos os detalhes e as ações de Editar/Excluir.
"""
import os

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image

from config import LOGOS_DIR, ASSINATURAS_DIR, Marca
from models.empresa_dao import EmpresaDAO
from utils.image_utils import copiar_arquivo_generico
from ui.components import ModalWindow, DrawerWindow, confirmar_exclusao, mostrar_alerta


class EmpresasView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.dao = EmpresaDAO()
        self._empresas_cache = []
        self._drawer_aberto = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_cabecalho()
        self._construir_lista()
        self._carregar_lista()

    # --------------------------------------------------------------- UI --
    def _construir_cabecalho(self):
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        cabecalho.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cabecalho, text="Minhas Empresas", font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Marca.PRIMARIA,
        ).grid(row=0, column=0, sticky="w")

        self.entry_busca = ctk.CTkEntry(
            cabecalho, placeholder_text="🔍  Buscar por nome...", width=280,
        )
        self.entry_busca.grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.entry_busca.bind("<KeyRelease>", lambda e: self._filtrar_lista())

        ctk.CTkButton(
            cabecalho, text="+ Novo Cadastro", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, width=150,
            command=lambda: self._abrir_formulario(),
        ).grid(row=0, column=2, sticky="e")

    def _construir_lista(self):
        self.lista_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista_scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.lista_scroll.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------ lista --
    def _carregar_lista(self):
        self._empresas_cache = self.dao.listar()
        self._renderizar_lista(self._empresas_cache)

    def _filtrar_lista(self):
        termo = self.entry_busca.get().strip().lower()
        if not termo:
            self._renderizar_lista(self._empresas_cache)
            return
        filtradas = [e for e in self._empresas_cache if termo in e["nome"].lower()]
        self._renderizar_lista(filtradas)

    def _renderizar_lista(self, empresas):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        if not empresas:
            ctk.CTkLabel(self.lista_scroll, text="Nenhuma empresa encontrada.",
                         text_color="gray").pack(pady=20)
            return

        for empresa in empresas:
            card = ctk.CTkFrame(self.lista_scroll, corner_radius=10, cursor="hand2")
            card.pack(fill="x", pady=5, padx=4)
            card.grid_columnconfigure(1, weight=1)

            thumb = self._thumb_logo(card, empresa.get("logo_path"))
            thumb.grid(row=0, column=0, padx=(12, 10), pady=10)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="w", pady=10)
            ctk.CTkLabel(info, text=empresa["nome"],
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            subtexto = empresa.get("cnpj") or empresa.get("telefone") or ""
            if subtexto:
                ctk.CTkLabel(info, text=subtexto, text_color="gray",
                             font=ctk.CTkFont(size=11)).pack(anchor="w")

            ctk.CTkLabel(card, text="›", font=ctk.CTkFont(size=18),
                         text_color="gray").grid(row=0, column=2, padx=14)

            # clique em qualquer parte do card abre o Drawer de detalhes
            for widget in (card, thumb, info):
                widget.bind("<Button-1>", lambda e, eid=empresa["id"]: self._abrir_drawer(eid))
            for child in info.winfo_children():
                child.bind("<Button-1>", lambda e, eid=empresa["id"]: self._abrir_drawer(eid))

    def _thumb_logo(self, parent, logo_path):
        if logo_path and os.path.exists(logo_path):
            try:
                img = Image.open(logo_path)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(44, 44))
                label = ctk.CTkLabel(parent, image=ctk_img, text="")
                label._ctk_img_ref = ctk_img  # evita garbage collection
                return label
            except Exception:
                pass
        return ctk.CTkLabel(parent, text="🏢", font=ctk.CTkFont(size=22), width=44)

    # ------------------------------------------------------------ drawer --
    def _abrir_drawer(self, empresa_id):
        empresa = self.dao.buscar_por_id(empresa_id)
        if not empresa:
            return
        if self._drawer_aberto is not None and self._drawer_aberto.winfo_exists():
            self._drawer_aberto.destroy()

        drawer = DrawerWindow(self.winfo_toplevel(), empresa["nome"], width=420)
        self._drawer_aberto = drawer

        if empresa.get("logo_path") and os.path.exists(empresa["logo_path"]):
            try:
                img = Image.open(empresa["logo_path"])
                logo_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(90, 90))
                label_logo = ctk.CTkLabel(drawer.body, image=logo_ctk, text="")
                label_logo._ctk_img_ref = logo_ctk
                label_logo.pack(pady=(20, 10))
            except Exception:
                pass

        campos = [
            ("Código da Empresa", EmpresaDAO.codigo_exibicao(empresa)),
            ("CNPJ", empresa.get("cnpj")),
            ("Telefone / E-mail", empresa.get("telefone")),
            ("Responsável Técnico", empresa.get("responsavel_tecnico")),
            ("Registro / CRT", empresa.get("responsavel_registro")),
        ]
        for rotulo, valor in campos:
            self._linha_detalhe(drawer.body, rotulo, valor)

        if empresa.get("assinatura_path") and os.path.exists(empresa["assinatura_path"]):
            try:
                ctk.CTkLabel(drawer.body, text="ASSINATURA DIGITAL",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="gray").pack(anchor="w", padx=20, pady=(10, 2))
                img_assin = Image.open(empresa["assinatura_path"])
                assin_ctk = ctk.CTkImage(light_image=img_assin, dark_image=img_assin,
                                          size=(180, 75))
                label_assin = ctk.CTkLabel(drawer.body, image=assin_ctk, text="")
                label_assin._ctk_img_ref = assin_ctk
                label_assin.pack(anchor="w", padx=20, pady=(0, 6))
            except Exception:
                pass

        ctk.CTkButton(
            drawer.footer, text="✏️ Editar Empresa", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER,
            command=lambda: self._abrir_formulario(empresa, drawer),
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            drawer.footer, text="🗑️ Excluir Empresa", fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
            command=lambda: confirmar_exclusao(
                drawer, empresa["nome"], lambda: self._excluir(empresa_id, drawer)
            ),
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        drawer.update_idletasks()

    def _linha_detalhe(self, parent, rotulo, valor):
        bloco = ctk.CTkFrame(parent, fg_color="transparent")
        bloco.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(bloco, text=rotulo.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray").pack(anchor="w")
        ctk.CTkLabel(bloco, text=valor or "—", font=ctk.CTkFont(size=13),
                     wraplength=360, justify="left").pack(anchor="w")

    # ------------------------------------------------------------ ações --
    def _excluir(self, empresa_id, drawer=None):
        try:
            self.dao.excluir(empresa_id)
        except ValueError as exc:
            mostrar_alerta(self.winfo_toplevel(), "Não foi possível excluir", str(exc), "erro")
            return
        if drawer is not None and drawer.winfo_exists():
            drawer.destroy()
        self._drawer_aberto = None
        self._carregar_lista()

    def _abrir_formulario(self, empresa=None, drawer_para_fechar=None):
        editando = empresa is not None
        titulo = f"Editar Empresa" if editando else "Nova Empresa"
        modal = ModalWindow(self.winfo_toplevel(), titulo, width=520, height=620)

        entradas = {}
        campos = [
            ("nome", "Nome da Empresa *"),
            ("codigo_empresa", "Código da Empresa (opcional — usado na pasta de relatórios)"),
            ("cnpj", "CNPJ"),
            ("telefone", "Telefone / E-mail"),
            ("responsavel_tecnico", "Responsável Técnico (Nome)"),
            ("responsavel_registro", "Registro / CRT do Responsável"),
        ]
        for chave, rotulo in campos:
            ctk.CTkLabel(modal.body, text=rotulo, font=ctk.CTkFont(size=12)).pack(
                anchor="w", padx=20, pady=(12, 0)
            )
            entrada = ctk.CTkEntry(modal.body, width=400)
            if editando:
                entrada.insert(0, empresa.get(chave) or "")
            entrada.pack(anchor="w", padx=20, pady=(2, 0), fill="x")
            entradas[chave] = entrada

        ctk.CTkLabel(modal.body, text="Logo da Empresa (.png / .jpg)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=20, pady=(14, 0))
        logo_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
        logo_frame.pack(anchor="w", padx=20, pady=(4, 0), fill="x")
        texto_inicial = "Logo já cadastrada" if (editando and empresa.get("logo_path")) else \
            "Nenhum arquivo selecionado"
        label_logo = ctk.CTkLabel(logo_frame, text=texto_inicial, text_color="gray")
        label_logo.pack(side="left", padx=(0, 10))
        estado_logo = {"novo_path": None}

        def selecionar_logo():
            caminho = filedialog.askopenfilename(
                title="Selecionar logo", filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
            )
            if caminho:
                estado_logo["novo_path"] = caminho
                label_logo.configure(text=os.path.basename(caminho))

        ctk.CTkButton(logo_frame, text="Selecionar...", width=110,
                      command=selecionar_logo).pack(side="left")

        ctk.CTkLabel(modal.body, text="Assinatura Digital do Responsável Técnico (.png / .jpg)",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=20, pady=(14, 0))
        ctk.CTkLabel(
            modal.body, text="Aparece na página de conclusão do relatório em PDF.",
            text_color="gray", font=ctk.CTkFont(size=10),
        ).pack(anchor="w", padx=20)
        assinatura_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
        assinatura_frame.pack(anchor="w", padx=20, pady=(4, 0), fill="x")
        texto_assinatura_inicial = "Assinatura já cadastrada" if (
            editando and empresa.get("assinatura_path")
        ) else "Nenhum arquivo selecionado"
        label_assinatura = ctk.CTkLabel(assinatura_frame, text=texto_assinatura_inicial,
                                         text_color="gray")
        label_assinatura.pack(side="left", padx=(0, 10))
        estado_assinatura = {"novo_path": None}

        def selecionar_assinatura():
            caminho = filedialog.askopenfilename(
                title="Selecionar assinatura", filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
            )
            if caminho:
                estado_assinatura["novo_path"] = caminho
                label_assinatura.configure(text=os.path.basename(caminho))

        ctk.CTkButton(assinatura_frame, text="Selecionar...", width=110,
                      command=selecionar_assinatura).pack(side="left")

        def salvar():
            nome = entradas["nome"].get().strip()
            if not nome:
                mostrar_alerta(modal, "Campo obrigatório", "Informe o nome da empresa.", "aviso")
                return

            dados = {chave: entrada.get().strip() for chave, entrada in entradas.items()}
            if estado_logo["novo_path"]:
                dados["logo_path"] = copiar_arquivo_generico(estado_logo["novo_path"], LOGOS_DIR)
            elif editando:
                dados["logo_path"] = empresa.get("logo_path")
            else:
                dados["logo_path"] = None

            if estado_assinatura["novo_path"]:
                dados["assinatura_path"] = copiar_arquivo_generico(
                    estado_assinatura["novo_path"], ASSINATURAS_DIR
                )
            elif editando:
                dados["assinatura_path"] = empresa.get("assinatura_path")
            else:
                dados["assinatura_path"] = None

            if editando:
                self.dao.atualizar(empresa["id"], dados)
            else:
                self.dao.criar(dados)

            modal.destroy()
            if drawer_para_fechar is not None and drawer_para_fechar.winfo_exists():
                drawer_para_fechar.destroy()
                self._drawer_aberto = None
            self._carregar_lista()

        botoes = ctk.CTkFrame(modal.body, fg_color="transparent")
        botoes.pack(fill="x", padx=20, pady=24)
        ctk.CTkButton(botoes, text="Salvar", fg_color=Marca.ACCENT,
                      hover_color=Marca.ACCENT_HOVER, command=salvar).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(botoes, text="Cancelar", fg_color="gray40",
                      command=modal.destroy).pack(side="left")

    def ao_exibir(self):
        self._carregar_lista()
