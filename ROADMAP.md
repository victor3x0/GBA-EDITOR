
# Roadmap

Ce document explique **le pourquoi** derrière les jalons qui restent à ouvrir : le scope,
les décisions déjà verrouillées avant même de commencer, et les questions volontairement
laissées ouvertes.

Une fois un jalon **livré**, son détail quitte ce fichier : une ligne part au
[CHANGELOG](CHANGELOG.md), la discussion complète (décisions verrouillées, pièges rencontrés,
mesures) part dans [changelog-archive/](changelog-archive/), un fichier par version. Rien n'est
perdu, ça change juste d'endroit — pour rouvrir une décision passée, c'est là qu'elle est.

Six documents, six rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| [CHANGELOG](CHANGELOG.md) | qui veut savoir ce qui a changé | une entrée courte par version livrée |
| [changelog-archive/](changelog-archive/) | qui rouvre une décision passée | le détail complet d'une version livrée |
| **ce fichier** | qui décide de la suite | scope, décisions, ouvert — jalons **non livrés** seulement |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |
| [SCRIPTING](SCRIPTING.md) | qui écrit un script | le Lua accepté, et ce qui ne l'est pas |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel — on ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement, le contexte du moment valant mieux que des
suppositions faites à l'avance.

---

## Où on en est

| Version | Sujet | État |
| --- | --- | --- |
| v0.2 | Palettes de couleurs | **Livrée**, quelques finitions — [archive](changelog-archive/v0.2.md) |
| v0.3 | Background vivant, texte et interface | **Livrée**, un report assumé — [archive](changelog-archive/v0.3.md) |
| v0.4 | Animation de décor | **Livrée** — [archive](changelog-archive/v0.4.md) |
| v0.5 | Sauvegarde | **Livrée** — [archive](changelog-archive/v0.5.md) |
| v0.6 | Polish de la boucle de jeu | **Livrée**, rouverte pour le game feel — [archive](changelog-archive/v0.6.md) |
| v0.7 | Structures de données, et le langage | **Livrée**, les deux chantiers rouverts avec — [archive](changelog-archive/v0.7.md) |
| v0.8 | Son : la musique par scène, les transitions, le mixage | **Livrée** — [archive](changelog-archive/v0.8.md) |
| v0.14 | Diagnostic (trace de débogage, budget) | **Livrée**, réduite au frame+OAM (canaux/DMA non mesurables) — [archive](changelog-archive/v0.14.md) |
| v0.19 | Le sous-pixel | **Livrée** — [archive](changelog-archive/v0.19.md) |
| v0.24 | Le projet à l'échelle d'une équipe | **En cours** — formats livrés, build et chargement à faire |
| v0.20 | L'état du monde : les collections persistantes | **Livrée** — [archive](changelog-archive/v0.20.md) |
| v0.23 | Ce qu'un boss demande | **Livrée** — [archive](changelog-archive/v0.23.md) |
| v0.21 | Le texte adressable : le dialogue piloté par la donnée | **Livrée** — [archive](changelog-archive/v0.21.md) |
| v0.22 | Menus, listes et curseur | **En cours** — navigation livrée ; en-tête de sauvegarde à faire |
| v0.9 | Traduction des jeux | Non commencée |
| v0.10 | Distribution Linux | Non commencée |
| v0.11 | Traduction de l'éditeur | Non commencée |
| v0.12 | Vue d'ensemble (graphe des scènes) | Non commencée |
| v0.13 | Édition mixte (appels d'API en blocs) | Non commencée |
| v0.15 | Visibilité des éléments d'interface | **Livrée**, sous une autre forme que prévu — [archive](changelog-archive/v0.15.md) |
| v0.16 | L'API : règle de construction et rangement | Non commencée |
| v0.17 | Le pool par scène | Non commencée |
| v0.18 | La valeur affichée : d'où elle vient | Non commencée |

Les sept lignes qui suivent la v0.8 — de la v0.14 à la v0.22 — sont rangées dans leur **ordre
de traitement recommandé**, issu de la revue « projet de production » du 2026-08-19 et détaillé
dans sa section, juste après ce tableau : **v0.14 → v0.19 → v0.24 → v0.20 → v0.23 → v0.21 →
v0.22**. Cinq d'entre elles (v0.14, v0.19, v0.20, v0.23, v0.21) sont livrées et archivées ; seules
**v0.24** et **v0.22** restent détaillées plus bas, dans cet ordre. Les jalons restants (v0.9 à
v0.18, hors ceux déjà cités) n'ont pas de priorité tranchée entre eux et restent dans leur ordre
numérique, à la suite du bloc priorisé.

Un numéro de version reste une **identité**, pas un rang : il n'est pas renuméroté quand
l'ordre de traitement change. Seul l'ordre de LECTURE de ce document — et l'ordre dans lequel
les chantiers seront ouverts — suit désormais l'ordre de traitement.

---

## Ce que la revue « projet de production » a relevé (2026-08-19)

Les six versions qui suivent viennent d'une seule séance : la relecture du logiciel du point
de vue d'un **projet cible** — un metroidvania à composante RPG (dialogues denses, arbre de
compétences, physique fine) et à combats de boss scénarisés (phases, projectiles, effets,
ambiance), mené par une **équipe de trois** : un programmeur, un sound designer, un pixel
artiste, avec une cartouche réelle au bout.

Ce ne sont pas des idées de fonctionnalités. Chacune est un point où ce projet-là **s'arrête**,
ou paie un prix qui ne se rattrape plus en fin de production. Elles passent avant la v1.0
parce que la v1.0 affirme « le logiciel absorbe un projet 2D de production », et qu'elle
déclare le platformer et le metroidvania « atteignables aujourd'hui » : la revue dit où c'est
faux.

**L'ordre recommandé n'est pas l'ordre des numéros** — un numéro est une identité, pas un
rang :

| Rang | Version | Pourquoi là |
| --- | --- | --- |
| 1 | **v0.14** — Diagnostic | Un combat de boss est l'endroit exact où le budget de frame se perd. Sans mesure, tout le reste se règle à l'aveugle. |
| 2 | **v0.19** — Le sous-pixel | Décide si le genre est faisable. Touche la structure `Actor` : plus il arrive tard, plus il casse de projets. |
| 3 | **v0.24** — Le projet à l'échelle d'une équipe | Les formats non fusionnables plafonnent l'outil au travail solitaire **dès la première semaine**, pas à la v1.0. |
| 4 | **v0.20** — Collections persistantes | Sans elle, l'état d'un monde metroidvania s'écrit à la main, une variable par coffre. |
| 5 | **v0.23** — Ce qu'un boss demande | Trois manques déjà connus, réunis par un seul cas d'usage. |
| 6 | **v0.21** — Le texte adressable | Débloque le dialogue dense ; la v0.9 (traduction) en dépend. |
| 7 | **v0.22** — Menus, listes et curseur | Le plus gros chantier, et le seul dont la forme reste ouverte. |

---

## v0.24 — Le projet à l'échelle d'une équipe — **EN COURS**

> **Volets « formats » et « build » livrés le 2026-08-20.** Le projet démo passe de 14 444 à
> 3 679 lignes de JSON, donnée pour donnée (vérifié par un aller-retour save/reload comparant
> les modèles, et par un build complet dont la ROM ne bouge pas). Le **rebuild à chaud** passe
> de 9,09 s à 6,56 s, dont `make` de 3,50 s à 0,17 s : plus aucun des 41 fichiers générés
> n'est réécrit quand rien n'a changé. Restent le **cache de conversion des assets** (~1 s,
> devenu le plus petit poste) et le **chargement paresseux** — que la mesure repousse
> explicitement, cf. « Ouvert ».

### L'état des lieux, relevé avant d'ouvrir le chantier (2026-08-19)

Trois points, dont un est déjà écrit en v1.0 — et c'est **la date qui change**, pas le
constat.

- **Les formats.** « Des formats que git sait relire » est le deuxième des quatre prérequis de
  la v1.0. Mais il ne se comporte pas comme un prérequis de v1.0 : à trois personnes, deux
  commits sur la même scène ne se fusionnent **pas**, et l'historique devient inexploitable dès
  la première semaine. Ce n'est pas une finition, c'est un préalable — et plus il est repoussé,
  plus l'historique qu'il faudra traverser est illisible.
- **Le build.** `make` est appelé sans `-j`
  ([rom_build.py:813](editor/codegen/rom_build.py:813)) : la compilation est **sérielle**. Et
  rien ne met en cache la conversion des assets — chaque build repasse grit sur tout le
  catalogue. Le temps d'itération grandit donc linéairement avec le nombre d'assets, alors que
  l'itération est exactement ce qui fait ou défait un combat de boss.
- **Le chargement.** `Project.load()` charge tout, tout de suite (déjà noté en v1.0). Pong et
  ses 118 fichiers vont bien ; quarante scènes et deux cents sprites, personne n'en sait rien.

### Décisions verrouillées

- **Les formats d'abord, et il n'y a rien à concevoir.** La correction est déjà écrite en
  v1.0 : une ligne de texte par rangée de grille — ce que `tileset` fait déjà, et c'est de loin
  la partie la plus lisible du sidecar — et les couleurs en hexadécimal (`#39A8FF`), **les deux
  formes acceptées en lecture**. Il reste à le faire, et à le faire avant que le projet cible
  n'accumule un historique qu'on ne relira jamais.
- **L'écriture bascule TOUT DE SUITE, la lecture accepte les deux pour de bon.** Aucun
  convertisseur à lancer : le premier enregistrement d'un fichier le réécrit. À plusieurs,
  l'ancienne forme n'est pas dans le passé mais **dans la branche d'à côté** — c'est ce qui
  justifie de garder deux lecteurs, alors que le projet refusait jusqu'ici toute migration de
  format (cf. l'en-tête de `core/project.py`, corrigé en conséquence). *(Tranché le
  2026-08-20.)*
- **La mise en page ne dépend QUE du nom de la clé.** Une règle « compact tant que la ligne
  fait moins de N caractères » ferait re-couler tout un fichier au premier changement de
  valeur — soit exactement le diff illisible qu'on cherche à supprimer. Les clés concernées
  sont listées une fois, dans `core/project_json.py`. *(Tranché le 2026-08-20.)*

### La mesure a contredit la justification (2026-08-20)

Le constat d'ouverture disait « deux commits sur la même scène ne se fusionnent **pas** ».
**C'est faux, et c'est l'inverse qui est vrai.** `git merge-file` travaille à la ligne : un
scalaire par ligne offrait donc la granularité *maximale*. Sur `Arena.json`, douze scénarios
de modifications concurrentes (cellules voisines, zones 4×4 côte à côte, bandes, colonnes) —
l'ancien format plat fusionne proprement dans **tous**, le format en rangées fait conflit dès
que deux personnes touchent la même rangée.

La décision verrouillée a quand même été maintenue, mais pour **l'autre** raison — la seule
qui tienne à la mesure :

- **Ce qui est gagné : l'historique se relit.** Un diff disait « ligne 347 : 0 → 1 », ce dont
  personne ne tire rien. Il montre maintenant la rangée entière, à sa place dans la carte. Et
  le projet démo passe de **14 444 à 3 679 lignes de JSON** (police : 2 251 → 235 ; scène :
  794 → 174) sans qu'une seule donnée change.
- **Ce qui est perdu, et assumé : la fusion automatique d'une même rangée.** Deux personnes
  qui peignent la même bande de carte se chevauchent réellement ; l'ancien format leur rendait
  en silence une carte que ni l'une ni l'autre n'avait voulue. Le conflit est désormais
  visible — et résoluble à l'œil, puisque la rangée se lit.

C'est la trace de ce qu'il ne faut pas re-supposer : sur ce sujet, « plus compact » et « mieux
fusionné » tirent en sens **opposés**.
- **`-j` n'est pas un réglage.** Le nombre de cœurs se lit ; le build en profite. Une case de
  plus à expliquer n'achèterait rien.
