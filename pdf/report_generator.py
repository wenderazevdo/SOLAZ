"""
Gerador de PDF do Relatório de Manutenção Preventiva (RMP) - ReportLab.
Padrão visual técnico da Solaz Inovação.

Principais características visuais:
  * fonte sans embutida (Liberation Sans / Arimo / Arial) - o PDF fica
    idêntico em qualquer visualizador, sem depender da Helvetica genérica;
  * títulos de seção desenhados com espaçamento entre letras (tracking) e
    barra azul #0183C7 compacta;
  * bloco do cliente, cards de foto, notas e pílulas de status com
    CANTOS ARREDONDADOS;
  * fotos recortadas em 4:3 (cover), com cantos arredondados, corrigidas
    pelo EXIF e reduzidas (PDF leve);
  * linha de cards com altura igual nas duas colunas;
  * tabelas compactas, só linhas horizontais finas.

FONTES: coloque `LiberationSans-Regular.ttf` e `LiberationSans-Bold.ttf`
(enviados junto) em `fonts/` na raiz do projeto (ou em `assets/fonts/`).
Opcional: `Montserrat-Bold.ttf` na mesma pasta para os títulos de seção.
Ordem de busca: pasta do projeto -> fontes do sistema (Liberation, Arial).
Sem nenhuma, cai para Helvetica sem quebrar.
"""
import os
from functools import lru_cache
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas_mod
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, Image, KeepTogether, Flowable,
)

from config import Marca

# ===================================================================== fontes
_BASE = os.path.dirname(os.path.abspath(__file__))
_PASTAS_FONTES = []
for _p in (getattr(Marca, "FONTES_DIR", None),
           os.path.join(_BASE, "fonts"), os.path.join(_BASE, "assets", "fonts"),
           os.path.join(_BASE, "static", "fonts"), os.path.join(_BASE, "resources", "fonts"),
           os.path.join(_BASE, "..", "fonts"), os.path.join(_BASE, "..", "assets", "fonts"),
           os.path.join(os.getcwd(), "fonts"), os.path.join(os.getcwd(), "assets", "fonts"),
           "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/liberation2",
           "C:/Windows/Fonts", "/Library/Fonts", "/System/Library/Fonts/Supplemental"):
    if _p:
        _PASTAS_FONTES.append(_p)


def _achar_fonte(*nomes):
    for pasta in _PASTAS_FONTES:
        for nome in nomes:
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                return caminho
    return None


