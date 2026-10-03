"""
Gerador do Relatório Financeiro / Cobrança de Serviços Realizados.

Diferente do RMP técnico (pdf/report_generator.py), este relatório usa um
cabeçalho puramente textual — "SOLAZ" em negrito escuro + "INOVAÇÃO" em
azul, sublinhados por uma linha azul contínua de borda a borda — sem
imagem de logo. Documento simples: tabela de atendimentos do período e
rodapé com o valor total consolidado a pagar.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as _canvas_mod

from config import Marca

_STYLES = getSampleStyleSheet()

COR_PRIMARIA = colors.HexColor(Marca.PRIMARIA)
COR_ACCENT = colors.HexColor(Marca.ACCENT)
COR_TITULO_EXEC = colors.HexColor("#334155")
COR_TEXTO_SEC = colors.HexColor(Marca.TEXTO_SECUNDARIO)
COR_CINZA_TECNICO = colors.HexColor(Marca.CINZA_TECNICO)
COR_CINZA_BORDA = colors.HexColor(Marca.CINZA_BORDA)
COR_SUCESSO_BG = colors.HexColor(Marca.SUCESSO_BG)
COR_SUCESSO_TXT = colors.HexColor(Marca.SUCESSO_TEXTO)

TITULO_DOC = ParagraphStyle(
    "TituloDoc", parent=_STYLES["Title"], fontName="Helvetica-Bold", fontSize=17,
    textColor=COR_TITULO_EXEC, alignment=TA_LEFT, spaceAfter=4,
)
SUBTITULO = ParagraphStyle(
    "Subtitulo", parent=_STYLES["Normal"], fontName="Helvetica", fontSize=11,
    textColor=COR_TEXTO_SEC, alignment=TA_LEFT, spaceAfter=2,
)
INFO_ROTULO = ParagraphStyle(
    "InfoRotulo", parent=_STYLES["Normal"], fontName="Helvetica-Bold", fontSize=7.7,
    textColor=COR_TEXTO_SEC, leading=10,
)
INFO_VALOR = ParagraphStyle(
    "InfoValor", parent=_STYLES["Normal"], fontName="Helvetica-Bold", fontSize=10.5,
    textColor=COR_TITULO_EXEC, leading=13,
)
CORPO = ParagraphStyle(
    "Corpo", parent=_STYLES["Normal"], fontName="Helvetica", fontSize=9.5,
    leading=13, textColor=COR_TITULO_EXEC, alignment=TA_LEFT,
)
CAB_TABELA = ParagraphStyle(
    "CabTabela", fontName="Helvetica-Bold", fontSize=8.5, textColor=COR_TEXTO_SEC,
)


def _formatar_reais(valor) -> str:
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        valor = 0.0
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


class _CabecalhoTextual:
    """Cabeçalho 100% textual (sem imagem de logo): 'SOLAZ' em negrito
    escuro + 'INOVAÇÃO' em azul, sublinhados por uma linha azul contínua
    de borda a borda — igual em toda página do documento."""

    def __init__(self, empresa_nome):
        self.empresa_nome = empresa_nome

    def __call__(self, canvas, doc):
        canvas.saveState()
        largura, altura = A4
        y_texto = altura - 1.6 * cm

        canvas.setFont("Helvetica-Bold", 18)
        canvas.setFillColor(COR_PRIMARIA)
        canvas.drawString(1.5 * cm, y_texto, "SOLAZ")
        largura_solaz = canvas.stringWidth("SOLAZ ", "Helvetica-Bold", 18)
        canvas.setFillColor(COR_ACCENT)
        canvas.drawString(1.5 * cm + largura_solaz, y_texto, "INOVAÇÃO")

        canvas.setStrokeColor(COR_ACCENT)
        canvas.setLineWidth(1.5)
        canvas.line(1.5 * cm, altura - 2.05 * cm, largura - 1.5 * cm, altura - 2.05 * cm)

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(COR_TEXTO_SEC)
        canvas.drawString(1.5 * cm, 1.2 * cm,
                           f"{self.empresa_nome} — Relatório de Cobrança de Serviços")
        canvas.setStrokeColor(COR_CINZA_BORDA)
        canvas.line(1.5 * cm, 1.6 * cm, largura - 1.5 * cm, 1.6 * cm)
        canvas.restoreState()


class _NumberedCanvasCobranca(_canvas_mod.Canvas):
    def __init__(self, *args, **kwargs):
        _canvas_mod.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_total_pages(total_pages)
            _canvas_mod.Canvas.showPage(self)
        _canvas_mod.Canvas.save(self)

    def _draw_total_pages(self, total_pages):
        largura, _ = A4
        self.setFont("Helvetica", 8)
        self.setFillColor(COR_TEXTO_SEC)
        self.drawRightString(largura - 1.5 * cm, 1.2 * cm,
                              f"Página {self._pageNumber} de {total_pages}")


def gerar_relatorio_cobranca_pdf(caminho_pdf, empresa_nome, periodo_inicio_str,
                                  periodo_fim_str, servicos, total_consolidado):
    """
    Gera o Relatório de Cobrança de Serviços Realizados.

    `servicos`: lista de dicts com chaves 'data', 'cliente_nome',
    'descricao_servico', 'valor_orcamento' (já filtrados por empresa e
    período pelo chamador).
    `total_consolidado`: soma total (float) a exibir no rodapé de fechamento.
    """
    os.makedirs(os.path.dirname(caminho_pdf), exist_ok=True)

    doc = BaseDocTemplate(
        caminho_pdf, pagesize=A4,
        topMargin=2.6 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title="Relatório de Cobrança de Serviços Realizados",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([
        PageTemplate(id="cobranca", frames=[frame], onPage=_CabecalhoTextual(empresa_nome))
    ])

    story = []
    story.append(Paragraph("Relatório de Cobrança de Serviços Realizados", TITULO_DOC))
    story.append(Paragraph("Fechamento de Orçamentos", SUBTITULO))
    story.append(Spacer(1, 0.5 * cm))

    def cel(rotulo, valor):
        sub = Table(
            [[Paragraph(rotulo.upper(), INFO_ROTULO)], [Paragraph(valor or "—", INFO_VALOR)]],
            colWidths=[8.6 * cm],
        )
        sub.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
        ]))
        return sub

    periodo_txt = f"{periodo_inicio_str} a {periodo_fim_str}"
    caixa = Table([[cel("Empresa Contratante", empresa_nome), cel("Período de Apuração", periodo_txt)]],
                   colWidths=[8.75 * cm, 8.75 * cm])
    caixa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COR_CINZA_TECNICO),
        ("BOX", (0, 0), (-1, -1), 0.5, COR_CINZA_BORDA),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, COR_CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(caixa)
    story.append(Spacer(1, 0.7 * cm))

    linhas = [[
        Paragraph("DATA", CAB_TABELA), Paragraph("CLIENTE / USINA", CAB_TABELA),
        Paragraph("SERVIÇO REALIZADO", CAB_TABELA),
        Paragraph("VALOR DO ORÇAMENTO (R$)", CAB_TABELA),
    ]]
    for s in servicos:
        linhas.append([
            Paragraph(s.get("data", "—"), CORPO),
            Paragraph(s.get("cliente_nome", "—"), CORPO),
            Paragraph(s.get("descricao_servico") or "—", CORPO),
            Paragraph(_formatar_reais(s.get("valor_orcamento")), CORPO),
        ])

    if not servicos:
        linhas.append([Paragraph("Nenhum serviço no período selecionado.", CORPO), "", "", ""])

    tabela = Table(linhas, colWidths=[2.3 * cm, 5 * cm, 6.7 * cm, 3.5 * cm])
    estilo_tabela = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_CINZA_TECNICO),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, COR_CINZA_BORDA),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, COR_CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    if not servicos:
        estilo_tabela.append(("SPAN", (0, 1), (-1, 1)))
    tabela.setStyle(TableStyle(estilo_tabela))
    story.append(tabela)
    story.append(Spacer(1, 0.8 * cm))

    rotulo_total_estilo = ParagraphStyle(
        "RotuloTotal", fontName="Helvetica-Bold", fontSize=11, textColor=COR_TITULO_EXEC,
    )
    valor_total_estilo = ParagraphStyle(
        "ValorTotal", fontName="Helvetica-Bold", fontSize=15, textColor=COR_SUCESSO_TXT,
        alignment=TA_RIGHT,
    )
    rodape = Table(
        [[Paragraph("VALOR TOTAL CONSOLIDADO A PAGAR", rotulo_total_estilo),
          Paragraph(_formatar_reais(total_consolidado), valor_total_estilo)]],
        colWidths=[11.5 * cm, 6 * cm],
    )
    rodape.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COR_SUCESSO_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(rodape)

    doc.build(story, canvasmaker=_NumberedCanvasCobranca)
    return caminho_pdf