- **Le cache de conversion se fait sur l'EMPREINTE de la source et des options, pas sur la
  date.** Une date de fichier change à chaque `git checkout` : un cache daté serait inutile
  exactement là où il sert le plus, c'est-à-dire en changeant de branche à trois.
- **On ne réécrit pas un fichier identique.** Corollaire de la règle ci-dessus, appliqué un
  cran plus haut : plutôt que de construire un cache À CÔTÉ du compilateur, on rend au
  compilateur le seul signal dont il a besoin pour utiliser le sien. Tout ce que le build
  dépose dans `build/` passe par `codegen/build_output.py`. *(Tranché le 2026-08-20.)*
- **Le ménage se fait à la FIN, par balayage, pas au début par `rmtree`.** Ce que ce build-ci
  n'a pas produit n'a plus lieu d'être compilé — même garantie qu'avant contre un `.c` périmé
  ramassé au glob par le Makefile, sans dater à neuf tout ce qui n'a pas bougé. Un outil
  externe qui écrit lui-même (grit) doit DÉCLARER sa sortie (`build_output.claim`), sinon le
  balayage la prend pour un reste. *(Tranché le 2026-08-20.)*

### Le vrai coût d'une itération n'était pas là où on le cherchait (2026-08-20)

Le constat d'ouverture visait la conversion des assets (« chaque build repasse grit sur tout
le catalogue »). La mesure dit autre chose : un rebuild où **rien n'a changé** coûtait 9,09 s
contre 10,08 s à froid — l'itération ne profitait de rien.

La cause n'était pas dans `make`, qui faisait exactement son travail. Sur 41 fichiers générés,
**36 avaient un contenu identique au build précédent, et 32 voyaient leur date réécrite** :

- `Project.prepare_build()` faisait `rmtree` sur `src/` et `grit_out/` à chaque build. Le
  risque auquel il répondait est réel (le Makefile ramasse `src/*.c` au glob, donc un asset
  retiré laissait derrière lui un `.c` toujours compilé et lié) — mais le prix était de
  recompiler l'intégralité du projet à chaque itération.
- `grit` estampille l'heure d'export dans un commentaire de ses `.c/.h`. Ce seul commentaire
  rendait ses fichiers « différents » à chaque passage — et les faisait apparaître modifiés
  dans `git status` sans qu'un octet de donnée ait bougé. *(Troisième défaut de grit relevé
  par ce projet, après `-fa` multi-fichier et `-pn` ignoré sous `-pS`.)*

Résultat, sur Pong, 4 cœurs :

| | Avant | Après |
| --- | --- | --- |
| Build à froid | 12,29 s | 10,95 s |
| **Rebuild à chaud** | **9,09 s** | **6,56 s** |
| dont `make` à chaud | 3,50 s | **0,17 s** |
| Fichiers générés réécrits à chaud | 32 / 41 | **0 / 41** |

Vérifié aussi dans l'autre sens : un `.c` périmé déposé à la main dans `src/` est bien retiré
par le balayage, et le build reste vert.

### Ce que ça touche

