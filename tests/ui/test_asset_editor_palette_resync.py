"""Les écrans Backgrounds et Animations resynchronisent le CATALOGUE de
palettes à chaque venue (`showEvent`).

Régression (même classe que les écrans Texte et Scripts) :
`Window._load_screen_for_project` ne charge un écran qu'à sa PREMIÈRE visite. La
grille « + du catalogue » de ces deux éditeurs lit `project.palettes` à ce
moment-là. Une palette ajoutée, renommée ou retirée ensuite dans l'écran
Palettes n'y apparaissait jamais.

Le correctif : `showEvent` re-lit le catalogue (`refresh_palette_catalog` du
panneau), bon marché car il ne relit que des banques déjà en mémoire, sans
re-décoder l'image de l'asset. Les tests pilotent `showEvent` directement — un
vrai `show()` réveille le canvas, qui ne survit pas au mode headless (offscreen),
alors que le câblage à vérifier est showEvent → refresh du catalogue."""
from __future__ import annotations

from PyQt6.QtGui import QShowEvent


def _new_palette(name):
    from core.models.palette import PaletteBank
    return PaletteBank(name=name, colors=[0] * 16)


def test_background_editor_relit_le_catalogue_au_retour(qapp, tmp_path):
    from core.project import Project
    from ui.background_editor.background_editor_screen import BackgroundEditorScreen

    p = Project(tmp_path)
    screen = BackgroundEditorScreen()
    screen.load_project(p)
    # Précondition : un fond est ouvert, donc le panneau connaît le projet — ce
    # que fait `_props.load(ba, project)` quand on sélectionne un fond.
    screen._props._project = p
    screen._props.refresh_palette_catalog()
    assert screen._props._pal_grid._catalog == []

    # Une palette créée dans l'écran Palettes, sans repasser par ici.
    p.palettes.append(_new_palette("hero_pal"))

    screen.showEvent(QShowEvent())

    assert [b.name for b in screen._props._pal_grid._catalog] == ["hero_pal"]


def test_sprite_editor_relit_le_catalogue_au_retour(qapp, tmp_path):
    from core.project import Project
    from core.models.sprite import SpriteAsset
    from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen

    p = Project(tmp_path)
    screen = SpriteEditorScreen()
    screen.load_project(p)
    # Le panneau droit ne tient son projet qu'une fois un sprite chargé.
    screen._right.load_sprite(SpriteAsset(name="hero"), p)
    assert screen._right._pal_grid._catalog == []

    p.palettes.append(_new_palette("hero_pal"))

    screen.showEvent(QShowEvent())

    assert [b.name for b in screen._right._pal_grid._catalog] == ["hero_pal"]