def _registrar_fontes():
    """Retorna (corpo, negrito, titulo)."""
    pares = [("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
             ("Arimo-Regular.ttf", "Arimo-Bold.ttf"),
             ("arial.ttf", "arialbd.ttf"), ("Arial.ttf", "Arial Bold.ttf")]
    corpo, negrito = "Helvetica", "Helvetica-Bold"
    for reg, bold in pares:
        p_reg, p_bold = _achar_fonte(reg), _achar_fonte(bold)
        if p_reg and p_bold:
            try:
                pdfmetrics.registerFont(TTFont("RMP-Sans", p_reg))
                pdfmetrics.registerFont(TTFont("RMP-Sans-Bold", p_bold))
                pdfmetrics.registerFontFamily(
                    "RMP-Sans", normal="RMP-Sans", bold="RMP-Sans-Bold",
                    italic="RMP-Sans", boldItalic="RMP-Sans-Bold")
                corpo, negrito = "RMP-Sans", "RMP-Sans-Bold"
                break
            except Exception:
                continue
    titulo = negrito
    p_mont = getattr(Marca, "FONTE_TITULO_PATH", None) or _achar_fonte("Montserrat-Bold.ttf")
    if p_mont and os.path.exists(p_mont):
        try:
            pdfmetrics.registerFont(TTFont("Montserrat-Bold", p_mont))
            titulo = "Montserrat-Bold"
        except Exception:
            pass
    return corpo, negrito, titulo


FONTE, FONTE_B, FONTE_TITULO = _registrar_fontes()

# ====================================================================== cores
_STYLES = getSampleStyleSheet()

COR_PRIMARIA = colors.HexColor(Marca.PRIMARIA)
COR_ACCENT = colors.HexColor(Marca.ACCENT)
COR_CINZA_BORDA = colors.HexColor(Marca.CINZA_BORDA)
COR_TEXTO = colors.HexColor(Marca.TEXTO)
COR_TEXTO_SEC = colors.HexColor(Marca.TEXTO_SECUNDARIO)
COR_SUCESSO_BG = colors.HexColor(Marca.SUCESSO_BG)
COR_SUCESSO_TXT = colors.HexColor(Marca.SUCESSO_TEXTO)
COR_ERRO_BG = colors.HexColor(Marca.ERRO_BG)
COR_ERRO_TXT = colors.HexColor(Marca.ERRO_TEXTO)

COR_AZUL_BARRA = colors.HexColor("#0183C7")
COR_TITULO = colors.HexColor("#0E1729")
COR_ROTULO = colors.HexColor("#334054")
COR_FUNDO_CLIENTE = colors.HexColor("#F7FAFB")
COR_BORDA_FINA = colors.HexColor("#CBD5E1")
COR_CAB_TABELA = colors.HexColor("#F1F5F9")
COR_VERMELHO = colors.HexColor("#C2410C")   # tom "vermelho-alaranjado" do exemplo
COR_VERDE = colors.HexColor("#15803D")
COR_LEGENDA = colors.HexColor("#475569")
COR_TITULO_EXEC = colors.HexColor("#334155")

LARGURA_UTIL = 18 * cm
RAIO_CARD = 6
RAIO_IMG = 4

# =================================================================== estilos
CORPO = ParagraphStyle(
    "Corpo", parent=_STYLES["Normal"], fontName=FONTE, fontSize=9.5,
    leading=13.5, textColor=COR_TEXTO, alignment=TA_LEFT,
)
SUBTITULO = ParagraphStyle(
    "Subtitulo", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=9.5,
    leading=12, textColor=COR_TITULO, spaceBefore=7, spaceAfter=2,
)
LEGENDA = ParagraphStyle(
    "Legenda", parent=_STYLES["Normal"], fontName=FONTE, fontSize=8,
    leading=10, textColor=COR_LEGENDA, alignment=TA_CENTER,
)
CAPA_TITULO = ParagraphStyle(
    "CapaTitulo", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=20,
    leading=24, textColor=COR_TITULO, alignment=TA_LEFT, spaceBefore=0, spaceAfter=2,
)
CAPA_SUB = ParagraphStyle(
    "CapaSub", parent=_STYLES["Normal"], fontName=FONTE, fontSize=10.5,
    leading=13, textColor=COR_TEXTO_SEC, alignment=TA_LEFT, spaceAfter=0,
)
INFO_ROTULO = ParagraphStyle(
    "InfoRotulo", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=7.5,
    leading=9.5, textColor=COR_ROTULO, spaceAfter=2,
)
INFO_VALOR = ParagraphStyle(
    "InfoValor", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=9.5,
    leading=12, textColor=COR_TITULO,
)
CAB_TABELA = ParagraphStyle(
    "CabTabela", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=7.5,
    leading=9, textColor=COR_ROTULO,
)
CORPO_TABELA = ParagraphStyle(
    "CorpoTabela", parent=_STYLES["Normal"], fontName=FONTE, fontSize=8.8,
    leading=11, textColor=COR_TEXTO,
)
ITEM_TABELA = ParagraphStyle(
    "ItemTabela", parent=CORPO_TABELA, fontName=FONTE_B, textColor=COR_ROTULO,
)
GRUPO_TABELA = ParagraphStyle(
    "GrupoTabela", parent=_STYLES["Normal"], fontName=FONTE_B, fontSize=8,
    leading=10, textColor=COR_ROTULO,
)

NOMES_SECOES = {
    "modulos_sujos": "Fotos dos Módulos Sujos (Antes da Limpeza)",
    "modulos_limpos": "Fotos dos Módulos Limpos (Após a Limpeza)",
    "reaperto_parafusos": "Fotos de Reaperto de Parafusos",
    "teste_tensao_cc": "Fotos dos Testes de Tensão CC",
    "teste_tensao_ca": "Fotos dos Testes de Tensão CA",
    "geracao_energia": "Comparativo de Geração de Energia (Antes e Depois)",
    "sugestoes_melhorias": "Sugestões de Melhorias",
    "tabela_conformidade": "Tabela de Conformidade String Box / Elétrica (CC e CA)",
}


# ================================================================== utilitários
def _texto_espacado(c, x, y, texto, fonte, tam, cor, esp=0.0, alinhar="left"):
    """Desenha texto com espaçamento entre letras (tracking). Retorna a largura."""
    larg = pdfmetrics.stringWidth(texto, fonte, tam) + esp * len(texto)
    if alinhar == "center":
        x -= larg / 2
    c.saveState()                      # charSpace persiste no estado gráfico:
    t = c.beginText()                  # isolar para não "vazar" p/ outros textos
    t.setFont(fonte, tam)
    t.setFillColor(cor)
    t.setCharSpace(esp)
    t.setTextOrigin(x, y)
    t.textOut(texto)
    c.drawText(t)
    c.restoreState()
    return larg


@lru_cache(maxsize=128)
def _carregar_imagem(caminho):
    """Abre a foto, corrige a rotação EXIF, reduz para no máx. 1600 px e
    devolve (ImageReader, largura, altura). Sem Pillow, usa o arquivo cru."""
    try:
        from PIL import Image as PILImage, ImageOps
        with PILImage.open(caminho) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1600, 1600))
            buf = BytesIO()
            im.save(buf, "JPEG", quality=86, optimize=True)
            buf.seek(0)
            return ImageReader(buf), im.width, im.height
    except Exception:
        leitor = ImageReader(caminho)
        w, h = leitor.getSize()
        return leitor, w, h


