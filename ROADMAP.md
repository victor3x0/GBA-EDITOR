
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
| v0.25 | La grammaire de la struct `Actor` | **En cours** |
| v0.26 | Les trois couleurs de l'interface | **En cours** |
| v0.9 | Traduction des jeux | **En cours** — déclarer, traduire, émettre et choisir livrés (phases 1-4, `lang.set`/`lang.get`) ; servir (phase 5 — SRAM, écran de choix) à faire |
| v0.10 | Distribution Linux | Non commencée |
| v0.11 | Traduction de l'éditeur | **En cours** — gabarit de notices et catalogue livrés ; sélection de langue à faire |
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

La **v0.25** ne vient pas de cette revue : elle est née d'une question posée à l'architecture le
2026-08-23 (« l'API C tient-elle les trois concepts de l'éditeur ? »). Sa section se lit juste
après le bloc priorisé, et elle se traite tôt : elle touche la struct que tous les autres
jalons manipulent, donc chaque jalon ouvert après elle est un jalon à ne pas migrer.

Un numéro de version reste une **identité**, pas un rang : il n'est pas renuméroté quand
l'ordre de traitement change. Seul l'ordre de LECTURE de ce document — et l'ordre dans lequel
les chantiers seront ouverts — suit désormais l'ordre de traitement.

---

## Correctifs (trouvés en marchant, hors chantier)

Six défauts réels, trouvés en construisant et en jouant les projets démo pendant le chantier
v0.9, sans rapport avec la traduction elle-même — consignés ici pour ne pas rester invisibles
faute d'un jalon à qui les rattacher.

- **`_hw_layer_z` — l'ordre de composition du canvas** (`ui/scene_manager/scene_canvas.py`).
  Un acteur (OBJ) portait un zValue fixe (10) et une zone d'interface un zValue fixe (120) :
  l'acteur passait donc TOUJOURS sous l'interface dans le canvas, quelle que soit la priorité
  réelle — le contraire de ce que montre la ROM dès que `text_bg` n'est pas 0 (priorité GBA =
  `bg_slot` directement, et à priorité égale l'OBJ passe devant le BG). Le canvas reproduit
  désormais l'ordre matériel plutôt qu'un empilement choisi pour le confort de l'édition.
  Tests : `test_canvas_draw_order.py`.

- **`BOXTAG_*` absent pour une box portée par un prefab** (`codegen/runtime_codegen/headers.py`).
  `spawn_<Prefab>()` écrit `boxes[].tag = BOXTAG_<TAG>` pour la box d'un prefab poolé et de ses
  parties (v0.23, « Ce qu'un boss demande »), mais la génération des `#define` ne parcourait
  que les acteurs de SCÈNE — un tag porté seulement par un prefab n'avait donc pas de
  constante, et le C émis ne compilait pas (`'BOXTAG_BODY' undeclared`).
  `Project.collision_tags()` était déjà la source unique (scènes, prefabs, parties de prefabs)
  pour le sélecteur de tag et la matrice de Project Settings ; le codegen en était la troisième
  lecture, et la seule qui mentait. Tests : `test_collision_tags.py`.

- **Glyphes animés d'une zone : dérivés, plus déclarés** (`core/project.py`,
  `core/models/ui_region.py`). Le nombre de caractères qu'une zone sort de la bande pour les
  animer était un champ rempli à la main dans l'inspecteur ; il se déduit désormais du texte
  affiché (`Project.region_animated_glyphs`), au maximum sur TOUTES les langues déclarées (une
  réservation trop basse fait retomber l'effet en statique sans un mot) et plafonné aux slots
  OAM disponibles (zéro quand rien n'est animé). Le modèle ne résout pas la table de textes —
  le compte lui est fourni, comme les frames d'un sprite. Tests : `test_animated_glyphs.py`.

- **Renommer une clé de texte désynchronisait les zones d'interface**
  (`core/project_renames.py`). `region.text_key` est une COPIE de chaîne, pas l'id stable du
  texte. Le script Lua qui cite une clé était déjà réécrit par `rename_lua_refs` ; les zones
  d'interface (`UIText.text_key`), l'autre des deux seuls référents d'une clé (cf.
  `TextUsage`), ne l'étaient pas — un rangement qui recale une clé automatiquement
  désynchronisait silencieusement l'écran de scène. Bug réel rencontré sur le projet démo
  Fonts&Texts (2026-08-27). Tests : `test_text_key_ui_sync.py`.

- **Surface de composition texte partagée entre zones qui ne devraient pas se disputer les
  tuiles** (`gba_engine.h`, `codegen/font_emit.py`). La surface partagée est adressée modulo
  et ne couvre que 8 rangées sur les 20 de l'écran : deux zones dont les rangées coïncidaient
  modulo 8 se disputaient les mêmes tuiles et s'écrasaient en VRAM — un titre en haut et une
  boîte de dialogue en bas, une mise en page banale, tombait dans ce cas, et aucun garde-fou ne
  pouvait le rendre acceptable : c'était la mise en page qu'il fallait interdire. Corrigé en
  allouant un bloc PAR ZONE (`RegionSurf`), à la taille du rectangle ABSOLU (une zone enfant
  d'un panneau n'occupe pas les tuiles écran de son offset local) ; la surface partagée n'est
  plus réservée que si un script écrit LIBREMENT (`text.draw`/`text.clear`, qui n'ont pas de
  rectangle à qui donner un bloc). Tests : `test_text_surface_alloc.py`.

- **`g_ui_list_total` démarrait à 0** (`codegen/runtime_codegen/main_gen.py`). Un panneau
  « Liste » restait figé tant que le script n'appelait pas `list.set_count`, même avec des
  rangées visibles posées dans le canvas — contraire au propre texte de l'inspecteur de scène
  (« place text zones INSIDE this panel — ceux-là sont ce que la liste parcourt »). Le total
  démarre désormais au compte de rangées AUTHORÉES ; `list.set_count` garde son rôle pour dire
  un total plus grand que les rangées visibles (un inventaire qui défile), auquel cas il écrase
  le défaut. Tests : `test_ui_list_default_count.py`.

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
> **L'en-tête de sauvegarde étendu est réglé le 2026-08-23**, par un troisième verbe plutôt
> qu'un nouveau concept : `save.read(slot, "nom")` rend la valeur d'UNE variable persistante
> dans un emplacement, sans toucher aux globales de la partie en cours. L'auteur compose son
> écran de sélection en l'appelant sur chacune des variables qu'il veut montrer — la
> « désignation » de la décision verrouillée n'est rien d'autre que le choix des variables sur
> lesquelles l'auteur appelle cette fonction. Au passage, l'ancien `save.read(slot)` — qui
> remplace TOUTES les persistantes de la partie en cours, un geste bien plus lourd que ce que
> « lire » suggère — est renommé `save.load(slot)`, le mot qu'un menu affiche déjà
> (« Charger une partie »).


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
- **`save.read(slot, "nom")`, pas un nouveau concept d'« en-tête ».** *(Tranché le
  2026-08-23.)* Le format SRAM (v0.20) range déjà chaque variable persistante dans son propre
  enregistrement, retrouvable par balayage indépendamment des autres — `save.read` ne fait que
  s'arrêter au premier enregistrement qui correspond, sans rejouer tout `save_read` (qui, lui,
  réécrit TOUTES les globales persistantes). Rien à ajouter au modèle : ni un champ « variable
  d'en-tête » sur `GlobalVar`, ni un panneau dédié. La désignation que demandait la décision
  ci-dessus est simplement l'ensemble des variables que l'auteur choisit d'appeler.
- **`save.read(slot)` devient `save.load(slot)`.** *(Tranché le 2026-08-23, renommage
  complet.)* Le nom masquait ce que fait l'appel : remplacer TOUTES les globales persistantes
  de la partie en cours n'est pas ce que « lire » suggère. « Charger » l'est, et c'est déjà le
  mot que porte le bouton du menu qui l'appelle. Ça libère aussi `save.read` pour ce qu'il
  désigne réellement ci-dessus : une lecture SANS effet de bord, symétrique de
  `global_read`/`global_read_at` (déjà ce nom en C, pour exactement ce sens) plutôt qu'un
  troisième mot (« peek ») pour un concept qui en avait déjà un dans cette base de code.

### Ce que ça touche

