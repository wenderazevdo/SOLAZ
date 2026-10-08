"""Módulo 5: Configurações — pasta padrão de relatórios, aparência, senha
e verificação de atualizações via GitHub Releases."""
import threading
import time

import customtkinter as ctk
from tkinter import filedialog, messagebox

from config import Marca, APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME
from models.usuario_dao import UsuarioDAO
from models.configuracao_dao import ConfiguracaoDAO
from utils import auto_updater
from utils.async_ui import rodar_em_segundo_plano
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

        # Atualização automática: ficam ocultos até serem necessários (na mesma
        # linha, para a tela não crescer).
        self._info_update = None
        self._baixando = False
        self._cancelar_evt = threading.Event()
        self.btn_atualizar_agora = ctk.CTkButton(
            linha_update, text="⬇  Baixar e Atualizar Agora", fg_color=Marca.SUCESSO_TEXTO,
            hover_color=Marca.SUCESSO_TEXTO, font=ctk.CTkFont(weight="bold"),
            command=self._baixar_e_atualizar,
        )
        self.barra_download = ctk.CTkProgressBar(linha_update, width=220)
        self.barra_download.set(0)
        self.label_progresso = ctk.CTkLabel(
            linha_update, text="", text_color="gray", font=ctk.CTkFont(size=11), width=150,
            anchor="w",
        )
        self.btn_cancelar_download = ctk.CTkButton(
            linha_update, text="Cancelar", width=80, fg_color=Marca.ERRO,
            hover_color=getattr(Marca, "ERRO_HOVER", "#B91C1C"),
            command=self._cancelar_download,
        )

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
        # Leitura no banco fora da thread da interface: a tela abre na hora e o
        # texto da pasta é atualizado assim que a consulta termina.
        rodar_em_segundo_plano(
            self, self.config_dao.obter_pasta_relatorios,
            lambda pasta: self.label_pasta_atual.configure(text=pasta),
        )

    # -------------------------------------------------- atualizações --
    def _ui(self, fn):
        """Agenda `fn` na thread da interface (seguro mesmo se a tela já fechou)."""
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _verificar_atualizacoes(self):
        """Consulta o GitHub em thread separada (rede é bloqueante) e devolve o
        resultado à thread do Tkinter com `after`, sem travar a janela."""
        self.btn_verificar_update.configure(state="disabled", text="Verificando...")
        self.label_status_update.configure(text="")
        self.btn_atualizar_agora.pack_forget()
        self._info_update = None

        def worker():
            try:
                info = auto_updater.verificar()
            except auto_updater.ErroAtualizacao as exc:
                msg = str(exc)
                self._ui(lambda: self._on_check_updates_erro(msg))
            except Exception as exc:  # rede indisponível, timeout etc.
                msg = f"Não foi possível verificar atualizações agora ({exc})."
                self._ui(lambda: self._on_check_updates_erro(msg))
            else:
                self._ui(lambda: self._on_check_updates_sucesso(info))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_updates_sucesso(self, info):
        self.btn_verificar_update.configure(state="normal", text="Verificar Atualizações")
        if not info.tem_nova:
            self.label_status_update.configure(
                text=f"✅ Você já está na versão mais recente ({info.versao_instalada}).",
                text_color=Marca.SUCESSO_TEXTO,
            )
            mostrar_alerta(
                self.winfo_toplevel(), "Sistema Atualizado",
                f"Você já está usando a versão mais recente ({info.versao_instalada}).",
                "sucesso",
            )
            return

        self._info_update = info
        self.label_status_update.configure(
            text=f"⬆️ Nova versão disponível: {info.versao_remota}", text_color=Marca.ACCENT,
        )
        if info.asset_url and auto_updater.atualizacao_automatica_disponivel():
            self.btn_atualizar_agora.pack(side="left", padx=(12, 0),
                                          before=self.label_status_update)
            return
        # Sem arquivo na release, ou rodando do código-fonte: só informa o link.
        mensagem = (
            f"Uma nova versão está disponível: {info.versao_remota}\n"
            f"(você está usando a {info.versao_instalada}).\n\n"
        )
        if info.url_pagina:
            mensagem += f"Baixe em:\n{info.url_pagina}"
        mostrar_alerta(self.winfo_toplevel(), "Nova Versão Disponível", mensagem, "aviso")

    def _on_check_updates_erro(self, mensagem_erro: str):
        self.btn_verificar_update.configure(state="normal", text="Verificar Atualizações")
        self.label_status_update.configure(text="⚠️ Falha ao verificar.", text_color=Marca.ERRO)
        mostrar_alerta(self.winfo_toplevel(), "Não foi possível verificar", mensagem_erro, "erro")

    # ----------------------------------------------- baixar e atualizar --
    def _modo_progresso(self, ativo: bool):
        """Troca os controles da linha: [barra + % + Cancelar] <-> [botões normais]."""
        if ativo:
            self.btn_verificar_update.pack_forget()
            self.label_status_update.pack_forget()
            self.btn_atualizar_agora.pack_forget()
            self.barra_download.set(0)
            self.label_progresso.configure(text="Iniciando...")
            self.barra_download.pack(side="left")
            self.label_progresso.pack(side="left", padx=(10, 0))
            self.btn_cancelar_download.configure(state="normal")
            self.btn_cancelar_download.pack(side="left", padx=(10, 0))
        else:
            for w in (self.barra_download, self.label_progresso, self.btn_cancelar_download):
                w.pack_forget()
            self.btn_verificar_update.pack(side="left")
            self.label_status_update.pack(side="left", padx=(12, 0))

    def _baixar_e_atualizar(self):
        info = self._info_update
        if not info or self._baixando:
            return
        if not messagebox.askyesno(
            "Atualizar agora",
            f"Baixar a versão {info.versao_remota} e atualizar agora?\n\n"
            "O programa será fechado e reaberto automaticamente.\n"
            "Seus dados (clientes, empresas, relatórios e configurações) "
            "não serão alterados.",
            parent=self.winfo_toplevel(),
        ):
            return

        self._baixando = True
        self._cancelar_evt.clear()
        self._modo_progresso(True)

        def worker():
            try:
                auto_updater.fazer_backup_antes()
                ultimo = [0.0]

                def progresso(feito, total):
                    agora = time.monotonic()
                    if feito != total and agora - ultimo[0] < 0.1:
                        return              # limita a ~10 atualizações/s
                    ultimo[0] = agora
                    self._ui(lambda: self._on_progresso(feito, total))

                caminho = auto_updater.baixar(info, progresso=progresso,
                                              cancelar=self._cancelar_evt)
            except auto_updater.DownloadCancelado:
                self._ui(self._on_download_cancelado)
            except auto_updater.ErroAtualizacao as exc:
                msg = str(exc)
                self._ui(lambda: self._on_download_erro(msg))
            except Exception as exc:
                msg = f"Falha inesperada no download ({exc})."
                self._ui(lambda: self._on_download_erro(msg))
            else:
                self._ui(lambda: self._on_download_ok(caminho))

        threading.Thread(target=worker, daemon=True).start()

    def _cancelar_download(self):
        self._cancelar_evt.set()
        self.btn_cancelar_download.configure(state="disabled")
        self.label_progresso.configure(text="Cancelando...")

    def _on_progresso(self, feito: int, total: int):
        if not self._baixando:
            return
        mb = feito / (1024 * 1024)
        if total:
            self.barra_download.set(min(feito / total, 1.0))
            self.label_progresso.configure(
                text=f"{feito * 100 // total}%  ({mb:.1f} / {total / (1024 * 1024):.1f} MB)")
        else:
            self.label_progresso.configure(text=f"{mb:.1f} MB")

    def _fim_download(self):
        self._baixando = False
        self._modo_progresso(False)

    def _on_download_cancelado(self):
        self._fim_download()
        self.label_status_update.configure(text="Download cancelado.", text_color="gray")
        if self._info_update:
            self.btn_atualizar_agora.pack(side="left", padx=(12, 0),
                                          before=self.label_status_update)

    def _on_download_erro(self, mensagem: str):
        self._fim_download()
        self.label_status_update.configure(text="⚠️ Falha ao baixar.", text_color=Marca.ERRO)
        if self._info_update:
            self.btn_atualizar_agora.pack(side="left", padx=(12, 0),
                                          before=self.label_status_update)
        mostrar_alerta(self.winfo_toplevel(), "Não foi possível atualizar", mensagem, "erro")

    def _on_download_ok(self, caminho: str):
        self.label_progresso.configure(text="Aplicando atualização...")
        self.barra_download.set(1)
        try:
            aplicado = auto_updater.aplicar(caminho, self._info_update)
        except Exception as exc:
            self._on_download_erro(f"Não foi possível iniciar a atualização ({exc}).")
            return
        if not aplicado:
            # Modo teste (rodando do código-fonte): baixou e validou, não aplica.
            self._fim_download()
            mostrar_alerta(
                self.winfo_toplevel(), "Download concluído (modo teste)",
                f"Arquivo baixado e verificado em:\n{caminho}\n\n"
                "A atualização só é aplicada quando o programa roda como .exe.", "sucesso",
            )
            return
        # O .bat auxiliar já está esperando: fecha o programa para ele trocar o .exe.
        self.winfo_toplevel().fechar_aplicacao()
