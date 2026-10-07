"""
Utilitários de imagem — padroniza fotos no formato 4:3 (sem distorcer),
usado tanto no upload quanto na composição do PDF.
"""
import os
import shutil
import tempfile
import time
import uuid

from PIL import Image, ImageOps

from config import FOTOS_DIR, FOTO_ASPECT_RATIO

# Fotos temporárias de relatório: reduzidas e comprimidas para poupar RAM e
# acelerar a geração do PDF (uma foto 4K de ~10 MB vira algumas centenas de KB).
_PREFIXO_TEMP = "solaz_rmp_"
_FOTO_TEMP_MAX = (1920, 1080)      # limite em px (mantém a proporção)
# Tamanho mínimo que o decode reduzido (draft) deve preservar. Quadrado de
# propósito: uma foto de celular em retrato vem gravada deitada (EXIF) e só
# gira depois; com um alvo retangular ela perderia resolução na rotação.
_FOTO_TEMP_DRAFT = (1440, 1440)
_FOTO_TEMP_QUALIDADE = 80          # JPEG, com optimize=True
_IDADE_MINIMA_ORFAOS_S = 3600      # só apaga temporários com mais de 1 h


def salvar_foto_padronizada(origem_path: str, subpasta: str = "") -> str:
    """
    Copia a imagem de origem para o diretório de fotos da aplicação,
    recortando (center-crop) para a proporção 4:3 definida em config,
    e retorna o novo caminho salvo. Usado para fotos PERMANENTES do
    cadastro (cliente/empresa) — não para fotos de relatório, que usam
    `salvar_foto_temporaria` (ver abaixo) e não deixam resíduo em disco.
    """
    destino_dir = os.path.join(FOTOS_DIR, subpasta) if subpasta else FOTOS_DIR
    os.makedirs(destino_dir, exist_ok=True)

    nome_arquivo = f"{uuid.uuid4().hex}.jpg"
    destino_path = os.path.join(destino_dir, nome_arquivo)

    with Image.open(origem_path) as img:
        img = ImageOps.exif_transpose(img)  # corrige rotação de fotos de celular
        img = img.convert("RGB")
        img_ajustada = _crop_to_aspect(img, FOTO_ASPECT_RATIO)
        img_ajustada.save(destino_path, "JPEG", quality=88)

    return destino_path


def criar_pasta_temporaria() -> str:
    """Cria um diretório temporário isolado para as fotos de UM relatório
    em construção. Nada aqui é salvo na pasta permanente do app — depois
    que o PDF é compilado, `limpar_pasta_temporaria` apaga tudo."""
    return tempfile.mkdtemp(prefix=_PREFIXO_TEMP)


def salvar_foto_temporaria(origem_path: str, diretorio_temp: str) -> str:
    """Versão de `salvar_foto_padronizada` que grava dentro do diretório
    temporário do relatório (não em `data/fotos/`), para que a foto some
    do disco assim que o PDF for finalizado e a pasta temporária limpa —
    política de 'armazenamento leve, sem persistência residual de fotos'.

    Não copia o arquivo bruto: corrige a rotação EXIF, mantém o recorte 4:3,
    reduz para no máximo 1920x1080 px (sem distorcer) e salva em JPEG
    qualidade 80 com optimize=True. Para JPEG, o `draft` faz o Pillow
    decodificar já em tamanho reduzido, então a foto 4K nem chega a ocupar a
    RAM inteira durante a conversão."""
    os.makedirs(diretorio_temp, exist_ok=True)
    nome_arquivo = f"{uuid.uuid4().hex}.jpg"
    destino_path = os.path.join(diretorio_temp, nome_arquivo)

    with Image.open(origem_path) as img:
        img.draft("RGB", _FOTO_TEMP_DRAFT)   # só atua em JPEG; no-op nos demais
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img = _crop_to_aspect(img, FOTO_ASPECT_RATIO)
        img.thumbnail(_FOTO_TEMP_MAX, Image.LANCZOS)
        img.save(destino_path, "JPEG", quality=_FOTO_TEMP_QUALIDADE, optimize=True)

    return destino_path


def limpar_pasta_temporaria(diretorio_temp: str = None):
    """Remove um diretório temporário e todo o seu conteúdo. Chamar sempre
    ao final da geração do relatório (sucesso ou falha) — só o .pdf final
    deve sobreviver na pasta do cliente.

    Sem argumento (`limpar_pasta_temporaria()`): limpeza PREVENTIVA — varre a
    pasta temporária do sistema e apaga as pastas `solaz_rmp_*` esquecidas por
    um fechamento inesperado em execuções anteriores (só as com mais de 1 h,
    para nunca atingir um relatório em andamento)."""
    if diretorio_temp is None:
        _limpar_temporarios_orfaos()
        return
    if diretorio_temp and os.path.isdir(diretorio_temp):
        shutil.rmtree(diretorio_temp, ignore_errors=True)


def _limpar_temporarios_orfaos():
    base = tempfile.gettempdir()
    agora = time.time()
    try:
        nomes = os.listdir(base)
    except OSError:
        return
    for nome in nomes:
        if not nome.startswith(_PREFIXO_TEMP):
            continue
        caminho = os.path.join(base, nome)
        try:
            if os.path.isdir(caminho) and agora - os.path.getmtime(caminho) >= _IDADE_MINIMA_ORFAOS_S:
                shutil.rmtree(caminho, ignore_errors=True)
        except OSError:
            pass


def _crop_to_aspect(img: Image.Image, aspect_ratio: tuple) -> Image.Image:
    """Recorta a imagem (center-crop) para a proporção alvo, sem distorcer."""
    target_w, target_h = aspect_ratio
    target_ratio = target_w / target_h

    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        # imagem mais larga que o alvo -> corta as laterais
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        # imagem mais alta que o alvo -> corta topo/base
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)

    return img.crop(box)


def copiar_arquivo_generico(origem_path: str, destino_dir: str) -> str:
    """Usado para logos e etiquetas — apenas copia preservando extensão."""
    os.makedirs(destino_dir, exist_ok=True)
    ext = os.path.splitext(origem_path)[1].lower() or ".png"
    nome_arquivo = f"{uuid.uuid4().hex}{ext}"
    destino_path = os.path.join(destino_dir, nome_arquivo)
    shutil.copy2(origem_path, destino_path)
    return destino_path
