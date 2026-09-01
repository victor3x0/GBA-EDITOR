"""Le garde-fou VRAM au pire cas des langues (ROADMAP v0.9, phase 3.4).

Avant ce chantier, `scene_text_reservation` ne mesurait que la source : une
traduction dont le sous-ensemble de glyphes est plus lourd déborderait sur son
voisin en VRAM le jour où cette langue serait active, sans qu'aucun mot ne le
dise avant que quelqu'un joue la ROM dans cette langue-là. Ces tests protègent
`_check_vram_lang_budget`, pendant de `_check_text_overflow`
(`test_text_overflow_langs.py`) côté GLYPHES plutôt que côté LARGEUR de zone.
"""
from __future__ import annotations

import pytest

# 12 glyphes hors-latin, pour simuler ce qu'une traduction ajoute (un vrai
# projet y mettrait des kanji ou des accents) sans dépendre d'une planche
# réelle sur disque.
_EXTRA = "".join(chr(0xE000 + i) for i in range(12))


def _font(p):
    # `encodable_project_fonts` écarte une police sans planche PRÉSENTE SUR
    # DISQUE (cf. test_text_surface_alloc.py) : une police sans fichier n'est
    # pas retenue, même déclarée dans le projet.
    from PIL import Image
    from core.models.font import Font, Glyph
    planche = p.root / "assets" / "fonts" / "test_font.png"
    planche.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(planche)
    f = Font(name="test_font", cell_w=8, cell_h=8, line_height=8,
             asset=p.asset_rel(planche))
    f.glyphs = [Glyph(char=c, w=8, h=8, advance=8) for c in ("Hi0123456789" + _EXTRA)]
    return f


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language
    from core.models.ui_region import UILayout, UIText
    from core.models.scene import Scene

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    p.fonts.append(_font(p))

    zone = UIText(name="bubble", w=64, h=16)
    layout = UILayout(name="hud")
    layout.elements.append(zone)
    p.ui_layouts.append(layout)

    t = p.new_text(content="Hi", path=["Dialogue", "Greet"])
    zone.text_key = t.key

    scene = Scene(name="Main", text_bg=1, ui_layout="hud", font_name="test_font")
    p.scenes.append(scene)

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="ja", name="Japanese")]
    p.load_translations()
    return p, scene, t


def _warnings_for(p):
    from core.validator import ValidationContext, _check_vram_lang_budget
    ctx = ValidationContext(p)
    _check_vram_lang_budget(ctx)
    return [m.message for m in ctx.warnings]


def test_aucune_traduction_ne_deborde_pas(projet):
    p, _scene, _t = projet
    assert _warnings_for(p) == []


def test_une_traduction_plus_lourde_deborde_et_le_dit(projet):
    p, scene, t = projet
    p.translations["ja"][t.id] = _EXTRA   # 12 glyphes de plus que "Hi"

    warns = _warnings_for(p)
    assert len(warns) == 1
    assert scene.name in warns[0]
    assert "Japanese" in warns[0]


def test_une_traduction_plus_courte_ne_deborde_pas(projet):
    """Moins de glyphes distincts que la source : rien à signaler."""
    p, _scene, t = projet
    p.translations["ja"][t.id] = "H"
    assert _warnings_for(p) == []


def test_projet_monolingue_ne_declenche_rien(projet):
    p, _scene, t = projet
    p.translations["ja"][t.id] = _EXTRA
    p.settings.languages = []
    assert _warnings_for(p) == []
