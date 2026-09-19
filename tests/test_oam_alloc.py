"""L'allocateur OAM per-scène (ROADMAP v0.17, T1+T2+T3).

`oam_alloc.scene_oam_layout` est la source de vérité de la géométrie OAM d'une
scène : ses acteurs actifs d'abord (base 0), puis les pools qu'ELLE déclare, à
leur place. Ces tests fixent le contrat que `headers`, `main_gen` et la façade
`actor_budget` lisent — base 0 par scène, symboles de pool préfixés par la
scène, pas de repli `max_instances`, et `g_actors` dimensionné sur le MAX des
scènes (pas la somme).
"""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from codegen.oam_alloc import (
    OAM_LIMIT, scene_oam_layout, project_actor_count, scene_pool_instances,
    prefab_group,
)


def _projet(tmp_path, *, scenes, prefabs=None) -> Project:
    p = Project(tmp_path)
    p.scenes.items = list(scenes)
    p.prefabs.items = list(prefabs or [])
    return p


# ── Base 0 par scène ──────────────────────────────────────────────────

def test_pools_partent_apres_les_acteurs_actifs(tmp_path):
    ball = Prefab(name="Ball")
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2
    (pool,) = lay.pools
    assert pool.start == 2          # juste après les 2 acteurs, base 0
    assert pool.size == 4 and lay.used == 6


def test_override_actor_slots_n_affecte_pas_la_geometrie(tmp_path):
    """`Scene.actor_slots` est une réservation d'INSPECTEUR (ROADMAP v0.17) : le
    build pose les pools après les acteurs RÉELLEMENT posés, jamais après
    l'override — sinon `g_actors` gonflerait de slots réservés-mais-vides."""
    ball = Prefab(name="Ball")
    scene = Scene(name="S", actors=[Actor(name="A")])
    scene.actor_slots = 96                     # ancien défaut 96/32, resté
    scene.prefab_pools = {"Ball": 8}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 1
    assert lay.pools[0].start == 1             # après le SEUL acteur, pas 96
    assert lay.used == 9 and project_actor_count(p) == 9


def test_chaque_scene_repart_de_zero(tmp_path):
    """Deux scènes, deux plages qui partent chacune de leur propre base 0 —
    aucune ne porte les acteurs de l'autre."""
    ball = Prefab(name="Ball")
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(5)])
    s2.prefab_pools = {"Ball": 8}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    l1, l2 = scene_oam_layout(p, s1), scene_oam_layout(p, s2)
    assert l1.pools == [] and l1.used == 1
    assert l2.pools[0].start == 5 and l2.used == 13


# ── Symboles de pool préfixés par la scène ────────────────────────────

def test_symbole_de_pool_prefixe_par_la_scene(tmp_path):
    ball = Prefab(name="Ball")
    s1 = Scene(name="Menu"); s1.prefab_pools = {"Ball": 2}
    s2 = Scene(name="Level"); s2.prefab_pools = {"Ball": 2}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert scene_oam_layout(p, s1).pools[0].sym == "Menu_Ball"
    assert scene_oam_layout(p, s2).pools[0].sym == "Level_Ball"


# ── Pas de repli max_instances, plus de max inter-scènes ──────────────

def test_pas_de_repli_sur_max_instances(tmp_path):
    """Un prefab qu'aucune scène ne déclare n'est plus poolé. Le champ hérité
    `Prefab.max_instances` a été RETIRÉ en T7 : le pool ne vit que sur la scène,
    et un prefab non déclaré n'a aucune plage."""
    ball = Prefab(name="Ball")
    assert not hasattr(ball, "max_instances")     # le champ n'existe plus
    scene = Scene(name="S")
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    assert scene_pool_instances(scene, ball) == 0
    assert scene_oam_layout(p, scene).pools == []


