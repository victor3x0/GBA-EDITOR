"""Dossiers d'assets — métadonnées d'organisation, réutilisables par famille.

Un même besoin traverse tout l'éditeur : ranger des assets dans des dossiers que
l'auteur crée. Les scènes en sont le premier client (les groupes du Graphe et les
dossiers du project viewer sont LE MÊME objet), mais sprites, prefabs, fonds…
recevront la même capacité. Elle vit donc ici, une fois, indexée par **famille**
(`scenes`, `sprites`, …) — jamais recopiée par écran.

Ces données ne changent ni le jeu, ni le build, ni le JSON de gameplay : un
dossier ne fait que choisir le parent visuel d'un asset. Sidecar d'éditeur sous
`project/editor/`, même patron que `scene-tree.json` (écriture atomique, clé =
identité durable de l'asset, orphelins purgés à `prune`). Les dossiers sont
**imbricables** (`parent_id`) : un dossier peut en contenir un autre.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import json

from core.resources.resource_store import atomic_write
from core.models import project_json


@dataclass(frozen=True)
class AssetFolder:
    id: str
    name: str
    parent_id: str | None
    members: tuple[str, ...]
    color: str = ""


class AssetFolderStore:
    """Lit et écrit les dossiers d'auteur, par famille et par clé durable.

    Une clé de membre est l'identité de l'asset dans sa famille — le nom d'une
    scène, d'un sprite… Un asset est membre d'au plus un dossier ; un dossier est
    enfant d'au plus un autre dossier de la même famille.
    """

    _VERSION = 1

    def __init__(self, project_root: Path):
        self._path = Path(project_root) / "project" / "editor" / "asset-folders.json"
        self._data: dict = {"version": self._VERSION, "families": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        families = raw.get("families") if isinstance(raw, dict) else None
        if isinstance(families, dict):
            self._data = {"version": self._VERSION, "families": families}

    def _family(self, family: str) -> dict:
        fam = self._data["families"].setdefault(family, {})
        if not isinstance(fam.get("folders"), list):
            fam["folders"] = []
        return fam

    def _raw_folder(self, family: str, folder_id: str | None) -> dict | None:
        if not folder_id:
            return None
        return next((f for f in self._family(family)["folders"]
                     if isinstance(f, dict) and f.get("id") == folder_id), None)

    @staticmethod
    def _to_folder(raw) -> AssetFolder | None:
        if not isinstance(raw, dict):
            return None
        fid = str(raw.get("id") or "")
        name = str(raw.get("name") or "")
        if not fid or not name:
            return None
        members = raw.get("members")
        members = tuple(map(str, members)) if isinstance(members, list) else ()
        parent = raw.get("parent_id")
        return AssetFolder(fid, name, str(parent) if parent else None, members,
                           str(raw.get("color") or ""))

    # ── Lecture ────────────────────────────────────────────────────

    def folders(self, family: str) -> list[AssetFolder]:
        out: list[AssetFolder] = []
        for raw in self._family(family)["folders"]:
            folder = self._to_folder(raw)
            if folder is not None:
                out.append(folder)
        return out

    def folder_of(self, family: str, key: str) -> str | None:
        for folder in self.folders(family):
            if key in folder.members:
                return folder.id
        return None

    def top_ancestor(self, family: str, folder_id: str | None) -> str | None:
        """Dossier racine de la chaîne de parents — le dossier de PREMIER niveau
        qui contient `folder_id` (lui-même s'il est déjà racine). None si absent.
        Sert au Graphe : au niveau racine, une scène appartient à sa boîte de
        premier niveau, quelle que soit sa profondeur d'imbrication."""
        current = folder_id if self._raw_folder(family, folder_id) is not None else None
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            raw = self._raw_folder(family, current)
            parent = raw.get("parent_id") if raw else None
            if not parent or self._raw_folder(family, str(parent)) is None:
                return current
            current = str(parent)
        return current

    # ── Écriture — dossiers ────────────────────────────────────────

    def create_folder(self, family: str, name: str, parent_id: str | None = None) -> AssetFolder:
        clean = name.strip() or "Folder"
        parent = parent_id if self._raw_folder(family, parent_id) is not None else None
        raw = {"id": uuid4().hex, "name": clean, "parent_id": parent,
               "members": [], "color": ""}
        self._family(family)["folders"].append(raw)
        self.save()
        return self._to_folder(raw)  # type: ignore[return-value]

    def create_group(self, family: str, name: str, member_keys=(),
                     parent_id: str | None = None) -> AssetFolder:
        """Crée un dossier, y range d'emblée `member_keys`, EN UNE écriture.

        Le nom est rendu unique parmi les dossiers de la famille (`name`,
        `name_2`…) : un groupe naît nommé, sans pop-up. C'est le geste « créer un
        groupe » partagé par ses deux points d'entrée — le project viewer et le
        Graphe — qui ne diffèrent que par leurs membres (une sélection, ou rien)
        et leur parent (le niveau ouvert du Graphe, ou la racine). Chaque membre
        est d'abord retiré de son dossier actuel : un asset n'est membre que d'un
        dossier."""
        existing = {f.name for f in self.folders(family)}
        unique = name.strip() or "Group"
        if unique in existing:
            i = 2
            while f"{unique}_{i}" in existing:
                i += 1
            unique = f"{unique}_{i}"
        parent = parent_id if self._raw_folder(family, parent_id) is not None else None
        raw = {"id": uuid4().hex, "name": unique, "parent_id": parent,
               "members": [], "color": ""}
        self._family(family)["folders"].append(raw)
        for key in member_keys:
            for f in self._family(family)["folders"]:
                if isinstance(f, dict) and f is not raw and key in (f.get("members") or []):
                    f["members"] = [m for m in f["members"] if m != key]
            if key not in raw["members"]:
                raw["members"].append(key)
        self.save()
        return self._to_folder(raw)  # type: ignore[return-value]

    def rename_folder(self, family: str, folder_id: str, name: str) -> bool:
        clean = name.strip()
        raw = self._raw_folder(family, folder_id)
        if not clean or raw is None or raw.get("name") == clean:
            return False
        raw["name"] = clean
        self.save()
        return True

    def delete_folder(self, family: str, folder_id: str) -> bool:
        """Supprime un dossier SANS supprimer son contenu : ses sous-dossiers et
        ses assets membres remontent au parent du dossier supprimé (racine s'il
        était de premier niveau)."""
        raw = self._raw_folder(family, folder_id)
        if raw is None:
            return False
        parent = raw.get("parent_id")
        parent = str(parent) if parent else None
        folders = self._family(family)["folders"]
        folders[:] = [f for f in folders
                      if not isinstance(f, dict) or f.get("id") != folder_id]
        for f in folders:
            if isinstance(f, dict) and f.get("parent_id") == folder_id:
                f["parent_id"] = parent
        target = self._raw_folder(family, parent)
        if target is not None:
            for member in list(raw.get("members") or []):
                target.setdefault("members", []).append(member)
        self.save()
        return True

    def set_parent(self, family: str, folder_id: str, parent_id: str | None) -> bool:
        """Imbrique un dossier sous un autre. Refuse tout cycle."""
        raw = self._raw_folder(family, folder_id)
        if raw is None:
            return False
        parent = parent_id if parent_id else None
        if parent == folder_id or (parent and self._raw_folder(family, parent) is None):
            return False
        if parent and folder_id in self._ancestors(family, parent):
            return False
        if raw.get("parent_id") == parent:
            return False
        raw["parent_id"] = parent
        self.save()
        return True

    def _ancestors(self, family: str, folder_id: str | None) -> set[str]:
        seen: set[str] = set()
        current = folder_id
        while current and current not in seen:
            seen.add(current)
            raw = self._raw_folder(family, current)
            current = str(raw.get("parent_id")) if raw and raw.get("parent_id") else None
        return seen

    def set_color(self, family: str, folder_id: str, color: str) -> bool:
        raw = self._raw_folder(family, folder_id)
        clean = color.strip()
        if raw is None or raw.get("color", "") == clean:
            return False
        raw["color"] = clean
        self.save()
        return True

    # ── Écriture — appartenance ────────────────────────────────────

    def move_member(self, family: str, key: str, folder_id: str | None) -> bool:
        """Range un asset dans un dossier, ou en racine avec None."""
        target = self._raw_folder(family, folder_id) if folder_id else None
        if folder_id and target is None:
            return False
        changed = False
        for f in self._family(family)["folders"]:
            if not isinstance(f, dict):
                continue
            members = list(f.get("members") or [])
            if key in members:
                f["members"] = [m for m in members if m != key]
                changed = True
        if target is not None and key not in target.setdefault("members", []):
            target["members"].append(key)
            changed = True
        if changed:
            self.save()
        return changed

    def rename_member(self, family: str, before: str, after: str) -> None:
        if before == after:
            return
        changed = False
        for f in self._family(family)["folders"]:
            if not isinstance(f, dict):
                continue
            members = f.get("members") or []
            rewritten = [after if m == before else m for m in members]
            if rewritten != members:
                f["members"] = list(dict.fromkeys(rewritten))
                changed = True
        if changed:
            self.save()

    def prune(self, family: str, valid_keys: set[str]) -> None:
        """Oublie les assets disparus et répare un `parent_id` orphelin. Ne
        supprime jamais un dossier."""
        changed = False
        ids = {f.get("id") for f in self._family(family)["folders"] if isinstance(f, dict)}
        for f in self._family(family)["folders"]:
            if not isinstance(f, dict):
                continue
            members = list(f.get("members") or [])
            kept = [m for m in members if m in valid_keys]
            if kept != members:
                f["members"] = kept
                changed = True
            parent = f.get("parent_id")
            if parent and parent not in ids:
                f["parent_id"] = None
                changed = True
        if changed:
            self.save()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path, project_json.dumps(self._data))
