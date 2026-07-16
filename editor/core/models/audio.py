"""Sfx / Music / Font — assets audio et police, stockés dans project/{sfx,music,fonts}/{name}.json.

TODO: champs à définir ensemble (format wav/source brut vs converti Maxmod,
volume, pitch, charset, largeur fixe/variable, spritesheet glyphes...)."""

from dataclasses import dataclass
from typing import Optional

from core.models.resource import Resource


@dataclass
class Sfx(Resource):
    name: str = "sfx"
    asset: Optional[str] = None
    volume: int = 255


# Extensions reconnues dans assets/sfx/ et assets/music/ (fichiers bruts
# sans sidecar) — utilisées à la fois par la resynchronisation au chargement
# du projet (Project.load) et par le ProjectWatcher pour le live-reload.
SFX_FILE_EXTS   = {".wav", ".ogg", ".mp3"}
MUSIC_FILE_EXTS = {".wav", ".mod", ".xm", ".s3m", ".it", ".mp3"}


@dataclass
class Music(Resource):
    name: str = "music"
    asset: Optional[str] = None
    loop: bool = True
    volume: int = 255


@dataclass
class Font(Resource):
    name: str = "font"
    asset: Optional[str] = None
