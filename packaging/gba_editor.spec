# -*- mode: python ; coding: utf-8 -*-
"""
GBA Editor — spec PyInstaller (build onefile).

Usage (depuis la racine du repo) :
    pip install pyinstaller
    pyinstaller packaging/gba_editor.spec --noconfirm

Sortie : dist/GBA Editor.exe — un seul fichier, portable, à distribuer et
lancer tel quel (pas d'installeur).

Notes de packaging :
- Mode onefile : contrepartie du fichier unique, démarrage un peu plus lent
  (le bootloader s'extrait dans un dossier temporaire à chaque lancement) —
  acceptable pour ce type d'outil.
- devkitPro (grit/make/arm-none-eabi-gcc) et mGBA ne sont PAS embarqués :
  ce sont des dépendances système externes, détectées à l'exécution par
  editor/core/toolchain.py et configurables depuis l'éditeur si absentes.
- editor/plugins/** est copié tel quel (datas) : les plugins sont chargés
  dynamiquement via importlib.util.spec_from_file_location() et doivent
  donc exister comme fichiers .py réels sur disque (dans le dossier
  d'extraction temporaire), pas seulement compilés dans le PYZ.
- runtime/ (sibling de editor/ dans le repo) est copié à la racine du
  bundle. editor/codegen/pipeline.py détecte sys.frozen et résout
  RUNTIME_DIR = sys._MEIPASS / "runtime" dans ce cas — identique en
  onefile et onedir, puisque sys._MEIPASS pointe toujours vers le dossier
  d'extraction courant.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

IS_WINDOWS = sys.platform.startswith("win")

REPO_ROOT = Path(SPECPATH).parent
EDITOR_DIR = REPO_ROOT / "editor"

datas = [
    (str(EDITOR_DIR / "plugins"), "plugins"),
    (str(EDITOR_DIR / "scripting" / "api_reference.json"), "scripting"),
    (str(REPO_ROOT / "runtime"), "runtime"),
]
datas += collect_data_files("qtawesome")

excludes = [
    "tkinter",
]

a = Analysis(
    [str(EDITOR_DIR / "main.py")],
    pathex=[str(EDITOR_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GBA Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(REPO_ROOT / "packaging" / "icon.ico") if IS_WINDOWS else None,
)
