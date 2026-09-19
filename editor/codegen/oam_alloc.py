"""editor/codegen/oam_alloc.py — allocation des 128 entrées OAM, PAR SCÈNE.

Source de vérité UNIQUE pour « quelle entrée de `g_actors[]` occupe chaque
acteur posé et chaque instance de pool d'UNE scène », sur le modèle de
`palette_alloc.py` pour les 16 banques de palette. Résolu au BUILD, en Python :
le nombre d'acteurs d'une scène ne change pas en cours de partie.

Le fait matériel qui autorise ce fichier : **une seule scène est vivante à la
fois** sur GBA. Chaque `scene_init` réutilise donc la même fenêtre OAM en
repartant de l'entrée 0 — ses acteurs posés d'abord, puis les pools de prefabs
QU'ELLE déclare (`Scene.prefab_pools`), sans porter ceux des autres scènes.
`g_actors[]` est dimensionné sur la scène la plus gourmande (max, pas somme),
et la RAM est partagée entre scènes.

Avant ce module, la géométrie OAM était **éparpillée et recalculée en trois
endroits qui devaient rester d'accord sans se parler** : la boucle `pool_offset`
de `headers.generate_actor_types`, `_pool_info` de `main_gen`, et les décomptes
de `actor_budget`. `oam_alloc` est la géométrie ; ces trois-là en deviennent des
LECTEURS.

Deux unités à ne pas confondre, converties ici :

  - un pool se DÉCLARE en instances (`Scene.prefab_pools`) ;
  - un pool se PAIE en slots — instances × parties, un prefab à sous-arbre
    occupant un groupe contigu par instance (ROADMAP v0.23).

Le plafond est celui du matériel : l'OAM de la GBA compte 128 entrées. Il ne se
règle nulle part — ce n'est pas une préférence. Un acteur SANS sprite ne
consomme aucune entrée OAM ; le budget les compte quand même (un seul nombre
lisible vaut mieux que deux plafonds — cf. [[project_v17_scene_pool]]).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from codegen.c_names import sym as c_sym
from core.models.scene import Scene

# Les 128 entrées de l'OAM. Le seul plafond du fichier, et il vient du matériel.
# `actor_budget` (façade de l'inspecteur) le ré-exporte pour ne pas le dupliquer.
OAM_LIMIT = 128


def prefab_group(prefab) -> int:
    """Entrées de `g_actors` qu'occupe UNE instance : la racine plus ses
    parties. Un prefab plat vaut 1.

    C'est ICI que le calcul vit désormais : `main_gen` et `actor_budget`
    l'importent (ROADMAP v0.17, le pool par scène rapatrie sa géométrie ici)."""
    return 1 + len(getattr(prefab, "children", []) or [])


def scene_pool_instances(scene: Scene, prefab) -> int:
    """Ce que CETTE scène déclare pour ce prefab — 0 si elle ne le spawne pas.

    Le pool est per-scène depuis que la compilation l'est (ROADMAP v0.17,
    T1+T2+T3) : plus de `max` inter-scènes ni de repli sur `Prefab.max_instances`
    — chaque scène paie EXACTEMENT ce qu'elle déclare."""
    return int(scene.prefab_pools.get(getattr(prefab, "name", str(prefab)), 0) or 0)


def scene_actor_slots(scene: Scene) -> int:
    """Le poste « acteurs » : les entrées que la scène occupe pour ses acteurs
    posés ACTIFS.

    0 = automatique : le poste vaut le nombre d'acteurs réellement posés — les
    acteurs se comptent, ils ne se réservent pas (ROADMAP v0.17). Une valeur > 0
    est un OVERRIDE manuel, gardé pour plus tard ; aucune scène neuve ne le pose.

    « réellement posés » = ACTIFS : le build n'émet que les acteurs actifs
    (`rom_build`, `scene_actors`), donc c'est sur eux que repose la géométrie —
    et non sur `len(scene.actors)`, qui compterait un acteur désactivé auquel
    aucune entrée OAM n'est jamais assignée."""
    if scene.actor_slots > 0:
        return scene.actor_slots
    return sum(1 for a in scene.actors if getattr(a, "active", True))


def scene_ui_obj_slots(scene: Scene, project) -> int:
    """Entrées OAM que les OBJ d'INTERFACE de cette scène consomment — bandes de
    texte en cible OBJ, images d'UI, fonds de conteneur en sprites (ROADMAP
    v0.17, T4). Posé ENTRE les acteurs et les pools : le build réserve la bande
    OBJ juste après les acteurs, et `scene_oam_layout` fait donc démarrer les
    pools à `placed + ui`.

    Délégué à `gen_text.scene_obj_ui_slots` (import paresseux — c'est le domaine
    texte/UI qui résout sprites et table de textes ; le charger au niveau module
    ferait remonter tout l'émetteur de texte dans ce petit allocateur, et
    l'inspecteur qui lit le budget avec lui). Défensif : un projet à demi chargé
    (asset manquant) ne doit pas faire tomber le budget — 0 alors, le poste UI
    reste sûrement sous-compté plutôt que de lever."""
    try:
        from codegen.runtime_codegen.gen_text import scene_obj_ui_slots
        return int(scene_obj_ui_slots(project, scene) or 0)
    except Exception:
        return 0


