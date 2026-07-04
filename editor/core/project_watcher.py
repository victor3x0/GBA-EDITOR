"""
project_watcher.py — Surveillance des fichiers projet en temps réel.

Principe :
  - assets/  → surveillé récursivement. Tout fichier déposé ou supprimé ici
               est détecté et notifié via asset_appeared / asset_removed.
               Les .lua émettent lua_changed directement.
  - project/ → seuls les JSONs de scènes et prefabs sont surveillés (éditeur
               interne). Les sidecars sprites/backgrounds vivent dans assets/.

Signaux principaux
------------------
asset_appeared(path)  — nouveau fichier brut dans assets/ (PNG, WAV, MOD…)
asset_removed(path)   — fichier supprimé de assets/
asset_modified(path)  — fichier existant modifié dans assets/ (ex. PNG mis à jour)
lua_changed(path)     — .lua modifié ou créé dans assets/scripts/
scene_changed(path)   — .json de scène modifié dans project/scenes/

Notes QFileSystemWatcher :
- fileChanged peut supprimer le fichier de la liste après un save atomique
  (delete+create) — on le re-ajoute systématiquement.
- Debounce par fichier (200 ms) pour ne pas spammer sur les sauvegardes en rafales.
"""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QFileSystemWatcher


# Extensions considérées comme des assets bruts utilisateur
_ASSET_SUFFIXES = {".png", ".bmp", ".wav", ".mod", ".xm", ".s3m", ".it", ".mp3", ".ogg"}
_LUA_SUFFIX     = ".lua"
_JSON_SUFFIX    = ".json"


