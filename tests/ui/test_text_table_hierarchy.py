"""Le Finder porte les dossiers ; la table centrale reste plate."""
from __future__ import annotations


def test_chemin_profond_est_recherchable_dans_la_liste_plate(qapp, tmp_path):
    from core.project import Project
    from ui.text_editor.text_table import _ROLE_TEXT, TextTable

    project = Project(tmp_path)
    deep = project.new_text("Bonjour", path=["Menu", "Options", "Audio", "Volume"])
    table = TextTable()
    table.load_project(project)

    # Le Finder porte l'arborescence ; la liste centrale ne doit pas réserver
    # une indentation d'arbre qui couperait les clés longues.
    assert not table._tree.rootIsDecorated()
    assert table._tree.topLevelItemCount() == 1
    assert table._tree.topLevelItem(0).data(0, _ROLE_TEXT) is deep
    table._search.setText("volume")
    qapp.processEvents()
    assert not table._tree.topLevelItem(0).isHidden()
