"""
core/project_templates.py — Registre des projets modèles téléchargeables.

Un template pointe vers un sous-dossier du dépôt GitHub de l'éditeur.
GitHub ne sert pas de zip pour un sous-dossier seul : on télécharge le zip
de la branche entière et on n'en extrait que `repo_subdir`. Une fois sur
le disque, le dossier extrait est un projet comme un autre (project.json
et tout) — aucune notion de « template » ne survit à l'extraction, il
s'ouvre par le chemin standard (Project.load).
"""

from __future__ import annotations

import io
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

REPO_ZIP_URL   = "https://github.com/victor3x0/GBA-EDITOR/archive/refs/heads/main.zip"
_REPO_ZIP_ROOT = "GBA-EDITOR-main"


@dataclass(frozen=True)
class ProjectTemplate:
    id:           str
    display_name: str
    description:  str
    repo_subdir:  str   # chemin dans le dépôt, ex. "Project Demo/Pong"

    @property
    def folder_name(self) -> str:
        return Path(self.repo_subdir).name


TEMPLATES: list[ProjectTemplate] = [
    ProjectTemplate(
        id="pong",
        display_name="Pong",
        description="Complete game — scenes, sprites, scripts, music.",
        repo_subdir="Project Demo/Pong",
    ),
]


def target_dir(template: ProjectTemplate, projects_dir: Path) -> Path:
    return projects_dir / template.folder_name


def is_downloaded(template: ProjectTemplate, projects_dir: Path) -> bool:
    d = target_dir(template, projects_dir)
    return d.is_dir() and any(d.iterdir())


def download_template(
    template: ProjectTemplate,
    projects_dir: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """Télécharge le zip du dépôt et n'en extrait que `repo_subdir`.

    Lève une exception (réseau, sous-dossier absent, extraction) — à
    l'appelant de l'afficher ; le dossier partiel est nettoyé avant de
    relancer l'exception."""
    dest = target_dir(template, projects_dir)
    if dest.exists():
        raise FileExistsError(f"'{dest}' already exists.")

    if progress_cb:
        progress_cb("Downloading…")
    with urllib.request.urlopen(REPO_ZIP_URL, timeout=30) as resp:
        data = resp.read()

    if progress_cb:
        progress_cb("Extracting…")
    prefix = f"{_REPO_ZIP_ROOT}/{template.repo_subdir}/"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            members = [m for m in zf.namelist() if m.startswith(prefix)]
            if not members:
                raise FileNotFoundError(
                    f"'{template.repo_subdir}' not found in the archive."
                )
            for member in members:
                rel = member[len(prefix):]
                if not rel:
                    continue
                out_path = dest / rel
                if member.endswith("/"):
                    out_path.mkdir(parents=True, exist_ok=True)
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(out_path, "wb") as f:
                        shutil.copyfileobj(src, f)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise

    return dest
