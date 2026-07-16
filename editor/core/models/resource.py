"""Resource — base commune à tous les objets moteur identifiés par un nom et
stockés en JSON (cf. core/resource_manager.ResourceManager pour la persistance)."""

import dataclasses
from dataclasses import dataclass, fields
from typing import TypeVar


@dataclass
class Resource:
    """
    Base pour tout objet identifié par un nom et stocké en JSON.
    to_dict/from_dict génériques via dataclasses ; les types avec des
    champs imbriqués non-dataclass-natifs (listes d'autres dataclasses)
    peuvent surcharger ces deux méthodes.
    """
    name: str = "resource"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})


T = TypeVar("T", bound=Resource)


# Mime types pour le drag&drop interne à l'éditeur (utilisés par window.py
# et scene_editor.py — définis ici pour éviter un import circulaire entre eux).
MIME_PREFAB_TEMPLATE = "application/x-gba-prefab-template"  # drag Prefab → instancier + placer dans scène
MIME_SCRIPT          = "application/x-gba-script"
