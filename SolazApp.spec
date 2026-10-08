# -*- mode: python ; coding: utf-8 -*-
#
# Build:   pyinstaller --noconfirm --clean SolazApp.spec
# Saída:   dist/SolazApp/SolazApp.exe  (formato "pasta": abre mais rápido que um
#          .exe único, porque não precisa se descompactar a cada abertura)
# Ícone:   assets/Solaz.ico (já configurado abaixo; não precisa pedir de novo)
import importlib.util
from PyInstaller.utils.hooks import collect_all

datas = [('database/schema.sql', 'database'), ('assets', 'assets')]
binaries = []
hiddenimports = ['babel.numbers', 'segredos']   # segredos.py: token do bot (local, fora do Git)

# Bibliotecas que precisam ir COMPLETAS no executável. Pacotes que não estão
# instalados neste ambiente são ignorados (os nomes mudam entre versões do
# supabase-py: gotrue/supabase_auth, supafunc/supabase_functions).
PACOTES = [
    'customtkinter',
    'supabase', 'supabase_auth', 'gotrue', 'postgrest', 'realtime',
    'storage3', 'supabase_functions', 'supafunc',
    'httpx', 'websockets',
    'telebot',
]
for pacote in PACOTES:
    if importlib.util.find_spec(pacote) is None:
        continue
    d, b, h = collect_all(pacote)
    datas += d; binaries += b; hiddenimports += h


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SolazApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # sem compressão: abre mais rápido e dá menos falso positivo no antivírus
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/Solaz.ico'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SolazApp',
)
