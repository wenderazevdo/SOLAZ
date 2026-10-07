"""
Tela de Login — layout split de 2 colunas, estilo dashboard executivo.

Coluna esquerda: painel institucional com a logo da Solaz Inovação sobre
fundo gradiente escuro com motivo sutil de painéis solares. Coluna
direita: formulário limpo e centralizado, campos arredondados, botão de
destaque na cor primária da marca e, no canto inferior direito, o botão
flat "Criar nova conta". Toda a regra de negócio (status, HWID, conta
Master) vive em services/auth_service.py — esta tela só chama e exibe.
"""
import os

import customtkinter as ctk
from PIL import Image

from config import Marca, LOGO_SOLAZ_PATH, ASSETS_DIR
import services.auth_service as auth_service
from services.security_service import pre_carregar_hwid
from ui.components import ModalWindow, mostrar_alerta

_PAINEL_LARGURA = 380
_JANELA_LARGURA = 900
_JANELA_ALTURA = 600

_MENSAGENS_ERRO = {
    auth_service.MOTIVO_CREDENCIAIS_INVALIDAS: "Usuário ou senha inválidos.",
    auth_service.MOTIVO_PENDENTE:
        "Cadastro aguardando liberação do desenvolvedor para este computador.",
    auth_service.MOTIVO_BLOQUEADO: "Este acesso está bloqueado. Fale com o administrador.",
    auth_service.MOTIVO_HWID_DIVERGENTE:
        "Este usuário já está vinculado a outro computador. Acesso bloqueado.",
}


