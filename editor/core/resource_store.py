"""ResourceStore — collection générique de Resource persistée sur disque
(un fichier JSON par item, dans un dossier). Utilitaire d'I/O générique,
réutilisé par Project pour chacune de ses collections (scenes, sprites,
backgrounds, prefabs, sfx, music, fonts, palettes)."""

import json
import time
from pathlib import Path
from typing import Generic, Iterator, Optional, Type, TypeVar

from core.models.resource import Resource
from core.models import project_json

T = TypeVar("T", bound=Resource)


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})

def safe_filename(name: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
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


# Rename atomique : nb de tentatives et délai entre elles (cf. atomic_write).
_REPLACE_RETRIES = 12
_REPLACE_RETRY_DELAY = 0.02   # 12 × 20 ms ≈ 240 ms de fenêtre de retry


class ResourceStore(Generic[T]):
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

    def path_of(self, item: T) -> Path:
        """Le JSON dans lequel CET item se sauvegarde.

        `item.name` décide du nom de fichier (cf. `_path`) : un appelant qui
        veut savoir si le sidecar d'une ressource existe doit le demander ici,
        et non le déduire du nom d'un fichier source voisin — les deux se
        ressemblent tant que personne n'a renommé, puis divergent en silence."""
        return self._path(item.name)

    def save(self, item: T):
        self.dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path(item.name), project_json.dumps(item.to_dict()))

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
                item = self.cls.from_dict(d)
                # LE NOM DE FICHIER EST L'IDENTITÉ. `save` écrit toujours dans
                # `<name>.json` : un fichier qui ne porte pas le nom qu'il
                # contient a été renommé sur le disque, et c'est le champ qui
                # est périmé, pas le fichier. Le garder ferait exister la même
                # ressource sous deux identités — le rattrapage à l'ouverture
                # cherche l'asset par le STEM de son fichier source, ne le
                # trouverait pas, et en créerait un SECOND à côté du premier,
                # lequel pointe désormais dans le vide (cf.
                # asset_encoding.sync_font_file).
                if safe_filename(item.name) != f.stem:
                    item.name = f.stem
                self.items.append(item)
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
            # Même règle qu'à `load` : le fichier nomme la ressource. Sans ça,
            # un sidecar dont le champ `name` a dérivé n'est jamais reconnu
            # comme celui qu'on recharge, et vient s'AJOUTER à la liste.
            if safe_filename(new_item.name) != safe_filename(name):
                new_item.name = name
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

    def pending_deletes(self) -> list[T]:
        """Les items `soft_delete`és pas encore committés — lecture seule.

        Une famille adossée à un fichier source les relit à la fermeture pour
        emporter AUSSI ce fichier, pas seulement le sidecar : sans quoi le
        `reconcile_*` le retrouverait au prochain lancement et recréerait la
        ressource (cf. project.commit_all_removals). Le store, lui, ne connaît
        que ses JSONs — il n'a pas à savoir ce qu'est un fichier source."""
        return list(self._pending_delete)

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
