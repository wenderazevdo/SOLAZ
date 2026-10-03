"""
Utilitários de imagem — padroniza fotos no formato 4:3 (sem distorcer),
usado tanto no upload quanto na composição do PDF.
"""
import os
import shutil
import tempfile
import uuid

from PIL import Image, ImageOps

from config import FOTOS_DIR, FOTO_ASPECT_RATIO


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
    return tempfile.mkdtemp(prefix="solaz_rmp_")


def salvar_foto_temporaria(origem_path: str, diretorio_temp: str) -> str:
    """Versão de `salvar_foto_padronizada` que grava dentro do diretório
    temporário do relatório (não em `data/fotos/`), para que a foto some
    do disco assim que o PDF for finalizado e a pasta temporária limpa —
    política de 'armazenamento leve, sem persistência residual de fotos'."""
    os.makedirs(diretorio_temp, exist_ok=True)
    nome_arquivo = f"{uuid.uuid4().hex}.jpg"
    destino_path = os.path.join(diretorio_temp, nome_arquivo)

    with Image.open(origem_path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img_ajustada = _crop_to_aspect(img, FOTO_ASPECT_RATIO)
        img_ajustada.save(destino_path, "JPEG", quality=88)

    return destino_path


def limpar_pasta_temporaria(diretorio_temp: str):
    """Remove o diretório temporário e todo o seu conteúdo. Chamar sempre
    ao final da geração do relatório (sucesso ou falha) — só o .pdf final
    deve sobreviver na pasta do cliente."""
    if diretorio_temp and os.path.isdir(diretorio_temp):
        shutil.rmtree(diretorio_temp, ignore_errors=True)


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
