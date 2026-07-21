"""ResourceManager — collection générique de Resource persistée sur disque
(un fichier JSON par item, dans un dossier). Utilitaire d'I/O générique,
réutilisé par Project pour chacune de ses collections (scenes, sprites,
backgrounds, prefabs, sfx, music, fonts, palettes)."""

import json
import time
from pathlib import Path
from typing import Generic, Iterator, Optional, Type, TypeVar

from core.models.resource import Resource

T = TypeVar("T", bound=Resource)


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})

def safe_filename(name: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique (tmp → rename).

    Sous Windows, `os.replace` lève transitoirement PermissionError (WinError 5
    « accès refusé ») ou une sharing violation (WinError 32) quand un autre
    process tient brièvement un handle sur la cible : indexeur, antivirus, ou
    le QFileSystemWatcher qui ré-arme sa surveillance du dossier. C'est très
    probable lors de sauvegardes en rafale (maintien d'une flèche = nudge
    répété, molette continue sur un spinbox). Non rattrapée, l'exception
    remonte hors d'un slot Qt et PyQt6 abandonne le process → crash observé.
    On réessaie donc le rename quelques fois (le verrou transitoire se libère
    en quelques dizaines de ms) avant d'abandonner."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        for attempt in range(_REPLACE_RETRIES):
            try:
                tmp.replace(path)   # atomique sur NTFS/ext4
                return
            except PermissionError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_REPLACE_RETRY_DELAY)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# Rename atomique : nb de tentatives et délai entre elles (cf. _atomic_write).
_REPLACE_RETRIES = 12
_REPLACE_RETRY_DELAY = 0.02   # 12 × 20 ms ≈ 240 ms de fenêtre de retry


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