# ================================================================== flowables
class _TituloSecao(Flowable):
    """Título de seção: barra azul compacta + texto em caixa alta com
    espaçamento entre letras. Reduz a fonte sozinho se o texto for longo."""
    ALTURA = 17
    BARRA = 4

    def __init__(self, texto):
        super().__init__()
        self.texto = texto
        self.hAlign = "LEFT"

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.ALTURA

    def draw(self):
        c = self.canv
        c.setFillColor(COR_AZUL_BARRA)
        c.roundRect(0, 0, self.BARRA, self.ALTURA, 1.2, stroke=0, fill=1)
        tam, esp = 12, 0.55
        larg_max = self.width - self.BARRA - 14
        larg = pdfmetrics.stringWidth(self.texto, FONTE_TITULO, tam) + esp * len(self.texto)
        if larg > larg_max:
            fator = larg_max / larg
            tam, esp = tam * fator, esp * fator
        base = (self.ALTURA - tam * 0.72) / 2
        _texto_espacado(c, self.BARRA + 8, base, self.texto, FONTE_TITULO, tam,
                        COR_TITULO, esp)


class _Caixa(Flowable):
    """Envolve outro flowable numa caixa de cantos arredondados."""

    def __init__(self, interno, pad_x=14, pad_y=9, fundo=COR_FUNDO_CLIENTE,
                 borda=COR_BORDA_FINA, raio=RAIO_CARD):
        super().__init__()
        self.interno, self.pad_x, self.pad_y = interno, pad_x, pad_y
        self.fundo, self.borda, self.raio = fundo, borda, raio
        self.hAlign = "LEFT"

    def wrap(self, aw, ah):
        self.width = aw
        _, ih = self.interno.wrap(aw - 2 * self.pad_x, ah)
        self.height = ih + 2 * self.pad_y
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.fundo)
        c.setStrokeColor(self.borda)
        c.setLineWidth(0.6)
        c.roundRect(0.3, 0.3, self.width - 0.6, self.height - 0.6, self.raio,
                    stroke=1, fill=1)
        self.interno.drawOn(c, self.pad_x, self.pad_y)


class _Pilula(Flowable):
    """Selo de status totalmente arredondado."""
    W, H = 2.9 * cm, 13.5

    def __init__(self, texto, conforme):
        super().__init__()
        self.texto, self.conforme = texto, conforme
        self.hAlign = "LEFT"

    def wrap(self, aw, ah):
        return self.W, self.H

    def draw(self):
        c = self.canv
        c.setFillColor(COR_SUCESSO_BG if self.conforme else COR_ERRO_BG)
        c.roundRect(0, 0, self.W, self.H, self.H / 2, stroke=0, fill=1)
        _texto_espacado(c, self.W / 2, 4.1, self.texto, FONTE_B, 7.2,
                        COR_SUCESSO_TXT if self.conforme else COR_ERRO_TXT,
                        0.25, "center")


