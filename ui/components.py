"""
Componentes de UI reutilizáveis: Modal centralizado, Drawer (painel lateral
de detalhes), diálogo de confirmação, seletor de hora/minuto e modal de
busca rápida — usados pelas telas de Empresas, Clientes, Relatório e Agenda
para seguir as heurísticas de Nielsen (evitar formulários abertos por
padrão, confirmar exclusões, busca eficiente etc).
"""
import customtkinter as ctk

from config import Marca


class ModalWindow(ctk.CTkToplevel):
    """Janela modal centralizada sobre a janela principal, usada para
    formulários de cadastro (\"+ Novo Cadastro\")."""

    def __init__(self, master, titulo: str, width: int = 560, height: int = 640):
        super().__init__(master)
        self.title(titulo)
        self.geometry(f"{width}x{height}")
        self.minsize(420, 360)
        self.transient(master)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=Marca.PRIMARIA, corner_radius=0, height=52)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        ctk.CTkLabel(
            header, text=titulo, text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            header, text="✕", width=32, height=32, fg_color="transparent",
            hover_color=Marca.PRIMARIA_CLARA, command=self.destroy,
        ).pack(side="right", padx=10, pady=8)

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)

        self._centralizar(master, width, height)

    def _centralizar(self, master, width, height):
        self.update_idletasks()
        try:
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            x = mx + (mw - width) // 2
            y = my + (mh - height) // 2
            self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass


class DrawerWindow(ctk.CTkToplevel):
    """Painel lateral de detalhes (Drawer), ancorado à direita da janela
    principal — abre ao clicar em um item de lista (cliente/empresa) e
    mostra todas as informações cadastradas + ações de Editar/Excluir."""

    def __init__(self, master, titulo: str, width: int = 420):
        super().__init__(master)
        self.title(titulo)
        self.overrideredirect(False)
        self.transient(master)
        self.resizable(False, True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=Marca.PRIMARIA, corner_radius=0, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        self.label_titulo = ctk.CTkLabel(
            header, text=titulo, text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"), wraplength=280, justify="left",
        )
        self.label_titulo.pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            header, text="✕", width=32, height=32, fg_color="transparent",
            hover_color=Marca.PRIMARIA_CLARA, command=self.destroy,
        ).pack(side="right", padx=10, pady=8)

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)

        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=2, column=0, sticky="ew", padx=16, pady=14)

        self._ancorar_direita(master, width)
        self.lift()
        self.focus_force()

    def _ancorar_direita(self, master, width):
        self.update_idletasks()
        try:
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mh = master.winfo_height()
            mw = master.winfo_width()
            x = mx + mw - width
            self.geometry(f"{width}x{mh}+{x}+{my}")
        except Exception:
            self.geometry(f"{width}x700")


