"""La navigation du Text Editor expose le pipeline Font → Asset → Texts."""
from __future__ import annotations


def test_pipeline_contexts_sont_dans_l_ordre_et_cliquables(qapp):
    from ui.text_editor.text_editor_screen import TextEditorScreen

    screen = TextEditorScreen()
    assert [button.text() for button in screen._pipeline._buttons.values()] == [
        "Font", "FontAsset", "Texts",
    ]
    assert screen._pipeline.parent() is screen._center_host

    screen._on_pipeline_context(screen._CTX_FONT_ASSET)
    assert screen._center.currentIndex() == screen._CTX_FONT_ASSET
    assert screen._pipeline._buttons[screen._CTX_FONT_ASSET].isChecked()
    assert not screen._fonts._sections["Font assets"].isHidden()
    assert screen._fonts._sections["Fonts"].isHidden()

    screen._on_pipeline_context(screen._CTX_TEXT)
    assert screen._center.currentIndex() == screen._CTX_TEXT
    assert screen._pipeline._buttons[screen._CTX_TEXT].isChecked()
    assert screen._finder_views.currentWidget() is screen._text_finder


def test_contexte_texts_du_finder_filtre_la_table_centrale(qapp, tmp_path):
    from PyQt6.QtCore import Qt
    from core.project import Project
    from ui.text_editor.text_editor_screen import TextEditorScreen

    project = Project(tmp_path)
    project.new_text("Jouer", path=["Menu"])
    project.new_text("Prêt", path=["Combat"])
    screen = TextEditorScreen()
    screen.load_project(project)
    screen._on_pipeline_context(screen._CTX_TEXT)

    finder = screen._text_finder
    root = finder._tree.topLevelItem(0)
    menu = next(root.child(i) for i in range(root.childCount())
                if root.child(i).data(0, Qt.ItemDataRole.UserRole) == ("Menu",))
    finder._tree.setCurrentItem(menu)
    menu.setSelected(True)
    qapp.processEvents()

    assert screen._texts._table._folder_filter == ("Menu",)
