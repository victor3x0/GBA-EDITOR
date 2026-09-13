"""Persistance et synchronisation des ressources d'un projet.

Ce package possède la frontière disque ↔ modèles : stores, index léger à
venir, et réconciliation des fichiers déposés hors de l'éditeur. Les écrans
passent par :class:`core.project.Project`, jamais par ces modules directement.
"""
