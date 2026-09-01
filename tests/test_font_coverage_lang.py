"""Un texte qui cite un caractère absent de sa police (ROADMAP v0.9).

`text_glyph_slot` rend -1 pour un glyphe absent (cf. `gba_engine.h`) : le
caractère disparaît de l'affichage, sans un mot au build. Bug réel rencontré
en jouant la démo Fonts&Texts — une traduction japonaise citait un kanji
absent des 3831 glyphes de la police du projet. `_check_font_coverage` est le
pendant de `_check_text_overflow` (`test_text_overflow_langs.py`) côté GLYPHE
plutôt que côté LARGEUR de zone.
"""
from __future__ import annotations

import pytest


def _font(name="test_font", chars="OK abcdefghijklmnopqrstuvwxyz"):
    from core.models.font import Font, Glyph
    f = Font(name=name, cell_w=8, cell_h=8, line_height=8)
    f.glyphs = [Glyph(char=c, w=8, h=8, advance=8) for c in chars]
    return f


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.settings import Language
    from core.models.ui_region import UILayout, UIText

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)
    p.fonts.append(_font())

    region = UIText(name="hud", w=200, h=40)   # large : jamais un débordement de LARGEUR ici
    layout = UILayout(name="main")
    layout.elements.append(region)
    p.ui_layouts.append(layout)

    t = p.new_text(content="OK")
    t.key = "hud_msg"
    region.text_key = t.key

    p.settings.source_lang = Language(code="en", name="English")
    p.settings.languages = [Language(code="ja", name="Japanese")]
    p.load_translations()
    return p, t


def _warnings_for(p):
    from core.validator import ValidationContext, _check_font_coverage
    ctx = ValidationContext(p)
    _check_font_coverage(ctx)
    return [m.message for m in ctx.warnings]


def test_une_source_couverte_ne_signale_rien(projet):
    p, _t = projet
    assert _warnings_for(p) == []


def test_un_caractere_absent_est_signale_avec_la_langue_et_la_police(projet):
    p, t = projet
    p.translations["ja"][t.id] = "こんにちは"   # aucun de ces glyphes n'est dans test_font

    warns = _warnings_for(p)
    assert len(warns) == 1
    assert "hud_msg" in warns[0] and "« ja »" in warns[0]
    assert "test_font" in warns[0]
    assert "こ" in warns[0]   # au moins un des caractères manquants est nommé


def test_une_source_absente_de_sa_propre_police_est_aussi_signalee(projet):
    """La règle vaut pour la source comme pour une traduction — un texte mal
    saisi n'est pas moins un trou parce que personne ne l'a encore traduit."""
    p, t = projet
    t.content = "日本語"
    warns = _warnings_for(p)
    assert len(warns) == 1
    assert "« " not in warns[0].split(":")[0]   # pas d'étiquette de langue pour la source


def test_langue_non_traduite_replie_sur_la_source_sans_redoubler(projet):
    p, _t = projet
    assert _warnings_for(p) == []   # "OK" est couvert, source et repli identiques


def test_le_remap_de_police_par_langue_est_pris_en_compte(projet):
    """Un kanji absent de la police PAR DÉFAUT ne doit plus être signalé si
    la langue déclare un remplacement qui le couvre (`Language.fonts`, phase
    3.2) — c'est CETTE police que `text_set_font` charge réellement."""
    from core.models.settings import Language
    p, t = projet
    ja_font = _font(name="ja_font", chars="こんにちは")
    p.fonts.append(ja_font)
    p.settings.languages = [Language(code="ja", name="Japanese",
                                     fonts={"test_font": "ja_font"})]
    p.translations["ja"][t.id] = "こんにちは"

    assert _warnings_for(p) == []


def test_projet_monolingue_verifie_quand_meme_la_source(projet):
    """Contrairement au garde-fou VRAM (3.4) et aux littéraux (3.5), celui-ci
    protège aussi un projet SANS langue déclarée — un caractère manquant est
    un bug qu'aucune traduction n'a besoin d'exister pour révéler."""
    p, t = projet
    p.settings.languages = []
    t.content = "日本語"
    warns = _warnings_for(p)
    assert len(warns) == 1
