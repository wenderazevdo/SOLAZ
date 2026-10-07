"""
Módulo 3: Construtor de Relatório Modular — Cards Visuais.

Cada seção do relatório é um card com Switch (ativo/inativo) e setas ▲▼
para reordenação. Inclui o construtor de Strings/medições elétricas com
seletor visual Conforme/Não Conforme (pílulas coloridas), o bloco opcional
do Circuito CA, busca rápida (lupa) de Empresa/Cliente e filtragem
dinâmica de clientes por empresa selecionada.
"""
import functools
import math
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime

import customtkinter as ctk
from tkcalendar import DateEntry
import tkinter as tk
from tkinter import filedialog

from config import (
    TEXTO_OBJETIVO_PADRAO, TEXTO_APLICACAO_PADRAO,
    TEXTO_NORMAS_PADRAO, Marca,
    PASTA_RELATORIOS_CLIENTE, SUBPASTA_RELATORIO_LIMPEZA,
    SUBPASTA_RELATORIO_TROCA,
)
from models.empresa_dao import EmpresaDAO
from models.cliente_dao import ClienteDAO
from models.relatorio_dao import RelatorioDAO
from models.configuracao_dao import (
    ConfiguracaoDAO, CHAVE_ORDEM_SECOES_LIMPEZA, CHAVE_ORDEM_SECOES_TROCA,
)
from utils.image_utils import criar_pasta_temporaria, salvar_foto_temporaria, limpar_pasta_temporaria
from pdf.report_generator import (
    gerar_relatorio_pdf, gerar_relatorio_troca_pdf, NOMES_SECOES,
)
from ui.components import mostrar_alerta, criar_seletor_hora_minuto, abrir_busca_modal
from utils.retry import executar_com_retry

_SECOES_FOTO = [
    "modulos_sujos", "modulos_limpos", "reaperto_parafusos",
    "teste_tensao_cc", "teste_tensao_ca", "geracao_energia",
    "sugestoes_melhorias",
]
_SECAO_TABELA = "tabela_conformidade"
_SECAO_OCORRENCIAS = "ocorrencias_extras"   # várias ocorrências, cada uma com título, texto e fotos

_TITULOS_TOPO_FOTO = {
    "modulos_sujos": ("ANTERIOR À LIMPEZA (Módulos Sujos)", "#C2410C"),
    "modulos_limpos": ("POSTERIOR À LIMPEZA (Módulos Limpos)", "#15803D"),
}

# O número é só um marcador ("Figura X:"): _reindexar_figuras() troca pelo
# número sequencial real de acordo com a posição da foto no relatório.
_LEGENDAS_PADRAO_FOTO = {
    "modulos_sujos": "Figura X: Presença de poeira espessa e resíduos orgânicos.",
    "modulos_limpos": "Figura X: Superfície de captação limpa e desobstruída.",
    "reaperto_parafusos": "Figura X: Reaperto de parafusos e bornes no circuito CA.",
    "teste_tensao_cc": "Figura X: Medição e teste de tensão de circuito aberto (CC).",
    "teste_tensao_ca": "Figura X: Medição e teste de tensão de circuito de corrente alternada (CA).",
}

# Seções cujas fotos entram na numeração única "Figura 1, 2, 3..." (os
# gráficos de geração e as sugestões têm legenda própria, sem número).
_SECOES_NUMERADAS = {
    "modulos_sujos", "modulos_limpos", "reaperto_parafusos",
    "teste_tensao_cc", "teste_tensao_ca",
}
_RE_PREFIXO_FIGURA = re.compile(r"^\s*Figura\s+(?:\d+|X)\s*:\s*", re.IGNORECASE)

_VOLTAGENS_DISJUNTOR = ["127V", "220V", "380V", "Outra"]
_TIPOS_DISJUNTOR = ["Bifásico", "Trifásico"]

_STATUS_ROTULOS = {
    "tensao": "Tensão de Operação",
    "flut_pos": "Teste Flutuação (+) / Terra",
    "flut_neg": "Teste Flutuação (−) / Terra",
    "neutro": "Teste de Neutro",
}


class _ScrollSuave(ctk.CTkScrollableFrame):
    """CTkScrollableFrame com rolagem do mouse suave.

    O padrão do customtkinter rola ~20 'units' (centenas de px) por clique
    da roda e redesenha a cada evento — daí os "pulinhos". Aqui:
      * o canvas passa a rolar em PIXELS (yscrollincrement=1);
      * a roda é acumulada e aplicada em passos pequenos com easing, a
        cada ~10 ms, em vez de um redesenho por evento <MouseWheel>;
      * o handler original (`_mouse_wheel_all`) é neutralizado.
    """
    PIXELS_POR_CLIQUE = 55      # distância por "clique" da roda (Windows: delta 120)
    INTERVALO_MS = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pendente = 0.0
        self._animando = False
        self.contador_roda = 0   # sobe a cada gesto do usuário (cancela restaurações de scroll)
        self._parent_canvas.configure(yscrollincrement=1)
        self.bind_all("<MouseWheel>", self._ao_girar_roda, add="+")
        if sys.platform.startswith("linux"):
            self.bind_all("<Button-4>", lambda e: self._ao_girar_roda(e, +120), add="+")
            self.bind_all("<Button-5>", lambda e: self._ao_girar_roda(e, -120), add="+")

    def _mouse_wheel_all(self, event):      # neutraliza o handler original
        return

    def _evento_e_meu(self, event):
        w = event.widget
        if isinstance(w, str):
            try:
                w = self.nametowidget(w)
            except Exception:
                return False
        while w is not None:
            if w is self or w is self._parent_canvas:
                return True
            w = getattr(w, "master", None)
        return False

    def _ao_girar_roda(self, event, delta=None):
        if not self._evento_e_meu(event):
            return
        if self._parent_canvas.yview() == (0.0, 1.0):   # conteúdo cabe: nada a rolar
            return
        delta = event.delta if delta is None else delta
        if sys.platform == "darwin":
            px = -delta * 4
        else:
            px = -(delta / 120.0) * self.PIXELS_POR_CLIQUE
        self.contador_roda += 1
        self._pendente += px
        if not self._animando:
            self._animando = True
            self.after(self.INTERVALO_MS, self._passo)

    def _passo(self):
        pend = self._pendente
        if abs(pend) < 1:
            self._pendente, self._animando = 0.0, False
            return
        inteiro = int(pend * 0.35) or (1 if pend > 0 else -1)
        self._pendente -= inteiro
        topo, base = self._parent_canvas.yview()
        if (inteiro < 0 and topo <= 0.0) or (inteiro > 0 and base >= 1.0):
            self._pendente, self._animando = 0.0, False   # chegou na borda
            return
        self._parent_canvas.yview_scroll(inteiro, "units")
        self.after(self.INTERVALO_MS, self._passo)


# ====================================================================
#  TRANSIÇÃO SUAVE (fade-in curto) — elimina o "corte" ao trocar de tela
# ====================================================================
# Fade-in da JANELA (Tk só tem opacidade por janela, não por frame):
# a opacidade cai para _FADE_ALPHA_INICIAL enquanto a tela é montada em
# memória e sobe até 1.0 em _FADE_DURACAO_MS, em _FADE_PASSOS etapas.
_FADE_DURACAO_MS = 120      # total (faixa pedida: 100–150 ms)
_FADE_PASSOS = 6            # ~20 ms por etapa
_FADE_ALPHA_INICIAL = 0.80  # discreto: só tira o corte brusco

# Cortina: cobre a lista de seções (cor lisa do fundo) enquanto os cards são
# refeitos, para ninguém ver o meio-caminho (cards cortados, áreas sem pintar).
_CORTINA_MS = 50            # tempo mínimo coberto (cobre o restaurar da rolagem, ~40 ms)
_CORTINA_COM_FADE = False   # True = ao descobrir, também faz o fade-in da janela


def _alpha_suportado(janela):
    """False em sistemas/gerenciadores sem suporte a '-alpha' (sem fade)."""
    try:
        janela.attributes("-alpha")
        return True
    except Exception:
        return False


def _cancelar_fade(janela):
    job = getattr(janela, "_rv_fade_job", None)
    if job:
        try:
            janela.after_cancel(job)
        except Exception:
            pass
        janela._rv_fade_job = None


