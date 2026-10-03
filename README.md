# Sistema de Relatórios de Manutenção Fotovoltaica — Solaz Inovação

Aplicação desktop 100% offline em Python, com identidade visual da **Solaz
Inovação**, geração de relatórios profissionais em PDF (ReportLab) no
padrão técnico de referência da marca, e persistência local em SQLite
(arquitetura DAO/Repository, pronta para migrar para nuvem no futuro).

## 1. Instalação

Requer Python 3.10+.

```bash
cd solarapp
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Execução

```bash
python main.py
```

- **Usuário padrão:** `admin`
- **Senha padrão:** `admin123` (altere em **Configurações** após o primeiro acesso)

## 3. O que mudou nesta versão

### Identidade visual (Solaz Inovação)
- Paleta corporativa aplicada em toda a interface: Azul Escuro `#0F2A4A`,
  Azul de Destaque `#0284C7` e Cinza Técnico `#F4F6F9`.
- Logo da Solaz em destaque na tela de Login e no topo da Sidebar.
- PDF gerado seguindo fielmente o layout de referência: cabeçalho com
  logo + `DOC:`/`CLIENTE:`, barra azul de destaque nos títulos de seção,
  cards de fotos com borda e legenda, e tabela de conformidade agrupada
  por String com pílulas coloridas (CONFORME / NÃO CONFORME).

### Construtor de relatório em Cards visuais
- A antiga lista de checkboxes foi substituída por **cards com Switch**
  (ativo/inativo) e setas ▲▼ para reordenar a sequência exata das seções
  no PDF final.
- Construtor de Strings com as 3 medições (Vcc, Flutuação +, Flutuação −)
  agrupadas visualmente, e seletor de status em pílulas Conforme (verde) /
  Não Conforme (vermelho).

### Correções de UI/UX (heurísticas de Nielsen)
- **Exclusão corrigida**: `EmpresaDAO.excluir` e `ClienteDAO.excluir` agora
  tratam violações de chave estrangeira (registro com relatórios/agendamentos
  vinculados) e mostram uma mensagem clara em vez de falhar silenciosamente;
  toda exclusão passa por um modal de confirmação e a lista é recarregada
  imediatamente após a ação.
- **Telas de Clientes/Empresas redesenhadas**: a visualização inicial é
  apenas uma lista limpa com busca. O botão **"+ Novo Cadastro"** abre o
  formulário em um Modal; clicar em um item da lista abre um **Drawer**
  lateral de detalhes com fotos e os botões Editar/Excluir.
- **Datas e horas**: todos os campos de texto livre para data/hora foram
  substituídos por `DateEntry` (calendário) e menus suspensos de hora/minuto,
  eliminando erros de digitação.
- **Gerador de WhatsApp**: a caixa de texto fixa na tela de Agenda foi
  removida; agora um botão **"💬 Gerar Texto para Equipe"** abre um Modal
  com seleção de período, texto formatado e botão **"📋 Copiar Texto"**.

## 4. Estrutura do projeto

```
solarapp/
├── main.py
├── config.py                  # caminhos, paleta de marca (Marca), textos padrão
├── assets/
│   └── logo_solaz.png         # logo da Solaz Inovação
├── database/
│   ├── db.py
│   └── schema.sql
├── models/                    # DAOs
│   ├── usuario_dao.py
│   ├── empresa_dao.py         # excluir() trata FK e levanta ValueError amigável
│   ├── cliente_dao.py         # idem
│   ├── relatorio_dao.py
│   └── agenda_dao.py
├── ui/
│   ├── components.py          # ModalWindow, DrawerWindow, confirmar_exclusao, etc.
│   ├── login_window.py        # logo + paleta Solaz
│   ├── main_window.py         # sidebar com logo + paleta Solaz
│   ├── empresas_view.py       # lista + busca, modal, drawer
│   ├── clientes_view.py       # lista + busca, modal, drawer
│   ├── relatorio_view.py      # cards com switch + setas + pílulas de status
│   ├── agenda_view.py         # DateEntry + hora/minuto + modal WhatsApp
│   └── config_view.py
├── pdf/
│   └── report_generator.py    # layout de referência da Solaz Inovação
├── utils/
│   ├── image_utils.py
│   └── whatsapp_generator.py
└── requirements.txt
```

Ao rodar `main.py` pela primeira vez, são criados automaticamente:
- `data/sistema.db`, `data/logos/`, `data/fotos/`
- `Relatorios_Gerais/[Empresa]/[Cliente]/[Codigo].pdf`

## 5. Pontos para evoluir (sugestões)

- **Calendário mensal completo na Agenda**: hoje a lista é filtrada por
  Hoje/Amanhã/Semana; uma grade mensal com os agendamentos plotados por dia
  pode ser construída sobre o `AgendaDAO` já pronto, reaproveitando o widget
  `Calendar` do `tkcalendar` (já usado no `DateEntry`).
- **Múltiplas empresas com identidade própria**: a marca Solaz é aplicada na
  interface do programa; o PDF já usa a logo da empresa selecionada no
  relatório (`empresa.logo_path`), então cadastrar uma segunda prestadora
  gera relatórios com a logo dela automaticamente.
- **Migração para nuvem**: toda a persistência passa pelos DAOs em
  `models/`; trocar SQLite por PostgreSQL exige reescrever apenas
  `database/db.py`.
