"""
Painel do Desenvolvedor (exclusivo da conta Master na nuvem): lista todas as
contas cadastradas no Supabase com status/HWID/PC e permite Aprovar,
Bloquear, Resetar o HWID (autoriza a troca de computador do cliente) e
Excluir a conta.

Permissões: quem decide é o banco (RLS + RPC excluir_usuario), não esta
tela. Se uma conta que não for master chegar a abrir o painel, qualquer ação
volta como "Sem permissão". Contas master (e a própria conta logada) nunca
mostram botões de ação, para ninguém se bloquear ou excluir sem querer.
"""
import logging
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from config import Marca
from models.usuario_dao import (
    UsuarioDAO, STATUS_PENDENTE, STATUS_APROVADO, STATUS_BLOQUEADO, PAPEL_MASTER,
)
from services import session
from ui.components import mostrar_alerta, confirmar_exclusao

_log = logging.getLogger(__name__)

_CORES_STATUS = {
    STATUS_PENDENTE: ("#92400E", "#FEF3C7"),   # laranja
    STATUS_APROVADO: (Marca.SUCESSO_TEXTO, Marca.SUCESSO_BG),
    STATUS_BLOQUEADO: (Marca.ERRO_TEXTO, Marca.ERRO_BG),
}
_ROTULOS_STATUS = {
    STATUS_PENDENTE: "PENDENTE", STATUS_APROVADO: "APROVADO", STATUS_BLOQUEADO: "BLOQUEADO",
}
# Pendentes primeiro (são os que precisam de ação), depois aprovados e bloqueados.
_ORDEM_STATUS = {STATUS_PENDENTE: 0, STATUS_APROVADO: 1, STATUS_BLOQUEADO: 2}


def _formatar_data(valor) -> str:
    """ISO 8601 do Supabase (UTC) -> dd/mm/aaaa HH:MM no horário local."""
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "—"


def _resumo_erro(exc: Exception) -> str:
    texto = str(exc) or exc.__class__.__name__
    return texto if len(texto) <= 200 else texto[:200] + "…"


