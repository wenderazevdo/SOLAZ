"""
DAO de Configurações gerais do sistema — pares chave/valor persistidos em
SQLite. Usado hoje para a Pasta Raiz Padrão de relatórios (Configurações),
mas serve como ponto único para qualquer preferência futura do sistema.
"""
import json

from database.db import get_cursor
from config import RELATORIOS_DIR

_CHAVE_PASTA_RELATORIOS = "pasta_relatorios"

# Ordem personalizada (▲▼) das seções de cada tipo de relatório (lista JSON).
CHAVE_ORDEM_SECOES_LIMPEZA = "ordem_secoes_limpeza"
CHAVE_ORDEM_SECOES_TROCA = "ordem_secoes_troca"


class ConfiguracaoDAO:
    def obter(self, chave: str, padrao: str = None):
        with get_cursor() as cur:
            cur.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
            row = cur.fetchone()
            return row["valor"] if row else padrao

    def definir(self, chave: str, valor: str):
        with get_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO configuracoes (chave, valor) VALUES (?, ?)
                   ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor""",
                (chave, valor),
            )

    # ------------------------------------------------ pasta de relatórios --
    def obter_pasta_relatorios(self) -> str:
        """Retorna a pasta raiz configurada pelo usuário em Configurações,
        ou o padrão de config.py (RELATORIOS_DIR) caso nunca tenha sido
        alterada."""
        return self.obter(_CHAVE_PASTA_RELATORIOS, RELATORIOS_DIR)

    def definir_pasta_relatorios(self, caminho: str):
        self.definir(_CHAVE_PASTA_RELATORIOS, caminho)

    # ------------------------------------------------- ordem das seções --
    def obter_ordem_secoes(self, chave: str, padrao) -> list:
        """Ordem salva (JSON) para `chave`, validada contra `padrao`: ignora
        itens desconhecidos/repetidos e acrescenta ao final seções novas que
        não estavam salvas. Sem valor salvo ou JSON inválido -> `padrao`."""
        padrao = list(padrao)
        try:
            salva = json.loads(self.obter(chave) or "[]")
        except (ValueError, TypeError):
            return padrao
        if not isinstance(salva, list):
            return padrao
        validas = []
        for item in salva:
            if item in padrao and item not in validas:
                validas.append(item)
        return validas + [s for s in padrao if s not in validas]

    def salvar_ordem_secoes(self, chave: str, ordem):
        self.definir(chave, json.dumps(list(ordem), ensure_ascii=False))