class _LinhaCards(Flowable):
    """Uma linha com 1 ou 2 cards de foto, sempre com a MESMA altura.
    Card = moldura arredondada, título colorido, divisória fina, foto 4:3
    (recorte 'cover', cantos arredondados) e legenda."""
    PAD = 8
    GAP = 10
    GAP_V = 10

    def __init__(self, itens):
        """itens: lista de (foto_dict, rotulo) onde rotulo = (texto, cor) | None"""
        super().__init__()
        self.itens = itens
        self.hAlign = "LEFT"

    def _medidas(self, aw):
        self.cw = (aw - self.GAP) / 2
        self.iw = self.cw - 2 * self.PAD
        self.ih = self.iw * 3 / 4
        self.legendas = []
        altura = 0
        for foto, rotulo in self.itens:
            txt = (foto.get("legenda") or "").strip()
            par = Paragraph(txt, LEGENDA) if txt else None
            ph = par.wrap(self.iw, 200)[1] if par else 0
            self.legendas.append((par, ph))
            h = self.PAD + self.ih + self.PAD
            if rotulo:
                h += 11 + 6 + 8        # título + respiro + respiro após divisória
            if par:
                h += 7 + ph
            altura = max(altura, h)
        self.altura_card = altura

    def wrap(self, aw, ah):
        self._medidas(aw)
        self.width = aw
        self.height = self.altura_card
        return aw, self.height

    def draw(self):
        c = self.canv
        H = self.altura_card
        for i, (foto, rotulo) in enumerate(self.itens):
            x0 = i * (self.cw + self.GAP)
            c.setFillColor(colors.white)
            c.setStrokeColor(COR_BORDA_FINA)
            c.setLineWidth(0.6)
            c.roundRect(x0 + 0.3, 0.3, self.cw - 0.6, H - 0.6, RAIO_CARD, stroke=1, fill=1)

            y = H - self.PAD
            if rotulo:
                texto, cor = rotulo
                _texto_espacado(c, x0 + self.cw / 2, y - 8, texto, FONTE_B, 8.5, cor,
                                0.35, "center")
                y -= 11 + 6
                c.setStrokeColor(COR_BORDA_FINA)
                c.setLineWidth(0.5)
                c.line(x0 + self.PAD, y, x0 + self.cw - self.PAD, y)
                y -= 8

            img_x, img_y = x0 + self.PAD, y - self.ih
            self._desenhar_foto(c, foto.get("foto_path"), img_x, img_y, self.iw, self.ih)
            y = img_y

            par, ph = self.legendas[i]
            if par:
                par.drawOn(c, x0 + self.PAD, y - 7 - ph)

    def _desenhar_foto(self, c, caminho, x, y, w, h):
        c.saveState()
        path = c.beginPath()
        path.roundRect(x, y, w, h, RAIO_IMG)
        try:
            leitor, iw, ih = _carregar_imagem(caminho)
            esc = max(w / iw, h / ih)           # cover: preenche sem distorcer
            dw, dh = iw * esc, ih * esc
            c.clipPath(path, stroke=0, fill=0)
            c.drawImage(leitor, x - (dw - w) / 2, y - (dh - h) / 2,
                        width=dw, height=dh)
        except Exception:
            c.setFillColor(COR_CAB_TABELA)
            c.roundRect(x, y, w, h, RAIO_IMG, stroke=0, fill=1)
            _texto_espacado(c, x + w / 2, y + h / 2, "[imagem indisponível]",
                            FONTE, 8, COR_LEGENDA, 0, "center")
        c.restoreState()