@dataclass
class PoolSlot:
    """La géométrie d'un pool de prefab dans UNE scène, repartant de la base
    OAM 0 de cette scène. `sym` est PRÉFIXÉ PAR LA SCÈNE (`<scène>_<prefab>`) :
    chaque scène compile ses propres unités de prefab contre SA géométrie
    (ROADMAP v0.17, T1), donc les symboles ne peuvent plus être project-wide."""
    prefab: object
    prefab_sym: str    # symbole nu du prefab (c_sym du nom)
    sym: str           # symbole scène-préfixé : f"{scene_sym}_{prefab_sym}"
    start: int         # 1ère entrée de g_actors du pool, dans la fenêtre de la scène
    instances: int
    group: int

    @property
    def size(self) -> int:
        """Entrées de `g_actors` réservées — instances × parties (ROADMAP v0.23)."""
        return self.instances * self.group


@dataclass
class OamLayout:
    """La fenêtre OAM d'UNE scène, base 0 : acteurs actifs POSÉS [0..placed),
    puis les pools qu'elle déclare, contigus. C'est la GÉOMÉTRIE DE BUILD — ce
    que `g_actors` réserve et où chaque instance atterrit. Lu par `headers` et
    `main_gen` ; la façade `actor_budget` la lit aussi pour l'inspecteur.

    Le poste est bâti sur `placed`, jamais sur l'override `Scene.actor_slots` :
    le build historique posait les acteurs et démarrait les pools juste après
    les acteurs RÉELLEMENT actifs, sans jamais consulter l'override (qui n'est
    qu'un indicateur de réservation pour l'inspecteur). Faire commencer un pool
    à l'override gonflerait `g_actors` de tous les slots réservés-mais-vides —
    une scène de démo restée à 96 (ancien défaut 96/32) paierait 93 entrées OAM
    fantômes. L'override vit donc UNIQUEMENT dans la façade budget."""
    scene: Scene
    scene_sym: str
    placed: int              # acteurs actifs réellement posés
    ui: int                  # OBJ d'interface (stub 0 jusqu'à T4)
    pools: list[PoolSlot]

    @property
    def pool_slots(self) -> int:
        return sum(pl.size for pl in self.pools)

    @property
    def used(self) -> int:
        """Empreinte OAM réelle de la scène — ce que `g_actors` doit couvrir."""
        return self.placed + self.ui + self.pool_slots

    @property
    def free(self) -> int:
        return OAM_LIMIT - self.used

    @property
    def over_budget(self) -> bool:
        return self.used > OAM_LIMIT

    def pool_for(self, prefab) -> Optional[PoolSlot]:
        """Le PoolSlot de ce prefab dans cette scène, ou None si non déclaré."""
        name = getattr(prefab, "name", str(prefab))
        pref = c_sym(name)
        return next((pl for pl in self.pools if pl.prefab_sym == pref), None)


def scene_oam_layout(project, scene: Scene) -> OamLayout:
    """Géométrie OAM déterministe d'une scène (base 0). Mêmes (project, scene)
    -> même layout : `headers` (TAG_/POOL_) et `main_gen` (spawn/pi/g_actors)
    restent cohérents sans se coordonner.

    Ordre des pools = ordre du catalogue `project.prefabs` (stable), pour que
    l'offset d'un pool ne dépende que de la scène, jamais de l'ordre d'appel."""
    scene_sym = c_sym(scene.name)
    placed = sum(1 for a in scene.actors if getattr(a, "active", True))
    ui = scene_ui_obj_slots(scene, project)

    pools: list[PoolSlot] = []
    offset = placed + ui
    for pf in project.prefabs:
        n = scene_pool_instances(scene, pf)
        if n <= 0:
            continue
        pref = c_sym(pf.name)
        pools.append(PoolSlot(
            prefab=pf, prefab_sym=pref, sym=f"{scene_sym}_{pref}",
            start=offset, instances=n, group=prefab_group(pf),
        ))
        offset += n * prefab_group(pf)

    return OamLayout(scene=scene, scene_sym=scene_sym,
                     placed=placed, ui=ui, pools=pools)


def project_actor_count(project) -> int:
    """Taille de `g_actors[]` : la scène la plus gourmande (MAX, pas somme).

    Une seule scène est vivante à la fois et chaque `scene_init` repart de la
    base 0 : dimensionner sur le max suffit, la somme des unions faisait payer à
    la scène de menu les slots des balles du niveau d'action (ROADMAP v0.17).
    Plancher à 1 — un `Actor g_actors[0]` ne compile pas."""
    return max((scene_oam_layout(project, sc).used for sc in project.scenes),
               default=0) or 1