def _fade_in(janela):
    intervalo = max(1, _FADE_DURACAO_MS // _FADE_PASSOS)

    def etapa(i):
        janela._rv_fade_job = None
        try:
            t = i / _FADE_PASSOS
            alpha = _FADE_ALPHA_INICIAL + (1 - _FADE_ALPHA_INICIAL) * (1 - (1 - t) ** 2)
            janela.attributes("-alpha", 1.0 if i >= _FADE_PASSOS else alpha)
            if i < _FADE_PASSOS:
                janela._rv_fade_job = janela.after(intervalo, etapa, i + 1)
        except Exception:        # janela fechada no meio do fade
            pass

    etapa(1)


def fade_in_janela(janela):
    """Baixa a opacidade da janela e sobe até 1.0 em ~120 ms (no-op se o
    sistema não suportar '-alpha')."""
    if not _alpha_suportado(janela):
        return
    try:
        _cancelar_fade(janela)
        janela.attributes("-alpha", _FADE_ALPHA_INICIAL)
        _fade_in(janela)
    except Exception:
        pass


@contextmanager
def transicao_suave(widget, fade=True):
    """Envolva a troca de tela/aba (fade=False: só agrupa e calcula o layout,
    sem mexer na opacidade — quem chama dispara `fade_in_janela` depois):

        with transicao_suave(self):
            ... destrói/cria widgets ...

    Ao entrar, baixa a opacidade; ao sair, calcula o layout final em memória
    (update_idletasks) e só então roda o fade-in de ~120 ms. Chamadas
    aninhadas viram uma só (o fade ocorre apenas no bloco mais externo) e a
    opacidade volta a 1.0 mesmo se ocorrer erro dentro do bloco."""
    try:
        janela = widget.winfo_toplevel()
    except Exception:
        yield
        return
    nivel = getattr(janela, "_rv_transicao_nivel", 0)
    janela._rv_transicao_nivel = nivel + 1
    com_fade = fade and nivel == 0 and _alpha_suportado(janela)
    if com_fade:
        _cancelar_fade(janela)
        try:
            janela.attributes("-alpha", _FADE_ALPHA_INICIAL)
        except Exception:
            com_fade = False
    try:
        yield
    finally:
        janela._rv_transicao_nivel = nivel
        if nivel == 0:
            try:
                janela.update_idletasks()   # dimensões/grid/pack prontos antes de exibir
            except Exception:
                pass
            if com_fade:
                _fade_in(janela)


def _mantem_scroll(metodo):
    """Decorador: executa o método e devolve a rolagem EXATAMENTE para onde
    estava (em pixels) — evita a tela "pular" quando o conteúdo é refeito."""
    @functools.wraps(metodo)
    def interno(self, *args, **kwargs):
        return self._com_scroll_preservado(metodo, self, *args, **kwargs)
    return interno


# ====================================================================
#  RELATÓRIO DE TROCA DE MICROINVERSOR — seções modulares
# ====================================================================
_TIPO_LIMPEZA = "Relatório de Limpeza e Reaperto"
_TIPO_TROCA = "Relatório de Troca de Microinversor"
_TIPOS_RELATORIO = [_TIPO_LIMPEZA, _TIPO_TROCA]

# Seções do relatório de troca (mesmo formato modular da limpeza: card com
# switch On/Off e setas ▲▼).
_SECOES_TROCA = [
    "troca_etiquetas", "troca_modulos", "troca_cabo_tronco",
    "troca_sugestoes", "troca_ocorrencia",
]
_NOMES_SECOES_TROCA = {
    "troca_etiquetas": "Etiquetas e Equipamentos (Micro Antigo e Novo)",
    "troca_modulos": "Testes dos Módulos (Voc / Isc)",
    "troca_cabo_tronco": "Medições no Cabo Tronco (Fase-Fase e Fase-Terra)",
    "troca_sugestoes": "Sugestões de Melhoria",
    "troca_ocorrencia": "Ocorrências Extras / Imprevistos (Opcional)",
}


_NOMES_SECOES_LIMPEZA_EXTRA = {
    _SECAO_OCORRENCIAS: "Ocorrências Extras / Imprevistos (Opcional)",
}


def _nome_secao(chave):
    return (_NOMES_SECOES_TROCA.get(chave)
            or _NOMES_SECOES_LIMPEZA_EXTRA.get(chave)
            or NOMES_SECOES[chave])


# Textos padrão (Objetivo / Aplicação / Normas) por tipo de relatório.
TEXTOS_TROCA_PADRAO = (
    "Este relatório tem como objetivo registrar a substituição de microinversor "
    "com avaria por um novo equipamento, apresentando as evidências fotográficas "
    "e os testes elétricos de validação realizados nos módulos fotovoltaicos e no "
    "cabo tronco, garantindo o correto funcionamento e a segurança da instalação.",
    "Procedimento técnico para substituição de microinversor em avaria e validação "
    "operacional do sistema fotovoltaico. Abrange o registro dos números de série dos "
    "equipamentos (antigo e novo), medições elétricas de tensão e corrente contínua (CC) "
    "nos módulos, verificação das tensões de saída em corrente alternada (CA) e a "
    "confirmação do pleno funcionamento do sistema.",
    "Os procedimentos seguem as recomendações da NBR 16690, NBR 5410, NR-10 e as "
    "orientações do fabricante dos equipamentos instalados.",
)
TEXTOS_LIMPEZA_PADRAO = (TEXTO_OBJETIVO_PADRAO, TEXTO_APLICACAO_PADRAO,
                         TEXTO_NORMAS_PADRAO)


def _rotulos_modulos(duplos):
    """Rótulos com numeração contínua: 'Módulo 1', 'Módulo 2 + 3', 'Módulo 4'..."""
    n, rotulos = 1, []
    for duplo in duplos:
        rotulos.append(f"Módulo {n} + {n + 1}" if duplo else f"Módulo {n}")
        n += 2 if duplo else 1
    return rotulos


def _fotos_valores(itens):
    return [{"origem": f["origem"], "legenda": f["legenda_var"].get().strip()}
            for f in itens]


def _fotos_definir(itens, lista):
    """Recarrega fotos salvas NA MESMA lista (só as cujo arquivo ainda existe)."""
    itens[:] = [
        {"origem": f["origem"], "legenda_var": ctk.StringVar(value=f.get("legenda", ""))}
        for f in (lista or []) if f.get("origem") and os.path.exists(f["origem"])
    ]


class _SeletorFotos(ctk.CTkFrame):
    """Título + lista de fotos (legenda opcional) + botão de adicionar.
    `itens` é uma lista EXTERNA (estado do formulário): os cards de seção são
    recriados a cada ▲/▼ ou switch, mas as fotos escolhidas sobrevivem.
    `max_fotos=1` faz uma nova foto substituir a anterior."""

    def __init__(self, master, titulo, itens, cor_titulo=None, max_fotos=None):
        super().__init__(master, fg_color="transparent", height=1)
        self.itens = itens
        self.max_fotos = max_fotos
        ctk.CTkLabel(self, text=titulo, text_color=cor_titulo or Marca.PRIMARIA,
                     font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(anchor="w", pady=(4, 0))
        # height=1: sem fotos o frame colapsa (CTkFrame vazio mede 200px).
        self.lista = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.lista.pack(fill="x")
        ctk.CTkButton(self, text="+ Adicionar Foto", width=140, fg_color=Marca.ACCENT,
                      hover_color=Marca.ACCENT_HOVER, command=self._adicionar
                      ).pack(anchor="w", pady=(2, 4))
        self._render()

    def _adicionar(self):
        tipos = [("Imagens", "*.png *.jpg *.jpeg")]
        if self.max_fotos == 1:
            # Limite de 1 foto: o diálogo aceita só um arquivo e ele substitui o atual.
            escolhida = filedialog.askopenfilename(title="Selecionar foto", filetypes=tipos)
            caminhos = (escolhida,) if escolhida else ()
        else:
            caminhos = filedialog.askopenfilenames(title="Selecionar fotos", filetypes=tipos)
        for c in caminhos:
            novo = {"origem": c, "legenda_var": ctk.StringVar(value="")}
            if self.max_fotos == 1:
                self.itens[:] = [novo]
            else:
                self.itens.append(novo)
        if caminhos:
            self._render()

    def _render(self):
        for w in self.lista.winfo_children():
            w.destroy()
        for idx, foto in enumerate(self.itens):
            linha = ctk.CTkFrame(self.lista, fg_color="transparent")
            linha.pack(fill="x", pady=1)
            ctk.CTkLabel(linha, text=os.path.basename(foto["origem"]), width=180,
                         anchor="w").pack(side="left")
            entry = ctk.CTkEntry(linha, placeholder_text="Legenda (opcional)", width=280)
            entry.insert(0, foto["legenda_var"].get())
            entry.bind("<KeyRelease>",
                       lambda e, v=foto["legenda_var"], en=entry: v.set(en.get()))
            entry.pack(side="left", padx=8)
            ctk.CTkButton(
                linha, text="Remover", width=80, fg_color=Marca.ERRO,
                hover_color=Marca.ERRO_HOVER,
                command=lambda i=idx: (self.itens.pop(i), self._render()),
            ).pack(side="left")


def _criar_seletor_status(parent, status_var):
    """Pílulas Conforme / Não Conforme (mesmo visual do relatório de limpeza)."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(side="left", padx=2)

    def escolher(valor):
        status_var.set(valor)
        atualizar_cores()

    btn_conforme = ctk.CTkButton(
        frame, text="Conforme", width=90, height=26,
        command=lambda: escolher("CONFORME"),
    )
    btn_nao = ctk.CTkButton(
        frame, text="Não Conforme", width=95, height=26,
        command=lambda: escolher("NAO_CONFORME"),
    )
    btn_conforme.pack(side="left", padx=(0, 3))
    btn_nao.pack(side="left")

    def atualizar_cores():
        if status_var.get() == "CONFORME":
            btn_conforme.configure(fg_color=Marca.SUCESSO_TEXTO, text_color="white")
            btn_nao.configure(fg_color="gray75", text_color="gray30")
        else:
            btn_nao.configure(fg_color=Marca.ERRO, text_color="white")
            btn_conforme.configure(fg_color="gray75", text_color="gray30")

    atualizar_cores()


class _BotaoFotoCompacto(ctk.CTkFrame):
    """Botão só com ícone de câmera ao lado de uma medição. Guarda UMA foto
    (caminho numa StringVar externa, que sobrevive à recriação dos cards).
    Com foto anexada o ícone fica verde e aparece um "✕" para removê-la."""

    def __init__(self, master, foto_var):
        super().__init__(master, fg_color="transparent")
        self.foto_var = foto_var
        self.btn = ctk.CTkButton(self, text="📷", width=32, height=26,
                                 font=ctk.CTkFont(size=14), command=self._escolher)
        self.btn.pack(side="left")
        self.btn_x = ctk.CTkButton(self, text="✕", width=24, height=26,
                                   fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                                   command=self._remover)
        self._atualizar()

    def _escolher(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar foto", filetypes=[("Imagens", "*.png *.jpg *.jpeg")])
        if caminho:
            self.foto_var.set(caminho)
            self._atualizar()

    def _remover(self):
        self.foto_var.set("")
        self._atualizar()

    def _atualizar(self):
        if self.foto_var.get():
            self.btn.configure(fg_color=Marca.SUCESSO_TEXTO, hover_color=Marca.SUCESSO_TEXTO)
            self.btn_x.pack(side="left", padx=(2, 0))
        else:
            self.btn.configure(fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER)
            self.btn_x.pack_forget()


# ---- Ocorrências Extras dinâmicas (compartilhado: limpeza e troca) ----------
def _nova_ocorrencia_extra():
    return {"titulo_var": ctk.StringVar(value=""),
            "descricao_var": ctk.StringVar(value=""),
            "fotos": []}


def _coletar_ocorrencias(lista):
    """[{"titulo", "descricao", "fotos": [{"origem", "legenda"}]}]. Ocorrência
    totalmente vazia (sem título, texto nem foto) é ignorada."""
    saida = []
    for oc in lista:
        titulo = oc["titulo_var"].get().strip()
        descricao = oc["descricao_var"].get().strip()
        fotos = _fotos_valores(oc["fotos"])
        if titulo or descricao or fotos:
            saida.append({"titulo": titulo, "descricao": descricao, "fotos": fotos})
    return saida


def _carregar_ocorrencias(destino, salvas):
    """Recarrega ocorrências salvas NA MESMA lista `destino` (só as fotos cujo
    arquivo ainda existe; ocorrência sem nada é descartada)."""
    destino[:] = []
    for sv in salvas or []:
        oc = _nova_ocorrencia_extra()
        oc["titulo_var"].set(sv.get("titulo", ""))
        oc["descricao_var"].set(sv.get("descricao", ""))
        _fotos_definir(oc["fotos"], sv.get("fotos"))
        if sv.get("titulo") or sv.get("descricao") or oc["fotos"]:
            destino.append(oc)


def _reconstruir_simples(pai, criar):
    """Reconstrução padrão de lista dinâmica (sem controle de scroll)."""
    antigos = list(pai.winfo_children())
    novos = criar()
    for w in antigos:
        w.destroy()
    for w, kw in novos:
        w.pack(**kw)


def _construir_lista_ocorrencias(bloco, ocorrencias, preservar_scroll=None,
                                 reconstruir_lista=None, margem=14):
    """Lista dinâmica de ocorrências extras dentro de `bloco`. `ocorrencias` é
    a lista de ESTADO (fora dos cards: sobrevive a ▲/▼, switch e
    re-renderizações). Cada ocorrência tem Título personalizado, Descrição
    (texto multilinha) e QUANTAS fotos o usuário quiser (+ Adicionar Foto /
    Remover). '+ Adicionar Ocorrência Extra' cria uma nova em branco; nada é
    exigido até o usuário preencher. `preservar_scroll` / `reconstruir_lista`
    são os ajudantes de scroll da tela (opcionais)."""
    preservar_scroll = preservar_scroll or (lambda fn: fn)
    reconstruir_lista = reconstruir_lista or _reconstruir_simples

    lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
    lista_frame.pack(fill="x", padx=margem, pady=(0, 6))

    @preservar_scroll
    def atualizar_lista():
        def criar():
            itens = []
            if not ocorrencias:
                vazio = ctk.CTkLabel(
                    lista_frame, text_color="gray", anchor="w",
                    text="Nenhuma ocorrência adicionada. Use o botão abaixo para incluir.")
                itens.append((vazio, dict(anchor="w", pady=2)))
            for idx, oc in enumerate(ocorrencias):
                grupo = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                     border_width=1, border_color=Marca.CINZA_BORDA,
                                     corner_radius=8)
                itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                topo = ctk.CTkFrame(grupo, fg_color="transparent")
                topo.pack(fill="x", padx=10, pady=(8, 2))
                ctk.CTkLabel(topo, text=f"Ocorrência Extra {idx + 1}",
                             text_color=Marca.PRIMARIA,
                             font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
                ctk.CTkButton(
                    topo, text="Remover Ocorrência", width=130, fg_color=Marca.ERRO,
                    hover_color=Marca.ERRO_HOVER,
                    command=lambda i=idx: (ocorrencias.pop(i), atualizar_lista()),
                ).pack(side="right")

                ctk.CTkEntry(
                    grupo, textvariable=oc["titulo_var"],
                    placeholder_text="Título da ocorrência (ex.: Cabo danificado)",
                ).pack(fill="x", padx=10, pady=(4, 4))

                # CTkTextbox não tem variável: grava na StringVar ao digitar/sair.
                caixa = ctk.CTkTextbox(grupo, height=90)
                caixa.insert("1.0", oc["descricao_var"].get())
                sincronizar = (lambda _e=None, v=oc["descricao_var"], c=caixa:
                               v.set(c.get("1.0", "end-1c")))
                for evento in ("<KeyRelease>", "<FocusOut>"):
                    caixa.bind(evento, sincronizar)
                caixa.pack(fill="x", padx=10, pady=(0, 4))

                _SeletorFotos(grupo, "Fotos da Ocorrência", oc["fotos"]
                              ).pack(fill="x", padx=10, pady=(0, 6))
            return itens
        reconstruir_lista(lista_frame, criar)

    def adicionar_ocorrencia():
        ocorrencias.append(_nova_ocorrencia_extra())
        atualizar_lista()

    ctk.CTkButton(bloco, text="+ Adicionar Ocorrência Extra", width=200,
                  fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                  command=adicionar_ocorrencia).pack(anchor="w", padx=margem, pady=(0, 12))
    atualizar_lista()


def _construir_lista_sugestoes(bloco, itens, preservar_scroll=None,
                               reconstruir_lista=None, margem=14):
    """Lista dinâmica de Sugestões de Melhoria (mesmo padrão do relatório de
    limpeza): cada item tem um texto e uma foto OPCIONAL ('📎 Anexar Foto
    (opcional)'). '+ Adicionar Sugestão' cria um item em branco. `itens` é a
    lista de ESTADO ([{"origem", "legenda_var"}]) e sobrevive à reconstrução
    dos cards."""
    preservar_scroll = preservar_scroll or (lambda fn: fn)
    reconstruir_lista = reconstruir_lista or _reconstruir_simples

    lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
    lista_frame.pack(fill="x", padx=margem, pady=(0, 6))

    @preservar_scroll
    def atualizar_lista():
        def criar():
            novos = []
            for idx, item in enumerate(itens):
                grupo = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                     border_width=1, border_color=Marca.CINZA_BORDA,
                                     corner_radius=8)
                novos.append((grupo, dict(fill="x", pady=4, ipady=6)))

                entry_texto = ctk.CTkEntry(
                    grupo, placeholder_text="Descreva a sugestão de melhoria...", width=380)
                entry_texto.insert(0, item["legenda_var"].get())
                entry_texto.bind(
                    "<KeyRelease>",
                    lambda e, v=item["legenda_var"], en=entry_texto: v.set(en.get()))
                entry_texto.pack(fill="x", padx=10, pady=(6, 4))

                linha_foto = ctk.CTkFrame(grupo, fg_color="transparent")
                linha_foto.pack(fill="x", padx=10, pady=(0, 6))
                nome_arquivo = (os.path.basename(item["origem"]) if item.get("origem")
                                else "Nenhuma foto anexada")
                label_arquivo = ctk.CTkLabel(linha_foto, text=nome_arquivo, text_color="gray")
                label_arquivo.pack(side="left")

                def anexar(it=item, label=label_arquivo):
                    caminho = filedialog.askopenfilename(
                        title="Anexar foto (opcional)",
                        filetypes=[("Imagens", "*.png *.jpg *.jpeg")])
                    if caminho:
                        it["origem"] = caminho
                        label.configure(text=os.path.basename(caminho))

                ctk.CTkButton(linha_foto, text="📎 Anexar Foto (opcional)", width=170,
                              fg_color="gray40", command=anexar).pack(side="left", padx=8)
                ctk.CTkButton(
                    linha_foto, text="Remover", width=80, fg_color=Marca.ERRO,
                    hover_color=Marca.ERRO_HOVER,
                    command=lambda i=idx: (itens.pop(i), atualizar_lista()),
                ).pack(side="right")
            return novos
        reconstruir_lista(lista_frame, criar)

    def adicionar_sugestao():
        itens.append({"origem": None, "legenda_var": ctk.StringVar(value="")})
        atualizar_lista()

    ctk.CTkButton(bloco, text="+ Adicionar Sugestão", width=170,
                  fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                  command=adicionar_sugestao).pack(anchor="w", padx=margem, pady=(0, 12))
    atualizar_lista()


class _FormTrocaMicroinversor:
    """ESTADO do relatório de troca + construtores do corpo de cada seção.
    Não é um widget: cada seção é desenhada dentro do card modular do
    RelatorioView (construir_secao) e todo valor digitado vive em
    StringVars/listas aqui, então sobrevive à reconstrução dos cards."""

    def __init__(self):
        self.fotos = {k: [] for k in ("antiga", "nova", "micro")}
        self.ff_var, self.ft_var = ctk.StringVar(), ctk.StringVar()
        self.status_ff_var = ctk.StringVar(value="CONFORME")
        self.status_ft_var = ctk.StringVar(value="CONFORME")
        self.foto_ff_var, self.foto_ft_var = ctk.StringVar(), ctk.StringVar()
        # Sugestões de Melhoria: [{"origem": caminho|None, "legenda_var": StringVar}]
        self.sugestoes = []
        # Ocorrências extras: [{"titulo_var", "descricao_var", "fotos": [...]}]
        self.ocorrencias_extras = []
        # (preservar_scroll, reconstruir_lista): a tela injeta os dela; sem isso,
        # usa a reconstrução simples.
        self.ferramentas_lista = (None, None)
        self.modulos_rows = [self._nova_entrada(), self._nova_entrada()]
        self._modulos_container = None

    # ------------------------------------------------ corpo das seções --
    def construir_secao(self, chave, bloco):
        if chave == "troca_etiquetas":
            _SeletorFotos(bloco, "Microinversor com avaria",
                          self.fotos["antiga"], Marca.ERRO_TEXTO,
                          max_fotos=1).pack(fill="x")
            _SeletorFotos(bloco, "Microinversor novo",
                          self.fotos["nova"], Marca.SUCESSO_TEXTO,
                          max_fotos=1).pack(fill="x")
            _SeletorFotos(bloco, "Novo microinversor instalado",
                          self.fotos["micro"], max_fotos=1).pack(fill="x")
        elif chave == "troca_modulos":
            self._modulos_container = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
            self._modulos_container.pack(fill="x")
            self._render_modulos()
            ctk.CTkButton(bloco, text="+ Adicionar Entrada", width=150,
                          fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                          command=self._add_entrada).pack(anchor="w", pady=(4, 6))
        elif chave == "troca_cabo_tronco":
            medicoes = [
                ("Tensão Fase-Fase (V)", self.ff_var, self.status_ff_var, self.foto_ff_var),
                ("Tensão Fase-Terra (V)", self.ft_var, self.status_ft_var, self.foto_ft_var),
            ]
            for rotulo, var_valor, var_status, var_foto in medicoes:
                linha = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
                linha.pack(fill="x", pady=2)
                ctk.CTkLabel(linha, text=rotulo, width=160, anchor="w").pack(side="left")
                ctk.CTkEntry(linha, textvariable=var_valor, width=100
                             ).pack(side="left", padx=(8, 6))
                _BotaoFotoCompacto(linha, var_foto).pack(side="left", padx=(0, 10))
                _criar_seletor_status(linha, var_status)
            # sem rótulo/botão geral de foto: cada medição tem o seu 📷 na linha;
            # respiro final para o card fechar limpo após a última linha.
            ctk.CTkFrame(bloco, fg_color="transparent", height=4).pack(fill="x")
        elif chave == "troca_sugestoes":
            _construir_lista_sugestoes(bloco, self.sugestoes,
                                       *self.ferramentas_lista, margem=0)
        elif chave == "troca_ocorrencia":
            ctk.CTkLabel(bloco, text="Preencha só se houve imprevisto/anomalia. Se ficar "
                         "vazio, a seção não aparece no PDF.", text_color="gray",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
            _construir_lista_ocorrencias(bloco, self.ocorrencias_extras,
                                         *self.ferramentas_lista, margem=0)

    # ---- entradas de módulos ----
    @staticmethod
    def _nova_entrada(duplo=False, tensao="", corrente="", status="CONFORME", foto=""):
        return {"duplo_var": ctk.BooleanVar(value=duplo),
                "tensao_var": ctk.StringVar(value=tensao),
                "corrente_var": ctk.StringVar(value=corrente),
                "status_var": ctk.StringVar(value=status or "CONFORME"),
                "foto_var": ctk.StringVar(value=foto or "")}

    def _add_entrada(self):
        self.modulos_rows.append(self._nova_entrada())
        self._render_modulos()

    def _atualizar_rotulos(self):
        rotulos = _rotulos_modulos([r["duplo_var"].get() for r in self.modulos_rows])
        for r, texto in zip(self.modulos_rows, rotulos):
            r["rotulo_lbl"].configure(text=texto)

    def _render_modulos(self):
        cont = self._modulos_container
        for w in cont.winfo_children():
            w.destroy()
        for i, r in enumerate(self.modulos_rows):
            bloco_mod = ctk.CTkFrame(cont, fg_color="transparent")
            bloco_mod.pack(fill="x", pady=2)
            linha = ctk.CTkFrame(bloco_mod, fg_color="transparent")
            linha.pack(fill="x")
            r["rotulo_lbl"] = ctk.CTkLabel(linha, text="", width=110, anchor="w",
                                           font=ctk.CTkFont(weight="bold"))
            r["rotulo_lbl"].pack(side="left")
            ctk.CTkLabel(linha, text="Tensão (V)").pack(side="left")
            ctk.CTkEntry(linha, textvariable=r["tensao_var"], width=80).pack(side="left", padx=(6, 14))
            ctk.CTkLabel(linha, text="Corrente (A)").pack(side="left")
            ctk.CTkEntry(linha, textvariable=r["corrente_var"], width=80).pack(side="left", padx=(6, 6))
            _BotaoFotoCompacto(linha, r["foto_var"]).pack(side="left", padx=(0, 10))
            _criar_seletor_status(linha, r["status_var"])
            if len(self.modulos_rows) > 1:
                ctk.CTkButton(
                    linha, text="Remover", width=80, fg_color=Marca.ERRO,
                    hover_color=Marca.ERRO_HOVER,
                    command=lambda i=i: (self.modulos_rows.pop(i), self._render_modulos()),
                ).pack(side="right")
            # 2ª linha: checkbox de entrada dupla, alinhado sob as medições
            ctk.CTkCheckBox(bloco_mod, text="2 Módulos nesta entrada", variable=r["duplo_var"],
                            command=self._atualizar_rotulos).pack(anchor="w", padx=(110, 0), pady=(2, 0))
        self._atualizar_rotulos()

    # ---- coleta / carga / limpeza ----
    def coletar(self):
        """Estrutura completa (texto digitado + caminhos das fotos) — é o que
        vai para o banco em relatorios.dados_troca_json."""
        return {
            "etiquetas_antigas": _fotos_valores(self.fotos["antiga"]),
            "etiquetas_novas": _fotos_valores(self.fotos["nova"]),
            "fotos_microinversor_novo": _fotos_valores(self.fotos["micro"]),
            "modulos": [{"duplo": r["duplo_var"].get(),
                         "tensao": r["tensao_var"].get().strip(),
                         "corrente": r["corrente_var"].get().strip(),
                         "status": r["status_var"].get(),
                         "foto": r["foto_var"].get()}
                        for r in self.modulos_rows],
            "cabo_tronco": {"tensao_ff": self.ff_var.get().strip(),
                            "tensao_ft": self.ft_var.get().strip(),
                            "status_ff": self.status_ff_var.get(),
                            "status_ft": self.status_ft_var.get(),
                            "foto_ff": self.foto_ff_var.get(),
                            "foto_ft": self.foto_ft_var.get()},
            "sugestoes": [{"texto": it["legenda_var"].get().strip(), "origem": it.get("origem")}
                          for it in self.sugestoes
                          if it["legenda_var"].get().strip() or it.get("origem")],
            "ocorrencias_extras": _coletar_ocorrencias(self.ocorrencias_extras),
        }

    @staticmethod
    def _foto_existente(caminho):
        return caminho if caminho and os.path.exists(caminho) else ""

    def carregar(self, d):
        self.limpar()
        if not d:
            return
        for chave, campo in (("antiga", "etiquetas_antigas"), ("nova", "etiquetas_novas"),
                             ("micro", "fotos_microinversor_novo")):
            _fotos_definir(self.fotos[chave], d.get(campo))
        mods = d.get("modulos") or []
        if mods:
            self.modulos_rows = [self._nova_entrada(m.get("duplo", False),
                                                    m.get("tensao", ""), m.get("corrente", ""),
                                                    m.get("status", "CONFORME"),
                                                    self._foto_existente(m.get("foto")))
                                 for m in mods]
        tronco = d.get("cabo_tronco") or {}
        self.ff_var.set(tronco.get("tensao_ff", ""))
        self.ft_var.set(tronco.get("tensao_ft", ""))
        self.status_ff_var.set(tronco.get("status_ff") or "CONFORME")
        self.status_ft_var.set(tronco.get("status_ft") or "CONFORME")
        self.foto_ff_var.set(self._foto_existente(tronco.get("foto_ff")))
        self.foto_ft_var.set(self._foto_existente(tronco.get("foto_ft")))
        self.sugestoes[:] = [
            {"origem": self._foto_existente(sv.get("origem")) or None,
             "legenda_var": ctk.StringVar(value=sv.get("texto", ""))}
            for sv in d.get("sugestoes") or []]
        salvas = d.get("ocorrencias_extras")
        if salvas is None and d.get("ocorrencia"):      # relatório salvo no formato antigo
            salvas = [d["ocorrencia"]]
        _carregar_ocorrencias(self.ocorrencias_extras, salvas)

    def limpar(self):
        for itens in self.fotos.values():
            itens.clear()
        self.modulos_rows = [self._nova_entrada(), self._nova_entrada()]
        self.ocorrencias_extras.clear()
        self.sugestoes.clear()
        for var in (self.ff_var, self.ft_var, self.foto_ff_var, self.foto_ft_var):
            var.set("")
        self.status_ff_var.set("CONFORME")
        self.status_ft_var.set("CONFORME")

    def para_pdf(self, d, converter):
        """Converte a estrutura salva no formato do gerador de PDF. `converter`
        copia cada foto para a pasta temporária e devolve o novo caminho."""
        def fotos(lista):
            return [{"foto_path": converter(f["origem"]), "legenda": f.get("legenda", "")}
                    for f in lista if f.get("origem") and os.path.exists(f["origem"])]

        def foto_unica(caminho):
            """Foto do botão 📷 compacto: caminho convertido ou None."""
            return converter(caminho) if caminho and os.path.exists(caminho) else None

        # Rótulos calculados ANTES de descartar linhas vazias (= numeração da tela).
        rotulos = _rotulos_modulos([m["duplo"] for m in d["modulos"]])
        modulos = []
        for rotulo, m in zip(rotulos, d["modulos"]):
            tensao = _to_float_medicao(m.get("tensao"))
            corrente = _to_float_medicao(m.get("corrente"))
            foto = foto_unica(m.get("foto"))
            # Linha só com foto (sem medição) também entra: a foto aparece no PDF.
            if tensao is not None or corrente is not None or foto:
                modulos.append({"rotulo": rotulo, "tensao": tensao, "corrente": corrente,
                                "status": m.get("status") or "CONFORME",
                                "foto_path": foto})
        tronco = d.get("cabo_tronco") or {}
        return {
            "etiquetas_antigas": fotos(d["etiquetas_antigas"]),
            "etiquetas_novas": fotos(d["etiquetas_novas"]),
            "fotos_microinversor_novo": fotos(d["fotos_microinversor_novo"]),
            "modulos": modulos,
            "cabo_tronco": {"tensao_ff": _to_float_medicao(tronco.get("tensao_ff")),
                            "tensao_ft": _to_float_medicao(tronco.get("tensao_ft")),
                            "status_ff": tronco.get("status_ff") or "CONFORME",
                            "status_ft": tronco.get("status_ft") or "CONFORME",
                            "foto_ff": foto_unica(tronco.get("foto_ff")),
                            "foto_ft": foto_unica(tronco.get("foto_ft"))},
            "sugestoes": [{"foto_path": foto_unica(sv.get("origem")),
                           "legenda": sv.get("texto", "")}
                          for sv in d.get("sugestoes") or []
                          if sv.get("texto") or foto_unica(sv.get("origem"))],
            "ocorrencias_extras": [
                {"titulo": oc["titulo"], "descricao": oc["descricao"],
                 "fotos": fotos(oc["fotos"])}
                for oc in d.get("ocorrencias_extras") or []],
        }


class RelatorioView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.empresa_dao = EmpresaDAO()
        self.cliente_dao = ClienteDAO()
        self.relatorio_dao = RelatorioDAO()
        self.config_dao = ConfiguracaoDAO()

        # Limpeza preventiva: apaga pastas temporárias de fotos deixadas por um
        # fechamento inesperado em execuções anteriores (nunca trava a tela).
        try:
            limpar_pasta_temporaria()
        except Exception:
            pass

        # Cada tipo de relatório tem sua própria lista de seções (ordem + switches).
        # `ordem_secoes` / `secoes_ativas_vars` (properties) devolvem a do tipo atual.
        self.tipo_var = ctk.StringVar(value=_TIPO_LIMPEZA)
        # Ordem padrão do código; se o usuário já reordenou com ▲▼, vale a salva no banco.
        self._ordem_limpeza = self._carregar_ordem(
            CHAVE_ORDEM_SECOES_LIMPEZA,
            list(_SECOES_FOTO) + [_SECAO_TABELA, _SECAO_OCORRENCIAS])
        self._vars_limpeza = {s: ctk.BooleanVar(value=False) for s in self._ordem_limpeza}
        self._ordem_troca = self._carregar_ordem(CHAVE_ORDEM_SECOES_TROCA,
                                                 list(_SECOES_TROCA))
        self._vars_troca = {s: ctk.BooleanVar(value=False) for s in self._ordem_troca}
        self.form_troca = _FormTrocaMicroinversor()
        self.form_troca.ferramentas_lista = (self._preservar_scroll, self._reconstruir_lista)
        # Ocorrências extras: [{"titulo_var", "descricao_var", "fotos": [...]}]
        # (estado fora dos cards: sobrevive a ▲/▼, switch e re-renderizações).
        self.ocorrencias_extras = []
        self.fotos_por_secao = {s: [] for s in _SECOES_FOTO}
        # Inversores: [{nome_var, foto_var (etiqueta), strings: [bloco de String]}]
        self.inversores = []
        self.disjuntores_rows = []
        # id do relatório carregado para edição (None = relatório novo).
        self._relatorio_editando_id = None

        # Teste de Neutro: opcional, aplicável a Strings e disjuntores do
        # Circuito CA quando a usina possui condutor neutro. Um único
        # switch controla a visibilidade do 4º campo em ambos os blocos.
        self.possui_neutro_var = ctk.BooleanVar(value=False)

        self._empresas_cache = []
        self._empresas_map = {}
        self._clientes_map = {}
        self._clientes_atuais = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_ui()
        self._sem_foco_por_tab(self)

    def _carregar_ordem(self, chave, padrao):
        """Ordem salva no banco ou, se não houver (ou der erro), a padrão."""
        try:
            return self.config_dao.obter_ordem_secoes(chave, padrao)
        except Exception:
            return list(padrao)

    def _salvar_ordem_atual(self):
        """Grava a ordem do tipo de relatório atual (JSON). Falha de banco
        nunca derruba a tela: a ordem continua valendo na sessão."""
        chave = (CHAVE_ORDEM_SECOES_TROCA if self.tipo_var.get() == _TIPO_TROCA
                 else CHAVE_ORDEM_SECOES_LIMPEZA)
        try:
            self.config_dao.salvar_ordem_secoes(chave, self.ordem_secoes)
        except Exception:
            pass

    @property
    def ordem_secoes(self):
        return self._ordem_troca if self.tipo_var.get() == _TIPO_TROCA else self._ordem_limpeza

    @ordem_secoes.setter
    def ordem_secoes(self, valor):
        if self.tipo_var.get() == _TIPO_TROCA:
            self._ordem_troca = valor
        else:
            self._ordem_limpeza = valor

    @property
    def secoes_ativas_vars(self):
        return self._vars_troca if self.tipo_var.get() == _TIPO_TROCA else self._vars_limpeza

    # --------------------------------------------------------------- UI --
    def _construir_ui(self):
        scroll = _ScrollSuave(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scroll.grid_columnconfigure(0, weight=1)
        self.scroll = scroll

        topo = ctk.CTkFrame(scroll, corner_radius=14)
        topo.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(topo, text="Tipo de Relatório", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(side="left", padx=(18, 14), pady=14)
        ctk.CTkOptionMenu(
            topo, values=_TIPOS_RELATORIO, variable=self.tipo_var, width=330,
            fg_color=Marca.ACCENT, button_color=Marca.ACCENT_HOVER,
            command=self._on_tipo_relatorio,
        ).pack(side="left", pady=14)

        cabecalho = ctk.CTkFrame(scroll, corner_radius=14)
        cabecalho.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(cabecalho, text="Dados do Relatório",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(16, 10))

        linha1 = ctk.CTkFrame(cabecalho, fg_color="transparent")
        linha1.pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(linha1, text="Empresa Prestadora *", width=200, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(linha1, text="Cliente *", width=200, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(20, 0)
        )

        bloco_empresa = ctk.CTkFrame(linha1, fg_color="transparent")
        bloco_empresa.grid(row=1, column=0, sticky="w")
        self.combo_empresa = ctk.CTkComboBox(
            bloco_empresa, values=[], width=250, command=self._on_empresa_selecionada,
        )
        self.combo_empresa.set("")
        self.combo_empresa.pack(side="left")
        ctk.CTkButton(
            bloco_empresa, text="🔍", width=34, fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._abrir_busca_empresa,
        ).pack(side="left", padx=(6, 0))

        bloco_cliente = ctk.CTkFrame(linha1, fg_color="transparent")
        bloco_cliente.grid(row=1, column=1, sticky="w", padx=(20, 0))
        self.combo_cliente = ctk.CTkComboBox(
            bloco_cliente, values=[], width=250, command=self._recalcular_codigo,
        )
        self.combo_cliente.set("")
        self.combo_cliente.pack(side="left")
        ctk.CTkButton(
            bloco_cliente, text="🔍", width=34, fg_color=Marca.ACCENT,
            hover_color=Marca.ACCENT_HOVER, command=self._abrir_busca_cliente,
        ).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            linha1, text="A lista de clientes é filtrada pela empresa escolhida.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=2, column=1, sticky="w", padx=(20, 0), pady=(3, 0))

        linha2 = ctk.CTkFrame(cabecalho, fg_color="transparent")
        linha2.pack(fill="x", padx=18, pady=(10, 4))
        ctk.CTkLabel(linha2, text="Data do Serviço", width=200, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.data_servico_entry = DateEntry(
            linha2, width=17, date_pattern="dd/mm/yyyy",
            background=Marca.ACCENT, foreground="white", borderwidth=1,
        )
        self.data_servico_entry.grid(row=1, column=0, sticky="w", ipady=3)
        self.data_servico_entry.bind("<<DateEntrySelected>>", self._recalcular_codigo)
        self.data_servico_entry.bind("<FocusOut>", self._recalcular_codigo)

        rodape_cabecalho = ctk.CTkFrame(cabecalho, fg_color="transparent")
        rodape_cabecalho.pack(fill="x", padx=18, pady=(12, 16))
        ctk.CTkLabel(rodape_cabecalho, text="Código do Relatório:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        # Somente leitura: o código é sempre gerado pelo sistema (próximo
        # número livre do dia), evitando códigos repetidos digitados à mão.
        self.entry_codigo = ctk.CTkEntry(
            rodape_cabecalho, width=190, justify="center",
            text_color=Marca.ACCENT, font=ctk.CTkFont(weight="bold"),
        )
        self.entry_codigo.pack(side="left", padx=(8, 24))
        self._definir_codigo(
            self.relatorio_dao.obter_proximo_codigo_relatorio(self.data_servico_entry.get())
        )

        ctk.CTkLabel(rodape_cabecalho, text="Revisão (REV):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.entry_revisao = ctk.CTkEntry(rodape_cabecalho, width=60)
        self.entry_revisao.insert(0, "01")
        self.entry_revisao.pack(side="left", padx=(8, 0))

        textos_frame = ctk.CTkFrame(scroll, corner_radius=14)
        textos_frame.pack(fill="x", pady=(0, 14))
        self.textos_frame = textos_frame
        ctk.CTkLabel(textos_frame, text="Objetivo, Aplicação e Normas de Referência",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=18, pady=(16, 8))
        self.txt_objetivo = self._textbox_com_rotulo(
            textos_frame, "Objetivo", TEXTO_OBJETIVO_PADRAO
        )
        self.txt_aplicacao = self._textbox_com_rotulo(
            textos_frame, "Aplicação", TEXTO_APLICACAO_PADRAO
        )
        self.txt_normas = self._textbox_com_rotulo(
            textos_frame, "Normas de Referência", TEXTO_NORMAS_PADRAO, ultimo=True
        )

        secoes_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        secoes_frame.pack(fill="x", pady=(0, 14))
        self.secoes_frame = secoes_frame
        ctk.CTkLabel(secoes_frame, text="Seções do Relatório",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=Marca.PRIMARIA).pack(anchor="w", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            secoes_frame, text="Ative apenas as etapas realizadas e use ▲▼ para reordenar.",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=4, pady=(0, 10))
        self.secoes_container = ctk.CTkFrame(secoes_frame, fg_color="transparent")
        self.secoes_container.pack(fill="x")
        self._renderizar_secoes()

        self.btn_gerar = ctk.CTkButton(
            scroll, text="📄  Gerar Relatório em PDF", height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
            command=self._gerar_relatorio,
        )
        self.btn_gerar.pack(fill="x", pady=(4, 30))

    def _textbox_com_rotulo(self, parent, rotulo, texto_padrao, ultimo=False):
        ctk.CTkLabel(parent, text=rotulo, font=ctk.CTkFont(size=12)).pack(
            anchor="w", padx=18, pady=(6, 0)
        )
        box = ctk.CTkTextbox(parent, height=70)
        box.pack(fill="x", padx=18, pady=(2, 16 if ultimo else 4))
        box.insert("1.0", texto_padrao)
        return box

    # ------------------------------------------ scroll / foco (estabilidade) --
    _CLASSES_DE_TEXTO = {"Entry", "Text", "TEntry", "TCombobox", "Spinbox"}

    def _canvas_scroll(self):
        scroll = getattr(self, "scroll", None)
        return getattr(scroll, "_parent_canvas", None)

    def _com_scroll_preservado(self, fn, *args, **kwargs):
        """Roda `fn` e restaura a posição de rolagem (em pixels)."""
        canvas = self._canvas_scroll()
        topo = canvas.canvasy(0) if canvas is not None else None
        try:
            return fn(*args, **kwargs)
        finally:
            if canvas is not None:
                self._restaurar_scroll(topo)

    def _preservar_scroll(self, fn):
        """Versão para closures (listas internas dos cards)."""
        @functools.wraps(fn)
        def interno(*args, **kwargs):
            return self._com_scroll_preservado(fn, *args, **kwargs)
        return interno

    def _restaurar_scroll(self, topo):
        canvas = self._canvas_scroll()
        if canvas is None or topo is None:
            return
        gesto = self.scroll.contador_roda

        def aplicar(checar=False):
            # se o usuário girou a roda nesse meio-tempo, não briga com ele
            if checar and self.scroll.contador_roda != gesto:
                return
            try:
                bbox = canvas.bbox("all")
                if not bbox:
                    return
                canvas.configure(scrollregion=bbox)
                total = bbox[3] - bbox[1]
                visivel = canvas.winfo_height()
                if total <= visivel:
                    canvas.yview_moveto(0)
                    return
                alvo = min(max(topo, bbox[1]), bbox[3] - visivel)
                canvas.yview_moveto((alvo - bbox[1]) / total)
            except Exception:
                pass

        try:
            canvas.update_idletasks()
        except Exception:
            pass
        aplicar()
        canvas.after_idle(lambda: aplicar(True))
        canvas.after(40, lambda: aplicar(True))

    def _reconstruir_lista(self, pai, criar_itens):
        """Reconstrói uma lista dinâmica sem piscar nem pular.

        `criar_itens()` cria os frames-item NOVOS como filhos de `pai`, SEM
        empacotá-los, e devolve [(widget, kwargs_do_pack), ...]. Aqui:
          1. os itens novos recebem tamanho/cores finais (update_idletasks)
             enquanto os antigos ainda estão na tela;
          2. os antigos são destruídos e os novos exibidos no mesmo ciclo.
        Nenhum `see()`/foco é chamado: a rolagem fica sob controle do
        usuário (a posição é preservada por `_preservar_scroll`)."""
        antigos = list(pai.winfo_children())
        novos = criar_itens()
        if pai.winfo_ismapped():
            self.update_idletasks()
        for w in antigos:
            w.destroy()
        for w, kw in novos:
            w.pack(**kw)

    def _sem_foco_por_tab(self, raiz):
        """takefocus=0 (direto no Tk) em botões, switches, combos e demais
        widgets de seleção. Campos de digitação ficam de fora, para o Tab
        e o clique continuarem funcionando neles."""
        try:
            filhos = raiz.winfo_children()
        except Exception:
            return
        for w in filhos:
            try:
                if w.winfo_class() not in self._CLASSES_DE_TEXTO:
                    w.tk.call(w._w, "configure", "-takefocus", 0)
            except Exception:
                pass
            self._sem_foco_por_tab(w)

    # --------------------------------------------------- busca / filtro --
    def _abrir_busca_empresa(self):
        itens = [
            {"id": e["id"], "label": e["nome"], "sublabel": e.get("cnpj") or ""}
            for e in self._empresas_cache
        ]
        abrir_busca_modal(
            self.winfo_toplevel(), "Buscar Empresa", itens, self._selecionar_empresa,
            placeholder="Buscar por nome da empresa...",
        )

    @_mantem_scroll
    def _selecionar_empresa(self, item):
        self.combo_empresa.set(item["label"])
        self._on_empresa_selecionada(item["label"])

    def _abrir_busca_cliente(self):
        if not self._clientes_atuais:
            mostrar_alerta(
                self.winfo_toplevel(), "Selecione a empresa primeiro",
                "Escolha uma Empresa Prestadora para ver os clientes vinculados a ela.",
                "aviso",
            )
            return
        itens = [
            {"id": c["id"], "label": c["nome_razao_social"], "sublabel": c.get("endereco") or ""}
            for c in self._clientes_atuais
        ]
        abrir_busca_modal(
            self.winfo_toplevel(), "Buscar Cliente", itens, self._selecionar_cliente,
            placeholder="Buscar por nome do cliente...",
        )

    @_mantem_scroll
    def _selecionar_cliente(self, item):
        self.combo_cliente.set(item["label"])
        self._recalcular_codigo()

    @_mantem_scroll
    def _on_empresa_selecionada(self, valor):
        self._atualizar_clientes_por_empresa(valor)
        self.combo_cliente.set("")
        self._recalcular_codigo()

    def _definir_codigo(self, texto):
        """Grava o texto no campo de código (que fica desabilitado)."""
        self.entry_codigo.configure(state="normal")
        self.entry_codigo.delete(0, "end")
        self.entry_codigo.insert(0, texto)
        self.entry_codigo.configure(state="disabled")

    def _recalcular_codigo(self, *_):
        """Preenche o Código do Relatório com o próximo código livre do dia
        da Data do Serviço (RMP-AAAAMMDD-NNN). Ao EDITAR um relatório
        existente o código original é mantido e nunca recalculado."""
        if self._relatorio_editando_id is not None:
            return
        self._definir_codigo(
            self.relatorio_dao.obter_proximo_codigo_relatorio(self.data_servico_entry.get())
        )

    @staticmethod
    def _proxima_revisao(revisao):
        """'01' -> '02', '09' -> '10'. Valor inválido -> '02'."""
        try:
            return f"{int(str(revisao).strip()) + 1:02d}"
        except (ValueError, TypeError):
            return "02"

    def _atualizar_clientes_por_empresa(self, nome_empresa):
        empresa_id = self._empresas_map.get(nome_empresa)
        if empresa_id:
            self._clientes_atuais = self.cliente_dao.listar(empresa_id=empresa_id)
        else:
            self._clientes_atuais = []

        self._clientes_map = {c["nome_razao_social"]: c["id"] for c in self._clientes_atuais}
        if self._clientes_atuais:
            self.combo_cliente.configure(values=list(self._clientes_map.keys()))
        else:
            placeholder = (
                "Nenhum cliente cadastrado para esta empresa" if empresa_id
                else "Selecione uma empresa primeiro"
            )
            self.combo_cliente.configure(values=[placeholder])

    # ------------------------------------------------------------ cortina --
    _cortina = None
    _cortina_job = None

    def _erguer_cortina(self):
        """Cobre a área rolável com um painel liso (cor do fundo). Devolve a
        cortina, ou None se não houver canvas (nesse caso nada é coberto)."""
        canvas = self._canvas_scroll()
        if canvas is None:
            return None
        try:
            if self._cortina_job:
                self.after_cancel(self._cortina_job)
                self._cortina_job = None
            try:
                cor = canvas.cget("bg")
            except Exception:
                cor = self.winfo_toplevel().cget("bg")
            if self._cortina is None or not self._cortina.winfo_exists():
                self._cortina = tk.Frame(self, bd=0, highlightthickness=0)
            self._cortina.configure(bg=cor)
            self._cortina.place(in_=canvas, x=0, y=0, relwidth=1, relheight=1)
            self._cortina.lift()
            return self._cortina
        except Exception:
            return None

    def _agendar_baixar_cortina(self):
        if self._cortina is None:
            return
        try:
            if self._cortina_job:
                self.after_cancel(self._cortina_job)
            self._cortina_job = self.after(_CORTINA_MS, self._baixar_cortina)
        except Exception:
            self._baixar_cortina()

    def _baixar_cortina(self):
        """Descobre a lista já pronta (layout e rolagem restaurados)."""
        self._cortina_job = None
        try:
            if self._cortina is not None:
                self._cortina.place_forget()
            if _CORTINA_COM_FADE:
                janela = self.winfo_toplevel()
                if _alpha_suportado(janela):
                    _cancelar_fade(janela)
                    janela.attributes("-alpha", _FADE_ALPHA_INICIAL)
                    _fade_in(janela)
        except Exception:        # tela fechada antes da hora
            pass

    # ------------------------------------------------------- seções UI --
    @_mantem_scroll
    def _renderizar_secoes(self):
        """Recria a lista de seções sem tremor:
          0) ergue a CORTINA sobre a área rolável: nenhum estado intermediário
             (cards cortados, pedaços sem pintar) chega a aparecer;
          1) OCULTA o container (pack_forget) enquanto cards são recriados;
          2) congela a geometria (pack_propagate(False)) durante a montagem;
          3) ao terminar: devolve a propagação, processa o layout em memória
             (update_idletasks), EXIBE o container e o decorador
             @_mantem_scroll restaura a rolagem; só então a cortina baixa
             (_CORTINA_MS depois).
        Os try/finally garantem que nem o container nem a cortina fiquem
        presos, mesmo se a montagem falhar."""
        container = self.secoes_container
        self._erguer_cortina()
        try:
            self.update_idletasks()  # fecha eventos pendentes ANTES de ocultar
            altura = max(container.winfo_height(), 1)
            container.pack_forget()
            container.configure(height=altura)
            container.pack_propagate(False)
            try:
                self._montar_secoes()
            finally:
                container.pack_propagate(True)
                self.update_idletasks()      # layout final calculado em memória
                container.pack(fill="x")     # só agora a lista reaparece
        finally:
            self._agendar_baixar_cortina()

    def _montar_secoes(self):
        # Monta os cards NOVOS fora da tela (sem pack) e só troca pelos
        # antigos quando estiverem prontos — sem "esqueleto" nem piscada.
        # A posição de rolagem é salva/restaurada (em pixels) pelo decorador
        # @_mantem_scroll, via self.scroll._parent_canvas.
        self.update_idletasks()  # fecha eventos pendentes ANTES de recriar
        # Toda re-renderização (ativar/desativar seção, ▲/▼, adicionar ou
        # remover foto) renumera as figuras antes de desenhar as legendas.
        self._reindexar_figuras()
        antigos = list(self.secoes_container.winfo_children())
        novos = []

        for i, chave in enumerate(self.ordem_secoes):
            ativo = self.secoes_ativas_vars[chave].get()

            # Ao ativar pela primeira vez, alguns módulos já vêm com
            # conteúdo padrão pronto (evita o card nascer vazio):
            if ativo and chave == "geracao_energia" and not self.fotos_por_secao[chave]:
                self.fotos_por_secao[chave] = [
                    {"origem": None,
                     "legenda_var": ctk.StringVar(value="Gráfico de geração — Antes da limpeza.")},
                    {"origem": None,
                     "legenda_var": ctk.StringVar(value="Gráfico de geração — Depois da limpeza.")},
                ]
            if ativo and chave == _SECAO_TABELA and not self.inversores:
                self.inversores.append(self._criar_inversor_padrao())

            # height=1 aqui é proposital: evita que o CTkFrame reserve a
            # altura padrão (200px) do customtkinter antes de ter
            # conteúdo — o card nasce compacto e só cresce conforme o
            # usuário adiciona fotos/strings/sugestões.
            card = ctk.CTkFrame(
                self.secoes_container,
                corner_radius=14, height=54,   # altura mínima fixa: título nunca é cortado
                border_width=2 if ativo else 0,
                border_color=Marca.ACCENT if ativo else ("#DBDBDB", "#2B2B2B")
            )
            novos.append((card, dict(fill="x", pady=6)))

            # Linha do item com altura FIXA (48px) e sem propagação: o
            # tamanho não depende do conteúdo, então nada é cortado nem
            # sobreposto durante a reconstrução.
            cabecalho = ctk.CTkFrame(card, fg_color="transparent", height=48)
            cabecalho.pack(fill="x", padx=14, pady=(4, 4))
            cabecalho.pack_propagate(False)

            # width=0: o CTkLabel usa a largura do texto (o padrão de 140px
            # era o que truncava "Comparativo de Geraç...").
            ctk.CTkLabel(
                cabecalho,
                text=_nome_secao(chave),
                font=ctk.CTkFont(size=13, weight="bold"),
                width=0, anchor="w",
            ).pack(side="left")

            botoes_frame = ctk.CTkFrame(cabecalho, fg_color="transparent")
            botoes_frame.pack(side="right")

            if i > 0:
                ctk.CTkButton(
                    botoes_frame, text="▲", width=28, height=24,
                    command=lambda pos=i: self._mover_secao(pos, pos - 1)
                ).pack(side="left", padx=2)

            if i < len(self.ordem_secoes) - 1:
                ctk.CTkButton(
                    botoes_frame, text="▼", width=28, height=24,
                    command=lambda pos=i: self._mover_secao(pos, pos + 1)
                ).pack(side="left", padx=2)

            switch = ctk.CTkSwitch(
                botoes_frame,
                text="",
                variable=self.secoes_ativas_vars[chave],
                command=self._renderizar_secoes
            )
            switch.pack(side="left", padx=(8, 0))

            if ativo:
                corpo_secao = ctk.CTkFrame(card, fg_color="transparent", height=1)
                corpo_secao.pack(fill="x", padx=14, pady=(0, 12))
                self._renderizar_conteudo_secao(chave, corpo_secao)

        # O container está oculto (ver _renderizar_secoes): troca direta,
        # sem nenhum quadro intermediário visível.
        for w in antigos:
            w.destroy()
        for w, kw in novos:
            w.pack(**kw)

        self._sem_foco_por_tab(self.secoes_container)

    def _renderizar_conteudo_secao(self, chave, bloco):
        if chave in _SECOES_TROCA:
            self.form_troca.construir_secao(chave, bloco)
        elif chave == "geracao_energia":
            self._construir_bloco_geracao_energia(bloco)
        elif chave == "sugestoes_melhorias":
            self._construir_bloco_sugestoes(bloco)
        elif chave in _SECOES_FOTO:
            self._construir_bloco_fotos(bloco, chave)
        elif chave == _SECAO_TABELA:
            self._construir_bloco_tabela(bloco)
        elif chave == _SECAO_OCORRENCIAS:
            self._construir_bloco_ocorrencias(bloco)

    def _reindexar_figuras(self):
        """Renumera "Figura X:" de todas as fotos das seções ATIVAS, na ordem
        em que aparecem no relatório (ordem_secoes), de forma contínua:
        Figura 1, 2, 3... somando todas as seções. Preserva o texto que o
        usuário escreveu depois do prefixo."""
        n = 0
        for chave in self.ordem_secoes:
            if chave not in _SECOES_NUMERADAS or not self.secoes_ativas_vars[chave].get():
                continue
            for foto in self.fotos_por_secao[chave]:
                if not foto.get("origem"):
                    continue
                n += 1
                resto = _RE_PREFIXO_FIGURA.sub("", foto["legenda_var"].get()).strip()
                foto["legenda_var"].set(f"Figura {n}: {resto}" if resto else f"Figura {n}:")

    @_mantem_scroll
    def _mover_secao(self, origem, destino):
        self.update_idletasks()
        self.ordem_secoes[origem], self.ordem_secoes[destino] = (
            self.ordem_secoes[destino], self.ordem_secoes[origem]
        )
        self._salvar_ordem_atual()
        self._renderizar_secoes()

    def _construir_bloco_fotos(self, bloco, chave):
        if chave in _TITULOS_TOPO_FOTO:
            texto_topo, cor_topo = _TITULOS_TOPO_FOTO[chave]
            ctk.CTkLabel(
                bloco, text=texto_topo, text_color=cor_topo,
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(anchor="w", padx=14, pady=(0, 8))

        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx, foto in enumerate(self.fotos_por_secao[chave]):
                    linha = ctk.CTkFrame(lista_frame, fg_color="transparent")
                    itens.append((linha, dict(fill="x", pady=2)))
                    nome_arquivo = os.path.basename(foto["origem"])
                    ctk.CTkLabel(linha, text=nome_arquivo, width=180, anchor="w").pack(
                        side="left"
                    )
                    entry_legenda = ctk.CTkEntry(linha, placeholder_text="Legenda (opcional)",
                                                  width=280)
                    entry_legenda.insert(0, foto["legenda_var"].get())
                    entry_legenda.bind(
                        "<KeyRelease>",
                        lambda e, v=foto["legenda_var"], en=entry_legenda:
                        v.set(en.get()),
                    )
                    entry_legenda.pack(side="left", padx=8)
                    ctk.CTkButton(
                        linha, text="Remover", width=80, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.fotos_por_secao[chave].pop(i), self._renderizar_secoes()
                        ),
                    ).pack(side="left")
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_fotos():
            caminhos = filedialog.askopenfilenames(
                title="Selecionar fotos", filetypes=[("Imagens", "*.png *.jpg *.jpeg")]
            )
            legenda_padrao = _LEGENDAS_PADRAO_FOTO.get(chave, "")
            for c in caminhos:
                self.fotos_por_secao[chave].append(
                    {"origem": c, "legenda_var": ctk.StringVar(value=legenda_padrao)}
                )
            if caminhos:
                self._renderizar_secoes()  # reindexa e redesenha todas as legendas

        ctk.CTkButton(bloco, text="+ Adicionar Fotos", width=140,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_fotos).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

    # ---------------------------------------------- comparativo geração --
    def _construir_bloco_geracao_energia(self, bloco):
        """2 slots fixos ('Gráfico Anterior' / 'Gráfico Posterior'), já
        prontos com título e legenda padrão assim que a seção é ativada —
        o usuário só precisa selecionar as duas imagens."""
        slots = self.fotos_por_secao["geracao_energia"]
        rotulos_slot = ["Gráfico Anterior (antes da limpeza)",
                         "Gráfico Posterior (depois da limpeza)"]

        container = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        container.pack(fill="x", padx=14, pady=(0, 6))

        for idx, slot in enumerate(slots):
            rotulo_slot = rotulos_slot[idx] if idx < len(rotulos_slot) else f"Gráfico {idx + 1}"
            grupo = ctk.CTkFrame(container, fg_color="transparent", height=1,
                                  border_width=1, border_color=Marca.CINZA_BORDA,
                                  corner_radius=8)
            grupo.pack(fill="x", pady=4, ipady=6)

            ctk.CTkLabel(grupo, text=rotulo_slot, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=Marca.PRIMARIA).pack(anchor="w", padx=10, pady=(4, 2))

            linha = ctk.CTkFrame(grupo, fg_color="transparent")
            linha.pack(fill="x", padx=10, pady=2)
            nome_arquivo = os.path.basename(slot["origem"]) if slot.get("origem") else \
                "Nenhuma imagem selecionada"
            label_arquivo = ctk.CTkLabel(linha, text=nome_arquivo, text_color="gray", width=200,
                                         anchor="w")
            label_arquivo.pack(side="left")

            def selecionar(i=idx, label=label_arquivo):
                caminho = filedialog.askopenfilename(
                    title="Selecionar imagem do gráfico",
                    filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
                )
                if caminho:
                    self.fotos_por_secao["geracao_energia"][i]["origem"] = caminho
                    label.configure(text=os.path.basename(caminho))

            ctk.CTkButton(linha, text="Selecionar...", width=110,
                          fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                          command=selecionar).pack(side="left", padx=8)

            entry_legenda = ctk.CTkEntry(grupo, width=380)
            entry_legenda.insert(0, slot["legenda_var"].get())
            entry_legenda.bind(
                "<KeyRelease>",
                lambda e, v=slot["legenda_var"], en=entry_legenda: v.set(en.get()),
            )
            entry_legenda.pack(fill="x", padx=10, pady=(4, 2))

    # ------------------------------------------------ sugestões dinâmicas --
    def _construir_bloco_sugestoes(self, bloco):
        """Lista dinâmica de sugestões — cada uma é um texto (obrigatório)
        com foto opcional anexada. '+ Adicionar Sugestão' cria uma
        nova entrada em branco; nada é exigido até o usuário preencher."""
        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx, item in enumerate(self.fotos_por_secao["sugestoes_melhorias"]):
                    grupo = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                          border_width=1, border_color=Marca.CINZA_BORDA,
                                          corner_radius=8)
                    itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                    entry_texto = ctk.CTkEntry(
                        grupo, placeholder_text="Descreva a sugestão de melhoria...", width=380,
                    )
                    entry_texto.insert(0, item["legenda_var"].get())
                    entry_texto.bind(
                        "<KeyRelease>",
                        lambda e, v=item["legenda_var"], en=entry_texto: v.set(en.get()),
                    )
                    entry_texto.pack(fill="x", padx=10, pady=(6, 4))

                    linha_foto = ctk.CTkFrame(grupo, fg_color="transparent")
                    linha_foto.pack(fill="x", padx=10, pady=(0, 6))
                    nome_arquivo = os.path.basename(item["origem"]) if item.get("origem") else \
                        "Nenhuma foto anexada"
                    label_arquivo = ctk.CTkLabel(linha_foto, text=nome_arquivo, text_color="gray")
                    label_arquivo.pack(side="left")

                    def anexar(i=idx, label=label_arquivo):
                        caminho = filedialog.askopenfilename(
                            title="Anexar foto (opcional)",
                            filetypes=[("Imagens", "*.png *.jpg *.jpeg")],
                        )
                        if caminho:
                            self.fotos_por_secao["sugestoes_melhorias"][i]["origem"] = caminho
                            label.configure(text=os.path.basename(caminho))

                    ctk.CTkButton(linha_foto, text="📎 Anexar Foto (opcional)", width=170,
                                  fg_color="gray40", command=anexar).pack(side="left", padx=8)
                    ctk.CTkButton(
                        linha_foto, text="Remover", width=80, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.fotos_por_secao["sugestoes_melhorias"].pop(i), atualizar_lista()
                        ),
                    ).pack(side="right")
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_sugestao():
            self.fotos_por_secao["sugestoes_melhorias"].append(
                {"origem": None, "legenda_var": ctk.StringVar(value="")}
            )
            atualizar_lista()

        ctk.CTkButton(bloco, text="+ Adicionar Sugestão", width=170,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_sugestao).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

    def _coletar_ocorrencias_extras(self):
        return _coletar_ocorrencias(self.ocorrencias_extras)

    def _construir_bloco_ocorrencias(self, bloco):
        _construir_lista_ocorrencias(bloco, self.ocorrencias_extras,
                                     self._preservar_scroll, self._reconstruir_lista)

    def _criar_inversor_padrao(self):
        """Novo bloco de Inversor ('Inversor 01'...), com foto de etiqueta
        opcional e já com 1 String pronta para preencher."""
        inv = {
            "nome_var": ctk.StringVar(value=f"Inversor {len(self.inversores) + 1:02d}"),
            "foto_var": ctk.StringVar(value=""),
            "strings": [],
        }
        inv["strings"].append(self._criar_string_padrao(inv))
        return inv

    def _criar_string_padrao(self, inversor):
        """Retorna um novo bloco de String (dentro de `inversor`) com os 3
        testes vazios prontos para preenchimento — usado pelo botão
        '+ Adicionar String' e ao criar um inversor."""
        n = len(inversor["strings"]) + 1
        return {
            "nome_var": ctk.StringVar(value=f"String {n:02d}"),
            "vcc_var": ctk.StringVar(value=""),
            "pos_var": ctk.StringVar(value=""),
            "neg_var": ctk.StringVar(value=""),
            "neutro_var": ctk.StringVar(value=""),
            "status_tensao_var": ctk.StringVar(value="CONFORME"),
            "status_flut_pos_var": ctk.StringVar(value="CONFORME"),
            "status_flut_neg_var": ctk.StringVar(value="CONFORME"),
            "status_neutro_var": ctk.StringVar(value="CONFORME"),
        }

    def _construir_bloco_tabela(self, bloco):
        switch_neutro = ctk.CTkSwitch(
            bloco, text="⚡ Usina possui condutor Neutro (habilita Teste de Neutro)",
            variable=self.possui_neutro_var, progress_color=Marca.ACCENT,
            font=ctk.CTkFont(size=12), command=self._renderizar_secoes,
        )
        switch_neutro.pack(anchor="w", padx=14, pady=(0, 10))

        lista_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        lista_frame.pack(fill="x", padx=14, pady=(0, 6))

        @self._preservar_scroll
        def atualizar_lista():
            def criar():
                itens = []
                for idx_inv, inv in enumerate(self.inversores):
                    caixa_inv = ctk.CTkFrame(lista_frame, fg_color="transparent", height=1,
                                             border_width=1, border_color=Marca.ACCENT,
                                             corner_radius=10)
                    itens.append((caixa_inv, dict(fill="x", pady=6, ipady=6)))

                    # Cabeçalho do inversor: nome + 📷 (foto da etiqueta) + remover.
                    cab_inv = ctk.CTkFrame(caixa_inv, fg_color="transparent")
                    cab_inv.pack(fill="x", padx=8, pady=(6, 4))
                    ctk.CTkEntry(cab_inv, textvariable=inv["nome_var"], width=170,
                                 font=ctk.CTkFont(weight="bold")).pack(side="left")
                    _BotaoFotoCompacto(cab_inv, inv["foto_var"]).pack(side="left", padx=(8, 0))
                    ctk.CTkLabel(cab_inv, text="Foto da etiqueta", text_color="gray",
                                 font=ctk.CTkFont(size=11)).pack(side="left", padx=(6, 0))
                    ctk.CTkButton(
                        cab_inv, text="Remover Inversor", width=120, height=26,
                        fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx_inv: (self.inversores.pop(i), atualizar_lista()),
                    ).pack(side="right")

                    for idx, s in enumerate(inv["strings"]):
                        grupo = ctk.CTkFrame(caixa_inv, fg_color="transparent", height=1,
                                             border_width=1, border_color=Marca.CINZA_BORDA,
                                             corner_radius=8)
                        grupo.pack(fill="x", padx=10, pady=4, ipady=6)

                        cabecalho_grupo = ctk.CTkFrame(grupo, fg_color="transparent")
                        cabecalho_grupo.pack(fill="x", padx=8, pady=(4, 6))
                        ctk.CTkEntry(cabecalho_grupo, textvariable=s["nome_var"], width=160,
                                     font=ctk.CTkFont(weight="bold")).pack(side="left")
                        ctk.CTkButton(
                            cabecalho_grupo, text="Remover String", width=110, height=26,
                            fg_color=Marca.ERRO, hover_color=Marca.ERRO_HOVER,
                            command=lambda i=idx, lst=inv["strings"]: (lst.pop(i),
                                                                        atualizar_lista()),
                        ).pack(side="right")

                        parametros = [
                            ("tensao", s["vcc_var"]), ("flut_pos", s["pos_var"]),
                            ("flut_neg", s["neg_var"]),
                        ]
                        if self.possui_neutro_var.get():
                            parametros.append(("neutro", s["neutro_var"]))

                        for chave_param, var_valor in parametros:
                            sub_linha = ctk.CTkFrame(grupo, fg_color="transparent")
                            sub_linha.pack(fill="x", padx=8, pady=2)
                            ctk.CTkLabel(sub_linha, text=_STATUS_ROTULOS[chave_param], width=190,
                                         anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
                            ctk.CTkEntry(sub_linha, textvariable=var_valor, width=90,
                                         placeholder_text="Vcc").pack(side="left", padx=6)
                            self._seletor_status(sub_linha, s[f"status_{chave_param}_var"])

                    def adicionar_string(inv=inv):
                        inv["strings"].append(self._criar_string_padrao(inv))
                        atualizar_lista()

                    ctk.CTkButton(caixa_inv, text="+ Adicionar String", width=140,
                                  fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                                  command=adicionar_string
                                  ).pack(anchor="w", padx=10, pady=(2, 4))
                return itens
            self._reconstruir_lista(lista_frame, criar)

        def adicionar_inversor():
            self.inversores.append(self._criar_inversor_padrao())
            atualizar_lista()

        ctk.CTkButton(bloco, text="+ Adicionar Inversor", width=150,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_inversor).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_lista()

        # ---- Circuito de Corrente Alternada (CA): disjuntores ----
        # Cada disjuntor traz sua própria Corrente de Injeção (A) — o
        # campo global "Corrente de Injeção Total" foi removido.
        ctk.CTkLabel(
            bloco, text="Circuito de Corrente Alternada (CA) — opcional",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=Marca.PRIMARIA,
        ).pack(anchor="w", padx=14, pady=(4, 6))

        disjuntores_frame = ctk.CTkFrame(bloco, fg_color="transparent", height=1)
        disjuntores_frame.pack(fill="x", padx=14, pady=(0, 4))

        @self._preservar_scroll
        def atualizar_disjuntores():
            def criar():
                itens = []
                for idx, d in enumerate(self.disjuntores_rows):
                    grupo = ctk.CTkFrame(disjuntores_frame, fg_color="transparent", height=1,
                                          border_width=1, border_color=Marca.CINZA_BORDA,
                                          corner_radius=8)
                    itens.append((grupo, dict(fill="x", pady=4, ipady=6)))

                    # Topo: identificação + voltagem nominal + excluir — igual
                    # ao cabeçalho do bloco de String.
                    cabecalho_grupo = ctk.CTkFrame(grupo, fg_color="transparent")
                    cabecalho_grupo.pack(fill="x", padx=8, pady=(4, 6))
                    ctk.CTkEntry(cabecalho_grupo, textvariable=d["nome_var"], width=130,
                                 font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
                    ctk.CTkOptionMenu(cabecalho_grupo, values=_VOLTAGENS_DISJUNTOR, width=90,
                                      variable=d["voltagem_var"]).pack(side="left")
                    ctk.CTkComboBox(cabecalho_grupo, values=_TIPOS_DISJUNTOR, width=110,
                                    variable=d["tipo_var"], state="readonly"
                                    ).pack(side="left", padx=(6, 0))
                    ctk.CTkButton(
                        cabecalho_grupo, text="X", width=30, fg_color=Marca.ERRO,
                        hover_color=Marca.ERRO_HOVER,
                        command=lambda i=idx: (
                            self.disjuntores_rows.pop(i), atualizar_disjuntores()
                        ),
                    ).pack(side="right")

                    # 3 linhas individuais de medição, cada uma com seu próprio
                    # seletor Conforme/Não Conforme — mesmo padrão vertical do
                    # bloco de String (String Box CC).
                    medicoes = [
                        ("Tensão de Linha (V)", d["valor_var"], d["status_tensao_var"], "V"),
                        ("Tensão de Fase (V)", d["fase_var"], d["status_fase_var"], "V"),
                        ("Corrente de Injeção (A)", d["corrente_var"], d["status_corrente_var"], "A"),
                    ]

                    for rotulo_medicao, var_valor, var_status, unidade in medicoes:
                        sub_linha = ctk.CTkFrame(grupo, fg_color="transparent")
                        sub_linha.pack(fill="x", padx=8, pady=2)
                        ctk.CTkLabel(sub_linha, text=rotulo_medicao, width=190,
                                     anchor="w", font=ctk.CTkFont(size=11)).pack(side="left")
                        ctk.CTkEntry(sub_linha, textvariable=var_valor, width=90,
                                     placeholder_text=unidade).pack(side="left", padx=6)
                        self._seletor_status(sub_linha, var_status)
                return itens
            self._reconstruir_lista(disjuntores_frame, criar)

        def adicionar_disjuntor():
            n = len(self.disjuntores_rows) + 1
            self.disjuntores_rows.append({
                "nome_var": ctk.StringVar(value=f"Disjuntor {n:02d}"),
                "voltagem_var": ctk.StringVar(value="220V"),
                "tipo_var": ctk.StringVar(value=_TIPOS_DISJUNTOR[0]),
                "valor_var": ctk.StringVar(value=""),
                "corrente_var": ctk.StringVar(value=""),
                "fase_var": ctk.StringVar(value=""),
                "status_tensao_var": ctk.StringVar(value="CONFORME"),
                "status_corrente_var": ctk.StringVar(value="CONFORME"),
                "status_fase_var": ctk.StringVar(value="CONFORME"),
            })
            atualizar_disjuntores()

        ctk.CTkButton(bloco, text="+ Adicionar Disjuntor", width=150,
                      fg_color=Marca.ACCENT, hover_color=Marca.ACCENT_HOVER,
                      command=adicionar_disjuntor).pack(anchor="w", padx=14, pady=(0, 12))
        atualizar_disjuntores()

    def _seletor_status(self, parent, status_var):
        _criar_seletor_status(parent, status_var)

    # -------------------------------------------------------- ao exibir --
    def ao_exibir(self):
        with transicao_suave(self):
            self._empresas_cache = self.empresa_dao.listar()
            self._empresas_map = {e["nome"]: e["id"] for e in self._empresas_cache}
            self.combo_empresa.configure(values=list(self._empresas_map.keys()))
            self._atualizar_clientes_por_empresa(self.combo_empresa.get())
            self._recalcular_codigo()

    # ------------------------------------------------- editar existente --
    def carregar_relatorio_existente(self, relatorio_id) -> bool:
        """Abre o relatório para edição com fade-in curto. O alerta de erro
        fica FORA da transição (a janela nunca fica esmaecida sob o modal)."""
        with transicao_suave(self):
            ok = self._carregar_relatorio_existente(relatorio_id)
        if not ok:
            mostrar_alerta(self.winfo_toplevel(), "Relatório não encontrado",
                           "Não foi possível carregar o relatório selecionado.", "erro")
        return ok

    def _carregar_relatorio_existente(self, relatorio_id) -> bool:
        """Carrega um relatório salvo no formulário para EDIÇÃO: mantém o
        código original e já sobe a Revisão (01 -> 02). As fotos não são
        guardadas no banco (ficam só em pasta temporária), então precisam
        ser anexadas de novo. Chame a partir da tela de histórico/lista."""
        rel = self.relatorio_dao.buscar_por_id(relatorio_id)
        if not rel:
            return False

        # sem renderizar aqui: o redesenho único acontece no fim do método
        self._resetar_formulario(renderizar=False)   # limpa e sai do modo edição

        self._empresas_cache = self.empresa_dao.listar()
        self._empresas_map = {e["nome"]: e["id"] for e in self._empresas_cache}
        self.combo_empresa.configure(values=list(self._empresas_map.keys()))
        empresa = self.empresa_dao.buscar_por_id(rel["empresa_id"])
        cliente = self.cliente_dao.buscar_por_id(rel["cliente_id"])
        nome_empresa = empresa["nome"] if empresa else ""
        self.combo_empresa.set(nome_empresa)
        self._atualizar_clientes_por_empresa(nome_empresa)
        self.combo_cliente.set(cliente["nome_razao_social"] if cliente else "")

        try:
            self.data_servico_entry.set_date(
                datetime.strptime(rel.get("data_servico") or "", "%d/%m/%Y").date()
            )
        except ValueError:
            pass

        eh_troca = rel.get("tipo_relatorio") == "troca_microinversor"
        self.tipo_var.set(_TIPO_TROCA if eh_troca else _TIPO_LIMPEZA)
        self._aplicar_tipo(renderizar=False)
        for caixa, campo in ((self.txt_objetivo, "texto_objetivo"),
                             (self.txt_aplicacao, "texto_aplicacao"),
                             (self.txt_normas, "texto_normas")):
            caixa.delete("1.0", "end")
            caixa.insert("1.0", rel.get(campo) or "")

        secoes = [s for s in rel.get("secoes", []) if s in self.secoes_ativas_vars]
        self.ordem_secoes = secoes + [s for s in self.ordem_secoes if s not in secoes]
        for s in secoes:
            self.secoes_ativas_vars[s].set(True)

        strings = self.relatorio_dao.listar_strings(relatorio_id)
        disjuntores = self.relatorio_dao.listar_disjuntores(relatorio_id)
        self.inversores = self._inversores_de_registros(strings)
        self.disjuntores_rows = [self._disjuntor_de_registro(r) for r in disjuntores]
        self.possui_neutro_var.set(
            any(r.get("neutro_valor") is not None for r in strings)
        )

        # Modo edição: código original travado + REV incrementada.
        self._relatorio_editando_id = rel["id"]
        self._definir_codigo(rel["codigo"])
        self.entry_revisao.delete(0, "end")
        self.entry_revisao.insert(0, self._proxima_revisao(rel.get("revisao")))

        if eh_troca:
            self.form_troca.carregar(self.relatorio_dao.carregar_troca(relatorio_id))

        self._renderizar_secoes()
        return True

    @staticmethod
    def _inversores_de_registros(registros):
        """Reagrupa as strings salvas por inversor (ordem de aparição). Relatórios
        antigos, sem inversor gravado, viram um único 'Inversor 01'. A foto da
        etiqueta só volta se o arquivo ainda existir no disco."""
        grupos = {}
        for r in registros:
            nome = (r.get("inversor_nome") or "").strip() or "Inversor 01"
            foto = r.get("inversor_foto_path") or ""
            foto = foto if foto and os.path.exists(foto) else ""
            inv = grupos.get(nome)
            if inv is None:
                inv = grupos[nome] = {"nome_var": ctk.StringVar(value=nome),
                                      "foto_var": ctk.StringVar(value=foto),
                                      "strings": []}
            elif foto and not inv["foto_var"].get():
                inv["foto_var"].set(foto)
            inv["strings"].append(RelatorioView._string_de_registro(r))
        return list(grupos.values())

    @staticmethod
    def _string_de_registro(r):
        legado = r.get("status") or "CONFORME"
        return {
            "nome_var": ctk.StringVar(value=r.get("string_nome") or ""),
            "vcc_var": ctk.StringVar(value=_fmt_num(r.get("tensao_vcc"))),
            "pos_var": ctk.StringVar(value=_fmt_num(r.get("flutuacao_positivo"))),
            "neg_var": ctk.StringVar(value=_fmt_num(r.get("flutuacao_negativo"))),
            "neutro_var": ctk.StringVar(value=_fmt_num(r.get("neutro_valor"))),
            "status_tensao_var": ctk.StringVar(value=r.get("status_tensao") or legado),
            "status_flut_pos_var": ctk.StringVar(
                value=r.get("status_flutuacao_positivo") or legado),
            "status_flut_neg_var": ctk.StringVar(
                value=r.get("status_flutuacao_negativo") or legado),
            "status_neutro_var": ctk.StringVar(value=r.get("status_neutro") or "CONFORME"),
        }

    @staticmethod
    def _disjuntor_de_registro(r):
        return {
            "nome_var": ctk.StringVar(value=r.get("nome") or ""),
            "voltagem_var": ctk.StringVar(value=r.get("voltagem") or "220V"),
            "tipo_var": ctk.StringVar(value=r.get("tipo") or _TIPOS_DISJUNTOR[0]),
            "valor_var": ctk.StringVar(value=_fmt_num(r.get("valor_medido"))),
            "corrente_var": ctk.StringVar(value=_fmt_num(r.get("corrente_injecao_valor"))),
            "fase_var": ctk.StringVar(value=_fmt_num(r.get("neutro_valor"))),
            "status_tensao_var": ctk.StringVar(value=r.get("status") or "CONFORME"),
            "status_corrente_var": ctk.StringVar(
                value=r.get("corrente_injecao_status") or "CONFORME"),
            "status_fase_var": ctk.StringVar(value=r.get("status_neutro") or "CONFORME"),
        }

    # ------------------------------------------------------------ gerar --
    def _gerar_relatorio(self):
        if self.tipo_var.get() == _TIPO_TROCA:
            return self._gerar_relatorio_troca()
        nome_empresa = self.combo_empresa.get()
        nome_cliente = self.combo_cliente.get()
        empresa_id = self._empresas_map.get(nome_empresa)
        cliente_id = self._clientes_map.get(nome_cliente)

        if not empresa_id or not cliente_id:
            mostrar_alerta(self.winfo_toplevel(), "Campos obrigatórios",
                            "Selecione a Empresa e o Cliente do relatório.", "aviso")
            return

        secoes_selecionadas = [
            s for s in self.ordem_secoes if self.secoes_ativas_vars[s].get()
        ]
        if not secoes_selecionadas:
            mostrar_alerta(self.winfo_toplevel(), "Nenhuma seção selecionada",
                            "Ative ao menos uma seção para incluir no relatório.", "aviso")
            return

        empresa = self.empresa_dao.buscar_por_id(empresa_id)
        cliente = self.cliente_dao.buscar_por_id(cliente_id)
        codigo = self.entry_codigo.get().strip()
        if self._relatorio_editando_id is None:
            # Relatório novo: garante um código livre no momento de gravar.
            # (Se o código já pertence a um relatório com PDF gerado, pega o
            # próximo; se for sobra de uma tentativa que falhou, reaproveita.)
            existente = self.relatorio_dao.buscar_por_codigo(codigo) if codigo else None
            if not codigo or (existente and existente.get("pdf_path")):
                codigo = self.relatorio_dao.obter_proximo_codigo_relatorio(
                    self.data_servico_entry.get()
                )
                self._definir_codigo(codigo)

        dados_relatorio = {
            "codigo": codigo,
            "empresa_id": empresa_id,
            "cliente_id": cliente_id,
            "data_servico": self.data_servico_entry.get(),
            "responsavel_tecnico": empresa.get("responsavel_tecnico", ""),
            "revisao": self.entry_revisao.get().strip() or "01",
            "texto_objetivo": self.txt_objetivo.get("1.0", "end").strip(),
            "texto_aplicacao": self.txt_aplicacao.get("1.0", "end").strip(),
            "texto_normas": self.txt_normas.get("1.0", "end").strip(),
            "secoes": secoes_selecionadas,
        }

        # INSERT se o código é novo; UPDATE (com a nova REV) se já existe.
        relatorio_id = self.relatorio_dao.salvar(dados_relatorio)

        # Armazenamento leve: as fotos do relatório são processadas em uma
        # pasta TEMPORÁRIA (fora de data/fotos) e são apagadas assim que o
        # PDF é compilado — nenhuma cópia permanente fica no disco, e os
        # caminhos não são persistidos em relatorio_fotos (só o .pdf final
        # sobrevive na pasta do cliente).
        pasta_temp = criar_pasta_temporaria()

        # Garante que as legendas do PDF == as da tela (numeração sequencial).
        self._reindexar_figuras()

        fotos_por_secao_final = {}
        for chave in _SECOES_FOTO:
            if chave not in secoes_selecionadas:
                continue
            registros = []
            for ordem, foto in enumerate(self.fotos_por_secao[chave]):
                legenda = foto["legenda_var"].get()
                origem = foto.get("origem")
                if not origem:
                    # Sugestões de Melhorias aceita entradas só-texto (sem
                    # foto); outras seções simplesmente ignoram o slot
                    # vazio (ex.: gráfico do comparativo não selecionado).
                    if chave == "sugestoes_melhorias" and legenda.strip():
                        registros.append({"foto_path": None, "legenda": legenda})
                    continue
                caminho_temp = salvar_foto_temporaria(origem, pasta_temp)
                registros.append({"foto_path": caminho_temp, "legenda": legenda})
            fotos_por_secao_final[chave] = registros

        strings_data = []
        disjuntores_data = []
        possui_neutro = self.possui_neutro_var.get()
        if _SECAO_TABELA in secoes_selecionadas:
            ordem = 0
            for n_inv, inv in enumerate(self.inversores, start=1):
                nome_inv = inv["nome_var"].get().strip() or f"Inversor {n_inv:02d}"
                origem_foto = inv["foto_var"].get()
                if origem_foto and not os.path.exists(origem_foto):
                    origem_foto = ""
                foto_pdf = (salvar_foto_temporaria(origem_foto, pasta_temp)
                            if origem_foto else None)
                for s in inv["strings"]:
                    vcc = _to_float(s["vcc_var"].get())
                    pos = _to_float(s["pos_var"].get())
                    neg = _to_float(s["neg_var"].get())
                    status_tensao = s["status_tensao_var"].get()
                    status_flut_pos = s["status_flut_pos_var"].get()
                    status_flut_neg = s["status_flut_neg_var"].get()
                    neutro = _to_float(s["neutro_var"].get()) if possui_neutro else None
                    status_neutro = s["status_neutro_var"].get()
                    self.relatorio_dao.adicionar_string(
                        relatorio_id, s["nome_var"].get(), vcc, pos, neg,
                        status_tensao, status_flut_pos, status_flut_neg, ordem,
                        neutro, status_neutro,
                        inversor_nome=nome_inv, inversor_foto_path=origem_foto or None,
                    )
                    ordem += 1
                    strings_data.append({
                        "string_nome": s["nome_var"].get(), "tensao_vcc": vcc,
                        "flutuacao_positivo": pos, "flutuacao_negativo": neg,
                        "status_tensao": status_tensao,
                        "status_flutuacao_positivo": status_flut_pos,
                        "status_flutuacao_negativo": status_flut_neg,
                        "neutro_valor": neutro, "status_neutro": status_neutro,
                        "inversor_nome": nome_inv, "inversor_foto_path": foto_pdf,
                    })

            for ordem, d in enumerate(self.disjuntores_rows):
                valor = _to_float(d["valor_var"].get())
                fase = _to_float(d["fase_var"].get())
                corrente = _to_float(d["corrente_var"].get())
                if valor is None and fase is None and corrente is None:
                    continue  # disjuntor totalmente vazio, ignora
                nome = d["nome_var"].get()
                voltagem = d["voltagem_var"].get()
                status_tensao_disj = d["status_tensao_var"].get()
                status_corrente_disj = d["status_corrente_var"].get()
                tipo = d["tipo_var"].get() or _TIPOS_DISJUNTOR[0]
                status_fase_disj = d["status_fase_var"].get()
                self.relatorio_dao.adicionar_disjuntor(
                    relatorio_id, nome, voltagem, valor, status_tensao_disj, ordem,
                    corrente, status_corrente_disj, fase, status_fase_disj, tipo,
                )
                disjuntores_data.append({
                    "nome": nome, "voltagem": voltagem,
                    "valor_medido": valor, "status": status_tensao_disj,
                    "corrente_injecao_valor": corrente,
                    "corrente_injecao_status": status_corrente_disj,
                    "neutro_valor": fase, "status_neutro": status_fase_disj,
                    "tipo": tipo,
                    # aliases legíveis para o gerador de PDF
                    "tensao_linha_valor": valor, "tensao_linha_status": status_tensao_disj,
                    "tensao_fase_valor": fase, "tensao_fase_status": status_fase_disj,
                })

        # Estrutura: [COD_EMPRESA] - [NOME_EMPRESA] / [COD_CLIENTE] - [NOME_CLIENTE]
        # / Relatórios / RELATORIO LIMPEZA / [codigo].pdf
        caminho_pdf = self._caminho_pdf(empresa, cliente, codigo,
                                        SUBPASTA_RELATORIO_LIMPEZA)

        try:
            # Ocorrências Extras: cópia temporária de cada foto + lista nos dados
            # do relatório (só para o PDF; dados_relatorio já foi salvo acima).
            ocorrencias_pdf = []
            if _SECAO_OCORRENCIAS in secoes_selecionadas:
                for oc in self._coletar_ocorrencias_extras():
                    ocorrencias_pdf.append({
                        "titulo": oc["titulo"], "descricao": oc["descricao"],
                        "fotos": [{"foto_path": salvar_foto_temporaria(f["origem"], pasta_temp),
                                   "legenda": f["legenda"]}
                                  for f in oc["fotos"]
                                  if f.get("origem") and os.path.exists(f["origem"])],
                    })
            # Até 3 tentativas (500 ms): o disco/subpasta pode ainda estar
            # voltando logo após acordar da hibernação/suspensão.
            executar_com_retry(
                gerar_relatorio_pdf,
                caminho_pdf, empresa, cliente,
                {**dados_relatorio, "ocorrencias_extras": ocorrencias_pdf},
                secoes_selecionadas, fotos_por_secao_final, strings_data,
                disjuntores_data,
            )
            self.relatorio_dao.atualizar_pdf_path(relatorio_id, caminho_pdf)
        except Exception as exc:
            mostrar_alerta(self.winfo_toplevel(), "Erro ao gerar PDF", str(exc), "erro")
            return
        finally:
            # As fotos temporárias somem do disco aqui, sucesso ou falha —
            # só o .pdf final (se gerado) permanece na pasta do cliente.
            limpar_pasta_temporaria(pasta_temp)

        mostrar_alerta(
            self.winfo_toplevel(), "Relatório gerado",
            f"Relatório {codigo} gerado com sucesso em:\n{caminho_pdf}", "sucesso",
        )
        self._resetar_formulario()

    # --------------------------------- tipo de relatório / troca de micro --
    def _on_tipo_relatorio(self, _valor=None):
        self._aplicar_tipo()

    def _aplicar_tipo(self, renderizar=True):
        """Troca o tipo de relatório mantendo a MESMA estrutura (cabeçalho,
        textos pré-definidos, cards com switch e setas ▲▼, botão de gerar):
        carrega os textos padrão do tipo e redesenha as seções dele."""
        with transicao_suave(self):
            self._aplicar_textos_padrao(self.tipo_var.get())
            if renderizar:
                self._renderizar_secoes()

    def _aplicar_textos_padrao(self, tipo):
        """Troca Objetivo/Aplicação/Normas pelo padrão do tipo escolhido, mas só
        nas caixas vazias ou ainda iguais ao padrão do outro tipo (texto que o
        usuário editou nunca é sobrescrito)."""
        padroes = {_TIPO_LIMPEZA: TEXTOS_LIMPEZA_PADRAO, _TIPO_TROCA: TEXTOS_TROCA_PADRAO}
        anteriores = padroes[_TIPO_LIMPEZA if tipo == _TIPO_TROCA else _TIPO_TROCA]
        for caixa, antigo, novo in zip(
                (self.txt_objetivo, self.txt_aplicacao, self.txt_normas),
                anteriores, padroes[tipo]):
            atual = caixa.get("1.0", "end").strip()
            if not atual or atual == antigo.strip():
                caixa.delete("1.0", "end")
                caixa.insert("1.0", novo)

    def _caminho_pdf(self, empresa, cliente, codigo, subpasta):
        """[raiz]/[EMPRESA]/[CLIENTE]/Relatórios/[subpasta do tipo]/[codigo].pdf —
        a subpasta é criada se não existir (o código do relatório não é alterado)."""
        pasta_raiz = self.config_dao.obter_pasta_relatorios()
        nome_pasta_empresa = f"{EmpresaDAO.codigo_exibicao(empresa)} - {empresa['nome']}"
        nome_pasta_cliente = (f"{ClienteDAO.codigo_exibicao(cliente)} - "
                              f"{cliente['nome_razao_social']}")
        pasta = os.path.join(pasta_raiz, _sanitizar(nome_pasta_empresa),
                             _sanitizar(nome_pasta_cliente), PASTA_RELATORIOS_CLIENTE,
                             subpasta)
        # Subpasta pode demorar a ficar disponível logo após acordar do PC.
        executar_com_retry(os.makedirs, pasta, exist_ok=True)
        return os.path.join(pasta, f"{codigo}.pdf")

    def _gerar_relatorio_troca(self):
        empresa_id = self._empresas_map.get(self.combo_empresa.get())
        cliente_id = self._clientes_map.get(self.combo_cliente.get())
        if not empresa_id or not cliente_id:
            mostrar_alerta(self.winfo_toplevel(), "Campos obrigatórios",
                           "Selecione a Empresa e o Cliente do relatório.", "aviso")
            return
        secoes_selecionadas = [s for s in self.ordem_secoes
                               if self.secoes_ativas_vars[s].get()]
        if not secoes_selecionadas:
            mostrar_alerta(self.winfo_toplevel(), "Nenhuma seção selecionada",
                           "Ative ao menos uma seção para incluir no relatório.", "aviso")
            return
        dados_form = self.form_troca.coletar()

        empresa = self.empresa_dao.buscar_por_id(empresa_id)
        cliente = self.cliente_dao.buscar_por_id(cliente_id)
        codigo = self.entry_codigo.get().strip()
        if self._relatorio_editando_id is None:
            existente = self.relatorio_dao.buscar_por_codigo(codigo) if codigo else None
            if not codigo or (existente and existente.get("pdf_path")):
                codigo = self.relatorio_dao.obter_proximo_codigo_relatorio(
                    self.data_servico_entry.get())
                self._definir_codigo(codigo)

        dados_relatorio = {
            "codigo": codigo, "empresa_id": empresa_id, "cliente_id": cliente_id,
            "data_servico": self.data_servico_entry.get(),
            "responsavel_tecnico": empresa.get("responsavel_tecnico", ""),
            "revisao": self.entry_revisao.get().strip() or "01",
            "texto_objetivo": self.txt_objetivo.get("1.0", "end").strip(),
            "texto_aplicacao": self.txt_aplicacao.get("1.0", "end").strip(),
            "texto_normas": self.txt_normas.get("1.0", "end").strip(),
            "secoes": secoes_selecionadas,
        }
        relatorio_id = self.relatorio_dao.salvar_troca(dados_relatorio, dados_form)
        caminho_pdf = self._caminho_pdf(empresa, cliente, codigo,
                                        SUBPASTA_RELATORIO_TROCA)

        pasta_temp = criar_pasta_temporaria()
        try:
            troca_pdf = self.form_troca.para_pdf(
                dados_form, lambda origem: salvar_foto_temporaria(origem, pasta_temp))
            executar_com_retry(gerar_relatorio_troca_pdf, caminho_pdf, empresa,
                               cliente, dados_relatorio, troca_pdf,
                               secoes_selecionadas)
            self.relatorio_dao.atualizar_pdf_path(relatorio_id, caminho_pdf)
        except Exception as exc:
            mostrar_alerta(self.winfo_toplevel(), "Erro ao gerar PDF", str(exc), "erro")
            return
        finally:
            limpar_pasta_temporaria(pasta_temp)

        mostrar_alerta(self.winfo_toplevel(), "Relatório gerado",
                       f"Relatório {codigo} gerado com sucesso em:\n{caminho_pdf}", "sucesso")
        self._resetar_formulario()

    def _resetar_formulario(self, renderizar=True):
        with transicao_suave(self):
            self.form_troca.limpar()
            self.fotos_por_secao = {s: [] for s in _SECOES_FOTO}
            self.inversores = []
            self.disjuntores_rows = []
            self.possui_neutro_var.set(False)
            self.ocorrencias_extras = []
            for var in list(self._vars_limpeza.values()) + list(self._vars_troca.values()):
                var.set(False)
            self.entry_revisao.delete(0, "end")
            self.entry_revisao.insert(0, "01")
            if renderizar:
                self._renderizar_secoes()
            self._relatorio_editando_id = None
            self._recalcular_codigo()


def _fmt_num(valor):
    """Número do banco -> texto do campo (None -> vazio; 281.0 -> '281')."""
    if valor is None:
        return ""
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    return str(int(f)) if f == int(f) else str(f).replace(".", ",")


def _to_float(valor):
    """Converte texto de campo numérico em float; devolve None se vazio/inválido.

    Aceita espaços (inclusive não separáveis), vírgula decimal e separador de
    milhar ('1.234,5' -> 1234.5). Rejeita NaN e infinito.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor) if math.isfinite(valor) else None

    texto = re.sub(r"\s+", "", str(valor))  # \s cobre espaço, tab e \u00a0
    if not texto:
        return None

    if "," in texto:
        # Vírgula é o decimal; pontos antes dela são separador de milhar.
        texto = texto.replace(".", "").replace(",", ".")

    try:
        numero = float(texto)
    except ValueError:
        return None
    return numero if math.isfinite(numero) else None


def _to_float_medicao(valor):
    """Como _to_float, mas tolera unidade/texto junto do número ('220 V',
    '220V', '~220,5'): sem isso a medição virava None e saía '—' no PDF."""
    numero = _to_float(valor)
    if numero is not None:
        return numero
    achado = re.search(r"-?\d[\d.,]*", str(valor if valor is not None else ""))
    return _to_float(achado.group(0).rstrip(".,")) if achado else None


def _sanitizar(nome: str) -> str:
    """Remove caracteres inválidos para nomes de pasta em Windows/Linux/Mac."""
    invalidos = '<>:"/\\|?*'
    for c in invalidos:
        nome = nome.replace(c, "-")
    return nome.strip() or "sem_nome"
