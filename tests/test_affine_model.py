"""Le modèle affine (ARCHITECTURE.md « Le modèle affine ») : la décision vit sur
l'Actor (`affine_transform`), et le rendu compose au runtime le transform MONDE
de l'actor avec le transform LOCAL du sprite (rotation somme, scale produit,
offset dans le repère local de l'actor).

Deux régressions sont scellées ici, toutes deux découvertes en refondant ce
modèle :
  * l'ancien `g_affine_*[]` était `static` dans un header multi-inclus → une
    COPIE par unité de compilation ; les écritures self.rotation/self.scale
    d'un script n'atteignaient jamais le rendu. Le stockage est maintenant
    PAR-ACTOR, dans la struct Actor ;
  * l'ancien seed scène lisait `flip_h` sur le SpriteComponent (champ
    inexistant → toujours faux) au lieu de l'Actor.
"""
from __future__ import annotations

from core.models.components import SpriteComponent
from core.models.scene import Actor
from codegen.runtime_codegen.main_gen import (
    _affine_entry, _compute_affine_info, _affine_oam_lines_dynamic,
)


def _actor(**kw) -> Actor:
    a = Actor(name="A")
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _sc(**kw) -> SpriteComponent:
    s = SpriteComponent()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ── L'allocation est pilotée par l'actor ────────────────────────────

def test_non_affine_ne_reserve_aucun_slot():
    a = _actor()
    sc = _sc()
    assert _affine_entry(a, sc, 3) is None


def test_affine_reserve_un_slot_meme_a_identite():
    """`affine_transform` coché réserve le slot même si scale/rotation valent leur
    défaut — c'est ce qui laisse self.rotation/self.scale avoir où écrire."""
    a = _actor(affine_transform=True)
    e = _affine_entry(a, _sc(), 7)
    assert e is not None
    assert e["slot"] == 7
    assert e["scale_x"] == 256 and e["scale_y"] == 256   # Q8, 100%


def test_le_scale_rotation_sans_affine_sont_ignores():
    """Un scale/rotation sur le sprite SANS « Affine transform » ne crée pas de
    slot : sans réservation, ils n'ont nulle part où atterrir."""
    sc = _sc(scale_x=2.0, rotation=45)
    assert _affine_entry(_actor(), sc, 0) is None


def test_monde_et_local_finissent_en_champs_actor():
    a = _actor(affine_transform=True, rotation=90, scale_x=2.0, scale_y=0.5)
    sc = _sc(rotation=45, scale_x=1.5, scale_y=0.25, offset_x=-8, offset_y=12)
    e = _affine_entry(a, sc, 2)
    assert e["rotation"] == 90            # monde
    assert e["scale_x"] == 512            # Q8 : 2.0×256
    assert e["scale_y"] == 128            # Q8 : 0.5×256
    assert e["sprite_rotation"] == 45     # local
    assert e["sprite_scale_x"] == 384     # Q8 : 1.5×256
    assert e["sprite_scale_y"] == 64      # Q8 : 0.25×256
    assert (e["offset_x"], e["offset_y"]) == (-8, 12)


def test_compute_affine_info_compte_des_slots_distincts():
    a1 = _actor(affine_transform=True)
    a1.components.append(_sc())
    a2 = _actor(affine_transform=True)
    a2.components.append(_sc())
    a3 = _actor()                       # pas d'affine → pas de sprite requis
    a3.components.append(_sc())
    scene_actors = [(a1, None), (a2, None), (a3, None)]
    info = _compute_affine_info(offset := 10, scene_actors, [])
    assert set(info) == {10, 11}          # a1 et a2, pas a3
    assert info[10]["slot"] == 0
    assert info[11]["slot"] == 1


# ── Le C émis reflète la composition ────────────────────────────────