[ui_region.py](editor/core/models/ui_region.py),
[main_gen.py](editor/codegen/runtime_codegen/main_gen.py) (le tick d'UI),
[api.py](editor/scripting/api.py) (un domaine `list`, et le renommage/l'ajout `save.*`),
[codegen.py](editor/scripting/codegen.py) et
[checker.py](editor/scripting/checker.py) (résolution et vérification de `save.read`),
[lua_compiler.py](editor/codegen/runtime_codegen/lua_compiler.py) (le contexte de vérification
sait désormais quelles variables sont persistantes),
[gba_engine.h](runtime/include/gba_engine.h) (`save_read_var`, la lecture sans effet de bord)
et [actor_api_static.h](runtime/include/actor_api_static.h) (son prototype — le piège relevé
plus haut), l'inspecteur de scène, et `validator.py`.

### Ouvert

- ~~**Où une liste se dessine.**~~ **Tranché le 2026-08-21** : sur le calque de texte — ses
  rangées sont ses zones de texte enfants, dans l'ordre de l'arbre. Le budget de tuiles d'UI et
  la grille de tuiles restent ceux d'un panneau de texte ordinaire ; rien de neuf à gérer côté
  OAM.
- ~~**Le défilement, à la ligne ou au pixel.**~~ **Tranché le 2026-08-21** : à la ligne — le
  texte reste sur sa grille de tuiles, et l'OAM reste libre pour les acteurs et le curseur.
- ~~**La répétition de touche.**~~ **Tranché le 2026-08-21** : cadence en défaut de PROJET,
  surchargeable par liste — le même patron que la transition de scène (v0.6.2), qui répond
  déjà à l'objection « trois listes à trois cadences, un joueur le sent ».
- ~~**Ce que le moteur fait d'un choix de dialogue.**~~ **Tranché le 2026-08-21** : une liste
  comme les autres — un raccourci pour 2-3 options aurait été le premier « widget par genre de
  menu », dont la liste n'a pas de fin.

Les quatre questions ouvertes sont donc closes, et implémentées de bout en bout (`list.*` dans
[api.py](editor/scripting/api.py), le tick dans
[main_gen.py](editor/codegen/runtime_codegen/main_gen.py),
[gba_engine.h](runtime/include/gba_engine.h) et
[actor_api_static.h](runtime/include/actor_api_static.h)) — de même que l'en-tête de sauvegarde
(`save.read`/`save.load`, tranché le 2026-08-23, câblé dans
[codegen.py](editor/scripting/codegen.py) et
[checker.py](editor/scripting/checker.py)). Rien ne reste ouvert pour ce jalon.

---

## v0.25 — La grammaire de la struct `Actor` — **EN COURS**

### D'où vient la question

Posée le 2026-08-23, en relisant l'architecture : l'éditeur distingue trois choses — un
**actor** (logique de jeu), un **sprite** (son rendu), un **background** (le décor). Est-ce
que l'API C tient la même distinction ?

Non. Côté C il n'existe **qu'une struct**, `Actor`, et elle porte les trois familles à plat :
la logique (`x, y, vx, vy, timer, tag`), le rendu OBJ (`frame, anim_*, flip_*, pal_bank,
obj_mode, priority, sprite_rot, sprite_scale_*, offset_*`) et la collision (`boxes, box_count,
grounded, last_x, slope_acc`). 37 `int` et 4 `CollisionBox`, sans frontière visible.

Le background, lui, n'a **pas** de type C, et c'est correct : le calque **est** le matériel
(`layer_*(int bg, …)`, `tilemap_*(int bg, …)` et les registres ombres `g_bgcnt_sh[4]`,
`g_bg_ofs_x/y[4]`). Il y a quatre plans dans la machine ; leur donner un type instanciable
suggérerait qu'on peut en créer un cinquième. **Ce point ne bouge pas.**

### Ce que ce jalon n'est pas

Il ne sépare **pas** `Actor` en deux structs. Le rapport est 1:1 (un actor porte au plus un
`SpriteComponent`), et l'indirection coûterait un déréférencement par accès sur un ARM7TDMI
sans cache. Le merge est **assumé** ; ce qui change, c'est qu'il devient lisible.

### Ce que la lecture du code a écarté, et pourquoi

Trois pistes ouvertes le 2026-08-23, deux refermées le jour même après lecture :

- **« Supprimer la recopie par tick de `anim_length`/`anim_loop`/`anim_finished` ».** Écartée.
  `anim_length` n'est pas `state_len[state]` : c'est la longueur du bloc de la **direction
  actuellement jouée**, que `_anim_tick_lines` trouve par un parcours de `anim_dirs[]` avec
  repli sur la direction omni. La recopie **mémoïse le parcours que le tick fait déjà**.
  Exposer les tables aux scripts déplacerait la boucle dans chaque lecture de
  `self.anim_length` — plus lent, pas plus propre. `anim_finished` en dérive.
  Reste `anim_loop`, seule copie réellement pure : l'effacer coûterait un `const SpriteDef*`
  de 4 octets pour économiser un `int` de 4 octets, plus une indirection. Gain nul.
- **« Découpler le slot OAM de l'index d'acteur ».** Hors périmètre par décision existante :
  c'est le *Chantier transverse — l'allocateur de ressources matérielles*, qui attend son
  deuxième consommateur, et dont une décision verrouillée dit déjà qu'« un arbitrage OAM par
  frame est un vrai coût CPU ; il se décide sur un cas mesuré, pas à l'avance ».
- **`frame_w`/`frame_h` par instance.** Ressemblent à une duplication de
  `SpriteAsset.frame_w/h`. N'en sont pas : le script d'un prefab poolé est une fonction C
  partagée par toutes ses instances, elle ne peut pas les recevoir en `#define`.

L'argument mémoire n'existe de toute façon pas : `g_actors` est en EWRAM ordinaire — 128
entrées de ~172 octets, soit ~22 Ko sur 256.

### Décisions verrouillées

- **Trois blocs, calqués sur les composants de l'éditeur.** Pas une taxonomie inventée pour
  l'occasion (`render`/`body`) : la décomposition existe déjà, c'est celle que l'inspecteur
  affiche. `Actor` racine ↔ `Actor` éditeur, `Actor.sprite` ↔ `SpriteComponent`,
  `Actor.collision` ↔ `CollisionBoxComponent`. Le C émis dit alors la même chose que l'UI —
  c'est la grammaire unique appliquée à la struct.

  | Bloc | Champs |
  | --- | --- |
  | `Actor` | `x, y, vx, vy, timer, tag, active, dir_x, dir_y, rotation, scale_x, scale_y, visible, priority, pal_bank, obj_mode, flip_h, flip_v` |
  | `Actor.sprite` | `frame, anim_state, anim_speed, anim_length, anim_loop, anim_finished, frame_w, frame_h, auto_dir, rotation, scale_x, scale_y, offset_x, offset_y, affine_slot` |
  | `Actor.collision` | `grounded, last_x, slope_acc, box_count, boxes[]` |

- **La réservation affine appartient au sprite, pas à l'actor** *(2026-08-25)*. `affine_transform`
  vivait sur l'`Actor` et s'affichait dans une carte « Affine » à part, dont le commentaire de
  l'inspecteur disait déjà pourquoi : « ce n'est pas un PLACEMENT mais une capacité de RENDU ».
  C'est l'argument exact qui la met sur le `SpriteComponent` — le composant de rendu, le seul
  qui s'affiche aussi sur une racine de prefab. Trois conséquences :

  - la carte « Affine » de l'inspecteur disparaît ; la case passe dans la carte du
    SpriteComponent, et Rotation/Scale de l'actor remontent dans **Transform** (ils y étaient
    déjà masqués sur une racine de prefab — rien ne change de ce côté) ;
  - côté C, `affine_slot` suit le flag et passe dans le bloc `sprite` : c'est le principe même
    de ce jalon, le C émis dit la même chose que l'UI ;
  - `Prefab.affine_transform` délègue au SpriteComponent de son actor racine, et les deux
    recopies manuelles de `command_dispatcher` (Relink/Expose) disparaissent — le
    `deepcopy(components)` qui les précède transporte déjà le flag.

- **`Actor.rotation`/`scale` sont du STOCKAGE, pas un privilège du slot** *(2026-08-25)*. Les
  accesseurs étaient gardés par `if (affine_slot >= 0)` : sans slot, setter no-op et getter
  identité — `self.rotation = self.rotation + 1` n'incrémentait rien, la valeur ne faisait
  même pas l'aller-retour. Les champs existent dans **chaque** `Actor` de toute façon ; seule
  l'écriture de la matrice OAM a besoin du slot. Les gardes tombent donc.

  Le checker **garde son contrôle mais descend d'un cran** : `error` → `warning`. Il reste le
  seul endroit qui voit qu'un script écrit `self.rotation`, et c'est l'oubli réel qu'il faut
  signaler ; ce qui change est qu'il ne refuse plus le build. Même registre que le cas
  parent/enfant juste à côté : le jeu tourne, c'est l'affichage qui ment. Une valeur qu'un
  script peut lire, écrire et relire sans effet visible est un modèle plus simple à expliquer
  qu'une propriété qui s'évapore. `BuildContext.affine_transform` reste donc, alimenté
  désormais par le SpriteComponent.

- **Les trois abréviations disparaissent avec le namespace qui les rendait nécessaires.**
  `sprite_rot` → `sprite.rotation`, `sprite_scale_x/y` → `sprite.scale_x/y`, `offset_x/y` →
  `sprite.offset_x/y`. Elles n'existaient que parce que la struct était plate. La règle
  « jamais d'abréviation » redevient tenue sans exception.

- **La surface Lua ne bouge pas d'un caractère.** `self.frame`, `self.sprite_scale`,
  `self.anim_length` passent tous par les accesseurs de `actor_api_static.h` :
  `scripting/api.py`, `codegen.py`, `checker.py` et `expr_types.py` ne touchent aucun champ
  directement. Ce jalon n'est pas une rupture pour les projets existants.

- **Le compilateur est le vérificateur exhaustif.** Un site oublié ne compile pas. La
  condition est donc de builder réellement la ROM à la fin, pas seulement de lancer les
  tests — sans quoi la garantie n'est pas encaissée.

### Ce que ça touche

| Fichier | Sites | Nature |
| --- | --- | --- |
| [main_gen.py](editor/codegen/runtime_codegen/main_gen.py) | 162 | `g_actors[i].champ` dans des f-strings |
| [actor_api_static.h](runtime/include/actor_api_static.h) | ~90 | `s->champ` dans les accesseurs |
| [actor_types_static.h](runtime/include/actor_types_static.h) | 1 | la struct elle-même |
| [test_affine_model.py](tests/test_affine_model.py) | 3 | assertions sur le C émis |
| [headers.py](editor/codegen/runtime_codegen/headers.py) | commentaire | l'en-tête de `actor_types.h` |

Et pour la réservation affine passée au sprite :

| Fichier | Nature |
| --- | --- |
| [components.py](editor/core/models/components.py) | `SpriteComponent.affine_transform` |
| [scene.py](editor/core/models/scene.py) | retrait de `Actor.affine_transform`, migration à la lecture, délégation `Prefab` |
| [actor_inspector.py](editor/ui/scene_manager/inspectors/actor_inspector.py) | carte « Affine » supprimée, Rotation/Scale remontés dans Transform |
| [component_editors/sprite.py](editor/ui/scene_manager/inspectors/component_editors/sprite.py) | la case, et le grisage qui la lit |
| [checker.py](editor/scripting/checker.py) | le contrôle passe de `error` à `warning` |
| [api.py](editor/scripting/api.py) | « Nécessite … sur l'actor » → « ne s'affiche que si le sprite … » (6 docs) |
| [lua_compiler.py](editor/codegen/runtime_codegen/lua_compiler.py) | le flag se lit sur le sprite (`_affine_reserved`) |
| [command_dispatcher.py](editor/core/command_dispatcher.py) | les deux recopies Relink/Expose disparaissent |
| [scene_canvas.py](editor/ui/scene_manager/scene_canvas.py) | le rendu éditeur lit le flag sur le sprite |

### Ouvert

- **`ARCHITECTURE.md` porte les anciens noms plats** (`Actor.obj_mode`, `g_actors[i].rotation`,
  `Actor.last_x`, `Actor.grounded`…). Ils y sont justes tant que le
  découpage n'est pas fait : ce fichier décrit le code tel qu'il est. Il devient donc la liste
  de contrôle du chantier, pas une dette à corriger d'avance.

---

## v0.26 — Les trois couleurs de l'interface — **EN COURS**

### D'où vient la question (2026-08-24)

Un conteneur en fond couleur ne colorait qu'une partie de sa zone. Le diagnostic n'a pas
trouvé un bug de géométrie mais **deux chemins qui ne s'accordaient pas sur ce qui est
émis** : `scene_color_fills` écarte un panneau dont la palette n'est pas dans les palettes
BG actives de la scène (il lui faut une banque matérielle), tandis que `_region_bg_fills` —
qui donnait aux zones de texte ENFANTS la couleur de leur panneau ancêtre — n'appliquait
aucune de ces conditions. Résultat : le panneau ne dessinait rien, mais sa couleur
apparaissait quand même dans la boîte de son texte enfant. Un échec **partiel et joli**, bien
plus difficile à lire qu'un fond franchement absent.

La cause profonde n'est pas la condition manquante, c'est qu'**une seule notion en portait
trois** : le fond d'un conteneur, l'encre d'un texte, et la couleur posée sous ce texte
étaient réglées à deux endroits pour trois effets.

### Décisions verrouillées

- **Trois couleurs nommées, trois champs distincts.** Le fond (`UIPanel.fill_palette` +
  `fill_index`), l'encre (`UIText.text_color`) et le **surlignement** (`UIText.highlight_color`,
  nouveau). Trois mots dans l'interface — *Color*, *Ink*, *Highlight* — parce que trois
  effets différents réglés sous le même mot est précisément ce qui a produit le défaut.
- **Un texte prend le fond de son conteneur, par défaut et sans rien déclarer.** Écrire ne
  doit jamais PERCER ce qu'il y a dessous : le chemin tilemap remplacerait la cellule par une
  tuile de glyphe, dont l'index 0 est transparent. C'est une règle de non-destruction, pas
  une teinte — la zone ne s'approprie pas la couleur, elle refuse de l'effacer.
- **Le surlignement SURCHARGE ce fond**, sur l'étendue que le texte écrit. Le fond dit ce
  qu'il y a dessous, le surlignement ce que l'auteur veut y voir à la place. Les deux
  coexistent sur une même zone, y compris sous un cadre nine-slice : le marqueur se pose SUR
  le cadre, il ne le troue pas.
- **Composer est décidé par le FOND autant que par la police.** Une zone à fond ou surlignée
  se compose même en police MONO. Le cas nine-slice était déjà censé le faire et ne le
  faisait pas (`text_is_composited` ne regardait pas la table des fonds) : un texte mono
  posé sur un cadre le trouait, alors que la donnée pour le recomposer existait. Fermé ici.
- **Le fond d'un texte est de l'état de SCÈNE, jamais de la table projet.** `RegionFill` est
  posée par `scene_init`, et son contenu DÉRIVE de `scene_color_fills` / `scene_image_fills`
  — c'est-à-dire de ce que le build émet réellement. C'est la correction de fond du
  chantier : l'ancien `_region_bg_fills`, table projet-globale, ne connaissait aucune des
  conditions d'émission, d'où un panneau écarté du build dont la couleur apparaissait quand
  même dans la boîte de son texte.