# ========================================================== cabeçalho/rodapé
class _HeaderFooterCanvas:
    LOGO_W = 5.0 * cm
    LOGO_H = 2.0 * cm

    def __init__(self, logo_path, codigo, cliente_nome, revisao, data_servico, empresa_nome):
        self.logo_path = logo_path
        self.codigo = codigo
        self.cliente_nome = cliente_nome or "—"
        self.revisao = revisao or "01"
        self.data_servico = data_servico or "—"
        self.empresa_nome = empresa_nome or Marca.NOME

    def __call__(self, canvas, doc):
        canvas.saveState()
        largura, altura = A4
        topo = altura - 1.45 * cm
        y_linha = altura - 2.75 * cm

        if self.logo_path and os.path.exists(self.logo_path):
            try:
                canvas.drawImage(
                    self.logo_path, 1.5 * cm, y_linha + 0.15 * cm,
                    width=self.LOGO_W, height=self.LOGO_H,
                    preserveAspectRatio=True, mask="auto", anchor="sw",
                )
            except Exception:
                self._logo_textual(canvas)
        else:
            self._logo_textual(canvas)

        dir_x = largura - 1.5 * cm
        canvas.setFont(FONTE_B, 9)
        canvas.setFillColor(COR_TITULO)
        canvas.drawRightString(dir_x, topo, f"DOC: {self.codigo}")
        canvas.setFont(FONTE_B, 8.5)
        canvas.setFillColor(COR_TITULO_EXEC)
        canvas.drawRightString(dir_x, topo - 0.4 * cm, f"CLIENTE: {self.cliente_nome}")
        canvas.setFont(FONTE, 8.5)
        canvas.setFillColor(COR_TEXTO_SEC)
        canvas.drawRightString(dir_x, topo - 0.8 * cm,
                               f"REV: {self.revisao}  |  DATA: {self.data_servico}")

        canvas.setStrokeColor(COR_ACCENT)
        canvas.setLineWidth(1.3)
        canvas.line(1.5 * cm, y_linha, largura - 1.5 * cm, y_linha)

        canvas.setStrokeColor(COR_CINZA_BORDA)
        canvas.setLineWidth(0.5)
        canvas.line(1.5 * cm, 1.6 * cm, largura - 1.5 * cm, 1.6 * cm)
        canvas.setFont(FONTE, 8)
        canvas.setFillColor(COR_TEXTO_SEC)
        canvas.drawString(1.5 * cm, 1.2 * cm,
                          f"{self.empresa_nome} — Relatório Técnico Fotovoltaico")
        canvas.restoreState()

    def _logo_textual(self, canvas):
        tam, y = 24, A4[1] - 2.2 * cm
        larg = _texto_espacado(canvas, 1.5 * cm, y, "SOLAZ ", FONTE_B, tam, COR_TITULO, -0.3)
        _texto_espacado(canvas, 1.5 * cm + larg, y, "INOVAÇÃO", FONTE_B, tam,
                        COR_AZUL_BARRA, -0.3)


def _criar_documento(caminho_pdf, logo_path, codigo, cliente_nome, revisao, data_servico,
                      empresa_nome):
    doc = BaseDocTemplate(
        caminho_pdf, pagesize=A4,
        topMargin=2.95 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title=f"Relatório {codigo}",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    hf = _HeaderFooterCanvas(logo_path, codigo, cliente_nome, revisao, data_servico,
                             empresa_nome)
    doc.addPageTemplates([PageTemplate(id="RMP", frames=[frame], onPage=hf)])
    return doc


# ================================================================== seções
def _titulo_com_barra(numero, texto):
    return [_TituloSecao(f"{numero}. {texto}".upper()), Spacer(1, 7)]


def _titulo_sem_numero(texto):
    return [_TituloSecao(texto.upper()), Spacer(1, 7)]


def _formatar_responsavel(relatorio, empresa):
    tecnico = (relatorio.get("responsavel_tecnico") or "").strip()
    registro = (empresa.get("responsavel_registro") or "").strip()
    if not registro:
        return tecnico or "—"
    if "crt" in registro.lower():
        return f"{tecnico} ({registro})" if tecnico else registro
    return f"{tecnico} (CRT: {registro})" if tecnico else f"CRT: {registro}"


def _bloco_capa(empresa, cliente, relatorio):
    elementos = [
        Paragraph("Relatório de Manutenção Preventiva (RMP)", CAPA_TITULO),
        Paragraph("Inspeção Técnica, Limpeza de Módulos e Testes de Funcionalidade Elétrica",
                  CAPA_SUB),
        Spacer(1, 0.4 * cm),
    ]

    from models.cliente_dao import ClienteDAO
    codigo_cliente = ClienteDAO.codigo_exibicao(cliente)
    responsavel_fmt = _formatar_responsavel(relatorio, empresa)

    def cel(rotulo, valor):
        return [Paragraph(rotulo.upper(), INFO_ROTULO), Paragraph(valor or "—", INFO_VALOR)]

    pad_x = 14
    larg_int = LARGURA_UTIL - 2 * pad_x
    tabela = Table(
        [[cel("Cliente / Contratante", cliente.get("nome_razao_social", "")),
          cel("Código do Cliente", codigo_cliente),
          cel("Responsável Técnico", responsavel_fmt)]],
        colWidths=[larg_int / 3] * 3,
    )
    tabela.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(_Caixa(tabela, pad_x=pad_x, pad_y=9))
    elementos.append(Spacer(1, 0.55 * cm))
    return elementos


def _tabela_base(linhas, larguras, extra=None):
    tabela = Table(linhas, colWidths=larguras)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_CAB_TABELA),
        ("LINEBELOW", (0, 0), (-1, 0), 1.4, COR_BORDA_FINA),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, COR_BORDA_FINA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    tabela.setStyle(TableStyle(estilo + (extra or [])))
    return tabela


