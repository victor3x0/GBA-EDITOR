"""editor/codegen/actor_budget.py — le budget d'acteurs d'une scène.

Source de vérité UNIQUE pour « combien d'entrées de `g_actors[]` une scène
réserve, et comment elle les dépense » (ROADMAP v0.17). Même famille que
`window_alloc.py` / `palette_alloc.py` : résolu au BUILD, en Python — le
nombre d'acteurs d'une scène ne change pas en cours de partie.

Le budget a DEUX postes et UN plafond :

    acteurs posés (réservés)  +  slots de pool  =  128

Le plafond est celui du matériel : l'OAM de la GBA compte 128 entrées, donc
128 sprites affichables. Il ne se règle nulle part, et surtout pas dans les
réglages de projet — ce n'est pas une préférence.

Une simplification est assumée, et elle est écrite dans la ROADMAP : un acteur
SANS sprite ne consomme aucune entrée OAM, le matériel en accepterait donc plus
de 128. Le budget les compte quand même — un seul nombre lisible vaut mieux que
deux plafonds dont l'auteur devrait suivre lequel s'applique.

Deux unités à ne pas confondre, et c'est ici qu'elles se convertissent :

  - un pool se DÉCLARE en instances (`Scene.prefab_pools`) ;
  - un pool se PAIE en slots — instances × parties, un prefab à sous-arbre
    occupant un groupe contigu par instance (ROADMAP v0.23).
"""
from __future__ import annotations

from core.models.scene import Scene

# Les 128 entrées de l'OAM. Le seul plafond du fichier, et il vient du
# matériel : cf. docstring de module pour ce qu'il compte et ce qu'il
# sur-compte volontairement.
OAM_LIMIT = 128

# Le partage d'une scène NEUVE : trois quarts pour ce qu'elle pose, un quart
# pour ce qu'elle spawne. Ce n'est pas une contrainte, c'est un point de départ
# — un chiffre rond qui montre d'emblée que le budget SE PARTAGE, là où « 0 =
# auto » laissait croire que poser des acteurs ne coûtait rien.
#
# Les 32 slots de pool ne sont écrits nulle part : ils SONT ce que le champ
# acteurs laisse. Un seul nombre stocké, pas deux à tenir d'accord.
#
# N'est PAS le défaut du dataclass `Scene.actor_slots`, qui reste 0 : une scène
# déjà écrite garde son comportement automatique, sinon tout projet existant
# réserverait 96 entrées par scène du jour au lendemain. Ce défaut ne vaut que
# pour une scène qui naît (cf. `command_dispatcher.add_scene`).
DEFAULT_ACTOR_SLOTS = 96


def prefab_group(prefab) -> int:
    """Entrées de `g_actors` qu'occupe UNE instance : la racine plus ses
    parties. Un prefab plat vaut 1.

    Dupliqué depuis `runtime_codegen/main_gen.py` ? Non — c'est l'inverse :
    `main_gen` importe celui-ci. Le calcul vivait dans le générateur de `main.c`
    alors que l'éditeur en a besoin pour afficher le budget, bien avant tout
    build.
    """
    return 1 + len(getattr(prefab, "children", []) or [])


def prefab_pool_instances(project, prefab) -> int:
    """Combien d'instances simultanées ce prefab peut avoir, tous niveaux
    confondus.

    C'est le SEUL point du build qui réponde à cette question, et il la pose
    aux scènes, pas au template. Tant que les scripts sont compilés une fois
    pour le projet (`POOL_<X>_SIZE` est une constante unique, cf. `headers.py`),
    le pool émis doit couvrir la scène la plus gourmande : d'où le MAXIMUM et
    non la somme. La moitié codegen de la v0.17 — la compilation par scène —
    rendra ce maximum inutile et chaque scène paiera le sien.

    Repli sur `Prefab.max_instances` quand AUCUNE scène ne déclare de pool pour
    ce prefab : c'est le champ hérité (cf. `models/scene.Prefab`), sans quoi
    tout projet antérieur à ce chantier verrait ses prefabs cesser
    silencieusement d'être spawnables. Dès qu'une scène déclare quoi que ce
    soit, l'ancien champ n'est plus consulté.
    """
    name = getattr(prefab, "name", str(prefab))
    declared = [int(s.prefab_pools.get(name, 0) or 0) for s in project.scenes]
    if any(n > 0 for n in declared):
        return max(declared)
    return int(getattr(prefab, "max_instances", 0) or 0)


def scene_pool_instances(scene: Scene, prefab) -> int:
    """Ce que CETTE scène déclare pour ce prefab — 0 si elle ne le spawne pas.

    Distinct de `prefab_pool_instances` : celui-ci dit l'intention de l'auteur,
    l'autre dit ce que la ROM alloue réellement aujourd'hui. Les deux
    coïncideront quand la compilation par scène sera là.
    """
    return int(scene.prefab_pools.get(getattr(prefab, "name", str(prefab)), 0) or 0)


def scene_pool_slots(scene: Scene, project) -> int:
    """Entrées de `g_actors` que les pools de cette scène consomment —
    instances × parties, sommées sur les prefabs qu'elle déclare."""
    total = 0
    for pf in project.prefabs:
        n = scene_pool_instances(scene, pf)
        if n > 0:
            total += n * prefab_group(pf)
    return total


def scene_actor_slots(scene: Scene) -> int:
    """Ce que la scène RÉSERVE pour ses acteurs posés.

    0 = automatique : la réservation vaut le nombre d'acteurs réellement posés.
    C'est le comportement d'avant ce champ, donc celui de toute scène
    antérieure — le défaut ne s'invente rien.
    """
    return scene.actor_slots if scene.actor_slots > 0 else len(scene.actors)


def scene_actor_budget(scene: Scene, project) -> dict:
    """Tout ce que la carte « Actor budget » affiche, en un seul appel — pour
    que l'inspecteur n'ait aucune arithmétique à refaire de son côté.

    `over` couvre les deux dépassements possibles, qui ne sont pas la même
    faute : le budget déborde des 128 entrées du matériel (`over_budget`), ou
    la scène pose plus d'acteurs qu'elle n'en réserve (`over_placed`).
    """
    reserved = scene_actor_slots(scene)
    pool     = scene_pool_slots(scene, project)
    placed   = len(scene.actors)
    return {
        "reserved":     reserved,
        "pool":         pool,
        "placed":       placed,
        "used":         reserved + pool,
        "total":        OAM_LIMIT,
        "free":         OAM_LIMIT - reserved - pool,
        "over_budget":  reserved + pool > OAM_LIMIT,
        "over_placed":  placed > reserved,
    }
