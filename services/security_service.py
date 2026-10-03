"""
Identificação da máquina para a trava por hardware (HWID) e telemetria.

`get_hwid()` usa o UUID da placa-mãe/BIOS (WMI). Como o `wmic` foi removido
das versões mais recentes do Windows 11, há fallbacks (PowerShell/CIM e
MachineGuid do registro). `get_hwid_candidates()` devolve TODOS os
identificadores disponíveis: se um método falhar numa execução e outro
responder, o HWID já gravado ainda é reconhecido (evita falso "PC diferente").
"""
import getpass
import os
import re
import socket
import subprocess
import sys
import threading
import uuid

_RE_UUID = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)

# UUIDs "de fábrica" preenchidos por alguns fabricantes — idênticos em várias
# máquinas, portanto inúteis como identificador único.
_UUIDS_GENERICOS = {
    "00000000-0000-0000-0000-000000000000",
    "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
    "03000200-0400-0500-0006-000700080009",
}

_lock = threading.Lock()
_cache_candidatos = None


def get_pc_name() -> str:
    """Nome do computador na rede."""
    try:
        return socket.gethostname() or "desconhecido"
    except Exception:
        return "desconhecido"


def get_win_user() -> str:
    """Usuário logado no sistema operacional."""
    try:
        return os.getlogin()
    except Exception:
        try:
            return getpass.getuser()
        except Exception:
            return "desconhecido"


def _executar(comando, timeout=8) -> str:
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # sem janela de console
        r = subprocess.run(
            comando, capture_output=True, text=True, timeout=timeout,
            creationflags=flags, shell=False,
        )
        return r.stdout or ""
    except Exception:
        return ""


def _extrair_uuid(texto: str):
    for achado in _RE_UUID.findall(texto or ""):
        u = achado.upper()
        if u not in _UUIDS_GENERICOS:
            return u
    return None


def _hwid_wmic():
    return _extrair_uuid(_executar(["wmic", "csproduct", "get", "uuid"]))


def _hwid_powershell():
    return _extrair_uuid(_executar([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
    ]))


def _hwid_machine_guid():
    """MachineGuid do Windows (registro) ou /etc/machine-id em outros SOs."""
    if sys.platform.startswith("win"):
        try:
            import winreg
            chave = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            )
            valor, _ = winreg.QueryValueEx(chave, "MachineGuid")
            return f"MG-{str(valor).upper()}" if valor else None
        except Exception:
            return None
    for caminho in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                mid = f.read().strip()
            if mid:
                return f"MG-{mid.upper()}"
        except Exception:
            continue
    return None


def _hwid_mac():
    """Último recurso: endereço MAC (pode ser instável em algumas máquinas)."""
    return f"MAC-{uuid.getnode():012X}"


def get_hwid_candidates() -> list:
    """Todos os identificadores de hardware obtidos, do mais confiável ao
    menos confiável (o primeiro é o gravado no cadastro). Cacheado."""
    global _cache_candidatos
    with _lock:
        if _cache_candidatos is not None:
            return list(_cache_candidatos)
        candidatos = []
        for fonte in (_hwid_wmic, _hwid_powershell, _hwid_machine_guid):
            try:
                valor = fonte()
            except Exception:
                valor = None
            if valor and valor not in candidatos:
                candidatos.append(valor)
        if not candidatos:
            candidatos.append(_hwid_mac())
        _cache_candidatos = candidatos
        return list(candidatos)


def get_hwid() -> str:
    """UUID único da placa-mãe/processador (WMI); com fallbacks."""
    return get_hwid_candidates()[0]


def pre_carregar_hwid():
    """Calcula o HWID em segundo plano (os comandos WMI/PowerShell podem
    levar 1-2 s) para o login não congelar a interface."""
    threading.Thread(target=get_hwid_candidates, daemon=True).start()