def _bloco_sumario(secoes_ativas):
    elementos = _titulo_sem_numero("Sumário do Relatório")
    linhas = [[Paragraph("ITEM", CAB_TABELA), Paragraph("SEÇÃO", CAB_TABELA)]]
    linhas.append([Paragraph("1.0", ITEM_TABELA),
                   Paragraph("Objetivo, Aplicação e Normas de Referência", CORPO_TABELA)])
    n = 2
    for secao in secoes_ativas:
        linhas.append([Paragraph(f"{n}.0", ITEM_TABELA),
                       Paragraph(NOMES_SECOES.get(secao, secao), CORPO_TABELA)])
        n += 1
    elementos.append(_tabela_base(linhas, [1.8 * cm, LARGURA_UTIL - 1.8 * cm]))
    elementos.append(Spacer(1, 0.5 * cm))
    return elementos


def _bloco_objetivo(relatorio):
    elementos = _titulo_com_barra("1", "Objetivo, Aplicação e Normas de Referência")
    elementos.append(Paragraph("Objetivo", SUBTITULO))
    elementos.append(Paragraph(relatorio.get("texto_objetivo", ""), CORPO))
    elementos.append(Paragraph("Aplicação", SUBTITULO))
    elementos.append(Paragraph(relatorio.get("texto_aplicacao", ""), CORPO))
    elementos.append(Paragraph("Normas de Referência", SUBTITULO))
    elementos.append(Paragraph(relatorio.get("texto_normas", ""), CORPO))
    elementos.append(Spacer(1, 0.45 * cm))
    return elementos


# ----------------------------------------------------------------- fotos ----
ROTULOS_CARD_SECAO = {
    "modulos_sujos": ("ANTERIOR À LIMPEZA", COR_VERMELHO),
    "modulos_limpos": ("POSTERIOR À LIMPEZA", COR_VERDE),
}
ROTULOS_CARD_COMPARATIVO = [
    ("ANTERIOR À LIMPEZA", COR_VERMELHO),
    ("POSTERIOR À LIMPEZA", COR_VERDE),
]


def _card_nota_texto(texto, largura_col):
    estilo = ParagraphStyle("NotaTexto", parent=CORPO, fontSize=9.5, leading=13.5)
    interno = Paragraph(texto, estilo)
    return _Caixa(interno, pad_x=12, pad_y=8)


def _bloco_fotos(secao_chave, numero, fotos):
    cabecalho = _titulo_com_barra(numero, NOMES_SECOES.get(secao_chave, secao_chave))

    if not fotos:
        cabecalho.append(Paragraph("Nenhuma foto registrada nesta seção.", CORPO))
        cabecalho.append(Spacer(1, 0.4 * cm))
        return [KeepTogether(cabecalho)]

    if secao_chave == "sugestoes_melhorias":
        com_foto = [f for f in fotos if f.get("foto_path")]
        sem_foto = [f for f in fotos if not f.get("foto_path")]
    else:
        com_foto, sem_foto = fotos, []

    elementos = []
    if com_foto:
        itens = []
        for i, foto in enumerate(com_foto):
            if secao_chave in ROTULOS_CARD_SECAO:
                rotulo = ROTULOS_CARD_SECAO[secao_chave]
            elif secao_chave == "geracao_energia" and i < len(ROTULOS_CARD_COMPARATIVO):
                rotulo = ROTULOS_CARD_COMPARATIVO[i]
            else:
                rotulo = None
            itens.append((foto, rotulo))

        linhas = [itens[i:i + 2] for i in range(0, len(itens), 2)]
        # Título + 1ª linha de cards juntos: título nunca fica órfão.
        cabecalho += [_LinhaCards(linhas[0]), Spacer(1, _LinhaCards.GAP_V)]
        elementos.append(KeepTogether(cabecalho))
        for linha in linhas[1:]:
            elementos += [_LinhaCards(linha), Spacer(1, _LinhaCards.GAP_V)]
    else:
        elementos.append(KeepTogether(cabecalho))

    for nota in sem_foto:
        elementos.append(_card_nota_texto(nota.get("legenda") or "", LARGURA_UTIL))
        elementos.append(Spacer(1, 0.25 * cm))

    elementos.append(Spacer(1, 0.2 * cm))
    return elementos


