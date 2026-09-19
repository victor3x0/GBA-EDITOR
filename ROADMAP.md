
# Roadmap

Ce document explique **le pourquoi** derrière les jalons qui restent à ouvrir : le scope,
les décisions déjà verrouillées avant même de commencer, et les questions volontairement
laissées ouvertes.

Une fois un jalon **livré**, son détail quitte ce fichier : la discussion complète (décisions
verrouillées, pièges rencontrés, mesures) part dans [changelog-archive/](changelog-archive/), un
fichier par version — ou par chantier, pour un [chantier technique](#chantiers-techniques). Un
jalon **produit** gagne en plus une ligne au [CHANGELOG](CHANGELOG.md) ; un chantier technique
n'y va jamais, il ne concerne que le code. Rien n'est perdu, ça change juste d'endroit — pour
rouvrir une décision passée, c'est là qu'elle est.

Six documents, six rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| [CHANGELOG](CHANGELOG.md) | qui veut savoir ce qui a changé | une entrée courte par version livrée |
| [changelog-archive/](changelog-archive/) | qui rouvre une décision passée | le détail complet d'une version livrée |
| **ce fichier** | qui décide de la suite | scope, décisions, ouvert — jalons **non livrés** seulement |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |
| [Référence de scripting](docs/scripting-reference.md) | qui écrit un script | le Lua accepté, et ce qui ne l'est pas |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel — on ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement, le contexte du moment valant mieux que des
suppositions faites à l'avance.

Un **jalon produit** porte un numéro (`vX.Y`) : il figure dans le tableau qui suit, et une fois
livré, une ligne rejoint le [README](README.md) — c'est ce qu'un visiteur vient chercher. Un
**chantier technique** n'en porte pas : né en cours de route (une question posée à
l'architecture, une dette relevée en marchant), il ne change rien pour qui joue au jeu produit
avec l'éditeur, seulement pour qui modifie le code. Il vit dans sa propre section,
[Chantiers techniques](#chantiers-techniques), à l'écart du tableau et du README — jamais
numéroté, jamais mélangé aux jalons produit.

---

## Où on en est

| Version | Sujet | État |
| --- | --- | --- |
| v0.2 | Palettes de couleurs | **Livrée**, quelques finitions — [archive](changelog-archive/v0.2.md) |
| v0.3 | Background vivant, texte et interface | **Livrée**, un report assumé, [balisage rouvert pour `[font=nom]`](#le-balisage-rouvert--fontnom-changer-de-police-en-cours-de-texte--en-cours) — [archive](changelog-archive/v0.3.md) |
| v0.4 | Animation de décor | **Livrée** — [archive](changelog-archive/v0.4.md) |
| v0.5 | Sauvegarde | **Livrée** — [archive](changelog-archive/v0.5.md) |
| v0.6 | Polish de la boucle de jeu | **Livrée**, rouverte pour le game feel — [archive](changelog-archive/v0.6.md) |
| v0.7 | Structures de données, et le langage | **Livrée**, les deux chantiers rouverts avec — [archive](changelog-archive/v0.7.md) |
| v0.8 | Son : la musique par scène, les transitions, le mixage | **Livrée** — [archive](changelog-archive/v0.8.md) |
| v0.14 | Diagnostic (trace de débogage, budget) | **Livrée**, réduite au frame+OAM (canaux/DMA non mesurables) — [archive](changelog-archive/v0.14.md) |
| v0.19 | Le sous-pixel | **Livrée** — [archive](changelog-archive/v0.19.md) |
| v0.24 | Le projet à l'échelle d'une équipe | **Livrée** — formats, build et chargement (paresseux + réconciliation incrémentale) — [archive](changelog-archive/v0.24.md) |
| v0.20 | L'état du monde : les collections persistantes | **Livrée** — [archive](changelog-archive/v0.20.md) |
| v0.23 | Ce qu'un boss demande | **Livrée** — [archive](changelog-archive/v0.23.md) |
| v0.21 | Le texte adressable : le dialogue piloté par la donnée | **Livrée** — [archive](changelog-archive/v0.21.md) |
| v0.22 | Menus, listes et curseur | **Livrée** — [archive](changelog-archive/v0.22.md) |
| v0.9 | Traduction des jeux | **Livrée** — [archive](changelog-archive/v0.9.md) |
| v0.10 | Distribution Linux | **Livrée** — format `.gba-project` et associations OS livrés |
| v0.11 | Traduction de l'éditeur | **Livrée (infra)** — extraction UI, contrôles et choix de langue livrés ; la traduction FR elle-même est reportée au chantier « traduction fr » (v2.0) |
| v0.12 | Vue d'ensemble (graphe des scènes) | **En cours** — carte, groupes, notes textuelles, mini-carte, recherche, inspecteur d'arête, retargetage du littéral et création de scène livrés ; création de transition ex nihilo, cibles calculées (`?`) et routage anti-croisement restent ouverts. Le tracé libre est reporté à v2.0. |
| v0.13 | Édition mixte (appels d'API en blocs) | Non commencée |
| v0.15 | Visibilité des éléments d'interface | **Livrée**, sous une autre forme que prévu — [archive](changelog-archive/v0.15.md) |
| v0.16 | L'API : règle de construction et rangement | Non commencée |
| v0.17 | Le pool par scène | **Livrée le 2026-09-19** — B1 (budget dérivé `128 − posés − UI` remplaçant le 96/32, liste « Spawné par », marqueur d'usage, compteur d'instances) **et** la moitié build B2b, en sept tranches vérifiées au build ROM (compilation par scène : symboles `<Scene>_<Prefab>`, `POOL_*`/`g_actors`/base OAM par scène, OBJ d'UI par scène, palettes propres des pools par scène, `spawn` rend `Actor*`/nil, budget OAM unique et bloquant). Reste ouvert : le culling existence/OBJ (« mille existent, cent-vingt-huit s'affichent »), un autre moteur |
| v0.18 | La valeur affichée : d'où elle vient | Non commencée |
| v0.25 | L'interface possède son chemin matériel | **Livrée** — [archive](changelog-archive/v0.25.md) |
| v0.26 | Les polices : sources, assets et aperçu | **Livrée** — [archive](changelog-archive/v0.26.md) |
| v0.27 | L'éditeur souffle le mot juste (autocomplétion) | **Livrée** — [archive](changelog-archive/v0.27.md) |

Les sept lignes qui suivent la v0.8 — de la v0.14 à la v0.22 — sont rangées dans leur **ordre
de traitement recommandé**, issu de la revue « projet de production » du 2026-08-19 et détaillé
dans sa section, juste après ce tableau : **v0.14 → v0.19 → v0.24 → v0.20 → v0.23 → v0.21 →
v0.22**. Les sept sont désormais livrées et archivées, v0.24 comprise. Les jalons restants (v0.10 à
v0.18, hors ceux déjà cités ; v0.9 est désormais livrée) n'ont pas de priorité tranchée entre eux
et restent dans leur ordre numérique, à la suite du bloc priorisé.

Le chantier technique *La grammaire de la struct `Actor`* (voir
[Chantiers techniques](#chantiers-techniques)) ne vient pas de cette revue : il est né d'une
question posée à l'architecture le 2026-08-23 (« l'API C tient-elle les trois concepts de
l'éditeur ? »). Il se traite tôt malgré tout : il touche la struct que tous les jalons produit
manipulent, donc chaque jalon ouvert après lui est un jalon à ne pas migrer avant qu'il se
referme.

Un numéro de version reste une **identité**, pas un rang : il n'est pas renuméroté quand
l'ordre de traitement change. Seul l'ordre de LECTURE de ce document — et l'ordre dans lequel
les chantiers seront ouverts — suit désormais l'ordre de traitement.

---

## Correctifs (trouvés en marchant, hors chantier)

Des défauts réels, trouvés en marchant — la plupart en construisant et en jouant les projets
démo pendant le chantier v0.9, quelques-uns depuis — sans rapport avec un jalon en particulier,
consignés ici pour ne pas rester invisibles faute d'un jalon à qui les rattacher.

- **`g_actors[]` débordait l'IWRAM sur un projet multi-scène dense**
  (`codegen/runtime_codegen/main_gen.py`), révélé par le fixture `BuildBenchmark` : 120
  acteurs répartis sur quatre scènes n'emploient jamais plus de 30 entrées OAM simultanément,
  mais leurs tranches restent réunies dans une table runtime unique. Ses ~20 Kio, ajoutés au
  moteur, dépassaient les 32 Kio d'IWRAM et faisaient échouer l'édition de liens. Cette table
  est désormais émise en **EWRAM** (`EWRAM_DATA`, 256 Kio) ; les `TAG_*` et la sémantique des
  transitions ne changent pas. Le dimensionnement par scène, gain plus large déjà identifié
  pour v0.17, reste un chantier distinct.

- **`project.save()` réécrivait tout à chaque `Ctrl+S`** (`core/resources/resource_store.py`), trouvé le
  2026-09-07 en traitant une lenteur de sauvegarde signalée sur le Script Editor. Enregistrer le
  projet sérialise et réécrit les quatorze collections ; or éditer un script ne change AUCUN
  asset, et `atomic_write` écrivait quand même chaque fichier (temporaire + rename, ré-armant le
  QFileSystemWatcher à chaque fois). Il **saute** désormais l'écriture quand le disque contient
  déjà le même texte — le patron de `build_output.write` côté build, porté au chemin de
  sauvegarde. Sur 200 assets intacts : ~950 ms → ~100 ms. Bénéfice au passage : un fichier non
  réécrit garde son mtime, donc pas de faux rebuild incrémental.

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

- **Un remplacement de police par langue n'était pas compté comme une composition**
  (`codegen/runtime_codegen/gen_text.py`, 2026-09-12). Une zone déclarée en Font8x8 Latin
  pouvait devenir Misaki Gothic 8 au runtime japonais : le moteur choisissait alors bien le
  chemin pixel, mais le build n'avait réservé aucun `RegionSurf` car il n'avait examiné que la
  police latine. `region_is_composited()` tient désormais compte de chaque remplacement de la
  police par défaut ; la réservation émet `text_set_region_surf` pour la zone. La palette de la
  police suit la même source persistante (`Scene.font_pal_banks`) dans l'inspecteur, le canvas,
  l'allocateur et le runtime. Tests : `test_text_surface_alloc.py`,
  `test_font_palette_tracking.py`, `test_scene_canvas_smoke.py`.

- **Trois trous du checker, fermés en avertissement** (`scripting/checker.py`, 2026-09-02).
  Trois défauts de la même famille, trouvés en écrivant un écran de sélection de langue : le
  script traverse le checker sans un mot, le codegen émet du C, et gcc parle d'un fichier que
  l'auteur n'a jamais écrit — le piège que l'ARCHITECTURE nomme le plus coûteux de cette
  chaîne. (1) **Un nom NU non déclaré** : `curpos = curpos + 1` émettait
  `curpos = (curpos + 1);`, un identifiant qui n'existe pas. `_check_expr` n'avait
  simplement AUCUNE branche `ExprName`. Le contrôle s'appuie sur un quatrième parcours à plat
  (`_collect_local_names`, même forme et même approximation que ses trois jumeaux) et sur la
  liste des espaces de noms, parce que la fin de la branche `ExprIndex` visite `e.obj` — le
  `global` de `global.score` passe par là. (2) **Les membres d'une référence d'élément
  d'interface** : `ui_element` est déclaré comme type de retour mais absent de `REF_TYPES`,
  donc `.y`, `.foo` et `:bouge()` passaient tous. Reconnue par sa FORME (`ui.get(...)`) et non
  en l'inscrivant dans `REF_TYPES` — l'y mettre ferait chercher les méthodes sous
  `ui_element:show` alors qu'elles vivent sous `self:show`, et casserait le `ui.get(x):show()`
  qui marche. (3) **Les arguments d'un appel utilisé comme RÉCEPTEUR** :
  `ui.get("Cusor"):show()` ne validait rien, alors que la même expression posée seule était
  refusée — `_check_call_expr` s'arrête à un récepteur `ExprName`. Corrigé en faisant descendre
  un appel posé seul par `_check_expr` comme n'importe quelle expression.

  **Avertissement pour (1) et (2)**, à durcir une fois éprouvés : ils s'appliquent à tous les
  scripts de tous les projets, et un cas légitime oublié bloquerait un build qui marche. **(3)
  garde la sévérité des contrôles existants** — il ne fait que les laisser passer, et un nom
  d'élément inconnu ne produit aucun `#define` : ce build-là échouait déjà au `make`.
  Tests : `test_checker_holes.py`, dont la moitié tient ce que les contrôles ne doivent PAS
  refuser.

- **Une faute de syntaxe disait « None »** (`scripting/parser.py`). Le parse est le PREMIER
  filtre de la chaîne, et c'était le seul message qui ne disait pas où regarder :
  `[error] Titre.lua — parse: syntax errors: None`, quelle que soit la faute. Le contraire de
  ce que la v0.7.5 a établi partout ailleurs — le checker nomme sa ligne, `lua_subset` nomme
  le nœud refusé ET la phrase à écrire à la place. Rien n'était perdu, c'était jeté au
  FORMATAGE : luaparser lève sa `SyntaxException` depuis un `except`, donc Python garde la
  `ParseCancellationException` d'antlr dans `__context__`, laquelle porte l'exception réelle
  avec son jeton fautif et ses jetons attendus. Deux décisions : le jeton **trouvé** n'est
  jamais rapporté — antlr le désigne là où il a renoncé, pas là où l'auteur s'est trompé (sur
  `if x(...) :`, il nomme la parenthèse de l'appel) —, et un « end » manquant se dit comme
  tel plutôt que d'envoyer l'auteur regarder la dernière ligne du fichier, qui est presque
  toujours correcte. S'y ajoute une table de **faux amis** (`+=` et les affectations
  composées, `++`, `:` au lieu de `then`, `!=`, `&&`, `||`, `elif`, `#` en commentaire…) balayée SEULEMENT après un échec, donc jamais sur
  un script valide, et hors chaînes et commentaires — un `!=` dans une réplique de dialogue
  n'est pas une faute de syntaxe. Elle n'est pas dans `lua_subset.REFUSED` : celui-là range
  des nœuds d'AST, et ces fautes-là empêchent l'AST d'exister. `LuaParseError` porte
  désormais sa `line`, que le build cite comme le reste (`Titre.lua:2 : …`).
  Tests : `test_parse_errors.py`.

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

## Chantiers techniques

Un chantier technique ne livre rien de visible pour qui joue au jeu produit avec l'éditeur —
seulement une réécriture, une clarification ou une garantie côté code. Il n'apparaît ni dans le
[README](README.md) ni dans le [CHANGELOG](CHANGELOG.md), et ne porte pas de numéro `vX.Y` : une
fois refermé, son détail rejoint [changelog-archive/](changelog-archive/) comme n'importe quel
jalon, mais référencé par son nom plutôt que par un numéro.

| Chantier | Ouvert le | État |
| --- | --- | --- |
| La grammaire de la struct `Actor` | 2026-08-23 | **Livré** — [archive](changelog-archive/actor-struct-grammar.md) |
| Les trois couleurs de l'interface | 2026-08-24 | **Livré** — [archive](changelog-archive/three-colors.md) |
| `global.nom` / `const.nom` — l'accès pointé | 2026-09-01 | **Livré** — [archive](changelog-archive/global-const.md) |
| L'identité d'un asset et son fichier | 2026-09-02 | **Livré** — [archive](changelog-archive/asset-identity.md) |
| Les formats acceptés à l'import | 2026-09-03 | **Livré** — [archive](changelog-archive/import-formats.md) |
| La police, une palette d'asset comme les autres | 2026-09-03 | **Livré** — [archive](changelog-archive/font-palette.md) |
| L'écran construit à sa première visite | 2026-09-13 | **Livré** — [archive](changelog-archive/lazy-screen-build.md) |
| L'ouverture d'un projet, et l'écran blanc | 2026-09-13 | **Livré** — [archive](changelog-archive/open-white-screen.md) |
| Les palettes, rangées avec les assets | 2026-09-18 | **Livré** — [archive](changelog-archive/palettes-in-assets.md) |
| Le cache de scène | 2026-09-16 | À ouvrir — voir [ci-dessous](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) |
| L'écran resynchronisé à sa revisite | 2026-09-18 | À ouvrir — voir [ci-dessous](#lécran-resynchronisé-à-sa-revisite--voir-les-catalogues-à-jour-en-revenant-sur-un-écran) |
| Undo/redo des sidecars d'éditeur | — | À ouvrir — envisagé pour **V2**, voir [ci-dessous](#undoredo-des-sidecars-déditeur-annuler-la-création-dun-groupe-un-déplacement-de-nœud) |

---

## Le cache de scène — rouvrir une scène déjà visitée sans tout redécoder

### D'où vient la question (2026-09-16)

Victor : sélectionner une scène dans le project viewer prend une demi-seconde perceptible, même
pour une scène triviale (title screen, deux zones de texte). Trois causes indépendantes trouvées
en investiguant `window._on_scene_selected` ([window.py:1128](editor/window.py:1128)) :

1. **Corrigé (2026-09-16).** `AssetsFinderPanel.refresh()` reconstruisait les 3 arbres (Scenes,
   Prefabs, Scripts) à chaque clic, alors que rien n'y change quand on change simplement de scène
   active. Remplacé par un simple surlignage de la scène active, sans repeuplement —
   `highlight_active_scene` ([assets_finder_panel.py](editor/ui/scene_manager/assets_finder_panel.py)),
   posé sur `AssetFinder.highlight_selection` déjà existant.
2. **Pas de bug.** `_refresh_diagnostics` → `validate_project` → `project.load_all_resources()`
   ([validator.py:126](editor/core/validator.py:126)) est déjà gardé par
   `_deferred_resource_collections` ([project.py:339](editor/core/project.py:339)) : le coût réel
   (stat + hash de tout le catalogue) n'est payé qu'à la toute première scène ouverte d'une
   session ; ensuite chaque `load_*` est un test d'ensemble vide, donc quasi gratuit.
3. **Ce chantier.** `SceneEditor.load_project` ([scene_canvas.py:721](editor/ui/scene_manager/scene_canvas.py:721))
   reconstruit le canvas ENTIER à chaque sélection — y compris en revenant sur une scène déjà
   visitée dans la même session, où rien n'a changé :
   - `compose_frame_image` ([sprite_compose.py:15](editor/core/sprite_compose.py:15)) rouvre et
     redécode depuis le disque le PNG source du sprite pour CHAQUE acteur, à CHAQUE visite —
     aucun cache, même quand le fichier n'a pas bougé depuis la visite précédente.
   - `bg_pixmap` / `BgLayerRaster.render` ([canvas_raster.py:171](editor/ui/scene_manager/canvas/canvas_raster.py:171))
     recompose le rendu tuile par tuile du fond à chaque visite. Le tileset lui-même est déjà en
     mémoire (`BackgroundAsset`, pas de disque ici), mais le raster complet est refait à zéro.
   - `_reload_ui_regions` / `set_ui_regions` ([canvas_scene.py:440](editor/ui/scene_manager/canvas/canvas_scene.py:440))
     détruit et recrée tous les items d'interface et recalcule les couleurs de banque
     (`_compute_bank_colors`, documenté à ~15 ms/région) à chaque visite.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Quoi cacher, précisément.** Deux formes envisagées avec Victor, pas encore choisies :
  - un cache des **décodages disque** purs (PNG source des sprites/fonds), invalidé par mtime —
    la composition par frame/scène (flips, palette, overrides live) continue de tourner à chaque
    visite. Scope net, risque faible : rien ne peut devenir périmé, seul le pixel brut du fichier
    est mémorisé, jamais un résultat qui dépend de l'état vivant du projet.
  - un cache du **canvas complet par scène** (QGraphicsScene/items déjà construits), pour rouvrir
    une scène visitée sans rien recalculer, même pas le raster de palette/bank colors. Gain plus
    net, mais très invasif (`SceneEditor.load_project` en profondeur) et risque de
    désynchronisation si un asset ou une palette change pendant que la scène est en cache
    (édition d'un sprite ou d'une palette depuis un autre écran) — demanderait une invalidation
    explicite, pas seulement un mtime.
- **Recouvrement avec CanvasRework.** Le chantier de refonte du canvas est en cours (`scene_graph`,
  `scene_graph_state`, non encore committés à l'ouverture de cette entrée) : ouvrir un cache de
  scène avant que cette refonte se stabilise risque de dupliquer le travail ou de mettre en cache
  un état que CanvasRework va remplacer. À revérifier au moment d'ouvrir.
- **Mesurer avant de trancher.** Aucune mesure chiffrée prise pour l'instant, seulement une lecture
  de code — profiler `load_project` sur un projet réel donnerait la vraie proportion entre
  décodage sprite, raster de fond et reconstruction des régions UI, plutôt que de deviner laquelle
  des trois mérite le cache en premier.

---

## L'écran resynchronisé à sa revisite — voir les catalogues à jour en revenant sur un écran

Le pendant de [« L'écran construit à sa première visite »](changelog-archive/lazy-screen-build.md) :
celui-là a rendu la construction paresseuse ; celui-ci s'occupe de ce qui se passe aux visites
SUIVANTES, quand l'écran existe déjà mais que le projet a bougé sous lui.

### D'où vient la question (2026-09-18)

Née en marge d'une session de debug du copier/coller de zones de texte. Symptôme rapporté par
Victor : l'éditeur de texte affichait « 1 of 8 shown » — huit textes dans le projet, un seul dans
la table. Cause : une zone de texte créée dans le Scene Manager ajoute son entrée à `project.texts`
([ui_inspector.py:1071](editor/ui/scene_manager/inspectors/ui_inspector.py:1071)), mais
`Window._load_screen_for_project` ([window.py:901](editor/window.py:901)) ne charge un écran qu'à
sa **première** visite (le garde `_project_loaded_screen_indices`). Revenir sur l'écran Texte ne le
rechargeait donc pas : sa table restait figée sur son ancien contenu, alors que le pied de page
lisait le total à jour du projet — d'où le « 1 of 8 ».

L'audit des huit écrans a montré que le trou n'est pas propre au texte. Le seul rafraîchissement
cross-écran câblé aujourd'hui vise les panneaux du **Scene Manager** (`project_tree_changed`,
`actors_list_changed`, … → `assets_finder_panel.refresh` / `scene_tree_panel.refresh`,
[window.py:654](editor/window.py:654)) et l'**écran Palettes** (`palettes_changed` → `refresh`,
[window.py:688](editor/window.py:688)). Tout autre écran qui affiche un catalogue écrit ailleurs se
périme à sa première visite passée :

- **Scripts** (le plus grave) — la sidebar RÉFÉRENCES et surtout l'**autocomplétion** capturent
  sprites, fonds, sons, globals, polices, constantes via `names_by_domain`
  ([project_names.py:31](editor/scripting/project_names.py:31)) au `load_project`. Un nom né ensuite
  ailleurs manquait **en silence** — aucune erreur, juste une complétion incomplète.
- **Backgrounds / Animations** — la grille « + du catalogue » lit `project.palettes` à l'ouverture.
  Une palette ajoutée/renommée/retirée dans l'écran Palettes n'y apparaissait pas.
- **Datas** — *pas* de bug : les listes de choix des colonnes de référence sont dérivées **en
  direct** à l'ouverture du menu déroulant (`data_column_choices` →
  [project.py:422](editor/core/project.py:422)), depuis les listes partagées du projet.
- **Sounds** — rien d'externe n'écrit l'audio ; sans objet.

### Ce qui a déjà été colmaté (2026-09-18), à consolider ici

Chaque écran touché a reçu, séparément, un `showEvent → refresh` bon marché (relire des noms/banques
déjà en mémoire, pas de re-décodage d'asset). Ce sont ces colmatages ponctuels que le chantier doit
remplacer par un mécanisme unique :

- Texte — `TextEditorScreen.showEvent` → `refresh()`
  ([text_editor_screen.py:183](editor/ui/text_editor/text_editor_screen.py:183)).
- Scripts — `ScriptEditorScreen.showEvent` → `_refresh_catalogs()`
  ([script_editor.py:245](editor/ui/script_editor/script_editor.py:245)).
- Backgrounds / Animations — `showEvent` → `refresh_palette_catalog()` du panneau
  ([background_editor_screen.py:1221](editor/ui/background_editor/background_editor_screen.py:1221),
  [sprite_editor_screen.py:74](editor/ui/sprite_editor/sprite_editor_screen.py:74)).
- Tests de non-régression : `tests/ui/test_text_editor_screen_resync.py`,
  `test_script_editor_screen_resync.py`, `test_asset_editor_palette_resync.py`.

Ces correctifs FONCTIONNENT mais traitent des cas, pas la cause : chaque nouvel écrivain cross-écran
rouvre le trou en silence, et rien ne force un écran neuf à se doter de son `showEvent`.

### L'esquisse

Faire du rafraîchissement un point du contrat `ProjectScreen`, appelé **au centre**, plutôt qu'un
`showEvent` réécrit dans chaque écran :

1. **`ProjectScreen.refresh()` (ou `on_reveal()`) devient contractuel** — chaque écran expose une
   méthode de re-dérivation idempotente et bon marché : relire les catalogues DÉJÀ en mémoire, sans
   toucher au disque ni re-décoder d'asset, en conservant sélection et état d'édition. Les écrans
   déjà pourvus (`refresh` existe sur Texte, Datas) n'ont qu'à s'y conformer.
2. **`Window._show_screen` l'appelle** juste après `setCurrentIndex`, si l'écran est construit ET
   déjà chargé pour ce projet — l'exact symétrique du garde `_load_screen_for_project`. Plus de
   `showEvent` par écran, plus d'oubli possible : un écran qui n'implémente pas `refresh` ne
   rafraîchit rien, mais le contrat le rend visible à la revue.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Central `_show_screen` vs `showEvent` par écran.** Le point central supprime le boilerplate et
  l'oubli, et se déclenche sur la seule transition qui compte (un écran empilé caché n'a pas besoin
  de suivre l'état en direct). À contre-courant : `showEvent` capte aussi les cas où l'écran
  réapparaît sans passer par `_show_screen` (restauration de fenêtre) — à vérifier si ça arrive.
- **Faut-il un événement du tout ?** Pour des écrans EMPILÉS (un seul visible), rafraîchir à la
  revisite suffit — inutile de s'abonner au bus pour réagir pendant qu'on est caché. Les abonnements
  existants (`palettes_changed` → Palette editor) pourraient même se simplifier en `refresh` à la
  revisite… SAUF si un écran doit refléter un changement pendant qu'il est visible (ex. deux vues
  d'un même bus dans un écran composite). À cartographier avant de tout basculer.
- **Le coût du `refresh`.** Le contrat n'a de sens que si `refresh` reste bon marché sur les écrans
  lourds : il doit re-dériver depuis la mémoire, jamais relancer `load_sprites` / un décodage PNG /
  un raster. Recouvre directement les arbitrages du [cache de scène](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) —
  les deux chantiers touchent « ce qu'on refait, ou pas, en revenant sur une vue ».
- **Le piège du `showEvent` qui lève.** Une exception dans un `showEvent` (appelé depuis le C++ de
  Qt) **abort** le process sans trace lisible — rencontré en écrivant les colmatages
  (`AttributeError` → exit 139). Le point central en Python propre évite ce mode d'échec : à retenir
  comme argument pour `_show_screen` plutôt que `showEvent`.

### Recouvrement

- Avec [« L'écran construit à sa première visite »](changelog-archive/lazy-screen-build.md) : ce
  chantier est le garde que celui-ci contourne ; il en est la moitié « visites suivantes ».
- Avec [Le cache de scène](#le-cache-de-scène-rouvrir-une-scène-déjà-visitée-sans-tout-redécoder) :
  même famille de questions (que refait-on en revenant sur une vue), et même exigence que le
  `refresh` ne paie pas le décodage.

---

## Undo/redo des sidecars d'éditeur — annuler la création d'un groupe, un déplacement de nœud

### D'où vient la question (2026-09-16)

En revue du chantier « groupes du Graphe de scènes » (créer/supprimer/renommer un groupe, y ranger
des scènes, déplacer et redimensionner les boîtes, déplacer les nœuds), Victor a demandé de
vérifier que **toutes** les opérations introduites étaient reliées à undo/redo. Constat :

- **Reliée.** La *suppression de scène* (clic-droit du Graphe) pousse `DeleteResourceCmd` dans
  l'historique — exactement la commande du project viewer. C'est une vraie mutation de `Resource`.
- **Non reliées, et à dessein.** Tout le reste — créer / supprimer / renommer / colorer un groupe,
  ranger une scène (`move_member`), déplacer une carte, déplacer ou redimensionner un cadre —
  écrit dans **deux sidecars d'éditeur** : `AssetFolderStore` (les groupes, partagés viewer ↔
  Graphe) et `SceneGraphState` (positions des nœuds, géométrie des cadres). Aucun ne passe par
  `get_history()`. Les opérations de dossiers du project viewer n'y sont **jamais** passées non
  plus, avant ce chantier — ce n'est pas une régression.

### Pourquoi ce n'est pas un simple oubli

Deux obstacles durs empêchent de brancher naïvement ces gestes sur l'historique existant :

1. **L'historique est PAR SCÈNE et vidé à chaque changement de scène ou d'écran**
   ([window.py:878](editor/window.py:878), [window.py:1135](editor/window.py:1135)). Créer ou
   déplacer un groupe est une action *projet*, pas *scène* : on créerait un groupe, on cliquerait
   une autre scène dans le viewer → `_history.clear()` → l'entrée « annuler le groupe » aurait déjà
   disparu. Un undo qui ne survit pas au prochain clic de scène est pire que pas d'undo.
2. **Ces sidecars ne changent ni le jeu, ni le build, ni le JSON de gameplay** (cf. en-tête de
   [asset_folder_store.py](editor/core/asset_folder_store.py)) : un dossier ne fait que choisir le
   parent visuel d'un asset, une position n'existe que pour l'œil. L'historique actuel sert les
   mutations du modèle, pas la présentation.

### Ce qu'il faudrait trancher avant d'ouvrir

- **Un stack undo DÉDIÉ, projet-wide.** Distinct de `get_history()`, non vidé au changement de
  scène ni d'écran, tant que le projet reste ouvert. C'est le cœur du chantier : sans lui, aucune de
  ces opérations n'est annulable de façon fiable.
- **Le conflit de Ctrl+Z.** Deux piles undo (modèle per-scène vs organisation projet) réclament la
  même touche dans le Scene Manager. Décider laquelle répond — selon le focus (Graphe/viewer vs
  canvas), selon le dernier geste, ou une pile unifiée — sans que Ctrl+Z devienne imprévisible.
- **Réversibilité de la suppression de groupe.** `delete_folder` remonte membres et sous-groupes au
  parent ([asset_folder_store.py](editor/core/asset_folder_store.py)) : l'undo doit restaurer
  l'appartenance *exacte* d'avant, donc capturer l'état (id, `parent_id`, `members`) avant de
  supprimer, pas seulement recréer un dossier vide.
- **Granularité et fusion.** Un `Ctrl+G` sur une sélection = plusieurs `move_member` → une seule
  entrée (comme le lot de suppression du finder via `MacroCmd`). Un glisser de nœud = une entrée,
  pas une par pixel (même besoin de fusion que `SetFieldCmd`).
- **Portée.** Trancher quelles opérations entrent : la *structure* seule (groupes + appartenance),
  ou aussi la *présentation* (positions, géométrie des cadres). La présentation change à chaque
  petit glisser ; l'y inclure gonfle la pile pour un gain douteux.

---

## Le balisage rouvert — `[font=nom]`, changer de police en cours de texte — **EN COURS**

Réouverture de **v0.3.2** (le balisage), pas un jalon neuf : la grammaire, la piste
d'événements et le catalogue de balises existent déjà et sont clos. On y ajoute UNE balise. Pas
de numéro — le balisage a le sien.

### D'où vient la question (2026-09-04)

« Dans notre balisage, peut-on changer de police dynamiquement ? » La réponse était **non** : le
catalogue s'arrête à `speed`, `pause`, `icon`, `wave`, `shake`, `color`
([text_markup.py:66](editor/core/text_markup.py:66)). La seule bascule typographique en cours de
chaîne est l'ENCRE (`[color=n]`), dans la sous-palette de la police déjà en place — jamais un
autre jeu de glyphes. La police est fixée un cran au-dessus : une zone porte UN `font_name`
([ui_region.py:329](editor/core/models/ui_region.py:329)), et la mise en page prend UNE police
([text_layout.py:47](editor/core/engine_emulation/text_layout.py:47)). Une scène affiche déjà
plusieurs polices — mais par zones, jamais au sein d'une chaîne.

La lecture du runtime a montré que l'ajout est **incrémental**, pas un sous-système : le moteur a
déjà tout ce qu'il faut, on ne fait que le câbler à une balise.

### Décisions verrouillées

- **Balise de PORTÉE, symétrique à `[color]`.** `[font=nom]…[/font]`, valeur `VALUE_NAME`. Elle
  entre au catalogue `TAGS` et rien d'autre : l'analyse est générique, `_close_scope`,
  l'imbrication croisée et l'avertissement de portée non refermée la couvrent déjà. Une balise
  ponctuelle (« change jusqu'à nouvel ordre ») est **écartée** plus bas.
- **Un ÉVÉNEMENT de plus, pas un mécanisme de plus.** `[font]` sort un `TEXT_EV_FONT` sur
  `[at, end)`, exactement comme `wave`/`shake`/`color`
  ([font_emit.py:972](editor/codegen/font_emit.py:972)). `value` = index de la police LOGIQUE
  (ordre de `project_fonts()`, le même que `g_fonts` et `g_lang_font`), résolu au build comme
  `[icon]` résout son glyphe.
- **La bascule passe par `text_set_font`, donc honore la LANGUE.** Franchir un `TEXT_EV_FONT`
  appelle `text_set_font(value)`, qui remappe déjà par langue
  (`f = g_lang_font[g_lang][f]`, [gba_engine.h:1686](runtime/include/gba_engine.h:1686)). Une
  `[font=titre]` suit donc la traduction sans une ligne de plus — même brique que `text.set_font`
  (v0.9). Aucun nouveau chemin de chargement.
- **Le coût est un RE-POINTAGE, pas une recopie.** Les polices sont co-résidentes en VRAM :
  chacune a sa base (`g_font_base[f]`) et un bit dans `g_font_loaded`
  ([gba_engine.h:1699](runtime/include/gba_engine.h:1699),
  [1708](runtime/include/gba_engine.h:1708)). Revenir à une police déjà chargée ne coûte qu'un
  test et une copie de palette (64 o). Le seul coût MATÉRIEL réel, ce sont les tuiles du
  sous-ensemble de la police appelée, comptées au build comme n'importe quelle police. C'est ce
  qui rend la balise abordable : sans co-résidence, elle aurait recopié la VRAM par segment.
- **La police citée devient RÉSIDENTE de la scène.** `scene_font_names` gagne une QUATRIÈME
  source, après la défaut, les zones et les scripts
  ([font_emit.py:461](editor/codegen/font_emit.py:461)) : les `[font=nom]` des textes que la
  scène peut afficher. Pas de nouvel allocateur — le sous-ensemble et la base par scène hébergent
  déjà N polices.
- **Le sous-ensemble suit la police ACTIVE, glyphe par glyphe.** Le glyphe du caractère `i`
  appartient à la police en vigueur en `i` (défaut de zone, ou dernière `[font]` ouverte). Le
  constructeur de sous-ensemble parcourt donc la piste d'événements — le même parcours que la
  mise en page. Chaque police n'embarque que les glyphes réellement atteints sous elle.
- **L'imbrication tombe juste toute seule.** `[color=3]` sous `[font=X]` = encre 3 de la
  sous-palette de X (la couleur se résout à la frappe contre la police courante). `[icon=y]` sous
  `[font=X]` = glyphe y de X (l'icône devient des codepoints, appariés à la mise en page sous la
  police active). Rien de spécial à écrire : les deux se résolvent déjà par position.

### Ce qui a été écarté, et pourquoi

- **Une balise PONCTUELLE `[font=X]` sans fermeture** (changer jusqu'à nouvel ordre). Elle
  rouvrirait ce que la portée a résolu : un effet sans borne est indécidable côté sous-ensemble
  (jusqu'où réserver ?) et laisse l'état d'un texte fuir sur le suivant. La forme fermée dit
  exactement où la police revient.
- **Recharger la VRAM à chaque bascule** (le chemin naïf où `text_set_font` recopie les
  glyphes). La co-résidence déjà en place l'écarte : inutile de payer une DMA par segment quand
  chaque police a sa place.
- **Une police par langue portée par la BALISE** (`[font=X:ja]`). La langue REMAPPE déjà la
  police (`g_lang_font`) — la substitution vit là, pas dans la source balisée. Même règle que
  « une langue n'a pas de police, elle a éventuellement un remplacement » (v0.9).

### Ce que ça touche

- [text_markup.py](editor/core/text_markup.py) : une entrée `TagSpec("font", True, VALUE_NAME, …)`
  au catalogue. Rien d'autre — l'analyse ne connaît pas les balises une à une.
- [font_emit.py](editor/codegen/font_emit.py) : `_EV_KIND` gagne `"font": "TEXT_EV_FONT"` ;
  l'émission résout le nom en index de `project_fonts()` et VALIDE que la police existe (comme
  `[icon]` valide son glyphe) ; `scene_font_names` scanne les `[font]` des textes de la scène ;
  le constructeur de sous-ensemble attribue chaque glyphe à la police active.
- [text_layout.py](editor/core/engine_emulation/text_layout.py) : `layout_text` devient conscient
  de la police PAR POSITION — chasse et appariement au plus long (ligatures) lus dans la police
  active, pas dans un unique argument. C'est le vrai travail : l'aperçu de l'éditeur doit tomber
  juste, sinon il ment sur le rendu ROM (la raison d'être du point unique `text_markup`).
- [gba_engine.h](runtime/include/gba_engine.h) : `TEXT_EV_FONT` à l'énum ; la boucle de dessin
  appelle `text_set_font(value)` en franchissant l'événement et REPOSE la police de zone en
  sortie de portée. `text_color_at`/`text_fx_at` ont déjà le modèle « quel événement couvre `i` »
  à recopier.
- l'écran Texte : la barre de balisage (`markup_toolbar`) et la coloration (`markup_highlighter`)
  prennent la balise gratuitement (dérivées de `TAGS`) ; l'aperçu écran doit charger la 2ᵉ police.

### Ouvert

- **La hauteur de ligne quand deux polices se partagent une ligne.** Interligne et ligne de base
  ne coïncident pas entre deux planches. À trancher : la ligne prend le MAX des hauteurs (jamais
  de chevauchement, mais le texte « saute »), ou la police de zone impose l'interligne (régulier,
  mais une grande police déborde). À rouvrir avec un cas réel sous les yeux.
- **La couverture par langue d'une police APPELÉE.** `Font.missing_chars` doit se vérifier contre
  la police active PAR SEGMENT, pas contre la seule police de zone — sinon un `[font=X]` sur un
  caractère que X ne porte pas passe le garde-fou de couverture (v0.9). Le parcours par événement
  de la décision « sous-ensemble » le donne ; reste à le brancher au garde-fou.
- **`[color]` sous une `[font]` NON composée.** `[color]` exige une police composée
  ([font_emit.py:948](editor/codegen/font_emit.py:948)) ; si `[font=X]` bascule vers une planche
  mono, la couleur du segment sera ignorée. Avertir au build (le message existe, il faut le rendre
  conscient du segment) ou l'assumer — à trancher.
- **Cerner les textes d'une scène pour la 4ᵉ source.** `scene_font_names` sait déjà rendre None
  quand c'est indécidable (script opaque) ; reste à confirmer que l'ensemble des textes
  atteignables par une scène est aussi bien cerné que ses polices de zone, ou à retomber sur la
  réservation projet quand il ne l'est pas.

---

## v0.9 — Traduction des jeux créés avec l'éditeur — **LIVRÉE**

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
  <br>↳ **Précisée par la [v0.26](changelog-archive/v0.26.md)** (2026-09-12) : la chaîne
  de couverture vit dans le `FontAsset` ; elle complète le remplacement optionnel de la police
  par défaut par langue, elle ne le remplace pas.
- **`font_de.fnt` est une PRATICITÉ D'IMPORT, jamais une règle.** Le suffixe pré-remplit la
  déclaration quand on ajoute une langue ; ce qui lie une police à une langue reste la
  déclaration explicite du projet. Déduire une liaison d'un suffixe de nom, c'est de la magie
  non vérifiable qui casse au premier renommage — et ça contredit `<asset>_name`, la règle du
  graphe de dépendances.
  <br>↳ **Toujours écartée** : le remplacement éventuel se configure explicitement dans
  `Language.default_font` ; un suffixe de fichier ne crée aucun lien.
- **Une scène ne change jamais de police selon la langue.** Elle nomme `dialog` ; c'est la
  RÉSOLUTION de ce nom qui dépend de la langue, par une table de remap. Sans ça, il faudrait
  réécrire chaque `text.set_font` et chaque zone de mise en page, dans quarante scènes, pour
  chaque langue ajoutée.
  <br>↳ **Confirmée et raccordée à la [v0.26](changelog-archive/v0.26.md)** : la scène
  nomme toujours `dialog`, et `g_lang_font` remappe seulement la police par défaut ; les sources
  de l'asset règlent ensuite la couverture des caractères manquants.
- **PNG et `.fnt` seulement** — c'est déjà le cas (`font_import.py` refuse même le BMFont
  binaire), mais ça mérite d'être écrit comme une décision et pas comme un état de fait : une
  police est un **jeu fini d'images de glyphes**. C'est exactement ce qui rend
  `scene_codepoints()` calculable, donc le sous-ensemble par scène possible, donc le japonais
  envisageable. Un TTF rendu au build ne donnerait pas ça.
  <br>↳ **Remplacée par la [v0.26](changelog-archive/v0.26.md)** : les sources
  vectorielles sont acceptées via `FontRasterizer` ; le « jeu fini de glyphes » se déplace de la
  source vers la **sortie de build** (le sous-ensemble requis), et l'argument tient toujours.
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
| 5 | **Servir** — *codée, build ROM réel en attente* | La réservation VRAM sur l'union, `lang_set` borné pour relire une langue sauvegardée, le compte des trous au build, et la recette du menu de langue dans le guide de scripting. | — |

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
3. **Le remap de police lit `Language.default_font`**, réglé dans
   [models/settings.py](editor/core/models/settings.py). `g_lang_font[lang][police]` remplace
   la police par défaut du projet par la police par défaut de la langue ; les autres polices
   conservent leur index. « Pas de remplacement » n'est donc pas un cas spécial au runtime,
   l'indirection reste toujours valide. `text_set_font(FONT)` résout d'abord `FONT`, puis
   applique le remap : le script continue de nommer `dialog`, jamais une variante par langue.
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
| 3.2 | Remap de police — *livrée* | `g_lang_font`, lu par `text_set_font` pour remplacer la police par défaut du projet par celle de la langue. | Toute langue sans `Language.default_font` (cas courant EN/FR/DE/ES et police déjà multilingue) — table = identité. |
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
langue (`Language.default_font`, décision 3.2) peut substituer une autre planche à celle que la zone
nomme, et c'est celle-là que `text_set_font` charge réellement une fois la langue active. Juger
la police déclarée aurait produit de faux positifs sur tout projet qui utilise le remap
justement pour ce genre de cas (un système d'écriture différent).

6 tests neufs (`test_font_coverage_lang.py`), dont un qui prouve que le remap éteint
l'avertissement quand il couvre vraiment le caractère. Vérifié sur Fonts&Texts (0 avertissement
après correction de la traduction) et Pong (aucune régression, les deux avertissements restants
sont ceux, déjà connus, de `_check_literal_texts`).

## Phase 5 — Servir : le design (2026-09-02)

Condition d'ouverture remplie : les phases 1 à 4 sont livrées, un projet peut déclarer ses
langues, les traduire, les émettre et en changer en jeu. Ce qui reste tient à la question
« et maintenant, comment un JOUEUR s'en sert ? » — plus l'ardoise que la lecture du code a
révélée en ouvrant le chantier.

### Ce que la lecture du code a trouvé, et qui n'était pas dans le plan

**La réservation VRAM est calculée sur la SOURCE, alors que le runtime charge l'UNION.**
La décision 4 de la phase 3.3 disait : le sous-ensemble ÉMIS est l'union de toutes les langues,
la RÉSERVATION reste sur la langue active. Les deux moitiés de cette phrase sont vraies
séparément et fausses ensemble : `text_set_font` copie `n_var × n_load` tuiles depuis le
`FontSubset` de la scène — donc l'union, **quelle que soit la valeur de `g_lang`** — pendant que
`scene_text_reservation` dimensionne le bloc avec `scene_codepoints(p, scene, "")`, la source
seule.

Mesuré sur un cas synthétique (une scène, une police, une zone, un side qui ajoute 12 glyphes) :
**24 tuiles chargées, 12 réservées**. Le bloc de texte fait la moitié de ce qui s'y écrit ; les
bases des polices suivantes, le bloc de surface composée et les sprites en cible BG sont posés
derrière et se font écraser. Et `res["total"]` alimentant `scene_layout`, le garde-fou de budget
— celui qui BLOQUE — compte faux lui aussi.

Deux corollaires qui corrigent des phrases déjà écrites plus haut :

- la justification de la phase 3.4 (« avertissement et non erreur : rien n'est cassé dans le
  build d'aujourd'hui, `g_lang` reste 0 ») est **fausse**. C'est cassé à `g_lang = 0`, dès
  qu'une traduction ajoute un caractère à une scène ;
- `_check_vram_lang_budget` sous-estime aussi : il compare langue par langue (22 tuiles dans le
  cas ci-dessus) là où le chargement réel est l'union (24). Il repère la bonne famille de cas,
  jamais la bonne quantité.

### Décisions verrouillées

1. **La réservation se dimensionne sur l'UNION, exactement comme le chargement.**
   `scene_text_reservation` appelle `scene_codepoints_union` — le même calcul que
   `_emit_font_subsets`, ce que son propre docstring réclamait déjà (« les laisser diverger
   validerait un budget que le placement ne tient pas »). Son paramètre `code` disparaît avec son
   dernier appelant : la réservation ne dépend plus d'une langue, elle les tient toutes.

2. **`_check_vram_lang_budget` disparaît avec la question qu'il posait.** « Quelle langue
   chargerait le plus de glyphes ? » n'a plus de sens quand la scène charge l'union en
   permanence : il n'y a plus de pire langue, il y a un coût, et c'est le budget de tuiles
   existant — **bloquant**, pas un avertissement — qui le juge sur des chiffres désormais
   justes. Un garde-fou de moins pour une garantie plus forte ; son fichier de tests est
   réécrit pour prouver l'égalité `réservé == chargé` plutôt que l'ancienne comparaison.

3. **L'écran de choix de la langue ne demande RIEN au moteur.** La question ouverte depuis
   l'ouverture du jalon (« afficher “Deutsch / 日本語” demande deux écritures avant tout choix »)
   se referme d'elle-même une fois la décision 1 appliquée : un endonyme est une entrée de la
   table comme une autre, l'union par scène couvre donc les deux écritures, la réservation les
   tient, et `_check_font_coverage` nomme un glyphe absent de la planche. Ce qui reste est une
   **recette** dans le [guide de scripting](docs/scripting.md), pas du code — avec sa règle : les entrées
   d'endonymes se laissent NON TRADUITES, pour que le menu se lise pareil quelle que soit la
   langue active (le repli sur la source, décision d'origine, fait exactement ce travail).

4. **La langue n'est pas un état du moteur : elle reste une globale persistante.** Le moteur ne
   connaît ni scène courante ni position d'acteur — il n'a pas de raison de connaître une
   langue, et lui donner sa propre zone de SRAM créerait un second format de sauvegarde à tenir.
   L'aller-retour s'écrit déjà avec ce qui existe : `global.langue = lang.get()` puis
   `save.write(slot)`, et au démarrage `lang.set(global.langue)` — **qui compile déjà**
   (`_check_args` laisse passer un argument non littéral, `_resolve_arg` retombe sur `_expr`, le
   C émis est `lang_set(g_langue)`). Ce qui manque n'est donc pas une API, c'est **une borne** :
   `lang_set` accepte aujourd'hui n'importe quel entier et `g_texts[g_lang]` sortirait de la
   table. D'où `g_lang_count` émis à côté de `g_font_count`, et un refus silencieux d'un code
   hors bornes — même geste que `text_set_font`, qui borne déjà sur `g_font_count`.
   Contrepartie assumée, à documenter : le choix de langue vit dans un emplacement de
   sauvegarde, donc effacer cet emplacement l'oublie. Dédier un emplacement aux préférences
   est un choix de jeu, pas une règle du moteur.

5. **Le build compte les trous et les nomme** — décision verrouillée à l'ouverture du jalon,
   jamais implémentée. `validator._check_translation_holes`, même contrat que ses deux voisins
   de la phase 3 : avertissement, silencieux en projet monolingue, un message par langue qui
   donne le compte et cite les premières clés. Le compte existait déjà dans l'ÉDITEUR (le badge
   par onglet, phase 2) ; il manquait là où quelqu'un fabrique une cartouche.

6. **Pas d'export/import tableur pour le traducteur** — la question ouverte se ferme par un
   refus écrit, pas par un report. Les sides sont déjà du JSON joint par id, diffable en git et
   relisible par un humain ; et l'atelier de la phase 2 donne au traducteur le balisage, la
   coloration et l'aperçu écran qu'un tableur ne rendra jamais. Un aller-retour CSV serait un
   **second chemin d'écriture** dans la même donnée, sans moyen de garantir qu'un `[speed=6]`
   ou un `$variable` en revienne valide — c'est-à-dire le risque de casser du texte pour gagner
   un confort que l'écran couvre déjà. À rouvrir le jour où un vrai traducteur extérieur le
   demande, avec ses contraintes à lui.

### Ordre d'implémentation

Chaque étape laisse le projet buildable.

| # | Étape | Ce qu'elle change | Ce qu'elle NE change PAS |
| --- | --- | --- | --- |
| 5.1 | La réservation sur l'union | `scene_text_reservation` perd son `code` et compte l'union ; `_check_vram_lang_budget` est retiré | Un projet monolingue : union = source, chiffres identiques |
| 5.2 | `lang_set` borné | `g_lang_count` émis, `lang_set` refuse un code hors bornes | `lang.set("fr")` littéral, résolu au build comme avant |
| 5.3 | Le compte des trous | `_check_translation_holes` | Le build lui-même — c'est un avertissement |
| 5.4 | La recette du menu | Guide de scripting : choisir sa langue, la sauver, la relire | Aucune ligne de moteur |

**Ce que la phase 5 a posé** (2026-09-02) : les quatre étapes sont codées et couvertes par
25 tests (`test_vram_lang_budget.py` réécrit, `test_translation_holes.py` neuf,
`test_lang_api.py` étendu) — 380 au total, aucun régressé.

- **5.1** — `scene_text_reservation` perd son paramètre `code` et compte
  `scene_codepoints_union` sur `_declared_lang_codes(p)`, le point unique que partage désormais
  `_emit_font_subsets`. `_check_vram_lang_budget` retiré : sa question (« quelle langue
  chargerait le plus ? ») n'existe plus, et le budget de tuiles — **bloquant** — la remplace
  sur des chiffres justes. Le fichier de tests correspondant ne compare plus deux langues, il
  prouve l'égalité `réservé == chargé`, ce que rien ne protégeait.
- **5.2** — `g_lang_count` émis à côté de la dimension de `g_texts`, et `lang_set` refuse un
  code hors bornes en SILENCE (garder la langue en cours plutôt que ramener le joueur à la
  source : une sauvegarde peut venir d'une version du jeu qui avait plus de langues). Fait
  découvert en ouvrant l'étape et qui l'a réduite de moitié : **`lang.set(global.langue)`
  compilait déjà** — `_check_args` laisse passer tout argument non littéral, `_resolve_arg`
  retombe sur `_expr`, le C émis est `lang_set(g_langue)`. Il n'y avait donc pas d'API à
  ajouter, seulement une borne à poser et une forme à nommer dans les tests pour qu'un futur
  durcissement des domaines ne la retire pas sans le savoir.
- **5.3** — `validator._check_translation_holes` : un message par langue, le compte et les
  trois premières clés. Une entrée dont la SOURCE est vide n'est pas comptée — il n'y a rien à
  traduire, et l'écran Texte le montre déjà en colonne Content.
- **5.4** — la recette dans le [guide de scripting](docs/scripting.md) (« Choisir sa langue, et s'en
  souvenir »), vérifiée en la compilant telle qu'elle est écrite : zéro message de checker,
  `lang_set(LANG_FR)` et `lang_set(save_read_var(0, GLOBAL_LANGUE))` dans le C émis.

**Validée par le jeu réel (2026-09-05).** La règle du projet — ne pas croire un chantier qui
touche la VRAM sur des tests unitaires seuls — a été tenue : un vrai projet multilingue (source
EN, traductions FR et JA non-latine, écran de choix de langue, bascule `lang.set` en jeu) a été
buildé et joué. Ce que le jeu a révélé et qui a été corrigé : la réservation VRAM comptait bien
l'union des codepoints (5.1) mais **l'ensemble des polices chargées ignorait les cibles de remap
de langue** — une scène rendait, dans une langue, avec une police jamais copiée. Corrigé en
faisant de `scene_font_names` une 4ᵉ source (les cibles de remap).

Dans la foulée, une **police par défaut du projet (« Default Font »)** a été ajoutée : à la fois
police de scène par défaut et **repli de couverture** (surchargeable par scène). Un caractère
absent de la police active — typiquement un texte laissé dans la langue source, latin, sous une
écriture japonaise qui n'a pas ses lettres — se rend depuis le repli au lieu de disparaître ; le
repli n'est **jamais remappé** par la langue (c'est le dernier recours), et le garde-fou de
couverture n'avertit que si ni l'active ni le repli ne portent le caractère.

---

## Raccordement build vectoriel — **LIVRÉ**

> **Livré le 2026-09-12.** Le build matérialise un
> `FontAsset` en `RasterGlyph` éphémères, puis en tuiles 4bpp : la même police
> sert à l'émission C, au choix tilemap/composition et au budget VRAM. Aucune
> planche dérivée n'est écrite ; les sources bitmap et les projets antérieurs
> conservent leur chemin historique.

### La chaîne, en une ligne

```
Font (source) → Glyph → RasterGlyph → représentation GBA
```

Chaque flèche est une couche, et chacune ignore les suivantes. Le `Glyph` est le caractère et
ses métriques ; le `RasterGlyph` est sa forme rasterisée, **indépendante du format GBA** ; la
conversion en tuiles et palette n'arrive qu'à l'export. Le bitmap est une représentation de
**rendu**, jamais le modèle principal du texte.

### Les couches, et où chacune vit

| Couche | Nature | Où | État |
| --- | --- | --- | --- |
| **`Font`** | source de glyphes — l'intrinsèque *disponible* dans le fichier (glyphes présents, codepoints, métriques) | sidecar `.json` à côté de la source, dans `assets/fonts/` (inchangé) | livré |
| **`Glyph`** | caractère + métriques (rect ou vectoriel, `advance`, `ox/oy`) | dans le sidecar `Font` | existe |
| **`FontAsset`** | usage projet : sources par variante (regular / bold / italic / bold italic), ordre de fallback, params de traitement (taille de rendu, cellule cible, bpp, seuil/dither, chasse) | un `.json` par asset, dans `project/fonts_assets/` | livré |
| **`RasterGlyph`** | forme bitmap d'un glyphe, **grille de couverture** (gris/alpha), sans index GBA | calculé à la demande pour l'aperçu et le build | livré |
| **`Text` / `TextStyle` / `Layout` / `TextEffect`** | contenu / apparence / placement / transformations | en aval — **hors de ce jalon** | partiels |
| **Build** | résout `FontAsset` → sous-ensemble requis → rasterise → tuiles + palette | `codegen/font_build.py` puis `font_emit.py` | premier raccord livré |

**Le `FontAsset` ne duplique jamais les données intrinsèques d'un `Font`.** Le sidecar décrit la
ressource ; le `FontAsset` décrit son usage. C'est pourquoi `bg_color` / `space_color` — qui
disent *comment lire* une planche bitmap — quittent `Font` pour devenir des params de traitement
du `FontAsset`, spécifiques aux sources bitmap : une source vectorielle n'a ni fond à trouer ni
chasse à mesurer, le rasterizer lui donne couverture et métriques directement.

### La chaîne de couverture — et ce que la langue conserve

Un `FontAsset` est une **police logique** qui résout **chaque codepoint requis** par une
**chaîne ordonnée de sources**. Un codepoint prend la première source de la chaîne qui sait le
rendre :

```
dialog (FontAsset)
  1. source primaire   (regular / bold / italic…)   ← couvre le Latin
  2. fallback          (ark-pixel-ja)                ← couvre ce que 1 ne couvre pas
```

L'axe n'est **pas la langue**, c'est la **couverture de glyphes** ; la langue ne fait qu'induire
quels codepoints sont requis — ce que `scene_codepoints()` calcule déjà, sur l'union des langues.
Une police Unicode « juste marche » (la chaîne ne retombe jamais) ; une police pixel Latin-only
reçoit un fallback pour les écritures qu'elle ne couvre pas, sans qu'on nomme jamais une langue.

La chaîne de couverture ne remplace pas le choix produit « police par défaut de la langue » :
`Language.default_font` peut remapper la police par défaut du projet, tandis que les fallbacks
d'un `FontAsset` résolvent les caractères absents DANS cette police. Le runtime conserve donc
`g_lang_font` pour ce premier choix, puis le build matérialise la recette de l'asset retenu. La
scène nomme toujours la police logique par défaut ; la décision doit être reflétée au build dans
le sous-ensemble, la palette et la surface de composition.

### Le rasterizer est appelé par le build

`FontRasterizer` est une **fonction pure** `(source, glyphe, params) → RasterGlyph`. L'aperçu
de l'éditeur et `codegen/font_build.py` l'appellent ; le build ne possède donc aucune seconde
implémentation. C'est la règle qu'on tient déjà ailleurs (`is_proportional()` partagé
par l'émetteur et l'aperçu, `key_out()` qui reflète `key_colors()`) : si l'aperçu et l'émetteur
divergent, le canvas ment sur ce qui part en ROM.

- **La rasterisation est résolue au BUILD, jamais au runtime.** Le jeu ne comprend aucun TTF/OTF
  — il ne manipule que des données de police déjà préparées pour la GBA. Le `RasterGlyph` n'est
  calculé que pour le **sous-ensemble requis** (clés de texte littérales, imposées par le
  checker) : la propriété « jeu fini d'images de glyphes » ne vit plus dans la *source* mais dans
  la *sortie de build* — et c'est suffisant pour garder le sous-ensemble par scène, le garde-fou
  VRAM et le CJK.
- **`RasterGlyph` = grille de couverture, pas d'index GBA.** Une source vectorielle produit de
  l'anti-crénelage naturel ; une source bitmap indexée donne une couverture binaire. La
  **quantisation couverture → N index de palette** (seuil ou dither) est l'étape *export GBA*,
  dans `font_emit._encode_raster_font()`.
  C'est cette grille abstraite, gardée jusqu'au dernier moment, qui rendra les couleurs, styles
  et effets simples à implémenter dans leur jalon à eux.
- **La preview ne persiste rien.** La différence nette avec le point d'entrée FreeType supprimé
  le 2026-09-03 (chantier *Les formats acceptés à l'import*) : ce hack rasterisait **à l'import**
  et **écrivait un PNG comme asset**. `FontRasterizer` rasterise **à la demande** (build +
  aperçu) et ne persiste que le `.json` du `FontAsset`. Ce n'est pas une ré-addition du hack,
  c'est un étage de première classe qui le remplace — et il ramène `freetype-py`, cette fois
  comme dépendance de **build**, documentée.

### Décisions verrouillées

- **Séparation stricte des couches.** `Font` ne connaît ni traductions, ni effets, ni layout, ni
  couleurs. `FontAsset` ne duplique pas l'intrinsèque de `Font`. `RasterGlyph` ignore le format
  GBA. La conversion GBA vit au build, et nulle part avant.
- **La résolution passe par la couverture, pas par la langue.** Un `FontAsset` = une chaîne
  ordonnée de sources ; un codepoint prend la première qui le couvre.
- **La primaire du `FontAsset` gouverne l'interligne** ; les glyphes de fallback s'y alignent.
  Une ligne mixte (rare — une traduction est presque toujours mono-script) reste donc régulière.
  Un override par plage de codepoints est une **porte** laissée ouverte, pas une fonctionnalité
  de ce jalon.
- **Un seul `FontRasterizer`, appelé par le build ET l'aperçu.** Résolution au build, jamais au
  runtime ; aucune persistance d'asset généré.
- **Deux dossiers, deux natures.** Les sources restent dans `assets/fonts/` (inchangé) — le
  fichier importé et son sidecar `Font`, l'intrinsèque. Les `FontAsset` vivent dans
  `project/fonts_assets/`, un fichier par asset, avec identité et référençables par nom, comme
  une palette. `assets/` = source décrite, `project/` = objet moteur ; aucune migration.
- **Bold / italic = faces NATIVES de la source, pas de synthèse.** Si la source vectorielle
  porte nativement ses faces bold / italic / bold-italic, le rasterizer les rend ; sinon la
  variante n'existe pas — une planche PNG n'a pas de style. Pas de faux-gras ni de cisaillement
  (le faux-gras sur une police pixel est laid). La synthèse reste une **porte** ultérieure
  (« pour l'instant »).

### Ce que ce jalon précise dans la v0.9

Trois décisions verrouillées de la v0.9 (section Traduction) sont **précisées** ici — signalées
là-bas par un renvoi vers ce jalon, pour ne pas laisser deux vérités vivantes :

- « Une langue n'a pas de police : elle a éventuellement un REMPLACEMENT » → la substitution
  de `Language.default_font` reste le choix de police par défaut de la langue ; la couverture
  du `FontAsset` ajoute des replis de caractères dans cette police, sans multiplier les
  remplacements.
- « Une scène ne change jamais de police selon la langue… par une table de remap » → la scène
  nomme toujours `dialog` ; `g_lang_font` conserve le remap de la police par défaut et la
  chaîne de couverture résout ensuite les caractères absents. `font_de.fnt` ne crée jamais ce
  lien automatiquement.
- « PNG et `.fnt` seulement… un TTF rendu au build ne donnerait pas ça » → les sources
  vectorielles sont acceptées via `FontRasterizer` ; le « jeu fini de glyphes » se déplace de la
  source vers la sortie de build, et l'argument tient toujours.

### Prolongements hors v0.26

- **Le seuil / dither** couverture → index : réglage par `FontAsset`, ou déduit du bpp cible ?
- **`TextStyle` / `TextEffect`** : leur propre jalon, en aval — ce qu'il faut, c'est que la
  grille de couverture reste manipulable jusqu'à l'export pour qu'ils restent simples.

### Ce que le raccordement build touche

| Fichier | Ce qui change |
| --- | --- |
| `core/models/font_asset.py` | **création** — `FontAsset` (chaîne de sources, variantes, params de traitement) |
| `core/font_rasterizer.py` | **création** — `FontRasterizer` (fonction pure) + `RasterGlyph` |
| `core/models/font.py` | dégraissage : `bg_color`/`space_color` sortent vers `FontAsset` ; `Font` devient source intrinsèque, vectorielle ou bitmap |
| `core/font_import.py` | lecture de source + extraction cmap/métriques ; plus aucun point d'entrée qui *fabrique* une planche |
| `codegen/font_emit.py` | réorganisé autour de `RasterGlyph` ; `emit_lang_fonts_c` conserve le remplacement de la police par défaut par langue |
| `codegen/runtime_codegen/main_gen.py` | émet les tables de `FontAsset` et le remap de police par langue |
| `core/models/settings.py` | `Language.default_font` conserve le choix de police par défaut de chaque langue |
| `ui/scene_manager/inspectors/languages_card.py` | la carte expose ce choix de police par défaut |
| `runtime/include/gba_engine.h` | `g_lang_font` remappe la police par défaut ; le rendu et la réservation tiennent compte de la police effective |
| `core/project_paths.py` | `fonts_assets_dir` ajouté (`project/fonts_assets/`) ; `assets/fonts/` inchangé |
| `core/project.py` | `ResourceStore[FontAsset]` monté sur `fonts_assets_dir` |
| `core/resources/asset_reconciliation.py` | synchro : sidecar `Font` (`assets/fonts/`) distinct du `FontAsset` (`project/fonts_assets/`) |
| `tests/` | `test_lang_font_remap.py` supprimé, sondes natives nettoyées ; tests neufs `FontRasterizer`/`FontAsset`/couverture |
| `requirements.txt` | `freetype-py` revient comme dépendance de build |
| `ARCHITECTURE.md` | la section police réécrite autour des couches (fait à l'étape suivante) |

---

## v0.10 — Distribution élargie

Deux choses tenaient sous le même toit dès qu'on a voulu livrer ailleurs que sur Windows, et
elles se répondent. La construction Linux (AppImage) est écrite depuis longtemps mais **en
pause** dans la CI : le job attend d'être validé sur une vraie distribution avant d'être
rallumé. Et le lanceur qu'un projet neuf posait à côté de lui — un `<Nom>.bat` — ne veut rien
dire hors Windows : sous Linux, le double-clic censé ouvrir l'éditeur sur ce projet tombait sur
un fichier inerte.

La réponse aux deux est la même : **un point d'entrée qui ne dépend pas de l'OS**. Pas un
script par plateforme, mais un **fichier de projet** que les deux systèmes savent associer à
l'éditeur — `<Nom>.gba-project`.

### Le format `.gba-project` — le manifeste EST le point d'entrée

Aujourd'hui un projet est un dossier, et `project.json` en est le manifeste (les réglages
globaux). Le `.bat` était un second fichier, à côté, dont le seul rôle était d'être
double-cliqué. Deux fichiers pour une seule identité — exactement ce que « source de vérité
unique » interdit.

`<Nom>.gba-project` **remplace** `project.json`. Même contenu (le JSON des réglages, format
`core/project_json.py`), même rôle de manifeste — mais c'est lui qu'on double-clique, et son
extension est ce que l'OS associe à l'éditeur. Un seul fichier porte l'identité du projet et
sert de porte d'entrée.

### Décisions verrouillées

- **Le nom du projet EST le nom du fichier.** Puisque le manifeste s'appelle
  `<Nom>.gba-project`, le stem est la seule source du nom — la clé `name` **sort du JSON**.
  Sans ça, trois porteurs se contrediraient (le dossier, le fichier, la clé). Renommer un
  projet, c'est renommer son `.gba-project` ; `settings.name` se lit sur le fichier.
- **Le `.bat` disparaît.** Il n'est pas porté sur Linux, il est retiré. Le `.gba-project` fait
  son travail sur les deux OS, et un seul mécanisme vaut mieux qu'un par plateforme. Ce qui
  écrivait le `.bat` dans `Project.create` s'en va avec.
- **Les projets d'avant se relisent, sans convertisseur.** Même règle que partout ailleurs
  (cf. l'en-tête de `core/project.py`) : un dossier sans `.gba-project` mais avec un
  `project.json` s'ouvre par lecture tolérante du legacy, et **la première sauvegarde réécrit
  dans la nouvelle forme** — le `.gba-project` est créé, le `project.json` supprimé. Rien à
  lancer à la main.
- **Zéro ou plusieurs manifestes : refus explicite.** L'ouverture par dossier (le picker, les
  récents, `--project`) cherche l'unique `*.gba-project`. Exactement un → il l'ouvre. Zéro →
  on tente le pont legacy ci-dessus, et à défaut « ce n'est pas un projet ». Plusieurs → refus
  clair (« plusieurs manifestes, gardez-en un ») : l'éditeur ne choisit pas à la place de
  l'auteur. À la création il y en a toujours exactement un ; deux, c'est une copie manuelle,
  un cas anormal qu'on signale au lieu de deviner.
- **Un `.gba-project` en argument ouvre directement.** Le double-clic fait lancer par l'OS
  `app "<chemin>/<Nom>.gba-project"`. `main.py` accepte donc ce chemin en argument positionnel
  (la racine du projet est le dossier parent) et saute l'écran d'accueil, comme le fait déjà
  `--project <dossier>`. Les deux formes coexistent : le fichier pour le double-clic, le
  dossier pour le picker.

### L'association, deux fois — une par OS

Le fichier ne se double-clique que si le système sait à qui le donner. C'est le seul endroit
où la plomberie diffère entre plateformes, et elle est entièrement dans le packaging, pas dans
l'éditeur.

- **Linux.** Le `.desktop` de l'AppImage déclare `MimeType=application/x-gba-project;` et passe
  le fichier avec le code de champ `%f` (`Exec="GBA Editor" %f`). Un fichier neuf,
  `packaging/linux/gba-project.xml`, déclare le type MIME lui-même (glob `*.gba-project`) ; le
  workflow l'installe dans l'AppDir (`usr/share/mime/packages/`).
- **Windows.** L'installateur NSIS enregistre `.gba-project` → un ProgID `GBAEditor.Project` →
  `"GBA Editor.exe" "%1"`, avec l'icône de l'application, et **défait** l'enregistrement à la
  désinstallation. Le ZIP portable, lui, n'enregistre rien (il ne s'installe pas) : le
  double-clic n'y marche qu'après une installation, l'ouverture par le picker marche toujours.

### Réactivation du build Linux

Le job `build-linux-appimage` repasse de `if: false` à `if: true` et rejoint les `needs` +
le `download-artifact` de `publish` — le commentaire en tête de `release.yml` décrit déjà le
geste exact. La vraie distribution de test, faute de Linux local, **est** le runner
`ubuntu-latest` : un `workflow_dispatch` produit l'AppImage en artefact, sans publier de
release.

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût récurrent — « Linux seul » est
  une option valable si le coût ne se justifie pas.
- Sur quelle version de glibc l'AppImage se cale-t-il ? Le runner `ubuntu-latest` monte de
  version au fil du temps, et un AppImage compilé sur une glibc récente ne démarre pas sur une
  distribution plus ancienne. À trancher au moment du test réel, la donnée du moment valant
  mieux qu'une supposition.

---

## v0.11 — Traduction de l'interface de l'éditeur — **LIVRÉE (infra), traduction FR reportée à v2.0**

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

### Le deuxième temps — l'extraction des libellés (2026-09-08 →)

La question laissée ouverte au premier temps — « les libellés partagent-ils le catalogue des
notices ou vivent-ils à côté ? » — est tranchée : **un catalogue à côté**. Un libellé n'a ni
ton ni niveau ; les fondre dans les notices aurait mis un champ mort dans chaque entrée. La
mécanique commune (maître + side, join par clé, repli sur la source, pluriel, `set_language`)
est remontée dans `ui/common/catalog.py`, et `notice.py` a été refondu dessus. Un second
catalogue frère, `ui/common/labels.py` + `labels/labels.json`, expose `label("clé", **args)` —
pour les libellés de champs, titres de cartes et d'écrans, entrées de menu, états vides,
boutons et les `setToolTip` posés à la main. Le contrôle de CI vérifie désormais les DEUX
catalogues dans les deux sens.

**Extraction faite sur tout le périmètre de l'UI (~1 270 libellés).** Menée en deux temps :
d'abord les gros écrans à la main — `settings_dialog`, `home/project_picker`, la fenêtre
principale (`window.py` — menus, barre d'outils, status bar), les inspecteurs du Scene
Manager, les éditeurs de composants, `scene_tree_panel`, `assets_finder_panel`, `sound_mixer`,
`sprite_editor`, `data_editor`, et les zones `palette_editor`/`text_editor`/`script_editor` ;
puis une passe outillée sur la longue traîne (widgets communs, canvas, imports, finders).
Les deux conventions de clés qui ont coexisté un temps (`<écran>.<slug>` court et
`<fichier>.<slug>`) ont été **unifiées** sur la première, avec des atomes `common.*` partagés
(52, traduits une seule fois). Les résidus français croisés en chemin ont été migrés à
l'anglais (règle de migration écran par écran).

Politique de la première passe : on laissait HORS catalogue les libellés d'annulation
(`SetFieldCmd label=…`, corpus du menu Undo à part), les identifiants qui doublent comme
libellé (`COLUMN_TYPES`, `NO_CATEGORY`…), les noms de format techniques (BGR555, PNG), les
titres d'`AssetFinder` (passe séparée), et les blocs de diagnostic très interpolés (à reprendre
en clés-phrases à arguments nommés). Piège récurrent noté : une variable locale nommée `label`
masque la fonction importée — grep systématique après chaque fichier. La passe de clôture
ci-dessous extrait aussi les titres de finders et les diagnostics formulés dans l'UI ;
les autres exceptions sont précisées dans [docs/development/ui-text.md](docs/development/ui-text.md).

### Ouvert

- **La sélection de langue est livrée.** Le panneau *Settings → Interface* écrit le code dans
  les préférences d'application, puis le catalogue le charge avant la construction des écrans
  au démarrage suivant. Le choix ne vit donc jamais dans le projet. Les widgets construits
  figent leur texte : demander un redémarrage donne une interface entièrement cohérente plutôt
  qu'une retraduction partielle. Un premier side français d'amorçage couvre les réglages,
  l'accueil et les atomes `common.*` ; les clés qui manquent retombent sur le maître. **La
  traduction française complète est reportée au chantier « traduction fr » (v2.0)** : l'infra
  la rend possible sans qu'aucune ligne de code ne change, ce n'est plus qu'un travail de
  contenu, sans dépendance technique.
- **Extraction de l'interface terminée sur le périmètre défini** : inspecteurs, widgets
  communs, build, canvas, imports et finders passent par le catalogue, désormais à 1 270
  libellés. Les tables portent des clés résolues à l'affichage ; les identifiants de
  sélection restent stables. `tools/check_ui_text.py` vérifie structure, paramètres,
  clés et textes directs ciblés, avec exceptions justifiées. Voir
  [le contrat et ses limites](docs/development/ui-text.md). La traduction française est reportée à v2.0.
  Le choix de langue ne change aucun texte avant le redémarrage, y compris dans les
  panneaux ouverts après le changement de préférence.
- **Les messages du validateur** (`core/validator.py`, ~40 phrases) sont l'autre corpus déjà
  centralisé, et le plus proche : ils ont une gravité, et le rouge y a un sens. Ils partiront
  probablement dans le même catalogue avec un ton `error` que le gabarit d'inspecteur n'offre
  pas — à décider quand ce sera leur tour, pas avant.
- **Une astuce peut être fermée pour la session.** La croix existe déjà dans `NoticeBox` ;
  le réglage global gouverne toutes les astuces. Une fermeture individuelle persistante
  reste hors périmètre.

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
- **La position des nœuds — tranché** (voir « Mémorisation de position » ci-dessous).
- **Les autres relations.** Prefabs, mises en page, caméras et fonds forment déjà un graphe de
  dépendances par les mêmes domaines. Les faire entrer dans la même vue est tentant et
  probablement illisible ; à rouvrir une fois le graphe des scènes utilisé pour de vrai.

### Fondation Canvas — contrat pour v0.12 et les vues futures

Le Canvas reste la surface centrale du Scene Manager. Il accueille deux vues aujourd'hui : la
scène et le graphe. La scène choisit elle-même son rendu : 2D maintenant, 3D quand son mode de
rendu le demandera. **Ce n'est pas un bouton de plus.** Le Graphe de scènes est le seul
basculement explicite dans la barre existante ; la palette d'outils flottante reste à sa place
et le reste de la fenêtre (arbre, inspecteur, console) ne change pas de propriétaire.

- **`CanvasWorkspace` est le conteneur, pas un second SceneEditor.** Il contient la vue de
  scène existante et une future `SceneGraphView`. `SceneEditor` ne reçoit ni nœuds ni arêtes :
  il garde l'édition/rendu de la scène. Cette frontière évite qu'il redevienne un monolithe
  après son extraction récente en `canvas_view`, `canvas_scene`, `canvas_items`,
  `canvas_toolbar`, `canvas_raster` et `canvas_controllers`.
- **La projection du graphe est pure.** Un module du domaine scripting (au voisinage de
  `index_refs_in_project`) rend des nœuds, arêtes et `LuaRef`, sans Qt. La vue les dessine et
  envoie les sélections ; elle ne reparcourt pas les scripts et ne possède aucune donnée.
- **Les points d'entrée UI sont publics.** La fenêtre ne doit pas appeler les méthodes privées
  du canvas ou des inspecteurs (`_reload_*`, `_save_*`, sous-inspecteurs) pour les nouveaux
  branchements. Les exposer sous quelques opérations de façade avant d'ajouter le graphe
  réduira le couplage déjà concentré dans `window.py`.
- **Les bus restent distincts.** Le `SelectionBus` porte une intention de sélection ; le
  `CommandDispatcher` annonce les mutations et rafraîchissements. Les fusionner mélangerait
  deux temporalités et n'apporte rien au graphe.
- **Hygiène de branche avant les gros changements.** Normaliser les fins de lignes dans
  `.gitattributes` : une variation globale masque les vrais diffs et rend la revue de cette
  surface coûteuse. Le contrôle d'architecture et les tests Canvas doivent être lancés dans
  l'environnement de développement fonctionnel avant toute extraction supplémentaire.

### Plan d'implémentation — première surface lisible

La première tranche vise une carte utile des transitions **connues** : elle ne tente ni de
créer du code ni de déduire le flux d'exécution. Les cibles calculées restent hors de la surface
tant que leur représentation explicite (`?`) n'est pas décidée. Le résultat attendu est une vue
qu'on peut lire, ouvrir et quitter sans changer le comportement du Canvas 2D.

1. **Projection de domaine — livré.** `scripting.scene_graph.scene_graph(project)` rend des
   `SceneGraphNode` et `SceneGraphEdge`, sans Qt ni persistance. Chaque arête conserve ses
   `LuaRef` (fichier, ligne, offsets) et agrège les appels de même source vers même cible ; une
   cible absente reste une arête visible, jamais une fausse scène. La couverture protège le
   commentaire non exécutable, l'agrégation, la scène de départ et l'argument calculé.
2. **Vue isolée — livré.** Créer `SceneGraphView` comme `QWidget` autonome de
   `ui/scene_manager/`, avec sa propre scène et sa propre vue graphiques. Elle reçoit le
   `SceneGraph` déjà projeté : elle ne lit aucun script, ne connaît aucune règle Lua et ne
   possède ni nœuds de domaine ni données à sauver.

   **Recalcul — pull à l'activation, mémoïsé sur une empreinte.** La projection est
   recalculée quand on affiche la vue, jamais mise en cache de façon persistante : il n'y a
   ni graphe sérialisé ni seconde source de vérité. Mais `scene_graph` relit et re-parse
   chaque `.lua` (luaparser), coûteux dès quelques dizaines de scènes ; on le mémoïse donc
   sur une **empreinte** = `file_stamp`/mtimes des scripts + noms de scènes + `start_scene`.
   Empreinte inchangée → on réutilise le dernier `SceneGraph` ; empreinte changée → recalcul.
   `scene_graph(project)` **reste pur** (aucun cache dedans) ; la mémoïsation vit dans la vue
   ou un petit projecteur qui l'enveloppe. Le graphe reflète les scripts **sur disque** : après
   une édition dans le Script Editor, il se rafraîchit à la sauvegarde, ce qui est le
   comportement honnête d'une citation.
3. **Rendu initial — livré.** Dessiner les scènes comme cartes portant leur nom ; marquer la scène de
   démarrage ; dessiner les arêtes dirigées et un compteur quand leurs `LuaRef` sont multiples.
   Une destination inexistante est rendue comme **marqueur terminal d'erreur de liaison** :
   à l'écran une petite carte barrée d'un ✕, mais ce n'est PAS un `SceneGraphNode`. Il n'a pas
   de `is_start`, n'entre pas dans le `SelectionBus`, ne se renomme pas, et son double-clic
   n'ouvre aucune scène. Un seul marqueur par nom manquant, même si plusieurs scènes le citent :
   le fait est « ce nom n'existe pas », pas « plusieurs erreurs ». Le style doit rester lisible
   à petite échelle, y compris pour une boucle.
4. **Disposition automatique stable — livré** (module pur `scene_graph_layout`). Poser les nœuds par couches de dépendances, de gauche à
   droite, puis ranger les scènes isolées sans chevauchement. Les cycles et les retours ne
   modifient pas l'ordre des nœuds : ils se dessinent en courbe. Cette tranche ne mémorise aucune
   position ; un sidecar de disposition ne viendra qu'avec la décision correspondante.
5. **Intégration au Canvas — livré.** Enregistrer la vue sous la constante `GRAPH_VIEW = "graph"`
   (symétrique à `SCENE_VIEW`) dans `CanvasWorkspace` et ajouter le seul basculement explicite
   « Scène / Graphe ». Changer de vue ne recharge pas la scène active, ne modifie pas l'arbre ni
   l'inspecteur, et revenir à « Scène » retrouve l'éditeur 2D inchangé.

   **Déviation actée — le basculement vit sur le `CanvasWorkspace`, pas dans `CanvasTopBar`.**
   La « barre existante » du Canvas (`CanvasTopBar` : zoom, toggles) appartient au `SceneEditor`
   et disparaît avec lui dans l'empilement exclusif ; elle ne peut donc pas héberger un
   basculement qui doit rester visible en mode Graphe pour permettre le retour. Le `CanvasWorkspace`
   porte un bandeau persistant à deux segments au-dessus des deux vues. La `CanvasTopBar` reste au
   `SceneEditor` pour les contrôles propres à la scène ; la vue Graphe aura les siens plus tard.
6. **Navigation et inspection — livré.** Un clic sur une scène sélectionne cette scène via le
   `SelectionBus` ; son double-clic revient au Canvas de scène et l'ouvre. Un clic sur une arête
   expose ses appels agrégés ; son double-clic ouvre le Script Editor à la ligne de l'appel.
   Retargeter le littéral, groupes, annotations, mini-carte et création de transition étaient
   hors de cette première surface ; les groupes, notes textuelles et mini-carte sont depuis livrés.
7. **Tests de contrat — livré.** Couvrir la projection sans Qt, la bascule `CanvasWorkspace`, le rendu
   vide/simple/agrégé, la cible absente et les deux gestes de navigation. Les tests existants du
   Canvas 2D restent le garde-fou : le graphe n'est jamais une extension de `SceneEditor`.

**Première surface lisible — livrée.** Les sept tranches sont en place ; 26 tests dédiés
(projection et disposition purs, vue mémoïsée, rendu, bascule et paresse du workspace, deux gestes
de navigation), le garde-fou Canvas 2D intact. Ce qui reste ouvert n'est pas de cette tranche :
le **routage** des arêtes (elles peuvent encore se croiser), la **mémorisation de position**
le **retargetage du littéral**, et la **représentation explicite des cibles calculées** —
chacun attend sa propre décision. La **mémorisation de position**, elle, est désormais tranchée
(ci-dessous).

### Mémorisation de position — décidé

La première surface ne mémorisait rien : relayout à chaque affichage. Sur un RPG de quarante
scènes, une carte qu'on ne peut pas ranger à sa main ne tient pas ; on autorise donc le
déplacement et on le retient. La règle « le graphe est dérivé, pas de seconde source de vérité »
n'est pas violée : elle interdit de sérialiser la **structure** (nœuds/arêtes, qui reste dérivée
des scripts) ; une position est de la **présentation**, pas de la structure.

**Décisions verrouillées :**

- **Un sidecar d'éditeur à responsabilité unique, jamais la `Scene` ni le manifeste.** Une scène
  « n'a rien à savoir de sa position dans une vue », et le manifeste `<Nom>.gba-project` est la
  source de vérité du JEU — y ranger des coordonnées d'éditeur en ferait un second porteur à
  synchroniser. Les positions vivent dans un fichier d'éditeur dédié (non livré en ROM),
  `project/editor/scene-graph.json`, frère de `scene-tree.json` et écrit par le même patron
  (sidecar atomique, orphelins purgés au chargement, clé = nom durable). Sa responsabilité est
  la **présentation du graphe** : les positions des nœuds, rien de plus. Le **rangement** en
  groupes n'est PAS ici — c'est un dossier d'assets de la famille `scenes`, capacité générale
  partagée (`AssetFolderStore`, cf. partie 2). Deux mécanismes de dossiers concurrents seraient
  une seconde source de vérité ; il n'y en a qu'un.
- **Tout est mémorisé ; l'auto-layout n'est plus qu'une graine.** `position(nœud) = sidecar[nom]`
  s'il existe, sinon l'auto-layout par couches calcule une place qui est **aussitôt écrite**. Dès
  le premier affichage, chaque nœud a une position stockée. Conséquence assumée : **stabilité
  plutôt que réactivité** — ajouter ou éditer une autre scène ne fait plus bouger la carte.
- **Le déplacement écrit la position ; « Re-arrange » relance l'auto complet et écrase tout.**
  C'est le seul geste qui re-flue la carte ; il remet chaque nœud à sa place auto et efface les
  positions manuelles. Sans lui, une carte rangée reste rangée.
- **La clé est le nom, avec crochet sur `rename_scene`.** Une scène n'a pas d'id opaque (identité
  = `name`) ; le renommage passe déjà par le choke point unique `Project.rename_scene`, où l'entrée
  du sidecar est déplacée en même temps que les refs de script.
- **Les orphelins sont purgés à la lecture.** Une entrée dont la scène n'existe plus est jetée au
  chargement : le sidecar ne garantit jamais une scène morte.
- **Les marqueurs de cible absente ne sont jamais mémorisés.** Leur identité est un littéral
  volatil ; ils se placent à chaque rendu à droite de la position ACTUELLE de leur source
  (dérivée, jamais stockée).

**Plan d'implémentation :**

1. **Store pur.** Un module lit/écrit le sidecar (nom → (x, y)), purge les orphelins contre la
   liste des scènes, sans Qt. Couverture : aller-retour, purge, absence de fichier = vide.
2. **Graine + matérialisation.** À l'affichage, les nœuds sans entrée reçoivent leur place
   auto-layout, aussitôt écrite ; les autres gardent la leur. `layout_positions` reste la graine,
   inchangé.
3. **Déplacement.** Les `SceneCardItem` deviennent déplaçables ; la fin de déplacement écrit la
   position. Les marqueurs de cible absente, eux, ne se déplacent pas.
4. **Re-arrange.** Une action (barre de la vue Graphe) relance l'auto complet et réécrit tout le
   sidecar. C'est le premier contrôle propre à la vue Graphe annoncé à l'étape 5.
5. **Crochet de renommage.** `rename_scene` déplace l'entrée ; test dédié.
6. **Tests de contrat.** Store pur, matérialisation d'une graine, persistance d'un déplacement,
   reset par Re-arrange, suivi du renommage, purge d'un orphelin.

### Profondeur de rendu — un geste direct, fidèle à la GBA

La profondeur n'est pas un ordre arbitraire « devant/derrière » : c'est une seule échelle
matérielle de priorité `0..3`, où `0` est devant et `3` derrière. Les BG et les OBJ partagent
cette échelle ; à priorité égale, l'OBJ passe devant le BG. Le canvas doit toujours montrer la
même composition que la ROM (`hw_layer_z`), sans opacité ou empilement d'édition qui mentirait.

Le **rail de profondeur** est un outil contextuel de l'acteur, ouvert par clic droit via
« Set priority » : quatre crans clairement nommés `0 avant` à `3 arrière`. Le badge de priorité
de la sélection se glisse verticalement entre ces crans, ou se pose par clic. Le changement est
immédiat, annulable et redessine le canvas ; le déplacement physique de l'acteur reste
exclusivement un geste de position. Ce rail remplace les commandes contextuelles « placer devant
/ derrière » et garde le nombre réel de niveaux perceptible.

L'ordre de deux OBJ à priorité égale doit être explicité et testé : il dépend aujourd'hui de
l'ordre de `scene.actors`, qui détermine aussi les slots OAM au build. Un second geste de
réordonnancement — dans l'arbre de scène existant, ou plus tard dans une liste locale du rail —
doit donc conserver l'ordre des frères sans confondre ce départage avec la priorité GBA.

### Scene Tree — deux projections, deux gestes

Le Scene Tree ne doit pas prétendre répondre à la fois à « qu'est-ce qui appartient à quoi ? »
et à « qu'est-ce qui est dessiné devant quoi ? ». Une parenté acteur peut traverser plusieurs
priorités ; fusionner hiérarchie et pile de rendu rendrait donc au moins l'une des deux fausse.
Le panneau reçoit deux contextes explicites, fondés sur les mêmes données :

- **Contenu** est l'arbre logique actuel : acteurs et leur parenté, caméras, nœuds Interface et
  leurs éléments. Son glisser-déposer signifie organiser, rattacher à un parent ou déplacer un
  frère dans cet arbre.
- **Priorité** est une projection plate de l'ordre de composition GBA, du devant vers le
  derrière : `OBJ 0`, `Background 0`, `OBJ 1`, `Background 1`, `OBJ 2`, `Background 2`,
  `OBJ 3`, `Background 3`. Chaque slot BG est visible, y compris vide ; un slot impossible dans
  le mode vidéo de la scène est explicitement indisponible. Son glisser-déposer entre groupes
  OBJ change `Actor.priority`; dans un même groupe il départage les slots OAM via l'ordre de
  `scene.actors`.

Cliquer une ligne Background sélectionne son slot et mène directement à la ligne correspondante
de l'inspecteur Scene (section ouverte et scrollée). Cela passe par un marqueur de sélection
`BackgroundLayerSelection(scene, bg_slot)`, symétrique de `CameraSelection`, puis une opération
publique `SceneInspector.focus_background_slot(slot)` — pas par un appel direct entre widgets.

### Sous-chantier — la cible de rendu appartient au nœud Interface (par scène)

Le réglage global `Scene.text_bg` décrivait le seul calque de texte historique. C'était, comme le
combobox « UI layer » de l'inspecteur Scene, une **simplification de production** : elle imposait
un unique BG d'UI à toute la scène. Elle devient fausse dès que le contexte Priority matérialise
le z-order et invite l'auteur à ranger **chaque nœud `Interface` indépendamment** dans la pile de
composition. Un nœud posé en Background doit choisir **son** slot ; deux nœuds peuvent viser le même
(ils partagent alors volontairement la même tilemap et s'écrivent dans l'ordre de leurs nœuds — au
recouvrement, le dernier dessin gagne, ce n'est pas une fusion de calques fictive).

Cette évolution ne consiste donc pas à déplacer le combobox. Le moteur actuel tient un seul BG
actif dans `text_set_layer()`, un seul screenblock UI dans `vram_alloc.scene_layout()`, et
`g_ui_regions` est une table globale au projet. Le choix doit devenir disponible au moment où une
zone est écrite, y compris par `text.draw_in()` dans un script.

#### Décision de modèle — verrouillée (2026-09-13)

Le principe qui tranche : **un asset se distingue de sa cible de rendu, et le z-order en fait
partie.** Un `UILayout` est du **contenu réutilisable** (éléments, géométrie, slots, images,
glyphes) — rien de matériel. La **cible de rendu** — ancrage, cible BG/OBJ, acteur suivi, slot BG,
donc la place dans la pile — est un fait **par instance dans une scène**.

Concrètement : `Scene.ui_layouts: list[str]` devient une liste de **nœuds** possédant
`{layout_name, anchor, anchor_actor, target, bg_slot}`. Le chemin matériel que la v0.25 avait
remonté sur l'asset (`anchor`, `target`) **descend sur le nœud** : ce n'est pas défaire la v0.25
mais l'**achever** — elle disait déjà « le nœud possède anchor+target », le nœud n'était
simplement qu'un nom nu faute de corps. L'asset ne connaît plus sa cible.

Conséquence assumée, la contrepartie exacte de la simplification qu'on retire — mais séparée avec
soin, parce que les constantes `REGION_*` / `IMAGE_*` / `UIELEM_*` que citent les scripts sont
indexées par **nom d'élément unique au projet**, donc par asset :

- **Les tables de CONTENU restent per-asset.** `g_ui_regions` (géométrie, police), `g_ui_images` et
  la table de visibilité `UIELEM_*` gardent leur index par nom d'élément — `all_regions` /
  `all_images` / `all_elements` ne changent pas. Rekeyer par nœud casserait l'ABI (un HUD partagé
  ferait apparaître `score` deux fois) ; l'identité d'un élément reste celle de son asset.
- **La CIBLE DE RENDU sort de ces tables.** La cible BG/OBJ figée par asset (que `font_emit` grave
  aujourd'hui dans `g_ui_regions`) et le slot BG deviennent une **table de routage par scène**,
  installée par `scene_init`. C'est elle qui remplace `text_set_layer()` implicite et l'ancien
  `Scene.text_bg`, et la règle « une cible par asset » du validateur prend sa retraite.

Le même `DialogBox` peut alors être un HUD en BG dans une scène et une bulle qui suit un acteur en
OBJ dans une autre — même index de région, routage différent selon la scène active. Le seul cas
exclu est le même layout posé DEUX fois dans une même scène : ses noms d'élément entreraient en
collision, le validateur l'interdit (cf. étape 5).

La migration lit les deux formes existantes (`ui_layouts` liste de noms *ou* de nœuds, plus
l'ancien `ui_layout` singulier). Chaque ancienne référence reçoit l'`anchor`/`target` de son asset
et le `Scene.text_bg` de sa scène comme `bg_slot` ; ni `text_bg` ni la cible d'asset ne sont plus
écrits ensuite. Deux anciennes scènes partageant un layout avec deux `text_bg` différents donnent
deux nœuds à slots distincts : c'est le test qui distingue ce modèle du champ posé sur l'asset.

#### Travail à réaliser

> **Livré (2026-09-13 → 09-14).** Le sous-chantier est en place, aux détails d'étendue près
> notés à l'item 1 et à l'« Ouvert » ci-dessous. Détail d'implémentation dans ARCHITECTURE.md
> (« Le slot BG appartient à l'INSTANCE… »). Ce qui a shippé, par item :
> 1 modèle (`InterfaceNode`/`BoundInterface`, migration) ; 2 éditeur (combo BG slot, Priority
> lit `node.bg_slot`, glisser-déposer, z-order canvas) ; 3+4 fusionnés : routage runtime C +
> `vram_alloc` multi-slot + retrait de `Scene.text_bg` ; 5 validation. Les tests (item 6) sont
> livrés avec chaque étape.

1. **Modèle et persistance.** `InterfaceNode` (par scène) porte `{layout_name, anchor,
   anchor_actor, target, bg_slot}` et **compose** son `UILayout` via `BoundInterface` (contenu
   délégué à l'asset). Migration lue, non réécrite (`_ui_nodes_from_dict`). **Étendue réelle :**
   seul `bg_slot` est effectivement par-nœud ; `anchor`/`target` restent portés par l'asset (les
   champs du nœud existent mais dormants — cf. « Ouvert »). `anchor`/`target`/`anchor_actor` NE
   sont donc PAS retirés de `UILayout`.
2. **Éditeur.** Retirer « UI layer » de l'inspecteur Scene ; le proposer dans l'inspecteur du
   nœud Interface uniquement quand sa cible effective est BG, le masquer pour OBJ et l'expliquer
   pour les modes bitmap. Le Canvas et le contexte Priorité lisent ce slot : chaque Background
   dépliable affiche exactement les Interfaces qui le ciblent.
3. **Allocation VRAM et initialisation.** Réserver un screenblock par slot BG effectivement
   utilisé par l'UI, tout en partageant les glyphes et les tuiles de fond compatibles dans le
   charblock UI. Configurer chaque `BGxCNT` concerné et ne plus exclure un unique `text_bg` du
   placement des backgrounds. Les fonds, textes et surfaces composées sont groupés par slot avant
   émission ; deux Interfaces sur le même slot écrivent dans la même map, dans l'ordre de scène.
4. **Routage de rendu par scène (ex-runtime de texte).** La cible de rendu sort des tables de
   contenu — qui restent per-asset, indexées par nom d'élément — et devient une **table de routage
   par scène** : pour chaque région/image active, sa cible (BG/OBJ), son `bg_slot` et son ancrage.
   `scene_init` installe celle de la scène active ; elle remplace l'état global implicite de
   `text_set_layer()`. `text_draw_in`, l'effacement, le reveal et les listes lisent le routage du
   nœud courant au lieu d'un layer figé ; les zones OBJ gardent leur chemin OAM. (Absorbe l'ancienne
   étape « runtime de texte » : retirer la cible des tables globales sans installer le routage
   casserait le ROM entre les deux, les deux ne font qu'une tranche.)

   Forme concrète (verrouillée) : `UIRegionInfo`/`UIImageInfo` perdent `target`/`anchor`/`actor` ;
   un **tableau plein** `g_region_route[REGION_COUNT]` (et `g_image_route`), parallèle aux tables de
   contenu, porte `{active, target, layer, map_sbb, anchor, actor}`. `scene_init` le remet à zéro
   puis remplit les entrées des régions/images de ses nœuds. `text_draw_in`/`clear_in`/reveal/listes
   /`ui_image_*` lisent ce routage ; le routage porte `target` pour trancher BG/OBJ par scène, le
   reste du chemin OAM est inchangé. L'**écriture libre** (`text_draw`/`text_clear` aux coordonnées,
   sans région) garde `text_set_layer` et son layer courant, posé au premier slot UI de la scène.
   `vram_alloc` réserve un screenblock par slot BG d'UI utilisé, en partageant le charblock de
   glyphes entre slots.
5. **Validation et règles de coexistence.** Signaler un slot invalide, indisponible dans le mode
   vidéo, ou une Interface BG sans slot. Conserver d'abord l'exclusivité actuelle entre une
   tilemap de BackgroundAsset et une tilemap UI sur le même BG ; autoriser une composition avec
   un décor existant demanderait une règle explicite d'écrasement et son propre chantier.
6. **Couverture.** Ajouter des tests de migration (dont un layout partagé par deux scènes), de
   routage statique et scripté vers deux BG, de partage de tilemap sur un même BG, de réservation
   VRAM et d'ordre de dessin Canvas/ROM. Mettre à jour les tests qui créent aujourd'hui une scène
   avec `text_bg` et les documents qui présentent ce champ comme le layer UI.

#### Ouvert — routage par nœud de `anchor`/`target`

Les champs `anchor`/`target`/`anchor_actor` existent sur `InterfaceNode` mais restent DORMANTS :
la cible et l'ancrage sont per-asset. Les rendre per-scène se scinde en deux, de coûts très
différents :

- **(1) dans le même plan (sûr).** Le même HUD écran-fixe ici / défilant (world) là : réintroduire
  la copie vivante runtime portant `target`/`anchor`, faire éditer le nœud (pas l'asset) dans
  `UINodeInspector`. Vérifiable au harnais.
- **(2) divergence BG↔OBJ (l'exemple phare, coûteux).** Un même layout HUD-BG dans une scène et
  bulle-acteur-OBJ dans une autre demande d'émettre le placement OBJ **inconditionnellement** dans
  `g_ui_regions` (la donnée existe déjà via `obj_text_alloc`), de réconcilier la géométrie BG
  (tuile) / OBJ (pixel) dans une seule entrée, et de résoudre l'`actor` (index g_actors) **par
  scène** (`region_actor_index` ne garde aujourd'hui que la première scène). Vérifiable seulement
  sur un vrai build ROM + émulateur. Reporté à un chantier dédié.

#### Hors de ce sous-chantier

Un Background UI n'est pas un calque isolé par Interface : deux interfaces sur le même slot ne
disposent ni de tilemap privée ni d'ordre matériel supplémentaire. Le dossier logique, la
visibilité d'auteur et la profondeur OBJ restent des responsabilités distinctes du contexte
Contenu et de la pile Priorité.

### Graphe de scènes — partie 2 : groupes et navigation par niveaux

Le graphe est une carte navigable du jeu, jamais un second langage de programmation. Les groupes
sont **organisationnels seulement** : ils ne possèdent pas de flux, ne contraignent pas les
scripts et ne promettent pas artificiellement une entrée ou une sortie unique. Ils sont des
métadonnées d'éditeur, mémorisées avec la disposition du graphe et sans effet sur le build.

- **Arêtes agrégées.** Plusieurs appels qui relient la même scène source et cible se lisent comme
  une arête unique avec un compteur ; l'inspecteur déroule les `LuaRef` qui la composent. Les
  cibles dynamiques ne disparaissent jamais : elles mènent vers une sortie `?` explicitement
  indéterminée. Une boucle n'est pas un objet spécial : c'est une arête de retour courbe qui
  révèle, au clic, le cycle réel qu'elle participe à former.
- **Boîte englobante repliable — décidé (2026-09-15).** Un groupe se dessine comme une **boîte
  qui entoure ses scènes membres** ; repliée, elle se condense à son seul en-tête (nom + nombre
  de membres) pour dégager la vue. Replier/déplier est un geste sur place, qui ne change pas de
  niveau. La boîte est déplaçable comme un nœud ; sa position et son état replié vivent dans le
  sidecar du graphe.
- **Niveaux de profondeur — fil d'Ariane en bas.** Double-clic (ou `Entrée`) sur l'en-tête d'un
  groupe **descend** dans son niveau : le contenu du groupe devient le seul contexte éditable.
  Le fil d'Ariane est une barre **en bas de la vue Graphe** (`Jeu / Village`), cliquable pour
  remonter ; `Backspace` remonte d'un cran et ne fait rien à la racine — raccourci local au
  Graphe, sans effet sur la suppression de l'éditeur de scène. Double-clic sur une scène reste
  l'ouverture de son contexte 2D (ou 3D selon son mode de rendu). Repli et descente coexistent :
  le premier condense sur place, la seconde change de niveau.
- **Frontières honnêtes.** Dans un groupe, les transitions externes deviennent des portes de
  frontière — `← 3 entrées`, `2 sorties →` — plutôt que des scènes externes modifiables. Elles
  préservent la lecture du lien sans casser le focus courant ; l'édition d'une transition reste
  dans le contexte de sa scène source.
- **Un groupe de scènes EST un dossier d'assets — décidé (2026-09-15).** « Groupe dans le
  Graphe » et « dossier de scènes dans le project viewer » sont le même objet, donc le même
  store. Et ce rangement n'a rien de propre aux scènes : c'est une **capacité générale**,
  `AssetFolderStore` (`core/asset_folder_store.py`), indexée par **famille** (`scenes`,
  `sprites`, …) — les scènes sont le premier client, les neuf autres familles l'adopteront. Le
  `AssetFinder` partagé gagne l'authoring de dossiers en **opt-in** (`FolderScheme` fourni par
  l'écran, capturant le store) : créer/renommer/supprimer/couleur/glisser, imbricable. Une
  famille qui n'en fournit pas reste inchangée. Le graphe et le project viewer lisent le **même
  store** — ranger d'un côté se voit de l'autre. **Une instance par session**, possédée par la
  fenêtre et injectée dans les deux ; deux instances du même fichier se désynchroniseraient (à la
  différence de `SceneTreeState`, per-panel car non partagé). Livré : 3a/3b (dossiers côté project
  viewer), 3c (boîtes englobantes repliables, arêtes redirigées vers la boîte d'un membre caché),
  3d (descente par niveaux : double-clic sur une boîte ouvre son niveau, fil d'Ariane cliquable en
  bas, `Backspace` remonte, transitions franchissant le bord agrégées en portes de frontière
  `← entrées` / `sorties →`), 4 (sélection croisée graphe↔project viewer : sélectionner des scènes
  d'un côté les surligne de l'autre, sans activation ni chargement, gardes anti-boucle). Notes
  textuelles, mini-carte, cadrage et recherche sont venus ensuite comme confort de lecture.
- **Calque Notes dessiné — reporté à v2.0.** Les textes, traits libres, surlignages et cadres
  appartiendront au niveau de graphe ouvert. Le calque sera verrouillé par défaut afin que dessiner
  ne concurrence pas la sélection des nœuds. Les annotations globales vivront à la racine ; celles
  d'un groupe ne l'encombreront pas. Les notes textuelles actuelles restent disponibles, mais le
  tracé libre n'entre pas dans le périmètre de v0.12.
- **Inspecteur contextuel.** Une scène expose sa miniature, son statut de départ et ses appels
  entrants/sortants connus ; une transition expose source, cible, fichier et ligne ; un groupe
  expose son nom et ses membres ; une annotation expose son style et son verrouillage. Retargeter
  le littéral connu reste permis ; créer une transition depuis le graphe ne l'est pas.

La première ouverture reçoit une disposition automatique, puis les positions sont mémorisées.
Zoom, mini-carte, cadrage global, recherche, scènes inaccessibles depuis le départ et scènes sans
sortie connue sont des aides de lecture ; aucune ne doit présenter une inférence comme un flux
exécutable certain.

### Graphe de scènes — partie 3 : création, édition et aperçu (2026-09-16/17)

La partie 2 posait les groupes en LECTURE (boîtes, niveaux, portes, dossiers partagés). Cette
tranche donne les **gestes d'auteur** sur la carte et une lisibilité de décor. Toujours la même
frontière : le graphe **organise et navigue**, il ne devient pas un langage — l'écriture de scripts
(retargetage, création de transition) reste explicitement dehors.

**Livré :**

- **Créer un groupe, des deux côtés.** Project viewer : menu du « + » de la section Scenes,
  `Ctrl+G` sur une sélection, et clic-droit « Grouper » (mono ET multi) + « Déplacer vers le
  dossier » pour un lot. Graphe : clic-droit « Créer un groupe » et `Ctrl+G` sur la sélection, au
  **niveau ouvert** (parent = le groupe courant). Groupe auto-nommé (`Group`, `Group_2`…),
  renommable en place côté viewer. Une seule écriture par geste (`AssetFolderStore.create_group`) ;
  `Ctrl+G` est un raccourci **remappable** (`scene.group`). Chaque changement de dossier émet
  `folders_changed`/`groups_changed` : créer/ranger d'un côté se voit de l'autre.
- **Le cadre déplié devient un rectangle POSÉ, pas dérivé.** Déplaçable **par son en-tête** (les
  cartes membres suivent), **redimensionnable** par les bords latéraux et bas ; géométrie persistée
  (`SceneGraphState.group_frame`). **Appartenance géométrique :** glisser une carte DANS un cadre
  l'y range, l'en sortir la sort du groupe (recalcul au relâchement, par contenance) — mais
  **redimensionner ne fait pas fuir** un membre (seul un glisser de carte change l'appartenance).
- **Un groupe vide est désormais visible** (une boîte est amorcée par dossier du niveau, plus
  seulement par ses membres) : un groupe créé vide apparaît, prêt à recevoir des scènes.
- **Portes de frontière reliées.** Chaque nœud interne qui franchit le bord est **relié par un
  trait** à sa porte (`← entrées`, `sorties →`) — cliquable/double-cliquable comme une arête
  (sélection de l'appel, ouverture à la ligne). Les portes ne flottent plus sans dire QUI franchit.
- **Supprimer, clic-droit contextuel.** Sur une scène : « Supprimer » (même `DeleteResourceCmd`
  annulable que le project viewer, avec confirmation). Sur un groupe : « Supprimer le groupe »
  (le dossier disparaît, membres et sous-groupes **remontent au parent**, jamais détruits).
- **Éditer / ouvrir une scène.** Clic-droit « Éditer la scène » = double-clic (bascule Canvas 2D +
  ouverture). Basculer **Graphe → Scène** ouvre la **scène sélectionnée** dans le graphe : l'éditeur
  pointe sur ce que l'auteur regardait (garde anti double-chargement pour l'ouverture explicite).
- **Racine du fil d'Ariane = nom du projet** (au lieu de « Toutes les scènes »).
- **Aperçu du fond PAR SCÈNE.** Une **pastille** ronde sur chaque nœud (état persisté par scène,
  `SceneGraphState.scene_previews`) bascule un rendu étendu : vignette 240×160 composant les
  **fonds** (backdrop en base + calques, slot 3→0), acteurs et interface exclus. **Sans fond
  affecté, la vignette est la couleur de backdrop** effective de la scène. Vignette mémoïsée, rendu
  paresseux (uniquement à l'activation).
- **Marqueur « scène active »** (liseré gauche) sur les cartes — cf. *Navigation des scènes*
  ci-dessous, même grammaire que le project viewer.

**Ce qui reste ouvert sur cet écran** (chacun sa décision propre — l'écran est utilisable, mais pas
« bouclé » au sens ROADMAP) :

- **Créer une transition depuis rien.** Le *retargetage du littéral* (glisser une arête vers une
  autre scène pour réécrire l'appel `scene.switch` via ses `LuaRef`) est **livré** (partie 4,
  2026-09-19), tout comme la *création d'une scène* depuis le graphe. Reste la **création de
  transition ex nihilo** : deviner dans quel script, à quel endroit et sous quelle garde poser
  l'appel n'a pas de défaut défendable — volontairement reportée (cf. décisions verrouillées).
- **Cibles calculées / indéterminées** — `scene.switch(variable)` aujourd'hui ignoré, à
  représenter par une sortie `?` explicite plutôt qu'un silence.
- **Routage des arêtes** — elles peuvent encore se croiser ; pas d'évitement.
- **Tracé libre du calque Notes** — reporté à **v2.0**. Les notes textuelles et la mini-carte sont
  livrées ; restent les traits libres, surlignages et cadres par niveau de graphe.
- **Undo/redo des sidecars** (groupes, positions, aperçu) — chantier séparé, envisagé **V2** (voir
  *Undo/redo des sidecars d'éditeur* dans les Chantiers techniques).
- **Finitions** : l'auto-layout et *Re-arrange* espacent pour la taille *condensée*, donc des cartes
  en **aperçu peuvent se chevaucher** ; la vignette ne se **rafraîchit** qu'au re-toggle de la
  pastille ou au rechargement du projet ; la bascule Graphe→Scène en **multi-sélection** ne choisit
  aucune scène (ambigu).

### Navigation des scènes — inspecter sans ouvrir (2026-09-17)

Jusqu'ici, cliquer une scène dans le project viewer la **chargeait** : `set_active_scene`,
historique vidé, canvas rebâti. Or on veut souvent régler un paramètre d'une scène — sa musique,
son mode, un pool d'acteurs — sans quitter celle qu'on édite. Le graphe le faisait déjà
correctement (clic simple = sélection sur le bus, l'inspecteur suit ; double-clic = ouverture) ;
c'était le project viewer qui restait l'exception, à cause de son chemin `_on_selected → scene_selected`.

On aligne donc le viewer sur le graphe, et on assume que **« sélectionnée » n'est plus
« active »** : deux notions distinctes, qui demandent deux repères visuels.

#### Décisions verrouillées

- **Clic simple = inspecter, double-clic = ouvrir.** Le clic simple pose la `Scene` sur le
  `SelectionBus` (l'inspecteur de scène la charge déjà pour n'importe quelle scène, `load(scene,
  project)`, et chaque mutation persiste sur *cette* scène via `save_scene`, pas sur l'active).
  Le double-clic seul bascule le canvas (`scene_selected` → `_on_scene_selected`). Même geste,
  mêmes deux issues que le graphe — une seule grammaire de navigation de scène.
- **Groupes imbriqués par glisser — cadres récursifs (2026-09-17).** Le geste « déplacer dans un
  groupe » vaut aussi pour les nœuds GROUPE : glisser la boîte d'un groupe dans un autre l'imbrique
  (`set_parent`, cycles refusés côté store), l'en sortir le remonte. Pour que « sortir » soit
  atteignable au glisser — et pas seulement « entrer » —, un **cadre déplié dessine ses sous-groupes
  à l'intérieur** (récursivement), comme il montre déjà ses cartes de scènes : le rendu passe de
  mono-niveau à « le sous-arbre du niveau courant, en descendant par les groupes DÉPLIÉS ». Un
  sous-groupe reste ainsi visible et sécable dedans/dehors. Placement dérivé (`_shown_groups` +
  `_place_scene` remplacent `_level_groups`/`_bucket_of`) ; déplacer un cadre emporte tout son
  sous-arbre (cartes + sous-groupes) ; l'appartenance se recalcule par contenance géométrique à
  toute profondeur (le plus petit conteneur, soi et ses descendants exclus). Le project viewer
  partage le store (`groups_changed`).
- **Grammaire de sélection à trois niveaux, cumulables — règle de design (2026-09-17).** Un même
  arbre distingue trois choses, sans qu'aucune n'en masque une autre : la scène **active** (celle
  qu'ouvre le canvas) porte une **barre verticale à gauche** ; l'**active selection** (première de
  la pile, l'item courant) porte le **remplissage plein** ; les **passive selections** (sélections
  secondaires) portent un **contour seul**. « active » se cumule avec une sélection (barre +
  remplissage/contour). Le bord gauche est réservé à « active » : le QSS ne dessine plus de liseré
  de sélection à gauche, qui se confondait avec lui. Comme Qt n'a aucun pseudo-état pour l'item
  *courant*, ce langage est peint par un **delegate partagé** (`RowSelectionDelegate`,
  `ui/common/selection_grammar.py`) qui possède seul le rendu de sélection — installé sur tous les
  arbres à sélection multiple (finders et arbre de contenu), pas seulement les scènes.
- **`project.active_scene` est la source de vérité de « quelle scène est ouverte ».** Le viewer
  et le graphe la lisent tous deux ; un signal du dispatcher au moment de la bascule déclenche le
  repaint des deux repères. On n'introduit pas d'état « scène active » dupliqué par vue —
  contrairement à la sélection, qui reste locale à chaque vue (Qt pour l'arbre, `QGraphicsItem`
  pour les cartes).
- **Historique couplé à la scène active — assumé.** L'inspecteur écrit dans le `get_history()`
  global, vidé à chaque bascule (`_on_scene_selected`). Éditer une scène non ouverte pousse donc
  dans l'historique de la scène ouverte, et un `Ctrl+Z` de cette édition « à distance » disparaît
  à la prochaine bascule. La persistance étant immédiate (`save_scene`), rien n'est perdu sur
  disque ; on accepte ce couplage plutôt que d'introduire un historique par scène.

#### Ce que ça touche

- `assets_finder_panel._on_selected` / `_on_activated` (famille Scenes) : le clic simple passe
  par le bus, le double-clic émet la bascule.
- Le liseré « active » dans l'arbre Scenes : porté par un delegate sur l'arbre du finder (la
  sélection native Qt peint déjà le remplissage ; le liseré est un état *en plus*), alimenté par
  un `set_active_scene(scene)` découplé de la sélection.
- Le même liseré sur `SceneCardItem` dans le graphe, alimenté par l'`active_scene` (la carte
  connaît déjà la scène de départ, pas l'active — même information à lui passer).

#### Ouvert

- La forme exacte du liseré (épaisseur, couleur d'accent, marge) — à caler au moment du code
  contre le thème, pas à supposer d'avance.

### Contenu — organisation et visibilité d'auteur

Le contexte **Contenu** sert aussi à organiser une scène de production, sans modifier son jeu.
Il reçoit des dossiers d'auteur (`Décor`, `PNJ`, `Gameplay`…) et deux états distincts sur chaque
acteur ou dossier :

- **Œil / Viewport** masque l'élément dans le canvas uniquement. Il reste compilé, actif et
  jouable dans la ROM. Les éléments masqués restent présents dans la vue Priorité, atténués,
  pour ne jamais devenir introuvables dans la pile de rendu.
- **Render** est l'état existant `Actor.visible` : il décide si l'acteur est émis dans la ROM.
  Il garde son sens actuel, mais son libellé et son icône doivent dire explicitement « rendu
  in-game » plutôt que seulement « visible ».

Un dossier propage chaque commande à ses descendants et affiche un état intermédiaire quand ils
ne sont pas homogènes, comme une collection Blender. Dossiers et visibilité viewport sont des
métadonnées d'éditeur, sans effet sur le build, le JSON de gameplay, la parenté acteur/enfant ou
la pile OAM. Ils vivent donc hors du modèle de scène compilé ; un renommage/déplacement d'acteur
doit migrer leur référence d'organisation avec lui.

### Graphe de scènes — partie 4 : la partie fonctionnelle — éditer les transitions (conception, 2026-09-17)

Les parties 1 à 3 posent une carte qu'on **lit, range et navigue**. Cette partie lui donne enfin
sa fonction : **agir sur les transitions depuis le graphe**. C'est le passage annoncé « de la
lecture à l'écriture de scripts », et c'est le plus délicat, parce que c'est là que la tentation
de faire du graphe un éditeur de code déguisé est la plus forte.

Cette section est une **conception**, pas encore un plan verrouillé : elle nomme les décisions à
trancher avant d'ouvrir. Elle part de trois idées posées — transitions multiples (tableau /
variable), inspecteur de dossier, batch multi-sélection — et les met en ordre autour d'une seule
question fondatrice.

**Mise à jour — livré le 2026-09-19.** La tranche sûre est désormais ouverte : les arêtes ont des
ports sémantiques (sortie droite → entrée gauche), un tracé droit ou courbe persisté, une
surbrillance de sélection et un inspecteur dédié. Celui-ci affiche les appels, édite leur ligne
de script, porte une note et accepte la multi-sélection ; notes et tracés sont annulables. Tirer
depuis un port reconnecte une cible littérale, avec aperçu sous le curseur ; une sélection
d'arêtes se traite en une commande Undo/Redo. La cible absente est un nœud rouge terminal,
déplaçable et muni de son entrée pour être reconnecté. Les groupes disposent aussi d'un
inspecteur (nom, couleur, note, état replié, contenu direct), partagé avec le dossier Scenes du
project viewer. Enfin la **création d'une scène** entre dans le graphe (elle est une DONNÉE, pas
un FLUX — cf. décisions verrouillées) : clic-droit dans le vide « Créer une scène ici » pose la
carte sous le curseur (`place_new_scene`) et la rattache au niveau ouvert, via la même commande
`add_scene` que le project viewer.

#### La règle qui gouverne tout — le graphe projette, il ne possède pas

Rappel du contrat, parce que chaque décision ci-dessous en découle. Une arête EST un
`scene.switch("…")` littéral à un endroit précis d'un script ; `SceneGraphEdge.refs` porte ses
`LuaRef` (fichier, ligne, offsets `start`/`stop`, guillemets inclus). **La source de vérité d'une
transition est le script.** Le sidecar `scene-graph.json` ne porte QUE de la présentation
(positions, aperçus, groupes) et ne gagnera jamais une table de transitions : ce serait une
seconde source de vérité. Toute écriture « depuis le graphe » est donc, sans exception, une
**réécriture du script** au bon offset via le choke point `refactor` (`rename_in_text` /
`rename_in_project`), jamais un stockage à côté.

#### La question fondatrice — la taxonomie des arêtes

Aujourd'hui la projection ne connaît qu'un cas : le littéral résoluble
(`scene.switch("Boss")`). Les cibles calculées sont **volontairement ignorées**
(`scripting/scene_graph.py`, commentaire l.53-55) et une cible inexistante devient un marqueur
d'erreur au rendu, pas un nœud. Or « on ne sait pas ce que l'auteur va construire » veut
précisément dire qu'il faut **nommer et représenter** ce que le graphe ne sait pas encore. Avant
tout geste d'édition, il faut donc trancher une taxonomie à quatre natures d'arête — c'est le
socle dont tout le reste dépend :

- **Littérale** — `scene.switch("Boss")`, cible existante. Arête pleine. **Seul cas
  retargetable inline** (voir plus bas).
- **Cassée** — `scene.switch("Bos")` (typo), cible inexistante. Déjà rendue comme marqueur
  terminal ✕ ; à promouvoir en **diagnostic** (voir plus bas), pas seulement un dessin.
- **Calculée** — `scene.switch(next_scene)` où l'argument n'est pas un littéral. Ne pas
  l'ignorer : arête **floue** vers un nœud fantôme « ? ». Quand l'analyse statique retrouve les
  littéraux assignés à cette variable, les proposer comme **cibles candidates** (arêtes
  pointillées vers chaque scène plausible), sans jamais prétendre que c'est le flux réel.
- **Conditionnelle** — un ou plusieurs `scene.switch` littéraux sous des gardes. Déjà des
  arêtes multiples groupées ; à enrichir de la **condition extraite** du ref (lecture seule).

Rappel maintenu de la partie 1 : **une arête est une citation, pas un flux.** Deux arêtes
sortantes ne veulent pas dire « branchement ». Le nœud « ? » ne ment donc pas — il dit « ce
script décide la cible au runtime », ce qui est l'information honnête.

**À trancher avec toi :** est-ce qu'on va jusqu'à la résolution des candidats (analyse des
assignations de la variable), ou est-ce qu'un simple nœud « ? » opaque suffit pour la première
tranche ? Le premier est beaucoup plus utile et beaucoup plus coûteux.

#### Éditer une transition — ce qui est sûr, et la ligne à tenir

- **Retargeter un littéral, inline.** Sélectionner une arête littérale → un combo des scènes
  existantes → réécriture du ref par offsets (mise en forme préservée octet pour octet, exactement
  `rename_in_text`). Le `if` qui entoure l'appel, sa condition et l'ordre des instructions ne
  sont **jamais** touchés. C'est le seul geste d'écriture réellement sûr, et c'est la ligne à
  tenir. Glisser le bout d'une arête d'une scène vers une autre est le même geste en direct.
- **Tout le reste = ouvrir le Script Editor à la ligne.** Changer une condition, déplacer un
  appel, éditer une cible calculée : ce sont des gestes de code, pas de graphe. Le double-clic
  (déjà livré) est la sortie de secours ; on ne la contourne pas.
- **Créer une transition depuis rien reste le cas le plus risqué.** Où l'insérer dans le
  script, sous quelle garde ? Aucune valeur par défaut n'est défendable en aveugle. Si on
  l'ouvre, ce doit être **inline et explicite** (fidèle à la règle « inline plutôt que
  dialogues ») : tirer une flèche A→B crée une ligne éditable proposant le point d'ancrage,
  jamais une insertion silencieuse.

#### Transitions multiples — le tableau ou la variable (idée 1)

C'est le cœur de la demande, et c'est le cas **calculé** de la taxonomie. Deux formes
réelles que l'auteur va produire :

- **Le tableau** — `local suivantes = {"A", "B", "C"}` puis `scene.switch(suivantes[i])`.
  L'analyse statique peut retrouver l'ensemble des littéraux du tableau → une arête « ? » qui
  se **déplie en N candidats pointillés**. L'inspecteur d'arête (ci-dessous) est le bon endroit
  pour lister ces cibles et sauter à chacune.
- **La variable libre** — `scene.switch(cible)` où `cible` vient d'un calcul ou d'un état de
  jeu. Irréductible à l'analyse : nœud « ? » opaque, double-clic vers le code.

Le piège à éviter : **ne pas inventer un mini-langage de transitions dans le graphe.** On
représente ce que le script contient déjà (un tableau de noms = N candidats), on ne crée pas une
structure de données de transitions que le script ne porterait pas.

#### Diagnostics — l'analyse que le graphe offre gratuitement (idée à moi)

Le graphe sait déjà qui pointe vers qui ; ces lectures ne coûtent presque rien et valent beaucoup
sur un RPG de quarante scènes :

- **Inatteignable** — scène sans arête entrante (sauf la scène de démarrage). Surlignée.
- **Cul-de-sac** — scène sans arête sortante. Marquée.
- **Cible cassée** — `scene.switch("Bos")` vers une scène absente : le marqueur ✕ existant
  devient un vrai diagnostic listé (« ce nom n'existe pas »), un par nom manquant.

Purement lecture, aucune écriture, aucun risque. Bon candidat pour la **première** tranche de la
partie 4, avant d'ouvrir l'écriture.

**Livré (2026-09-17) — les ports de diagnostic.** Chaque nœud porte un **point d'entrée** (à
gauche) et un **point de sortie** (à droite), colorés par un état DÉRIVÉ de la projection, sans
re-parser un script : lavande = cible(s) trouvée(s) / scène atteignable, jaune = cible calculée
(vigilance), gris = cul-de-sac / scène inatteignable, et **croix rouge** = cible introuvable
(signale sans résoudre). Les états sont une fonction pure `scene_graph.node_diagnostics(graph)`
(sans Qt, testée) ; la couleur vit dans l'item (`NodePortItem`). La projection gagne
`SceneGraphNode.has_dynamic_exit` — le seul fait que les arêtes ne portaient pas —, calculé via
`refactor.domain_args_in_text` (même primitive que la réservation VRAM). Ordre de vigilance quand
plusieurs cas coexistent : cassée > calculée > résolue > absente. Les ports ne captent aucun clic :
l'écriture depuis le graphe reste la suite de la partie 4.

#### Inspecteur d'arête — le complément naturel (idée à moi)

Plus fondateur que l'inspecteur de dossier pour la partie fonctionnelle. Sélectionner une arête →
un inspecteur qui montre : ses N occurrences (`fichier:ligne`), la condition extraite, les cibles
candidates si calculée, et les gestes sûrs (retarget du littéral, saut au code). C'est le pendant
« arête » de l'inspecteur de scène déjà en place, et l'endroit où vivent le retargetage et la
lecture des transitions multiples.

#### Inspecteur de dossier & batch (idées 2 et 3)

- **Inspecteur de dossier.** Attention à ce qu'un dossier EST ici : l'appartenance vit dans
  `AssetFolderStore` (famille `scenes`), le graphe n'en connaît que la présentation. Un
  inspecteur de dossier édite donc légitimement le groupe (renommer, réordonner) et ses scènes
  **membres**. « Batch les transitions du dossier » n'existe pas en propre : une transition
  appartient à une scène, pas au dossier ; ça se ramène à « pour chaque scène membre, applique X »
  — une boucle de réécritures explicites, jamais une abstraction magique.
- **Batch multi-sélection de scènes.** Cohérent avec `selection_grammar` / `tree_selection`
  déjà en place. Gestes batch **sûrs et sans ambiguïté** : aperçu/condensé sur N scènes, ranger
  dans un groupe, re-arranger le sous-graphe, supprimer. Les gestes qui touchent au **contenu**
  (renommer, retargeter) restent per-scène ou passent par une règle explicite — un batch ne doit
  jamais réécrire du script en aveugle. (Rappel : la bascule Graphe→Scène en multi-sélection est
  déjà notée comme ambiguë ; le batch hérite du même principe — pas d'action à cible unique sur
  une sélection multiple.)

#### Ce qu'il faut trancher avant d'ouvrir

1. **La taxonomie des arêtes** (littérale / cassée / calculée / conditionnelle) — tout en
   découle. À figer en premier.
2. **La profondeur de résolution du calculé** — nœud « ? » opaque, ou résolution des candidats
   par analyse d'assignations (tableau, variable). Utilité vs coût.
3. **Jusqu'où le graphe écrit** — le retargetage inline du littéral est acquis comme sûr ; la
   **création** de transition est-elle dans le périmètre de cette partie, ou reportée ?
4. **L'ordre des tranches** — ma recommandation : (a) diagnostics lecture seule, (b) inspecteur
   d'arête + retargetage du littéral, (c) représentation du calculé, (d) inspecteurs de dossier
   et batch. L'écriture arrive après que la lecture soit complète.

Reste par ailleurs ouvert et indépendant : le **routage des arêtes** (évitement des
croisements), déjà noté en partie 3.

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
| afficher mon score | **Texte** montre huit fonctions, aucune ne dit que la valeur vient d'une globale écrite au script (`global.score = 12`) plus un marqueur `$`. La recette traverse deux sections et un écran de l'éditeur. |
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
  `ui.get` — `global.get`/`const.get`, cités ici à l'origine, ont depuis quitté l'API
  au profit de l'accès pointé, cf. [Chantiers techniques](#chantiers-techniques)) ; `ui` → `interface` (une abréviation, que la grammaire
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
  ou à refuser par écrit dans la référence de scripting.
- **La référence de scripting adopte-t-elle les mêmes huit sections ?** Deux plans différents pour la même
  API rouvriraient exactement le problème qu'on ferme ici.
- **v0.13 hérite de ce rangement** : les palettes de blocs de l'édition mixte seront ces huit
  sections. À vérifier quand le chantier démarre, pas maintenant.
- **`ARCHITECTURE.md` porte déjà les anciens noms** (`get_actor`, `ui.get`, `text.draw_in`
  — huit endroits au moins). Ils y sont **justes tant que le renommage n'est pas fait** : ce
  fichier décrit le code tel qu'il est. Il devient donc la liste de contrôle du renommage,
  pas une dette à corriger d'avance.

---

## v0.17 — Le pool par scène

> **LIVRÉE le 2026-09-19** — B1 (éditeur) et la moitié build B2b (sept tranches T1→T7, cf.
> « Livrée (2026-09-19) : la moitié build » plus bas). Ce qui suit est le DOSSIER DE
> CONCEPTION du jalon : l'état de départ y est décrit au présent (« `max_instances` est un
> champ du Prefab »…) parce qu'il l'était au moment de la décision — ce n'est plus vrai
> aujourd'hui (le champ a été retiré, le pool vit sur la scène, `spawn` rend `Actor*`). Le
> récapitulatif à jour est la section des tranches ; les décisions ci-dessous en restent le
> « pourquoi ».

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
- **Le budget OAM est DÉRIVÉ, pas réparti** (révisé le 2026-09-19, cf. section dédiée plus
  bas). `budget_prefab = 128 − acteurs_posés − OBJ_UI`. Acteurs et UI se comptent au build ;
  seul le pool (en instances) est déclaré, et il se valide contre ce qui reste. Remplace le
  partage manuel 96/32.
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
tombe), `scripting/api_reference.json` (la fiche, aujourd'hui fausse), et la référence de scripting.

Pour l'écran : `ui/scene_manager/inspectors/scene_inspector.py` (le widget de budget à deux
champs), `ui/scene_manager/inspectors/uses_inspectors.py` (« Spawné par »), et
`core/validator.py` (l'avertissement « plus d'acteurs posés que de slots réservés »).

### Livrée (2026-09-19) : la moitié build, en sept tranches (B2b)

Les sept tranches sont **livrées et vérifiées au build ROM** (projet OrbitTest, deux scènes
poolant des prefabs distincts : `G_ACTOR_COUNT` tombe de la somme projet 53 au max des scènes
41, `objdump` confirme la taille de `g_actors`). Pierre angulaire : un nouveau module
`codegen/oam_alloc.py`, source de vérité unique de la géométrie OAM d'une scène
(`scene_oam_layout(project, scene) -> OamLayout`), sur le modèle de `palette_alloc.py` —
`headers`, `main_gen` et la façade `actor_budget` en deviennent des LECTEURS.

- **T1** symboles per-scène : `actor_<Scene>_<Prefab>.c`, `spawn_<Scene>_<Prefab>`,
  `POOL_<Scene>_<Prefab>_*`, garde `compiled_prefabs` retiré (chaque scène recompile ses
  prefabs contre sa géométrie). `CodegenContext.scene_sym` porte la scène jusqu'au
  `_emit_actor_spawn`.
- **T2** plage de pool per-scène, repli `Prefab.max_instances` retiré du chemin build
  (`prefab_pool_instances` = max sur les scènes, sans repli).
- **T3** `g_actors[]` dimensionné sur le MAX des scènes (pas la somme), base OAM repartant de 0
  à chaque `scene_init` ; `TAG_*` devient scène-local (Modèle A ci-dessous).
- **T4** OBJ d'interface par scène : ordre OAM **acteurs → UI → pools** (décision Victor), base
  de la bande UI = `placed`, `scene_ui_obj_slots` réel lit la même source que le placement des
  zones (`gen_text._layout_obj_budget`).
- **T5** palettes propres des pools per-scène : `prefab_own_slots` (slot global) supprimé, un
  prefab poolé rejoint les consommateurs de palette propre de SA scène ; corrige au passage la
  palette d'une PARTIE de prefab (jamais réservée avant, retombait banque 0).
- **T6** `spawn` rend `Actor*`/`NULL` (au lieu de `int`/`-1`) : un handle chaînable et un
  `if not b then` qui teste vraiment le pool plein. `actor.spawn` typé `ret="actor"`.
- **T7** budget OAM unique et BLOQUANT : `validator._check_actor_budget` lit `scene_oam_layout`
  (même source que le build) et passe en ERREUR — le rendu écrit `shadow_oam[<indice>]`, 128
  entrées, au-delà c'est une corruption. Champ `Prefab.max_instances` retiré du modèle.

**T1+T2+T3 étaient indivisibles** (constat de lecture, 2026-09-19) : les symboles per-scène (T1)
exigent une plage de pool per-scène (T2), qui n'a de sens que si `g_actors`/la base OAM repartent
de 0 par scène (T3). Livrés d'un seul refactor.

**Deux pièges découverts en route, non prévus au plan :**
1. `g_sfx_on_destroy_id/_vol` étaient project-wide indexés par `Actor.tag` ; les tags repartant
   de 0 par scène (T3) se chevauchent. Rendus PAR SCÈNE + pointeur posé au `scene_init` (patron
   `g_active_cmap`), leur `extern` passe tableau → pointeur. Silencieux sinon.
2. L'override `Scene.actor_slots` ne doit PAS piloter la géométrie de build (l'ancien build
   posait les pools après les acteurs *réellement actifs*, jamais après l'override). `OamLayout`
   est `placed`-based ; l'override ne vit que dans la façade budget de l'inspecteur — une vue
   d'INTENTION, distincte de l'empreinte matérielle. Sinon une scène de démo restée à 96
   gonflait `g_actors` de 93 entrées fantômes.

**Reste en aval (non couvert par v0.17)** : le checker de script valide encore `actor.spawn("X")`
contre la liste PROJET des prefabs, pas contre le pool de la scène courante — l'erreur « spawner
un prefab qu'aucune scène ne poole ici » reste donc invisible. C'est un gain que le per-scène
rend possible (cf. plus bas), à cueillir dans un chantier ultérieur.

**`TAG_*` per-scène — tranché le 2026-09-19 (Modèle A).** Un `TAG_<Actor>` est aujourd'hui
*l'indice dans `g_actors[]`* (identité = indice : `get_actor("X")` → `&g_actors[TAG_X]`,
`other.tag == "X"` → `== TAG_X`). Quand `g_actors` repart de 0 par scène, l'indice devient
scène-local. **Décision : le TAG reste l'indice, et les symboles se préfixent par scène** —
`TAG_<Scene>_<Actor>`, `actor_<Scene>_<Actor>.c`, comme `spawn_<Scene>_<Prefab>`. Un seul geste
de préfixe, une seule règle « un acteur = une entrée de `g_actors` ». Le modèle alternatif
(découpler identité et indice via une table d'offsets runtime) a été écarté : une indirection
de plus pour éviter un préfixe qui doit exister de toute façon pour les prefabs. **Conséquence :
ce bloc absorbe le préfixe de scène des ACTEURS**, que « Ouvert » listait comme chantier séparé
— T3 ne tient pas sans lui.

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

### Révisé (2026-09-19) : le budget est DÉRIVÉ, pas deux tranches à répartir

La version livrée le 2026-08-26 (décrite plus bas) faisait **répartir** un total de 128 entre
deux champs réglables — « Acteurs de la scène [96] » et « Pool de prefabs [32] », l'un
descendant quand l'autre monte. C'était un **plafond fixe posé à la main** (`DEFAULT_ACTOR_SLOTS
= 96`) : exactement le « curseur mémoire » que le reste du projet bannit (cf. l'allocateur de
charblock, qui *calcule* le placement au lieu d'un plafond fixe). Un acteur posé est connu au
build ; le lui faire **réserver** est une fiction d'ergonomie qui masque le vrai calcul.

La règle correcte : le budget prefab n'est pas **réservé**, il est **ce qui reste**.

```
Acteurs posés          N   ← compté, pas réglé
OBJ d'interface        M   ← compté (texte OBJ, ui_image, fonts OBJ)
Pool de prefabs        P   ← déclaré en instances (× parties = slots)
                     ─────
budget prefab = 128 − N − M   ← dérivé ; le pool se valide contre lui
```

- **Le total est 128 parce que le matériel affiche 128 sprites.** Il ne se règle nulle part,
  et surtout pas dans Project Settings : ce n'est pas une préférence, c'est l'OAM.
- **Les acteurs et l'UI se COMPTENT, ils ne se réservent pas.** Un acteur posé, une bande de
  texte OBJ, une image d'UI sont résolus au build — leur nombre est connu, pas estimé. Le
  champ « acteurs » n'est donc plus une tranche : c'est un **décompte affiché**. `actor_slots`
  survit comme **override optionnel** (0 = auto = compté), gardé pour un réglage manuel
  ultérieur, mais aucune scène neuve ne le sème plus à 96.
- **`UISlot` entre dans l'équation.** Le widget d'origine oubliait les consommateurs OBJ de
  l'UI ; ils étaient vérifiés à part (`main_gen.py`, test `> 128` séparé). C'est précisément
  l'objectif « le budget compte TOUS ses consommateurs » (2026-09-10) : les deux ne font plus
  qu'un. Décomposer ces comptes UI **par scène** dépend de la moitié BUILD (compilation par
  scène) — d'où la livraison en deux temps ci-dessous.
- **Le pool se dit en INSTANCES, le budget se paie en SLOTS.** Un prefab à sous-arbre coûte
  instances × parties (v0.23, `POOL_*_INSTANCES` contre `POOL_*_SIZE`). Le widget montre les
  deux, sans quoi déclarer huit boss à quatre parties consomme trente-deux slots en silence.
- **Une seule faute reste possible, pas deux.** L'ancien modèle avertissait quand on posait
  plus d'acteurs qu'on n'en réservait (`over_placed`) : cette faute **disparaît**, puisqu'on
  ne réserve plus. Ne subsiste que le débordement des 128 (`over_budget`), avec ses trois
  postes dans le message.

**Livraison en deux temps** (fork tranché avec l'auteur) :

- **B1 — maintenant** : le budget dérivé `128 − posés − pools`, la **liste visuelle** des
  prefabs réellement en usage dans la scène (posés OU spawnés par ses scripts, via
  `refactor.iter_call_sites(DOMAIN_PREFAB)`, avec lien vers le script qui les instancie), et le
  **compteur d'instances** par prefab.
- **B2 — dès que la compilation par scène le permet** : brancher `M` (OBJ d'UI par scène) dans
  la formule, en décomposant `obj_text_alloc` / `ui_image_sprites` du niveau projet au niveau
  scène. C'est là que le vrai gain OAM se joue.

**Une simplification est assumée, et il faut qu'elle soit écrite** : un acteur **sans sprite**
ne consomme aucune entrée OAM — le matériel en accepterait donc plus de 128. Le budget les
compte quand même, parce qu'un seul nombre lisible vaut mieux que deux plafonds dont l'auteur
devrait suivre lequel s'applique. C'est un choix d'ergonomie contre le matériel, et c'est
exactement ce que la piste future « découpler l'existence d'une instance de son entrée OBJ »
(cf. « Ouvert ») rendrait réversible.

### Livré le 2026-08-26 : la moitié éditeur

> **Dépassé par la révision du 2026-09-19** (budget dérivé, ci-dessus), **B1 livrée**. Ce qui
> suit décrit l'état intermédiaire du 2026-08-26 — le partage 96/32 et `DEFAULT_ACTOR_SLOTS` —
> que la révision a remplacé (`actor_slots` survit en override, plus aucun seeding). Conservé
> comme dossier de la trajectoire du chantier.

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

### Objectif ajouté (2026-09-10) : le budget OAM compte TOUS ses consommateurs

Le budget des 128 slots ne compte aujourd'hui que **les acteurs de scène et les pools**
(`actor_budget.py`). Les autres consommateurs d'OAM sont réels, mais vérifiés **ailleurs**, hors du
budget de scène :

- **Les bandes de texte en cible OBJ** et **les images d'UI** — `text_update` / `ui_image_update`,
  posées après les acteurs et les pools sur la même base (`text_obj_set_base`), contrôlées par un
  test séparé `> 128` à l'émission (`main_gen.py:2033`).
- **Les fonts en cible OBJ** tombent dans cette même bande.

Résultat : deux comptes des mêmes 128 entrées, qui ne se parlent pas. Un pool trop large et une UI
en sprites peuvent chacun passer leur propre contrôle et se disputer le stock à l'exécution — le
message d'erreur de `main_gen.py:2036` le dit déjà à demi-mot (« réduire un pavage de fond […] ou
diminuer le pool de prefabs »), preuve que les deux postes visent bien le même stock.

**L'objectif du per-scène est donc un budget OAM UNIQUE par scène**, qui range côte à côte tous ses
consommateurs *résolus au build* :

```
acteurs posés  +  pools de prefabs  +  bandes de texte OBJ  +  images d'UI  +  fonts OBJ  =  128
```

C'est la moitié BUILD de la question « OAM » (cf. « Deux allocateurs, pas un » du chantier
transverse). La moitié FRAME — les consommateurs qui apparaissent en cours de partie — est traitée
là-bas, pas ici.

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

- **Découpler l'existence d'une instance de son entrée OBJ — piste future, pas ce chantier.**
  Aujourd'hui existence = OAM : une instance vivante occupe son slot pour toute sa vie, et
  `spawn_<Prefab>` rend `NULL` quand la plage est pleine. Le plafond réel d'un pool est donc
  `POOL_<X>_SIZE`, pas 128 ; le budget des 128 marche *parce que* les deux coïncident. On pourrait
  vouloir l'inverse : N instances vivant en RAM, et un culling par frame décidant lesquelles 128
  reçoivent un OBJ (« mille existent, cent-vingt-huit s'affichent »). Ce serait **un autre moteur** —
  le vrai plafond deviendrait la RAM (`g_actors[]`, état de script), pas l'OAM, et toute la
  sémantique du budget de scène changerait de nature. C'est la même famille que le spawn dynamique
  écarté plus haut, et **ça implique aussi les acteurs** : c'est ce qui rendrait réversible la
  simplification assumée ci-dessus (« un acteur sans sprite est compté quand même ») — le but visé
  est de **réduire le coût d'un acteur sans sprite par scène**. À rouvrir dans son propre jalon, une
  fois le per-scène build livré.

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

#### Le cas mesuré de l'allocateur de frame — l'OAM dynamique (2026-09-10)

La décision « l'allocateur de frame se décide sur un cas mesuré » (« Ouvert » ci-dessus) a son cas.
Trois familles de consommateurs OAM apparaissent ou disparaissent **en cours de partie**, et aucune
n'a de place dans le partitionnement build de la scène :

- **Les projectiles** — un acteur poolé les sert déjà (v0.17) : ils ont position, vélocité,
  collision, un brin de logique. Ce ne sont PAS un cas pour une primitive à part, seulement pour une
  bonne API de spawn/despawn. Ils prennent leurs slots dans le pool de leur scène.
- **Les particules** — le vrai cas hors-budget : des centaines, éphémères, sans collision ni script.
  Un `Actor` plein par particule est absurde, et 128 OAM sature instantanément. Elles veulent
  probablement un modèle À PART (cap fixe, ou effet BG) — peut-être pas de l'OAM du tout.
- **L'UI en sprites** — déjà des consommateurs OAM légers (texte, images), placés au build et
  repositionnés par frame. À laisser tels quels côté runtime ; ce qui change pour eux est la
  **source visuelle** (chantier séparé ci-dessous).

**Décision de conception (2026-09-10) : on ne scinde PAS `Actor` en deux structs.** L'idée d'un
`Actor` (logique) référençant un `Sprite` (affichage) par pointeur a été pesée puis écartée : sur un
ARM7TDMI sans cache, l'indirection frappe le cas 1:1 majoritaire dans les boucles les plus chaudes
(tick d'anim, compose OAM), et rouvre un second allocateur à durée de vie coordonnée — exactement ce
que le merge de la v0.25 (`actor_types_static.h`, « Une seule entité runtime ») refuse. « Actor sans
sprite » existe DÉJÀ (le marqueur : point de tir, ancre). Le seul cas neuf, « sprite sans actor »,
est couvert soit par l'acteur poolé (projectile), soit par une primitive d'affichage légère posée
sur un slot OAM (particule, UI) — jamais par un `Actor` amaigri.

**Ce qui reste ouvert** : la forme exacte de l'allocateur OAM de frame (une free-list de slots pour
ce qui apparaît en jeu), et si les particules relèvent de l'OAM ou d'un effet BG. À trancher sur un
projet réel qui en a besoin, pas avant — fidèle à la règle du chantier.

### Chantier transverse — le Sprite, source visuelle unique

Ne porte pas de numéro : c'est un remaniement de **données**, déclenché par le constat qu'un même
dessin animé a aujourd'hui **plusieurs pipelines de définition** selon qui l'affiche. Un acteur
pointe un `SpriteAsset` (ses tables d'anim émises en ROM) ; une image d'UI pointe une autre voie ;
un futur projectile ou une particule ne pointent rien. Le dessin, ses frames, ses états et ses
directions sont pourtant la même chose — celle qu'on édite dans **l'écran d'animation**.

**La direction (2026-09-10)** : tout ce qui s'affiche — acteur, image d'UI, projectile, particule —
**référence un seul `Sprite`**, l'asset de l'écran d'animation. C'est « source de vérité unique »
appliquée au visuel. Distinct des deux questions OAM ci-dessus : celles-ci partagent le STOCK
matériel (les 128 slots) ; celle-ci partage la DÉFINITION (l'asset). Un consommateur peut être léger
côté runtime (une particule ne porte pas de logique) tout en pointant le même Sprite qu'un acteur
lourd.

**Ce que ça ne fait pas** : ça ne touche pas la struct `Actor` (cf. décision ci-dessus) et ça ne
crée pas de runtime commun. C'est la couche asset qui s'unifie, pas la couche entité.

**Ouvert** : l'inventaire des pipelines actuels (SpriteAsset côté acteur, la voie image de l'UI) et
lequel absorbe l'autre ; et si le décor animé (v0.4) relève de ce même `Sprite` ou reste une voie BG
à part.

### Chantier transverse — la Liste d'interface est un contrôleur, pas une collection

La liste actuelle (v0.22) a résolu le morceau qui devait l'être dans le moteur : navigation à la
croix, sélection, bornes, répétition, défilement et curseur. Elle expose encore une partie de la
mécanique de données et de rendu (`list.set_count`, `list.first`, `list.row`) : l'auteur doit dire à
la primitive combien d'items sa collection contient, puis la consulter pour repeupler les rangées.
Cela fabrique un second vocabulaire de collection alors qu'une liste n'a pas vocation à posséder les
données qu'elle affiche.

Le projet a déjà TROIS formes de tableau accessibles à l'auteur, qui ne se recouvrent pas :

| Forme | Rôle | Lua |
| --- | --- | --- |
| Tableau local | mémoire de travail privée d'un script | `local grille = array(20, 12)` |
| État global | valeurs mutables du jeu, partageables et éventuellement sauvegardées | `global.inventaire[i]` |
| Catalogue Data | fiches structurées, constantes, éditées dans le projet et émises en ROM | `data.Objets[i].prix` |

Le tableau local reste une construction du langage, hors inspecteur. Les deux autres sont les deux
formes de **donnée de projet** : elles vivront dans le même écran *Data*, rangées en **État** et
**Catalogues**, sans les faire passer pour la même chose. Un global peut devenir un vecteur ou une
grille 2D homogène ; une Data Table reste une suite de fiches à colonnes nommées et typées. La
seconde ne doit pas être réduite à un « global 2D » : elle est en lecture seule, vit en ROM et ses
colonnes portent des références validées au build.

Le but est de conserver le helper là où il évite du code répétitif, tout en rétablissant une seule
source de vérité. Dans l'inspecteur, une Liste choisira une source déclarée — un vecteur d'état ou
un catalogue Data — ; le script lira et modifiera l'état directement avec `global.*`, et lira les
fiches avec `data.*`. La Liste ne sera qu'une vue navigable sur cette source. Un auteur qui veut un
comportement hors modèle pourra laisser la Liste de côté et écrire son propre contrôleur sans migrer
ni recopier sa donnée.

#### Décisions verrouillées

- **La donnée appartient à l'état ou au catalogue, jamais à `UIList`.** L'inspecteur conserve une
  référence vers la source, pas une copie de ses items ni une structure propre au widget. Un même
  tableau global ou catalogue Data peut donc alimenter une Liste standard, une vue entièrement
  scriptée, ou les deux selon la scène.
- **`list.*` ne modifie jamais les items.** Il n'existera pas de `list.add_item`,
  `list.delete_item`, `list.sort`, ni de méthode équivalente. Ajouter, retirer, transformer ou
  chercher une valeur relève de l'état et du Lua, pas de l'interface.
- **La primitive ne porte que son état d'interaction.** Son API vise la position sélectionnée
  (`list.cursor_pos`, et son éventuel setter), la prise de focus (`active`) et les paramètres de
  navigation. Elle observe la taille de la source liée, borne elle-même le curseur après une
  mutation et recale seule le défilement et l'image curseur. Exemple : `list.cursor_pos("Inventaire")`
  donne le rang avec lequel le script lit `global.inventaire[rang]`, puis éventuellement
  `data.Objets[id]`.
- **La longueur logique appartient à la source, pas à l'API Liste.** Un vecteur d'état à capacité
  fixe peut déclarer dans l'inspecteur la variable globale qui porte son nombre d'items utiles
  (`global.inventaire_count`) ; la Liste l'observe. Le script déplace les valeurs et met ce compteur
  à jour sans jamais appeler `list.set_count`.
- **Le défilement n'est pas une donnée publique.** La première case visible est une conséquence de
  la sélection, de la géométrie et de la taille de la source ; elle ne doit pas devenir une
  seconde position à tenir par le script. Le contrat de rendu devra permettre de repeupler les
  rangées visibles sans imposer à l'auteur de manipuler `first`/`row`.
- **Une Liste reste un helper optionnel, pas une dépendance des données.** Remplacer son rendu ou
  sa navigation ne demande pas de convertir la donnée : `global.*` et `data.*` restent directement
  accessibles en Lua dans tous les cas.

#### Ce que le chantier implique

Le chantier dépasse un renommage de fonctions. Il relie l'inspecteur de Liste, l'écran Data (État +
Catalogues), le modèle de globals, le checker Lua, le codegen, le runtime de navigation et le rendu
de texte. Il faudra aussi remplacer le chemin actuel où le script pose explicitement le texte dans
`text.draw_in(list.row(...), ...)` par un contrat de rendu lié aux rangées authorées, sans faire de
l'item un nouvel objet d'interface.

Les tableaux Lua actuels sont **de taille fixe au build** et `table.insert`/`table.remove` ne font
pas partie du sous-ensemble accepté. Les globals ne portent aujourd'hui qu'une dimension ; les
grilles 2D font partie de leur extension, pas de la responsabilité de `UIList`. Une collection
réellement redimensionnable n'est donc pas à faire entrer subrepticement dans la Liste : si les cas
d'usage demandent plus qu'une capacité fixe et une longueur logique, ce sera un chantier de modèle
de données explicite, avec sa mémoire, sa sauvegarde et ses opérations propres. La Liste suivra
cette donnée ; elle ne l'implémentera pas.

#### Ouvert

- Le contrat exact entre une collection liée et le rendu des rangées : callback de rendu, boucle
  dédiée, liaison déclarative, ou autre forme qui laisse le défilement interne sans masquer la
  donnée Lua.
- La forme exacte de l'extension 2D des globals : syntaxe, inspection, bornes, valeur par défaut,
  sérialisation et sauvegarde. Elle doit conserver la règle des tableaux locaux : les dimensions
  sont de la forme du type, non des propriétés manipulées par le runtime.
- La forme du modèle de collections dynamiques, si un projet réel en demande : capacité fixe avec
  longueur logique, collection compacte redimensionnable, identifiants stables, persistance et
  coût RAM. Cette décision précède toute promesse de suppression physique d'un item.
- La migration des listes v0.22 et de leurs appels `set_count`/`first`/`row` : compatibilité
  temporaire ou rupture guidée. Elle se décide avec un inventaire des projets existants, pas en
  supposant qu'aucun script ne les emploie.
- Le comportement après mutation : le curseur conserve-t-il son index, se rabat-il sur le dernier
  item valide, ou peut-il suivre un identifiant stable ? Le bon choix dépend du modèle de données
  finalement retenu.

### v2.0 — Cible cartouche : le matériel embarqué façonne le langage — **JALON OUVERT**

> La famille v2.0 n'est pas rangée. Ce jalon est **posé, pas ordonnancé** : quand on y sera,
> on fera le point de tout ce qui s'y accumule et on décidera de la découpe. Ce qui suit fixe
> l'**intention** et les décisions déjà prises (2026-09-10), pas un périmètre daté.

Un **profil de cartouche** décrit ce que la cartouche embarque **physiquement** — capteurs,
rumble, RTC, type et taille de sauvegarde. Il reste **100% GBA** : les limites mémoire (IWRAM,
EWRAM, VRAM, OAM, palettes) sont fixes pour toute la gamme et **ne bougent pas**. Cibler un
matériel aux limites différentes (NDS…) serait un second backend d'émission, un autre modèle
mémoire — **hors de ce jalon**, écarté explicitement le 2026-09-10.

Le profil n'énumère que des **faits matériels** ; il ne porte aucune logique. Il est la **source
de vérité unique** de « ce que porte la cartouche », d'où tout dérive :

| Capacité | Ce qu'elle débloque | Réel |
| --- | --- | --- |
| `tilt` | API `tilt.*` (angle brut X/Y) | WarioWare Twisted, Yoshi Topsy-Turvy |
| `solar` | `solar.level` | Boktai |
| `rumble` | `rumble.*` | Drill Dozer |
| `rtc` | `rtc.*` | Pokémon Ruby/Sapphire |
| `save` | type + taille (SRAM/Flash/EEPROM) | déjà modélisé partiellement (v0.5) |

**Trois conséquences en cascade** (une source, tout en dérive) :

1. **API script.** Chaque capacité présente ajoute son module au langage ; absente, le module
   **n'existe pas** — pas grisé. Ce sont des modules **moteur spécialisés et nommés**, jamais de
   l'itération par défaut (cf. la règle des deux couches).
2. **Éditeur.** Les nœuds et champs qui dépendent d'une capacité absente ne s'affichent pas. Le
   *pourquoi* d'une absence ne sort qu'en notice niveau 3, désactivable — l'éditeur ne commente
   pas le matériel.
3. **Émission ROM.** Le codegen n'inclut le driver (lecture capteur, IRQ RTC, registre rumble)
   que si la capacité est déclarée. Pas de code mort dans une ROM qui n'a pas le hardware.

#### Décision verrouillée (2026-09-10) — le profil ABSORBE la sauvegarde

La config SRAM de la v0.5 est déjà un morceau de « ce que porte la cartouche » qui vit à côté.
Le profil **l'absorbe** : une seule source de vérité, pas deux partielles. C'est un **vrai
chantier de migration** — migration du modèle de save existant et relecture du codegen de
sauvegarde, l'ancien supprimé avant de dire terminé — pas un bonus glissé dans autre chose.

#### Deux pièges matériels à encoder

- **Capteurs analogiques mutuellement exclusifs.** Une cartouche GBA porte *un* capteur
  analogique (tilt **ou** solaire), pas les deux — même ligne d'acquisition. Le profil doit
  interdire la combinaison, sinon on laisse décrire une cartouche qui n'existe pas.
- **Le tilt n'est pas un axe de pad.** Il rend un angle bruité à calibrer/filtrer. L'exposer
  comme un axe propre mentirait sur le matériel : valeur brute, et au plus un helper de
  calibration nommé.

#### Le catalogue « cartouche conseillée » — trois tiers (2026-09-10)

Le catalogue s'inscrit dans une démarche homebrew/retrodev : on ne propose que des cartouches
qu'un utilisateur peut **réellement obtenir ou fabriquer**. Décisions de cadrage :
**marques écartées** (pas de nom de flashcart commercial dans l'UI, cf. le risque « GBA » de
`project_licensing_model`), **flashcarts reprogrammables dépriorisées** au profit des vraies
cartouches, et **priorité aux créateurs indépendants**.

**Tier 1 — Profils de base : cartouches réelles historiques reproductibles.** Les configs que
la logithèque GBA a réellement portées, reproductibles avec des puces standard et un gabarit
`kicad-gamepaks` (djedditt — contours aux dimensions des coques officielles). La vraie variable
est la puce de save + le périphérique embarqué :

| Profil de base | Matériel embarqué | Équivalent historique |
| --- | --- | --- |
| Save — SRAM | SRAM sur pile | gros de la logithèque |
| Save — Flash | Flash 64/128K | jeux à grosse sauvegarde |
| Save — EEPROM | EEPROM 4/64K | petits jeux |
| RTC | horloge + Flash | RPG jour/nuit (Pokémon G3) |
| Solaire + RTC | photodiode + RTC | Boktai |
| Rumble | moteur + driver | Drill Dozer, Pinball R/S |

**Tier 2 — Options « cool » : créateurs indépendants.** Cartouches à matériel embarqué,
buildables. Référence mature : **insideGadgets** (RTC+Rumble, Solar+RTC, FRAM sans pile, kits
*build-it-yourself*). Écosystème : **GBMake** (fabrication indé de cartouches sur mesure),
`kicad-gamepaks` (la brique de conception open source qui rend le Tier 1 fabricable).

**Frontière — documentée, pas livrée comme profil.** De la R&D, pas des cibles stables :
`jojolebarjos/gba-cartridge` (cartouche **FPGA**, TinyFPGA BX — mappers/périphériques custom) et
`konsumer/dkart` (framework open hardware avec **ESP32 + SD** soudés — « cartouche
intelligente »). Notés comme horizon, hors catalogue conseillé.

#### Convention de nommage — capacité d'abord, board number en note

Les cartouches historiques portent une nomenclature Nintendo, mais deux schémas coexistent :
`AGB-002/013/019…` désigne la **coque/famille physique** (inutile ici) ; `AGB-Exx-nn` est le
**PCB du jeu** qui encode save + périphérique (p. ex. `AGB-E05-01` = RTC + Flash, la carte
Pokémon Gen 3 — le seul rock-solid). Le fil nesdev le confirme : pour un jeu GBA, les seules
variables sont **taille de ROM, type de save, taille de save, présence d'un RTC** — donc notre
modèle de capacités *est* déjà la bonne granularité.

**On ne nomme PAS les profils par `AGB-Exx`** : c'est une désignation interne Nintendo (marque,
écartée), le catalogue de référence est mort (Pocket Heaven — reconstituer une table exhaustive
serait deviner), et le numéro n'encode rien qu'un nom de capacité ne dise mieux. Les profils
sont nommés **par capacité** ; le board number n'apparaît qu'en **note historique** pour les cas
sûrs (« profil RTC — équivalent historique `AGB-E05` »), jamais comme identifiant.

#### Références externes à surveiller

- [`kicad-gamepaks`](https://github.com/djedditt/kicad-gamepaks) — gabarits KiCad aux dimensions
  des cartouches officielles (la brique de fabrication du Tier 1).
- [insideGadgets](https://shop.insidegadgets.com/) — cartouches à RTC / Solar / Rumble / FRAM
  (référence Tier 2, kits *build-it-yourself*).
- [GBMake](https://gbmake.com/us) — fabrication indé de cartouches GB/GBA sur mesure.
- [`jojolebarjos/gba-cartridge`](https://github.com/jojolebarjos/gba-cartridge) — cartouche
  FPGA (TinyFPGA BX, KiCad) — frontière.
- [`konsumer/dkart`](https://github.com/konsumer/dkart) — framework cartouche open hardware
  ESP32 + SD — frontière.

#### Ouvert

- La découpe : ce jalon face aux autres candidats v2.0 (Backgrounds affines ci-dessous, etc.),
  et s'il se scinde par capacité.
- La forme exacte du profil dans le projet, et où il vit par rapport au reste de la config projet.
- L'ordre de livraison des capacités (RTC, rumble et les saves sont sûrs et fabricables ;
  l'ordre des capteurs analogiques dépend de la demande réelle). **Le tilt/gyro reste hors
  catalogue** : historique et réel, mais non reproductible (soudé dans la cartouche OEM, aucune
  flashcart ni repro ne l'embarque) — documenté « OEM-only », jamais proposé comme cible.

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
