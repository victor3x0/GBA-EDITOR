"""Allocation des banques de palette — `codegen/palette_alloc.py`.

Deuxième module où une erreur ne dit rien : elle sort une ROM aux mauvaises
couleurs. Le module est en outre la **source de vérité unique** de deux
consommateurs qui ne se parlent pas (grit `-mp` dans `rom_build`, `g_pal_*` dans
`main_gen`) : ils ne restent d'accord que parce qu'ils rappellent la même
fonction et qu'elle est déterministe. C'est donc aussi ce que ces tests fixent.

Le pool BG sert de terrain d'essai — il exerce les deux modes d'allocation (slot
unique et BLOC contigu pour un fond compressé) là où le pool OBJ n'a que le
premier.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.palette import OWN_PAL_BANK, PaletteBank, RESERVED_SLOT_COLOR
from core.models.scene import Scene
from core.palette_presets import DEFAULT_PAL_BANK_COLORS
from core.project import Project
from codegen.palette_alloc import (
    SceneBankLayout, scene_bank_layout, _find_free_block, _own_bank_content,
)


# ── Fabriques ─────────────────────────────────────────────────────

def _couleurs(graine: int) -> list[int]:
    """16 couleurs BGR555 distinctes et reproductibles — le CONTENU est ce qui
    déduplique une banque, il doit donc différer d'une graine à l'autre."""
    return [(graine * 97 + i * 31) & 0x7FFF for i in range(16)]


@pytest.fixture
def projet(tmp_path) -> Project:
    """Un projet vide, en mémoire. Aucun sidecar n'est lu : les registres se
    remplissent à la main, ce qui rend chaque cas lisible d'un bloc."""
    return Project(tmp_path)


def _ajouter_palette(p: Project, nom: str, graine: int) -> PaletteBank:
    bank = PaletteBank(name=nom, colors=_couleurs(graine))
    p.palettes.append(bank)
    return bank


def _ajouter_fond_compresse(p: Project, nom: str, sous_palettes: list[list[int]],
                            bpp: int = 4) -> BackgroundAsset:
    """Un fond COMPRESSÉ : il porte ses propres sous-palettes et réclame donc un
    bloc de banques contiguës, pas un slot."""
    ba = BackgroundAsset(name=nom, asset=f"{nom}.png", palettes=sous_palettes,
                         tileset=["0" * 64], tilemap=[0], tiles_w=1, tiles_h=1,
                         bpp=bpp)
    p.backgrounds.append(ba)
    return ba


def _scene_avec_fonds(*noms: str) -> Scene:
    s = Scene(name="Test")
    s.background_layers = [
        BackgroundLayer(background_name=nom, bg_slot=i, pal_bank=OWN_PAL_BANK)
        for i, nom in enumerate(noms)
    ]
    return s


# ── Recherche d'un bloc contigu ───────────────────────────────────

def test_find_free_block_prend_le_premier_trou_assez_grand():
    slots = [None] * 16
    slots[0] = _couleurs(1)
    slots[3] = _couleurs(2)
    assert _find_free_block(slots, 2) == 1     # [1,3) — avant le trou d'après
    assert _find_free_block(slots, 4) == 4     # [1,3) trop court, on va après


def test_find_free_block_exige_la_contiguite():
    """Les N sous-palettes d'un fond compressé occupent des banques CONSÉCUTIVES
    (le champ SE_PALBANK d'une tuile est un index de banque, pas une table
    d'indirection) : quatre trous épars ne valent pas un bloc de quatre."""
    slots = [None if i % 2 == 0 else _couleurs(i) for i in range(16)]
    assert _find_free_block(slots, 2) is None
    assert _find_free_block(slots, 1) == 0


def test_find_free_block_rend_none_quand_rien_ne_tient():
    slots = [_couleurs(i) for i in range(16)]
    assert _find_free_block(slots, 1) is None


def test_find_free_block_couvre_les_seize_banques():
    """Un fond de 16 sous-palettes tient dans une scène vierge, et lui seul."""
    assert _find_free_block([None] * 16, 16) == 0
    presque = [None] * 16
    presque[15] = _couleurs(1)
    assert _find_free_block(presque, 16) is None