# --------------------------------------------------------- conformidade -----
def _bloco_tabela_conformidade(numero, strings_data, disjuntores_data=None):
    cabecalho = _titulo_com_barra(numero, "Tabela de Conformidade Elétrica (CC e CA)")
    cabecalho.append(Paragraph(
        "Os testes de medição de tensão e isolamento/flutuação para cada String "
        "resultaram nos seguintes parâmetros:", CORPO))
    cabecalho.append(Spacer(1, 0.25 * cm))

    disjuntores_data = disjuntores_data or []
    if not strings_data and not disjuntores_data:
        cabecalho.append(Paragraph("Nenhuma string registrada.", CORPO))
        return [KeepTogether(cabecalho)]

    linhas = [[Paragraph("CIRCUITO / PARÂMETRO AVALIADO", CAB_TABELA),
               Paragraph("MEDIÇÃO OBTIDA", CAB_TABELA),
               Paragraph("STATUS DE CONFORMIDADE", CAB_TABELA)]]
    extra = []
    idx = 1

    def linha_grupo(texto):
        nonlocal idx
        linhas.append([Paragraph(texto, GRUPO_TABELA), "", ""])
        extra.append(("SPAN", (0, idx), (-1, idx)))
        extra.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F8FAFC")))
        idx += 1

    def linha_param(nome, valor, unidade, status):
        nonlocal idx
        if valor is None:
            valor_txt, cel_status = "—", Paragraph("—", CORPO_TABELA)
        else:
            conforme = (status or "").upper() == "CONFORME"
            valor_txt = f"{valor} {unidade}"
            cel_status = _Pilula("CONFORME" if conforme else "NÃO CONFORME", conforme)
        linhas.append([Paragraph(nome, CORPO_TABELA), Paragraph(valor_txt, CORPO_TABELA),
                       cel_status])
        idx += 1

    for s in strings_data:
        nome = s.get("string_nome", "")
        linha_grupo(nome.upper())
        linha_param(f"Tensão de Operação ({nome})", s.get("tensao_vcc"), "Vcc",
                    s.get("status_tensao") or s.get("status"))
        linha_param("Teste Flutuação (+) / Terra", s.get("flutuacao_positivo"), "Vcc",
                    s.get("status_flutuacao_positivo") or s.get("status"))
        linha_param("Teste Flutuação (-) / Terra", s.get("flutuacao_negativo"), "Vcc",
                    s.get("status_flutuacao_negativo") or s.get("status"))
        if s.get("neutro_valor") is not None:
            linha_param("Teste de Neutro", s.get("neutro_valor"), "Vcc",
                        s.get("status_neutro") or s.get("status"))

    if disjuntores_data:
        linha_grupo("CIRCUITO DE CORRENTE ALTERNADA (CA)")
        for d in disjuntores_data:
            nome = d.get("nome") or "Disjuntor"
            volt = d.get("voltagem") or "220V"
            tipo = d.get("tipo") or "Bifásico"
            st = d.get("status")
            # Subtítulo por disjuntor: nome, voltagem nominal e tipo.
            linha_grupo(f"{nome.upper()} — {volt} — {tipo.upper()}")
            linha_param(f"Tensão de Linha ({nome})", d.get("valor_medido"), "V", st)
            linha_param(f"Tensão de Fase ({nome})", d.get("neutro_valor"), "V",
                        d.get("status_neutro") or st)
            linha_param(f"Corrente de Injeção ({nome})",
                        d.get("corrente_injecao_valor"), "A",
                        d.get("corrente_injecao_status") or st)

    tabela = _tabela_base(linhas, [9 * cm, 4 * cm, 5 * cm], extra)
    tabela.repeatRows = 1
    # Título + intro + tabela juntos (se couber numa página): evita grupo órfão.
    return [KeepTogether(cabecalho + [tabela]), Spacer(1, 0.4 * cm)]


