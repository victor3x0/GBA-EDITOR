"""Le preview texte choisit une recette de police, pas sa source brute."""
from __future__ import annotations

from core.project import Project
from ui.text_editor.text_workbench import TextWorkbench


def test_screen_preview_lists_font_assets_and_uses_the_selected_recipe(qapp, tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")
    workbench = TextWorkbench()
    workbench.load_project(project)

    assert [workbench._preview_font.itemText(i)
            for i in range(workbench._preview_font.count())] == [
        "Font8x8 Latin", "GNU Unifont JP 16", "Misaki Gothic 8",
    ]

    workbench._preview_font.setCurrentText("Misaki Gothic 8")
    selected = project.get_font_asset("Misaki Gothic 8")
    assert workbench._preview._font is selected
    # Les consommateurs historiques reçoivent toujours la source primaire,
    # mais l'écran reçoit bien la recette complète ci-dessus.
    assert workbench.preview_font() is project.fonts.get("misaki-gothic")


def test_screen_preview_materializes_bitmap_font_asset(qapp, tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")
    workbench = TextWorkbench()
    workbench.load_project(project)
    workbench._preview.set_text("é")

    materialized = workbench._preview._font_for_text()
    glyph = materialized.glyph("é")
    image = workbench._preview._glyph_image(glyph)

    assert materialized.name == "Font8x8 Latin"
    assert image.width() == image.height() == 8
    assert any(image.pixelColor(x, y).alpha() for y in range(8) for x in range(8))