def confirmar_exclusao(master, nome_item: str, on_confirm, tipo="registro"):
    """Abre um modal de confirmação de exclusão. `on_confirm` é chamado sem
    argumentos caso o usuário confirme."""
    modal = ctk.CTkToplevel(master)
    modal.title("Confirmar exclusão")
    modal.geometry("380x190")
    modal.resizable(False, False)
    modal.transient(master)
    modal.grab_set()
    modal.lift()
    modal.focus_force()

    ctk.CTkLabel(
        modal, text="⚠️", font=ctk.CTkFont(size=30),
    ).pack(pady=(22, 4))
    ctk.CTkLabel(
        modal, text=f"Tem certeza que deseja excluir\n\"{nome_item}\"?",
        font=ctk.CTkFont(size=13, weight="bold"), justify="center",
    ).pack(pady=(0, 4))
    ctk.CTkLabel(
        modal, text=f"Esta ação não pode ser desfeita.",
        text_color="gray", font=ctk.CTkFont(size=11),
    ).pack(pady=(0, 14))

    botoes = ctk.CTkFrame(modal, fg_color="transparent")
    botoes.pack()

    def _confirmar():
        modal.destroy()
        on_confirm()

    ctk.CTkButton(
        botoes, text="Cancelar", width=120, fg_color="gray40", hover_color="gray30",
        command=modal.destroy,
    ).pack(side="left", padx=8)
    ctk.CTkButton(
        botoes, text="Excluir", width=120, fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
        command=_confirmar,
    ).pack(side="left", padx=8)

    # centraliza sobre a master
    modal.update_idletasks()
    try:
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        x = mx + (mw - 380) // 2
        y = my + (mh - 190) // 2
        modal.geometry(f"380x190+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass


def mostrar_alerta(master, titulo: str, mensagem: str, tipo="info"):
    """Modal simples de alerta (sucesso/erro/aviso), consistente com a
    identidade visual — usado no lugar do messagebox padrão do sistema."""
    cores = {
        "sucesso": (Marca.SUCESSO_TEXTO, "✅"),
        "erro": (Marca.ERRO, "⚠️"),
        "aviso": (Marca.ACCENT, "ℹ️"),
        "info": (Marca.ACCENT, "ℹ️"),
    }
    cor_texto, icone = cores.get(tipo, cores["info"])

    modal = ctk.CTkToplevel(master)
    modal.title(titulo)
    modal.geometry("400x220")
    modal.resizable(False, False)
    modal.transient(master)
    modal.grab_set()
    modal.lift()
    modal.focus_force()

    ctk.CTkLabel(modal, text=icone, font=ctk.CTkFont(size=30)).pack(pady=(22, 4))
    ctk.CTkLabel(
        modal, text=titulo, font=ctk.CTkFont(size=14, weight="bold"), text_color=cor_texto,
    ).pack(pady=(0, 6))
    ctk.CTkLabel(
        modal, text=mensagem, font=ctk.CTkFont(size=12), justify="center", wraplength=340,
    ).pack(pady=(0, 16), padx=16)
    ctk.CTkButton(modal, text="OK", width=120, command=modal.destroy).pack()

    modal.update_idletasks()
    try:
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        x = mx + (mw - 400) // 2
        y = my + (mh - 220) // 2
        modal.geometry(f"400x220+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass
    return modal


def formatar_reais(valor) -> str:
    """Formata um número como moeda brasileira: 1234.5 -> 'R$ 1.234,50'."""
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return "R$ 0,00"
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def criar_seletor_hora_minuto(parent, hora_inicial="09", minuto_inicial="00"):
    """Cria um par de CTkOptionMenu (hora 00-23 / minuto de 00 a 45 em passos
    de 15) para prevenção de erros de digitação em horários (heurística de
    Nielsen 'prevenção de erros'). Retorna (frame, menu_hora, menu_minuto)."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    horas = [f"{h:02d}" for h in range(0, 24)]
    minutos = ["00", "15", "30", "45"]

    menu_hora = ctk.CTkOptionMenu(frame, values=horas, width=70)
    menu_hora.set(hora_inicial)
    menu_hora.pack(side="left")
    ctk.CTkLabel(frame, text=":").pack(side="left", padx=4)
    menu_minuto = ctk.CTkOptionMenu(frame, values=minutos, width=70)
    menu_minuto.set(minuto_inicial)
    menu_minuto.pack(side="left")

    return frame, menu_hora, menu_minuto


def abrir_busca_modal(master, titulo: str, itens, on_selecionar, placeholder="Digite para buscar..."):
    """Modal de pesquisa rápida com filtro em tempo real (usado pela lupa
    🔍 ao lado dos combos de Empresa/Cliente no Gerador de Relatório).

    `itens`: lista de dicts no formato {"id": ..., "label": ..., "sublabel": ...}
             ("sublabel" é opcional — texto secundário cinza abaixo do label).
    `on_selecionar`: callback chamado com o item completo (dict) escolhido;
                      o modal se fecha automaticamente após a seleção.
    """
    modal = ctk.CTkToplevel(master)
    modal.title(titulo)
    modal.geometry("460x520")
    modal.minsize(360, 320)
    modal.transient(master)
    modal.grab_set()
    modal.lift()
    modal.focus_force()

    modal.grid_columnconfigure(0, weight=1)
    modal.grid_rowconfigure(2, weight=1)

    header = ctk.CTkFrame(modal, fg_color=Marca.PRIMARIA, corner_radius=0, height=52)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    ctk.CTkLabel(
        header, text=titulo, text_color="white", font=ctk.CTkFont(size=15, weight="bold"),
    ).pack(side="left", padx=20, pady=12)
    ctk.CTkButton(
        header, text="✕", width=32, height=32, fg_color="transparent",
        hover_color=Marca.PRIMARIA_CLARA, command=modal.destroy,
    ).pack(side="right", padx=10, pady=8)

    entry_busca = ctk.CTkEntry(modal, placeholder_text=f"🔍  {placeholder}")
    entry_busca.grid(row=1, column=0, sticky="ew", padx=16, pady=14)
    entry_busca.focus_set()

    resultados = ctk.CTkScrollableFrame(modal, fg_color="transparent")
    resultados.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 14))
    resultados.grid_columnconfigure(0, weight=1)

    def selecionar(item):
        modal.destroy()
        on_selecionar(item)

    def renderizar(lista_filtrada):
        for w in resultados.winfo_children():
            w.destroy()
        if not lista_filtrada:
            ctk.CTkLabel(resultados, text="Nenhum resultado encontrado.",
                         text_color="gray").pack(pady=20)
            return
        for item in lista_filtrada:
            linha = ctk.CTkButton(
                resultados, text=item["label"], anchor="w", fg_color="transparent",
                hover_color=("gray85", "gray25"), text_color=("black", "white"),
                height=36, command=lambda it=item: selecionar(it),
            )
            linha.pack(fill="x", padx=4, pady=2)
            if item.get("sublabel"):
                ctk.CTkLabel(
                    resultados, text=item["sublabel"], text_color="gray",
                    font=ctk.CTkFont(size=10),
                ).pack(anchor="w", padx=16, pady=(0, 4))

    def filtrar(event=None):
        termo = entry_busca.get().strip().lower()
        if not termo:
            renderizar(itens)
            return
        filtrados = [i for i in itens if termo in i["label"].lower()]
        renderizar(filtrados)

    entry_busca.bind("<KeyRelease>", filtrar)
    renderizar(itens)

    modal.update_idletasks()
    try:
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        x = mx + (mw - 460) // 2
        y = my + (mh - 520) // 2
        modal.geometry(f"460x520+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass
    return modal
