"""
core/external_tools.py — chemins des logiciels tiers, réglage du LOGICIEL
(un chemin par machine, comme `core/toolchain.py`), pas du projet.

Portée actuelle : trois chemins configurables depuis l'écran Réglages
(catégorie « External Tools »), pour l'image, le son et la police. Rien ne
les LIT encore ailleurs dans l'éditeur — aucun bouton « Edit externally »
n'existe sur les finders de sprites/fonds/sons/polices. C'est un choix
délibéré (portée resserrée à la demande) : cette classe ne fait qu'exister
et se souvenir, le câblage viendra dans un chantier séparé, quand chaque
finder saura quoi faire d'un chemin vide (proposer l'app par défaut du
système ? refuser silencieusement ? — une question par écran, pas ici).
"""
from __future__ import annotations

import json
from pathlib import Path

from core.toolchain import config_dir

CONFIG_FILE = config_dir() / "external_tools.json"

# (clé de config, libellé écran) — dans l'ordre d'affichage.
TOOL_KINDS: list[tuple[str, str]] = [
    ("image", "Image editor"),
    ("audio", "Audio editor"),
    ("font",  "Font editor"),
]


class ExternalTools:
    """Même forme que `Toolchain` : un petit JSON, chargé une fois, écrit à
    chaque changement."""

    def __init__(self):
        self._config: dict = self._load()

    def _load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._config, indent=2), encoding="utf-8")

    def path(self, kind: str) -> Path | None:
        if p := self._config.get(kind):
            return Path(p)
        return None

    def set_path(self, kind: str, path: Path | None):
        if path:
            self._config[kind] = str(path)
        else:
            self._config.pop(kind, None)
        self.save()