class ProjectWatcher(QObject):
    """
    Surveille le répertoire d'un projet et notifie les changements de fichiers.

    assets/   → asset_appeared / asset_removed / asset_modified / lua_changed
    project/  → scene_changed
    """

    asset_appeared = pyqtSignal(str)   # nouveau fichier brut dans assets/
    asset_removed  = pyqtSignal(str)   # fichier supprimé de assets/
    asset_modified = pyqtSignal(str)   # fichier existant modifié dans assets/
    lua_changed    = pyqtSignal(str)   # .lua créé ou modifié dans assets/scripts/
    scene_changed  = pyqtSignal(str)   # .json de scène modifié dans project/scenes/

    _DEBOUNCE_MS = 200

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._timers: dict[str, QTimer] = {}
        self._project_root: Optional[Path] = None
        self._suppress = False

        # snapshot des fichiers connus dans chaque dossier surveillé
        # dir_str -> set[file_str]
        self._dir_snapshots: dict[str, set[str]] = {}

    # ── API publique ────────────────────────────────────────────────

    def watch_project(self, project_path: Path):
        """Lance la surveillance d'un projet."""
        self._clear()
        self._project_root = project_path

        # Dossiers à surveiller dans assets/
        assets_root = project_path / "assets"
        asset_dirs = [
            assets_root,
            assets_root / "sprites",
            assets_root / "backgrounds",
            assets_root / "sounds",
            assets_root / "sfx",
            assets_root / "music",
            assets_root / "fonts",
            assets_root / "scripts",
            assets_root / "scripts" / "actors",
            assets_root / "scripts" / "scenes",
            assets_root / "scripts" / "behaviors",
        ]

        # Dossiers project/ (éditeur uniquement)
        project_dirs = [
            project_path / "project" / "scenes",
            project_path / "project" / "prefab",
            project_path / "project" / "backgrounds",
        ]

        for d in asset_dirs + project_dirs:
            if d.exists():
                self._watcher.addPath(str(d))
                self._dir_snapshots[str(d)] = self._scan_dir(d)

        self._index_files(project_path)

    def unwatch(self):
        self._clear()

    @contextmanager
    def suspended(self):
        """Désactive temporairement les notifications pendant une sauvegarde interne."""
        paths = list(self._watcher.files())
        dirs  = list(self._watcher.directories())
        if paths:
            self._watcher.removePaths(paths)
        if dirs:
            self._watcher.removePaths(dirs)
        self._suppress = True
        try:
            yield
        finally:
            for t in list(self._timers.values()):
                t.stop()
            self._timers.clear()
            if paths:
                self._watcher.addPaths(paths)
            if dirs:
                self._watcher.addPaths(dirs)
            QTimer.singleShot(self._DEBOUNCE_MS + 150, self._clear_suppress)

    # ── Interne ─────────────────────────────────────────────────────

    def _scan_dir(self, d: Path) -> set[str]:
        """Retourne l'ensemble des fichiers pertinents présents dans d (non-récursif)."""
        if not d.exists():
            return set()
        return {
            str(f) for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in (_ASSET_SUFFIXES | {_LUA_SUFFIX, _JSON_SUFFIX})
        }

    def _clear(self):
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        for t in self._timers.values():
            t.stop()
        self._timers.clear()
        self._dir_snapshots.clear()

    def _index_files(self, project_path: Path):
        """Ajoute tous les fichiers pertinents à la surveillance."""
        assets_root = project_path / "assets"
        asset_subdirs = ["sprites", "backgrounds", "sounds", "sfx", "music", "fonts",
                         "scripts", "scripts/actors", "scripts/scenes", "scripts/behaviors"]
        for subdir in asset_subdirs:
            d = assets_root / subdir
            if d.exists():
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() in (_ASSET_SUFFIXES | {_LUA_SUFFIX}):
                        self._watcher.addPath(str(f))

        # JSONs de scènes (éditeur)
        scenes_dir = project_path / "project" / "scenes"
        if scenes_dir.exists():
            for f in scenes_dir.glob("*.json"):
                self._watcher.addPath(str(f))

    def _clear_suppress(self):
        self._suppress = False

    def _on_file_changed(self, path_str: str):
        """Fichier existant modifié (éditeur externe)."""
        path = Path(path_str)
        if path.exists():
            self._watcher.addPath(path_str)

        if self._suppress:
            return

        if path_str in self._timers:
            self._timers[path_str].stop()

        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(self._DEBOUNCE_MS)
        t.timeout.connect(lambda p=path_str: self._emit_modified(p))
        self._timers[path_str] = t
        t.start()

    def _on_dir_changed(self, dir_str: str):
        """Un fichier a été créé ou supprimé dans un répertoire surveillé."""
        d = Path(dir_str)
        old_snap = self._dir_snapshots.get(dir_str, set())

        if not d.exists():
            # Dossier lui-même supprimé
            for path_str in old_snap:
                self.asset_removed.emit(path_str)
            self._dir_snapshots.pop(dir_str, None)
            return

        new_snap = self._scan_dir(d)
        self._dir_snapshots[dir_str] = new_snap

        # Fichiers apparus
        for path_str in new_snap - old_snap:
            path = Path(path_str)
            self._watcher.addPath(path_str)
            if path.suffix.lower() == _LUA_SUFFIX:
                self.lua_changed.emit(path_str)
            elif path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_appeared.emit(path_str)

        # Fichiers disparus
        for path_str in old_snap - new_snap:
            path = Path(path_str)
            self._watcher.removePath(path_str)
            if path.suffix.lower() in _ASSET_SUFFIXES:
                self.asset_removed.emit(path_str)

    def _emit_modified(self, path_str: str):
        """Émet le bon signal pour un fichier modifié."""
        path = Path(path_str)
        suffix = path.suffix.lower()

        if suffix == _LUA_SUFFIX:
            self.lua_changed.emit(path_str)
        elif suffix == _JSON_SUFFIX:
            parent = path.parent.name
            if parent == "scenes":
                self.scene_changed.emit(path_str)
        elif suffix in _ASSET_SUFFIXES:
            self.asset_modified.emit(path_str)
