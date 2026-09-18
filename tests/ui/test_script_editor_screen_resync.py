"""L'écran Scripts se resynchronise à chaque venue (`showEvent`).

Régression (même classe que l'écran Texte) : `Window._load_screen_for_project`
ne charge un écran qu'à sa PREMIÈRE visite. La sidebar RÉFÉRENCES et surtout
l'AUTOCOMPLÉTION de l'écran Scripts capturent les catalogues du projet (sprites,
fonds, sons, globals, polices…) à ce moment-là. Un nom né ensuite dans un autre
écran (import d'un sprite, ajout d'un global) n'apparaissait jamais — en silence,
sans erreur, l'autocomplétion ignorait le nom neuf.

Le correctif : `ScriptEditorScreen.showEvent` re-dérive les catalogues
(`_refresh_catalogs`), bon marché car il ne relit que des noms déjà en mémoire.
Ce test verrouille qu'un global créé hors de l'écran entre bien dans les noms
d'autocomplétion à la prochaine venue."""
from __future__ import annotations


def _completion_names(screen):
    return screen._editor._completer._project_names or {}


def test_un_global_ne_ailleurs_entre_dans_lautocompletion_au_retour(qapp, tmp_path):
    from core.project import Project
    from core.models.settings import GlobalVar
    from ui.script_editor.script_editor import ScriptEditorScreen

    p = Project(tmp_path)

    screen = ScriptEditorScreen()
    screen.load_project(p)          # première visite : aucun global
    assert "score" not in _completion_names(screen).get("global", [])

    # Un global déclaré ailleurs (inspecteur de projet, Scene Manager) : il entre
    # dans `project.globals` sans repasser par l'écran Scripts.
    p.globals.append(GlobalVar(name="score"))

    # Revenir sur l'écran (Qt délivre showEvent) doit re-dériver les catalogues.
    screen.show()
    qapp.processEvents()

    assert "score" in _completion_names(screen).get("global", [])
