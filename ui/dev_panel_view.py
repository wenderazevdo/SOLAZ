"""
Módulo exclusivo da conta Master (dev_master): lista todas as contas
cadastradas com HWID/PC/status, e permite Aprovar, Bloquear ou Resetar o
HWID (autoriza a troca de computador do cliente).
"""
from tkinter import messagebox

import customtkinter as ctk

from config import Marca
from models.usuario_dao import UsuarioDAO, STATUS_PENDENTE, STATUS_APROVADO, STATUS_BLOQUEADO
from ui.components import mostrar_alerta, confirmar_exclusao

_CORES_STATUS = {
    STATUS_PENDENTE: ("#92400E", "#FEF3C7"),   # laranja
    STATUS_APROVADO: (Marca.SUCESSO_TEXTO, Marca.SUCESSO_BG),
    STATUS_BLOQUEADO: (Marca.ERRO_TEXTO, Marca.ERRO_BG),
}
_ROTULOS_STATUS = {
    STATUS_PENDENTE: "PENDENTE", STATUS_APROVADO: "APROVADO", STATUS_BLOQUEADO: "BLOQUEADO",
}


# Conta Master / Administrador Principal: nunca pode ser excluída.
ADMIN_PRINCIPAL = "dev_master"


class DevPanelView(ctk.CTkFrame):
    def __init__(self, master, usuario_logado: str = None):
        super().__init__(master, fg_color="transparent")
        self.dao = UsuarioDAO()
        self.usuario_logado = usuario_logado  # nome do usuário da sessão atual

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_cabecalho()
        self._construir_lista()

    def _construir_cabecalho(self):
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        cabecalho.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cabecalho, text="🛠️ Painel do Desenvolvedor",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=Marca.PRIMARIA,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(cabecalho, text="Atualizar", width=100,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=self._carregar_lista).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            cabecalho, text="Contas com acesso vinculado por HWID a este sistema.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _construir_lista(self):
        self.lista_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista_scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.lista_scroll.grid_columnconfigure(0, weight=1)
        self._carregar_lista()

    def _carregar_lista(self):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        usuarios = self.dao.listar_todos()
        if not usuarios:
            ctk.CTkLabel(self.lista_scroll, text="Nenhuma conta cadastrada ainda.",
                         text_color="gray").pack(pady=20)
            return

        for u in usuarios:
            self._linha_usuario(u)

    def _linha_usuario(self, u):
        card = ctk.CTkFrame(self.lista_scroll, corner_radius=10)
        card.pack(fill="x", pady=5, padx=4)
        card.grid_columnconfigure(0, weight=1)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=14, pady=10)

        linha_topo = ctk.CTkFrame(info, fg_color="transparent")
        linha_topo.pack(anchor="w")
        ctk.CTkLabel(linha_topo, text=u["usuario"], font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(side="left")
        cor_txt, cor_bg = _CORES_STATUS.get(u["status"], (Marca.TEXTO_SECUNDARIO, Marca.CINZA_TECNICO))
        ctk.CTkLabel(
            linha_topo, text=_ROTULOS_STATUS.get(u["status"], u["status"]),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=cor_txt, fg_color=cor_bg,
            corner_radius=6, padx=8, pady=2,
        ).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            info, text=f"PC: {u.get('nome_pc') or '—'}   •   Usuário Windows: {u.get('win_user') or '—'}",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(
            info, text=f"HWID: {u.get('hwid_vinculado') or 'ainda não vinculado'}",
            text_color="gray", font=ctk.CTkFont(size=10),
        ).pack(anchor="w")

        acoes = ctk.CTkFrame(card, fg_color="transparent")
        acoes.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        if u["status"] != STATUS_APROVADO:
            ctk.CTkButton(
                acoes, text="Aprovar Acesso", width=110, height=28,
                fg_color=Marca.SUCESSO_TEXTO, hover_color="#14532D",
                command=lambda uid=u["id"]: self._mudar_status(uid, STATUS_APROVADO),
            ).pack(side="left", padx=3)
        if u["status"] != STATUS_BLOQUEADO:
            ctk.CTkButton(
                acoes, text="Bloquear", width=90, height=28,
                fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                command=lambda uid=u["id"]: self._mudar_status(uid, STATUS_BLOQUEADO),
            ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="Resetar HWID", width=110, height=28, fg_color="gray40",
            command=lambda uid=u["id"], nome=u["usuario"]: confirmar_exclusao(
                self.winfo_toplevel(),
                f"vínculo de HWID de '{nome}' (o próximo PC que logar será autorizado)",
                lambda: self._resetar_hwid(uid),
            ),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="Excluir", width=80, height=28,
            fg_color="#7F1D1D", hover_color="#450A0A",
            command=lambda uid=u["id"], nome=u["usuario"]: self._excluir_usuario(uid, nome),
        ).pack(side="left", padx=3)

    def _excluir_usuario(self, usuario_id, nome):
        if nome == ADMIN_PRINCIPAL:
            messagebox.showwarning("Ação bloqueada",
                                   "O Administrador Principal não pode ser excluído.")
            return
        if nome == self.usuario_logado:
            messagebox.showwarning("Ação bloqueada",
                                   "Você não pode excluir o usuário atualmente logado.")
            return
        if not messagebox.askyesno("Confirmar exclusão",
                                   f"Tem certeza que deseja excluir o usuário {nome}?"):
            return
        self.dao.deletar(usuario_id)
        self._carregar_lista()

    def _mudar_status(self, usuario_id, novo_status):
        self.dao.atualizar_status(usuario_id, novo_status)
        self._carregar_lista()

    def _resetar_hwid(self, usuario_id):
        self.dao.resetar_hwid(usuario_id)
        mostrar_alerta(
            self.winfo_toplevel(), "HWID resetado",
            "O vínculo de hardware foi removido. O próximo computador que fizer "
            "login com esta conta será autorizado automaticamente.", "sucesso",
        )
        self._carregar_lista()

    def ao_exibir(self):
        self._carregar_lista()
