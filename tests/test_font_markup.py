"""Fondations du balisage typographique ``[font=nom]…[/font]``."""
from __future__ import annotations


def test_font_est_une_portee_et_ne_sort_pas_dans_le_texte_affiche():
    from core.text_markup import parse

    parsed = parse("Bonjour [font=Titre]monde[/font] !")

    assert parsed.display == "Bonjour monde !"
    assert [(m.kind, m.at, m.end, m.value) for m in parsed.of_kind("font")] == [
        ("font", 8, 13, "Titre")
    ]


def test_font_partage_les_regles_generiques_d_imbrication():
    from core.text_markup import parse

    parsed = parse("[font=Titre][color=2]A[/font][/color]")

    assert parsed.display == "A"
    assert parsed.of_kind("font")[0].value == "Titre"
    assert any("imbrication croisée" in issue.message for issue in parsed.issues)


def test_une_police_de_balisage_inconnue_bloque_le_build(tmp_path):
    from core.project import Project
    from core.models.font import Font, Glyph
    from core.validator import ValidationContext, _check_markup_fonts

    project = Project(tmp_path / "jeu")
    project.fonts.append(Font(name="Dialogue", glyphs=[Glyph(char="A", w=8, h=8)]))
    text = project.new_text(content="[font=Titre]A[/font]")
    text.key = "intro"

    ctx = ValidationContext(project)
    _check_markup_fonts(ctx)

    assert len(ctx.errors) == 1
    assert "intro" in ctx.errors[0].message
    assert "Titre" in ctx.errors[0].message


def test_une_police_de_balisage_connue_est_acceptee(tmp_path):
    from core.project import Project
    from core.models.font import Font, Glyph
    from core.validator import ValidationContext, _check_markup_fonts

    project = Project(tmp_path / "jeu")
    project.fonts.append(Font(name="Titre", glyphs=[Glyph(char="A", w=8, h=8)]))
    project.new_text(content="[font=Titre]A[/font]")

    ctx = ValidationContext(project)
    _check_markup_fonts(ctx)

    assert ctx.errors == []