def test_une_scene_ne_paie_que_ce_qu_elle_declare(tmp_path):
    ball = Prefab(name="Ball")
    s1 = Scene(name="Menu")                          # ne spawne rien
    s2 = Scene(name="Level"); s2.prefab_pools = {"Ball": 10}
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert scene_oam_layout(p, s1).pool_slots == 0
    assert scene_oam_layout(p, s2).pool_slots == 10


# ── g_actors = MAX des scènes, pas la somme ───────────────────────────

def test_taille_g_actors_est_le_max_pas_la_somme(tmp_path):
    ball = Prefab(name="Ball")
    s1 = Scene(name="Menu", actors=[Actor(name="Cursor")])          # used 1
    s2 = Scene(name="Level", actors=[Actor(name=f"E{i}") for i in range(4)])
    s2.prefab_pools = {"Ball": 6}                                   # used 10
    p = _projet(tmp_path, scenes=[s1, s2], prefabs=[ball])
    assert project_actor_count(p) == 10        # max(1, 10), pas 11


def test_projet_vide_plancher_a_un(tmp_path):
    p = _projet(tmp_path, scenes=[Scene(name="S")])
    assert project_actor_count(p) == 1         # Actor g_actors[0] ne compile pas


# ── Groupes (prefab à sous-arbre) ─────────────────────────────────────

def test_prefab_a_sous_arbre_occupe_un_groupe_par_instance(tmp_path):
    boss = Prefab(name="Boss")
    boss.children = [Actor(name="ArmL"), Actor(name="ArmR")]   # groupe = 3
    scene = Scene(name="S"); scene.prefab_pools = {"Boss": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[boss])
    assert prefab_group(boss) == 3
    pool = scene_oam_layout(p, scene).pools[0]
    assert pool.group == 3 and pool.instances == 4 and pool.size == 12


# ── Acteurs inactifs : comptés comme le build les traite (exclus) ─────

def test_les_acteurs_inactifs_ne_sont_pas_comptes(tmp_path):
    a, b = Actor(name="A"), Actor(name="B")
    b.active = False
    scene = Scene(name="S", actors=[a, b])
    p = _projet(tmp_path, scenes=[scene])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 1


# ── Ordre acteurs → UI → pools (T4) ───────────────────────────────────

def test_ui_obj_pousse_les_pools_apres_la_bande(tmp_path, monkeypatch):
    """Ordre OAM : acteurs, puis la bande d'interface en sprites, puis les pools
    (ROADMAP v0.17 T4). Le poste UI (résolu ailleurs) décale donc le départ des
    pools de `placed` à `placed + ui`, et `g_actors` grandit d'autant."""
    import codegen.oam_alloc as oa
    monkeypatch.setattr(oa, "scene_ui_obj_slots", lambda scene, project: 5)
    ball = Prefab(name="Ball")
    scene = Scene(name="S", actors=[Actor(name="A"), Actor(name="B")])
    scene.prefab_pools = {"Ball": 4}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball])
    lay = scene_oam_layout(p, scene)
    assert lay.placed == 2 and lay.ui == 5
    assert lay.pools[0].start == 7          # 2 acteurs + 5 slots d'UI
    assert lay.used == 11 and project_actor_count(p) == 11


# ── Déterminisme ──────────────────────────────────────────────────────

def test_layout_deterministe(tmp_path):
    ball, boss = Prefab(name="Ball"), Prefab(name="Boss")
    scene = Scene(name="S", actors=[Actor(name="A")])
    scene.prefab_pools = {"Ball": 3, "Boss": 2}
    p = _projet(tmp_path, scenes=[scene], prefabs=[ball, boss])
    a = [(pl.sym, pl.start, pl.size) for pl in scene_oam_layout(p, scene).pools]
    b = [(pl.sym, pl.start, pl.size) for pl in scene_oam_layout(p, scene).pools]
    assert a == b
    # Ordre = ordre du catalogue de prefabs (stable), pas celui du dict.
    assert [s for s, _, _ in a] == ["S_Ball", "S_Boss"]
