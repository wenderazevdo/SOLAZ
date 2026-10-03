-- Schema SQLite - Sistema de Relatórios de Manutenção Fotovoltaica
-- Desenhado para futura migração para PostgreSQL/MySQL (tipos e nomes compatíveis)

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    -- Trava por Hardware ID (HWID) --
    hwid_vinculado TEXT,
    nome_pc TEXT,
    win_user TEXT,
    -- 'pendente' (aguardando aprovação do dev) / 'aprovado' / 'bloqueado' --
    status TEXT NOT NULL DEFAULT 'aprovado',
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    cnpj TEXT,
    telefone TEXT,
    email TEXT,
    responsavel_tecnico TEXT,
    responsavel_registro TEXT,
    logo_path TEXT,
    -- Assinatura digital do Responsável Técnico (imagem), posicionada
    -- automaticamente na página de conclusão do relatório em PDF.
    assinatura_path TEXT,
    -- Código curto da empresa, usado na estrutura de pastas dos
    -- relatórios (ex: '01'). Se vazio, cai no fallback do ID interno.
    codigo_empresa TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_razao_social TEXT NOT NULL,
    foto_local_path TEXT,
    qtd_modulos INTEGER,
    modulo_marca TEXT,
    modulo_potencia_wp REAL,
    modulo_foto_etiqueta_path TEXT,
    acesso_telhado_facil INTEGER DEFAULT 0,   -- 0/1 (bool)
    acesso_telhado_obs TEXT,
    ponto_agua_local TEXT,
    ponto_agua_pressao TEXT,                   -- 'Boa' / 'Ruim'
    ponto_agua_foto_path TEXT,
    inversores_qtd INTEGER,
    inversores_foto_etiqueta_path TEXT,
    endereco TEXT,
    google_maps_link TEXT,
    -- Dados cadastrais/comerciais e vínculo com a empresa prestadora --
    cpf_cnpj TEXT,
    contato_nome TEXT,
    telefone TEXT,
    empresa_id INTEGER REFERENCES empresas(id),
    potencia_sistema_kwp REAL,
    inversor_marca_modelo TEXT,
    -- Código do cliente exibido no cabeçalho do relatório PDF (ex: '020101').
    -- Se em branco, a interface usa o ID interno formatado como fallback.
    codigo_cliente TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relatorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,               -- Ex: RMP-YYYYMMDD-001
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    data_servico TEXT,
    responsavel_tecnico TEXT,
    -- Número de revisão do documento, exibido no cabeçalho como "REV: 02"
    revisao TEXT DEFAULT '01',
    texto_objetivo TEXT,
    texto_aplicacao TEXT,
    texto_normas TEXT,
    secoes_json TEXT,                          -- ordem e seções ativas (JSON)
    pdf_path TEXT,
    criado_em TEXT DEFAULT (datetime('now'))
);

-- Fotos vinculadas a um relatório, por seção
CREATE TABLE IF NOT EXISTS relatorio_fotos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL REFERENCES relatorios(id) ON DELETE CASCADE,
    secao TEXT NOT NULL,      -- ex: 'modulos_sujos', 'modulos_limpos', 'reaperto', ...
    foto_path TEXT NOT NULL,
    legenda TEXT,
    ordem INTEGER DEFAULT 0
);

-- Tabela de conformidade elétrica (Strings). Cada String tem 3 parâmetros
-- avaliados de forma independente: tensão de operação, flutuação (+) e
-- flutuação (-), cada um com seu próprio status CONFORME/NAO_CONFORME.
-- O Teste de Neutro (4º parâmetro) é opcional — só é preenchido quando a
-- usina possui condutor neutro no circuito.
-- A coluna `status` é mantida por compatibilidade (status geral calculado
-- como CONFORME apenas se os parâmetros preenchidos estiverem CONFORME).
CREATE TABLE IF NOT EXISTS relatorio_strings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL REFERENCES relatorios(id) ON DELETE CASCADE,
    string_nome TEXT NOT NULL,        -- ex: 'String 01'
    tensao_vcc REAL,
    flutuacao_positivo REAL,
    flutuacao_negativo REAL,
    status TEXT,                      -- status geral (legado/compatibilidade)
    status_tensao TEXT DEFAULT 'CONFORME',
    status_flutuacao_positivo TEXT DEFAULT 'CONFORME',
    status_flutuacao_negativo TEXT DEFAULT 'CONFORME',
    neutro_valor REAL,                -- Teste de Neutro (opcional)
    status_neutro TEXT DEFAULT 'CONFORME',
    ordem INTEGER DEFAULT 0
);

-- Bloco do Circuito de Corrente Alternada (CA) — mantido apenas por
-- compatibilidade com bancos antigos; a Corrente de Injeção Total global
-- foi substituída por um valor individual por disjuntor (ver
-- `relatorio_ca_disjuntores`) e não é mais gravada aqui.
CREATE TABLE IF NOT EXISTS relatorio_ca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL UNIQUE REFERENCES relatorios(id) ON DELETE CASCADE,
    tensao_linha_valor REAL,
    tensao_linha_status TEXT DEFAULT 'CONFORME',
    corrente_injecao_valor REAL,
    corrente_injecao_status TEXT DEFAULT 'CONFORME'
);

-- Múltiplos disjuntores do Circuito CA, cada um com sua tensão nominal
-- (127V / 220V / 380V / outra), tensão medida, CORRENTE DE INJEÇÃO
-- individual e status de conformidade. O Teste de Neutro é opcional.
CREATE TABLE IF NOT EXISTS relatorio_ca_disjuntores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relatorio_id INTEGER NOT NULL REFERENCES relatorios(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,          -- ex: 'Disjuntor 01'
    voltagem TEXT DEFAULT '220V',
    valor_medido REAL,
    status TEXT DEFAULT 'CONFORME',
    corrente_injecao_valor REAL,
    corrente_injecao_status TEXT DEFAULT 'CONFORME',
    neutro_valor REAL,
    status_neutro TEXT DEFAULT 'CONFORME',
    ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agenda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    data TEXT NOT NULL,           -- YYYY-MM-DD
    hora TEXT,                    -- HH:MM
    ordem_atendimento INTEGER DEFAULT 1,
    observacoes TEXT,
    -- Módulo de Serviços Realizados / Gestão Financeira --
    descricao_servico TEXT,       -- 'Serviço a ser realizado'
    valor_orcamento REAL,         -- Valor do Orçamento (R$)
    criado_em TEXT DEFAULT (datetime('now'))
);

-- Configurações gerais do sistema, persistidas como pares chave/valor
-- (ex: 'pasta_relatorios' -> caminho absoluto escolhido pelo usuário em
-- Configurações, sobrepondo o padrão RELATORIOS_DIR de config.py).
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
