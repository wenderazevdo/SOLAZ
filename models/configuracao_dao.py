"""
DAO de Configurações gerais do sistema — pares chave/valor persistidos em
SQLite. Usado hoje para a Pasta Raiz Padrão de relatórios (Configurações),
mas serve como ponto único para qualquer preferência futura do sistema.
"""
from database.db import get_cursor
from config import RELATORIOS_DIR

_CHAVE_PASTA_RELATORIOS = "pasta_relatorios"


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