- **Deux formes de fond, UNE table.** Une carte de tuiles (nine-slice / background) ou un
  aplat (couleur), distingués par `se == NULL`. C'est une seule question — « qu'y a-t-il sous
  cette zone ? » — et deux tables auraient permis à une zone d'avoir deux fonds, ou aucun.
  Même raison pour `region_fill_panel()` : la règle « le fond le plus proche gagne » s'écrit
  une fois et se lit des deux côtés.
- **Le surlignement est un index dans la banque d'UI de la scène**, comme l'encre — même
  référentiel, même plage 0-15, `0` = aucun. Ce n'est PAS une palette + index comme le fond :
  la surface composée reçoit `g_pal_bank_bg` (une seule banque par tuile, le matériel
  l'impose), donc une couleur venue d'ailleurs devrait de toute façon être recopiée dans
  cette banque. Le champ dirait « n'importe quelle couleur » là où le matériel n'en offre
  que seize.
- **Le surlignement couvre l'étendue RENDUE du texte**, pas la boîte authorée : un
  surlignement est un trait de marqueur. La boîte entière reste PRÉPARÉE (c'est ce qui
  empêche un texte plus court que le précédent de laisser l'encre de l'ancien), mais seule
  l'étendue écrite reçoit la couleur — origine comprise, de sorte qu'un texte centré ne
  surligne pas sa marge gauche.
- **Où vit la couleur d'un aplat dépend de `scene.ui_pal_bank`, et le build tranche seul.**
  En mode AUTOMATIQUE la banque d'UI appartient à la police : le build y loge la couleur du
  conteneur, depuis le HAUT (15, 14, …) et en sautant les index que l'encre et les
  surlignements de la scène occupent déjà — la réservation est PAR SCÈNE, là où l'ancienne
  était projet-globale et ne pouvait éviter aucune collision. En banque DÉSIGNÉE le build
  n'écrit rien (ce serait remplacer en douce les couleurs choisies) : l'index du conteneur
  passe tel quel, et `_check_ui_text_fill_bank` exige que la banque désignée soit celle du
  conteneur — même contrat que le cadre nine-slice, pour la même raison matérielle.
- **Cible OBJ : pas de surlignement.** Une zone en bande de sprites ne passe pas par la
  surface BG ; le champ est masqué plutôt que proposé sans effet — même règle que
  `_FILL_TARGETS`, qui dit ce que le build ÉMET.
- **Le fond d'un conteneur se choisit dans les palettes BG ACTIVES de la scène**, par le slot
  de sélection partagé (`pickers.palette_picker_slot`) et non par une liste de tout le
  catalogue. Proposer une palette que le build écartera est exactement le défaut d'origine,
  déplacé dans le widget.
- **Pas de migration de données, et il n'en faut aucune** : le fond redevenant automatique,
  les textes qui héritaient retrouvent leur rendu sans qu'un champ soit écrit nulle part.
  `highlight_color` naît à 0 et ne dit que ce que l'auteur y a mis.

### Ce que ça touche

| Fichier | Nature |
| --- | --- |
| [ui_region.py](editor/core/models/ui_region.py) | `UIText.highlight_color` |
| [gba_engine.h](runtime/include/gba_engine.h) | `UIRegionInfo.bg_fill` → `highlight`, rectangle surligné, `text_layout` rend son origine |
| [font_emit.py](editor/codegen/font_emit.py) | la table lit le champ de la zone, plus une table annexe |
| [main_gen.py](editor/codegen/runtime_codegen/main_gen.py) | `_region_bg_fills` remplacé par `region_fill_panel` + `scene_region_colors`, dérivés des fonds émis |
| [validator.py](editor/core/validator.py) | `_check_ui_text_fill_bank` — le contrat de banque, étendu à l'aplat |
| [ui_inspector.py](editor/ui/scene_manager/inspectors/ui_inspector.py) | *Ink* / *Highlight*, slot de sélection filtré pour le fond |
| [scene_canvas.py](editor/ui/scene_manager/scene_canvas.py) | aperçu du surlignement, composition sous un conteneur à fond |
| [text_layout_probe.c](tests/native/text_layout_probe.c) + [gba_shim_common.h](tests/native/libgba_shim/gba_shim_common.h) | la sonde suit la signature — **et les stubs que la v0.22 lui devait** |

**Le test d'équivalence Python/C était déjà rouge avant ce chantier**, et il ne
le disait à personne : la sonde ne compilait plus contre `gba_engine.h` depuis
que la navigation de liste lit les touches (`KEY_*` absents du shim libgba) et
que six globales plus récentes (`g_ui_list_*`, `g_ui_element*`, `g_save_bits`,
`g_save_len`, `global_read_at/write_at`) n'avaient pas de stub. Le fichier de
test lui-même prévient qu'« un saut n'est pas un succès » — ici ce n'était même
pas un saut, c'était une erreur de compilation avalée par 37 `ERROR` de setup.
Les stubs sont complétés dans ce chantier parce que c'est exactement
`text_layout` que la sonde garde, et que je venais d'en changer la signature.

### Ouvert

- **La banque d'UI reste implicite quand `scene.ui_pal_bank` vaut -1** : encre et
  surlignement désignent alors des index de la banque de police, que l'auteur ne choisit pas.
  L'inspecteur montre les pastilles quand la banque est désignée, et rien sinon.
- **Huit fonds de zone par scène** (`TEXT_REGION_FILL_MAX`), aplats et cadres confondus —
  ils partagent désormais la table. Au-delà, les zones en trop n'ont pas de fond et le
  percent. Rien ne le signale encore ; le plafond n'a jamais été atteint, mais il est plus
  facile à atteindre maintenant que le fond est automatique.
- **Le surlignement n'est pas scriptable.** Comme l'encre, il est authoré. Un menu qui
  surligne sa ligne courante se fait aujourd'hui en écrivant dans des zones distinctes ; si
  la v0.22 rend ça pénible, c'est ici que ça se verra.

---

## v0.9 — Traduction des jeux créés avec l'éditeur — **EN COURS**

Sujet **séparé** de la traduction de l'éditeur (v0.11) : deux chantiers indépendants.

Le jalon se traite en **deux temps, dans cet ordre** : d'abord l'écran, ensuite les langues.
La raison n'est pas cosmétique. La table de textes a été conçue en v0.3 pour être traduite
(clé de référence, `note` pour le traducteur, contenu séparé du script), mais elle s'affiche
encore comme un **classeur** : un arbre qu'on déplie pour retrouver une réplique. Traduire,
c'est le geste inverse — balayer deux cents entrées pour trouver les trous. Ajouter une
seconde langue à une vue qui ne sait pas déjà montrer les trous d'une seule reviendrait à
doubler un problème avant de le résoudre.

---

### Temps 1 — L'écran central devient une table de travail

Aucune langue à ce stade, aucun changement de modèle : la même table de textes, regardée
autrement.

#### Décisions verrouillées

- **La vue est PLATE, comme le stockage.** `texts.json` est une liste dont chaque entrée
  porte son chemin ; l'arbre en était déjà une vue dérivée. Une table l'est tout autant, mais
  elle se **trie** et se **compare ligne à ligne**, ce qu'un arbre ne fait pas. Le
  regroupement ne disparaît pas pour autant : des lignes d'en-tête repliables, optionnelles,
  redonnent la lecture par catégorie quand on la veut — sans que la structure de données en
  dépende.
- **Les trois niveaux du rangement sont trois colonnes, et aucune ne s'appelle « Key ».**
  Dans le modèle, `key` désigne une chose précise et unique : la poignée que le Lua écrit et
  que le build résout. Un niveau de chemin n'est jamais résolu ni référencé. Leur donner le
  même mot dans l'interface ferait croire à deux systèmes de référence là où il n'y en a
  qu'un — la faute exacte que [le modèle](editor/core/models/text.py) refuse depuis le début.
  La clé garde donc sa propre colonne, en mono, copiable.
- **L'usage se compte, et il couvre DEUX sources.** Un texte est cité par les scripts
  (`DOMAIN_TEXT`) **et** par les mises en page (`UIText.text_key`). N'en compter qu'une
  afficherait « orphelin » sur un texte posé dans une boîte de dialogue, et quelqu'un le
  supprimerait. D'où un point unique, `Project.text_usage_index()`, que la table et
  l'inspecteur partagent — l'inspecteur avait son propre index, scripts seulement : deux
  vérités pour la même question.
- **Contenu et usage sont deux axes séparés, jamais une pastille unique.** Un texte peut être
  écrit et inutilisé, ou référencé et vide. Les fondre dans un seul statut ferait disparaître
  celui des deux qui n'a pas la priorité, et c'est précisément le croisement qui est
  intéressant : « référencé mais vide » est un bug, « écrit mais orphelin » est un oubli de
  ménage, et ce ne sont pas les mêmes gens qui les corrigent.
- **Pas de statut « traduit » tant qu'il n'y a qu'une langue.** Une pastille verte
  « Translated » sur un projet monolingue est un mensonge poli : elle dit qu'un travail a été
  fait alors qu'aucun n'a été demandé. La colonne apparaîtra avec les langues, pas avant.

#### Ce que ça coûte

Le **glisser-déposer entre nœuds** disparaît avec l'arbre. Il est remplacé par l'édition
directe des cellules de rangement — ce qui range une ligne, mais aussi N lignes d'un coup par
la sélection multiple, ce que le glisser-déposer ne savait pas faire. Le renommage d'un
groupe entier reste couvert par `repath_segment`, déclenché depuis la ligne d'en-tête.

---

### Temps 2 — Les langues

Cible **homebrew, cartouche réelle** : toutes les langues sont dans la ROM, choisies au
build, et il n'y a rien à télécharger ni à chercher au runtime. C'est ce qui décide de toute
la structure — les fichiers par langue sont un objet d'**authoring** (git, diff, traducteur),
jamais un objet de moteur. Au build, ils deviennent une dimension de tableau.

```
project/texts.json      le maître   — id, key, path, note, note de scène, contenu SOURCE
project/texts_de.json   un side     — la traduction seule, jointe par id
project/texts_ja.json   un side     — idem
```

```
text.draw(TEXT_CLE)   →   g_texts[g_lang][TEXT_CLE]     un index, jamais une recherche
text_set_font(FONT)   →   g_lang_font[g_lang][FONT]     un remap, vide = la police du projet
```

#### Décisions verrouillées

- **La langue est une DIMENSION, pas un chemin de résolution.** Tout se tranche au build,
  comme le balisage : le moteur ne connaît ni fichier, ni code de langue, ni repli à calculer
  — il indexe. Un second chemin de résolution au runtime coûterait de la ROM, du temps de
  frame, et une deuxième façon de se tromper.
- **Le maître possède la STRUCTURE, le side ne porte que la TRADUCTION.** `id`, `key`, `path`
  et `note` vivent dans `texts.json` et nulle part ailleurs. Les dupliquer dans huit fichiers
  donnerait huit vérités à tenir d'accord, et la neuvième serait fausse.
- **Le side se joint par `id`.** C'est ce que l'id opaque est fait pour faire : renommer une
  clé ou re-ranger une entrée ne doit pas casser huit traductions. `key` et le texte source
  sont **échoués** dans le side à côté de chaque entrée, pour qu'un humain puisse le lire et
  le diffuser — mais ils sont en lecture seule et l'éditeur les recale à chaque écriture. Ce
  n'est pas un second identifiant : c'est une annotation, et en cas de désaccord c'est le
  maître qui a raison, jamais l'inverse.
- **Une entrée absente d'un side n'est pas une chaîne vide, c'est la SOURCE.** Un trou de
  traduction doit se voir comme un texte de la mauvaise langue — pas comme un écran blanc que
  personne ne saura interpréter sur console. Le build compte les trous et les nomme.
- **Une langue n'a pas de police : elle a éventuellement un REMPLACEMENT.** EN, FR, DE, ES
  partagent la même planche latine — seuls les glyphes accentués changent, et le
  sous-ensemble par scène les traite déjà un par un. Seul un système d'écriture différent
  (JA, RU, EL) demande une autre planche. Déclarer une police par langue obligerait à
  dupliquer la même planche quatre fois pour rien.
- **`font_de.fnt` est une PRATICITÉ D'IMPORT, jamais une règle.** Le suffixe pré-remplit la
  déclaration quand on ajoute une langue ; ce qui lie une police à une langue reste la
  déclaration explicite du projet. Déduire une liaison d'un suffixe de nom, c'est de la magie
  non vérifiable qui casse au premier renommage — et ça contredit `<asset>_name`, la règle du
  graphe de dépendances.
- **Une scène ne change jamais de police selon la langue.** Elle nomme `dialog` ; c'est la
  RÉSOLUTION de ce nom qui dépend de la langue, par une table de remap. Sans ça, il faudrait
  réécrire chaque `text.set_font` et chaque zone de mise en page, dans quarante scènes, pour
  chaque langue ajoutée.
- **PNG et `.fnt` seulement** — c'est déjà le cas (`font_import.py` refuse même le BMFont
  binaire), mais ça mérite d'être écrit comme une décision et pas comme un état de fait : une
  police est un **jeu fini d'images de glyphes**. C'est exactement ce qui rend
  `scene_codepoints()` calculable, donc le sous-ensemble par scène possible, donc le japonais
  envisageable. Un TTF rendu au build ne donnerait pas ça.
