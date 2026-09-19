"""editor/codegen/actor_budget.py — le budget d'acteurs d'une scène.

Source de vérité UNIQUE pour « combien d'entrées de `g_actors[]` une scène
réserve, et comment elle les dépense » (ROADMAP v0.17). Même famille que
`window_alloc.py` / `palette_alloc.py` : résolu au BUILD, en Python — le
nombre d'acteurs d'une scène ne change pas en cours de partie.

Le budget est DÉRIVÉ, pas réparti (ROADMAP v0.17, révisé le 2026-09-19). Il a
TROIS postes et UN plafond :

    acteurs posés  +  OBJ d'interface  +  slots de pool  =  128

Les deux premiers postes se COMPTENT (ils sont résolus au build : leur nombre
est connu, pas estimé) ; seul le pool se DÉCLARE. Le budget prefab n'est donc
pas une tranche réservée à la main — c'est ce que les deux autres laissent :

    budget_prefab = 128 − acteurs_posés − OBJ_UI

Cela remplace l'ancien partage 96/32 (`DEFAULT_ACTOR_SLOTS`), qui était un
plafond fixe posé à la main, contraire au reste du projet (l'allocateur de
charblock calcule le placement au lieu de le régler). `Scene.actor_slots`
survit comme OVERRIDE optionnel (0 = auto = compté), gardé pour un réglage
manuel ultérieur ; plus aucune scène neuve ne le sème.

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
    """Le poste « acteurs » du budget : ce que la scène occupe pour ses acteurs
    posés.

    0 = automatique : le poste vaut le nombre d'acteurs réellement posés — les
    acteurs se comptent, ils ne se réservent pas (révision 2026-09-19). Une
    valeur > 0 est un OVERRIDE manuel, gardé pour plus tard ; aucune scène neuve
    ne le pose. S'il est un jour exposé et réglé SOUS le nombre d'acteurs posés,
    l'avertissement « posés > réservés » devra revenir — il a été retiré du
    budget parce que le cas automatique ne peut pas le déclencher.
    """
    return scene.actor_slots if scene.actor_slots > 0 else len(scene.actors)


def scene_ui_obj_slots(scene: Scene, project) -> int:
    """Entrées OAM que les OBJ d'INTERFACE de cette scène consomment — bandes de
    texte en cible OBJ, `ui_image`, fonts OBJ.

    Vaut 0 pour l'instant (B1) : ces comptes existent côté build mais au niveau
    PROJET (union de toutes les scènes — `obj_text_alloc` / `ui_image_sprites`
    dans `runtime_codegen/main_gen.py`), pas par scène. Les décomposer par scène
    est la tranche B2 du chantier, qui suit la compilation par scène — c'est là
    que ce poste cesse d'être nul et que le vrai gain OAM se joue (ROADMAP v0.17,
    « le budget compte TOUS ses consommateurs »).
    """
    return 0


def scene_actor_budget(scene: Scene, project) -> dict:
    """Tout ce que la carte « Actor budget » affiche, en un seul appel — pour
    que l'inspecteur n'ait aucune arithmétique à refaire de son côté.

    Budget dérivé (révision 2026-09-19) : trois postes comptés/déclarés, une
    seule faute possible — le total déborde des 128 entrées du matériel
    (`over_budget`). L'ancien `over_placed` a disparu avec la réservation.
    """
    actors = scene_actor_slots(scene)
    ui     = scene_ui_obj_slots(scene, project)
    pool   = scene_pool_slots(scene, project)
    placed = len(scene.actors)
    used   = actors + ui + pool
    return {
        "actors":       actors,
        "ui":           ui,
        "pool":         pool,
        "placed":       placed,
        "used":         used,
        "total":        OAM_LIMIT,
        "free":         OAM_LIMIT - used,
        "over_budget":  used > OAM_LIMIT,
    }
