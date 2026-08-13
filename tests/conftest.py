"""Racine des tests — met `editor/` sur `sys.path`.

L'éditeur s'importe depuis `editor/` (`from core...`, `from codegen...`), jamais
depuis la racine du dépôt : c'est la porte qu'emprunte `main.py` au lancement et
celle que suit `tools/check_architecture.py`. Les tests entrent par la même,
sinon ils vérifieraient une arborescence de modules que personne n'exécute.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR   = Path(__file__).resolve().parent.parent
EDITOR_DIR = REPO_DIR / "editor"

if str(EDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_DIR))