- **Le garde-fou VRAM se dimensionne sur la PIRE langue.** La ROM contient N sous-ensembles
  de glyphes par scène, la VRAM n'en tient qu'un. Un contrôle fait sur la seule langue source
  laisserait passer un projet qui explose en allemand — c'est-à-dire au moment exact où il
  est trop tard pour le corriger.
- **Les littéraux de script deviennent un avertissement NOMMÉ.** `text.draw("Bonjour")` était
  un raccourci assumé au prix de la traduction (v0.3.2) ; en multilingue, c'est un trou par
  construction. Le build les liste, avec leur fichier et leur ligne.
- **La langue vit dans la sauvegarde de la v0.5**, et se lit avant la première scène.
- **L'ordre des mots appartient à la traduction, pas au script.** Les marqueurs `$nom` — et
  les positionnels `$1`/`$2` de la [v0.18](#v018--la-valeur-affichée--doù-elle-vient) —
  vivent DANS l'entrée : une langue qui dit « 3/5 PV » dans l'autre sens réordonne ses
  marqueurs chez elle, sans que le script sache qu'elle existe. Rien à prévoir de plus ici,
  mais c'est la raison pour laquelle il ne faut jamais laisser une phrase se composer par
  concaténation dans un script.

#### Ce que ça coûte, en chiffres

La ROM n'est pas la contrainte, et il vaut mieux le savoir avant de dimensionner quoi que ce
soit. Un glyphe est **une tuile 4bpp, 32 octets** : une planche latine complète tient en
3 Ko, et cent mille caractères de dialogue pèsent environ 200 Ko par langue — sur une
cartouche de 16 Mio, huit langues ne se voient pas.

Ce qui coince est la **VRAM par scène**, et seulement pour les écritures non latines. C'est
précisément ce que le sous-ensemble par scène rend praticable : une scène qui affiche deux
cents kanji distincts charge deux cents tuiles, pas une fonte de deux mille.

#### Ouvert

- ~~**Changer de langue en cours de partie.**~~ **Tranché en phase 4 (2026-08-27)** : au prix
  d'un rechargement de la scène courante — l'option du milieu des trois listées ici. `lang.set`
  pose `g_lang` puis force la boucle principale à retraverser la scène ACTIVE comme un vrai
  changement de scène (`g_lang_reload`, consommé au tour suivant, jamais dans `lang_set`
  lui-même — un acteur peut être en train de s'itérer). Le sous-ensemble de glyphes déjà UNI
  sur toutes les langues (décision 4, phase 3.3) rendait ce choix bon marché : aucune tuile de
  police à recharger, seulement les tuiles de texte déjà posées — l'argument qui a tranché
  contre le rechargement complet des zones (plus de code, pour le même résultat) et contre le
  redémarrage (trop cher pour un jeu qui a déjà de l'état).
- **L'écran de choix de la langue et son amorçage.** Afficher « Deutsch / 日本語 » demande les
  glyphes de deux écritures EN MÊME TEMPS, avant qu'aucune langue ne soit choisie : c'est la
  seule scène du jeu qui viole la règle « une langue à la fois ». Solutions possibles — un
  sous-ensemble spécial « endonymes », des noms de langue en latin partout, ou des images.
- **Workflow pour un traducteur sans compétence de développement** : édition directe dans
  l'éditeur, ou export/import type tableur ? Le side joint par id rend l'aller-retour sûr,
  reste à savoir s'il vaut son écran.

**Tranché en phase 2 (2026-08-25)** — « où vit la langue dans l'écran Texte » : le modèle
POEdit, pas les colonnes. La colonne Content montre toujours la langue ACTIVE (source si rien
n'est traduit — même repli que `text_content()`, jamais une cellule vide qui mentirait sur ce
que le joueur verra) ; l'atelier montre la source en lecture seule au-dessus du champ
éditable. Choisi contre les colonnes parce que la table sert déjà trois autres colonnes
(rangement × 3, clé, usages) — leur ajouter une colonne par langue meurt après trois langues,
quand le modèle POEdit encaisse dix langues sans changer de forme. La longueur reste
vérifiable : c'est l'aperçu écran de l'atelier qui la montre, pas une colonne côte à côte.

**Revu le même jour** : le sélecteur ne vit plus dans la table (« Editing: ‹langue› »), mais
en ONGLETS dans l'atelier — un par langue déclarée, source comprise, caché entier tant qu'il
n'y a rien à choisir. Deux raisons : la langue est un contexte D'ÉDITION, pas un filtre
d'affichage, elle a donc sa place là où on écrit ; et une traduction porte du balisage comme
la source (`[speed=6]`, `[icon=…]`, `$variable`) — un onglet « Translations » qui listait
plutôt que d'ouvrir le même atelier complet (barre de balisage, coloration, aperçu écran)
aurait rendu une traduction moins outillée que la source, alors que c'est elle qui doit
tenir dans la même zone à l'écran. Chaque onglet de traduction porte son compte de trous en
badge (`Deutsch (12)`) — le compte affiché dans la bande de langue de la table a disparu avec
elle. Le fil d'Ariane des trois niveaux de rangement (`ARENA › arena_ui › element1`) a suivi
le même geste : trois pastilles éditables en place plutôt que trois champs nus, même langage
visuel que la colonne Category de la table.

#### Le plan, en cinq phases

Chacune laisse le projet **buildable** — aucune ne demande de finir la suivante pour livrer
une ROM qui marche.

| # | Phase | Ce qu'elle pose | Ce qui ne change pas encore |
| --- | --- | --- | --- |
| 1 | **Déclarer** — *livrée* | Les langues dans les paramètres du projet : code, nom, police de remplacement facultative. Création du side vide. | Le build ignore tout : une seule langue est émise. |
| 2 | **Traduire** — *livrée* | Lecture/écriture des sides, la colonne de langue dans la table, le statut « traduit / manquant / déborde », le compte de trous. | Le build, toujours. On peut traduire tout un jeu avant qu'une ligne de C bouge. |
| 3 | **Émettre** — *livrée* | La dimension langue dans `g_texts`, le remap de police, le sous-ensemble de glyphes par (scène, langue), et le garde-fou VRAM au pire cas. | La ROM contient N langues mais n'en montre qu'une : `g_lang` est une constante. |
| 4 | **Choisir** — *livrée* | `lang.set`/`lang.get`, résolus comme `TEXT_*`/`SCENE_IDX_*` (`LANG_<CODE>`, jamais une chaîne au runtime). Rechargement de la scène courante pour rendre le changement visible. | La persistance SRAM (survivre à une coupure de courant) et l'écran de choix lui-même — toujours à la charge du jeu. |
| 5 | **Servir** | L'amorçage du menu de langue, et l'export/import traducteur si la phase 2 montre qu'il manque. | — |

**Ce que la phase 1 a posé** (2026-08-24) : `Language` dans les paramètres du projet (code,
nom, remplacements de police), la carte « Languages » de l'inspecteur de projet, et
`core/project_langs.py` — l'I/O des sides, le repli en un point unique (`text_content`) et
les deux règles qui décident du sort d'un travail humain : **une traduction orpheline est
conservée**, et **un side vide et non déclaré est le seul qu'on jette**. Neuf tests dans
`tests/test_translations.py`.

**Ce que la phase 2 a posé** (2026-08-25) : le sélecteur « Editing » dans la table, la colonne
Status (Translated/Missing) et le chip de filtre assorti, le compte de trous dans la bande de
langue, la référence source en lecture seule dans l'atelier. `SetTranslationCmd`
(`text_commands.py`) écrit dans le side, symétrique de `SetFieldCmd` pour la source — les deux
FUSIONNENT leurs frappes consécutives, donc un signal par GESTE (déclarer/renommer/retirer
une langue) et non une liste repoussée en bloc, sans quoi l'annulation ramènerait le projet à
zéro langue. `_check_text_overflow` (`validator.py`) mesure désormais TOUTES les langues
déclarées, pas seulement la source — un trou fermé qui existait avant ce chantier : une
traduction plus longue débordait une zone en silence, la troncature ne se découvrant qu'en
jouant la ROM dans cette langue. Piège réel rencontré et corrigé : le champ éditable ne doit
JAMAIS se pré-remplir avec la source en repli — seule la table et le build ont le droit de
replier, le champ que le traducteur REMPLIT doit rester vide tant que rien n'est écrit, sans
quoi la moindre retouche commite toute la source comme si elle était traduite. Cinq tests
dans `tests/test_text_overflow_langs.py`.

L'ordre n'est pas négociable sur un point : **la phase 3 ne s'ouvre pas avant que la phase 2
ait tourné sur un vrai jeu traduit.** C'est elle qui dira ce que pèsent réellement les
glyphes d'une langue, et le garde-fou VRAM se conçoit avec ces chiffres-là, pas avec des
suppositions.

#### Phase 3 — Émettre : le design (2026-08-27)

Condition d'ouverture remplie : le projet démo **Fonts&Texts** porte 8 entrées traduites en
FR et JAP, table complète — c'est lui qui sert de banc pour les chiffres ci-dessous une fois
l'étape 3 codée.

**Décisions verrouillées :**

1. **`g_texts` gagne une dimension, `g_lang` reste une CONSTANTE de build.**
   `g_texts[LANG_COUNT][N_TEXTES]` ; chaque `g_text_<lang>_<i>` est un tableau de codepoints
   séparé, le balisage résolu par langue exactement comme aujourd'hui pour la source.
   `g_lang` est un `#define` qui vaut l'index de la langue SOURCE (0) tant que rien ne le
   change — donc un projet qui n'ouvre pas la phase 4 compile et joue EXACTEMENT comme
   aujourd'hui, seul le poids ROM change (les N-1 langues supplémentaires voyagent dans la
   cartouche, invisibles). Pas de champ projet « langue de build » ajouté maintenant : ce
   serait une notion utile seulement en attendant la phase 4, à retirer aussitôt après.
2. **L'ordre des langues est fixe et dérivé des settings** : index 0 = `source_lang`, puis
   `settings.languages` dans l'ordre déclaré. Le même ordre partout — `g_texts`,
   `g_lang_font`, et les futurs sélecteurs de la phase 4 — une seule vérité, comme le reste
   du projet.
3. **Le remap de police lit `Language.fonts`**, posé dès la phase 1
   ([models/settings.py](editor/core/models/settings.py)) et jamais lu par le build jusqu'ici.
   `g_lang_font[lang][police]` vaut l'index de la police de remplacement si `Language.fonts`
   en déclare une pour cette police, sinon l'index de la police elle-même — « pas de
   remplacement » n'est donc pas un cas spécial à tester au runtime, l'indirection est
   toujours valide. `text_set_font(FONT)` résout d'abord `FONT`, puis applique le remap : le
   script continue de nommer `dialog`, jamais une variante par langue.
4. **`scene_codepoints` prend un paramètre langue**, calculé pour CHAQUE langue déclarée
   (source comprise) plutôt qu'une fois. Le sous-ensemble ÉMIS dans la ROM pour une scène est
   l'UNION de tous les sous-ensembles par langue — c'est ce qui permettra à la phase 4 de
   recharger une scène dans une autre langue sans reconstruire la police en VRAM. La
   RÉSERVATION, elle, reste dimensionnée sur la langue ACTIVE (`g_lang`, donc la source
   aujourd'hui) : charger l'union en permanence gâcherait de la VRAM pour des glyphes
   qu'aucune langue affichée aujourd'hui n'utilise.
5. **Le garde-fou VRAM (`validator.py`) teste les N langues, pas seulement la source.** Il
   recalcule le budget d'une scène avec le sous-ensemble de CHAQUE langue (même fonction que
   la réservation, argument différent) et remonte la PIRE, nommée — « la scène X déborde en
   allemand (312 tuiles > 256) » même si la source tient. Sans ça, le problème n'apparaît que
   lorsque quelqu'un teste la ROM dans cette langue-là, au moment le plus cher pour le
   corriger.
6. **Les littéraux de script deviennent un avertissement NOMMÉ**, comme annoncé plus haut :
   `text.draw("Bonjour")` reste compilable (une entrée anonyme, v0.3.2), mais le build liste
   désormais chaque occurrence avec fichier et ligne — un littéral ne peut être que dans la
   langue source, donc un trou de traduction garanti dès qu'une deuxième langue est déclarée.
7. **Rien ne change pour un projet monolingue.** `LANG_COUNT == 1` (aucune langue déclarée) :
   le code émis est identique à aujourd'hui, `g_texts[1][N]` compile comme `g_texts[N]` d'hier
   — pas de branche spéciale à maintenir pour ce cas, juste une dimension qui vaut 1.

**Ordre d'implémentation** (chaque étape laisse le projet buildable) :

| # | Étape | Ce qu'elle change | Ce qu'elle NE change PAS |
| --- | --- | --- | --- |
| 3.1 | `g_texts[lang][i]` — *livrée* | `font_emit.emit_texts_c` lit `project.text_content(t, code)` par langue déclarée. `g_lang` posé en `extern const int`, toujours 0. | Le rendu : un seul texte lu, celui d'aujourd'hui. |
| 3.2 | Remap de police — *livrée* | `g_lang_font`, lu par `text_set_font` au lieu de l'index direct. | Tout projet dont `Language.fonts` est vide (cas courant EN/FR/DE/ES **et** une police déjà multilingue, cf. Fonts&Texts) — table = identité. |
| 3.3 | `scene_codepoints` par langue + union émise — *livrée* | `scene_codepoints_union` — la police d'une scène grossit dès qu'une traduction ajoute des caractères. | La réservation VRAM (toujours la langue active, `scene_codepoints` sans `code`). |
| 3.4 | Garde-fou VRAM multi-langue — *livrée* | `validator._check_vram_lang_budget` : `scene_text_reservation(p, scene, code)` rejouée par langue, avertit sur la PIRE si elle charge plus de tuiles que la source. | La réservation réelle (toujours la langue active) — c'est un avertissement, `g_lang` reste 0. |
| 3.5 | Avertissement nommé sur les littéraux — *livrée* | `validator._check_literal_texts` : un `text.draw("...")` liste fichier + ligne, dès qu'une langue est déclarée. | Le comportement runtime (toujours une entrée anonyme valide) ; silencieux en monolingue. |

**Ce que 3.1-3.3 ont posé** (2026-08-27) : les trois validées par un build ROM réel de bout en
bout (Fonts&Texts ET Pong, `build/` supprimé avant, comme il faut) — pas seulement des tests
unitaires. 13 tests neufs (`test_text_lang_emit.py`, `test_lang_font_remap.py`,
`test_scene_codepoints_lang.py`). Piège réel rencontré : le seul projet démo disponible
(Fonts&Texts) utilise UNE police déjà nativement multilingue (`ark-pixel-10px-monospaced-ja`,
latin + japonais dans la même planche) — elle ne peut donc prouver ni le remap de police (3.2,
toujours identité chez elle) ni l'élargissement du sous-ensemble par l'union (3.3, cette police
est composée donc toujours chargée ENTIÈRE, jamais en sous-ensemble). Les deux chemins sont
couverts par les tests unitaires sur des cas synthétiques plutôt que par ce projet.

**Ce que 3.4-3.5 ont posé** (2026-08-27) : les deux garde-fous vivent dans `validator.py`,
même sévérité qu'`_check_text_overflow` (avertissement — `ctx.warn`, jamais bloquant : rien
n'est cassé dans le build d'aujourd'hui, `g_lang` reste 0) et silencieux en projet monolingue,
même contrat. `scene_text_reservation` prend désormais un `code` optionnel, rejoué une fois par
langue par le garde-fou 3.4 SANS toucher au calcul réel (`_apply_vram_layout`/
`_scene_tile_budgets` continuent de l'appeler sans argument). 7 tests neufs
(`test_vram_lang_budget.py`, `test_literal_texts_lang.py`) — Fonts&Texts et Pong compilent
toujours, sans avertissement nouveau (la police composée du premier ne charge aucun glyphe donc
n'a rien à déborder ; le second n'a que des traductions vides). **Les 5 étapes de la phase 3 sont
livrées.**

**Fait nouveau pour l'« Ouvert » plus haut** — *changer de langue en cours de partie* : comme
le sous-ensemble de glyphes ÉMIS est déjà l'union de toutes les langues (décision 4), aucun
changement de langue n'aura JAMAIS à recharger de tuiles de police, quelle que soit l'option
choisie en phase 4 — le coût restant est celui du TEXTE déjà posé. **Tranché en phase 4** (voir
plus bas) : le rechargement de la scène courante, pas le « à chaud » — plus simple à écrire
pour un coût déjà bas grâce à ce fait-là.

## Ce que la phase 4 a posé (2026-08-27)

`lang.set(code)` / `lang.get()` — l'API tient dans ces deux appels, comme prévu : la police
effective (3.2) et le sous-ensemble de glyphes (3.3) étaient déjà prêts pour n'importe quelle
langue, `g_lang` n'avait donc rien d'autre à faire que changer.

**Décisions verrouillées :**

- **`g_lang` cesse d'être une constante de build.** `int g_lang` (non `const`), écrit par
  `lang_set`. Aucun projet qui n'appelle jamais `lang.set` n'en est affecté — le comportement
  par défaut reste `g_lang = 0`.
- **Rendre le changement VISIBLE recharge la scène ACTIVE**, l'option du milieu des trois
  listées plus haut (ni redémarrage du jeu, ni réécriture zone par zone) : `scene.switch()` vers
  la scène courante ne faisant RIEN aujourd'hui (`g_next_scene != g_current_scene` gardait déjà
  un self-switch), `lang_set` pose un drapeau (`g_lang_reload`) que la boucle principale
  consomme au tour suivant en forçant `g_current_scene = -1` avant son garde-fou existant —
  zéro code de réinitialisation dupliqué, la scène repart EXACTEMENT comme un vrai changement de
  scène (acteurs, caméra, musique compris). Contrepartie assumée et documentée : l'état de la
  scène (dialogue en cours, position d'un acteur) repart à zéro, comme n'importe quelle
  transition de scène.
- **Jamais dans `lang_set` lui-même.** Le drapeau, pas un appel direct : `lang_set` peut être
  invoqué au milieu d'un `on_update`, pendant qu'un acteur s'itère — même précaution que
  `scene_switch`, qui ne bascule jamais avant le début de la frame suivante.
- **`lang.set("fr")` résout en `LANG_FR` au build**, exactement comme `scene.switch("Arena")`
  résout en `SCENE_IDX_ARENA` — jamais une chaîne comparée au runtime. Un code non déclaré
  refuse de compiler, une liste vide (projet monolingue) refuse tout code : aucun cas spécial,
  la même mécanique que `DOMAIN_SCENE`.
- **`lang_set`/`lang_get` ne sont PAS `static inline`**, contrairement à `scene_switch` — piège
  réel rencontré : `main.c` inclut à la fois `gba_engine.h` et `actor_api_static.h`, qui le
  redéclare pour les unités de compilation d'acteur/scène ; deux corps `static inline` du même
  nom dans la même unité de traduction refusent de compiler. Même découpe que `text_set_font` :
  prototype des deux côtés, IMPLÉMENTATION UNIQUE sous `GBA_ENGINE_IMPL`.

**Validé par build réel** (Fonts&Texts ET Pong, `build/` supprimé avant) : `LangageSelector.lua`
appelle désormais `lang.set(LANG_EN/LANG_JAP/LANG_FR)` selon l'item choisi — inspection du C
généré, `lang_set(LANG_FR)` littéral, aucune chaîne. 8 tests neufs (`test_lang_api.py`) côté
checker/codegen ; le rechargement lui-même (`g_lang_reload`, la boucle principale) n'est vérifié
que par le build réel — aucun harnais Python ne rejoue la boucle GBA.

**Reste ouvert** (hors phase 4, non retranché) : la persistance SRAM (le choix de langue ne
survit pas à l'extinction — `save.write`/`save.load` existent déjà, phase 5 ou un chantier
séparé les y branchera) et l'écran de choix de langue lui-même (« Deutsch / 日本語 » simultanés,
cf. l'« Ouvert » plus haut) restent à la charge du jeu.

## Garde-fou : couverture de police par langue (2026-08-27)

Trouvé en JOUANT la démo Fonts&Texts, pas en la lisant : une traduction japonaise citait un
kanji (友) absent des 3831 glyphes de la police du projet. Le moteur fait exactement ce que la
doc dit — `text_glyph_slot` rend -1, le caractère disparaît de l'affichage, sans un mot au
build (cf. `gba_engine.h`). Aucun garde-fou existant ne couvrait ce cas : `_check_text_overflow`
mesure la LARGEUR d'un texte contre sa zone, pas son EXISTENCE dans la police.

`validator._check_font_coverage` comble le trou, même reprise que `_check_text_overflow` :
DEUX sources (scripts + textes authorés), TOUTES les langues déclarées (`_text_variants`),
avertissement et non erreur. Une différence assumée avec les deux autres garde-fous de la
phase 3 (VRAM, littéraux) : ceux-là sont silencieux en projet monolingue, celui-ci vérifie
la SOURCE même sans aucune langue déclarée — un caractère manquant est un bug de saisie
qu'aucune traduction n'a besoin d'exister pour révéler.

**Décision verrouillée** : la police jugée est l'EFFECTIVE, pas la déclarée — le remap par
langue (`Language.fonts`, décision 3.2) peut substituer une autre planche à celle que la zone
nomme, et c'est celle-là que `text_set_font` charge réellement une fois la langue active. Juger
la police déclarée aurait produit de faux positifs sur tout projet qui utilise le remap
justement pour ce genre de cas (un système d'écriture différent).

6 tests neufs (`test_font_coverage_lang.py`), dont un qui prouve que le remap éteint
l'avertissement quand il couvre vraiment le caractère. Vérifié sur Fonts&Texts (0 avertissement
après correction de la traduction) et Pong (aucune régression, les deux avertissements restants
sont ceux, déjà connus, de `_check_literal_texts`).

---

## v0.10 — Distribution élargie

Réactivation de la construction Linux (en pause, en attendant un test sur une vraie
distribution).

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût récurrent — « Linux seul » est
  une option valable si le coût ne se justifie pas.

---

## v0.11 — Traduction de l'interface de l'éditeur — **EN COURS**

Complètement indépendant du runtime GBA. Déplaçable librement dans l'ordre : peut être fait
en parallèle de n'importe quelle autre version.

### D'où vient la question (2026-08-25)

Le jalon ne s'est pas ouvert par la traduction, mais par **le contenu informatif de
l'interface**. Un inspecteur disait déjà beaucoup de choses — l'empreinte d'une zone de
texte, un recouvrement de surface, une palette que le build va écarter — et les disait
**chacune à sa façon** : un `W.hint()` dont l'appelant choisissait la couleur à la main,
un `setStyleSheet(f"color:{C.ACCENT_YLW}")` recalculé à chaque rafraîchissement, des
phrases assemblées par concaténation (`"s" if n > 1`, `"frame(s)"`), et deux langues
mélangées dans le même écran.

Trois défauts, dont un seul se voyait :

- **Rien ne distinguait un constat d'un risque.** Le jaune était posé par jugement de
  l'appelant, pas par la nature du message. Deux messages de gravité opposée pouvaient
  sortir de la même ligne de code avec la même couleur.
- **Rien ne disait à quel point un message était optionnel.** Un avertissement expliquant
  une contrainte matérielle avait été retiré parce qu'il était « trop précis pour l'interface
  d'un IDE » — ce qui était juste, mais laissait sans place les explications qu'on veut
  garder pour qui débute.
- **Aucun texte n'était traduisible.** Pas un `tr()` dans le dépôt, 103 fichiers d'interface,
  et des phrases construites en Python à l'exécution — c'est-à-dire la forme exacte qu'une
  traduction ne peut pas reprendre, l'ordre des mots n'étant pas le même d'une langue à
  l'autre.

Le premier temps de ce jalon répond aux trois d'un coup : **un gabarit à trois niveaux**, et
**les textes sortis du code**.

### Le gabarit — trois niveaux, quatre tons

Le NIVEAU dit à quel point le message s'impose, le TON dit ce qu'il annonce. Le niveau est
choisi par l'appelant (c'est une question de place dans l'écran), le ton est écrit dans le
catalogue (c'est une propriété du message). Deux sources de vérité distinctes, aucune
redondance entre elles.

| Niveau | Appel | Forme | Se tait quand |
| --- | --- | --- | --- |
| **1** | `note(layout, clé="")` | une ligne sans cadre, sous un `W.section()`, en sous-brillance | son texte est vide |
| **2** | `notice(clé, ancre, layout)` | **la gravité tranche** : `info`/`accent` → bulle au survol de l'ancre ; `build`/`render` → encadré permanent | son texte est vide |
| **3** | `tip(clé, layout)` | encadré à ampoule, affiché tout de suite | les astuces sont coupées dans les réglages du projet |

**Le niveau 1 est le seul dont la clé peut changer d'un rafraîchissement à l'autre** — c'est
sa raison d'être : une ligne d'inspecteur dit tantôt une empreinte, tantôt pourquoi elle est
vide. D'où sa signature, qui met le LIEU d'abord et la clé en second, facultative. Aux deux
autres niveaux la clé est fixe : au niveau 2 parce que c'est elle qui décide de la forme, au
niveau 3 parce qu'une astuce explique une notion et n'a donc aucun état à attendre.

| Ton | Couleur | Ce qu'il annonce |
| --- | --- | --- |
| `info` | `TEXT_MUTED` | un constat — une empreinte, un compte, une provenance |
| `accent` | `ACCENT` périwinkle | un complément qui renvoie à un autre écran ou à une notion de l'éditeur |
| `build` | `ACCENT_YLW` + ⚠ | ça compile, mais le build va écarter ou rogner ce qui est là |
| `render` | `ACCENT_YLW` + 👁 | ça compile et ça s'émet, mais la console n'affichera pas ce qui est authoré |

### Décisions verrouillées

- **Le rouge n'entre pas dans le gabarit.** Une seule couleur d'alerte, deux icônes : `build`
  et `render` sont tous deux jaunes, et c'est la FORME de l'icône qui les distingue — la même
  règle que les familles d'icônes (« la forme, pas la teinte »). `ACCENT_RED` reste ce qu'il
  est depuis le thème : les erreurs BLOQUANTES du validateur et la suppression. Un inspecteur
  qui se met à parler rouge banalise la seule couleur qui devait arrêter quelqu'un.
- **Une entrée peut porter un `code`** — l'expression Lua que le champ MIROITE
  (`self.collision.solid`). Elle s'affiche en tête de l'infobulle et **ne part jamais dans un
  side** : une expression d'API ne se traduit pas, la traduire casserait le script qu'elle
  donne à recopier. C'est ce qui a permis d'absorber les deux mini-catalogues `_TOOLTIPS`
  qui existaient déjà — voir plus bas.
- **Le niveau 2 n'a qu'un appel, et la forme en découle.** `notice(clé, ancre, layout)` :
  un message de niveau 2 est toujours À PROPOS de quelque chose (l'ancre) et vit toujours
  QUELQUE PART (la carte). S'il n'a pas d'ancre, c'est qu'il parle du panneau entier — donc
  ce n'est pas un niveau 2, c'est un niveau 1 ou un niveau 3. La règle tranche les deux à la
  fois : où le poser, et de quel niveau il relève.
- **Le niveau 3 est le seul endroit où l'éditeur a le droit d'EXPLIQUER.** Les niveaux 1 et 2
  restent tenus par la règle qui avait fait retirer l'avertissement de centrage : on dit ce
  qui est ACTIONNABLE et probablement non voulu, on ne commente pas le matériel. Une
  explication de concept, une astuce d'optimisation, un rappel de règle : niveau 3, donc
  coupable d'un interrupteur. C'est ce qui la rend acceptable — elle ne peut pas noyer les
  deux autres niveaux puisqu'elle n'est pas obligatoire.
- **L'interrupteur vit dans les réglages de l'APPLICATION**
  (`core/interface_preferences.py`, catégorie *Interface*), pas dans ceux du projet. Il y a
  d'abord été posé côté projet, puis déplacé le même jour, pour deux raisons dont la seconde
  est la vraie : `project.json` est versionné, donc couper les astuces les coupait pour toute
  l'équipe — y compris pour celui qui arrive et à qui elles s'adressent ; et surtout, un
  réglage de projet passe par `SetFieldCmd`, donc **annuler une édition de scène pouvait
  rebasculer une préférence de machine**. Un réglage d'application n'entre pas dans
  l'historique d'un projet.
- **Le partage n'est pas un risque, c'est une portée.** « Mise en page partagée par 3
  scènes » et « entrée montrée par 2 autres éléments » étaient JAUNES ; ils passent en
  périwinkle, sur leur propre ligne au lieu de teinter la ligne du nom. Rien n'est écarté,
  rien ne s'affiche mal — c'est un fait sur l'étendue d'une modification, et c'est
  exactement ce que le périwinkle désigne partout ailleurs. Le jaune y gagne : il ne reste
  qu'à ce que le build ou l'écran feront vraiment.
- **Un texte n'est plus écrit dans le code d'interface.** Il vit dans
  `ui/common/notices/notices.json`, cité par une clé. Le Python passe les VALEURS
  (`show_text(other=…, n=…)`), jamais des morceaux de phrase — c'est précisément la
  concaténation qui rend une phrase intraduisible, l'ordre des mots n'étant pas universel.
- **Le catalogue reprend la grammaire de la table de textes du JEU (v0.9), à une exception
  près.** Un maître `notices.json` porte la structure (clé, ton, texte source), un side
  `notices_<code>.json` ne porte que la traduction, jointe par clé ; **une entrée absente vaut
  la SOURCE, jamais une chaîne vide**. L'exception : ici la clé EST la jointure, là où le jeu
  utilise un id opaque. La raison est que la clé est écrite dans du Python versionné — un id
  opaque y serait illisible, et la renommer est un changement de code qui touche le side dans
  le même commit, ce qu'un renommage fait par l'utilisateur ne pourrait pas garantir.
- **Le pluriel est déclaré, pas bricolé.** Une entrée peut porter `one`/`other` au lieu de
  `text` ; c'est l'argument nommé `n` qui choisit. Les `"s" if n > 1` et les `frame(s)` qui
  traînaient dans les inspecteurs disparaissent — ils n'étaient traduisibles dans aucune
  langue, y compris en français (« 1 rangée » / « 2 rangées »). Une langue à pluriel plus
  riche que deux formes demandera une règle par langue : le format peut l'accueillir, la
  question ne se pose pas avant d'avoir cette langue.
- **Une phrase composée l'est par CLÉS, pas par fragments.** Le coût d'une image est une
  entrée, et le morceau « où ça coûte » en est une autre, injectée par `text()`. Chaque
  morceau reste une phrase entière pour le traducteur.
- **Le catalogue est vérifié par la CI, dans les deux sens.** `check_architecture.py` relit
  l'AST de tout `editor/` : toute clé citée doit exister, toute entrée du catalogue doit être
  citée. Sans ce contrôle, l'extraction se défait toute seule — une clé mal tapée donne un
  message vide, et un message vide ne se plaint jamais.

### Ce que ça touche

| Fichier | Nature |
| --- | --- |
| [notice.py](editor/ui/common/notice.py) | **nouveau** — les trois niveaux, les quatre tons, le catalogue |
| [notices.json](editor/ui/common/notices/notices.json) | **nouveau** — le catalogue source (langue `en`) |
| [theme.py](editor/ui/common/theme.py) | `QSS.notice_box(tone)` — l'encadré, une seule définition |
| [icons.py](editor/ui/common/icons.py) | `info`, `tip` (⚠ et l'œil existaient) |
| [interface_preferences.py](editor/core/interface_preferences.py) | **nouveau** — les réglages d'affichage, un par machine |
| [settings_dialog.py](editor/ui/common/settings_dialog.py) | catégorie **Interface** — l'interrupteur des astuces |
| [toolchain.py](editor/core/toolchain.py) | `_config_dir` → `config_dir` : quatre modules y posent leur fichier |
| [project_settings_dialog.py](editor/ui/scene_manager/inspectors/project_settings_dialog.py) | l'astuce des Collisions |
| [ui_inspector.py](editor/ui/scene_manager/inspectors/ui_inspector.py) | 30 messages extraits, plus un seul `setStyleSheet` de couleur |
| [actor_inspector.py](editor/ui/scene_manager/inspectors/actor_inspector.py) + [collision.py](editor/ui/scene_manager/inspectors/component_editors/collision.py) | les deux `_TOOLTIPS`/`_tip()` locaux **supprimés** |
| [ui_region.py](editor/core/models/ui_region.py) | `forced_target_reason()` **supprimée** — de la prose d'interface dans `core/models` |
| [data_inspector_panel.py](editor/ui/data_editor/data_inspector_panel.py) | le dernier `W.hint` statique |
| [project.py](editor/core/project.py) | `show_tips` n'y est plus lu — clé ignorée, sans migration |
| [nuitka_build.py](packaging/nuitka_build.py) | le catalogue embarqué dans la distribution |
| [widgets.py](editor/ui/common/widgets.py) | `W.hint()` **supprimé** — il était le mécanisme d'avant |
| [check_architecture.py](tools/check_architecture.py) | 7e contrôle — catalogue ↔ code |

### Ce que le chantier a trouvé en chemin

- **Deux mini-catalogues d'infobulles à clés existaient déjà**, dupliqués : un `_TOOLTIPS` +
  `_tip()` dans `actor_inspector.py`, un autre dans `component_editors/collision.py`, avec la
  même mécanique recopiée et le `ACCENT_BLU` déprécié en dur. C'était le niveau 2 avant
  l'heure, en français, et sans personne pour le savoir. Les onze messages rejoignent le
  catalogue, les deux helpers disparaissent.
- **Quatre de ces appels citaient une clé absente de leur propre dictionnaire**
  (`actor.rotation`, `actor.scale`, `actor.obj_mode`, `actor.visible`) : `_tip()` retournait
  en silence, donc ces quatre champs n'ont JAMAIS eu d'infobulle. Les appels morts sont
  retirés plutôt que remplis d'un contenu inventé — s'il faut les écrire, c'est une décision
  d'auteur, pas un effet de bord d'extraction. C'est ce défaut-là qui a fait écrire le
  contrôle de catalogue, et c'est lui qui l'aurait vu.
- **`forced_target_reason()` fabriquait de la prose d'interface dans `core/models`** — deux
  phrases françaises destinées « à être affichées telles quelles », dans la couche qui n'a
  pas le droit de connaître l'interface. Un seul appelant. Les deux raisons deviennent deux
  entrées du catalogue et la fonction disparaît.
- **Trois messages étaient restés en français** dans un écran déjà migré à l'anglais (la
  carte Liste, le libellé du mode Solid). Ils sont traduits au passage, comme le veut la
  règle de migration écran par écran.

### Ouvert

- **La sélection de langue n'existe pas encore.** `notice.set_language(code)` est écrit et
  n'a aucun appelant : c'est la seule pièce délibérément inemployée du chantier, et le premier
  commit de la suite du jalon (un réglage d'application, pas de projet — l'interface est celle
  de l'éditeur, pas du jeu). Tant qu'il n'est pas appelé, le maître est la seule source.
- **Le reste de l'interface n'est pas extrait** : libellés, titres, états vides, menus, et les
  202 `setToolTip` posés à la main. Le catalogue est fait pour les accueillir sans déménager,
  mais les notices sont ce qui se traduit le moins bien et se lit le plus mal — d'où l'ordre.
  Reste à trancher si les libellés partagent le catalogue des notices ou vivent à côté : un
  libellé n'a ni ton ni niveau.
- **Les messages du validateur** (`core/validator.py`, ~40 phrases) sont l'autre corpus déjà
  centralisé, et le plus proche : ils ont une gravité, et le rouge y a un sens. Ils partiront
  probablement dans le même catalogue avec un ton `error` que le gabarit d'inspecteur n'offre
  pas — à décider quand ce sera leur tour, pas avant.
- **Une astuce n'est pas dismissible individuellement.** L'interrupteur est global. Un « ne
  plus montrer celle-ci » demanderait une liste de clés vues dans le projet ; personne n'a
  encore dit que c'était le besoin.

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

### La référence rendue, et pourquoi elle tient en UN temps

La forme demandée le 2026-08-26 était en deux temps — un template obtenu, puis instancié :

```lua
local template = prefab.get("Bullet")     -- n'existera pas
local inst     = prefab.spawn(template)   -- n'existera pas
```

Elle ne peut pas exister, et la raison n'est pas la même que celle du spawn dynamique
ci-dessus. **`spawn_<Prefab>` est une fonction C distincte par prefab**, écrite au build avec
la plage du pool, la banque de palette, les boîtes de collision et les enfants du template
cuits dedans (`main_gen.py:549`). Un template tenu dans une variable devrait choisir la
fonction à l'exécution : il faudrait une table de dispatch prefab → fonction, donc rendre
adressables des symboles que le build sait résoudre gratuitement. Le codegen l'a d'ailleurs
toujours refusé — il exige le littéral et le dit (`codegen.py:1815`).

C'est la règle des trois provenances, déjà écrite plus haut : `module.get("Nom")` rend une
chose **nommée du projet**, et son coût est *un `#define`*. Un prefab n'est pas une chose qu'on
obtient puis qu'on instancie — **le nom du prefab EST l'argument du spawn**. Les deux temps
n'achètent rien qu'un temps ne donne déjà.

Ce que l'auteur voulait vraiment — *tenir l'instance et la piloter* — est exactement la
décision verrouillée ci-dessus, en un temps :

```lua
local inst = actor.spawn("Bullet", vec2(116, 76))
if inst ~= nil then          -- le pool peut être plein
    inst:move_to(x, y)
end
```

**La référence est un `Actor*`, pas un indice de slot.** C'est le point à ne pas rater : le
langage sait déjà tenir un acteur dans une variable — `get_actor("PADDLE")` porte `ret="actor"`
et le codegen en fait un `Actor*` (`codegen.py:1194`), et `local bras = self.bras` fait pareil
depuis la v0.23. Rendre un `int` obligerait à écrire `&g_actors[i]` à chaque appel : **deux
représentations d'un acteur dans le même langage**, pour la même chose. Donc :

- `REF_ACTOR = "actor"` entre dans `REF_TYPES`, et `C_REF_TYPES["actor"] = "Actor*"`
  (`api.py:56`, `expr_types.py:155`) — le mécanisme générique des références, celui de `sfx`.
- `spawn_<Prefab>` rend `Actor*` au lieu de `int` (`main_gen.py:549`, `headers.py:298`) ;
  `NULL` remplace `-1`. `nil` vaut déjà `0` dans le C émis, le test s'écrit donc en Lua.
- Le cas particulier `is_actor_ref` du codegen (`codegen.py:1174-1187`) **disparaît** : il
  reconnaît `get_actor` par son nom alors que `ret="actor"` le dit déjà. Une fois `"actor"`
  dans `REF_TYPES`, `infer_ref_type` le couvre — un chemin au lieu de deux.

> **Incohérence à corriger au passage** : `api.py:489` déclare `actor.spawn` avec `ret="void"`,
> pendant que `api_reference.json:634` documente « retourne l'index du slot ou -1 ». Les deux
> sont faux après ce chantier, et ils se contredisent déjà aujourd'hui.

### Ce que l'écran Scene doit montrer

C'est la question qui a ouvert ce chantier : *un script déclare un spawn, et rien dans l'écran
de scène ne le dit.* Elle a une réponse simple, parce que le nom du prefab est un **littéral
obligatoire** — donc lisible statiquement, sans exécuter quoi que ce soit.

Le lien existe déjà dans les deux sens, mais aucun ne passe par le spawn :
`PrefabUsesInspector` compare `actor.prefab_name` (les instances **posées** dans la scène) et
`ScriptUsesInspector` compare `component.script` (qui **porte** le script) —
`ui/scene_manager/inspectors/uses_inspectors.py`. Ni l'un ni l'autre ne lit les appels du
script. Il manque donc un troisième lien, et un seul : **qui SPAWNE ce prefab.**

- La source est `refactor.iter_call_sites(DOMAIN_PREFAB)`, qui existe déjà et sert aux
  renommages : `DOMAIN_PREFAB` est précisément la déclaration « cet argument cite un prefab du
  projet » (`api.py:98`). Pas de nouveau parseur, pas de graphe persistant à maintenir — un
  balayage à la demande, comme le reste de `uses_inspectors.py`.
- `PrefabUsesInspector` gagne une section « Spawné par », à côté de « Utilisé par ».
- Et c'est **la même lecture** qui alimente le pool de la scène : les prefabs qu'une scène
  spawne réellement sont ceux que ses scripts citent. L'éditeur peut donc *proposer* le pool au
  lieu de le faire deviner — proposer, pas imposer : la taille reste une décision d'auteur.

**À ne pas faire** : lire la table `exports` pour ça. Un `prefab_ref` exposé a été envisagé
puis écarté — un spawn n'est pas un paramètre d'acteur, c'est un appel. La citation est déjà
dans le code, la dupliquer en en-tête créerait une seconde source de vérité qui pourrait
mentir.

### Ce que ça touche

`core/models/scene.py` (le champ change de classe), `headers.py` (les `POOL_*` deviennent
per-scène, et `spawn_X` rend `Actor*`), `main_gen.py` (`_pool_info`, la boucle de spawn, la
signature), `lua_compiler.py` (le dimensionnement de `g_state_*`), `palette_alloc.py`,
`rom_build.py`, `validator.py`, et l'écran Scene, qui doit désormais montrer les pools de la
scène.

Pour la référence rendue : `scripting/api.py` (`REF_ACTOR`, le `ret` de `actor.spawn`),
`scripting/expr_types.py` (`C_REF_TYPES`), `scripting/codegen.py` (le cas `is_actor_ref` qui
tombe), `scripting/api_reference.json` (la fiche, aujourd'hui fausse), et `SCRIPTING.md`.

Pour l'écran : `ui/scene_manager/inspectors/scene_inspector.py` (le widget de budget à deux
champs), `ui/scene_manager/inspectors/uses_inspectors.py` (« Spawné par »), et
`core/validator.py` (l'avertissement « plus d'acteurs posés que de slots réservés »).

### Tranché (2026-08-26) : les scripts se compilent PAR SCÈNE

Des deux sorties envisagées — dimensionner `g_state_<X>[]` sur le maximum du projet, ou
compiler par scène — **c'est la seconde**. On récupère tout : les entrées de `g_actors[]` *et*
l'état de script.

**L'hypothèse qui tombe est plus petite qu'annoncé, et il faut le dire avant de chiffrer le
chantier.** `transpile_all` reçoit déjà `scene` et ses acteurs : **les scripts d'acteur, de
scène et de caméra sont DÉJÀ compilés par scène**. Un seul cas échappe à la règle, et c'est
celui-là qu'on change :

> `compiled_prefabs` (`lua_compiler.py:399`, posé par `rom_build.py:315`) : « la première scène
> les compile tous, les suivantes n'en recompilent aucun ». Le prefab sort en
> `actor_<Prefab>.c`, un fichier pour le projet, avec `pool_size = pf.max_instances` cuit
> dedans. C'est ce `set` de garde qui disparaît — pas une architecture.

Ce que ça impose :

- **Le symbole porte la scène.** `actor_<Scene>_<Prefab>.c`, `<Scene>_<Prefab>_on_update`,
  `spawn_<Scene>_<Prefab>`. Sans ça, deux scènes qui emploient le même prefab donnent deux
  définitions du même symbole, et l'édition de liens refuse.
- **`POOL_<X>_*` devient per-scène**, ce qui est tout l'objet du chantier. `headers.py:63`
  porte encore la justification inverse (« compilé une fois pour le PROJET et ne peut donc pas
  connaître ces bornes autrement ») : ce commentaire devient faux et doit partir avec le code.
- **Le codegen préfixe le spawn.** `_emit_actor_spawn` émet `spawn_{sym}` (`codegen.py:1830`) ;
  il émettra `spawn_{scene}_{sym}`. Un prefab qui en spawne un autre se résout naturellement —
  il est désormais compilé *pour une scène*, donc il sait laquelle.

Ce que ça coûte, et il faut l'assumer : **un prefab employé dans N scènes occupe N fois sa
place en ROM**, et le build le transpile N fois. C'est le prix du per-scène, il est réel, et il
se mesure comme le reste (règle de la v0.7.6 : le build dit, rien ne bloque). La ROM est la
ressource la plus large de la machine ; l'EWRAM, celle qu'on récupère, est la plus étroite.

Ce que ça achète, en plus du pool — **deux gains qui ne se voyaient pas depuis la question de
départ** :

- **Les palettes propres des prefabs se libèrent.** `prefab_own_slots` (`palette_alloc.py:191`)
  force aujourd'hui la palette propre d'un prefab au **même slot matériel dans TOUTES les
  scènes**, et la raison écrite est exactement celle qui tombe : « spawn_X est global ». Une
  fois le spawn per-scène, chaque scène alloue ses seize banques pour elle seule. Une scène de
  menu cesse de payer la banque de la balle du niveau d'action.
- **`actor.spawn` dans une scène sans pool devient une ERREUR de build.** Le checker valide
  aujourd'hui contre la liste du PROJET (`lua_compiler.py:188` : « `actor.spawn("X")` vise la
  liste entière, pas ce que la scène courante contient »). Avec un pool per-scène, il valide
  contre **le pool de cette scène** — et attrape une faute qu'aucun outil ne peut voir
  aujourd'hui, parce que tous les pools existent partout.

**La v0.23 a sa réponse** : l'état de script d'une partie se range là où se range celui de la
racine, c'est-à-dire dans l'unité de compilation de la scène.

### Tranché (2026-08-26) : le budget d'acteurs de la scène, en deux champs

Le pool se déclare **dans l'inspecteur de scène**, par un widget à deux champs qui partagent
un total :

```
Acteurs de la scène   [ 96 ]  slots réservés
Pool de prefabs       [ 32 ]  slots de spawn
                      ─────
                        128   ← la limite OAM, pas un réglage
```

**Les deux champs sont réglables et se répondent** : monter le pool descend les acteurs, et
l'inverse. Ce n'est pas une commodité d'interface, c'est la forme exacte de la contrainte —
il y a **un** budget, et deux façons de le dépenser.

- **Le total est 128 parce que le matériel affiche 128 sprites.** Il ne se règle nulle part,
  et surtout pas dans Project Settings : ce n'est pas une préférence, c'est l'OAM. L'auteur
  apprend la vraie limite de la machine en manipulant le widget, ce qui est précisément ce
  qu'un éditeur de GBA doit enseigner.
- **Le champ « acteurs » compte des slots RÉSERVÉS, pas des acteurs posés.** C'est ce qui le
  rend éditable, donc le widget bidirectionnel. L'auteur peut poser moins que ce qu'il
  réserve ; le validateur avertit s'il pose plus (même famille d'avertissement que les
  caméras et les windows, cf. « Ouvert » plus bas).
- **Le pool se dit en INSTANCES, le budget se paie en SLOTS.** Un prefab à sous-arbre coûte
  instances × parties (v0.23, `POOL_*_INSTANCES` contre `POOL_*_SIZE`). Le widget doit
  montrer les deux, sans quoi déclarer huit boss à quatre parties consomme trente-deux slots
  en silence.

**Une simplification est assumée ici, et il faut qu'elle soit écrite** : un acteur **sans
sprite** ne consomme aucune entrée OAM — le matériel en accepterait donc plus de 128. Le
budget les compte quand même, parce qu'un seul nombre lisible vaut mieux que deux plafonds
dont l'auteur devrait suivre lequel s'applique. C'est un choix d'ergonomie contre le
matériel, le seul de ce chantier, et il se rouvrira si un projet réel bute dessus.

### Livré le 2026-08-26 : la moitié éditeur

Le widget existe et pilote la vraie ROM. Ce qui est en place :

- `Scene.actor_slots` et `Scene.prefab_pools` (`core/models/scene.py`), absents du JSON tant
  que la scène n'a rien réglé.
- `codegen/actor_budget.py` — le plafond OAM, la conversion instances → slots, et le budget
  d'une scène en un seul appel. Source unique : les **huit** sites du build qui lisaient
  `Prefab.max_instances` passent tous par lui.
- La carte « Actor budget » dans l'inspecteur de scène, une ligne de pool par prefab.
- `validator._check_actor_budget` — les deux dépassements, en avertissement.
- `DEFAULT_ACTOR_SLOTS = 96` — une scène NEUVE naît partagée 96 / 32, écrit aux deux
  sites de naissance (`command_dispatcher.add_scene`, `Project.create`) et **pas** dans
  le défaut du dataclass : une scène déjà sur le disque garde son « auto », sinon tout
  projet existant réserverait 96 entrées par scène du jour au lendemain.

**`Prefab.max_instances` n'est pas supprimé, et c'est délibéré.** Plus rien ne l'édite et
aucun site du build ne le lit ; il ne sert plus que de **repli** pour un prefab dont aucune
scène ne déclare de pool. Le supprimer aujourd'hui viderait en silence les pools de tout
projet antérieur — le Pong compile encore parce que ce repli existe. Il part avec la moitié
codegen (compilation par scène), pas avant.

**Ce qui n'est donc PAS encore gagné** : la ROM alloue toujours UN pool par prefab, dimensionné
sur le **maximum** de ce que les scènes demandent (`prefab_pool_instances`), parce que
`POOL_<X>_SIZE` reste une constante unique pour le projet. L'économie par scène — celle qui
motive le chantier — arrive avec la compilation par scène. Le widget, lui, dit déjà la vérité
sur ce que l'auteur demande.

### Ce que ce budget fait apparaître, et qui n'était pas dans le chantier

**`g_actors[]` est dimensionné sur la SOMME des scènes, alors qu'une seule vit à la fois.**
`n_actors = total_scene_actors + pools` (`main_gen.py:4009`), où `total_scene_actors` est le
total de **toutes** les scènes concaténées (`main_gen.py:4007`) — chaque scène reçoit une
tranche, et les tranches des scènes endormies restent allouées en EWRAM pendant toute la
partie.

Tant que le budget était dérivé, ça se voyait à peine. Avec un plafond de 128 **par scène**,
un projet de cinq scènes réserve 640 `Actor` pour n'en utiliser jamais plus de 128 à la fois.
La conclusion logique du per-scène est donc : **dimensionner `g_actors[]` sur la scène la plus
chargée, pas sur leur somme**, et faire repartir chaque tranche de zéro. Ce n'est pas décidé
ici — ça touche la résolution des `TAG_*`, qui sont aujourd'hui des offsets globaux à travers
toutes les scènes — mais c'est le gain le plus large que v0.17 rend accessible, et il ne faut
pas le perdre de vue en chemin.

### Ouvert

- **`G_ACTOR_COUNT` n'est plus ce qu'il dit.** `actor_api.h` le fixe au total des acteurs de
  scène **sans les pools** (`rom_build.py:291`), alors que le tableau réel les inclut
  (`main_gen.py:4009`). Son seul consommateur documenté était la macro `broadcast`, et
  `actor_api_static.h:692` note que « broadcast est résolu directement dans le codegen de
  chaque scène » — la constante semble donc n'avoir plus de lecteur. À vérifier puis à retirer,
  ou à corriger : une constante qui ment est pire qu'une constante absente.
- **Les acteurs de scène ont le même défaut de nom, non traité ici.** `actor_{c_sym(nom)}.c`
  (`lua_compiler.py:386`) et `#define TAG_{NOM}` (`headers.py:58`) sont écrits sans préfixe de
  scène, alors que `headers.py` parcourt les acteurs de **toutes** les scènes : deux scènes
  portant chacune un acteur « Player » écrivent le même fichier et redéfinissent le même
  `#define`. Le préfixe de scène décidé ci-dessus pour les prefabs est la même réponse — à
  étendre aux acteurs, mais dans son propre chantier, pas dans celui-ci.

  Le projet **sait déjà nommer ce défaut** : `validator._check_cameras` ③ avertit quand deux
  caméras de scènes différentes portent le même nom, « `camera.switch("Nom")` viserait l'une
  des deux au hasard du build » — et `_check_window_regions` fait pareil. Les acteurs n'ont pas
  cet avertissement, alors que leur collision est **plus grave** : elle n'égare pas un appel,
  elle écrase un fichier généré. Le contrôle manquant coûte quinze lignes calquées sur celui
  des caméras, et il est utile **avant** le chantier de préfixe, pas après.

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
le jour où une ressource matérielle a son deuxième consommateur. Le viewport de caméra
(`Camera.frame_w/h`, réglé le 2026-08-24) a d'abord semblé ne PAS en être un — une seule
caméra active à la fois, allocation fixe WIN0=caméra/WIN1=scène. **Corrigé le 2026-08-25** :
c'en était bien un. Le second consommateur n'a pas besoin d'être simultané À L'EXÉCUTION pour
poser le problème — il suffit que deux INTENTIONS différentes (le cadre d'une caméra, un
panneau UI) veuillent la même ressource dans la MÊME scène, même si une seule caméra tourne à
la fois. `codegen/window_alloc.py` est livré : c'est la première instance réelle de ce
chantier, cf. ARCHITECTURE.md, « Windows — le pochoir ». Le candidat qui reste vraiment ouvert
est l'**écran partagé** de la v2.0 (plusieurs caméras actives SIMULTANÉMENT — un arbitrage
différent, à l'exécution).

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
  - **Précisé le 2026-08-25, pour les windows** : « renoncer au masquage » silencieusement est
    justement le pire cas ici — une région qui ne cache rien à la place d'une région découpée
    est un bug visuel sans signal. `window_alloc.py` choisit donc l'échec de build NOMMÉ
    plutôt que ce repli-là : pas de fusion possible (rangs différents, `WINR_0`/`WINR_1` ne
    sont pas interchangeables), pas de HBlank par scanline (hors périmètre v1), pas
    d'assignation à la main proposée (ce serait renommer la ressource matérielle). Un futur
    consommateur d'un AUTRE type de ressource peut légitimement choisir un vrai repli parmi la
    liste — ce n'est pas une règle générale, c'est ce que « exister matériellement » a donné
    pour CE cas.
- **L'assignation matérielle reste visible, dans un panneau avancé.** Le principe « l'auteur
  peut descendre jusqu'au matériel » n'est pas suspendu : il ne nomme plus la ressource pour
  obtenir un masque, mais il peut voir laquelle lui a été donnée, et la forcer.

#### Ce qui est fait (2026-08-25) — les windows

1. **Le principe est écrit** (cf. ARCHITECTURE), pour que rien de neuf ne lie un concept de
   haut niveau à un slot matériel.
2. **`WindowSlot.region` n'est plus un index matériel côté auteur** — renommé `.name`, résolu
   par `codegen/window_alloc.py`.
3. **La rupture assumée sur l'API Lua est faite pour les windows** :
   `window.set`/`window.show`/`window.is_visible` adressent maintenant par nom
   (`DOMAIN_WIN_REGION`), comme `window.set_layer` le faisait déjà — un seul schéma, plus de
   numéro matériel brut atteignable depuis un script.

#### Ouvert

- Jusqu'où va l'allocateur de frame (OAM, DMA, matrices affines). Un arbitrage par frame est
  un vrai coût CPU ; il se décide sur un cas mesuré, pas à l'avance — les windows n'en avaient
  pas besoin (résolubles au build, cf. ARCHITECTURE.md « Deux allocateurs, pas un »).
- L'assignation matérielle « visible dans un panneau avancé, et forçable » (décision
  verrouillée ci-dessus) n'est pas construite pour les windows — l'auteur voit le budget
  (N/2) mais pas quelle intention a reçu quel rang. À rouvrir si un projet réel en a besoin
  pour déboguer un recouvrement.

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

Une chose à traiter à ce moment-là, pas avant : l'**écran partagé**, qui rouvrira la question
« une région appartient-elle à une caméra, ou l'inverse ? ». Tant que les caméras sont
exclusives (une seule active par scène à la fois), la question ne se pose pas.

*Mise à jour 2026-08-24* : « unifier les mécanismes de caméra concurrents » (l'autre point que
cette piste listait) est réglé — c'est fait depuis la v0.6.1, et l'objet nommé porteur d'un
état existe déjà. Ce qui a bougé depuis n'est pas cet axe-là mais la PROPRIÉTÉ de la caméra :
elle appartient désormais à sa scène plutôt qu'au projet (cf. `changelog-archive/v0.6.md`,
« Révisé le 2026-08-24 »). Ça ne contredit pas Caméra2D — une caméra reste exclusive, une
seule active à la fois — et ça ne change rien à ce qui reste ouvert ici.

*Mise à jour 2026-08-24 (suite)* : la question « une région appartient-elle à une caméra, ou
l'inverse ? » posée ci-dessus est **réglée pour le cas à une seule caméra active** — la
caméra possède désormais un viewport (`Camera.frame_w/h`, cf. `ARCHITECTURE.md`, « Windows —
le pochoir ») : WIN0 lui appartient, WIN1 reste à la scène. Une allocation FIXE, décidée une
fois, pas un arbitrage à l'exécution — donc pas l'allocateur de ressources générique que ce
chantier réserve. Ce qui reste ouvert ici, sans changement, c'est l'**écran partagé** :
plusieurs caméras actives SIMULTANÉMENT (split-screen), qui redemanderait de vrais
arbitrages entre plusieurs propriétaires possibles des mêmes deux rectangles.

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
