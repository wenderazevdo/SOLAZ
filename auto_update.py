"""
Atualização automática do SOLAZ via GitHub Releases.

Fluxo: consulta a última release -> compara com config.APP_VERSION -> se houver
versão nova, mostra uma janela com as novidades -> "Atualizar agora" baixa o
instalador (.exe) anexado à release, confere tamanho/integridade, executa o
instalador no modo silencioso do Inno Setup e fecha o app para o instalador
poder substituir os arquivos (o instalador reabre o SOLAZ ao terminar).

Requisitos:
  * a release do GitHub precisa ter o instalador .exe ANEXADO (de preferência
    com "Setup" no nome, ex.: SolazApp_Setup_1.1.1.exe);
  * o repositório precisa ser PÚBLICO (a consulta é anônima);
  * o .iss deve manter o mesmo AppId e, em [Run], abrir o app SEM o flag
    "skipifsilent" (ver orientações na conversa).

As partes de rede/arquivo não dependem da interface (dá para testar sozinhas);
customtkinter só é importado quando a janela é aberta.
"""
import hashlib
import logging
import os
import re
import sys
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from config import APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME

_log = logging.getLogger("solaz.update")

_API_ULTIMA_RELEASE = (
    f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"
)
# Só baixamos de dentro das releases DESTE repositório.
_PREFIXO_DOWNLOAD = (
    f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/download/"
)
_TIMEOUT_API = 8          # segundos
_TIMEOUT_DOWNLOAD = 30    # segundos sem receber dados
# Inno Setup: janela de progresso simples, sem perguntas, sem reiniciar o Windows,
# fechando o SOLAZ se ainda estiver aberto.
_ARGS_INSTALADOR = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


class AtualizacaoErro(Exception):
    """Falha previsível do processo de atualização (mensagem já amigável)."""


@dataclass
class InfoAtualizacao:
    versao: str            # ex.: "1.1.1"
    tag: str               # ex.: "v1.1.1"
    url_pagina: str        # página da release no GitHub
    nome_arquivo: str      # "" se a release não tiver instalador anexado
    url_download: str
    tamanho: int
    sha256: str            # "" se o GitHub não informar
    notas: str


@dataclass
class ResultadoVerificacao:
    disponivel: bool = False
    info: Optional[InfoAtualizacao] = None
    erro: Optional[str] = None


# ---------------------------------------------------------------- versões --
def _versao_tupla(texto: str) -> tuple:
    numeros = [int(n) for n in re.findall(r"\d+", texto or "")][:4]
    return tuple(numeros + [0] * (4 - len(numeros)))


def _escolher_instalador(assets: list) -> Optional[dict]:
    """Prefere um .exe com 'setup' no nome; senão, qualquer .exe."""
    exes = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    for a in exes:
        if "setup" in a["name"].lower():
            return a
    return exes[0] if exes else None


# ------------------------------------------------------------ verificação --
def verificar_atualizacao() -> ResultadoVerificacao:
    """Consulta a última release. NUNCA levanta exceção."""
    try:
        resp = requests.get(
            _API_ULTIMA_RELEASE,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "SolazApp-Updater"},
            timeout=_TIMEOUT_API,
        )
        if resp.status_code == 404:
            return ResultadoVerificacao(
                erro="Nenhuma versão publicada foi encontrada (ou o repositório é privado)."
            )
        resp.raise_for_status()
        dados = resp.json()

        tag = str(dados.get("tag_name", ""))
        if _versao_tupla(tag) <= _versao_tupla(APP_VERSION):
            return ResultadoVerificacao()          # já está na versão mais recente

        asset = _escolher_instalador(dados.get("assets") or [])
        digest = str((asset or {}).get("digest") or "")
        info = InfoAtualizacao(
            versao=tag.lstrip("vV"),
            tag=tag,
            url_pagina=str(dados.get("html_url", "")),
            nome_arquivo=str((asset or {}).get("name", "")),
            url_download=str((asset or {}).get("browser_download_url", "")),
            tamanho=int((asset or {}).get("size") or 0),
            sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
            notas=str(dados.get("body") or ""),
        )
        return ResultadoVerificacao(disponivel=True, info=info)
    except requests.RequestException:
        return ResultadoVerificacao(
            erro="Não foi possível consultar as atualizações. Verifique sua internet."
        )
    except Exception:                                 # noqa: BLE001
        _log.exception("Falha inesperada ao verificar atualização")
        return ResultadoVerificacao(erro="Não foi possível verificar as atualizações.")


# --------------------------------------------------------------- download --
def _apagar(caminho: str):
    try:
        os.remove(caminho)
    except OSError:
        pass