def test_find_free_block_traite_zero_comme_un():
    """Un asset sans sous-palette ne réclame pas « rien » : le rendre `0`
    donnerait un offset valide sur une banque occupée."""
    slots = [None] * 16
    slots[0] = _couleurs(1)
    assert _find_free_block(slots, 0) == 1


# ── Contenu d'une banque de palette propre ────────────────────────

def test_le_pool_obj_reserve_le_slot_zero():
    """Piège documenté : sans ce décalage, la 1re couleur d'un sprite atterrit en
    position 0, que le hardware OBJ rend transparente quoi qu'il arrive — la
    couleur n'apparaît jamais, sans un mot."""
    cols = [1, 2, 3]
    assert _own_bank_content(cols, "obj") == [RESERVED_SLOT_COLOR, 1, 2, 3]


def test_le_pool_bg_ne_le_reserve_pas():
    """Le BG legacy passe par `extract_palette_from_image`, qui inclut DÉJÀ ce
    slot : le préfixer une seconde fois décalerait toutes les couleurs d'un
    cran."""
    cols = [RESERVED_SLOT_COLOR, 1, 2, 3]
    assert _own_bank_content(cols, "bg") == cols


# ── Lecture du résultat ───────────────────────────────────────────

def test_bank_index_d_une_palette_referencee():
    lay = SceneBankLayout([None] * 16, {})
    assert lay.bank_index(5, None) == 5
    assert lay.bank_index(0, None) == 0
    assert lay.bank_index(16, None) is None      # hors des 16 banques
    assert lay.bank_index(-2, None) is None      # ni OWN, ni un slot


def test_bank_index_d_une_palette_propre():
    cols = _couleurs(7)
    lay = SceneBankLayout([None] * 16, {tuple(cols): 3})
    assert lay.bank_index(OWN_PAL_BANK, cols) == 3
    assert lay.bank_index(OWN_PAL_BANK, _couleurs(8)) is None   # jamais allouée
    assert lay.bank_index(OWN_PAL_BANK, []) is None             # rien à allouer


def test_overflow_signale_le_debordement():
    cols = _couleurs(1)
    assert SceneBankLayout([None] * 16, {tuple(cols): 4}).overflow() is False
    assert SceneBankLayout([None] * 16, {tuple(cols): None}).overflow() is True
    assert SceneBankLayout([None] * 16, {}, {(): None}).overflow() is True


def test_bank_count_ne_compte_que_les_banques_remplies():
    slots = [None] * 16
    slots[0], slots[9] = _couleurs(1), _couleurs(2)
    assert SceneBankLayout(slots, {}).bank_count() == 2


# ── Allocation d'une scène, de bout en bout ───────────────────────

def test_les_palettes_referencees_gardent_leur_index(projet):
    """Une palette référencée n'est pas allouée, elle est POSÉE : son index dans
    la sélection de la scène EST son index matériel."""
    ciel = _ajouter_palette(projet, "Ciel", 1)
    sol = _ajouter_palette(projet, "Sol", 2)
    scene = Scene(name="Test")
    scene.active_bg_palettes = ["Ciel", "", "Sol"]

    lay = scene_bank_layout(projet, scene, "bg")
    # Comparé à `bank.colors`, pas aux couleurs de la fabrique : `PaletteBank`
    # force son index 0 vers RESERVED_SLOT_COLOR, et c'est la banque telle
    # qu'elle EST qui doit atterrir dans le slot.
    assert lay.slot_colors[0] == ciel.colors
    assert lay.slot_colors[2] == sol.colors
    assert lay.slot_colors[1] is None
    assert lay.bank_index(2, None) == 2


def test_une_scene_vide_n_invente_aucune_couleur(projet):
    """La banque 0 de secours ne se remplit que si la scène a du contenu :
    sinon l'émission de `main_gen` paierait une palette que rien ne lit."""
    lay = scene_bank_layout(projet, Scene(name="Vide"), "bg")
    assert all(c is None for c in lay.slot_colors)
    assert lay.bank_count() == 0


