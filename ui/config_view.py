"""Módulo 5: Configurações — pasta padrão de relatórios, aparência, senha
e verificação de atualizações via GitHub Releases."""
import threading

import customtkinter as ctk
from tkinter import filedialog, messagebox

from config import Marca, APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME
from models.usuario_dao import UsuarioDAO
from models.configuracao_dao import ConfiguracaoDAO
from utils.github_updater import verificar_atualizacao, ErroVerificacaoAtualizacao
from ui.components import mostrar_alerta


class ConfigView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.dao = UsuarioDAO()
        self.config_dao = ConfiguracaoDAO()

        # ---- Card: Pasta Padrão de Relatórios ----
        pasta_frame = ctk.CTkFrame(self, corner_radius=14)
        pasta_frame.pack(fill="x", padx=24, pady=(24, 12), anchor="n")

        # Cabeçalho: título à esquerda e botão de logout em destaque à direita
        # (na mesma linha, para não aumentar a altura da tela).
        cabecalho = ctk.CTkFrame(pasta_frame, fg_color="transparent")
        cabecalho.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(cabecalho, text="Configurações", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(side="left")
        ctk.CTkButton(
            cabecalho, text="🚪  Sair da Conta (Logout)", height=34,
            font=ctk.CTkFont(size=13, weight="bold"), text_color="white",
            fg_color=Marca.ERRO, hover_color=getattr(Marca, "ERRO_HOVER", "#B91C1C"),
            command=self._sair_da_conta,
        ).pack(side="right")

        ctk.CTkLabel(
            pasta_frame, text="Pasta Raiz Padrão dos Relatórios",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=Marca.PRIMARIA,
        ).pack(anchor="w", padx=18, pady=(6, 2))
        ctk.CTkLabel(
            pasta_frame,
            text="Todos os PDFs gerados são organizados automaticamente dentro dela,\n"
                 "na estrutura [Empresa]/[Cliente]/[Código].pdf.",
            justify="left", text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=18, pady=(0, 10))

        linha_pasta = ctk.CTkFrame(pasta_frame, fg_color="transparent")
        linha_pasta.pack(fill="x", padx=18, pady=(0, 18))
        linha_pasta.grid_columnconfigure(0, weight=1)

        self.label_pasta_atual = ctk.CTkLabel(
            linha_pasta, text=self.config_dao.obter_pasta_relatorios(),
            anchor="w", fg_color=Marca.CINZA_TECNICO, corner_radius=6,
            text_color=Marca.TEXTO, height=36,
        )
        self.label_pasta_atual.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipadx=10)
        ctk.CTkButton(
            linha_pasta, text="Alterar Pasta...", width=150, fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._alterar_pasta,
        ).grid(row=0, column=1)

        # ---- Card: Senha ----
        frame = ctk.CTkFrame(self, corner_radius=14)
        frame.pack(fill="x", padx=24, pady=(0, 24), anchor="n")

        ctk.CTkLabel(frame, text="Alterar Senha do Usuário",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(18, 6))
        self.entry_usuario = ctk.CTkEntry(frame, placeholder_text="Usuário", width=300)
        self.entry_usuario.insert(0, "admin")
        self.entry_usuario.pack(anchor="w", padx=18, pady=4)
        self.entry_senha_atual = ctk.CTkEntry(
            frame, placeholder_text="Senha atual", show="•", width=300
        )
        self.entry_senha_atual.pack(anchor="w", padx=18, pady=4)
        self.entry_senha_nova = ctk.CTkEntry(
            frame, placeholder_text="Nova senha", show="•", width=300
        )
        self.entry_senha_nova.pack(anchor="w", padx=18, pady=4)

        ctk.CTkButton(frame, text="Salvar Nova Senha", fg_color=Marca.ACCENT,
                      hover_color=Marca.ACCENT_HOVER,
                      command=self._alterar_senha).pack(anchor="w", padx=18, pady=18)

        # ---- Card: Sobre / Atualizações ----
        sobre_frame = ctk.CTkFrame(self, corner_radius=14)
        sobre_frame.pack(fill="x", padx=24, pady=(0, 24), anchor="n")

        ctk.CTkLabel(sobre_frame, text="Sobre o Sistema",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(18, 6))
        ctk.CTkLabel(
            sobre_frame, text=f"Versão instalada: {APP_VERSION}",
            text_color="gray", font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(
            sobre_frame, text=f"Repositório: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=18, pady=(0, 10))

        linha_update = ctk.CTkFrame(sobre_frame, fg_color="transparent")
        linha_update.pack(anchor="w", padx=18, pady=(0, 18))
        self.btn_verificar_update = ctk.CTkButton(
            linha_update, text="Verificar Atualizações", fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._verificar_atualizacoes,
        )
        self.btn_verificar_update.pack(side="left")
        self.label_status_update = ctk.CTkLabel(
            linha_update, text="", text_color="gray", font=ctk.CTkFont(size=11),
        )
        self.label_status_update.pack(side="left", padx=(12, 0))

    # ----------------------------------------------------------- logout --
    def _sair_da_conta(self):
        """Pede confirmação e, se confirmado, pede à janela principal para
        encerrar a sessão e voltar à tela de Login."""
        janela = self.winfo_toplevel()
        if not hasattr(janela, "fazer_logout"):
            return
        if messagebox.askyesno("Sair da conta", "Deseja realmente sair da sua conta?",
                               parent=janela):
            janela.fazer_logout()

    # ------------------------------------------------------------ pasta --
    def _alterar_pasta(self):
        pasta_atual = self.config_dao.obter_pasta_relatorios()
        nova_pasta = filedialog.askdirectory(
            title="Selecionar pasta raiz dos relatórios",
            initialdir=pasta_atual if pasta_atual else None,
        )
        if not nova_pasta:
            return  # usuário cancelou o diálogo
        self.config_dao.definir_pasta_relatorios(nova_pasta)
        self.label_pasta_atual.configure(text=nova_pasta)
        mostrar_alerta(
            self.winfo_toplevel(), "Pasta atualizada",
            f"Os próximos relatórios serão salvos em:\n{nova_pasta}", "sucesso",
        )

    # ------------------------------------------------------------ senha --
    def _alterar_senha(self):
        usuario = self.entry_usuario.get().strip()
        senha_atual = self.entry_senha_atual.get()
        senha_nova = self.entry_senha_nova.get()

        if not senha_nova or len(senha_nova) < 4:
            mostrar_alerta(self.winfo_toplevel(), "Senha inválida",
                            "A nova senha deve ter ao menos 4 caracteres.", "aviso")
            return
        if not self.dao.validar_login(usuario, senha_atual):
            mostrar_alerta(self.winfo_toplevel(), "Senha atual incorreta",
                            "Verifique a senha atual informada.", "erro")
            return

        self.dao.alterar_senha(usuario, senha_nova)
        mostrar_alerta(self.winfo_toplevel(), "Senha alterada",
                        "Senha atualizada com sucesso.", "sucesso")
        self.entry_senha_atual.delete(0, "end")
        self.entry_senha_nova.delete(0, "end")

    def ao_exibir(self):
        self.label_pasta_atual.configure(text=self.config_dao.obter_pasta_relatorios())

    # -------------------------------------------------- atualizações --
    def _verificar_atualizacoes(self):
        """Dispara a checagem em uma thread separada (requisição de rede
        é bloqueante) e usa `.after(0, ...)` para aplicar o resultado na
        UI de volta na thread principal do Tkinter, evitando travar a
        janela enquanto espera a resposta do GitHub."""
        self.btn_verificar_update.configure(state="disabled", text="Verificando...")
        self.label_status_update.configure(text="")

        def worker():
            try:
                resultado = verificar_atualizacao()
                self.after(0, lambda: self._on_check_updates_sucesso(resultado))
            except ErroVerificacaoAtualizacao as exc:
                self.after(0, lambda: self._on_check_updates_erro(str(exc)))
            except Exception as exc:  # rede indisponível, timeout etc.
                self.after(0, lambda: self._on_check_updates_erro(
                    f"Não foi possível verificar atualizações agora ({exc})."
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_updates_sucesso(self, resultado: dict):
        self.btn_verificar_update.configure(state="normal", text="Verificar Atualizações")
        if resultado["atualizado"]:
            self.label_status_update.configure(
                text=f"✅ Você já está na versão mais recente ({resultado['versao_instalada']}).",
                text_color=Marca.SUCESSO_TEXTO,
            )
            mostrar_alerta(
                self.winfo_toplevel(), "Sistema Atualizado",
                f"Você já está usando a versão mais recente ({resultado['versao_instalada']}).",
                "sucesso",
            )
        else:
            self.label_status_update.configure(
                text=f"⬆️ Nova versão disponível: {resultado['versao_remota']}",
                text_color=Marca.ACCENT,
            )
            mensagem = (
                f"Uma nova versão está disponível: {resultado['versao_remota']}\n"
                f"(você está usando a {resultado['versao_instalada']}).\n\n"
            )
            if resultado.get("url"):
                mensagem += f"Baixe em:\n{resultado['url']}"
            mostrar_alerta(self.winfo_toplevel(), "Nova Versão Disponível", mensagem, "aviso")

    def _on_check_updates_erro(self, mensagem_erro: str):
        self.btn_verificar_update.configure(state="normal", text="Verificar Atualizações")
        self.label_status_update.configure(text="⚠️ Falha ao verificar.", text_color=Marca.ERRO)
        mostrar_alerta(self.winfo_toplevel(), "Não foi possível verificar", mensagem_erro, "erro")