def baixar_instalador(info: InfoAtualizacao,
                      progresso: Optional[Callable[[int, int], None]] = None) -> str:
    """Baixa o instalador para a pasta temporária e devolve o caminho.
    Confere origem, tamanho, SHA-256 (quando o GitHub informa) e se é um
    executável do Windows. Levanta AtualizacaoErro com mensagem amigável."""
    if not info.url_download:
        raise AtualizacaoErro("Esta versão não tem instalador anexado na release.")
    if not info.url_download.startswith(_PREFIXO_DOWNLOAD):
        raise AtualizacaoErro("Endereço de download não reconhecido; atualização cancelada.")

    pasta = os.path.join(tempfile.gettempdir(), "SolazApp_update")
    destino = os.path.join(pasta, os.path.basename(info.nome_arquivo))
    parcial = destino + ".part"
    sha = hashlib.sha256()
    baixado = 0
    try:
        os.makedirs(pasta, exist_ok=True)
        with requests.get(info.url_download, stream=True, timeout=_TIMEOUT_DOWNLOAD) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or info.tamanho or 0)
            with open(parcial, "wb") as arq:
                for bloco in resp.iter_content(chunk_size=256 * 1024):
                    if not bloco:
                        continue
                    arq.write(bloco)
                    sha.update(bloco)
                    baixado += len(bloco)
                    if progresso:
                        progresso(baixado, total)
    except (requests.RequestException, OSError) as exc:
        _apagar(parcial)
        _log.warning("Falha no download da atualização: %r", exc)
        raise AtualizacaoErro("Falha ao baixar a atualização. Tente novamente.") from exc

    if info.tamanho and baixado != info.tamanho:
        _apagar(parcial)
        raise AtualizacaoErro("O download veio incompleto. Tente novamente.")
    if info.sha256 and sha.hexdigest().lower() != info.sha256.lower():
        _apagar(parcial)
        raise AtualizacaoErro("A verificação de integridade do arquivo falhou. Atualização cancelada.")
    try:
        with open(parcial, "rb") as arq:
            cabecalho = arq.read(2)
    except OSError as exc:
        raise AtualizacaoErro("Não foi possível ler o arquivo baixado.") from exc
    if cabecalho != b"MZ":
        _apagar(parcial)
        raise AtualizacaoErro("O arquivo baixado não é um instalador válido.")

    os.replace(parcial, destino)
    return destino


# ------------------------------------------------------------- instalação --
def iniciar_instalador(caminho: str) -> None:
    """Executa o instalador (o Windows mostra o pedido de permissão do
    administrador). Levanta AtualizacaoErro se for cancelado ou falhar."""
    if sys.platform != "win32":
        raise AtualizacaoErro("A instalação automática só funciona no Windows.")
    import ctypes

    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "open", caminho, " ".join(_ARGS_INSTALADOR), os.path.dirname(caminho), 1
    )
    if ret <= 32:    # <= 32 = erro (inclui o usuário recusar a permissão de administrador)
        raise AtualizacaoErro("A instalação foi cancelada ou não pôde ser iniciada.")


def _fechar_app(janela) -> None:
    """Fecha o app pelo mesmo caminho do botão X (main.py: _encerrar), para
    parar o bot, encerrar a sessão e liberar a trava de instância única."""
    janela = janela.winfo_toplevel()
    try:
        comando = janela.protocol("WM_DELETE_WINDOW")
        if comando:
            janela.tk.call(comando)
            return
    except Exception:                                 # noqa: BLE001
        pass
    try:
        janela.destroy()
    except Exception:                                 # noqa: BLE001
        pass


# ---------------------------------------------------------------- interface --
_dialogo_aberto = False