def _cancelar_afters_pendentes(janela):
    """Cancela os `after()` ainda agendados (inclusive os do customtkinter)
    antes do destroy(); senão eles disparam depois e o terminal mostra
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


class LoginWindow(ctk.CTk):
    def __init__(self, on_login_success):
        super().__init__()
        # on_login_success(is_master: bool) — a janela principal decide se
        # abre o app normal ou o Painel do Desenvolvedor.
        self.on_login_success = on_login_success

        # O HWID (WMI/PowerShell) pode levar 1-2s para responder; calcula em
        # segundo plano assim que a tela abre, para o login não travar.
        pre_carregar_hwid()

        self.title(f"{Marca.NOME} — Sistema de Relatórios Fotovoltaicos")
        self.geometry(f"{_JANELA_LARGURA}x{_JANELA_ALTURA}")
        self.resizable(False, False)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_painel_institucional()
        self._construir_formulario()

    # ----------------------------------------------------- painel esq. --
    def _construir_painel_institucional(self):
        painel = ctk.CTkFrame(self, width=_PAINEL_LARGURA, corner_radius=0,
                               fg_color=Marca.PRIMARIA)
        painel.grid(row=0, column=0, sticky="nsw")
        painel.grid_propagate(False)

        bg_path = os.path.join(ASSETS_DIR, "login_bg.png")
        if os.path.exists(bg_path):
            try:
                img = Image.open(bg_path).resize(
                    (_PAINEL_LARGURA, _JANELA_ALTURA), Image.LANCZOS
                )
                self._bg_img = ctk.CTkImage(light_image=img, dark_image=img,
                                             size=(_PAINEL_LARGURA, _JANELA_ALTURA))
                label_bg = ctk.CTkLabel(painel, image=self._bg_img, text="")
                label_bg.place(x=0, y=0)
            except Exception:
                pass

        conteudo = ctk.CTkFrame(painel, fg_color="transparent")
        conteudo.place(relx=0.5, rely=0.32, anchor="center")

        if os.path.exists(LOGO_SOLAZ_PATH):
            img_logo = Image.open(LOGO_SOLAZ_PATH)
            self._logo_img = ctk.CTkImage(light_image=img_logo, dark_image=img_logo,
                                           size=(110, 110))
            ctk.CTkLabel(conteudo, image=self._logo_img, text="").pack()

        ctk.CTkLabel(
            conteudo, text="Solaz Inovação", font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white",
        ).pack(pady=(14, 2))
        ctk.CTkLabel(
            conteudo, text="Gestão Técnica de Sistemas Fotovoltaicos",
            font=ctk.CTkFont(size=12), text_color=Marca.ACCENT,
        ).pack()

        ctk.CTkLabel(
            painel,
            text="Relatórios de manutenção preventiva,\ncadastros e agenda em um só lugar.",
            font=ctk.CTkFont(size=11), text_color="#B9CBDA", justify="center",
        ).place(relx=0.5, rely=0.92, anchor="center")

    # ----------------------------------------------------- formulário --
    def _construir_formulario(self):
        painel = ctk.CTkFrame(self, corner_radius=0, fg_color=("white", "gray14"))
        painel.grid(row=0, column=1, sticky="nsew")

        container = ctk.CTkFrame(painel, fg_color="transparent")
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container, text="Bem-vindo de volta",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=Marca.PRIMARIA,
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            container, text="Entre com suas credenciais para acessar o sistema.",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(anchor="w", pady=(0, 26))

        ctk.CTkLabel(container, text="Usuário", font=ctk.CTkFont(size=12),
                     text_color=Marca.TEXTO_SECUNDARIO).pack(anchor="w")
        self.entry_usuario = ctk.CTkEntry(
            container, width=320, height=42, corner_radius=12,
            placeholder_text="Digite seu usuário",
        )
        self.entry_usuario.pack(pady=(4, 16))

        ctk.CTkLabel(container, text="Senha", font=ctk.CTkFont(size=12),
                     text_color=Marca.TEXTO_SECUNDARIO).pack(anchor="w")
        self.entry_senha = ctk.CTkEntry(
            container, width=320, height=42, corner_radius=12, show="•",
            placeholder_text="Digite sua senha",
        )
        self.entry_senha.pack(pady=(4, 6))
        self.entry_senha.bind("<Return>", lambda e: self._tentar_login())

        self.label_erro = ctk.CTkLabel(container, text="", text_color=Marca.ERRO,
                                        font=ctk.CTkFont(size=11), wraplength=320,
                                        justify="left")
        self.label_erro.pack(anchor="w", pady=(0, 10))

        self.btn_entrar = ctk.CTkButton(
            container, text="Entrar", width=320, height=42, corner_radius=12,
            fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._tentar_login,
        )
        self.btn_entrar.pack(pady=(8, 0))

        # Canto inferior direito do painel de formulário — botão flat, sem
        # contorno, para abrir o cadastro de nova conta.
        ctk.CTkButton(
            painel, text="Criar nova conta", fg_color="transparent", hover=False,
            text_color=Marca.ACCENT, font=ctk.CTkFont(size=11, underline=True),
            command=self._abrir_cadastro, width=0, height=0,
        ).place(relx=0.97, rely=0.96, anchor="se")

    # ------------------------------------------------------------ login --
    def _tentar_login(self):
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get()

        if not usuario or not senha:
            self.label_erro.configure(text="Preencha usuário e senha.")
            return

        self.btn_entrar.configure(state="disabled", text="Entrando...")
        self.update_idletasks()
        try:
            resultado = auth_service.autenticar(usuario, senha)
        finally:
            self.btn_entrar.configure(state="normal", text="Entrar")

        if not resultado.sucesso:
            self.label_erro.configure(
                text=_MENSAGENS_ERRO.get(resultado.motivo, "Não foi possível entrar.")
            )
            return

        _cancelar_afters_pendentes(self)
        self.destroy()
        self.on_login_success(resultado.is_master)

    # --------------------------------------------------------- cadastro --
    def _abrir_cadastro(self):
        modal = ModalWindow(self, "Criar Nova Conta", width=440, height=360)

        ctk.CTkLabel(
            modal.body, text="A conta é vinculada a este computador e fica pendente\n"
                              "até a aprovação do desenvolvedor.",
            text_color="gray", font=ctk.CTkFont(size=11), justify="left",
        ).pack(anchor="w", padx=20, pady=(16, 14))

        ctk.CTkLabel(modal.body, text="Usuário", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20
        )
        entry_usuario = ctk.CTkEntry(modal.body, width=380, corner_radius=10)
        entry_usuario.pack(padx=20, pady=(4, 12))

        ctk.CTkLabel(modal.body, text="Senha", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20
        )
        entry_senha = ctk.CTkEntry(modal.body, width=380, corner_radius=10, show="•")
        entry_senha.pack(padx=20, pady=(4, 12))

        ctk.CTkLabel(modal.body, text="Confirmar Senha", font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=20
        )
        entry_confirmar = ctk.CTkEntry(modal.body, width=380, corner_radius=10, show="•")
        entry_confirmar.pack(padx=20, pady=(4, 4))

        label_erro_cadastro = ctk.CTkLabel(modal.body, text="", text_color=Marca.ERRO,
                                            font=ctk.CTkFont(size=11), wraplength=380)
        label_erro_cadastro.pack(anchor="w", padx=20, pady=(4, 0))

        def cadastrar():
            usuario = entry_usuario.get().strip()
            senha = entry_senha.get()
            confirmar = entry_confirmar.get()

            if senha != confirmar:
                label_erro_cadastro.configure(text="As senhas não conferem.")
                return

            resultado = auth_service.registrar_conta(usuario, senha)
            if not resultado.sucesso:
                label_erro_cadastro.configure(text=resultado.mensagem)
                return

            modal.destroy()
            mostrar_alerta(self, "Cadastro Realizado", resultado.mensagem, "sucesso")

        ctk.CTkButton(
            modal.body, text="Cadastrar", width=380, height=40, corner_radius=10,
            fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
            command=cadastrar,
        ).pack(padx=20, pady=(12, 16))
