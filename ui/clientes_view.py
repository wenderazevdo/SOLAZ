"""
Módulo 2: Cadastro/Gerenciamento de Clientes.

Mesmo padrão de UX das Empresas: lista limpa com busca, formulário completo
em Modal ("+ Novo Cadastro"/"Editar") e Drawer lateral com todos os dados e
fotos cadastradas do cliente.
"""
import os

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image

from config import Marca
from models.cliente_dao import ClienteDAO
from models.empresa_dao import EmpresaDAO
from utils.image_utils import salvar_foto_padronizada
from ui.components import ModalWindow, DrawerWindow, confirmar_exclusao, mostrar_alerta

_CAMPOS_FOTO = [
    ("foto_local_path", "Foto do Local (Casa / Empresa)"),
    ("modulo_foto_etiqueta_path", "Foto da Etiqueta do Módulo"),
    ("ponto_agua_foto_path", "Foto do Ponto de Água"),
    ("inversores_foto_etiqueta_path", "Foto da Etiqueta do Inversor"),
]


class ClientesView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.dao = ClienteDAO()
        self.empresa_dao = EmpresaDAO()
        self._clientes_cache = []
        self._empresas_map = {}
        self._drawer_aberto = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._construir_cabecalho()
        self._construir_badges()
        self._construir_lista()
        self._carregar_lista()

    # --------------------------------------------------------------- UI --
    def _construir_cabecalho(self):
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        cabecalho.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cabecalho, text="Clientes", font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Marca.PRIMARIA,
        ).grid(row=0, column=0, sticky="w")

        controles = ctk.CTkFrame(cabecalho, fg_color="transparent")
        controles.grid(row=0, column=1, sticky="e")

        self.combo_filtro_empresa = ctk.CTkComboBox(
            controles, values=["Todas as Empresas"], width=200,
            command=lambda _: self._carregar_lista(),
        )
        self.combo_filtro_empresa.set("Todas as Empresas")
        self.combo_filtro_empresa.pack(side="left", padx=(0, 10))

        self.entry_busca = ctk.CTkEntry(
            controles, placeholder_text="🔍  Buscar por nome...", width=240,
        )
        self.entry_busca.pack(side="left", padx=(0, 10))
        self.entry_busca.bind("<KeyRelease>", lambda e: self._filtrar_lista())

        ctk.CTkButton(
            controles, text="+ Novo Cadastro", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, width=150,
            command=lambda: self._abrir_formulario(),
        ).pack(side="left")

    def _construir_badges(self):
        badges = ctk.CTkFrame(self, fg_color="transparent")
        badges.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))

        def _badge(texto_inicial):
            b = ctk.CTkLabel(
                badges, text=texto_inicial, font=ctk.CTkFont(size=12, weight="bold"),
                text_color=Marca.PRIMARIA, fg_color=Marca.CINZA_TECNICO,
                corner_radius=8, padx=14, pady=6,
            )
            b.pack(side="left", padx=(0, 10))
            return b

        self.badge_clientes = _badge("Total Geral de Clientes: 0")
        self.badge_empresas = _badge("Total de Empresas: 0")

    def _atualizar_badges(self):
        nome_filtro = self.combo_filtro_empresa.get()
        empresa_id = self._empresas_map.get(nome_filtro)
        total_empresas = len(self._empresas_map)

        if empresa_id:
            total_clientes = self.dao.contar_total(empresa_id=empresa_id)
            self.badge_clientes.configure(
                text=f"Clientes de {nome_filtro}: {total_clientes}"
            )
        else:
            total_clientes = self.dao.contar_total()
            self.badge_clientes.configure(text=f"Total Geral de Clientes: {total_clientes}")

        self.badge_empresas.configure(text=f"Total de Empresas: {total_empresas}")

    def _construir_lista(self):
        self.lista_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista_scroll.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.lista_scroll.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------ lista --
    def _carregar_lista(self):
        nome_filtro = self.combo_filtro_empresa.get()
        empresa_id = self._empresas_map.get(nome_filtro)  # None = "Todas as Empresas"
        self._clientes_cache = self.dao.listar_com_empresa(empresa_id=empresa_id)
        self._renderizar_lista(self._clientes_cache)
        self._atualizar_badges()

    def _filtrar_lista(self):
        termo = self.entry_busca.get().strip().lower()
        if not termo:
            self._renderizar_lista(self._clientes_cache)
            return
        filtrados = [c for c in self._clientes_cache if termo in c["nome_razao_social"].lower()]
        self._renderizar_lista(filtrados)

    def _renderizar_lista(self, clientes):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        if not clientes:
            ctk.CTkLabel(self.lista_scroll, text="Nenhum cliente encontrado.",
                         text_color="gray").pack(pady=20)
            return

        for cliente in clientes:
            card = ctk.CTkFrame(self.lista_scroll, corner_radius=10, cursor="hand2")
            card.pack(fill="x", pady=5, padx=4)
            card.grid_columnconfigure(1, weight=1)

            thumb = self._thumb_foto(card, cliente.get("foto_local_path"))
            thumb.grid(row=0, column=0, padx=(12, 10), pady=10)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="w", pady=10)
            ctk.CTkLabel(info, text=cliente["nome_razao_social"],
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            subtexto_partes = [p for p in (
                cliente.get("empresa_nome"), cliente.get("endereco")
            ) if p]
            if subtexto_partes:
                ctk.CTkLabel(info, text="  •  ".join(subtexto_partes), text_color="gray",
                             font=ctk.CTkFont(size=11)).pack(anchor="w")

            ctk.CTkLabel(card, text="›", font=ctk.CTkFont(size=18),
                         text_color="gray").grid(row=0, column=2, padx=14)

            for widget in (card, thumb, info):
                widget.bind("<Button-1>", lambda e, cid=cliente["id"]: self._abrir_drawer(cid))
            for child in info.winfo_children():
                child.bind("<Button-1>", lambda e, cid=cliente["id"]: self._abrir_drawer(cid))

    def _thumb_foto(self, parent, foto_path):
        if foto_path and os.path.exists(foto_path):
            try:
                img = Image.open(foto_path)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(44, 44))
                label = ctk.CTkLabel(parent, image=ctk_img, text="")
                label._ctk_img_ref = ctk_img
                return label
            except Exception:
                pass
        return ctk.CTkLabel(parent, text="👤", font=ctk.CTkFont(size=22), width=44)

    # ------------------------------------------------------------ drawer --
    def _abrir_drawer(self, cliente_id):
        cliente = self.dao.buscar_por_id(cliente_id)
        if not cliente:
            return
        if self._drawer_aberto is not None and self._drawer_aberto.winfo_exists():
            self._drawer_aberto.destroy()

        drawer = DrawerWindow(self.winfo_toplevel(), cliente["nome_razao_social"], width=440)
        self._drawer_aberto = drawer

        # Todo o preenchimento do drawer fica sob um try/except de topo: se
        # algo inesperado falhar, mostramos o erro em vez de deixar a janela
        # silenciosamente em branco (bug anterior — difícil de diagnosticar).
        try:
            # Dados em texto vêm ANTES da foto principal, de propósito: o
            # bug relatado era "só a foto aparece, o texto some" — colocar
            # o texto primeiro garante que ele sempre é desenhado, mesmo
            # que a foto (um CTkImage grande) cause algum problema de
            # relayout no CTkScrollableFrame logo em seguida.
            self._secao_detalhe(drawer.body, "Dados Cadastrais", [
                ("Empresa Prestadora", cliente.get("empresa_nome")),
                ("Código do Cliente", ClienteDAO.codigo_exibicao(cliente)),
                ("CPF/CNPJ", cliente.get("cpf_cnpj")),
                ("Contato", cliente.get("contato_nome")),
                ("Telefone", cliente.get("telefone")),
            ])

            self._secao_detalhe(drawer.body, "Sistema Fotovoltaico", [
                ("Quantidade de Módulos", cliente.get("qtd_modulos")),
                ("Marca do Módulo", cliente.get("modulo_marca")),
                ("Potência (Wp)", cliente.get("modulo_potencia_wp")),
                ("Potência do Sistema (kWp)", cliente.get("potencia_sistema_kwp")),
                ("Inversor (Marca/Modelo)", cliente.get("inversor_marca_modelo")),
            ])
            self._foto_inline(drawer.body, cliente.get("modulo_foto_etiqueta_path"),
                               "Etiqueta do Módulo")

            self._secao_detalhe(drawer.body, "Acesso ao Telhado", [
                ("Fácil Acesso", "Sim" if cliente.get("acesso_telhado_facil") else "Não"),
                ("Observações", cliente.get("acesso_telhado_obs")),
            ])

            self._secao_detalhe(drawer.body, "Ponto de Água", [
                ("Localização", cliente.get("ponto_agua_local")),
                ("Pressão", cliente.get("ponto_agua_pressao")),
            ])
            self._foto_inline(drawer.body, cliente.get("ponto_agua_foto_path"), "Ponto de Água")

            self._secao_detalhe(drawer.body, "Inversores / Microinversores", [
                ("Quantidade", cliente.get("inversores_qtd")),
            ])
            self._foto_inline(drawer.body, cliente.get("inversores_foto_etiqueta_path"),
                               "Etiqueta do Inversor")

            self._secao_detalhe(drawer.body, "Endereço", [
                ("Endereço completo", cliente.get("endereco")),
                ("Link do Google Maps", cliente.get("google_maps_link")),
            ])

            # Foto principal do local, por último — isolada em try/except
            # próprio (uma foto corrompida nunca deve apagar o texto acima).
            if cliente.get("foto_local_path") and os.path.exists(cliente["foto_local_path"]):
                try:
                    ctk.CTkLabel(drawer.body, text="FOTO DO LOCAL",
                                 font=ctk.CTkFont(size=10, weight="bold"),
                                 text_color="gray").pack(anchor="w", padx=20, pady=(14, 4))
                    img = Image.open(cliente["foto_local_path"])
                    foto_ctk = ctk.CTkImage(light_image=img, dark_image=img, size=(360, 200))
                    label_foto = ctk.CTkLabel(drawer.body, image=foto_ctk, text="")
                    label_foto._ctk_img_ref = foto_ctk
                    label_foto.pack(pady=(0, 14), padx=20)
                except Exception:
                    pass
        except Exception as exc:
            ctk.CTkLabel(
                drawer.body, text=f"Não foi possível exibir todos os dados.\nDetalhe: {exc}",
                text_color=Marca.ERRO, wraplength=380, justify="left",
            ).pack(anchor="w", padx=20, pady=20)

        ctk.CTkButton(
            drawer.footer, text="✏️ Editar Cliente", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER,
            command=lambda: self._abrir_formulario(cliente, drawer),
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            drawer.footer, text="🗑️ Excluir Cliente", fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
            command=lambda: confirmar_exclusao(
                drawer, cliente["nome_razao_social"], lambda: self._excluir(cliente_id, drawer)
            ),
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Força o redesenho do CTkScrollableFrame recém-populado — evita o
        # bug de o drawer aparecer em branco até a janela ser redimensionada.
        drawer.update_idletasks()

    def _secao_detalhe(self, parent, titulo, pares):
        ctk.CTkLabel(parent, text=titulo, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=20, pady=(14, 4))
        for rotulo, valor in pares:
            bloco = ctk.CTkFrame(parent, fg_color="transparent")
            bloco.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(bloco, text=rotulo, font=ctk.CTkFont(size=10),
                         text_color="gray").pack(anchor="w")
            texto = "—" if valor in (None, "") else str(valor)
            ctk.CTkLabel(bloco, text=texto, font=ctk.CTkFont(size=13),
                         wraplength=380, justify="left").pack(anchor="w")

    def _foto_inline(self, parent, foto_path, rotulo):
        if not (foto_path and os.path.exists(foto_path)):
            return
        try:
            img = Image.open(foto_path)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(140, 105))
            label = ctk.CTkLabel(parent, image=ctk_img, text="")
            label._ctk_img_ref = ctk_img
            label.pack(anchor="w", padx=20, pady=(2, 4))
        except Exception:
            pass

    # ------------------------------------------------------------ ações --
    def _excluir(self, cliente_id, drawer=None):
        try:
            self.dao.excluir(cliente_id)
        except ValueError as exc:
            mostrar_alerta(self.winfo_toplevel(), "Não foi possível excluir", str(exc), "erro")
            return
        if drawer is not None and drawer.winfo_exists():
            drawer.destroy()
        self._drawer_aberto = None
        self._carregar_lista()

    def _abrir_formulario(self, cliente=None, drawer_para_fechar=None):
        editando = cliente is not None
        titulo = "Editar Cliente" if editando else "Novo Cliente"
        modal = ModalWindow(self.winfo_toplevel(), titulo, width=560, height=700)

        entradas = {}
        fotos_temp = {}
        labels_foto = {}

        def campo_texto(chave, rotulo):
            ctk.CTkLabel(modal.body, text=rotulo, font=ctk.CTkFont(size=12)).pack(
                anchor="w", padx=20, pady=(10, 0)
            )
            e = ctk.CTkEntry(modal.body, width=420)
            if editando:
                valor = cliente.get(chave)
                e.insert(0, "" if valor is None else str(valor))
            e.pack(anchor="w", padx=20, pady=(2, 0), fill="x")
            entradas[chave] = e

        def campo_foto(chave, rotulo):
            ctk.CTkLabel(modal.body, text=rotulo, font=ctk.CTkFont(size=12)).pack(
                anchor="w", padx=20, pady=(10, 0)
            )
            linha = ctk.CTkFrame(modal.body, fg_color="transparent")
            linha.pack(anchor="w", padx=20, pady=(2, 0), fill="x")
            texto_inicial = "Foto já cadastrada" if (editando and cliente.get(chave)) else \
                "Nenhuma foto selecionada"
            label_status = ctk.CTkLabel(linha, text=texto_inicial, text_color="gray")
            label_status.pack(side="left", padx=(0, 10))

            def selecionar():
                caminho = filedialog.askopenfilename(
                    title="Selecionar foto", filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
                )
                if caminho:
                    fotos_temp[chave] = caminho
                    label_status.configure(text=os.path.basename(caminho))

            ctk.CTkButton(linha, text="Selecionar...", width=110,
                          command=selecionar).pack(side="left")
            labels_foto[chave] = label_status

        campo_texto("nome_razao_social", "Nome do Cliente / Razão Social *")

        ctk.CTkLabel(modal.body, text="Empresa Prestadora *", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20, pady=(10, 0)
        )
        empresas = self.empresa_dao.listar()
        mapa_empresas = {e["nome"]: e["id"] for e in empresas}
        combo_empresa = ctk.CTkComboBox(modal.body, values=list(mapa_empresas.keys()), width=420)
        if editando and cliente.get("empresa_nome"):
            combo_empresa.set(cliente["empresa_nome"])
        elif empresas:
            combo_empresa.set("")
        combo_empresa.pack(anchor="w", padx=20, pady=(2, 0), fill="x")

        campo_texto("codigo_cliente", "Código do Cliente (opcional — exibido no cabeçalho do PDF)")
        campo_texto("cpf_cnpj", "CPF / CNPJ")
        campo_texto("contato_nome", "Nome do Contato")
        campo_texto("telefone", "Telefone")
        campo_foto("foto_local_path", "Foto do Local (Casa / Empresa)")

        campo_texto("qtd_modulos", "Quantidade de Módulos")
        campo_texto("modulo_marca", "Marca do Módulo")
        campo_texto("modulo_potencia_wp", "Potência do Módulo (Wp)")
        campo_texto("potencia_sistema_kwp", "Potência Total do Sistema (kWp)")
        campo_texto("inversor_marca_modelo", "Inversor — Marca / Modelo")
        campo_foto("modulo_foto_etiqueta_path", "Foto da Etiqueta do Módulo")

        ctk.CTkLabel(modal.body, text="Acesso ao Telhado", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20, pady=(10, 0)
        )
        var_acesso = ctk.StringVar(
            value="Sim" if (not editando or cliente.get("acesso_telhado_facil")) else "Não"
        )
        acesso_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
        acesso_frame.pack(anchor="w", padx=20, pady=(2, 0))
        ctk.CTkRadioButton(acesso_frame, text="Fácil Acesso: Sim",
                           variable=var_acesso, value="Sim").pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(acesso_frame, text="Não",
                           variable=var_acesso, value="Não").pack(side="left")
        campo_texto("acesso_telhado_obs", "Observações sobre o acesso")

        campo_texto("ponto_agua_local", "Ponto de Água — Localização")
        ctk.CTkLabel(modal.body, text="Ponto de Água — Pressão", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20, pady=(10, 0)
        )
        combo_pressao = ctk.CTkComboBox(modal.body, values=["Boa", "Ruim"], width=420)
        combo_pressao.set(cliente.get("ponto_agua_pressao") or "Boa" if editando else "Boa")
        combo_pressao.pack(anchor="w", padx=20, pady=(2, 0), fill="x")
        campo_foto("ponto_agua_foto_path", "Foto do Ponto de Água")

        campo_texto("inversores_qtd", "Quantidade de Inversores/Microinversores")
        campo_foto("inversores_foto_etiqueta_path", "Foto da Etiqueta do Inversor")

        campo_texto("endereco", "Endereço completo")
        campo_texto("google_maps_link", "Link do Google Maps")

        def salvar():
            nome = entradas["nome_razao_social"].get().strip()
            if not nome:
                mostrar_alerta(modal, "Campo obrigatório", "Informe o nome do cliente.", "aviso")
                return

            nome_empresa = combo_empresa.get().strip()
            empresa_id = mapa_empresas.get(nome_empresa)
            if not empresa_id:
                mostrar_alerta(
                    modal, "Campo obrigatório",
                    "Selecione a Empresa Prestadora responsável por este cliente "
                    "(necessário para filtrar o cliente no Gerador de Relatório).",
                    "aviso",
                )
                return

            dados = {chave: entrada.get().strip() for chave, entrada in entradas.items()}
            dados["empresa_id"] = empresa_id
            dados["acesso_telhado_facil"] = 1 if var_acesso.get() == "Sim" else 0
            dados["ponto_agua_pressao"] = combo_pressao.get()

            try:
                for campo_num in ("qtd_modulos", "inversores_qtd"):
                    dados[campo_num] = int(dados[campo_num]) if dados.get(campo_num) else None
                for campo_float in ("modulo_potencia_wp", "potencia_sistema_kwp"):
                    dados[campo_float] = (
                        float(dados[campo_float]) if dados.get(campo_float) else None
                    )
            except ValueError:
                mostrar_alerta(modal, "Valor inválido",
                                "Verifique os campos numéricos (quantidade/potência).", "erro")
                return

            for chave, _ in _CAMPOS_FOTO:
                if chave in fotos_temp:
                    dados[chave] = salvar_foto_padronizada(fotos_temp[chave])
                elif editando:
                    dados[chave] = cliente.get(chave)
                else:
                    dados[chave] = None

            if editando:
                self.dao.atualizar(cliente["id"], dados)
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
        empresas = self.empresa_dao.listar()
        self._empresas_map = {e["nome"]: e["id"] for e in empresas}
        self.combo_filtro_empresa.configure(
            values=["Todas as Empresas"] + list(self._empresas_map.keys())
        )
        self._carregar_lista()
