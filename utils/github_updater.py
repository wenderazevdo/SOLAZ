"""
Verificação de atualizações via GitHub Releases API.

Faz a requisição HTTP (bloqueante) para a API pública do GitHub e compara
a versão instalada (config.APP_VERSION) com a versão da release mais
recente do repositório configurado. Puramente de rede/lógica — quem chama
`buscar_release_mais_recente` deve rodar em uma thread separada para não
travar a interface, e sincronizar o resultado de volta com `.after(0, ...)`.
"""
import json
import urllib.error
import urllib.request

from config import APP_VERSION, GITHUB_REPO_OWNER, GITHUB_REPO_NAME

_TIMEOUT_SEGUNDOS = 8
_URL_API = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"


class ErroVerificacaoAtualizacao(Exception):
    """Erro de rede, HTTP ou de formato ao consultar a API do GitHub."""


def buscar_release_mais_recente() -> dict:
    """Retorna {'versao': str, 'url': str, 'nome': str} da release mais
    recente publicada no GitHub. Levanta ErroVerificacaoAtualizacao em
    caso de falha de rede, HTTP ou resposta em formato inesperado."""
    req = urllib.request.Request(
        _URL_API, headers={"Accept": "application/vnd.github+json",
                            "User-Agent": "SolazInovacao-RMP-App"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEGUNDOS) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ErroVerificacaoAtualizacao(
                "Nenhuma release publicada foi encontrada neste repositório."
            )
        raise ErroVerificacaoAtualizacao(f"Erro HTTP {exc.code} ao consultar o GitHub.")
    except urllib.error.URLError as exc:
        raise ErroVerificacaoAtualizacao(
            "Não foi possível conectar ao GitHub. Verifique sua conexão com a internet."
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ErroVerificacaoAtualizacao("Resposta inesperada da API do GitHub.")

    tag = dados.get("tag_name") or ""
    if not tag:
        raise ErroVerificacaoAtualizacao("A release mais recente não informa uma versão (tag).")

    return {
        "versao": tag,
        "url": dados.get("html_url") or "",
        "nome": dados.get("name") or tag,
    }


def comparar_versoes(v1: str, v2: str) -> int:
    """Compara duas versões no estilo 'v1.2.3' / '1.2.3'.
    Retorna 1 se v1 > v2, -1 se v1 < v2, 0 se iguais."""
    def normalizar(v):
        v = v.strip().lstrip("vV")
        partes = v.split(".")
        numeros = []
        for p in partes:
            digitos = "".join(c for c in p if c.isdigit())
            numeros.append(int(digitos) if digitos else 0)
        return numeros

    a, b = normalizar(v1), normalizar(v2)
    tamanho = max(len(a), len(b))
    a += [0] * (tamanho - len(a))
    b += [0] * (tamanho - len(b))
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


def verificar_atualizacao() -> dict:
    """Função de alto nível: busca a release mais recente e já compara com
    a versão instalada (config.APP_VERSION). Retorna:
    {'atualizado': bool, 'versao_instalada': str, 'versao_remota': str,
     'url': str}. Levanta ErroVerificacaoAtualizacao em caso de falha."""
    release = buscar_release_mais_recente()
    cmp = comparar_versoes(APP_VERSION, release["versao"])
    return {
        "atualizado": cmp >= 0,
        "versao_instalada": APP_VERSION,
        "versao_remota": release["versao"],
        "url": release["url"],
    }
