"""
Configurações globais da aplicação.
"""
import os

# Diretório base da aplicação (onde o executável/script está rodando)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Diretório do banco de dados SQLite
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "sistema.db")

# Diretório raiz onde os relatórios em PDF são salvos (pasta padrão do
# usuário — sobreposta em tempo de execução por ConfiguracaoDAO caso o
# usuário escolha outra em Configurações).
# Estrutura: /Documentos/SOLAZ/[Empresa]/[Cliente]/Relatórios/[Subpasta do tipo]/[Codigo].pdf
#            /Documentos/SOLAZ/[Empresa]/Serviços Realizados/[Arquivo].pdf
_DOCUMENTOS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
if not os.path.isdir(_DOCUMENTOS_DIR):
    # fallback multi-idioma/plataforma (ex: "Documentos" em pt-BR)
    alternativa = os.path.join(os.path.expanduser("~"), "Documentos")
    _DOCUMENTOS_DIR = alternativa if os.path.isdir(alternativa) else _DOCUMENTOS_DIR
RELATORIOS_DIR = os.path.join(_DOCUMENTOS_DIR, "SOLAZ")
os.makedirs(RELATORIOS_DIR, exist_ok=True)

# Nome da pasta de relatórios dentro da pasta do cliente e subpastas por tipo
# de relatório (criadas automaticamente com os.makedirs(..., exist_ok=True)).
PASTA_RELATORIOS_CLIENTE = "Relatórios"
SUBPASTA_RELATORIO_LIMPEZA = "RELATORIO LIMPEZA"
SUBPASTA_RELATORIO_TROCA = "RELATORIO TROCA MICRO"

# Diretório de logos das empresas
LOGOS_DIR = os.path.join(DATA_DIR, "logos")
os.makedirs(LOGOS_DIR, exist_ok=True)

# Diretório das assinaturas digitais dos responsáveis técnicos
ASSINATURAS_DIR = os.path.join(DATA_DIR, "assinaturas")
os.makedirs(ASSINATURAS_DIR, exist_ok=True)

# Diretório de fotos enviadas pelo usuário (cache local antes de compor o PDF)
FOTOS_DIR = os.path.join(DATA_DIR, "fotos")
os.makedirs(FOTOS_DIR, exist_ok=True)

# Diretório de assets estáticos da aplicação (logo da marca, etc.)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGO_SOLAZ_PATH = os.path.join(ASSETS_DIR, "logo_solaz.png")

# Aparência padrão da interface
APPEARANCE_MODE = "System"   # "System", "Dark", "Light"
COLOR_THEME = "blue"         # tema de cor do CustomTkinter (base do CTk)

# ---------------------------------------------------------------------------
# Versão instalada e repositório do GitHub usado para checagem de
# atualizações (Configurações → "Verificar Atualizações").
# ---------------------------------------------------------------------------
APP_VERSION = "1.1.0"
GITHUB_REPO_OWNER = "wenderazevdo"
GITHUB_REPO_NAME = "SOLAZ"

# ---------------------------------------------------------------------------
# Telemetria via Telegram Bot API (alertas de novo cadastro e de uso em outro
# PC). Os valores podem ser sobrescritos por variáveis de ambiente, para não
# precisar editar o código ao trocar/rotacionar o token.
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get(
    "SOLAZ_TELEGRAM_TOKEN", "8834142296:AAGQ4NGAct4jv6k-7Kp94kaCTyL4c7H-k4o"
)
TELEGRAM_CHAT_ID = os.environ.get("SOLAZ_TELEGRAM_CHAT_ID", "1768982003")

# ---------------------------------------------------------------------------
# Conta Master de Desenvolvedor. Só o HASH da senha é guardado (nunca a senha).
# Gere com:  python gerar_hash_master.py   e cole o resultado abaixo (ou na
# variável de ambiente SOLAZ_MASTER_HASH). Enquanto estiver vazio, a conta
# master fica DESATIVADA (ninguém consegue entrar como dev_master).
# ---------------------------------------------------------------------------
MASTER_USUARIO = "dev_master"
MASTER_SENHA_HASH = os.environ.get("SOLAZ_MASTER_HASH", "fa5e528bf9455ef7e6729e5b33791c28$a09023c605a3b7f456add9ff9d2b12629090e9b517b66ac707f7fe180a6752f6")

# Proporção fixa exigida para as fotos nos relatórios (largura, altura)
FOTO_ASPECT_RATIO = (4, 3)

# ---------------------------------------------------------------------------
# Identidade visual — Solaz Inovação
# Paleta extraída da logo/relatório de referência da marca.
# ---------------------------------------------------------------------------
class Marca:
    NOME = "Solaz Inovação"
    PRIMARIA = "#0F2A4A"        # Azul Escuro (textos fortes, sidebar, cabeçalho do PDF)
    PRIMARIA_CLARA = "#1B4A73"  # variação para hover/estados em modo claro
    ACCENT = "#0284C7"          # Azul de Destaque (links, ícones, barra de seção no PDF)
    ACCENT_HOVER = "#0369A1"
    CINZA_TECNICO = "#F4F6F9"   # fundo neutro de cards/tabelas
    CINZA_BORDA = "#E2E8F0"
    BRANCO = "#FFFFFF"
    TEXTO = "#1E293B"
    TEXTO_SECUNDARIO = "#64748B"
    SUCESSO_BG = "#DCFCE7"
    SUCESSO_TEXTO = "#166534"
    ERRO_BG = "#FEE2E2"
    ERRO_TEXTO = "#991B1B"
    ERRO = "#C62828"
    ERRO_HOVER = "#8E1E1E"

# Textos padrão editáveis (seção "Objetivo, Aplicação e Normas de Referência")
TEXTO_OBJETIVO_PADRAO = (
    "Este relatório tem como objetivo apresentar os resultados dos serviços de "
    "limpeza e reaperto de conexões elétricas realizados no sistema fotovoltaico "
    "do cliente, visando garantir a máxima eficiência de geração de energia e a "
    "segurança da instalação."
)
TEXTO_APLICACAO_PADRAO = (
    "O procedimento aplica-se a sistemas de geração fotovoltaica conectados à "
    "rede (on-grid) e isolados (off-grid), abrangendo módulos fotovoltaicos, "
    "string boxes, quadros de proteção CC/CA e inversores/microinversores."
)
TEXTO_NORMAS_PADRAO = (
    "Os procedimentos seguem as recomendações da NBR 16690, NBR 5410, NR-10 e "
    "as orientações do fabricante dos equipamentos instalados."
)
