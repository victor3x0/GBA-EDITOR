"""Paquet de génération : conversion d'assets, émission du C, build de la ROM.

`BuildWorker` est exposé ici pour que l'application écrive `from codegen import
BuildWorker` sans connaître le fichier qui le porte.

**Importé PARESSEUSEMENT** (PEP 562), et c'est nécessaire, pas une élégance :
importer `codegen.quoi_que_ce_soit` exécute d'abord ce fichier. Tant qu'il
tirait `rom_build` immédiatement, le moindre accès à un petit module du paquet
— `codegen.c_names`, sept lignes sans aucune dépendance — traînait derrière lui
toute la chaîne de build, jusqu'à `core.project`. Un module de bas niveau qui
voulait juste fabriquer un identifiant C se retrouvait donc en boucle avec le
projet.

La règle qui en découle : **ce fichier ne doit rien importer au chargement.**
Ajouter un `from codegen.X import Y` en tête ici, c'est le remettre sur le dos
de chaque module du paquet.
"""

__all__ = ["BuildWorker"]


def __getattr__(name):
    if name == "BuildWorker":
        from codegen.rom_build import BuildWorker
        return BuildWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
