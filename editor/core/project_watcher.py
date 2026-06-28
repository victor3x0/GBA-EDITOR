"""
project_watcher.py — Surveillance des fichiers projet en temps réel.

Émet des signaux typés quand des fichiers changent (éditeur externe, build, etc.).
MainWindow s'abonne et déclenche les rafraîchissements appropriés.

Notes QFileSystemWatcher :
- fileChanged peut supprimer le fichier de la liste après un save atomic
  (delete + create) — on le re-ajoute systématiquement.
- Debounce par fichier (200 ms) pour ne pas spammer sur les sauvegardes en rafales.
"""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QFileSystemWatcher


class ProjectWatcher(QObject):
    """
    Surveille le répertoire d'un projet et notifie les changements.

    Signaux
    -------
    lua_changed(path)    — un .lua a changé (créé, modifié, supprimé)
    scene_changed(path)  — un .json de scène a changé
    sprite_changed(path) — un .json de sprite a changé
    asset_changed(path)  — un asset (PNG, WAV…) a changé
    """

    lua_changed    = pyqtSignal(str)
    scene_changed  = pyqtSignal(str)
    sprite_changed = pyqtSignal(str)
    asset_changed  = pyqtSignal(str)

    _DEBOUNCE_MS = 200

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        # timers de debounce par chemin absolu
        self._timers: dict[str, QTimer] = {}
        self._project_root: Optional[Path] = None
        # Supprime les notifications pendant et juste après une sauvegarde interne
        self._suppress = False

    # ── API publique ───────────────────────────────────────────────

    def watch_project(self, project_path: Path):
        """Lance la surveillance d'un projet. Peut être appelé à nouveau pour changer de projet."""
        self._clear()
        self._project_root = project_path

        dirs_to_watch = [
            project_path / "project" / "scenes",
            project_path / "project" / "sprites",
            project_path / "project" / "scripts",
            project_path / "assets",
            project_path / "assets" / "sprites",
            project_path / "assets" / "backgrounds",
        ]
        for d in dirs_to_watch:
            if d.exists():
                self._watcher.addPath(str(d))

        self._index_files(project_path)

    def unwatch(self):
        self._clear()

    @contextmanager
    def suspended(self):
        """
        Désactive temporairement les notifications pendant une sauvegarde interne.
        Evite que nos propres écritures déclenchent un rechargement de projet.

        Usage :
            with self._watcher.suspended():
                project.save_scene(scene)
        """
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
            # Annuler les timers de debounce déjà en vol pour les paths sauvegardés
            # (ils ont pu être déclenchés avant la suppression ou pendant le yield)
            for t in list(self._timers.values()):
                t.stop()
            self._timers.clear()
            if paths:
                self._watcher.addPaths(paths)
            if dirs:
                self._watcher.addPaths(dirs)
            # Lever la suppression APRÈS la fenêtre de debounce pour absorber
            # les notifications OS buffées qui arrivent en différé
            QTimer.singleShot(self._DEBOUNCE_MS + 150, self._clear_suppress)

    # ── Interne ────────────────────────────────────────────────────

    def _clear(self):
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        for t in self._timers.values():
            t.stop()
        self._timers.clear()

    def _index_files(self, project_path: Path):
        """Ajoute tous les fichiers pertinents à la surveillance."""
        patterns = [
            ("project/scripts", "*.lua"),
            ("project/scenes",  "*.json"),
            ("project/sprites", "*.json"),
            ("assets",          "*.png"),
            ("assets/sprites",  "*.png"),
        ]
        for subdir, glob in patterns:
            d = project_path / subdir
            if d.exists():
                for f in d.glob(glob):
                    self._watcher.addPath(str(f))

    def _clear_suppress(self):
        self._suppress = False

    def _on_file_changed(self, path_str: str):
        """Déclenché par QFileSystemWatcher — on debounce avant d'émettre."""
        path = Path(path_str)
        # Re-ajouter : certains éditeurs sauvent en delete+create
        if path.exists():
            self._watcher.addPath(path_str)

        # Ignorer les notifications causées par nos propres sauvegardes internes
        if self._suppress:
            return

        if path_str in self._timers:
            self._timers[path_str].stop()

        t = QTimer(self)
        t.setSingleShot(True)
        t.setInterval(self._DEBOUNCE_MS)
        t.timeout.connect(lambda p=path_str: self._emit(p))
        self._timers[path_str] = t
        t.start()

    def _on_dir_changed(self, dir_str: str):
        """Un fichier a été créé ou supprimé dans un répertoire surveillé."""
        d = Path(dir_str)
        if not d.exists():
            return
        # Re-indexer les nouveaux fichiers dans ce dossier
        for f in d.iterdir():
            if f.suffix in (".lua", ".json", ".png") and str(f) not in self._watcher.files():
                self._watcher.addPath(str(f))
                # Émettre immédiatement pour les nouveaux fichiers
                self._emit(str(f))

    def _emit(self, path_str: str):
        path = Path(path_str)
        suffix = path.suffix.lower()
        name_parts = path.parts

        if suffix == ".lua":
            self.lua_changed.emit(path_str)
        elif suffix == ".json":
            # Distinguer scène vs sprite selon le dossier parent
            parent = path.parent.name
            if parent == "scenes":
                self.scene_changed.emit(path_str)
            elif parent == "sprites":
                self.sprite_changed.emit(path_str)
        elif suffix in (".png", ".bmp", ".wav", ".mod"):
            self.asset_changed.emit(path_str)
