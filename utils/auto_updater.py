"""Atualização automática via GitHub Releases (repositório definido em config.py).

Fluxo:
  1. verificar()  -> consulta /releases/latest e compara com APP_VERSION;
  2. baixar()     -> baixa o .exe da release para a pasta temporária, com
                     progresso, cancelamento e verificação de integridade;
  3. aplicar()    -> grava um .bat auxiliar que espera o app fechar, troca o
                     executável (ou roda o instalador) e reabre o programa.

Segurança dos dados: o atualizador NUNCA mexe na pasta de dados (banco,
configurações, relatórios). Só o executável do programa é substituído, e o
backup do banco (rotina_backup_banco) é feito antes de baixar.

Convenção da release no GitHub (tag maior que APP_VERSION, ex.: v1.2.0):
  * anexar o executável .exe do programa (substitui o .exe atual); ou
  * anexar um instalador cujo nome tenha "setup", "install" ou "instalador"
    (ex.: SolazSetup.exe) — é executado em modo /SILENT (padrão Inno Setup).
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from config import APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME

log = logging.getLogger(__name__)

_TIMEOUT_S = 20
_CHUNK = 64 * 1024
_HOSTS_PERMITIDOS = ("github.com", "githubusercontent.com")   # só baixa daqui
_USER_AGENT = "SOLAZ-AutoUpdater"
_PASTA_TEMP = os.path.join(tempfile.gettempdir(), "solaz_update")
_VAR_MODO_TESTE = "SOLAZ_UPDATE_TESTE"   # =1: baixa e valida, mas não aplica (p/ testar fora do .exe)


class ErroAtualizacao(Exception):
    """Falha esperada (rede, release sem arquivo, checksum...) com mensagem para o usuário."""


class DownloadCancelado(ErroAtualizacao):
    pass


@dataclass
class InfoAtualizacao:
    versao_instalada: str
    versao_remota: str
    tem_nova: bool
    url_pagina: str = ""
    asset_nome: str = ""
    asset_url: str = ""
    asset_tamanho: int = 0
    sha256: str = ""            # vem do campo "digest" do GitHub, se existir
    sha256_url: str = ""        # ou de um arquivo <nome>.sha256 anexado à release
    eh_instalador: bool = False


# ------------------------------------------------------------ utilidades --
def esta_empacotado() -> bool:
    """True quando rodando como .exe (PyInstaller); False rodando do código-fonte."""
    return bool(getattr(sys, "frozen", False))


def atualizacao_automatica_disponivel() -> bool:
    return esta_empacotado() or os.environ.get(_VAR_MODO_TESTE) == "1"


def _versao_tupla(texto: str) -> tuple:
    numeros = [int(n) for n in re.findall(r"\d+", texto or "")][:4]
    return tuple(numeros + [0] * (4 - len(numeros)))


def _checar_host(url: str):
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme != "https" or not any(
            host == h or host.endswith("." + h) for h in _HOSTS_PERMITIDOS):
        raise ErroAtualizacao("Endereço de download não confiável; atualização cancelada.")


def _abrir(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json, */*"})
    return urllib.request.urlopen(req, timeout=_TIMEOUT_S)


def _get_json(url: str) -> dict:
    try:
        with _abrir(url) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ErroAtualizacao("Nenhuma versão publicada no GitHub ainda.") from exc
        if exc.code in (403, 429):
            raise ErroAtualizacao("Limite de consultas do GitHub atingido. Tente em alguns minutos.") from exc
        raise ErroAtualizacao(f"O GitHub respondeu com erro {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ErroAtualizacao("Sem conexão com o GitHub. Verifique a internet.") from exc
    except ValueError as exc:
        raise ErroAtualizacao("Resposta inválida do GitHub.") from exc


def _escolher_asset(assets: list):
    """(asset, eh_instalador). Instalador (setup/install) tem preferência; senão
    o .exe de mesmo nome do executável atual; senão o primeiro .exe."""
    exes = [a for a in assets if str(a.get("name", "")).lower().endswith(".exe")]
    if not exes:
        return None, False
    for a in exes:
        if re.search(r"setup|install|instalador", a["name"].lower()):
            return a, True
    if esta_empacotado():
        atual = os.path.basename(sys.executable).lower()
        for a in exes:
            if a["name"].lower() == atual:
                return a, False
    return exes[0], False


# ------------------------------------------------------------- verificar --
def verificar() -> InfoAtualizacao:
    dados = _get_json(
        f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest")
    tag = str(dados.get("tag_name") or "")
    if not tag:
        raise ErroAtualizacao("A release mais recente não tem versão (tag).")
    info = InfoAtualizacao(
        versao_instalada=APP_VERSION, versao_remota=tag,
        tem_nova=_versao_tupla(tag) > _versao_tupla(APP_VERSION),
        url_pagina=str(dados.get("html_url") or ""))
    if not info.tem_nova:
        return info
    assets = dados.get("assets") or []
    asset, info.eh_instalador = _escolher_asset(assets)
    if asset:
        info.asset_nome = asset["name"]
        info.asset_url = asset.get("browser_download_url", "")
        info.asset_tamanho = int(asset.get("size") or 0)
        digest = str(asset.get("digest") or "")
        if digest.lower().startswith("sha256:"):
            info.sha256 = digest.split(":", 1)[1].strip().lower()
        else:
            for a in assets:
                if a.get("name", "").lower() == asset["name"].lower() + ".sha256":
                    info.sha256_url = a.get("browser_download_url", "")
    return info


# ---------------------------------------------------------------- backup --
def fazer_backup_antes():
    """Backup do banco antes de atualizar (best-effort: nunca impede a atualização)."""
    try:
        from database.db import rotina_backup_banco
        rotina_backup_banco()
    except Exception:
        log.exception("Backup antes da atualização falhou")


# --------------------------------------------------------------- download --
def _sha_esperado(info: InfoAtualizacao) -> str:
    if info.sha256:
        return info.sha256
    if info.sha256_url:
        try:
            _checar_host(info.sha256_url)
            with _abrir(info.sha256_url) as resp:
                m = re.search(r"\b[0-9a-fA-F]{64}\b", resp.read(4096).decode("utf-8", "ignore"))
            return m.group(0).lower() if m else ""
        except Exception:
            log.warning("Não foi possível ler o .sha256 da release", exc_info=True)
    return ""


def baixar(info: InfoAtualizacao, progresso=None, cancelar: threading.Event = None) -> str:
    """Baixa o arquivo da release e devolve o caminho. `progresso(feito, total)`
    é chamado a cada bloco; `cancelar` (Event) interrompe o download."""
    if not info.asset_url:
        raise ErroAtualizacao("A release não tem um arquivo .exe para baixar.")
    _checar_host(info.asset_url)
    esperado = _sha_esperado(info)

    os.makedirs(_PASTA_TEMP, exist_ok=True)
    final = os.path.join(_PASTA_TEMP, os.path.basename(info.asset_nome))
    parcial = final + ".part"
    for velho in (parcial, final):
        try:
            os.remove(velho)
        except OSError:
            pass

    hasher = hashlib.sha256()
    feito = 0
    try:
        with _abrir(info.asset_url) as resp, open(parcial, "wb") as saida:
            total = int(resp.headers.get("Content-Length") or info.asset_tamanho or 0)
            primeiro = True
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise DownloadCancelado("Download cancelado.")
                bloco = resp.read(_CHUNK)
                if not bloco:
                    break
                if primeiro and bloco[:2] != b"MZ":
                    raise ErroAtualizacao("O arquivo baixado não é um executável do Windows.")
                primeiro = False
                saida.write(bloco)
                hasher.update(bloco)
                feito += len(bloco)
                if progresso:
                    progresso(feito, total)
        if total and feito != total:
            raise ErroAtualizacao("Download incompleto. Tente novamente.")
        if esperado and hasher.hexdigest() != esperado:
            raise ErroAtualizacao("Falha na verificação de integridade (SHA-256). Arquivo descartado.")
        os.replace(parcial, final)
        return final
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ErroAtualizacao(f"Falha no download: {exc}") from exc
    finally:
        if os.path.exists(parcial):
            try:
                os.remove(parcial)
            except OSError:
                pass


# ----------------------------------------------------------------- aplicar --
def _bat(texto: str) -> str:
    return texto.replace("%", "%%")


def gerar_script(app_exe: str, novo: str, pid: int, instalador: bool) -> str:
    """Texto do .bat auxiliar. Sem blocos entre parênteses de propósito: o cmd
    expande %VAR% ao ler o bloco inteiro, o que quebraria os contadores."""
    cab = (
        "@echo off\r\n"
        f'set "APP={_bat(app_exe)}"\r\n'
        f'set "NOVO={_bat(novo)}"\r\n'
        f'set "PID={int(pid)}"\r\n'
        "set /a ESPERA=0\r\n"
        ":esperar\r\n"
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
        "if errorlevel 1 goto fechou\r\n"
        "set /a ESPERA+=1\r\n"
        "if %ESPERA% GEQ 60 goto fechou\r\n"
        "ping 127.0.0.1 -n 2 >nul\r\n"
        "goto esperar\r\n"
        ":fechou\r\n"
        "ping 127.0.0.1 -n 3 >nul\r\n"          # folga: solta .exe e a trava de instância única
    )
    if instalador:
        corpo = (
            'start /wait "" "%NOVO%" /SILENT /NORESTART /CLOSEAPPLICATIONS\r\n'
            'del /f /q "%NOVO%" >nul 2>&1\r\n'
            'start "" "%APP%"\r\n'
        )
    else:
        corpo = (
            "set /a TENT=0\r\n"
            ":tentar\r\n"
            "set /a TENT+=1\r\n"
            'move /y "%APP%" "%APP%.bak" >nul 2>&1\r\n'
            "if not errorlevel 1 goto copiar\r\n"
            "if %TENT% GEQ 30 goto reabrir\r\n"
            "ping 127.0.0.1 -n 2 >nul\r\n"
            "goto tentar\r\n"
            ":copiar\r\n"
            'copy /y "%NOVO%" "%APP%" >nul 2>&1\r\n'
            "if errorlevel 1 goto restaurar\r\n"
            'del /f /q "%APP%.bak" >nul 2>&1\r\n'
            'del /f /q "%NOVO%" >nul 2>&1\r\n'
            "goto reabrir\r\n"
            ":restaurar\r\n"                      # cópia falhou: volta o .exe antigo
            'move /y "%APP%.bak" "%APP%" >nul 2>&1\r\n'
            ":reabrir\r\n"
            'start "" "%APP%"\r\n'
        )
    return cab + corpo + '(goto) 2>nul & del "%~f0"\r\n'


def aplicar(caminho_novo: str, info: InfoAtualizacao) -> bool:
    """Dispara o .bat auxiliar e devolve True (o chamador deve fechar o app em
    seguida). Rodando do código-fonte (modo teste) não aplica nada: False."""
    if not esta_empacotado():
        return False
    script = os.path.join(_PASTA_TEMP, "solaz_atualizar.bat")
    texto = gerar_script(sys.executable, caminho_novo, os.getpid(), info.eh_instalador)
    try:
        with open(script, "w", encoding="oem", newline="") as f:
            f.write(texto)
    except LookupError:
        with open(script, "w", encoding="utf-8", newline="") as f:
            f.write(texto)

    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # o app reaberto extrai a versão NOVA
    flags = 0x08000000 | 0x00000008 | 0x00000200  # sem janela | destacado | novo grupo
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True,
                     env=env, cwd=_PASTA_TEMP)
    # Garantia: se algo travar o encerramento normal, o processo cai em 10 s
    # para o .bat conseguir trocar o arquivo.
    t = threading.Timer(10.0, lambda: os._exit(0))
    t.daemon = True
    t.start()
    return True
