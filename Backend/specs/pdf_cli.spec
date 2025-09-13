# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# PyInstaller runs with CWD set to the spec's directory
SPEC_DIR = Path.cwd()                 # .../backend-api/specs
BASE_DIR = SPEC_DIR.parent              # .../backend-api
HOOKS_DIR = BASE_DIR / "hooks"
SCRIPT = BASE_DIR / "pdf_cli.py"      # point to the real script

block_cipher = None

a = Analysis(
    [str(SCRIPT)],
    pathex=[
        str(BASE_DIR),
        str(BASE_DIR / "markitdown-source" / "packages" / "markitdown" / "src")
    ],
    binaries=[],
    datas=[
        # Bundle the markitdown source package
        (str(BASE_DIR / "markitdown-source" / "packages" / "markitdown" / "src" / "markitdown"), "markitdown"),
        # Bundle magika models from virtual environment
        (str(BASE_DIR / "venv-unified" / "Lib" / "site-packages" / "magika" / "models"), "magika/models"),
    ],
    hookspath=[str(HOOKS_DIR)],
    hiddenimports=[
        'markitdown',
        'markitdown.core',
        'markitdown.extractors',
        'markitdown.processors',
        'magika',
        'magika.models',
        'PyPDF2',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont'
    ],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)



pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pdf_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    onefile=True
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pdf_cli',
)
