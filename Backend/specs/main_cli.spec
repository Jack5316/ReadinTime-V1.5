# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# PyInstaller runs with CWD set to the spec's directory
SPEC_DIR = Path.cwd()                 # .../backend-api/specs
BASE_DIR = SPEC_DIR.parent              # .../backend-api
HOOKS_DIR = BASE_DIR / "hooks"
SCRIPT = BASE_DIR / "main_cli.py"     # point to the real script

block_cipher = None

a = Analysis(
    [str(SCRIPT)],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=[],  # Do NOT bundle models or data - they'll be in external Data/ folder
    hookspath=[str(HOOKS_DIR)],
    hiddenimports=['chatterbox', 'chatterbox.tts', 'chatterbox.vc', 'chatterbox.models'],
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
    name='main_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    onefile = True
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main_cli',
)