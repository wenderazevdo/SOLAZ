"""Janela principal — sidebar com identidade Solaz Inovação e navegação
entre módulos. Quando o login é feito com a conta Master (dev_master), a
aba extra "Painel do Desenvolvedor" é liberada e vira a tela inicial."""
import os

import customtkinter as ctk
from PIL import Image

from config import APPEARANCE_MODE, COLOR_THEME, Marca, LOGO_SOLAZ_PATH
from ui.empresas_view import EmpresasView
from ui.clientes_view import ClientesView
from ui.relatorio_view import RelatorioView
from ui.agenda_view import AgendaView
from ui.servicos_realizados_view import ServicosRealizadosView
from ui.config_view import ConfigView
from ui.dev_panel_view import DevPanelView

ctk.set_appearance_mode(APPEARANCE_MODE)
ctk.set_default_color_theme(COLOR_THEME)

# (chave, rótulo, classe da view, ícone emoji simples)
_MODULOS_BASE = [
    ("empresas", "Minhas Empresas", EmpresasView, "🏢"),
    ("clientes", "Clientes", ClientesView, "👥"),
    ("relatorio", "Gerar Relatório", RelatorioView, "📄"),
    ("agenda", "Agenda / Calendário", AgendaView, "🗓️"),
    ("servicos", "Serviços Realizados", ServicosRealizadosView, "💰"),
    ("config", "Configurações", ConfigView, "⚙️"),
]
_MODULO_DEV = ("dev_panel", "Painel do Desenvolvedor", DevPanelView, "🛠️")


class MainWindow(ctk.CTk):
    def __init__(self, is_master: bool = False):
        super().__init__()
        self.is_master = is_master
        self._modulos = list(_MODULOS_BASE) + ([_MODULO_DEV] if is_master else [])

        titulo = f"{Marca.NOME} — Sistema de Relatórios de Manutenção Fotovoltaica"
        if is_master:
            titulo += " [MODO DESENVOLVEDOR]"
        self.title(titulo)
        self.geometry("1240x780")
        self.minsize(1040, 660)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_sidebar()

        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self._views_instanciadas = {}
        self._mostrar_modulo("dev_panel" if is_master else "empresas")

    # ------------------------------------------------------------ sidebar --
    def _construir_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=240, corner_radius=0, fg_color=Marca.PRIMARIA,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        topo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        topo.pack(pady=(26, 18), padx=20, fill="x")

        if os.path.exists(LOGO_SOLAZ_PATH):
            img = Image.open(LOGO_SOLAZ_PATH)
            self._logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(52, 52))
            ctk.CTkLabel(topo, image=self._logo_img, text="").pack(side="left", padx=(0, 10))

        texto_frame = ctk.CTkFrame(topo, fg_color="transparent")
        texto_frame.pack(side="left")
        ctk.CTkLabel(
            texto_frame, text="Solaz", font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white",
        ).pack(anchor="w")
        ctk.CTkLabel(
            texto_frame, text="Inovação", font=ctk.CTkFont(size=11),
            text_color=Marca.ACCENT,
        ).pack(anchor="w")

        if self.is_master:
            ctk.CTkLabel(
                self.sidebar, text="⚠ MODO DESENVOLVEDOR", font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#FBBF24",
            ).pack(padx=20, pady=(0, 10), anchor="w")

        self._botoes = {}
        for chave, rotulo, _, icone in self._modulos:
            btn = ctk.CTkButton(
                self.sidebar, text=f"  {icone}  {rotulo}", anchor="w",
                fg_color="transparent", hover_color=Marca.PRIMARIA_CLARA,
                text_color="white", height=42, font=ctk.CTkFont(size=13),
                command=lambda c=chave: self._mostrar_modulo(c),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self._botoes[chave] = btn

        ctk.CTkLabel(
            self.sidebar, text="Aparência", font=ctk.CTkFont(size=11),
            text_color="#9FB3C8",
        ).pack(side="bottom", pady=(0, 4))
        self.menu_aparencia = ctk.CTkOptionMenu(
            self.sidebar, values=["System", "Light", "Dark"],
            command=lambda modo: ctk.set_appearance_mode(modo),
            width=170, fg_color=Marca.PRIMARIA_CLARA,
            button_color=Marca.ACCENT, button_hover_color=Marca.ACCENT_HOVER,
        )
        self.menu_aparencia.set(APPEARANCE_MODE)
        self.menu_aparencia.pack(side="bottom", pady=(0, 20))

    # ------------------------------------------------------------- troca --
    def _mostrar_modulo(self, chave):
        for k, btn in self._botoes.items():
            btn.configure(fg_color=Marca.PRIMARIA_CLARA if k == chave else "transparent")

        for widget in self.content_frame.winfo_children():
            widget.grid_forget()

        if chave not in self._views_instanciadas:
            _, _, classe_view, _ = next(m for m in self._modulos if m[0] == chave)
            self._views_instanciadas[chave] = classe_view(self.content_frame)

        view = self._views_instanciadas[chave]
        view.grid(row=0, column=0, sticky="nsew")
        if hasattr(view, "ao_exibir"):
            view.ao_exibir()
