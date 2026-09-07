"""
GBA Editor — point d'entrée
Usage : python main.py
"""

import sys
from pathlib import Path

# Garantit que `editor/` est toujours le premier élément du path,
# quelle que soit la façon dont le process est lancé (python main.py,
# import depuis un test, lancement via l'IDE…).
# Tous les modules internes importent sans préfixe "editor." — un seul
# nom par module, pas de risque de double-import.
_EDITOR_DIR = str(Path(__file__).resolve().parent)
if _EDITOR_DIR not in sys.path:
    sys.path.insert(0, _EDITOR_DIR)

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtGui import QPalette, QColor
from window import MainWindow
from ui.common.theme import GLOBAL_QSS, C, install_app_fonts
from ui.common import icons
from ui.home.project_picker import HomeScreen, PROJECTS_DIR
from core.project_paths import PROJECT_EXT, find_manifest, ProjectManifestError


def dark_palette() -> QPalette:
    """Thème sombre teinté indigo/violet (identité GBA) — accent primaire
    périwinkle. Toutes les valeurs dérivent de ui.common.theme.C."""
    p = QPalette()
    bg      = QColor(C.BG_PANEL)
    surface = QColor(C.BG_INPUT)
    border  = QColor(C.BORDER_MID)
    text    = QColor("#d2d2e0")
    muted   = QColor(C.TEXT_DIM)
    accent  = QColor(C.ACCENT)

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            surface)
    p.setColor(QPalette.ColorRole.AlternateBase,   border)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
    p.setColor(QPalette.ColorRole.Button,          surface)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
    return p


if __name__ == "__main__":
    # Charger les plugins avant de créer la fenêtre (enrichissent le registre)
    from plugins import load_all_plugins
    loaded, plugin_errors = load_all_plugins()

    # Projet fourni au lancement, deux formes :
    #   --project <dossier>          (le picker, les récents)
    #   <chemin>/<Nom>.gba-project   (double-clic : l'OS passe le fichier associé)
    project_path = None
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            project_path = Path(sys.argv[idx + 1])
    else:
        for arg in sys.argv[1:]:
            if arg.endswith(PROJECT_EXT):
                project_path = Path(arg)
                break

    # Le manifeste vit DANS le dossier projet : un .gba-project double-cliqué se
    # ramène à son dossier parent, la racine que MainWindow/Project attendent.
    if project_path is not None and project_path.is_file():
        project_path = project_path.parent

    app = QApplication(sys.argv)
    app.setApplicationName("GBA Editor")
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    install_app_fonts()
    # Les QSS référencent quelques icônes par chemin de fichier : il faut les
    # rendre maintenant (la QApplication existe) avant d'appliquer la feuille.
    icons.ensure_qss_assets()
    app.setStyleSheet(GLOBAL_QSS)

    # Refus explicite si le dossier porte plusieurs manifestes (ROADMAP v0.10) :
    # on le dit et on retombe sur l'accueil, plutôt que d'en choisir un au hasard.
    # Après la QApplication : une QMessageBox sans elle planterait.
    if project_path is not None:
        try:
            find_manifest(project_path)
        except ProjectManifestError as exc:
            QMessageBox.critical(None, "Open project", str(exc))
            project_path = None

    # Si aucun projet fourni en argument, afficher l'écran d'accueil
    if project_path is None:
        picker = HomeScreen(PROJECTS_DIR)
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.result_path:
            sys.exit(0)
        project_path = picker.result_path
        _is_new  = picker.result_is_new
        _name    = picker.result_name
    else:
        _is_new = False
        _name   = ""

    win = MainWindow(project_path=project_path)
    if _is_new and _name:
        win._new_project(_name, project_path)
    # else : projet déjà ouvert par MainWindow.__init__ -> _load_default_project()
    # (appeler _open_project() une 2e fois ici rechargeait tout le projet en
    # double au démarrage : deux fois le watcher connecté, deux fois la scène
    # reconstruite dos à dos, sans laisser l'event loop tourner entre les deux
    # — source probable du crash "GBAScene has been deleted" au lancement).
    win.show()

    # Défauts des points d'extension, APRÈS que la fenêtre est visible : un
    # plugin qui n'a pas pu être chargé, et un écran qui ne remplit pas le
    # contrat ProjectScreen (`ui/screens.py`). Les deux se constatent au
    # démarrage et nulle part ailleurs — un écran muet ne se distingue sinon
    # pas d'un écran vide.
    problems = ([f"{name} : {exc}" for name, exc in plugin_errors]
                + list(win.screen_errors))
    if problems:
        box = QMessageBox(win)
        box.setWindowTitle("Extension Errors")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"{len(problems)} problem(s) found while loading extensions:")
        box.setDetailedText("\n".join(f"• {p}" for p in problems))
        box.exec()
    sys.exit(app.exec())