# ------------------------------------------------------ "Página X de Y" -----
class NumberedCanvas(_canvas_mod.Canvas):
    def __init__(self, *args, **kwargs):
        _canvas_mod.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setFont(FONTE, 8)
            self.setFillColor(COR_TEXTO_SEC)
            self.drawRightString(A4[0] - 1.5 * cm, 1.2 * cm,
                                 f"Página {self._pageNumber} de {total}")
            _canvas_mod.Canvas.showPage(self)
        _canvas_mod.Canvas.save(self)


# -------------------------------------------------------------- assinatura --
def _bloco_assinatura(empresa, relatorio):
    titulo = _titulo_sem_numero("Encerramento e Responsabilidade Técnica")
    conteudo = [Paragraph(
        "Este relatório foi elaborado e revisado pelo responsável técnico abaixo "
        "identificado, que atesta a veracidade das informações e medições aqui "
        "registradas.", CORPO), Spacer(1, 1.2 * cm)]

    assinatura_path = empresa.get("assinatura_path")
    if assinatura_path and os.path.exists(assinatura_path):
        try:
            img = Image(assinatura_path, width=5.5 * cm, height=2.3 * cm, kind="proportional")
            img.hAlign = "CENTER"
            conteudo += [img, Spacer(1, 0.15 * cm)]
        except Exception:
            conteudo.append(Spacer(1, 2 * cm))
    else:
        conteudo.append(Spacer(1, 2 * cm))

    nome_estilo = ParagraphStyle("NomeAss", parent=_STYLES["Normal"], fontName=FONTE_B,
                                 fontSize=10.5, leading=13, textColor=COR_TITULO,
                                 alignment=TA_CENTER, spaceBefore=4)
    cargo_estilo = ParagraphStyle("CargoAss", parent=_STYLES["Normal"], fontName=FONTE,
                                  fontSize=9, leading=12, textColor=COR_TEXTO_SEC,
                                  alignment=TA_CENTER)

    linha = Table([[""]], colWidths=[7 * cm])
    linha.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.7, COR_TEXTO_SEC)]))
    linha.hAlign = "CENTER"
    conteudo.append(linha)

    nome_tecnico = (relatorio.get("responsavel_tecnico") or "—").strip()
    registro = (empresa.get("responsavel_registro") or "").strip()
    cargo = "Responsável Técnico"
    if registro:
        cargo += f" — {registro}" if "crt" in registro.lower() else f" — CRT: {registro}"
    conteudo += [Paragraph(nome_tecnico, nome_estilo), Paragraph(cargo, cargo_estilo),
                 Paragraph(empresa.get("nome", ""), cargo_estilo)]
    return [KeepTogether(titulo + conteudo)]


# ------------------------------------------------------------------ entrada --
def gerar_relatorio_pdf(caminho_pdf, empresa, cliente, relatorio,
                         secoes_ativas, fotos_por_secao, strings_data,
                         disjuntores_data=None):
    """Monta e salva o PDF final no padrão visual da Solaz Inovação.

    `disjuntores_data`: lista de dicts {nome, voltagem, tipo, valor_medido,
    status, neutro_valor, status_neutro, corrente_injecao_valor,
    corrente_injecao_status}. Por disjuntor são exibidos o tipo
    (Bifásico/Trifásico) e as 3 medições com seus status: Tensão de Linha
    (valor_medido), Tensão de Fase (neutro_valor) e Corrente de Injeção
    (corrente_injecao_valor).
    """
    pasta = os.path.dirname(caminho_pdf)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    doc = _criar_documento(
        caminho_pdf, empresa.get("logo_path"), relatorio["codigo"],
        cliente.get("nome_razao_social", ""), relatorio.get("revisao"),
        relatorio.get("data_servico"), empresa.get("nome", ""),
    )

    story = []
    story += _bloco_capa(empresa, cliente, relatorio)
    story += _bloco_sumario(secoes_ativas)
    story += _bloco_objetivo(relatorio)

    numero = 2
    for secao in secoes_ativas:
        if secao == "tabela_conformidade":
            story += _bloco_tabela_conformidade(numero, strings_data, disjuntores_data)
        else:
            story += _bloco_fotos(secao, numero, fotos_por_secao.get(secao, []))
        numero += 1

    story += _bloco_assinatura(empresa, relatorio)
    doc.build(story, canvasmaker=NumberedCanvas)
    return caminho_pdf
