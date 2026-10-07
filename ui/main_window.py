"""Janela principal — sidebar com identidade Solaz Inovação e navegação
entre módulos. Quando o login é feito com a conta Master (dev_master), a
aba extra "Painel do Desenvolvedor" é liberada e vira a tela inicial."""
import gc
import os
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from config import APPEARANCE_MODE, COLOR_THEME, Marca, LOGO_SOLAZ_PATH
from ui.empresas_view import EmpresasView
from ui.clientes_view import ClientesView
from ui.relatorio_view import RelatorioView, transicao_suave, fade_in_janela
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

# Transição entre telas: a tela nova é montada em memória sob uma cortina lisa
# (cor do fundo) e só é revelada, com fade-in curto, quando está pronta.
_CORTINA_MS = 40                   # tempo coberto para o Tk pintar a tela nova
_PRE_CARREGAR_TELAS = True         # instancia as telas em segundo plano (sem exibir)
_PRE_CARREGAR_INTERVALO_MS = 250   # uma tela por vez, para não travar a interface


def cancelar_afters_pendentes(janela):
    """Cancela todos os `after()` ainda agendados na janela (inclusive os do
    próprio customtkinter: update, check_dpi_scaling, _click_animation...).
    Chamar logo ANTES de destroy(): sem isso, esses agendamentos disparam
    depois que a janela some e o Tcl imprime no terminal
    'invalid command name ... ("after" script)'. Nunca levanta exceção."""
    try:
        ids = janela.tk.splitlist(janela.tk.call("after", "info"))
    except Exception:
        return
    for after_id in ids:
        try:
            # Cancela direto no Tcl. NÃO usar janela.after_cancel(): ele apaga
            # o comando Tcl na janela errada e, no destroy() do widget dono,
            # dá "TclError: can't delete Tcl command".
            janela.tk.call("after", "cancel", after_id)
        except Exception:
            pass


class MainWindow(ctk.CTk):
    def __init__(self, is_master: bool = False, on_logout=None):
        super().__init__()
        self.is_master = is_master
        self._on_logout = on_logout    # chamado após o logout (main.py reabre o Login)
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
        self._modulo_atual = None
        self._cortina = None
        self._revelar_job = None
        self._pre_falhas = set()
        self._mostrar_modulo("dev_panel" if is_master else "empresas", animar=False)
        if _PRE_CARREGAR_TELAS:
            self.after(400, self._pre_carregar_proxima)

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
            with Image.open(LOGO_SOLAZ_PATH) as arquivo:
                img = arquivo.convert("RGBA")   # decodifica agora, não na 1ª pintura
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
    def _obter_view(self, chave):
        if chave not in self._views_instanciadas:
            _, _, classe_view, _ = next(m for m in self._modulos if m[0] == chave)
            self._views_instanciadas[chave] = classe_view(self.content_frame)
        return self._views_instanciadas[chave]

    def _mostrar_modulo(self, chave, animar=True):
        for k, btn in self._botoes.items():
            btn.configure(fg_color=Marca.PRIMARIA_CLARA if k == chave else "transparent")

        # Clique na tela que já está aberta: só atualiza, sem animação.
        if chave == self._modulo_atual and chave in self._views_instanciadas:
            view = self._views_instanciadas[chave]
            if hasattr(view, "ao_exibir"):
                with transicao_suave(self, fade=False):
                    view.ao_exibir()
            return

        if animar:
            self._erguer_cortina()
        try:
            # fade=False: o fade-in só começa quando a cortina sai (_revelar)
            with transicao_suave(self, fade=False):
                for widget in self.content_frame.winfo_children():
                    widget.grid_forget()
                view = self._obter_view(chave)
                view.grid(row=0, column=0, sticky="nsew")
                self._modulo_atual = chave
                if hasattr(view, "ao_exibir"):
                    view.ao_exibir()
        finally:
            if animar:
                self._agendar_revelar()

    # ------------------------------------------------------------ encerrar --
    def fechar_aplicacao(self):
        """Fecha o programa exatamente como o X da janela (o main.py registra o
        encerramento limpo em WM_DELETE_WINDOW). Usado pela atualização."""
        try:
            self.tk.call(self.wm_protocol("WM_DELETE_WINDOW"))
        except Exception:
            cancelar_afters_pendentes(self)
            try:
                self.quit()
            finally:
                self.destroy()

    # ------------------------------------------------------------ logout --
    def fazer_logout(self):
        """Encerra a sessão: descarta as telas (e os dados em memória que elas
        guardam), fecha esta janela e avisa o main.py, que reabre o Login.
        A próxima MainWindow nasce do zero — sem herdar nada, nem o perfil
        Master/Comum desta sessão."""
        try:
            if self._revelar_job:
                self.after_cancel(self._revelar_job)
                self._revelar_job = None
        except Exception:
            pass
        self._views_instanciadas.clear()
        self._pre_falhas.clear()
        self._modulo_atual = None
        callback = self._on_logout
        cancelar_afters_pendentes(self)
        try:
            self.quit()
        except Exception:
            pass
        self.destroy()

        # Limpeza de caches/rascunhos da sessão (best-effort, nunca levanta).
        try:
            from pdf.report_generator import limpar_cache_imagens
            limpar_cache_imagens()
        except Exception:
            pass
        try:
            from utils.image_utils import limpar_pasta_temporaria
            limpar_pasta_temporaria()
        except Exception:
            pass
        gc.collect()

        if callback:
            callback()

    # ---------------------------------------------- cortina / pré-carga --
    def _erguer_cortina(self):
        try:
            if self._revelar_job:
                self.after_cancel(self._revelar_job)
                self._revelar_job = None
            if self._cortina is None or not self._cortina.winfo_exists():
                self._cortina = tk.Frame(self, bd=0, highlightthickness=0)
            try:
                cor = self.cget("bg")
            except Exception:
                cor = "#EBEBEB"
            self._cortina.configure(bg=cor)
            self._cortina.place(in_=self.content_frame, x=0, y=0, relwidth=1, relheight=1)
            self._cortina.lift()
            self.update_idletasks()      # a cortina aparece ANTES de mexer nas telas
        except Exception:
            pass

    def _agendar_revelar(self):
        try:
            if self._revelar_job:
                self.after_cancel(self._revelar_job)
            self._revelar_job = self.after(_CORTINA_MS, self._revelar)
        except Exception:
            self._revelar()

    def _revelar(self):
        self._revelar_job = None
        try:
            if self._cortina is not None:
                self._cortina.place_forget()
            fade_in_janela(self)
        except Exception:                # janela fechada antes da hora
            pass

    def _pre_carregar_proxima(self):
        """Instancia (sem exibir) uma tela ainda não criada, uma por vez, para o
        primeiro clique em cada módulo não precisar construir a interface."""
        for chave, _, _, _ in self._modulos:
            if chave in self._views_instanciadas or chave in self._pre_falhas:
                continue
            try:
                self._obter_view(chave)
            except Exception:
                self._pre_falhas.add(chave)   # o erro reaparece normalmente no clique
            self.after(_PRE_CARREGAR_INTERVALO_MS, self._pre_carregar_proxima)
            return