def test_la_banque_zero_de_secours_se_remplit(projet):
    """Un asset qui retombe sur la banque 0 (référence cassée, débordement) doit
    afficher des couleurs PRÉVISIBLES plutôt que ce qui traîne en mémoire."""
    sol = _ajouter_palette(projet, "Sol", 2)
    scene = Scene(name="Test")
    scene.active_bg_palettes = ["", "Sol"]

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.slot_colors[0] == list(DEFAULT_PAL_BANK_COLORS)
    assert lay.slot_colors[1] == sol.colors


def test_un_fond_compresse_obtient_un_bloc_contigu(projet):
    sous = [_couleurs(10), _couleurs(11), _couleurs(12)]
    ba = _ajouter_fond_compresse(projet, "Foret", sous)

    lay = scene_bank_layout(projet, _scene_avec_fonds("Foret"), "bg")
    debut = lay.bg_block_offset(ba)
    assert debut is not None
    assert lay.slot_colors[debut:debut + 3] == sous
    assert lay.overflow() is False


def test_deux_fonds_aux_memes_couleurs_partagent_leur_bloc(projet):
    """Dédup par CONTENU exact : deux fonds identiques ne paient qu'une fois."""
    sous = [_couleurs(20), _couleurs(21)]
    a = _ajouter_fond_compresse(projet, "Foret", sous)
    b = _ajouter_fond_compresse(projet, "ForetNuit", [list(p) for p in sous])

    lay = scene_bank_layout(projet, _scene_avec_fonds("Foret", "ForetNuit"), "bg")
    assert lay.bg_block_offset(a) == lay.bg_block_offset(b)
    assert lay.bank_count() == 2


def test_un_fond_compresse_deborde_faute_de_place(projet):
    """Douze banques référencées, un fond qui en réclame six d'affilée : il n'y a
    pas de bloc, et le dire est tout ce que le module peut faire."""
    scene = _scene_avec_fonds("Foret")
    noms = []
    for i in range(12):
        _ajouter_palette(projet, f"P{i}", i + 1)
        noms.append(f"P{i}")
    scene.active_bg_palettes = noms
    ba = _ajouter_fond_compresse(projet, "Foret", [_couleurs(30 + i) for i in range(6)])

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.bg_block_offset(ba) is None
    assert lay.overflow() is True


def test_un_fond_8bpp_occupe_les_seize_banques(projet):
    """En 8bpp le `pal_bank` d'une tuile est IGNORÉ par le hardware : la palette
    de 256 couleurs s'étale sur toute PAL_BG_RAM, découpée en 16 tranches."""
    pal256 = [(i * 7) & 0x7FFF for i in range(256)]
    ba = _ajouter_fond_compresse(projet, "Photo", [pal256], bpp=8)

    lay = scene_bank_layout(projet, _scene_avec_fonds("Photo"), "bg")
    assert lay.bg_block_offset(ba) == 0
    assert lay.bank_count() == 16
    assert lay.slot_colors[0] == pal256[:16]
    assert lay.slot_colors[15] == pal256[240:]


def test_un_fond_8bpp_ne_cohabite_avec_rien(projet):
    """Il prend les 16 banques ou rien : une seule palette référencée suffit à
    rendre la scène impossible, et ça doit se voir au build."""
    _ajouter_palette(projet, "Ciel", 1)
    scene = _scene_avec_fonds("Photo")
    scene.active_bg_palettes = ["Ciel"]
    ba = _ajouter_fond_compresse(projet, "Photo",
                                 [[(i * 7) & 0x7FFF for i in range(256)]], bpp=8)

    lay = scene_bank_layout(projet, scene, "bg")
    assert lay.bg_block_offset(ba) is None
    assert lay.overflow() is True


def test_l_allocation_est_deterministe(projet):
    """La promesse dont dépend la cohérence entre grit et `main_gen` : ils
    n'échangent rien, ils rappellent cette fonction chacun de leur côté."""
    _ajouter_palette(projet, "Ciel", 1)
    scene = _scene_avec_fonds("Foret", "Roche")
    scene.active_bg_palettes = ["Ciel"]
    _ajouter_fond_compresse(projet, "Foret", [_couleurs(40), _couleurs(41)])
    _ajouter_fond_compresse(projet, "Roche", [_couleurs(42)])

    a = scene_bank_layout(projet, scene, "bg")
    b = scene_bank_layout(projet, scene, "bg")
    assert a.slot_colors == b.slot_colors
    assert a.bank_count() == b.bank_count()