def test_oam_dynamic_compose_monde_local_et_offset():
    a = _actor(affine_transform=True, rotation=30, scale_x=1.0, scale_y=1.0)
    sc = _sc(rotation=0, scale_x=1.0, scale_y=1.0, offset_x=10, offset_y=5)

    class SpriteShape:
        frame_w, frame_h = 8, 8
        oam_shape, oam_size = 1, 0     # 8×8 affine
        tiles_per_frame = 1

    entry = _affine_entry(a, sc, 0)
    lines = "\n".join(_affine_oam_lines_dynamic(7, entry, SpriteShape(), bt=0, priority_expr="0"))
    # Lecture des champs par-Actor, plus de globals par slot
    assert "g_actors[7].rotation" in lines
    assert "g_actors[7].sprite_rot" in lines
    assert "g_actors[7].offset_x" in lines
    assert "g_affine" not in lines
    # Composition : la rotation effective est la SOMME monde+local
    assert "int _ang=_arot+_srot;" in lines
    # Offset transformé par la matrice de l'ACTOR (hérarchie)
    assert "int _ofx=(_acos*_asxs" in lines
    assert "int _ofy=(_asin*_asxs" in lines


def test_script_lua_compile_avec_les_props_affine():
    """(end-to-end) parse → check → C : un script qui lit/écrit les props monde
    et locaux passe quand l'actor a « Affine transform », et le C émis appelle
    bien les setters/getters par-Actor."""
    from scripting.parser import parse as lua_parse
    from scripting.checker import check as lua_check, BuildContext
    from scripting.codegen import generate as lua_generate, CodegenContext

    src = """
    function on_update(self)
        self.rotation = self.rotation + 1
        self.sprite_rotation = 45
        self.sprite_scale = vec2(150, 150)
        self.sprite_offset = vec2(-10, 6)
        local s = self.sprite_scale
        local o = self.sprite_offset
    end
    """
    script = lua_parse(src)
    ctx = BuildContext(actor_name="Ball", affine_transform=True)
    assert [str(e) for e in lua_check(script, ctx)] == []

    cg = CodegenContext(actor_name="Ball", actor_sym="Ball", anim_names=[],
                        sfx_names=[], music_names=[], global_names=set(),
                        const_names=set(), all_actor_syms=["Ball"])
    code, _, _ = lua_generate(script, cg)
    for needle in (
        "actor_set_rotation(self", "actor_get_rotation(self",
        "actor_set_sprite_rotation(self, 45",
        "actor_set_sprite_scale(self,", "actor_set_sprite_offset(self,",
        "Vec2 s = actor_get_sprite_scale(self);",
        "Vec2 o = actor_get_sprite_offset(self);",
    ):
        assert needle in code, needle


def test_script_lua_sans_affine_signale_le_manque_de_slot():
    """Un actor sans « Affine transform » n'a aucun slot : le checker doit le
    dire, sinon self.rotation s'écrit dans le vide au runtime."""
    from scripting.parser import parse as lua_parse
    from scripting.checker import check as lua_check, BuildContext

    src = "function on_update(self)\n    self.rotation = 1\nend\n"
    script = lua_parse(src)
    errs = [str(e) for e in lua_check(script, BuildContext(actor_name="Ball", affine_transform=False))]
    assert errs, "le checker doit signaler un self.rotation sans slot affine"


def test_seed_scene_ecrit_dans_la_struct_actor():
    """(régression) la struct Actor a bien les champs que le seed écrit : on les
    déclare dans actor_types_static.h, pas dans des globaux cachés."""
    from pathlib import Path
    hdr = (Path(__file__).resolve().parent.parent
           / "runtime" / "include" / "actor_types_static.h").read_text(encoding="utf-8")
    for f in ("affine_slot", "rotation", "scale_x", "scale_y",
              "sprite_rot", "sprite_scale_x", "sprite_scale_y",
              "offset_x", "offset_y"):
        assert f in hdr
    api = (Path(__file__).resolve().parent.parent
           / "runtime" / "include" / "actor_api_static.h").read_text(encoding="utf-8")
    # (régression) plus de globals par slot : chaque TU en aurait une copie
    assert "g_affine_angle" not in api
    assert "g_affine_scale_x" not in api