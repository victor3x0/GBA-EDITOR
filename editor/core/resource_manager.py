"""ResourceManager — collection générique de Resource persistée sur disque
(un fichier JSON par item, dans un dossier). Utilitaire d'I/O générique,
réutilisé par Project pour chacune de ses collections (scenes, sprites,
backgrounds, prefabs, sfx, music, fonts, palettes)."""

import json
from pathlib import Path
from typing import Generic, Iterator, Optional, Type, TypeVar

from core.models.resource import Resource

T = TypeVar("T", bound=Resource)


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})

def safe_filename(name: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique (tmp → rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)   # atomique sur NTFS/ext4
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class ResourceManager(Generic[T]):
    """
    Gère une collection de Resource d'un type donné, persistée dans
    `directory/<name>.json`. Se comporte comme une liste (itération,
    len, indexation, append) pour rester un drop-in replacement des
    anciennes `list[Actor]` / `list[Background]` etc.
    """

    def __init__(self, directory: Path, cls: Type[T]):
        self.dir = directory
        self.cls = cls
        self.items: list[T] = []
        self._pending_delete: list[T] = []

    # -- accès liste --
    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx) -> T:
        return self.items[idx]

    def append(self, item: T) -> T:
        self.items.append(item)
        return item

    def remove(self, item: T):
        if item in self.items:
            self.items.remove(item)

    def __contains__(self, item) -> bool:
        return item in self.items

    # -- lookup --
    def get(self, name: str) -> Optional[T]:
        return next((i for i in self.items if i.name == name), None)

    # -- I/O --
    def _path(self, name: str) -> Path:
        return self.dir / f"{safe_filename(name)}.json"

    def save(self, item: T):
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path(item.name), json.dumps(item.to_dict(), indent=2, ensure_ascii=False))

    def save_all(self):
        for item in self.items:
            self.save(item)

    def load(self):
        self.items = []
        if not self.dir.exists():
            return
        for f in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                self.items.append(self.cls.from_dict(d))
            except Exception as e:
                print(f"[project] erreur lecture {self.cls.__name__} {f.name}: {e}")

    def load_one(self, name: str) -> Optional[T]:
        """Recharge un seul item depuis le disque et met à jour la liste en place."""
        path = self._path(name)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            new_item = self.cls.from_dict(d)
            for i, item in enumerate(self.items):
                if item.name == name:
                    self.items[i] = new_item
                    return new_item
            self.items.append(new_item)
            return new_item
        except Exception as e:
            print(f"[project] erreur reload {self.cls.__name__} {name}: {e}")
            return None

    def delete(self, item: T):
        """Suppression immédiate (JSON effacé maintenant)."""
        path = self._path(item.name)
        if path.exists():
            path.unlink()
        self.remove(item)
        self._pending_delete = [x for x in self._pending_delete if x is not item]

    def soft_delete(self, item: T):
        """Suppression différée : retire de la liste en mémoire, JSON effacé à la fermeture."""
        self.remove(item)
        if item not in self._pending_delete:
            self._pending_delete.append(item)

    def restore(self, item: T):
        """Annule un soft_delete : remet l'item dans la liste et le resauvegarde."""
        self._pending_delete = [x for x in self._pending_delete if x is not item]
        if item not in self.items:
            self.items.append(item)
        self.save(item)

    def commit_deletes(self):
        """Efface définitivement les JSONs en attente (appeler à la fermeture)."""
        for item in self._pending_delete:
            path = self._path(item.name)
            if path.exists():
                path.unlink()
        self._pending_delete.clear()

    def rename(self, item: T, new_name: str):
        old_path = self._path(item.name)
        if old_path.exists():
            old_path.unlink()
        item.name = new_name
        self.save(item)
