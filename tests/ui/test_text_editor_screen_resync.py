"""L'écran Texte se resynchronise à chaque venue (`showEvent`).

Régression : `Window._load_screen_for_project` ne charge un écran qu'à sa
PREMIÈRE visite. Une zone de texte créée dans le Scene Manager ajoute son entrée
à `project.texts`, mais l'écran Texte déjà visité ne la voyait jamais — la table
restait figée sur son ancien contenu, y compris après un changement d'écran (le
pied de page lisait pourtant le total à jour du projet, d'où le « 1 of 8 shown »
alors qu'une seule ligne était construite).

Le correctif : `TextEditorScreen.showEvent` rappelle `refresh()`, bon marché et
sélection conservée. Ce test verrouille qu'une entrée née hors de l'écran
apparaît bien à la prochaine venue."""
from __future__ import annotations


def _text_rows(screen):
    from ui.text_editor.text_table import _ROLE_TEXT
    table = screen._texts._table
    return [it for it in table._iter_rows()
            if it.data(0, _ROLE_TEXT) is not None]


def test_une_entree_nee_ailleurs_apparait_au_retour_sur_lecran(qapp, tmp_path):
    from core.project import Project
    from ui.text_editor.text_editor_screen import TextEditorScreen

    p = Project(tmp_path)
    p.new_text(content="HUB", path=["Hub", "text"])

    screen = TextEditorScreen()
    screen.load_project(p)          # première visite : 1 texte
    assert len(_text_rows(screen)) == 1

    # Une zone de texte créée dans une autre partie de l'éditeur (Scene Manager)
    # ajoute son entrée au projet, sans passer par l'écran Texte.
    p.new_text(content="", path=["Menu", "text"])
    p.new_text(content="", path=["Boss", "text"])

    # Revenir sur l'écran (Qt délivre showEvent) doit resynchroniser la table.
    screen.show()
    qapp.processEvents()

    assert len(_text_rows(screen)) == 3
