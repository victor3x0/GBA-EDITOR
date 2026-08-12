"""
core/engine_emulation/ — ce que l'éditeur REFAIT en Python parce que la console le
fait en C.

Une règle vaut pour tout ce qui est rangé ici, et c'est la raison d'être du
dossier : **ces modules ont un jumeau dans `runtime/`, et les deux doivent
rester d'accord.** Corriger une formule d'un côté sans l'autre ne casse rien, ne
lève aucune erreur, et ne se voit qu'à l'œil — l'aperçu montre une chose, la ROM
en produit une autre. C'est le pire mode de panne du projet, parce que
l'utilisateur ne peut pas savoir lequel des deux ment.

Ce n'est PAS du code partagé. Quand le build et l'aperçu appellent la même
fonction (`nine_slice`, `models/tile_codec`), il n'y a rien à tenir d'accord :
il n'y a qu'une implémentation. Ici il y en a deux, dans deux langages, et c'est
inévitable — le C tourne sur l'ARM, Python dessine dans une fenêtre.

Ce qui vit ici aujourd'hui, et son jumeau :

    text_layout.py    <-> text_layout()  dans runtime/include/gba_engine.h
                          (ligatures, chasses, coupe au mot, repli)
    blend_preview.py  <-> les formules BLDCNT/BLDALPHA/BLDY du moteur
                          (alpha saturé, éclaircir vers le blanc, assombrir)
    mod_render.py     <-> le mixeur logiciel Maxmod (taux réduit, plus proche
                          voisin — le GBA n'interpole pas)
    mod_file.py           le format ProTracker que mod_render.py lit

Avant d'ajouter un fichier ici, poser la question : y a-t-il vraiment DEUX
implémentations ? Si une seule suffit, elle va ailleurs et tout le monde
l'appelle.
"""