def mostrar_dialogo_atualizacao(parent, info: InfoAtualizacao,
                                ao_sair: Optional[Callable[[], None]] = None) -> None:
    """Janela 'Nova versão disponível' com as novidades e o botão Atualizar agora."""
    global _dialogo_aberto
    if _dialogo_aberto:
        return
    import webbrowser
    import customtkinter as ctk
    from config import Marca

    _dialogo_aberto = True
    dlg = ctk.CTkToplevel(parent)
    dlg.title("Nova versão disponível")
    dlg.geometry("500x440")
    dlg.resizable(False, False)
    try:
        dlg.transient(parent.winfo_toplevel())
    except Exception:                                 # noqa: BLE001
        pass
    dlg.after(200, lambda: dlg.winfo_exists() and dlg.focus_force())

    def fechar():
        global _dialogo_aberto
        _dialogo_aberto = False
        if dlg.winfo_exists():
            dlg.destroy()

    dlg.protocol("WM_DELETE_WINDOW", fechar)

    botoes = ctk.CTkFrame(dlg, fg_color="transparent")
    botoes.pack(side="bottom", pady=(8, 18))

    ctk.CTkLabel(dlg, text="Nova versão disponível",
                 font=ctk.CTkFont(size=18, weight="bold"),
                 text_color=Marca.ACCENT).pack(pady=(20, 2))
    ctk.CTkLabel(dlg, text=f"SOLAZ {info.versao}   (você está na {APP_VERSION})",
                 font=ctk.CTkFont(size=12)).pack()

    caixa = ctk.CTkTextbox(dlg, width=440, height=170)
    caixa.pack(padx=20, pady=(12, 8))
    caixa.insert("1.0", (info.notas or "Sem notas de versão.").strip()[:3000])
    caixa.configure(state="disabled")

    status = ctk.CTkLabel(dlg, text="", text_color="gray", font=ctk.CTkFont(size=11),
                          wraplength=440, justify="center")
    status.pack()
    barra = ctk.CTkProgressBar(dlg, width=440)
    barra.set(0)

    btn_depois = ctk.CTkButton(botoes, text="Depois", width=130, fg_color="gray40",
                               command=fechar)
    btn_depois.pack(side="right", padx=6)

    if not info.url_download:
        # Release sem instalador anexado: oferece abrir a página para baixar à mão.
        status.configure(text="Esta versão ainda não tem instalador anexado.")
        ctk.CTkButton(botoes, text="Abrir página de download", width=190,
                      fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
                      command=lambda: webbrowser.open(info.url_pagina)).pack(side="right", padx=6)
        return

    def atualizar():
        btn_atualizar.configure(state="disabled", text="Baixando...")
        btn_depois.configure(state="disabled")
        status.configure(text="Baixando a atualização...", text_color="gray")
        barra.pack(pady=(4, 0))
        estado = {"baixado": 0, "total": info.tamanho, "pronto": False, "erro": None, "caminho": None}

        def ao_progredir(baixado, total):
            estado["baixado"] = baixado
            estado["total"] = total or estado["total"]

        def trabalho():
            try:
                estado["caminho"] = baixar_instalador(info, ao_progredir)
            except AtualizacaoErro as exc:
                estado["erro"] = str(exc)
            except Exception:                         # noqa: BLE001
                _log.exception("Falha inesperada no download da atualização")
                estado["erro"] = "Falha inesperada ao baixar a atualização."
            estado["pronto"] = True

        threading.Thread(target=trabalho, name="solaz-update", daemon=True).start()

        def acompanhar():
            if not dlg.winfo_exists():
                return
            total = estado["total"]
            if total:
                barra.set(min(1.0, estado["baixado"] / total))
                status.configure(
                    text=f"Baixando... {estado['baixado'] / 1e6:.1f} de {total / 1e6:.1f} MB")
            if not estado["pronto"]:
                dlg.after(150, acompanhar)
                return
            if estado["erro"]:
                status.configure(text=estado["erro"], text_color=Marca.ERRO)
                btn_atualizar.configure(state="normal", text="Tentar novamente")
                btn_depois.configure(state="normal")
                return
            status.configure(text="Iniciando a instalação... o SOLAZ será fechado e reaberto.")
            dlg.update_idletasks()
            try:
                iniciar_instalador(estado["caminho"])
            except AtualizacaoErro as exc:
                status.configure(text=str(exc), text_color=Marca.ERRO)
                btn_atualizar.configure(state="normal", text="Tentar novamente")
                btn_depois.configure(state="normal")
                return
            (ao_sair or (lambda: _fechar_app(parent)))()

        dlg.after(150, acompanhar)

    btn_atualizar = ctk.CTkButton(botoes, text="Atualizar agora", width=150,
                                  fg_color=Marca.PRIMARIA, hover_color=Marca.PRIMARIA_CLARA,
                                  command=atualizar)
    btn_atualizar.pack(side="right", padx=6)


def verificar_e_perguntar(parent, silencioso: bool = False,
                          ao_sair: Optional[Callable[[], None]] = None) -> None:
    """Verifica em segundo plano (a janela não trava) e, se houver versão nova,
    abre o diálogo de atualização.
      silencioso=True  -> usar ao abrir o app: só aparece algo se houver versão nova;
      silencioso=False -> usar no botão 'Verificar Atualizações': também avisa
                          quando já está atualizado ou quando dá erro."""
    caixa = {}

    def trabalho():
        caixa["res"] = verificar_atualizacao()

    threading.Thread(target=trabalho, name="solaz-update-check", daemon=True).start()

    def conferir():
        try:
            if not parent.winfo_exists():
                return
        except Exception:                             # noqa: BLE001
            return
        if "res" not in caixa:
            parent.after(150, conferir)
            return
        res = caixa["res"]
        if res.disponivel and res.info:
            mostrar_dialogo_atualizacao(parent, res.info, ao_sair)
        elif not silencioso:
            from tkinter import messagebox
            if res.erro:
                messagebox.showerror("Atualizações", res.erro, parent=parent.winfo_toplevel())
            else:
                messagebox.showinfo(
                    "Atualizações",
                    f"Você já está usando a versão mais recente ({APP_VERSION}).",
                    parent=parent.winfo_toplevel(),
                )

    parent.after(150, conferir)