class DevPanelView(ctk.CTkFrame):
    def __init__(self, master, usuario_logado: str = None):
        super().__init__(master, fg_color="transparent")
        self.dao = UsuarioDAO()
        # Mantido só por compatibilidade com quem instancia o painel; a conta
        # logada é lida da sessão (services/session.py), pelo UUID.
        self.usuario_logado = usuario_logado

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_cabecalho()
        self._construir_lista()

    # ----------------------------------------------------------- helpers --
    @staticmethod
    def _id_logado():
        sessao = session.sessao_atual()
        return sessao.user_id if sessao else None

    def _executar(self, acao) -> bool:
        """Roda uma ação de rede tratando falhas. True se deu certo."""
        try:
            acao()
        except PermissionError as exc:
            messagebox.showwarning("Sem permissão", str(exc))
            return False
        except Exception as exc:                      # noqa: BLE001
            _log.exception("Falha em ação do Painel do Desenvolvedor")
            messagebox.showerror(
                "Erro", f"Não foi possível concluir a ação.\n\n{_resumo_erro(exc)}"
            )
            return False
        return True

    # ------------------------------------------------------------- layout --
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
            cabecalho,
            text="Contas cadastradas na nuvem, com acesso vinculado por HWID a este sistema.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.label_resumo = ctk.CTkLabel(
            cabecalho, text="", text_color=Marca.TEXTO_SECUNDARIO,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.label_resumo.grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _construir_lista(self):
        self.lista_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista_scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.lista_scroll.grid_columnconfigure(0, weight=1)
        self._carregar_lista()

    def _carregar_lista(self):
        for w in self.lista_scroll.winfo_children():
            w.destroy()

        try:
            usuarios = self.dao.listar_todos()
        except Exception as exc:                      # noqa: BLE001
            _log.exception("Falha ao listar contas")
            self.label_resumo.configure(text="")
            ctk.CTkLabel(
                self.lista_scroll,
                text=f"Não foi possível carregar as contas.\n{_resumo_erro(exc)}",
                text_color=Marca.ERRO, justify="center",
            ).pack(pady=20)
            return

        if not usuarios:
            self.label_resumo.configure(text="")
            ctk.CTkLabel(self.lista_scroll, text="Nenhuma conta cadastrada ainda.",
                         text_color="gray").pack(pady=20)
            return

        # Mais recentes primeiro; depois (ordenação estável) pendentes no topo.
        usuarios.sort(key=lambda u: u.get("criado_em") or "", reverse=True)
        usuarios.sort(key=lambda u: _ORDEM_STATUS.get(u.get("status"), 9))

        pendentes = sum(1 for u in usuarios if u.get("status") == STATUS_PENDENTE)
        self.label_resumo.configure(
            text=f"{pendentes} pendente(s) de aprovação   •   {len(usuarios)} conta(s) no total"
        )

        for u in usuarios:
            self._linha_usuario(u)

    def _linha_usuario(self, u):
        eh_master = u.get("papel") == PAPEL_MASTER
        eh_eu = u["id"] == self._id_logado()
        email = u.get("email") or "—"
        nome = u.get("nome") or email

        card = ctk.CTkFrame(self.lista_scroll, corner_radius=10)
        card.pack(fill="x", pady=5, padx=4)
        card.grid_columnconfigure(0, weight=1)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=0, sticky="w", padx=14, pady=10)

        linha_topo = ctk.CTkFrame(info, fg_color="transparent")
        linha_topo.pack(anchor="w")
        ctk.CTkLabel(linha_topo, text=nome, font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(side="left")
        cor_txt, cor_bg = _CORES_STATUS.get(u["status"], (Marca.TEXTO_SECUNDARIO, Marca.CINZA_TECNICO))
        ctk.CTkLabel(
            linha_topo, text=_ROTULOS_STATUS.get(u["status"], u["status"]),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=cor_txt, fg_color=cor_bg,
            corner_radius=6, padx=8, pady=2,
        ).pack(side="left", padx=(10, 0))
        if eh_master:
            ctk.CTkLabel(
                linha_topo, text="MASTER", font=ctk.CTkFont(size=10, weight="bold"),
                text_color="white", fg_color=Marca.PRIMARIA, corner_radius=6, padx=8, pady=2,
            ).pack(side="left", padx=(6, 0))
        if eh_eu:
            ctk.CTkLabel(
                linha_topo, text="VOCÊ", font=ctk.CTkFont(size=10, weight="bold"),
                text_color=Marca.ACCENT, fg_color=Marca.CINZA_TECNICO, corner_radius=6,
                padx=8, pady=2,
            ).pack(side="left", padx=(6, 0))

        login = u.get("usuario")
        prefixo = f"Usuário: {login}   •   " if login and login != email else ""
        ctk.CTkLabel(
            info, text=f"{prefixo}{email}   •   Cadastro: {_formatar_data(u.get('criado_em'))}",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(
            info, text=f"PC: {u.get('nome_pc') or '—'}   •   Usuário Windows: {u.get('win_user') or '—'}",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w")
        ctk.CTkLabel(
            info, text=f"HWID: {u.get('hwid_vinculado') or 'ainda não vinculado'}",
            text_color="gray", font=ctk.CTkFont(size=10),
        ).pack(anchor="w")

        # Contas master e a conta logada ficam protegidas: sem botões de ação.
        if eh_master or eh_eu:
            return

        acoes = ctk.CTkFrame(card, fg_color="transparent")
        acoes.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        uid = u["id"]
        if u["status"] != STATUS_APROVADO:
            ctk.CTkButton(
                acoes, text="Aprovar Acesso", width=110, height=28,
                fg_color=Marca.SUCESSO_TEXTO, hover_color="#14532D",
                command=lambda: self._mudar_status(uid, STATUS_APROVADO),
            ).pack(side="left", padx=3)
        if u["status"] != STATUS_BLOQUEADO:
            ctk.CTkButton(
                acoes, text="Bloquear", width=90, height=28,
                fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                command=lambda: self._mudar_status(uid, STATUS_BLOQUEADO),
            ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="Resetar HWID", width=110, height=28, fg_color="gray40",
            command=lambda: confirmar_exclusao(
                self.winfo_toplevel(),
                f"vínculo de HWID de '{nome}' (o próximo PC que logar será autorizado)",
                lambda: self._resetar_hwid(uid),
            ),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            acoes, text="Excluir", width=80, height=28,
            fg_color="#7F1D1D", hover_color="#450A0A",
            command=lambda: self._excluir_usuario(uid, nome),
        ).pack(side="left", padx=3)

    # ------------------------------------------------------------- ações --
    def _excluir_usuario(self, usuario_id, nome):
        if usuario_id == self._id_logado():
            messagebox.showwarning("Ação bloqueada",
                                   "Você não pode excluir a conta atualmente logada.")
            return
        if not messagebox.askyesno(
            "Confirmar exclusão",
            f"Tem certeza que deseja excluir a conta de {nome}?\n\n"
            "A conta será removida da nuvem e o acesso deixa de existir.",
        ):
            return
        if self._executar(lambda: self.dao.deletar(usuario_id)):
            self._carregar_lista()

    def _mudar_status(self, usuario_id, novo_status):
        if self._executar(lambda: self.dao.atualizar_status(usuario_id, novo_status)):
            self._carregar_lista()

    def _resetar_hwid(self, usuario_id):
        if not self._executar(lambda: self.dao.resetar_hwid(usuario_id)):
            return
        mostrar_alerta(
            self.winfo_toplevel(), "HWID resetado",
            "O vínculo de hardware foi removido. O próximo computador que fizer "
            "login com esta conta será autorizado automaticamente.", "sucesso",
        )
        self._carregar_lista()

    def ao_exibir(self):
        self._carregar_lista()
