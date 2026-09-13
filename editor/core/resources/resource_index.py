"""Index léger d'une collection de ressources persistées.

Un :class:`ResourceIndex` ne désérialise jamais un asset : il répond seulement
à « quels fichiers existent ? » et « où se trouve celui-ci ? ». C'est la
première moitié d'un chargement paresseux ; le cache d'objets reste dans
``ResourceStore``.
"""

from __future__ import annotations

from pathlib import Path


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})


def safe_filename(name: str) -> str:
    """Forme disque canonique d'un nom de ressource sous Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


class ResourceIndex:
    """Inventaire ``nom de ressource → fichier`` d'une collection.

    Le nom exposé est le stem du fichier : comme dans ``ResourceStore``, le
    fichier est l'identité faisant foi lorsqu'un champ ``name`` du JSON a
    dérivé. Les entrées sont rangées par nom pour rendre les écrans et les tests
    déterministes.
    """

    def __init__(self, directory: Path, suffix: str = ".json"):
        self.directory = directory
        self.suffix = suffix
        self._paths: dict[str, Path] = {}

    def scan(self) -> None:
        """Reconstruit l'inventaire sans ouvrir le contenu des fichiers."""
        if not self.directory.exists():
            self._paths = {}
            return
        self._paths = {
            path.stem: path
            for path in sorted(self.directory.glob(f"*{self.suffix}"))
            if path.is_file()
        }

    def names(self) -> tuple[str, ...]:
        """Noms connus, dans l'ordre stable du système de fichiers projet."""
        return tuple(self._paths)

    def path_for(self, name: str) -> Path | None:
        """Chemin du sidecar nommé ``name``, ou ``None`` s'il n'est pas indexé."""
        return self._paths.get(safe_filename(name))

    def record(self, name: str, path: Path | None = None) -> None:
        """Enregistre une écriture connue sans rescanner toute la collection."""
        stem = safe_filename(name)
        self._paths[stem] = path or self.directory / f"{stem}{self.suffix}"

    def forget(self, name: str) -> None:
        """Retire une ressource effacée de l'inventaire mémoire."""
        self._paths.pop(safe_filename(name), None)

    def __contains__(self, name: str) -> bool:
        return self.path_for(name) is not None