Volet **formats** (fait) : [project_json.py](editor/core/project_json.py) — nouveau, il
possède à lui seul la mise en page et la forme des grilles —,
[gba_color.py](editor/core/gba_color.py) (la forme écrite d'une couleur),
[background.py](editor/core/models/background.py),
[sprite.py](editor/core/models/sprite.py),
[palette.py](editor/core/models/palette.py),
[resource_store.py](editor/core/resource_store.py) et
[project.py](editor/core/project.py). `scene.py` n'a **pas** été touché :
`collision_map` était déjà une liste de rangées, seule son écriture l'éclatait — pareil pour
les `glyphs` d'une police. Deux des quatre formats se sont donc corrigés sans toucher au
schéma, donc sans rien à relire de neuf.

Volet **build** (fait) : [build_output.py](editor/codegen/build_output.py) — nouveau, il
possède seul la règle « ne pas réécrire un fichier identique » et le balayage de fin —,
[rom_build.py](editor/codegen/rom_build.py) (`-j`, le balayage),
[project.py](editor/core/project.py) (`prepare_build` n'efface plus), et les huit émetteurs
qui écrivent dans `build/` : `grit_conversion`, `runtime_codegen/{headers, main_gen,
lua_compiler, data_tables}`, `scripting/{globals, constants}`.

Volet **chargement** (repoussé par la mesure) : [project.py](editor/core/project.py).

### Ouvert

- ~~**Le temps de build réel n'est pas mesuré.**~~ **Mesuré le 2026-08-20**, sur Pong, 4 cœurs :

  | Poste | Sériel | Après `-j4` |
  | --- | --- | --- |
  | `make` | 6,14 s (**50 %**) | 3,64 s |
  | mmutil | 0,63 s | — |
  | grit (fonds) | 0,37 s | — |
  | `Project.load()` | **0,08 s** | — |
  | **Total** | **12,29 s** | **9,92 s** |

  Trois choses que la mesure tranche : `make` est le seul poste qui vaille la peine (`-j` est
  **livré**, 1,7× dessus) ; **le chargement n'est pas un problème** — 173 fichiers en 80 ms,
  soit 0,6 % du build, donc le chantier « chargement paresseux » n'a aucune justification
  mesurée à cette échelle et attendra un projet où il en aura une ; et le cache de conversion
  ne peut plus rapporter qu'**environ 1 s**, ce qui le fait passer derrière le reste.
  Reste à refaire la mesure sur un projet gonflé artificiellement — c'est là que les pentes
  se croisent, pas sur Pong.

- **Le cache de conversion des assets reste à faire, et il ne vaut plus qu'environ 1 s.**
  Ce qui reste à chaud, une fois `make` réduit à 0,17 s : mmutil 0,66 s, grit sprites, bin2s
  0,19 s. C'est exactement le périmètre de la décision verrouillée « empreinte de la source
  et des options » — mais c'est désormais le PLUS PETIT des postes, et le mesurer sur un
  projet à deux cents assets doit précéder de l'écrire.
- ~~**Quand cesse-t-on d'ÉCRIRE l'ancien format ?**~~ **Tranché le 2026-08-20** : tout de
  suite, lecture des deux à vie, aucun convertisseur (cf. décisions verrouillées).
- **Le chargement paresseux, par collection ou par écran ?** La seconde est plus simple et
  suffit peut-être. À décider sur la mesure, pas avant — et la mesure du 2026-08-20 dit
  **pas encore** : 0,08 s pour tout charger. La question se rouvre sur un projet qui a le
  volume, pas sur celui-ci.

---

## v0.22 — Menus, listes et curseur — **EN COURS**

> **La navigation est livrée le 2026-08-21.** Un panneau d'interface peut être une LISTE :
> une propriété du conteneur existant, pas un quatrième type d'élément — « le moteur prend la
> navigation, pas la mise en page ». Ses rangées sont ses zones de texte enfants, dans l'ordre
> de l'arbre : rien à déclarer, ce qu'on voit dans l'éditeur est ce que la liste parcourt.
>
> Les quatre questions ouvertes sont tranchées, trois d'entre elles depuis les règles déjà
> écrites du projet : **rangées sur le calque de texte et défilement À LA LIGNE** (le texte
> reste sur sa grille de tuiles, l'OAM reste libre pour les acteurs et le curseur) ; **cadence
> de répétition en défaut de PROJET surchargeable par liste** (le patron de la transition de
> scène, v0.6.2 — il répond à l'objection « trois listes à trois cadences, un joueur le sent »)
> ; **un choix de dialogue est une liste comme les autres**, parce qu'un raccourci pour 2-3
> options serait le premier « widget par genre de menu », dont la liste n'a pas de fin.
>
> Le script dit combien d'items il y a (`list.set_count`) et écrit chaque rangée —
> `text.draw_in(list.row("Menu", r), …)`. Un item est une ligne de donnée : c'est ce qui fait
> qu'un inventaire, un arbre de compétences et un menu de sauvegarde se partagent le même
> mécanisme.
>
> **Le validateur du projet a attrapé une faute en cours de route** : une fonction exposée en
> Lua doit être déclarée dans `actor_api_static.h` et pas seulement dans le moteur, faute de
> quoi le C généré l'appellerait sans prototype. Deuxième leçon du même genre : le tick ne peut
> pas utiliser les `BTN_*` du script — `gba_engine.h` ne voit pas les en-têtes d'acteur —, il
> lit les `KEY_*` de libgba, qui sont les mêmes bits matériels.
>
> Reste **l'en-tête de sauvegarde étendu** (chapitre, temps de jeu, nom — lisible sans charger
> la partie), que la roadmap qualifie elle-même de manque « plus petit ».


### L'état des lieux, relevé avant d'ouvrir le chantier (2026-08-19)

`UILayout` a trois types d'éléments : texte, panneau, image
([ui_region.py](editor/core/models/ui_region.py)). **Aucun ne tient une sélection.** Un menu
s'écrit donc entièrement en script : index courant, bornes, défilement, répétition de touche,
retour arrière, et le curseur à déplacer. Sans fonction déclarable dans le langage, **chaque
écran le réécrit en entier**.

La v1.0 le note déjà, en « Ouvert » : *« si les trois genres à menus le rendent pénible, c'est
ici que ça se verra »*. La revue tranche : pour un RPG à arbre de compétences, à inventaire et
à équipement, ce n'est pas un confort qu'on jugera après coup — c'est un tiers du contenu du
jeu, et il est aujourd'hui entièrement à la charge de l'auteur.

Un manque va avec, et il est plus petit : `save.exists(slot)` répond « il y a quelque chose
ici », rien de plus (v0.5, « Ouvert »). Un écran de sélection de partie ne peut donc afficher
**ni chapitre, ni temps de jeu, ni nom** — c'est-à-dire rien de ce qu'un joueur regarde pour
choisir sa partie.

### Décisions verrouillées

- **Le moteur prend la NAVIGATION, pas la mise en page.** Une liste, c'est un `UILayout`
  existant plus quatre choses : un index courant, des bornes, un pas de défilement, et
  l'entrée qui les fait bouger. Ce qui s'affiche reste du texte et des images authorées, avec
  les outils qui existent.
- **Un item est une LIGNE DE DONNÉE, pas un objet d'interface.** Une liste se lie à un tableau
  (v0.20) ou à une table (v0.7.2), et l'auteur écrit ce qu'une ligne affiche. L'alternative —
  un widget par genre de menu — n'a pas de fin, et chaque genre de jeu en redemanderait un.
- **Le curseur est ce qui existe déjà** : un acteur `screen_space` ou une image d'UI. Pas de
  troisième chose à apprendre.
- **L'en-tête de sauvegarde s'étend, et il reste de l'auteur.** Un bloc descriptif par
  emplacement — les valeurs de N globales que l'auteur désigne — lisible **sans charger la
  partie**. Le moteur ne décide pas *ce qu'*une partie affiche, comme il ne décide pas où elle
  reprend (v0.5).

### Ce que ça touche

[ui_region.py](editor/core/models/ui_region.py),
[main_gen.py](editor/codegen/runtime_codegen/main_gen.py) (le tick d'UI),
[api.py](editor/scripting/api.py) (un domaine `list`),
[gba_engine.h](runtime/include/gba_engine.h) (l'en-tête de sauvegarde), l'inspecteur de scène,
et `validator.py`.

### Ouvert

- **Où une liste se dessine.** Sur le calque de texte — donc soumise au budget de tuiles d'UI
  et à la grille de tuiles — ou en sprites, donc dans les 128 OAM ? Les deux chemins existent
  déjà (v0.3.3) ; il faut dire lequel une liste choisit, et pourquoi.
- **Le défilement, à la ligne ou au pixel.** À la ligne, le texte reste sur sa grille et rien
  ne coûte ; au pixel, un inventaire long défile joliment mais demande un redessin partiel à
  chaque frame.
- **La répétition de touche** : réglage par liste, ou du projet ? C'est un réglage de game
  feel, donc probablement par liste — mais trois listes avec trois cadences est une incohérence
  qu'un joueur sent.
- **Ce que le moteur fait d'un choix de dialogue** (2–3 options dans une boîte) : est-ce une
  liste comme les autres, ou la seule forme qui mérite un raccourci ?

---

## v0.9 — Traduction des jeux créés avec l'éditeur

Sujet **séparé** de la traduction de l'éditeur (v0.11) : deux chantiers indépendants.

### Périmètre

- Tables de chaînes multilingues, basées sur les clés posées en v0.3 — c'est précisément pour
  éviter un refactor complet ici que les textes sont référencés par clé depuis le début.
- Sélection de la langue en jeu, persistée par la sauvegarde de la v0.5.

### Ouvert

- Format des tables multilingues non défini.
- Workflow de traduction pour quelqu'un sans compétence de développement : édition directe
  dans l'éditeur, ou export/import type tableur ?

---

## v0.10 — Distribution élargie

Réactivation de la construction Linux (en pause, en attendant un test sur une vraie
distribution).

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût récurrent — « Linux seul » est
  une option valable si le coût ne se justifie pas.

---

## v0.11 — Traduction de l'interface de l'éditeur

Complètement indépendant du runtime GBA. Déplaçable librement dans l'ordre : peut être fait
en parallèle de n'importe quelle autre version.

---

## v0.12 — Vue d'ensemble — le graphe des scènes

Un mode du Scene Canvas où chaque scène est un nœud et chaque transition une arête : on voit
la logique du jeu d'un coup, au lieu de la reconstituer en ouvrant les scripts un par un.

Pong a trois scènes ; un RPG en a quarante. C'est donc **la version qui sert le plus
directement l'affirmation de la v1.0** (« le logiciel absorbe un projet de production ») :
un projet qu'on ne peut pas parcourir n'est pas un projet qu'on peut tenir. Placée tard
malgré ça, parce que sa valeur croît avec la taille des projets — donc après la v0.7, qui les
rend gros. Comme les v0.9 à v0.11, elle se déplace librement dans l'ordre.

### Ce que ça ne coûte pas

Le graphe est **dérivé, et son index existe déjà**. `index_refs_in_project(project,
DOMAIN_SCENE)` parcourt les scripts une seule fois et rend `{scène citée: {script: nombre}}` ;
`LuaRef` porte en plus `path`, `line`, `start`, `stop` et `api_key`. Autrement dit : les
nœuds, les arêtes, leur nature (`scene.switch`) et l'emplacement exact de chaque appel sont
déjà calculables aujourd'hui. Cette version pose une vue, elle n'ajoute pas de modèle.

Et le repérage est **structurel** (AST, via les domaines de `RUNTIME_API`), pas textuel : un
commentaire qui mentionne « ARENA » ne crée pas d'arête.

### Décisions verrouillées

- **Le nœud existe parce que l'appel existe.** Le graphe ne possède rien que le script ne
  possède déjà : il projette `scene.switch` là où il se trouve. Pas de modèle parallèle, pas
  de sérialisation du graphe, donc aucune seconde source de vérité à tenir d'accord. C'est
  la même règle que celle qui gouverne toute l'édition mixte de la v0.13.
- **L'ARGUMENT s'édite, le FLUX ne s'édite pas.** Déplacer une arête de `VICTORY` vers
  `ARENA`, c'est remplacer un littéral à sa position — le mécanisme exact de
  `rename_in_text` (réécriture par offsets, mise en forme préservée octet pour octet), et
  `LuaRef` porte déjà `start`/`stop`, guillemets inclus. Le `if` qui entoure l'appel, sa
  condition et l'ordre des instructions ne sont jamais touchés. **C'est ce qui rend le geste
  sûr, et c'est la ligne à tenir.**
- **Créer une arête à partir de rien reste dehors.** Il faudrait deviner dans quel script,
  à quel endroit et sous quelle garde poser l'appel — aucune valeur par défaut n'est
  défendable. Une transition naît dans le script ; le graphe la retarge ensuite.
- **Double-clic sur une arête = ouverture du script à la ligne de l'appel.** `LuaRef` la rend
  presque gratuite, et c'est la sortie de secours pour tout ce que le graphe ne sait pas
  faire : changer la condition, déplacer l'appel, le supprimer.
- **Le graphe montre QU'un lien existe, jamais QUAND il se déclenche.** Dit explicitement
  dans l'interface plutôt que laissé à supposer : une arête n'est pas un flux, c'est une
  citation. Deux arêtes sortantes ne veulent pas dire « branchement », elles veulent dire
  « ce script cite deux scènes ».
- **Ce qui est une DONNÉE s'édite aussi** : la scène de démarrage du projet, la création
  d'une scène, le renommage (qui se propage déjà aux scripts via `rename_in_project`).

### Ouvert

- **Les cibles dynamiques.** `scene.switch(une_variable)` ne se résout pas à l'analyse. Une
  arête vers une cible inconnue, un nœud « indéterminé », ou rien du tout ? Ne rien montrer
  ferait mentir le graphe par omission, ce qui est pire qu'une arête floue.
- **La position des nœuds.** Disposition automatique, ou déplaçable et mémorisée ? La seconde
  demande de ranger des coordonnées de présentation quelque part — soit dans la scène (qui
  n'a rien à savoir de sa position dans une vue), soit dans un fichier d'éditeur à part. À
  trancher, parce que c'est une décision de modèle et non d'affichage.
- **Les autres relations.** Prefabs, mises en page, caméras et fonds forment déjà un graphe de
  dépendances par les mêmes domaines. Les faire entrer dans la même vue est tentant et
  probablement illisible ; à rouvrir une fois le graphe des scènes utilisé pour de vrai.

---

## v0.13 — Édition mixte — les appels d'API en blocs

Un appel d'API d'un script apparaît comme un bloc éditable, et modifier le bloc réécrit
l'appel là où il est. Du code ET du no-code, sans que ce soient deux chemins : **le script
reste la source, le bloc en est une projection.**

Référence assumée : GB Studio, dont l'ergonomie est le bon modèle. Son **architecture** ne
l'est pas, et pour une raison précise — GB Studio n'a pas de texte du tout, ce qui rend son
approche cohérente chez lui et inapplicable ici. Copier son modèle imposerait soit d'abandonner
le Lua, soit d'accepter deux chemins d'authoring pour la même logique.

La v0.12 (graphe des scènes) est la première instance de ce principe, appliquée à
`scene.switch` seul. Cette version le généralise à tout le catalogue. Les deux reposent sur ce
qui existe déjà : `iter_call_sites` pour trouver les appels, `RUNTIME_API` pour les décrire,
la réécriture par offsets de `refactor.py` pour les modifier.

### Décisions verrouillées

- **Les appels seulement, jamais le flux de contrôle.** `if`, `while`, `for` restent du texte.
  La raison est l'aller-retour : un appel dont les arguments sont des littéraux se relit et se
  réécrit à l'identique, octet pour octet. Le flux de contrôle, lui, pose immédiatement la
  question des commentaires, des lignes vides et de la mise en forme — et la première chose
  qu'un éditeur structuré perd, c'est ce que l'auteur avait écrit autour de son code.
- **La vue ne possède rien.** Chaque édition visuelle est une édition de texte à des offsets
  connus (le mécanisme de `rename_in_text`). Aucun modèle parallèle, aucune sérialisation de
  blocs, donc rien à tenir d'accord et rien à migrer.
- **Les blocs DÉRIVENT de `RUNTIME_API`**, jamais écrits à la main. Même règle et même raison
  mesurée que pour les snippets de la sidebar (cf. ARCHITECTURE, « Ce que l'éditeur INSÈRE
  dérive du catalogue ») : écrits en dur, ils ont proposé pendant des mois `scene_goto("X")`
  et `instantiate("X", x, y)`, deux noms qui n'ont jamais existé. Une fonction ajoutée à
  `api.py` obtient son bloc gratuitement ; une fonction retirée perd le sien.
- **Un argument s'édite selon son DOMAINE**, pas selon son rang. Un paramètre `DOMAIN_SCENE`
  ouvre un sélecteur de scènes, `DOMAIN_SFX` un sélecteur d'effets, un entier un champ
  numérique — tout vient de `Param.ptype` et `Param.domain`. Aucune interface par fonction à
  écrire, et un réordonnancement de paramètres n'invalide rien.
- **Ce qui n'est pas représentable s'affiche EN TEXTE, jamais masqué.** Un argument qui est une
  expression (`self:move(dx * 2, 0)`), un appel hors catalogue, un helper de l'auteur :
  fragment de code opaque dans la surface, éditable dans le Script Editor. **La surface ne
  ment jamais par omission** — c'est la règle qui rend l'hybride honnête, et c'est exactement
  celle dont GB Studio n'a pas besoin.

### Ouvert

- Où vit la surface : un panneau à côté du texte, une bascule qui le remplace, ou dans
  l'inspecteur du composant Script qui porte le fichier ?
- **Insérer un appel depuis la surface.** Contrairement à l'arête du graphe, une position par
  défaut est ici défendable (fin de la fonction courante). À rouvrir sur un cas réel — c'est
  la frontière entre « lire et ajuster » et « écrire », et elle mérite d'être franchie
  sciemment.
- Un argument qui référence une variable plutôt qu'un littéral. `FieldValue` traite déjà
  exactement cette question pour les champs de composant (px / tuile / variable) ; c'est la
  même, et sa réponse devrait être la même.

---

## v0.16 — L'API : la règle de construction, et le rangement

Le constat, posé le 2026-08-19 : **l'API est inégale, et il lui manque une règle de
construction.** Relevé sur le catalogue réel — `api_reference.get_categories()` réconcilié
rend **22 sections, 124 entrées, aucune périmée, aucune permutée**. La mécanique est saine :
`api.py` reste la source de vérité, le JSON ne décide que de la mise en rayon, et le loader
filtre puis complète tout seul. C'est le **rangement** qui ne va pas, pas la machinerie.

### Deux couches

L'API se conçoit à deux niveaux, et toute porte ouverte doit dire auquel elle appartient.

- **La couche d'itération** est celle de la majorité des scripts : simple à découvrir, rapide
  à utiliser, proche du Lua ordinaire, suffisante pour le gameplay courant, sans exposer
  l'intérieur du moteur. Faire une chose courante tient en quelques lignes.
- **La couche moteur** expose les outils spécialisés, et leur **nom** dit qu'ils en sont :
  `Interface`, `TextTable`, `DataTable`, `SoundBox`, `MusicBox`, `JingleBox`.

L'itération répond au **besoin immédiat**, le moteur au **besoin spécialisé**. On ne déplace
pas le simple vers le spécialisé par anticipation — afficher un texte ponctuel ne doit pas
exiger `TextTable` ; à l'inverse, un RPG de centaines de dialogues ira volontairement le
chercher. **Et l'itération ne cherche pas à égaler le moteur** : les deux ont volontairement
des objectifs différents. Le moteur peut être complexe ; l'API de base ne doit pas l'être.

### La règle de construction : on ne construit rien

**Une règle existe déjà, et elle n'est pas celle-ci.** `ARCHITECTURE.md` tranche la **forme**
d'un appel : état intrinsèque → propriété, requête sans argument → propriété en lecture seule,
requête indexée → fonction, action → méthode ou fonction de module. Elle répond à « *comment
ça s'écrit* ». Elle ne dit rien de « *d'où vient la chose sur laquelle j'écris* » — et c'est ce
deuxième axe qui manque. Les deux se composent ; aucune ne remplace l'autre.

Signe que le manque était déjà visible : `ARCHITECTURE.md` range `get_actor(name)` parmi les
« cas hors des trois formes », sans pouvoir dire pourquoi il détonne. La réponse est ici — il
ne suit aucune des trois provenances.

Trois provenances, et trois seulement :

| Provenance | Ce que c'est | Coût runtime |
| --- | --- | --- |
| `module.get("Nom")` | une chose **nommée du projet**, qui existe avant que le jeu démarre | un `#define` |
| `module.spawn(…)` / `sfx.play(…)` | un **slot pris dans un pool dimensionné au build** ; rend une référence, ou rien si le pool est plein | une boucle sur une plage contiguë |
| `module.verbe(n, …)` | le **matériel, numéroté par le matériel** : 4 calques, 2 fenêtres, 16 banques | un registre |

Plus une quatrième, qui n'obtient rien et ne vise rien de numéroté : `text.draw(tx, ty, id)`
dessine à des **coordonnées libres**. Elle est légitime — elle doit être nommée comme telle au
lieu d'être subie.

**Aucun constructeur ne rend une référence.** Le seul `new` envisagé —
`new_sound_effect()` — a été retiré le jour même : les huit canaux de maxmod sont un pool, et
`sfx.play` rend son slot comme `actor.spawn` rend le sien (v0.8.6). `vec2` / `vec3` / `rect`
sont bien des constructeurs, comme `ARCHITECTURE.md` les nomme — mais ils construisent une
**valeur**, comme `12` : rien qui vive dans le moteur, rien dont on tienne une référence. La
règle se dit donc précisément : *aucune référence ne s'obtient autrement que par les trois
provenances ci-dessus.*

Ce qui est inégal, c'est exactement ce qui ne suit aucune des trois : `get_actor("x")`, seule
fonction du catalogue à porter son verbe devant — et le seul « cas hors formes » de
`ARCHITECTURE.md` que ce chantier fait rentrer dans le rang.

### Ce que le rangement actuel enseigne de faux

Cinq intentions ordinaires, passées sur les 22 sections. **Quatre échouent.**

| « Je veux… » | Ce que l'auteur trouve |
| --- | --- |
| cacher quelque chose | cinq réponses dans cinq sections — `self.visible` (Animation), `self:hide()` (Interface), `self.active` (Actor), `layer.show` (Layer), `window.show` (Window). Choisir suppose de savoir ce qu'est sa chose **pour le moteur** — précisément ce que l'itération promet de ne pas exiger. Et `self.visible` rangé dans « Animation » ne s'invente pas. |
| faire sauter mon perso | **Movement** ne contient rien à ce sujet ; la réponse est dans **Physics** (`add_velocity`, `velocity`, `grounded`). Deux sections, un sujet, une frontière indevinable — et on s'arrête raisonnablement à la première. |
| afficher mon score | **Texte** montre huit fonctions, aucune ne dit que la valeur vient de `global.set` plus un marqueur `$`. La recette traverse deux sections et un écran de l'éditeur. |
| changer mon fond | cinq sections, trente entrées, toutes nommées d'après des **registres**. Et **Tile** (1 entrée) parle de collision, pas de décor : posé à côté de Tilemap, il se lit comme son petit frère. |
| débuter | **Actor** est la corbeille de repli du réconciliateur (`_ACTOR_FALLBACK`) : la section la plus consultée par un débutant est celle dont le contenu est le moins prévisible. |

Seule **Sauvegarde** passe proprement : quatre fonctions, un sujet, un nom.

Et la liste des intitulés **inverse la réalité deux fois** :

| Ce que la liste montre | Ce qui est vrai |
| --- | --- |
| Transform, Movement, Physics, Animation, Actor — **5 sections** | **un seul objet**, `self` |
| Layer, Tilemap, Palette, Window, Blend — **5 sections** | **une seule chose**, le décor |
| Tableaux (1), Tile (1), Scène (3) | des feuilles isolées, au même rang qu'Audio (11) |

Les sections sont nommées d'après le **grain de l'implémentation** — une famille de verbes, un
registre matériel — jamais d'après la **chose que l'auteur a en tête**. Qui lit la barre
latérale en déduit un moteur à 22 sous-systèmes de poids comparable. Il en a huit.

### Décisions verrouillées

- **Huit sections, une par chose qu'on tient.**

  | Section | Ce qu'elle absorbe | Entrées |
  | --- | --- | --- |
  | **L'acteur** | Transform + Movement + Physics + Animation + Actor | 17 fn + 18 propriétés |
  | **Le décor** | Layer + Tilemap + Window + Blend + Palette | 29 fn + 1 |
  | **Le son** | Audio + les trois boîtes | 22 |
  | **Le texte et l'interface** | Texte + Interface | 14 |
  | **Les données** | Variables + Sauvegarde + `data` + `array` | 8 + l'indexation |
  | **Le script** | Maths + Séquences + `vec2`/`rect` + `wait` + les handlers | 21 + les handlers |
  | **La scène** | Scène + Caméra + `tile.get` | 5 fn + 4 |
  | **Le joueur** | Input | 2 fn + 1 |

- **Les 22 noms actuels deviennent des sous-titres**, ils ne disparaissent pas. `blend` reste
  `blend` pour qui le connaît déjà ; il cesse d'être une **porte d'entrée** pour qui ne le
  connaît pas.

- **La couche est une MARQUE sur l'entrée, pas la navigation.** Couper le panneau en deux au
  premier niveau (« Itération » / « Moteur ») obligerait qui cherche à faire défiler son fond
  à savoir d'abord que le défilement est « moteur » — encore de la connaissance du moteur pour
  trouver la porte. Donc : **une seule navigation, par nom** ; dans chaque section,
  l'itération d'abord, le moteur replié sous un « Aller plus loin ». C'est la réponse à la
  question « où la frontière se voit-elle », sans laquelle la frontière ne survivrait pas
  trois versions.

- **Quatre renommages, complets.** `get_actor` → `actor.get` (le verbe passe derrière, comme
  `ui.get`, `global.get`, `const.get`) ; `ui` → `interface` (une abréviation, que la grammaire
  de la maison refuse) ; les quatre `text.*_in` → `interface.draw_text` / `clear_text` /
  `reading` / `skip` (elles visent une **zone nommée d'une mise en page**, pas des coordonnées
  libres — c'est ce mélange qui rendait « Texte » illisible) ; les trois boîtes sonores
  (v0.8.6).

- **`TextTable` n'a pas de module.** Sa surface Lua **est** `text.draw` plus les marqueurs
  `$variable` de l'entrée ; clés, balisage et traductions sont résolus au build. Pas de module
  vide inventé par symétrie avec les autres assets nommés.

- **`text.draw` accepte DÉJÀ un littéral écrit sur place** (`api.py`, entrée anonyme
  `_lit_<hash>` dérivée du contenu). « Un texte ponctuel ne doit pas exiger `TextTable` » est
  donc tenu depuis le début, et n'était écrit nulle part. **À documenter, pas à construire.**

- **C'est du rangement, pas une réécriture.** `api_reference.json` décide déjà de la mise en
  rayon, et le loader complète depuis `api.py` : il faut réécrire ses catégories et
  `_PROP_HOME`. Le catalogue, lui, ne bouge que par les quatre renommages.

Bilan : **112 fonctions de catalogue** (100 + 12 par v0.8.6), **24 propriétés** rangées avec
leur objet, **6 mots du langage** enfin listés (`vec2`, `vec3`, `rect`, `wait`, `wait_until`,
`require`), **8 sections** au lieu de 22.

### Ouvert

- **`#data.Objets`** — le nombre de lignes d'une table de données. Évident, absent. À ouvrir,
  ou à refuser par écrit dans `SCRIPTING.md`.
- **`SCRIPTING.md` adopte-t-il les mêmes huit sections ?** Deux plans différents pour la même
  API rouvriraient exactement le problème qu'on ferme ici.
- **v0.13 hérite de ce rangement** : les palettes de blocs de l'édition mixte seront ces huit
  sections. À vérifier quand le chantier démarre, pas maintenant.
- **`ARCHITECTURE.md` porte déjà les anciens noms** (`get_actor`, `ui.get`, `text.draw_in`
  — huit endroits au moins). Ils y sont **justes tant que le renommage n'est pas fait** : ce
  fichier décrit le code tel qu'il est. Il devient donc la liste de contrôle du renommage,
  pas une dette à corriger d'avance.

---

## v0.17 — Le pool par scène

### Ce qui a été écarté, et pourquoi

Un **spawn dynamique depuis la librairie de prefabs** a été envisagé le 2026-08-19, puis
écarté. Ce n'est pas « compliqué » : c'est incompatible avec **trois allocateurs qui sont tous
au build**.

1. Les tuiles du sprite sont en VRAM **par scène** (`tile_offset` calculé à l'émission).
2. La palette est allouée **par scène** (`palette_alloc`, plafond de 16 banques).
3. L'état de script d'une instance est un tableau dimensionné sur `POOL_<X>_SIZE` (v0.7.6).

Un prefab tiré de la librairie en cours de partie demanderait les trois à l'exécution. Ce ne
serait pas un chantier, ce serait un autre moteur.

### Ce qui existe déjà, et ce qui manque vraiment

Le pool old-school **est écrit** : `spawn_<Prefab>` balaie sa plage à la recherche d'un slot
inactif, `pool_init` remet l'état à zéro, `-1` si plein. Ce qui manque n'est pas le pool,
c'est **où il se déclare**.

> `max_instances` est un champ du **Prefab** (`core/models/scene.py`), pas de la Scene. Et
> `headers.py` fait `sum(pf.max_instances for pf in prefabs)` : **chaque scène du projet porte
> les slots de tous les prefabs spawnables du projet**, y compris ceux qu'elle n'utilise
> jamais. Une scène de menu paie les seize balles du niveau d'action — en EWRAM, en entrées de
> `g_actors[]`, et en état de script.

### Décisions verrouillées

- **Le pool se déclare sur la SCÈNE**, avec les prefabs qu'elle emploie réellement.
  `max_instances` quitte `Prefab`. Un prefab reste un **template de projet** ; combien
  d'exemplaires en vivent en même temps est une propriété du **niveau**, pas du template.
- **Pas de spawn dynamique depuis la librairie.** Écarté pour les trois raisons ci-dessus. À
  ne pas rouvrir tant qu'aucune des trois n'a changé.
- **`active = false` LIBÈRE le slot.** C'est déjà le comportement — la boucle de spawn cherche
  `if(!g_actors[_i].active)` (`main_gen.py`) — mais rien ne le disait : désactiver un acteur
  ne le met pas en pause, ça le rend réutilisable, et le prochain spawn écrasera tout par
  `(Actor){0}`. `self:destroy()` devient le **nom lisible du même geste**. Trois états
  (actif / réservé inactif / libre) ont été envisagés et écartés : un drapeau de plus par
  acteur, une règle de plus à expliquer, et un pool qui peut se remplir de slots réservés que
  rien ne rend.
- **`actor.spawn` rend sa référence, ou rien si le pool est plein.** Le C rend déjà `_i` ou
  `-1` (`main_gen.py`) ; le Lua le jetait. Même forme que `sfx.play` (v0.8.6), parce que c'est
  la même chose : prendre un slot dans un pool dimensionné au build.
- **La mesure, pas de garde-fou** — même règle qu'en v0.7.6 : le build dit ce que les pools de
  la scène coûtent, rien ne bloque.

### Ce que ça touche

`core/models/scene.py` (le champ change de classe), `headers.py` (les `POOL_*` deviennent
per-scène), `main_gen.py` (`_pool_info`, la boucle de spawn), `lua_compiler.py` (le
dimensionnement de `g_state_*`), `palette_alloc.py`, `rom_build.py`, `validator.py`, et
l'écran Scene, qui doit désormais montrer les pools de la scène.

### Ouvert

- **Le vrai coût du chantier, et il n'est pas tranché.** `POOL_<X>_START` / `POOL_<X>_SIZE`
  sont des constantes de build lues par le **script transpilé**, qui est compilé **une seule
  fois pour le projet** — c'est écrit tel quel dans `headers.py`. Si la taille devient
  per-scène, un même script voit deux tailles selon la scène. Deux sorties : dimensionner
  `g_state_<X>[]` sur le **maximum du projet** (on récupère les entrées de `g_actors[]`, mais
  pas l'état de script), ou **compiler les scripts par scène** (on récupère tout, au prix du
  temps de build et d'une hypothèse tenue partout ailleurs qui tombe). À trancher avant
  d'écrire une ligne. **La v0.23 attend cette réponse** : un prefab qui porte un sous-arbre
  dimensionne son pool en instances × parties, et l'état de script de chaque partie se range
  là où celui-ci se range.
- **Où le pool d'une scène se déclare dans l'éditeur** : dans la liste des acteurs de la
  scène, ou dans un panneau à part ?

---

## v0.18 — La valeur affichée : d'où elle vient

### L'état des lieux, relevé avant d'ouvrir le chantier (2026-08-19)

Le grief de départ était « il faut traverser trois écrans pour afficher un score ». **Il est
faux, et il faut le dire avant de concevoir quoi que ce soit** : le littéral est déjà accepté
par `text.draw` (« une clé de la table, *ou un littéral écrit sur place* »), il fabrique son
entrée anonyme tout seul (`api.anon_text_key`), et les globals se déclarent dans la **sidebar
du Script Editor**. Afficher un score, aujourd'hui, c'est un écran et deux gestes — ce que
fait déjà le Pong :

```lua
-- sidebar : déclarer `score_player`. Puis, sans quitter l'écran :
text.draw(9, 2, "$score_player")
```

Le défaut est ailleurs, et il est **structurel : la valeur affichée ne peut être qu'un global
déclaré.** `text_materialize` lit `global_read(g_text_values[src])`
([gba_engine.h:1758](runtime/include/gba_engine.h:1758)), et `font_emit` ne sait écrire dans
`g_text_values` qu'un `GLOBAL_<NOM>` ([font_emit.py:842](editor/codegen/font_emit.py:842)).
Il n'existe pas d'autre source au runtime.

Ce que ça interdit : afficher un `local`, une expression, une propriété (`self.position.x`),
une cellule de table de données. Il faut **promouvoir** la valeur en global — payer un nom
dans un espace de noms de projet, de la RAM, et une décision de persistance, pour un nombre
qui vit trois frames. L'auteur déforme son modèle pour satisfaire l'afficheur.

Un fait qui décide de la forme de la solution : **une constante, elle, est déjà cuite dans les
codepoints au build** (`_bake_values`). La substitution n'est donc pas « globale par nature » :
elle est globale *au runtime*, faute d'une autre source à cet instant-là. Il en manque une
troisième, et c'est le **site d'appel**.

### Décisions verrouillées

- **Des marqueurs positionnels `$1` à `$4`, à côté du `$nom` existant.** L'entrée porte la
  phrase, l'appel porte les valeurs :

  ```lua
  text.draw(9, 2, "score", points)              -- l'entrée dit « Score : $1 »
  text.draw_in("boite", "degats", hp, hp_max)   -- « $1 / $2 PV »
  text.draw(2, 2, "PV : $1", hp)                -- littéral : rien à déclarer
  text.draw(2, 2, "$1", self.position.x)        -- debug, une ligne, zéro écran
  ```

- **`$nom` ne bouge pas.** Deux sources pour deux durées de vie : un global est un état
  *partagé et persistant* que plusieurs textes citent, un positionnel est une valeur que
  l'appelant a déjà en main. Confondre les deux rendrait le HUD propriétaire d'un espace de
  noms de projet.
- **Ceci ne rouvre pas le retrait de `display.print`.** Le motif de ce retrait était « leur
  chaîne de format vivait dans le script, donc hors de la table de textes : intraduisible »
  ([api.py:643](editor/scripting/api.py:643)). Ici la **phrase reste dans l'entrée** ; seule la
  *valeur* vient de l'appel. `$1` n'est pas du texte, c'est un trou — il occupe une place de
  sentinelle exactement comme `$score` aujourd'hui, donc le centrage, la coupe, la machine à
  écrire et la traduction continuent de fonctionner.
- **Les positionnels sont admis dans une entrée de la table, pas seulement dans un littéral.**
  C'est même leur premier intérêt en v0.9 : une langue qui ordonne « 3/5 PV » autrement
  réordonne ses `$n` dans sa propre entrée, sans que le script sache qu'elle existe.
- **Les valeurs voyagent par un tampon de passage, pas par des varargs.**

  ```c
  g_text_arg[0] = score; g_text_arg[1] = hp; g_text_arg_n = 2;
  text_draw(9, 2, TEXT_HUD);
  ```

  Le codegen émet déjà des instructions : poser deux affectations avant l'appel ne lui coûte
  rien, et **la signature de `text_draw` ne bouge pas**. C'est ce qui donne le mécanisme
  gratuitement à `text_draw_in`, `text_reading` et `text_length` — toutes passent par
  `text_materialize`. Ce dernier point décide : `text_length` doit voir la valeur substituée
  (c'est la borne de la machine à écrire) et ne prend, elle, aucun argument. Des varargs
  n'auraient rien pu pour elle.
- **Plafond de quatre valeurs par entrée, refusé au Build au-delà.** Une ligne de HUD n'en
  demande pas plus, et le tampon est dimensionné au build comme tout le reste : un plafond
  variable serait une allocation.
- **L'arité est vérifiée au Build.** Une entrée qui cite `$2` appelée avec une seule valeur est
  une erreur sur sa ligne, pas un zéro affiché. `BuildContext.text_keys` doit donc porter le
  nombre de `$n` par entrée, là où il n'est aujourd'hui qu'une liste de clés.
- **La mécanique variadique existe déjà et suffit.** `ApiFunc.variadic` est câblé de bout en
  bout — contrôle d'arité ([checker.py:1014](editor/scripting/checker.py:1014)) et
  pass-through des args au-delà des paramètres déclarés
  ([codegen.py:1283](editor/scripting/codegen.py:1283)) — et sert déjà à `array(20, 12)`.
  Rien à inventer côté langage : `text.draw` et `text.draw_in` prennent le drapeau.
- **La conversion en chiffres est déjà écrite.** `text_num_cp`
  ([gba_engine.h:2691](runtime/include/gba_engine.h:2691)) reste le point unique ; seule la
  **source** de `src` change dans `text_materialize`.

### Ce qui a été écarté, et pourquoi

- **`text.number(tx, ty, valeur)`** — le moins cher à écrire (le rendu des chiffres existe), et
  le plus mauvais. Il ramène exactement le défaut qui avait fait retirer `text_draw_num` : pour
  poser « Score : » puis le nombre, l'auteur doit savoir **où finit le libellé en pixels**.
  Faux dès qu'une police est proportionnelle, faux dès qu'on traduit, faux dès que la valeur
  change de nombre de chiffres. Et c'est le geste du débutant, donc l'endroit où se tromper
  coûte le plus cher.
- **Les varargs C** — `__va_start` embarqué, la signature d'une fonction chaude modifiée pour
  tous ses appelants, et `text_length` toujours sans réponse.

### Ce que ça touche

[text_markup.py](editor/core/text_markup.py) (la regex de marqueur
[ligne 185](editor/core/text_markup.py:185), l'arité rendue par l'analyse, `resolve` pour
l'aperçu), [font_emit.py](editor/codegen/font_emit.py) (`emit_texts_c` : un marqueur
positionnel écrit son rang au lieu d'un index dans `g_text_values`),
[gba_engine.h](runtime/include/gba_engine.h) (`text_materialize` : deux sources au lieu d'une,
plus `g_text_arg`), [api.py](editor/scripting/api.py) (le drapeau `variadic` sur les deux
`text.draw*`), [checker.py](editor/scripting/checker.py) (l'arité, et le contexte de build qui
la porte), [codegen.py](editor/scripting/codegen.py) (les affectations posées avant l'appel),
et l'écran Texte, qui doit montrer un aperçu de ce qu'il ne connaît pas.

### Ouvert

- **Ce que l'aperçu de l'écran Texte affiche pour un `$n`.** `resolve()` substitue aujourd'hui
  la vraie valeur d'un global ; un positionnel n'en a aucune au moment de l'authoring. Trois
  sorties : laisser `$1` visible tel quel (comme un `$nom` inconnu, cf. `_bake_values`),
  afficher un `0`, ou donner à l'entrée une **colonne de valeurs d'exemple** — qui a le mérite
  de montrer la mise en page réelle d'un « 999/999 » avant qu'elle ne déborde en jeu.
- **`text.length` et `text.reading` sur une entrée à positionnels.** Leur résultat dépend des
  dernières valeurs posées dans le tampon, donc du dernier `text.draw` — y compris quand ce
  n'était pas la même entrée. À trancher : rendre le tampon **propre à la zone** (une copie par
  tête de lecture, comme `g_reads`), ou assumer un tampon global et dire dans quel ordre les
  deux appels s'écrivent. La première est la seule qui reste vraie avec deux boîtes de dialogue
  à l'écran.
- **Un `$n` au-delà de ce que l'appel a fourni**, si le contrôle d'arité est un jour contourné
  (entrée modifiée après coup, traduction ajoutant un `$3`) : un trou de cellule comme un
  glyphe absent, ou zéro ? La règle maison dit trou — « mieux qu'un nombre silencieusement
  faux » (cf. le commentaire de `text_num_cp`).

---

## v1.0 — Le pipeline 2D complet

### L'objectif concret — cinq genres

La v1.0 était écrite comme un jalon de *validation* (« un deuxième jeu de démo, plus
stabilisation »). Elle porte en réalité une **affirmation de capacité** : à la v1.0, le
logiciel absorbe un projet 2D de production, de bout en bout.

Une affirmation pareille n'est décidable que si on dit *quoi*. Voici le critère, sur le modèle
de « V-Rally 3 » pour la v3.1 — une cible se compare, une capacité s'étend indéfiniment :

| Genre | Ce qu'il exerce en propre |
| --- | --- |
| **Platformer** | gravité scriptée, pentes, collision de tuiles, caméra en suivi |
| **Metroidvania** | état persistant entre scènes, retour arrière, déverrouillages |
| **RPG** | tables de données (objets, sorts), menus, dialogues, sauvegarde longue |
| **Tactique** (Advance Wars, FFT en vue de dessus) | grille, liste d'unités, recherche de chemin, curseur |
| **Gestion** (Zoo Tycoon) | N entités à état propre, économie, budget OAM sous tension |

Les trois derniers attendaient la v0.7, qui est livrée. Quant aux deux premiers, ils étaient
écrits ici comme **atteignables aujourd'hui** : la revue du 2026-08-19 (juste au-dessus) dit
que c'est faux, et où. Un platformer sans sous-pixel (v0.19) n'a ni accélération ni saut à
hauteur variable ; un metroidvania sans collection persistante (v0.20) écrit une variable par
coffre. Les deux genres réputés acquis sont donc, en réalité, les deux qui ouvrent la liste.

### Le deuxième jeu de démo se choisit dans cette liste

Et **pas parmi les deux premiers**. Un platformer ne validerait presque rien de neuf : il
n'exerce ni les tables, ni les menus, ni la sauvegarde longue. Un proto-tactique ou un
proto-gestion, à l'inverse, échoue immédiatement si la v0.7 a manqué sa cible — ce qui est
exactement ce qu'on attend d'un jeu de validation.

Le reste de la version est ce qu'il était : stabilisation du runtime et de l'éditeur,
documentation utilisateur.

### Ce qu'une « première version stable » exige, et qui n'est pas une fonctionnalité

Quatre points sans lesquels le mot « 1.0 » ne tient pas. Aucun n'ajoute de capacité au moteur ;
tous conditionnent le fait que quelqu'un puisse réellement bâtir dessus. **Le premier est
réglé** ; il reste trois.

- ~~**Une licence.**~~ **FAIT.** Le point était plus aigu ici qu'ailleurs : l'éditeur **copie
  son propre C dans la ROM de l'utilisateur** (`gba_engine.h` et les sources générées), donc
  sous une licence unique tout jeu construit avec l'outil serait devenu un travail dérivé sous
  GPL. D'où **deux licences, et c'est la découpe qui compte** : `LICENSE` (GPL-3.0-only) couvre
  l'ÉDITEUR, `runtime/LICENSE` (zlib) couvre le moteur recopié dans la ROM — le jeu et sa ROM
  appartiennent entièrement à leur auteur, sans rien à publier ni à demander.
  `THIRD-PARTY-NOTICES.md` recense les composants redistribués, obligation déjà active
  puisqu'ils sont dans l'installateur. Reste hors de ce point, et à trancher ailleurs : le nom
  et la marque, où « GBA » porte un risque Nintendo.
- **Des formats que git sait relire** — devenu la **v0.24**, où il est traité avec le build et le chargement, parce que la revue du 2026-08-19 a montré qu'il ne se comporte pas comme une finition de v1.0 mais comme un préalable. Aujourd'hui un fond fait 688 lignes et la carte de
  collision d'une scène environ 600, à raison d'**un entier par ligne** ; les couleurs sont
  des entiers BGR555 décimaux. Ce n'est pas qu'un défaut de lisibilité : chaque modification
  de scène produit un diff illisible, l'historique devient inexploitable, et deux personnes ne
  peuvent pas toucher la même scène sans un conflit qu'aucun humain ne résout à la main. **Ça
  plafonne le logiciel au travail solitaire**, ce qui est incompatible avec « projet de
  production ».

  La correction est connue et petite : une ligne de texte par rangée de grille — c'est
  exactement ce que `tileset` fait déjà, une chaîne hexadécimale par tuile, et c'est de loin
  la partie la plus lisible du sidecar. Et les couleurs en hexadécimal (`#39A8FF`), les deux
  formes acceptées en lecture.
- **Des modèles de départ.** Un seul projet de démo existe (Pong). Un modèle « platformer »
  enseigne l'API sans qu'on lise une ligne de documentation, et c'est ce qui décide qu'on
  reste après la première heure. Même famille que le deuxième jeu de démo : du contenu qui
  enseigne, pas une fonctionnalité.
- **La vérification que ça tient à l'échelle** (le chargement paresseux lui-même est en v0.24 ; ce qui reste ici, c'est la vérification sur un vrai projet). `Project.load()` charge tout, tout de suite —
  chaque sidecar de chaque collection. Pong et ses 118 fichiers vont très bien ; quarante
  scènes et deux cents sprites, personne n'en sait rien. L'affirmation « absorbe un projet de
  production » se vérifie ou s'écroule exactement là, et c'est le deuxième jeu de démo qui
  tranchera.

### Ouvert

- Lequel des trois genres bloqués sert de démo. À trancher quand la v0.7 est livrée, sur ce
  qu'elle rend réellement confortable.
- ~~Les menus et listes (curseur, défilement, sélection)~~ **Tranché le 2026-08-19 : le moteur
  en prend une part, et c'est la v0.22.** La question posée ici — « si les trois genres à menus
  le rendent pénible, c'est ici que ça se verra » — a reçu sa réponse d'un projet cible à arbre
  de compétences, inventaire et équipement : ce n'est pas un confort qu'on juge après coup,
  c'est un tiers du contenu, entièrement à la charge de l'auteur.

---

## Au-delà de la v1.0

### Chantier transverse — l'allocateur de ressources matérielles

Ne porte pas de numéro de version : il **se déclenche par un événement**, pas par une date —
le jour où une ressource matérielle a son deuxième consommateur. Le premier candidat est le
viewport de caméra / l'écran partagé de la v2.0, qui rouvre déjà « une région appartient-elle
à une caméra, ou l'inverse ? ». Le second est le clipping d'UI.

#### Le problème

Les ressources du matériel ne correspondent pas aux concepts du game design. Une window GBA
n'est pas une fonctionnalité : c'est une ressource. Or une caméra veut une région de rendu,
l'UI un rectangle de découpe, un acteur un masque de visibilité, un effet un pochoir — quatre
intentions distinctes qui réclament le même stock de trois slots.

Écrire `camera.window = WIN0`, `ui.window = WIN1` fabrique le bug le plus classique de
l'ingénierie logicielle : chaque fonctionnalité marche parfaitement, jusqu'au jour où deux
d'entre elles servent en même temps. Et les windows ne sont que le premier exemple — sprites,
palettes, VRAM, OAM, DMA, canaux sonores, matrices affines posent le même problème.

Le principe et ses trois niveaux (intention / ressource logique / ressource matérielle) sont
décrits dans [ARCHITECTURE](ARCHITECTURE.md), « Ressources matérielles — l'auteur ne les nomme
jamais ». Ce jalon est son implémentation.

#### Décisions verrouillées

- **Deux allocateurs, pas un.** Ce qui se résout au BUILD (palettes, VRAM, tuiles) et ce qui
  se résout à la FRAME (OAM, DMA, windows disputées) ne partagent qu'un vocabulaire. Le
  premier peut être coûteux et **doit** parler à l'auteur ; le second tourne 60 fois par
  seconde et n'a personne à qui parler. `palette_alloc.py` et `vram_alloc.py` sont déjà des
  instances correctes du premier — ce chantier ne les refait pas, il leur donne une famille.
- **Le rang fait partie de la ressource.** `WINR_0` > `WINR_1` > `WINR_OBJ` > `WINR_OUT` est
  une priorité câblée : traiter deux slots comme équivalents produit une allocation valide et
  une image fausse. C'est le mode de panne à empêcher par construction, parce que rien ne le
  signalera au runtime.
- **Déterminisme avant optimalité.** Pas d'ordonnancement par priorités déclarées
  (`critical`/`high`/`medium`) : une allocation qui change parce que l'auteur a posé un sprite
  sans rapport casse son UI sans qu'il puisse faire le lien. Un ordre de résolution stable,
  documenté et ennuyeux vaut mieux qu'un ordre optimal — il est prévisible, et il est
  testable.
- **Les solutions de repli proposées doivent exister matériellement.** Fusionner deux masques
  identiques, reprogrammer par scanline en HBlank (donne réellement plus de régions, au prix
  de cycles), renoncer au masquage, assigner à la main. Pas de « clipping logiciel » pour un
  calque tuilé en mode 0 : il faudrait réécrire la tilemap. Une liste courte et vraie, sinon
  l'éditeur promet ce que la machine ne fait pas.
- **L'assignation matérielle reste visible, dans un panneau avancé.** Le principe « l'auteur
  peut descendre jusqu'au matériel » n'est pas suspendu : il ne nomme plus la ressource pour
  obtenir un masque, mais il peut voir laquelle lui a été donnée, et la forcer.

#### Ce qu'il faut faire AVANT, et qui ne coûte presque rien

L'allocateur complet attend son deuxième client — une abstraction à un seul consommateur se
dessinerait contre des besoins imaginés. Deux gestes se font en revanche dès maintenant, et
rendent le reste possible sans rien casser :

1. **Le principe est écrit** (fait — cf. ARCHITECTURE), pour que rien de neuf ne lie un
   concept de haut niveau à un slot matériel d'ici là.
2. **Cesser de faire de `WindowSlot.region` un index matériel côté auteur.** C'est une
   indirection et un renommage, pas un ordonnanceur.

#### Ouvert

- L'API Lua `window.set_layer(r, …)` expose les régions par numéro matériel, et des scripts
  les adressent déjà ainsi. C'est la partie la plus dure à déplacer, et la maison ne migre
  pas les formats — à traiter comme une rupture assumée, au bon moment.
- Jusqu'où va l'allocateur de frame. Un arbitrage OAM par frame est un vrai coût CPU ; il se
  décide sur un cas mesuré, pas à l'avance.

### v2.0 — Backgrounds affines (« Mode 7 »)

Un calque affine ajoute rotation et zoom, au prix de perdre des calques réguliers ailleurs —
et il adresse sa carte différemment, donc c'est un **second chemin de génération de code**,
pas « un calque de plus ».

Volontairement décrit à haut niveau : la portée exacte dépendra de ce qui aura été appris en
construisant les fondations précédentes.

#### Ce que la v2.0 n'est PAS — l'objectif V-Rally 3 n'est pas ici

Cet objectif a été rangé dans cette version pendant une journée, sur une lecture de captures
d'écran qui concluait au Mode 7 : sol texturé fuyant vers l'horizon, décor en sprites mis à
l'échelle, HUD en calque normal. **Cette lecture était fausse**, et la mesure l'a montrée
(2026-08-13, visualiseur de cartes mGBA sur la ROM) :

| Relevé | Lecture |
| --- | --- |
| Fond de tuile : *s.o.* | aucune base de tuiles — le fond n'est pas tuilé |
| Taille : 240×160 | un écran, pas une carte |
| Fond de carte : `0x0600A000` | VRAM + 0xA000 = **frame 1 du mode 4** |

Le mode 3 n'a pas de second tampon et le mode 5 afficherait 160×128 : c'est donc le **mode 4**,
240×160 en 8bpp double-tamponné. Un framebuffer rempli par le processeur. Confirmé par des
maillages qui tournent dans les menus.

La leçon vaut d'être gardée : **un rasteriseur logiciel et un sol affine produisent la même
image.** Une capture ne distingue pas les deux — seul le mode vidéo le fait. Aucune décision
de rendu ne se verrouille sur une image, ici ou ailleurs.

L'objectif part donc en **v3.1**, derrière le framebuffer dont il dépend. La v2.0 redevient
ce qu'elle était : une capacité, sans cible de jeu.

#### Piste posée — l'abstraction « caméra » sera remise en cause ici

La caméra est en train de devenir une entité, en absorbant les fenêtres de la v0.3.2 — auquel
cas ce n'est plus « où on regarde » mais **une configuration d'écran nommée qu'on active** :
cadrage, suivi, et régions qui découpent l'affichage. Comme les caméras sont mutuellement
exclusives, deux fenêtres par caméra n'impliquent jamais plus de deux rectangles à l'écran :
la contrainte matérielle tient.

Nom de travail : **Caméra2D** (convention Godot, immédiatement lisible). Réserve à garder en
tête, il promet une Caméra3D qui n'existera jamais sur GBA — le Mode 7 n'est pas de la 3D mais
une transformation affine en 2D. Le vrai axe est donc *régulière* contre *affine*, pas 2D
contre 3D.

Deux choses à traiter à ce moment-là, pas avant : **unifier les mécanismes de caméra
concurrents** (c'est quand la caméra devient un objet nommé porteur d'un état qu'il devient
absurde d'en avoir deux), et l'**écran partagé**, qui rouvrira la question « une région
appartient-elle à une caméra, ou l'inverse ? ». Tant que les caméras sont exclusives, la
question ne se pose pas.

### v2.1 — Physique et collision

Le moteur n'a aujourd'hui aucune physique à lui : un script décide du mouvement, la
résolution de la v0.6.3 ne fait que le corriger. Cette version est **le renversement de cette
règle** — pas son extension. C'est pour ça qu'elle est ici et pas en v0.6.4 : tant que les
fondations 2D ne sont pas finies, un moteur qui décide du mouvement à la place du script
coûterait plus qu'il ne rendrait.

#### Périmètre

- **Collision par normale.** Le contact rend une direction, pas seulement un booléen — c'est
  ce qui distingue « je touche » de « je glisse le long de », et c'est la condition de tout
  le reste.
- **Gravité**, et deux milieux qui la modulent : **air** (traînée) et **viscosité**
  (résistance d'un fluide). Trois réglages qui vivent quelque part entre la scène et
  l'acteur — l'endroit reste ouvert.
- **Nouvelles primitives** : cercle de collision et maillage de collision. Ce sont des
  primitives **2D** ; le mot « mesh » ne promet pas de volume. La distinction devient
  critique une fois la v3.1 au programme : deux choses différentes porteront le même mot si
  personne n'y veille.
- **Nouveaux types de collision**, en remplacement du booléen `solid` actuel :

  | Type | Sens |
  | --- | --- |
  | `rigidbody` | réactif — le moteur calcule sa réponse au contact |
  | `actor` | simplifié — se déplace, se bloque, ne réagit pas |
  | `solid` | immobile — ne bouge jamais, sert de décor de collision |

- **Import de carte de collision** — un nouvel asset, pour des collisions fidèles à l'image.

#### Décisions verrouillées

- **Jamais avant la v2.0.** Décidé explicitement (2026-08-12) : les fondations 2D passent
  d'abord. La section « Ouvert » de la v0.6.3 reste donc vraie jusque-là, elle n'est pas
  contredite — elle est datée.
- **Les trois types ne sont pas un confort, ils sont le budget.** Une réponse par normale sur
  N acteurs se paie en cycles, sans FPU et en virgule fixe. `actor` et `solid` existent pour
  que `rigidbody` reste payable : le coût élevé se réserve à ce qui en a besoin. Une
  taxonomie à deux niveaux (« physique ou trigger », l'actuelle) ne permet pas cet arbitrage.
- **La carte de collision s'IMPORTE, elle ne se peint pas.** Même règle que partout ailleurs :
  l'image source n'est jamais modifiée, un sidecar porte le résultat, et l'éditeur n'ajoute
  pas d'outil de dessin (cf. la même décision pour les fonds et les sprites). C'est un
  troisième client du pipeline d'import existant, pas un nouveau pipeline.
- **« Pixel perfect » veut dire par tuile, pas par pixel.** Tester chaque pixel d'une scène
  240×160 à chaque frame n'est pas tenable ; la forme réalisable est un masque de bits par
  tuile, consulté après un rejet grossier par boîte. Le nom du champ doit dire ça, sinon il
  promet une précision que le runtime ne tient pas.

#### Ouvert

- **`CollisionBoxComponent.solid` est un booléen aujourd'hui.** Les trois types le
  remplacent : c'est un changement de format de composant, à traiter comme tel (la maison ne
  migre pas les formats — cf. `core/project.py`).
- Où vivent gravité, air et viscosité : propriétés de scène, de zone, ou d'acteur ? Les trois
  se défendent et le choix dépend du premier jeu qui s'en sert.
- Le maillage de collision est-il authoré, dérivé de l'image importée, ou les deux ? Dérivé
  est cohérent avec le refus de l'outil de dessin ; authoré est ce que réclame une forme qui
  n'existe dans aucune image.
- Rien n'est dit du coût réel. Il se mesure sur un cas, pas avant — c'est la règle qui a
  servi pour les animés de décor (v0.4.1, « L'ordre de grandeur, mesuré »).

### v2.2 — Distorsion d'image

Déformer un fond pour l'eau, la chaleur, la vitesse. Rangé ici parce que c'est **la même
plomberie que le sol affine de la v2.0** : dans les deux cas on réécrit des registres de
rendu à chaque scanline, seuls les registres visés et la table de valeurs changent. Construire
l'un donne l'autre presque gratuitement — c'est la raison de leur voisinage, et l'ordre entre
les deux n'a pas d'importance.

#### Décisions verrouillées

- **Sur un fond tuilé, la distorsion est PAR LIGNE, jamais par pixel.** On réécrit les
  registres de décalage du calque à chaque scanline (HDMA) — c'est l'effet eau/chaleur
  classique, réel et bon marché sur ce matériel. Une flow map par pixel suppose un
  framebuffer : elle appartient donc à la v3.0, et n'a pas de sens avant.
- **Les sprites n'en font pas partie.** Un OBJ ne connaît que la transformation affine
  (rotation, échelle) ; il n'y a pas de distorsion libre à lui appliquer. Le proposer
  promettrait un rendu que le matériel ne produit pas — même règle que les modes de mélange
  *multiply* et *overlay*, absents pour cette raison.

#### Ouvert

- La forme d'authoring : une courbe par calque, une table d'amplitudes, ou un script qui
  écrit la table lui-même ? Le troisième cas existe de toute façon, la question est ce que
  le déclaratif couvre.

### v2.3 — Rendu isométrique

**Ce n'est pas un mode de rendu**, et c'est le piège du sujet : l'isométrique reste du 2D
tuilé ordinaire, sur le même matériel, avec les mêmes calques. Ce qui change est la
**convention de projection** et, surtout, l'**ordre de dessin**. Aucune ligne du moteur 2D
n'est remplacée ; il s'en ajoute.

#### Périmètre

- **Le tri en profondeur des sprites.** C'est le cœur, et c'est du runtime. En vue de dessus,
  l'ordre OAM suffit tel quel ; en isométrique, un acteur passe *devant* ou *derrière* un
  autre selon sa position dans le monde, et l'ordre doit être recalculé quand ils bougent.
  Le matériel dessine les OBJ dans l'ordre de la table : c'est donc la table qu'on trie.
- **La projection.** Une position monde (x, y) devient une position écran en losange. Une
  seule formule, mais elle doit vivre **au même endroit pour l'éditeur et pour le moteur** —
  sinon le canvas ment sur l'emplacement des choses (c'est déjà le rôle de
  `core/engine_emulation/`).
- **La collision en espace isométrique.** Une boîte alignée à l'écran n'est pas une boîte
  alignée dans le monde. À raccorder à la v2.1, qui aura introduit les normales et les
  nouvelles primitives — les deux versions se touchent ici.
- **L'authoring.** Poser un acteur au canvas doit se faire dans la grille du monde, pas dans
  les pixels du losange.

#### Ouvert

- Le coût du tri par frame, et son plafond. Trier N acteurs à chaque frame sur un ARM7TDMI a
  un prix ; le nombre d'entités simultanées s'en déduira, il ne se décrète pas.
- Vraie isométrique (2:1) ou projection libre ? La première se tuile proprement, la seconde
  ouvre des cas qui ne se rangent pas dans une grille.
- La hauteur. Un décor isométrique sans élévation est une grille inclinée ; avec élévation,
  le tri cesse d'être un tri sur Y. À décider avant, parce que ça change la donnée de carte.

### v2.4 — Sucre syntaxique Lua (+=, ++, ?:)

Demandé le 2026-08-14 : `x += 1` / `x -= 1` / `x *= 2` / `x /= 2`, `x++` / `x--`, et
`cond ? a : b`. **Aucun des trois n'est du Lua** — Lua n'a jamais eu d'affectation composée ni
d'opérateur ternaire, choix délibéré du langage — et `luaparser` (un vrai parseur ANTLR) les
refuse net :

```
x += 1          → no viable alternative at input 'x +'
x++             → no viable alternative at input 'x+'
a ? b : c       → token recognition error at: '?'
```

Donc ce n'est pas « étendre l'AST » : `parser.py` reçoit le texte source tel quel et le passe
à `luaparser.ast.parse()` sans passe intermédiaire (`scripting/parser.py::parse()`). Accepter
cette syntaxe demande une **réécriture du texte AVANT `luaparser`** — un dialecte Lua-like, pas
du Lua strict.

**Le ternaire a déjà un équivalent qui ne coûte rien** : `cond and a or b` est du Lua valide
aujourd'hui et couvre tout ce que ce sous-ensemble manipule (entiers, vec2/vec3, chaînes) —
sauf le cas où `a` vaut `false`, où Lua bascule sur `b` alors qu'un vrai `? :` ne le ferait
pas. À vérifier si ce cas se présente en pratique avant d'écrire quoi que ce soit.

#### Ce que le fork coûterait, si tranché « oui »

- **La coloration syntaxique du Script Editor** (`lua_editor.py`) devrait apprendre ces tokens
  en plus, sinon ils s'afficheraient comme une erreur alors qu'ils compileraient.
- **Un vrai script Lua copié ailleurs** (interpréteur externe, autre colorateur) ne le
  reconnaîtrait plus comme du Lua valide.
- **Les numéros de ligne/colonne d'une vraie erreur de syntaxe** se décaleraient : `luaparser`
  rapporterait la position dans le texte RÉÉCRIT, pas dans ce que l'auteur a tapé — une faute
  ailleurs sur la ligne verrait son message mentir sur l'endroit fautif.
- `? :` est le plus dur à réécrire sûrement en texte (imbrication, `?`/`:` à l'intérieur d'une
  chaîne…) — une regex naïve est fragile ; il faudrait un petit tokenizer dédié, pas un
  remplacement de texte.
- `+=`/`++`/`--` sont plus simples : réécriture au niveau de l'instruction complète
  (`NOM (+=|-=|*=|/=) EXPR` ou `NOM (\+\+|--)`), sans ambiguïté de priorité d'opérateurs.

### v3.0 — Le second moteur de rendu

**Décidé (2026-08-13) : l'éditeur porte DEUX moteurs de rendu.** Un moteur 2D — tout ce qui
existe jusqu'à la v2.2 incluse, calques tuilés et OBJ — et un moteur 3D, qui est le sujet de
cette version.

L'ancienne v3.0 « modes bitmap » disparaît en tant que jalon et **devient le substrat de
celle-ci**. Elle n'avait jamais été un jalon pour l'auteur de jeu : personne ne veut « le
support du mode 4 », on veut ce qu'il permet. Elle reste décrite ci-dessous parce que ses
contraintes ne changent pas, mais elle ne se livre plus seule.

Ce n'est pas un mode de plus dans le moteur existant. C'est **un second moteur**, et cette
version consiste autant à réoutiller l'éditeur qu'à écrire un rasteriseur.

#### Le substrat — les modes bitmap

Famille complètement différente des modes tuilés : un seul calque, pas de tuiles ni de cartes,
un framebuffer direct. Le budget des sprites y est par ailleurs divisé par deux.

| Mode | Résolution | Couleur | Tampons |
| --- | --- | --- | --- |
| 3 | 240×160 | 16 bits directs | 1 seul |
| 4 | 240×160 | 8 bits indexés | 2 (double tampon) |
| 5 | 160×128 | 16 bits directs | 2, résolution réduite |

**Priorité au mode 4** : 256 couleurs, double tampon, pleine résolution — il évite le
déchirement d'image du mode 3 et la résolution réduite du mode 5. C'est aussi celui que le
jeu de référence emploie (relevé du 2026-08-13).

**Exclu délibérément des fondations v0.3** : les modes bitmap cassent tout le pipeline actuel
(tilesets réutilisables, palettes par banque) au profit d'un framebuffer brut — et c'est aussi
pourquoi de vrais jeux commerciaux les emploient rarement.

Une brique est déjà là : `BackgroundAsset.mode == "bitmap"` existe côté éditeur (image plein
écran, détectée à l'import) et n'attend que son émission ROM. C'est le plus petit usage du
framebuffer, sans géométrie — un bon premier pas dans cette version.

**Ce que le framebuffer débloque, et rien d'autre ne débloquera** : la vraie *flow map* — une
distorsion décidée par pixel, et non par ligne comme en v2.2 — et le rendu de géométrie
ci-dessous. C'est le seul mode où l'adresse de chaque pixel de destination est écrite par le
programme.

#### Ce qui reste PARTAGÉ entre les deux moteurs

C'est la liste la plus importante de cette version : ce qui n'y figure pas se dédouble, et
tout ce qui se dédouble est une occasion de diverger. Elle se tient courte volontairement.

Palettes, audio, table de textes, variables et sauvegarde, scripting (le langage, le parseur,
le checker, le renommage), le pipeline de build et la construction de la ROM, la découverte
d'assets et les sidecars. **Rien de tout cela ne connaît le mode de rendu**, et rien ne doit
l'apprendre.

Les sprites (OBJ) sont partagés aussi, et c'est contre-intuitif : ils survivent au changement
de moteur puisque le matériel OBJ est le même — mieux, c'est en 3D qu'ils portent le CIEL
(cf. « rôles inversés » ci-dessous).

#### Ce qui se DÉDOUBLE, et à quel niveau

- **La scène.** `Scene.render_mode` existe déjà en ébauche : c'est le bon endroit, et
  l'arbitrage est **par scène, pas par projet** — un jeu veut ses menus en 2D et sa course en
  3D. Conséquence : la moitié des champs de `Scene` n'a de sens que dans un moteur
  (`background_layers`, `collision_map`, `windows`, `text_bg` d'un côté ; la géométrie et la
  caméra à projection de l'autre). À trancher : deux types de scène, ou un type dont les
  champs se taisent selon le mode.
- **Le canvas.** Cf. « Le point dur » ci-dessous.
- **Les assets de géométrie.** Maillages et textures n'ont aucun équivalent 2D. Ils entrent
  dans le pipeline d'import existant (fichier déposé → sidecar), pas dans un pipeline neuf.
- **Le codegen.** Second chemin d'émission, comme prévu de longue date pour l'affine.
- **L'API Lua.** `layer.*`, `tilemap.*`, `window.*` ne veulent rien dire en 3D, et la
  géométrie n'a pas d'équivalent en 2D. `RUNTIME_API` doit donc porter la disponibilité par
  moteur, et le checker refuser un appel 2D dans une scène 3D — sinon la faute n'apparaît
  qu'au `make`, sur une ligne générée, jamais sur la cause. C'est le même défaut que les deux
  listes de prototypes du moteur, et il se règle au même endroit : dans le catalogue.
- **Les écrans de l'éditeur.** Le Background Editor n'a pas d'objet en 3D ; le Palette Editor
  et le Sprite Editor gardent le leur ; le Scene Manager change de nature. Un écran doit
  pouvoir déclarer les moteurs où il s'applique, faute de quoi l'utilisateur voit des outils
  qui ne peuvent rien produire pour la scène ouverte.

#### L'aperçu fidèle — une source, deux compilations

`core/engine_emulation/` existe parce que **l'éditeur refait en Python ce que la console fait
en C**, pour montrer le vrai résultat plutôt qu'une approximation : le layout de texte, les
formules de mélange, le mixeur. Promesse tenue jusqu'ici, à un coût connu — deux
implémentations à tenir d'accord.

Un moteur 3D aurait mis cette promesse en défaut : porter un rasteriseur en Python fait de la
double implémentation un vrai risque, et ses divergences sont **invisibles** — un arrondi en
virgule fixe qui diffère ne plante pas, il donne une autre image. L'autre issue était d'admettre
un aperçu approximatif, c'est-à-dire de mentir pour la première fois.

**Décision (2026-08-13) : ni l'un ni l'autre. Le rasteriseur s'écrit UNE fois, en C portable,
et se compile DEUX fois** — pour la GBA (ARM, en IWRAM), et pour l'hôte en bibliothèque
partagée que l'éditeur appelle et dont il affiche le tampon rendu. Même source, mêmes types en
virgule fixe : l'image de l'aperçu est identique au pixel près **par construction**, et non par
discipline. C'est ce qu'Unity obtient en embarquant son runtime dans son éditeur ; on l'obtient
en compilant le même fichier deux fois.

Ce que ça implique, et qui n'est pas négociable :

- **Le cœur du rasteriseur ne touche JAMAIS le matériel.** Il reçoit un pointeur de destination
  et une palette de son appelant ; c'est la couche GBA qui lui passe la VRAM. Si la version
  console écrit dans la VRAM en ligne, la compilation hôte devient impossible. **C'est le seul
  point de cette version dont l'ordre est irréversible** : la contrainte ne coûte rien
  aujourd'hui et ne se rattrape pas après coup.
- **Ce que l'aperçu ne donnera pas : le temps.** Sur PC il tournera vite quoi qu'il arrive et ne
  dira jamais si la frame tient dans le budget. mGBA reste l'outil de la cadence — appelé, pas
  incorporé, et le lancement de ROM est déjà outillé.
- **Un compilateur C hôte devient une dépendance de build**, pour ce composant seulement.
  Relevé sur la machine de développement (2026-08-13) : aucun compilateur hôte, et le msys2
  livré avec devkitPro n'expose que les dépôts `msys`, `dkp-libs`, `dkp-windows` — pas de
  mingw-w64. C'est donc une installation à part, et elle ne concerne que qui touche au
  rasteriseur : l'éditeur se distribue avec la bibliothèque déjà compilée, et le reste du
  travail Python n'en a pas besoin.
- **TCC pour développer, gcc pour publier.** TCC (Tiny C Compiler) tient en quelques
  mégaoctets et un seul dossier, et sort la bibliothèque directement (`tcc -shared`) : c'est
  le coût d'entrée le plus bas pour itérer sur le rasteriseur. Il convient d'autant mieux que
  la source doit de toute façon rester du C conservateur et sans dépendances — elle compile
  pour un ARM7TDMI avec devkitARM, ce qui interdit déjà tout ce que TCC ne saurait pas
  digérer. Les builds de **release** passent par gcc (w64devkit, ou la CI qui en fournit un
  gratuitement), pour du code optimisé et un compilateur éprouvé.

  Le risque de TCC est réel mais borné : moins éprouvé que gcc, et une compilation fausse
  donnerait une **image fausse** plutôt qu'un plantage. Deux garde-fous tombent tout seuls :
  la même source tourne sur le vrai matériel (mGBA), et la présence des deux chaînes fait du
  build de release un **test différentiel gratuit** — si l'image TCC et l'image gcc diffèrent,
  l'un des deux compilateurs a tort et on le sait avant l'utilisateur.

  **Ce choix n'engage rien.** Le compilateur hôte est un détail de build, pas une décision
  d'architecture : la source étant du C portable dans les deux cas, remplacer TCC par autre
  chose ne déplace aucune ligne, aucun format, aucune structure. À rouvrir librement, sans
  que ce soit une reprise de décision.

#### Ouvert

- Le nom des deux moteurs, dans le code comme dans l'interface. Il sera lu partout et pour
  longtemps.
- Une scène peut-elle mélanger les deux ? Le matériel dit non pour les calques, mais les OBJ
  traversent — donc « pas de mélange » est faux tel quel, et « mélange libre » est faux
  aussi.
- Ce que devient un projet dont l'auteur bascule une scène d'un moteur à l'autre. Rien ne se
  convertit ; la question est ce que l'éditeur en dit.

### v3.1 — Le rasteriseur

Le moteur 3D proprement dit, une fois le substrat et le réoutillage de la v3.0 en place.

#### L'objectif concret — V-Rally 3

**Un jeu du niveau de V-Rally 3 sur GBA doit être constructible avec l'éditeur.** Premier
objectif de la roadmap énoncé comme un résultat visible plutôt que comme une capacité — c'est
ce qui rend sa portée décidable : une capacité s'étend indéfiniment, une cible se compare.

#### Décisions verrouillées

- **C'est un rasteriseur logiciel, mesuré, pas supposé.** Relevé mGBA du 2026-08-13 : mode 4,
  framebuffer 240×160 8bpp double-tamponné (`0x0600A000` = frame 1), aucune base de tuiles, et
  des maillages qui tournent dans les menus. **Confirmé en course**, où toute la scène passe
  par ce même framebuffer — le doute « les menus seulement » est levé, il n'y a pas de chemin
  hybride. Le détail du relevé et l'erreur qu'il corrige sont conservés en v2.0, « Ce que la
  v2.0 n'est PAS ».
- **Le framebuffer d'abord, sans alternative.** Le rendu écrit chaque pixel : il lui faut le
  substrat bitmap de la v3.0, et il n'y a aucun chemin par les calques tuilés. Ce n'est pas
  une préférence d'ordonnancement, c'est une dépendance — d'où la découpe v3.0 / v3.1.
- **La GBA n'a ni FPU ni matériel 3D.** Tout est en virgule fixe et coûte des cycles
  proportionnels au nombre de triangles — c'est le seul renderer de la roadmap dont le coût
  dépend du contenu de la scène et non de sa configuration. Le budget est donc un sujet de
  conception, pas une optimisation de fin de chantier.
- **Le vocabulaire ne change pas de règle pour autant.** « 3D » décrit ici ce que le
  PROGRAMME calcule, jamais une capacité du matériel : pas de calque 3D, pas de mode vidéo
  3D. La réserve de la v2.0 sur « Caméra3D » tombe en revanche — une caméra à projection
  perspective a un sens dans cette version, parce que quelque chose la calcule enfin.
- **Les rôles fond/sprite sont INVERSÉS par rapport à tout le reste de l'éditeur.** Relevé en
  course (2026-08-13) : le monde entier — sol, route, panneaux publicitaires, bâtiments,
  public — est rasterisé dans l'unique fond disponible, et **c'est le ciel qui est fait de
  sprites**.

  Mesuré : un seul fond porte toute la scène, aucun élément de décor n'est un OBJ, l'arrière-
  plan lointain en est un. Déduit : en mode bitmap il ne reste qu'un fond (BG2 = le
  framebuffer), donc aucun calque pour le ciel ; et remplir le ciel dans le framebuffer
  coûterait du CPU à chaque pixel de chaque frame, quand le matériel OBJ le peint pour rien.
  Le rasteriseur ne dessine que sous l'horizon.

  Trois conséquences, toutes structurantes :

  - **Le vocabulaire actuel de l'éditeur ne tient pas ici.** Ce que l'auteur appelle « le
    fond » (le ciel) est de l'OBJ ; ce que le matériel appelle le fond est la cible de rendu,
    que personne n'authore. Les deux sens du mot se croisent — à trancher avant d'écrire le
    moindre écran, sous peine d'un inspecteur qui ment sur ce qu'il configure.
  - **Le budget OBJ devient un sujet.** Les modes bitmap divisent déjà la VRAM des sprites
    par deux (cf. v3.0) — et le ciel vient maintenant en réclamer une part. Un ciel en bandes
    répétées, avare en tuiles uniques, n'est pas une optimisation tardive : c'est la
    condition pour qu'il reste des sprites au jeu.
  - **Aucune contrainte affine ne s'applique.** Les 32 jeux de paramètres OBJ, invoqués tant
    que la lecture était « décor en sprites mis à l'échelle », ne concernent rien ici.

#### Ouvert

- Tout le reste. Format des maillages, texturage ou faces plates, élimination des faces
  cachées, tri en profondeur, découpage, budget par scène, et ce que l'éditeur montre d'un
  maillage sans devenir un modeleur — le refus de l'outil de dessin s'applique ici aussi, et
  il est bien plus dur à tenir face à de la géométrie que face à des tuiles.
- **Le ciel est-il authoré comme un fond, ou comme des sprites ?** Les deux réponses coûtent
  quelque chose. « Comme un fond » garde le modèle mental de l'auteur — il dessine un ciel,
  le build le découpe en OBJ — mais c'est l'éditeur qui commente le matériel au lieu de le
  rendre, ce que la maison refuse partout ailleurs. « Comme des sprites » est honnête et
  demande à l'auteur de comprendre pourquoi son ciel n'est pas un fond. La tension est réelle
  et ne se tranche pas à l'avance.
- Le lien avec la v2.1 : une course a besoin de physique, mais la physique de la v2.1 est
  **2D**. Ce qu'il faut ici pour un véhicule sur un relief n'est pas décidé, et ce n'est pas
  la même chose.
- La cadence visée. 60 fps n'est pas donné ; le jeu de référence tourne dans un budget qu'il
  faudra mesurer plutôt que supposer.

---

## Hors périmètre (pour l'instant)

- **Multijoueur par câble Link** — envisagé après la v1.0, pas avant. Très spécifique et
  coûteux à implémenter proprement.
