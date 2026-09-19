"""Empreinte des dossiers source au dernier rattrapage — la porte de la
réconciliation incrémentale.

La réconciliation à l'ouverture (`core.resources.asset_reconciliation`) rattrape
ce qui a changé sur le disque *éditeur fermé*. Elle est idempotente, mais refait
tout son travail à chaque fois, même à vide. Ce manifeste répond, par dossier
source, à la seule question qui permet de la sauter : « le disque a-t-il bougé
depuis la dernière fois ? »

Il ne devient JAMAIS une source de vérité — la réconciliation dérive toujours
tout du disque. Il ne porte que l'empreinte `nom → "taille:mtime_ns"` des
fichiers vus à la fin de la dernière passe. Sidecar d'éditeur sous
`project/editor/`, frère de `scene-graph.json`, jamais livré en ROM.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

from core.resources.resource_store import atomic_write
from core.models import project_json


class ReconcileManifest:
    """Lit et écrit l'empreinte des dossiers source, indexée par dossier."""

    _VERSION = 1

    def __init__(self, project_root: Path):
        self._root = Path(project_root)
        self._path = self._root / "project" / "editor" / "reconcile-manifest.json"
        self._data: dict = {"version": self._VERSION, "dirs": {}}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        dirs = raw.get("dirs") if isinstance(raw, dict) else None
        self._data = {"version": self._VERSION,
                      "dirs": dirs if isinstance(dirs, dict) else {}}

    def _key(self, directory: Path) -> str:
        """Clé stable d'un dossier : son chemin relatif au projet, en posix.

        Relatif plutôt qu'absolu pour que le manifeste survive au déplacement du
        projet (un clone à trois n'ouvre pas le même chemin absolu)."""
        directory = Path(directory)
        try:
            rel = directory.resolve().relative_to(self._root.resolve())
        except ValueError:
            rel = directory
        return rel.as_posix()

    @staticmethod
    def _scan(directory: Path, exts) -> dict[str, str]:
        """Empreinte courante d'un dossier : `nom → "taille:mtime_ns"`.

        Un seul `os.scandir` — le `DirEntry` porte taille et mtime sans stat de
        plus. Ne retient que les fichiers dont l'extension est dans `exts`
        (comparée en minuscules, comme les passes de réconciliation)."""
        out: dict[str, str] = {}
        exts = {e.lower() for e in exts}
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if not entry.is_file():
                        continue
                    if os.path.splitext(entry.name)[1].lower() not in exts:
                        continue
                    st = entry.stat()
                    out[entry.name] = f"{st.st_size}:{st.st_mtime_ns}"
        except (OSError, FileNotFoundError):
            return out
        return out

    def matches(self, directory: Path, exts) -> bool:
        """Le dossier a-t-il la MÊME empreinte qu'au dernier `record` ?

        Absent du manifeste → faux (premier lancement, clone frais) : la passe
        doit tourner, puis s'enregistrer."""
        stored = self._data["dirs"].get(self._key(directory))
        if not isinstance(stored, dict):
            return False
        return stored == self._scan(directory, exts)

    def record(self, directory: Path, exts) -> None:
        """Mémorise l'empreinte courante du dossier — appelé à la FIN d'une passe
        qui a tourné."""
        self._data["dirs"][self._key(directory)] = self._scan(directory, exts)
        self.save()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path, project_json.dumps(self._data))
