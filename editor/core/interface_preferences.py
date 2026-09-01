"""
core/interface_preferences.py — ce que l'interface MONTRE, réglé par machine.

Réglage du LOGICIEL, comme `core/toolchain.py` et `core/external_tools.py` :
un petit JSON dans le dossier de config utilisateur, jamais dans le projet.

**Pourquoi pas dans `ProjectSettings`.** L'affichage des astuces y a vécu un
temps, et deux choses l'ont sorti de là : `project.json` est versionné, donc
couper les astuces les coupait pour toute l'équipe — y compris pour celui qui
arrive et à qui elles s'adressent ; et un réglage de projet passe par
`SetFieldCmd`, donc **annuler une édition de scène pouvait rebasculer une
préférence de machine**. Un réglage d'application n'a rien à faire dans
l'historique d'un projet, et c'est le vrai argument des deux.

Portée actuelle : une seule préférence, les astuces (le niveau 3 de
`ui/common/notice.py`, ROADMAP v0.11). Le fichier existe pour ce qui décrit
l'AFFICHAGE de l'éditeur — pas pour devenir le tiroir de tout ce qui n'a pas
trouvé de place ailleurs : un réglage qui décrit le JEU va dans
`ProjectSettings`, un chemin de machine dans `toolchain`/`external_tools`.
"""
from __future__ import annotations

import json

from core.toolchain import config_dir

CONFIG_FILE = config_dir() / "interface.json"

# Ce qu'une installation neuve montre. Les astuces sont VRAIES par défaut :
# elles s'adressent d'abord à qui découvre l'éditeur, et celui-là n'ira pas
# les allumer dans un écran de réglages qu'il ne connaît pas encore.
_DEFAULTS = {"show_tips": True}

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Fichier absent au premier lancement, ou illisible : on repart des
            # défauts plutôt que d'empêcher l'éditeur de démarrer pour une
            # préférence d'affichage.
            _cache = {}
    return _cache


def _save():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(_load(), indent=2), encoding="utf-8")


def tips_shown() -> bool:
    """Les astuces (niveau 3) sont-elles affichées ?"""
    return bool(_load().get("show_tips", _DEFAULTS["show_tips"]))


def set_tips_shown(value: bool):
    _load()["show_tips"] = bool(value)
    _save()
