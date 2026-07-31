
# Roadmap détaillée

Ce document est la version détaillée de la section "Roadmap" du [README](README.md) — le
README reste volontairement condensé (une ligne par version, pour un lecteur public) ;
ce fichier explique le scope, les décisions verrouillées et les questions encore ouvertes
derrière chaque jalon.

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel. **Ouvert** =
identifié mais volontairement non tranché — à rouvrir quand le chantier démarre
réellement, pas avant (le contexte au moment de l'implémentation sera meilleur que des
suppositions faites à l'avance).

---

## v0.2 — Gestion des palettes de couleurs

Aujourd'hui, `Actor` et `Prefab` ont un champ `pal_bank: int` brut (`editor/core/project.py:709,751`)
— un entier tapé à la main, sans aucune vue sur ce qu'il y a dans les autres banks, ni
détection de conflit. `grit` génère une palette "optimale" par PNG indépendamment
(`editor/codegen/asset_pipeline.py:52-53`), sans garantie de compatibilité entre deux
sprites assignés au même bank.

### Livré (branche `ColorPaletteSystem`)

Le cœur de la v0.2 est en place. Livré à ce stade :

- **Catalogue unifié illimité** (`PaletteBank`, `project/palettes/*.json`, un fichier par
  palette, partagé OBJ/BG) + **sélection active par scène** (`Scene.active_obj_palettes` /
  `active_bg_palettes`, jusqu'à 16 banques par pool). Le picker à swatches a remplacé les
  `pal_bank: int` bruts partout (Actor/Prefab/`BackgroundLayer`).
- **Écran Palette dédié** avec édition manuelle, roue chromatique, saisie BGR555, rampes,
  damier de transparence, import/export PNG et `.gpl`.
- **Allocation déterministe** des 16 banques par scène/pool (`codegen/palette_alloc.py`,
  `scene_bank_layout`) : palettes référencées à leur slot fixe, palettes propres
  auto-allouées aux slots libres. Source de vérité unique partagée par grit et `main_gen`.
- **Validateur** : avertissement sur conflit inter-scènes (même sprite/prefab résolu vers
  des palettes différentes) et sur débordement des 16 banques.

Au-delà du plan initial, plusieurs chantiers ont été livrés dans la foulée (voir aussi
[ARCHITECTURE.md](ARCHITECTURE.md), section « Système de palette & import d'assets ») :

- **Import non-destructif d'assets** — un PNG déposé est détecté, validé et **encodé** en
  métadonnées (sidecar JSON à côté du source, jamais réécrit). Une **quantification**
  (réduction de couleurs, destructive) n'intervient qu'en repli, si la source n'est pas
  déjà GBA-compatible. Le `match_mode` initial a été supprimé au profit d'un **build en
  indexé universel** ; le champ sprite `compress_method` est devenu `quantize_method`.
- **Encodage de fond** (`core/bg_import.py`) — tuilerie 8×8 + dédup + jusqu'à 16
  sous-palettes par fond (`SE_PALBANK` par tuile), émission C directe sans grit
  (`codegen/bg_emit.py`). Sidecar `BackgroundAsset` co-localisé avec le PNG dans
  `assets/backgrounds/` (même modèle que `SpriteAsset`).
- **Palette BG par layer** — `BackgroundLayer.pal_bank` remplace l'ancienne « une seule
  palette BG par scène » (voir décision barrée ci-dessous), CBB = `bg_slot`, garde-fou VRAM
  bloquant au build (`_check_bg_tile_budget`).
- **Inpainting (repeindre la palette par tuile 8×8, non-destructif)** — deux niveaux :
  *scène* (`BackgroundLayer.tile_palette_overrides`, canvas du Scene Manager, la scène est
  source de vérité) et *éditeur* (`BackgroundAsset.tile_palette_overrides`,
  `effective_tilemap()`, partagé entre scènes). L'asset/PNG d'origine reste intact ; la
  gomme restaure.
- **Modes de fond** — tuilé 4bpp / 8bpp + bitmap Mode 4 (photos), **auto-détectés à
  l'import** (`detect_import_mode` : pivot indexé/non-indexé, bornes ≤16 / ≤256 / >256).

### Décisions verrouillées

- **Deux pools hardware séparés**, fidèles au GBA (mémoire palette OBJ et BG
  physiquement distinctes) : 16 banques OBJ (sprites) × 16 couleurs, 16 banques BG
  (fonds) × 16 couleurs. Cette séparation vit dans la **sélection active par scène**
  (voir ci-dessous), pas dans le catalogue d'édition — depuis le 2026-07-08 le
  catalogue lui-même est unifié (voir plus bas).
- **Nouvel écran Palette** dédié pour construire ces palettes à la main.
- **Import** : depuis un PNG (bande de couleurs) ou un export standard Aseprite
  (PNG/`.gpl`) — pas de parsing du format `.aseprite` natif (trop de travail pour la
  valeur ajoutée, fragile aux évolutions du format).
- **Catalogue de palettes illimité et unifié au niveau projet** (2026-07-08, révision du
  plan initial "16 banks fixes par pool") — sur le modèle GB Studio : autant de palettes
  nommées que voulu, **partagées entre OBJ et BG** (une palette n'est que 16 couleurs,
  rien n'empêche la même définition de servir aux deux — la séparation hardware n'a
  jamais besoin de vivre dans le catalogue), stockées comme n'importe quelle autre
  Resource (`project/palettes/*.json`, un fichier par palette, plat). Chaque `Scene`
  choisit jusqu'à 16 palettes actives par pool (`Scene.active_obj_palettes` /
  `active_bg_palettes`, ordre = index de banque hardware) — c'est cette sélection, pas
  le catalogue, qui occupe réellement les 16 banques par pool au build.
  `Actor`/`Prefab.pal_bank` reste un `int` mais indexe désormais un **slot de la
  sélection OBJ de la scène**, pas directement le catalogue projet.
  - `Prefab.pal_bank` reste scene-relatif comme `Actor.pal_bank` (même forme de champ),
    bien qu'un prefab poolé n'ait pas de scène propriétaire unique (spawn_X() appelable
    depuis n'importe quel script Lua, non analysé statiquement) — un validateur
    (avertissement, pas un blocage) signale les cas où deux scènes résolvent des
    palettes différentes pour le même prefab ou le même sprite.
  - **Coupe assumée (OBJ)** : la quantification/remap des tuiles d'un `SpriteAsset`
    (slice 1) reste dédupliquée une fois par nom de sprite pour tout le projet — si le
    même sprite est utilisé dans deux scènes dont la sélection de palette diffère au
    slot concerné, un seul jeu de couleurs "gagne" (1ère scène rencontrée) et le
    validateur avertit. Générer une variante de tuiles par scène est un chantier
    pipeline à part, pas fait à ce stade.
  - ~~**Coupe assumée (BG)** : une seule palette BG par scène (`active_bg_palettes[0]`),
    partagée par tous les layers de la scène — pas d'override par `BackgroundLayer`
    individuel.~~ **→ levée (livré)** : `BackgroundLayer.pal_bank` donne une palette par
    layer, et l'inpainting descend au `SE_PALBANK` par tuile 8×8. Les 16 banques de
    `active_bg_palettes` sont désormais toutes exploitables.
  - Pas de banks réservées (voir "Mis de côté" ci-dessous pour l'ancien plan de
    réservoir auto-import).
- **`SpriteAsset` et `BackgroundLayer`** ont chacun leur propre champ palette
  configurable (nouveau — contrairement à `Actor`/`Prefab` qui ont déjà `pal_bank`).
- **Deux cascades de surcharge séparées, sans influence croisée** :
  - *Domaine background* : `Scene` peut surcharger la palette de chaque `BackgroundLayer`
    **individuellement** → sinon fallback sur la palette propre du `BackgroundLayer`.
    L'Actor/Prefab n'a aucune influence ici.
  - *Domaine sprite* : `Actor`/`Prefab` peut surcharger, via sa propre palette si
    configurée, **tous** ses `SpriteComponent` d'un coup → sinon fallback sur la palette
    propre de chaque `SpriteComponent`. La `Scene` n'a aucune influence ici.
  - Usage : override Scène = thème de couleurs cohérent pour tout le décor d'une scène
    sans éditer chaque layer ; override Actor/Prefab = recolorage global d'une instance
    précise (tous ses sprites d'un coup) sans toucher aux autres instances du même prefab.
- Remplacement des `pal_bank: int` bruts par un vrai picker référençant les palettes
  nommées de l'écran, avec swatches visuels.

### Mis de côté (2026-07-07)

- **Réservoir auto-import** — le plan initial (N banks par pool réservées à l'import
  automatique, grit récupère les couleurs des PNG non explicitement palettisés, mapping
  vers la couleur auto la plus proche sans éviction quand le réservoir est plein) a été
  **abandonné temporairement** avant implémentation, sur deux problèmes de conception
  identifiés en revue :
  - *Dégradation silencieuse* : à N=3 (48 couleurs/pool), le réservoir sature vite ;
    au-delà, les couleurs dérivent vers l'approximation la plus proche sans aucun
    avertissement — confusion probable ("pourquoi mon sprite a changé de couleur en
    ajoutant un autre sprite ?").
  - *Non-déterminisme* : quelle couleur atterrit dans quelle bank dépend de l'ordre de
    traitement des sprites au build, qui n'est pas garanti stable — même projet, même
    assets, rendu potentiellement différent selon des détails d'implémentation du
    pipeline plutôt que des choix explicites.
  - **État actuel** : les 16 banks par pool sont toutes directement utilisables/éditables
    (pas de réservation). `ProjectSettings.palette_auto_import_enabled` a été **supprimé**
    (le nouveau système de couleurs — catalogue unifié + sélection par scène — le rend
    caduc) ; la clé des anciens `project.json` est ignorée au chargement. Rien dans l'UI
    ne s'y réfère : ni banks réservées, ni option "Automatique" dans le picker.
  - À rouvrir avec une conception plus solide : débordement *visible* au build (warning
    explicite plutôt que silencieux) + ordre de traitement déterministe (tri par nom,
    pas ordre d'itération).

### Reste à faire (finitions v0.2)

Le gros est livré (voir « Livré » plus haut). Restent des finitions :

- ~~`Scene` doit probablement recevoir un nouveau champ palette dédié~~ — **fait**
  (`active_obj_palettes`/`active_bg_palettes`).
- ~~Branchement BG dans le pipeline + override par `BackgroundLayer` individuel~~ —
  **fait** : palette par layer (`BackgroundLayer.pal_bank`), émission directe des fonds
  encodés (`SE_PALBANK` par tuile) sans grit, palette canonique par scène copiée dans
  `PAL_BG_RAM` par `main_gen`.
- **Support ROM du mode bitmap (Mode 4)** — les fonds bitmap sont éditables et encodés
  côté éditeur, mais **ignorés au build** (`_bg_build_asset` retourne `None`,
  « increment 2 »). C'est la principale finition restante côté runtime.
- **Vrai 16bpp** — un import 16bpp retombe aujourd'hui sur `bitmap16`, repli interim vers
  Mode 4 ; l'UI bitmap dédiée reste à faire.
- **8bpp** — une palette 256 occupe toute la `PAL_BG_RAM` : garde-fou en place (un seul
  layer de fond par scène en 8bpp), pas de cohabitation multi-layers.
- **Aperçu contextuel** dans l'écran Palette (point restant du redesign UI).
- Calcul de "couleur la plus proche" (distance colorimétrique) — distance euclidienne
  simple pour l'instant, pas de justification perceptuelle.
- Variante de tuiles par scène (lever la "coupe assumée" OBJ ci-dessus) — chantier
  pipeline à part si le conflit multi-scènes s'avère gênant en pratique.

---

## v0.3 — Fondations runtime "background vivant" + Texte & UI in-game

### v0.3.1 — Fondations runtime "background vivant"

#### État de départ (vérifié par exploration du runtime, corrigé le 2026-07-06)

> Constat **avant** le chantier — voir « Livré » plus bas pour ce qui a changé depuis.


Le système de background est aujourd'hui pensé pour du décor pré-cuit, mais moins figé
qu'il n'y paraît au premier abord :

- Mode 0 confirmé (4 layers regular max), mais **un seul tileset partagé par scène**,
  chargé une fois dans un charblock fixe à l'init (`editor/codegen/runtime_codegen/main_gen.py:576`).
- **Le scroll et le parallax SONT câblés** (correction : une première exploration avait
  conclu par erreur que `scroll_speed` était un champ mort — elle cherchait les noms
  `REG_BG0X`/`REG_BG0Y` littéraux et manquait la macro réellement utilisée). En réalité :
  `BGOFS(n) = cam_x * layer.speed >> 8` par layer (`main_gen.py:885`), et `BGOFS`
  pointe bien sur le registre hardware réel `REG_BG0HOFS` (`0x04000010+n*4`,
  `runtime/include/gba_engine.h:20`). Le scroll est piloté par `cam_x`/`cam_y`
  (voir v0.6.1 Caméra), pas par un défilement autonome indépendant de la caméra.
- **Aucune mutation de tilemap au runtime** : pas de fonction pour écrire une tuile à
  `(x,y)`, ni côté C (`gba_engine.h`) ni exposée en Lua. `tile.get` (`api.py:378-383`)
  ne lit que la carte de collision, pas la VRAM.
- **Aucun show/hide de layer** : les bits `DISPCNT` sont posés une fois à l'init de
  scène et jamais retouchés.
- Tout l'agencement VRAM (charblock/screenblock) est figé au moment du build.

Le texte est un **cas particulier de la primitive manquante "mutation de tilemap"** :
afficher du texte sur un BG, c'est écrire des index de tuiles (glyphes) dans une tilemap
au runtime, frame après frame. Donc cette fondation sert à la fois le texte (v0.3.2) et
(en v0.4) l'éditeur de background/l'animation — pas de scope redondant entre les deux
chantiers.

#### Décisions verrouillées

- ~~Primitive générique de **mutation de tilemap au runtime**, exposée en Lua~~ — **fait**.
- ~~**Show/hide de layer** exposé en Lua~~ — **fait**.
- **Champ `render_mode` sur `Scene`** (`editor/core/project.py`, dataclass `Scene`
  autour de la ligne 842, à côté de `text_bg`/`collision_layer`) : ajouté dès maintenant,
  défaut = Mode 0, **caché dans `scene_inspector.py`** tant qu'aucun autre mode n'est
  supporté. Anticipe v2.0 (Mode 7) et v3.0 (bitmap) sans migration de fichiers de scène
  plus tard.

#### Livré

Socle « layer vivant » posé, plus large que le show/hide + `tile(x,y)` initialement prévu :
tout ce qui était gratuit une fois les **shadows de registres** en place a été pris au
passage (voir `ARCHITECTURE.md` → « Layers BG vivants »).

- `gba_engine.h` — shadows `g_dispcnt_sh` / `g_bgcnt_sh[4]`, `display_reset()` en tête
  de `scene_init_*`, et **toutes** les écritures de registre BG du codegen passent
  désormais par `dispcnt_set()` / `bg_cnt_set()`.
- **Lua `layer.*`** : `show`, `is_visible`, `set_priority`/`get_priority` (z-order
  dynamique, sprites compris), `set_scroll`/`scroll_by`/`get_scroll_x`/`get_scroll_y`
  (décalage propre au layer, **additionné** au scroll caméra par `scene_tick_*` — les deux
  se composent), `set_map`/`get_map` (bascule de screenblock = double-buffering de
  tilemap, avancé).
- **Lua `tilemap.*`** : `set`/`get` (index de tuile, flip et palette de la case
  préservés), `set_palette` (l'inpainting au runtime), `set_flip`, `fill`. Coordonnées en
  **tuiles** dans la carte du layer — à ne pas confondre avec `tile.get()`, qui lit la
  collision en pixels monde.
- Documenté dans `api_reference.json` (catégories Layer et Tilemap du script editor).

Restent hors périmètre, à ouvrir plus tard : fenêtres (WIN0/WIN1/OBJ-window), blending
(`BLDCNT`), mosaïque, et tout ce qui demande une infrastructure d'IRQ HBlank (effets par
scanline). Aucun n'est bloquant pour la v0.3.2.

### v0.3.2 — Texte & API

#### Décisions verrouillées

- Police custom (`Font`, actuellement un stub vide dans `project.py:544`) et API texte
  enrichie (dialogues, HUD, menus) — construits sur la primitive de mutation de v0.3.1.
- **Windows (régions d'écran) exposées brutes.** On garde le mot « window » du GBA ;
  c'est à notre documentation d'expliquer le concept de région. Les **deux** rectangles
  matériels sont exposés tels quels — pas d'allocateur : l'utilisateur gère la pénurie,
  un allocateur qui réattribue en douce rendrait les bugs incompréhensibles.
  **Purement scriptable** dans un premier temps (leur place dans l'éditeur se décidera
  le moment venu). **Fenêtre-objet incluse** — c'est elle qui donne les formes libres.

##### Neutralité de style — règle de conception

Objectif explicite : **couvrir tous les besoins sans induire un style graphique**. La
window matérielle est le bon socle précisément parce qu'elle ne dessine rien : elle dit
*où*, jamais *à quoi ça ressemble*. Trois garde-fous, à tenir dans la durée :

1. **Aucun skin par défaut.** Si on livre des exemples, on en livre plusieurs
   visuellement opposés (cadre pixel-art épais, bandeau plein sans bordure, texte nu sur
   fond estompé), dans le projet de démo — jamais dans le moteur. Un seul exemple *est*
   un défaut, quoi qu'en dise la doc.
2. **Le 9-slice est un outil, pas un look.** Proposer d'auteur un panneau étirable est
   légitime ; en faire le seul chemin ne l'est pas. Panneau en sprites, panneau plein
   écran ou pas de panneau du tout doivent rester aussi simples.
3. **Aucune position ni géométrie par défaut.** Pas de « le texte va dans le tiers
   inférieur ». Et **vocabulaire de moteur** dans l'API : région, layer, tilemap — jamais
   `dialogue`, `message`, `textbox`. Un nom de fonction est une suggestion de design.

#### Livré (socle window)

- `gba_engine.h` — shadows `g_winin_sh`/`g_winout_sh`, `window_reset()` appelé par
  `display_reset()` : défaut = **tout autorisé partout, aucune window active**, pour
  qu'activer une window ne vide pas l'écran par surprise (le piège classique de
  `WINOUT`). Rectangles clampés à 240×160 et jamais inversés — le matériel se comporte
  de façon erratique sur X1>X2, ces cas ne sortent pas de `window_set()`.
- **Lua `window.*`** : `show`, `is_visible`, `set` (rectangle), `set_layer`/`get_layer`,
  `set_obj`, `set_blend`. Régions : 0 = WIN0, 1 = WIN1, 2 = fenêtre-objet, 3 = extérieur.
- **Fenêtre-objet** : champ `Actor.obj_mode`, injecté dans `attr0` aux 3 sites d'émission
  OAM (acteur, prefab poolé, affine), piloté par `self:set_obj_mode(2)`. Mode 1
  (semi-transparent) réservé au blending, pas encore câblé.
- Constantes C préfixées `WINR_*` — les `WIN_*` de libtonc existent déjà avec une
  sémantique différente (masques de bits).

#### Livré (blending)

Complète le socle window : `window.set_blend()` autorisait le mélange par région, mais
rien ne le configurait. C'est fait, et l'effet « panneau net sur monde assombri » est
désormais réalisable de bout en bout, sans un octet de VRAM.

- `gba_engine.h` — shadows `g_bldcnt_sh`/`g_bldalpha_sh` (`BLDY` est write-only et n'a
  aucun lecteur : pas de shadow), `blend_reset()` appelé par `display_reset()`,
  coefficients clampés à 0-16 par `ev_clamp()`.
- **Lua `blend.*`** : `set_mode`/`get_mode` (0 aucun, 1 alpha, 2 vers le blanc, 3 vers le
  noir), `set_layer`/`set_obj`/`set_backdrop` (paramètre `side` : 0 = le dessus, 1 = le
  dessous — `BLDCNT` porte **deux** listes de cibles, pas une), `set_alpha(eva, evb)`,
  `set_fade(evy)`.
- `bg_layers_reset()` renommé **`display_reset()`** : il remet désormais à neuf les
  layers, les windows ET le blending. L'ancien nom était devenu faux.

#### Texte — décisions verrouillées (2026-07-21)

Le point de départ n'est pas l'API d'affichage mais **où le texte est stocké** : la v0.8
exige qu'il soit référencé par clé dès la v0.3. Principe directeur : **séparer le stockage
de la saisie**. Les conflater donne soit des clés à taper partout, soit du texte enterré
dans les scripts.

- **Stockage** — table au niveau projet (`project/texts.json`, `core/models/text.py`),
  entrée dans le graphe de dépendances, compilée en table C indexée par constante.
- **Saisie** — l'utilisateur ne tape jamais une clé. Trois portes, une seule table :
  le champ dans l'inspecteur (type d'export `text`), l'écran Textes, et
  `text.get("...")` avec autocomplétion.
- **Un type d'export `text` distinct de `string`** : `text` = destiné au joueur, référencé,
  traduisible ; `string` = technique, littéral, reste dans le script. Un mot maintenant
  évite un tri manuel en v0.8.
- **La table reste plate — pas d'éditeur de dialogue.** Ni arbre de conversation, ni
  portraits, ni choix branchés : c'est le même piège que les boîtes Pokémon, un éditeur de
  dialogue *est* une décision de genre. Le séquencement reste du script, écrit une fois
  dans un behavior réutilisable et paramétré par une référence — c'est ça qui tue la
  redondance, pas la table.
- **Trois identifiants, un seul résolvable** : `id` opaque (fichiers de données, insensible
  au renommage), `key` lisible (résolue **au build**, ce qu'écrit le Lua), `label` libre
  (jamais résolu). Détail dans `ARCHITECTURE.md` → « Textes du joueur ».
- **La clé situe, elle ne résume pas** : dérivée du contexte de création
  (`village_garde_01`), jamais du contenu — sinon elle ment dès que le garde devient un
  mendiant. **Jamais recalculée** ; le sens arrive par renommage manuel quand un texte le
  mérite.
- **Registry à id opaques** : les textes servent de **pilote**. Généraliser aux sprites,
  scènes, palettes, sfx, prefabs (et à tous les `DOMAIN_*` du codegen) révise la convention
  `<asset>_name` livrée en v0.2 — chantier à part, à ouvrir une fois le modèle éprouvé.

#### Livré (stockage des textes)

- `core/models/text.py` — dataclass `Text` (`id`/`key`/`label`/`content`/`note`/`scene`/
  `auto_key`), `slug()` qui déplie les accents, `new_id()` sur 12 chiffres (survit à une
  fusion de branches, là où un compteur monotone casserait), `make_key()` positionnel.
- `Project` — `texts_file`, `load_texts`/`save_texts` (câblés dans `load()`/`save()`),
  `new_text`, `get_text` (par clé) / `get_text_by_id`, `rename_text_key`, `delete_text`,
  et `_repair_texts()` pour un fichier édité à la main.

#### Polices — décisions verrouillées (2026-07-21)

- **Un glyphe = une tuile** en mono (rendu à chasse fixe, sur la primitive `tilemap.*` de la
  v0.3.1). Le rendu proportionnel est **livré** depuis (voir plus bas) ; l'asset stockait
  déjà `advance`, donc rien n'a eu à être réimporté — c'était tout l'intérêt. Bénéfice caché du choix : un glyphe étant une tuile, `tilemap.set_palette` le
  recolore, les windows le découpent, la priorité de layer le place — sans une ligne de
  code spécifique au texte.
- **Deux points d'entrée, pas plus** : planche **PNG** ou descripteur **BMFont `.fnt`**.
  TTF/OTF écarté (rastérisation imprécise, sélection de taille pénible) alors que le
  corpus de polices pixel d'itch.io est déjà énorme et vient en PNG. BDF et `.hex` Unifont
  restent en réserve.
- **Charset explicite et corrigeable**, jamais un « ASCII 32-126 » figé : c'est ce qui
  permet les accents, et des icônes de boutons ou n'importe quel symbole dans une police.
  Neutralité de style appliquée aux polices — on ne présuppose pas un alphabet.
- **Pas d'éditeur de glyphes** : on dessine dans son outil habituel, comme pour les
  sprites. Et **pas d'assistant d'import** en plusieurs étapes — le dépôt suffit, l'écran
  Police sert aux ajustements.
- **Pas de police par défaut, mais jamais de cul-de-sac** : une étagère de départ de trois
  polices visuellement opposées, présentées comme des exemples à modifier. Le pluriel est
  ce qui fait la différence entre un exemple et un défaut (même règle que les panneaux).
  (`display.print`/TTE servait de filet le temps que la police custom existe ; il est
  **retiré** depuis — voir plus bas.)

#### Livré (asset Font + import)

- `core/models/font.py` — `Glyph` (rect + `advance` + offsets) et `Font` (`asset`,
  `descriptor`, `cell_w/h`, `line_height`, `glyphs`), modèle **à rectangles** pour
  accueillir BMFont ; `charset` dérivé, `missing_chars()`, `tile_count()`.
- `core/font_import.py` — `detect_grid()` (découpage noté), `propose_charset()`,
  `import_font_png()` (mesure d'encre, bourrage de fin retiré), `parse_bmfont()`
  texte + XML, `import_font_fnt()`.
- `core/asset_sync.py::sync_font_file` + `project_migrations.reconcile_fonts`
  (dépôts hors ligne, `.fnt` prioritaire sur sa page).
- **Couleurs-clés** — `Font.bg_color` / `space_color`, désignées à la **pipette** dans
  l'inspecteur de police. Une planche reprise ailleurs (GB Studio, itch.io) arrive souvent
  opaque, sur un aplat de fond et avec une seconde couleur qui marque l'espacement ; sans
  les désigner, l'encodeur prend tout pour de l'encre et les glyphes sortent en pavés
  pleins. `Font.key_colors()` est lu par l'aperçu (planche trouée sur damier), l'import
  (`_ink_mask`, donc la chasse mesurée) et `encode_font` — même transparence partout, sinon
  l'aperçu mentirait sur la ROM. Le fond est **proposé** à l'import (couleur dominante d'une
  planche opaque), jamais imposé, et le PNG source n'est jamais modifié.
- **Chasse déclarée, jamais devinée** — trois sources par ordre d'autorité : le `xadvance`
  d'un `.fnt`, sinon le marqueur d'espacement s'il a été désigné (la couleur dit où finit le
  caractère), sinon **mono** (chasse = cellule). Pas de repli sur une mesure d'encre : sans
  flanc déclaré, une chasse proportionnelle colle les lettres et donne un texte irrégulier à
  rattraper case par case, là où du mono est toujours lisible. Repiquer la couleur
  d'espacement relit les chasses **sans redécouper** la planche (`measure_advances`) — les
  caractères corrigés à la main et les cases fusionnées survivent ; `_SetKeyColorCmd` rend
  couleur ET chasses à l'annulation.

#### Livré (rendu proportionnel)

**Deux chemins, choisis par la donnée.** `font_emit.is_proportional()` est la règle unique
(partagée par l'émetteur ET l'aperçu de l'éditeur, sinon l'aperçu promettrait un placement
que la ROM ne tiendrait pas) : une police dont chaque chasse remplit sa cellule garde le
chemin **mono**, qui ne coûte rien par appel. On ne paie la composition pixel que quand elle
change quelque chose.

- **Mono** (`proportional == 0`) — inchangé : les tuiles de glyphes vont en VRAM, le tilemap
  pointe dessus. Écrire du texte, c'est poser des index de tuiles.
- **Proportionnel** (`proportional == 1`) — une tuile se pose à 8 px près, donc le tilemap ne
  sait pas placer un glyphe à x=13. Le moteur réserve une **surface** de tuiles vierges, y
  fait pointer le tilemap une fois, et **compose les glyphes pixel par pixel depuis la ROM**
  (`text_blit_row`, masque de quartets non nuls pour ne pas effacer le voisin dont on
  chevauche la tuile). Les tuiles de glyphes ne vont alors jamais en VRAM : elles ne servent
  que de source, ce qui libère la place que prend la surface.
- **Adressage de la surface** déterministe depuis la position écran
  (`base + (ty % 8) * 30 + (tx % 30)`, 240 tuiles = moins de la moitié du charblock). Aucun
  état d'allocation : redessiner au même endroit réutilise les mêmes tuiles, ce qui rend
  `text_draw_upto` (machine à écrire) stable et permet à deux boîtes de coexister. **Limite
  assumée** : deux boîtes distantes d'un multiple exact de 8 rangées partagent leurs tuiles.
- **Une seule mise en page** pour les deux chemins (`text_layout`, tout en pixels — en mono
  les chasses valent gw*8, les positions retombent d'elles-mêmes sur des multiples de 8). La
  passe de mesure et la passe de dessin sont le MÊME code : mesurer autrement que l'on
  dessine, c'est se garantir un décalage entre la zone préparée et la zone écrite.
- `text_clear` vide les **pixels** de la surface en proportionnel, pas seulement le tilemap :
  la composition ne pose que de l'encre, sans effacer.
- L'origine (`tx`, `ty`) reste en TUILES dans toute l'API Lua — inchangée. C'est le placement
  des glyphes entre eux qui devient pixellisé.

#### Livré (police riche : composition automatique)

Une police MONO est chargée entière en VRAM (le tilemap pointe ses glyphes). Au-delà de
512 tuiles elle ne rentre dans aucun charblock — une police CJK était donc simplement
**impossible**. Or le chemin de composition, lui, ne charge **aucun** glyphe : ils restent en
ROM et servent de source, le coût se résume à la surface.

- `font_emit.render_composited()` bascule de lui-même dès que les glyphes coûtent plus cher
  que la surface (240 tuiles) : on prend le moins cher des deux. Une police de 800 glyphes
  (25 Ko de tuiles) passe ainsi à 240 tuiles ; en dessous du seuil rien ne change, le chemin
  tilemap ne coûtant rien par appel.
- Le drapeau `FontInfo.proportional` devient **`composited`** : il désigne le CHEMIN DE RENDU,
  plus la typographie. Les deux notions avaient divergé en même temps qu'elles se confondaient
  dans un seul champ.
- **Chasses, interligne et avance de secours sont émis DÉJÀ RÉSOLUS** (`font_line_px`,
  `font_fallback_adv_px`). Sans ça, forcer la composition sur une police mono aurait changé son
  interligne (`line_height` brut au lieu de l'arrondi tuile) — un déplacement de rendu
  invisible à la relecture. Le runtime et l'aperçu lisent désormais ces valeurs sans brancher
  sur le mode.
- Le log de build annonce le chemin et le coût VRAM réel, sinon un basculement automatique
  serait invisible.

Vérifié sur la cible : une police mono **forcée en composition** rend `###.....#####...###`,
soit A@0 B@8 A@16 — strictement ce que produit le chemin tilemap. Le basculement ne change
rien visuellement.

#### Livré (allocateur de charblock par scène)

`codegen/vram_alloc.py` — la VRAM BG n'est plus distribuée par la convention figée
« CBB = bg_slot, map à la fin de son propre charblock », mais **allouée par scène**.

- **Tout se raisonne en blocs de 2 Ko** (= 1 screenblock = 64 tuiles 4bpp) : c'est la seule
  unité qui voit à la fois les charblocks (tuiles) et les screenblocks (maps), qui se
  **recouvrent** dans les mêmes 64 Ko.
- **L'asymétrie qui dicte tout** : un fond est *rigide* (champ CharBlock de `BGxCNT` sur
  2 bits, et grit numérote à partir de 0 → collé à la base d'un charblock) ; le texte est
  *souple* (c'est nous qui écrivons ses entrées de map, en y ajoutant `g_text_tile_base`).
  Donc c'est le texte qu'on glisse dans les trous, jamais le fond.
- **Les maps sortent du chemin de croissance.** Posée à la fin de son propre charblock, la map
  d'un layer murait sa propre croissance — la croissance étant contiguë, il ne peut pas sauter
  par-dessus. Autoriser le débordement sans déplacer les maps n'aurait rien donné.
- **Portée 10 bits** : un layer voit 1024 tuiles depuis la base de son charblock, soit deux
  charblocks. Il déborde sur le suivant si rien ne l'occupe. Cas particulier : au-delà du
  charblock 3 commence la VRAM des sprites, donc un layer en CBB3 reste plafonné à 512.
- **Runtime** : `text_set_charblock()` dissocie le charblock du texte de son layer (les 4
  écritures de tuiles visent le CBB, les écritures de tilemap le LAYER).
- **Garde-fou** : le placement calculé n'est retenu que s'il donne à CHAQUE layer au moins ce
  que donnait le placement historique — sinon repli complet. Une allocation plus fine ne doit
  jamais casser un projet qui passait.
- `_check_bg_tile_budget` consulte l'allocateur au lieu d'un plafond fixe, et prend le budget
  le plus serré parmi les scènes qui posent ce fond (les tuiles sont partagées, l'allocation
  non).

Résultat sur le démo Pong : le décor d'ARENA passe de **448 à 1024 tuiles**. Un fond à map
64×64 passe de 256 à 960. Vérifié sur la cible (layer BG0 / charblock 3 / base 128 / SBB30 :
rendu identique, index de tuiles conformes à la base allouée).

Modes bitmap hors périmètre — leur framebuffer occupe la VRAM BG, à traiter avec le rendu
bitmap.

#### Livré (libtonc TTE retiré)

Deux systèmes de texte coexistaient, dont un contredisait la règle de l'autre. TTE est sorti :

- **La vraie raison est l'i18n**, pas la VRAM : la chaîne de format de `display.print` vivait
  dans le SCRIPT, donc hors de la table de textes — intraduisible, exactement le trou que la
  table existe pour fermer. Accessoirement, TTE chargeait sa police **à partir de la tuile 1**
  du charblock d'UI (mesuré sur la cible), là où `text_set_font` pose la nôtre : les deux
  s'écrasaient, donc `display.print` rendait des glyphes corrompus dès qu'un projet avait une
  police.
- **Remplacements** : `text.draw` pour un libellé (il vit dans la table, donc il se traduit) et
  **`text.draw_num`** pour une valeur (un nombre ne se traduit pas — seule primitive de texte
  dont le contenu n'est pas dans la table, et c'est volontaire). `draw_num` passe par le même
  `text_render_cp` que le reste : mêmes chasses, même surface, même effacement.
- **Migration automatique** au chargement (`project_migrations.migrate_display_calls`) : un
  appel à littéral pur crée une entrée de table rangée sous le nom du script et devient
  `text.draw(col, row, "clé")` ; `display.clear(c,r,len)` devient `text.clear(c,r,len,1)`. Les
  appels **formatés** ne sont pas devinés — décider ce qui est un libellé traduisible et ce
  qui est une valeur appartient à l'auteur, et `api.REMOVED_API` fait dire au checker quoi
  écrire au lieu de « fonction inconnue ».
- **`-ltonc` disparaît du link**, ainsi que `gba_font.h` (police 1bpp dont le consommateur
  `text_init()` n'existait plus, encore recopiée dans chaque build).
- `text.draw_fmt` (marqueurs substituables dans une entrée — le remplacement complet de
  `display.print` avec valeurs interpolées) était **différé** : il demandait de choisir une
  syntaxe de marqueur et de la faire vivre dans l'éditeur. La syntaxe est tranchée depuis
  (voir « décisions verrouillées (2026-07-27) » plus bas) — et le nom ne survit pas :
  l'interpolation vit dans l'entrée, donc c'est `text.draw` lui-même qui la porte.

Vérifié : build complet du démo Pong (migration → codegen → grit → compilation → link sans
libtonc → ROM), et `text.draw_num` sur la cible.

Vérifié **sur la cible** (ROM de test sous mGBA, résultats relus via le registre de debug) :
chasses 3/5/3 → 11 px d'encre contigus, translation à la tuile près, coupe au mot avec
chasses variables, machine à écrire, effacement réel des pixels, et non-régression du chemin
mono (tilemap pointant les slots de glyphes).

#### Livré (encodeur + API texte)

- `codegen/font_emit.py` — `encode_font()` (glyphes → tuiles 4bpp, palette des couleurs
  d'encre les plus fréquentes, table codepoint → tuile **triée** pour la dichotomie
  runtime), `emit_fonts_c()`, `emit_texts_c()`.
- **Runtime** (`gba_engine.h`) — `FontInfo`, `text_set_layer`, `text_set_font` (charge
  glyphes + palette en VRAM), `text_draw`, `text_draw_upto`, `text_draw_box` (retour à la
  ligne **au mot**, avec coupe au caractère en filet pour un mot plus long que la boîte),
  `text_clear`, `text_length`.
- **Lua `text.*`** — `draw`, `draw_box`, `draw_upto`, `clear`, `length`, `set_font`.
  Nouveaux domaines `DOMAIN_TEXT`/`DOMAIN_FONT` : une clé de texte ou un nom de police
  inconnus sont une **erreur** de checker (le `#define` n'existerait pas).

> État de ce bloc : `draw_box` a été **retiré** depuis, remplacé par les zones de texte
> (sa géométrie vivait dans le script). `draw_upto` et `draw_num` sont à leur tour datés —
> voir les décisions verrouillées du 2026-07-27 en fin de section.
- `main_gen` émet les tables et appelle `text_set_layer` + `text_set_font(0)` à l'init de
  chaque scène. Un projet sans police ni texte émet des tables vides et compile.

**Pas de réglage de vitesse dans le moteur** : `text.draw_upto(id, tx, ty, n)` révèle les
n premiers caractères, et le rythme appartient au script. Un champ « vitesse du texte »
dans l'inspecteur choisirait le genre à la place de l'utilisateur — même refus que pour
les boîtes de dialogue.

> Affiné le 2026-07-27 : ce que ce refus visait est un réglage **global**, imposant un genre
> à tous les textes. Un `{P3}` posé à un endroit précis d'une réplique est de l'écriture, pas
> un réglage — le tempo rejoint donc le contenu, et `draw_upto` disparaît avec lui.

#### Livré (propagation d'un renommage de clé)

- `rename_text_key` réécrit les appels des scripts via `DOMAIN_TEXT` — repérage
  **structurel** et non par liste de fonctions : toute primitive dont un paramètre porte ce
  domaine suit d'elle-même, ce qui a fait que `draw_in`/`draw_in_upto` n'ont rien eu à
  déclarer en arrivant. Une chaîne sans rapport ou un commentaire qui cite la clé ne bougent
  pas. Annulable (`RenameTextKeyCmd` repasse par la même fonction en sens inverse), et la
  barre de statut annonce combien de références ont suivi.
- `refactor.index_refs_in_project()` — index `{clé: {script: n}}` en **un seul** parcours,
  qui alimente la section « UTILISÉ PAR » de l'inspecteur de texte. Périmé (donc recalculé
  paresseusement) sur `scripts_changed`, sur renommage et sur undo.
- `Project._renaming()` émet `flush_script_edits` avant de commencer : la réécriture lit les
  scripts sur disque, une frappe encore dans le buffer du Script Editor serait ignorée puis
  ressauvée par-dessus, cassant le lien en silence.

#### Livré (zones de texte — `UIRegion` / `UILayout`)

La géométrie du texte sort du script et devient **authorée**. Détail technique dans
`ARCHITECTURE.md` → « Zones de texte ».

- `core/models/ui_region.py` — `UIRegion` (ancrage écran/monde/actor, rectangle en pixels,
  alignement, police, `preview_text`, `animated_glyphs`) et `UILayout`, **asset** rangé dans
  `project/ui_layouts/` et référencé par nom via `Scene.ui_layout` : une boîte dessinée une
  fois sert quarante scènes. Le badge « partagée — N scènes » fait partie de la feature —
  éditer une zone depuis une scène modifie un objet commun.
- **L'ancrage contraint la cible, il ne la suggère pas.** Ancrage sur un actor → OBJ sans
  alternative : un acteur bouge au pixel, la grille BG avance par 8. Ce n'est pas une
  préférence de qualité. `forced_target_reason()` rend la contrainte affichable — une
  contrainte muette se lit comme un bug de l'éditeur.
- **Cible OBJ = bande de sprites**, composée par le MÊME code que le BG (seul le bloc de
  destination change). Blocs de 8 px de haut parce que l'interligne vient de la police,
  qu'un script peut changer. Plafond de 32 px par colonne : un OBJ 64×8 n'existe pas.
- Table C `g_ui_regions` + constantes `REGION_*`, `DOMAIN_REGION` au checker (un nom de zone
  inconnu est une erreur). Placement OBJ **relatif** à la mise en page, comme `FontInfo.slot`.
- Outil « Zone de texte » (T) au canvas, création de la mise en page à la volée, item
  déplaçable avec snap 8 px en BG / 1 px en OBJ, `MoveUIRegionCmd` annulable, inspecteur
  contextuel par le `selection_bus`.
- `text.draw_in` / `draw_in_upto` / **`clear_in`** / **`draw_num_in`**. Les deux derniers
  comblent le trou qui renvoyait l'auteur aux coordonnées en tuiles : faire disparaître une
  boîte ou y mettre un score obligeait à tenir une seconde géométrie à la main, ce que la
  zone existe précisément pour éviter.
- `text_clear_in` vide **les deux cibles** (elle ne savait masquer qu'une bande OBJ) et
  applique la police de la zone avant d'effacer — une police composée range ses pixels dans
  les tuiles de surface, une mono pose des index dans le tilemap ; se tromper laisse l'encre
  en place.
- `preview_text` affiche une entrée réelle dans le canvas : le mesureur existait déjà
  (`FontScreenPreview` rejoue `text_layout`), il lui manquait un rectangle contre quoi se
  mesurer. Le débordement devient visible **à la conception**.

#### Livré (la boucle éditeur → script)

Le chaînon manquant : une fois la zone dessinée, rien dans l'UI ne menait à
`text.draw_in(...)`. La sidebar du Script Editor listait scènes, actors, prefabs, sprites,
fonds et SFX — ni textes, ni zones, ni polices.

- Sections **Textes** (rangés par premier niveau de chemin, tooltip = chemin + extrait),
  **Zones de texte** (celles de la scène active ; la clé vient du `preview_text`, donc le
  code inséré marche tel quel) et **Polices**.
- `scripting/api_snippets.py` — tout snippet inséré **dérive de `RUNTIME_API`**, et remplit
  ses arguments par DOMAINE et non par position. Écrits en dur, ils pourrissaient en silence :
  la sidebar proposait encore `scene_goto("X")` et `instantiate("X", x, y)`, deux noms jamais
  présents dans le catalogue — que le checker laisse passer (un appel inconnu peut être un
  helper de l'utilisateur), donc l'erreur n'arrivait qu'à la compilation C.
- `api_reference.json` ne décrit plus que la présentation : `get_categories()` le filtre par
  le catalogue puis le complète avec lui. Il proposait `display.print`, `display.clear` et
  `text.draw_box` — retirées — tout en ignorant `text.draw_in` et quatorze autres.
- **Garde-fou de prototypes** (`validator._check_api_prototypes`) : une fonction du moteur
  exposée en Lua doit être déclarée dans `gba_engine.h` ET redéclarée dans
  `actor_api_static.h`, que les TU de scène incluent seules. C'est ce qui a maintenu
  `text_clear_in` inatteignable — écrite dans le moteur, jamais redéclarée, donc checker
  vert, C correct, et échec au `make` sur un `implicit declaration` qui ne dit rien de la
  cause. Règle dérivée de la duplication elle-même, donc sans liste d'exceptions.

#### Texte — décisions verrouillées (2026-07-27)

La forme FINALE de l'API d'écriture, décidée avant d'ouvrir le chantier des marqueurs pour
ne pas figer des signatures deux fois.

- **Deux fonctions pour écrire, pas plus** : `text.draw(x, y, contenu)` et
  `text.draw_in(zone, contenu)`. Grammaire **position/conteneur → contenu**, tenue dans les
  deux. Tout le reste est du paramétrage, déclaré avant le draw ou porté par les marqueurs.
  **La grammaire est appliquée depuis** (voir « Livré » ci-dessous) : toute la famille `text.*`
  y est passée, y compris les primitives datées — une grammaire mixte pendant l'intérim
  coûterait plus cher que de les aligner.
- **`draw` accepte un littéral autant qu'une clé** — le seul à le permettre. C'est un accès
  rapide qui ne passe pas par l'interface, au prix assumé de la traduction. À la compilation
  un littéral devient une **entrée anonyme** de `g_texts` : le runtime ne connaît qu'un
  chemin, et un futur « extraire vers la table » reste un refactor mécanique.
  Désambiguïsation : la chaîne résout vers une clé si elle en matche une, sinon littéral ; le
  checker avertit quand elle a la forme d'un slug sans matcher — aucun vrai littéral ne
  ressemble à ça, donc la faute de frappe reste visible sans bruit.
- **`draw_upto` et `draw_num` disparaissent** avec les marqueurs. `draw_num_in` aussi : elle
  n'existe que pour ne pas laisser le trou ouvert d'ici là, et son retrait est déjà outillé
  (`api.REMOVED_API` dira quoi écrire à la place).
- **Le tempo s'écrit dans le texte, par l'auteur.** Ça ne contredit pas le refus de
  « vitesse du texte » ci-dessus, qui visait un réglage global imposant un genre à tous les
  textes : une pause posée à un endroit précis est de l'écriture, au même titre qu'une
  virgule.
- **Syntaxe à la BBCode**, sur le modèle du `RichTextLabel` de Godot — `[speed=4]`,
  `[pause=3]`, `[wave]…[/wave]`. Trois raisons : elle est **fermée** (sans borne de fin,
  `/S12` serait indécidable — vitesse 12, ou vitesse 1 suivie d'un « 2 » ?), les crochets
  n'apparaissent pas en prose là où `/` le fait (« et/ou », « 12/05 »), et elle a des
  **balises de portée** — ce dont `UIRegion.animated_glyphs` a besoin, puisqu'un effet par
  caractère s'applique à un intervalle et pas à un point. Précédent connu de beaucoup
  d'utilisateurs, donc rien à apprendre.
- **L'interpolation vit dans l'entrée, pas au site d'appel** : `hud_score` =
  `"score : $score_player"` → `score : 28`. Donc pas de varargs, donc une signature à trois
  arguments qui ne peut plus grandir. `$name` désigne un global ou une const (les deux ont
  déjà un namespace et un domaine de checker). **Porte fermée assumée** : pas de valeur
  calculée — `self:get_x()` passe par un global intermédiaire. Un score *est* un global dans
  la quasi-totalité des cas ; l'échange se fait contre une signature définitive.
- **Résolution au build, aucun parseur au runtime.** L'encodeur sort les codepoints
  affichables, une piste d'événements de tempo et la table des sources à interpoler. Trois
  gains : `text.length` reste la longueur *affichée*, le moteur n'embarque pas de parseur, et
  un littéral de script suit le même chemin puisque le codegen le voit aussi au build.
- **`draw` ne gagnera jamais largeur, alignement ni police en argument.** Chacun ramènerait
  `draw_box` : géométrie dans le script, invisible à l'éditeur, incalculable avant le build.
  La réponse à ces trois besoins est « dessine une zone », et c'est la bonne pédagogie.
- **Pas de retour à la ligne automatique dans `draw`** — `\n` seulement, comportement
  attendu d'un `print`. Corollaire à implémenter : un **clip franc** au bord de l'écran (et
  au rectangle pour `draw_in`), pour que le débordement soit visible et inoffensif au lieu
  d'aller écrire ailleurs dans le tilemap, ce qu'il fait aujourd'hui.
- **Les marqueurs de tempo sont ignorés par `draw`** : une tête de lecture doit s'accrocher à
  quelque chose de nommé, et un couple `(x, y)` ne l'est pas. Les marqueurs de valeur, eux,
  marchent partout.
- Conséquence à ne pas oublier : un texte à tempo introduit un **état de lecture** par zone,
  donc un petit groupe *lecture* (savoir si c'est fini, sauter au bout) à côté des deux
  primitives. Elles ne dessinent rien, la règle des deux fonctions tient.

#### Livré (grammaire position/conteneur → contenu)

- Toute la famille `text.*` réordonnée, **en Lua comme en C** : `text.draw(tx, ty, id)`,
  `draw_upto(tx, ty, id, n)`, `draw_num(tx, ty, value)`, `draw_in(region, id)`,
  `draw_in_upto(region, id, n)`, `draw_num_in(region, value)`. Un seul ordre partout plutôt
  qu'une permutation invisible entre les deux couches — `codegen._emit_api_call` mappe par
  position.
- **Migration automatique au chargement** (`project_migrations.migrate_text_arg_order`).
  C'est la seule migration du projet dont l'absence serait **invisible** : l'ancien ordre
  reste du Lua valide (mêmes noms, mêmes arités), donc ni le checker ni le compilateur C ne
  peuvent le voir — `text.draw("clé", 2, 16)` résoudrait « clé » comme une coordonnée.
- La détection se fait donc sur la **forme** des arguments, et pour `draw_in` sur le
  **namespace** de chaque chaîne (l'une nomme une zone, l'autre une clé de texte — les deux
  sont des chaînes dans les deux ordres). Ce qui reste indécidable — `draw_num` à trois
  littéraux entiers, ou un nom vivant dans les deux namespaces — est **signalé**, jamais
  deviné. Corollaire gratuit : la migration est idempotente, sans marqueur de version à
  poser (un marqueur peut mentir, une forme non).
- **Garde-fou d'ordre** ajouté à `validator._check_api_prototypes` : un désaccord d'ordre
  entre `api.py` et `gba_engine.h` est une erreur bloquante. C'est le seul désaccord de la
  chaîne qui compile proprement et rend faux à l'exécution, tous les paramètres étant des
  `int`. Seules les *permutations* sont signalées ; un renommage délibéré (`layer.show(n, on)`
  côté Lua, `layer_show(bg, on)` côté C) ne l'est pas — mesuré : 0 faux positif sur les 39
  fonctions du moteur.
- Même règle appliquée à `api_reference.json` : un libellé permuté par rapport au catalogue
  est régénéré au chargement (`RELABELED`), un paramètre simplement renommé est laissé — sinon
  on écraserait des exemples choisis à la main (`self:set_frame(0)` valant mieux que
  `self:set_frame(frame)`).
- **La sidebar n'a pas été touchée** et suit le nouvel ordre : c'est ce que le palier
  « snippets dérivés du catalogue » promettait, vérifié plutôt qu'affirmé.

#### Livré (langage de balisage — analyse et éditeur)

- **`core/text_markup.py`** : le parseur, point unique pour l'aperçu de l'éditeur et (à venir)
  l'encodeur. Une analyse rend trois choses : le texte **affiché** (balises retirées), les
  **marqueurs** repérés en coordonnées d'affichage — c'est ce que la piste d'événements
  émettra —, et les **anomalies** repérées en coordonnées de source, pour être soulignées
  dans l'atelier.
- **Six balises** : `[speed=n]`, `[pause=n]`, `[icon=nom]` (ponctuelles), `[wave]`, `[shake]`,
  `[color=n]` (de portée). Plus le marqueur de valeur `$nom`. `[[` échappe un crochet, `$$` un
  dollar — seuls eux ouvrent quelque chose, un `]` isolé passe toujours.
- **Un crochet en prose n'est pas une faute.** Une balise inconnue reste du texte, et n'est
  signalée que si sa forme trahit une TENTATIVE : nom voisin d'une balise connue (`[wav]`),
  casse fautive (`[Wave]`), valeur portée (`[foo=3]`), ou paire ouverte/fermée. « Touche [A] »
  s'écrit donc sans rien échapper et sans être signalée — même compromis que le checker de
  scripts sur les chaînes en forme de clé.
- **La résolution des références est dans l'éditeur, pas dans le parseur**, qui reste
  indépendant du projet : `[icon=X]` vérifie que la police porte ce glyphe (et renvoie vers la
  fusion de cases), `$nom` qu'il existe un global ou une const.
- **`Font.missing_chars()` est enfin branché** — il existait depuis l'import de police sans
  qu'aucun écran ne l'appelle. L'inspecteur croise le texte affiché avec la police d'aperçu.
#### Livré (encodeur — trois pistes, aucun parseur en ROM)

- **`emit_texts_c` résout le balisage au build.** Il sort les codepoints affichables, une
  piste d'événements par texte (`g_text_events` / `g_text_ev_count`) et la table des sources
  à interpoler (`g_text_values`). `g_text_len` est désormais la longueur ÉMISE.
- **Trois sorts pour un `$nom`**, et c'est ce qui rend l'encodeur simple :
  - **constante** → ses chiffres sont **cuits** dans les codepoints. Elle ne change jamais,
    la lire au runtime coûterait une indirection pour rien.
  - **global** → une place réservée (`TEXT_CP_VALUE`, le non-caractère U+FFFF, donc jamais
    un vrai glyphe) plus un **pointeur** dans `g_text_values`. Pointeur et pas index :
    `globals.h` déclare des variables C nommées (`g_score`), pas les cases d'une table.
  - **ni l'un ni l'autre** → écrit **littéralement**, exactement comme l'aperçu de l'éditeur
    le montre, et signalé dans le log de build. Une faute se voit sur la console au lieu de
    creuser un trou muet.
- La substitution passe par une **réécriture de la source** suivie d'une ré-analyse, jamais
  par un rapiéçage du résultat : une constante vaut « 7 » comme « 100 », donc décale tout ce
  qui suit — recalculer les positions à la main les ferait diverger au premier oubli.
- Les événements `icon` ne sont **pas** émis : le glyphe est déjà résolu dans les codepoints,
  la correspondance au plus long fait le reste. Rien à faire au runtime.
- **Les anomalies de balisage remontent dans le log de build**, pas seulement dans
  l'inspecteur — « Balise inconnue « wav » — vouliez-vous « wave » ? » apparaît au `make`.
- Vérifié : sur des textes **sans balise**, l'encodeur sort **exactement** les mêmes
  codepoints et longueurs qu'avant, aucun tableau d'événements n'est émis, et la ROM Pong
  construit (devkitARM, `-Wall` propre) avec les quatre textes de test injectés.

#### Livré (runtime — valeurs, tempo, effets)

- **Matérialisation.** Un texte qui porte des valeurs est recopié en RAM avec les chiffres
  substitués — même procédé que `text_draw_num`, donc un seul chemin de rendu. Les positions
  des ÉVÉNEMENTS se décalent d'autant : une **carte index source → index matérialisé** les
  recale toutes, plutôt qu'un rattrapage au fil de l'eau qui devrait rejouer à la main les
  cas d'imbrication et de portée à cheval sur une valeur. `text_length` rend donc la longueur
  AFFICHÉE, valeurs comprises.
- **Tête de lecture par ZONE** (`TextRead`), et non par appel : c'est la raison pour laquelle
  le tempo est ignoré par `text_draw` — une tête doit s'accrocher à quelque chose de nommé.
  Un texte SANS marqueur de tempo s'affiche entier, immédiatement : ne pas en mettre est une
  décision d'auteur, pas un oubli à compenser par une vitesse par défaut. Une pause
  s'AJOUTE à la cadence courante, sinon `[pause=0]` deviendrait un accélérateur.
- **Groupe lecture** : `text.reading(zone)` et `text.skip(zone)`. Ils ne dessinent rien de
  neuf — la règle « deux fonctions pour écrire » tient — mais sans eux un script n'aurait
  aucun moyen de savoir quand enchaîner.
- **Effets par caractère** : la capture vise désormais les glyphes couverts par une portée
  animée, et non les premiers venus — le budget `UIRegion.animated_glyphs` réserve de l'OAM
  pour un effet, pas pour un préfixe. L'effet déplace le SPRITE (deux mots d'OAM), jamais la
  composition : recomposer coûterait un rendu complet par frame pour deux pixels. Le rang du
  caractère déphase, sinon la portée monterait et descendrait d'un bloc.
- `text_update()` est appelée une fois par frame par le code généré, avant `oam_update` :
  une lecture démarrée pendant le tick avance dès cette frame.
- **Vérifié** : l'algorithme du moteur rejoué sur le C réellement généré rend **exactement**
  ce que `resolve()` affiche dans l'éditeur, sur 15 cas dont portées à cheval sur une valeur,
  valeurs multi-chiffres et imbrications. La ROM Pong construit (`-Wall` propre).

**Pas encore fait, et pourquoi** : le retrait de `draw_upto`/`draw_num`/`draw_num_in`. Le
Pong s'en sert pour son HUD (`text.draw_num(9, 2, global.get("score_player"))`), leur
remplacement passe par une entrée de table `"$score_player"` — donc par une migration qui
CRÉE des entrées à partir d'appels de script. Cette migration touche exactement le lien
global ↔ script que le chantier « index + nom utilisateur » va refaire : la faire maintenant
obligerait à la refaire après.

#### Livré (couleur — en ROM et dans l'atelier)

- **`[color=n]` au runtime**, sur les chemins COMPOSÉS (surface BG et bande de sprites) :
  `text_recolor` remappe l'encre d'une rangée de 8 pixels par un masque —
  `text_nib_mask(row) & (0x11111111 * n)`. La transparence est préservée, l'encre devient
  uniforme. Une police à plusieurs teintes est donc **aplatie** : `[color]` désigne une
  couleur, pas une transposition de rampe — supposer un rangement de palette en rampes aurait
  marché sur les polices qui l'ont et produit n'importe quoi sur les autres.
- **Le chemin tilemap ne peut pas suivre** : il pose une tuile DÉJÀ encrée, partagée par
  toutes ses occurrences ; la recolorer recolorerait le texte entier. Signalé aux deux
  endroits qui peuvent le savoir — le build (si aucune police du projet ne compose) et
  l'inspecteur (sur la police d'aperçu, qui elle est connue nommément).
- **1..15 est une contrainte matérielle**, pas un choix : 4bpp, l'index 0 est la transparence.
  Hors plage, `0x11111111 * n` déborderait son mot de 32 bits et le dernier nibble sortirait
  d'une autre couleur que les sept autres — d'où `TagSpec.vmin/vmax`, refusé à l'analyse, et
  une garde défensive au runtime.
- Un glyphe **animé** garde son encre : composé après la bande, donc hors du parcours de mise
  en page, il la reprend depuis la capture (`g_cap_ink`).

#### Livré (coloration des balises dans l'atelier)

- `markup_highlighter.py` lit les **spans du parseur** (`ParsedText.tokens`), jamais une
  seconde grammaire en expressions régulières. Ce qui est peint est donc exactement ce qui
  disparaîtra du rendu, et un `[wav]` fautif se lit comme du texte — ce qu'il sera.
- L'analyse porte sur le document ENTIER (une portée enjambe les retours à la ligne), puis
  les spans sont reprojetés dans chaque bloc, Qt ne colorant que bloc par bloc.
- Les anomalies **s'ajoutent** en soulignement ondulé sans repeindre : un `[wave]` jamais
  refermé reste peint en balise ET souligné, parce qu'il est les deux.

#### Livré (retrait des primitives datées)

- **Quatre fonctions retirées** : `text.draw_upto`, `text.draw_in_upto`, `text.draw_num`,
  `text.draw_num_in` — en Lua, dans `gba_engine.h` et dans `actor_api_static.h`. Il ne reste
  que `draw` / `draw_in` pour écrire, plus le groupe lecture. `text_num_cp` survit : c'est
  elle qui fabrique les chiffres d'une valeur interpolée.
- **Migration du mécanique seulement** (`migrate_removed_text_calls`), la règle déjà suivie
  pour `display.print` :
  - `draw_num(tx, ty, global.get("x"))` → une entrée de contenu `$x` + `draw(tx, ty, "clé")`.
    Un global cité deux fois ne donne qu'une entrée.
  - `draw_in_upto(zone, clé, scene.frame() / K)` → `draw_in(zone, clé)` + `[speed=K]` en tête
    du texte. K est exactement le nombre de frames par caractère, et c'est l'idiome que la
    doc de la fonction enseignait elle-même. Refusé si l'entrée porte déjà du tempo — deux
    rythmes sur la même entrée n'ont pas de réponse.
  - Tout le reste (valeur calculée, `draw_upto` qui n'a pas de zone où accrocher une tête de
    lecture) est **laissé en place et signalé**. Contrairement au réordonnancement
    d'arguments, l'absence de migration se VOIT ici : les fonctions n'existent plus.
- **Ordonnée en dernier**, après le réordonnancement d'arguments : elle lit les arguments par
  position, il lui faut donc le nouvel ordre déjà posé.
- **Bug de la passe ③ trouvé en écrivant la migration** : `text_draw_in` relançait la tête de
  lecture à chaque appel. Or un script appelle `draw_in` depuis `on_update`, donc soixante
  fois par seconde — le texte n'aurait jamais avancé. Il est désormais **idempotent** tant que
  la lecture court ; pour recommencer, `text.clear_in` (qui annule aussi la lecture) ou un
  autre texte. La façon la plus naturelle de s'en servir devait être la bonne.
- Le projet démo Pong est migré et construit : `intro_02` porte `[speed=6]`, et deux entrées
  `$score_player` / `$score_auto` remplacent les `draw_num`.

Reste à faire côté v0.3.2 : le type d'export `text` branché sur l'inspecteur existant —
attention, `exports_values` (les overrides par instance) n'est lu par **aucun** codegen
aujourd'hui, donc un menu de clés dans l'inspecteur serait une fausse feature tant que ce
câblage n'existe pas.

#### Ouvert

- Le layer BG unique réservé à l'UI (`Scene.text_bg` actuel) suffit-il une fois panneaux
  + texte + police custom ajoutés, ou faut-il en réserver plusieurs ?
- Indexation des appels à `text.set_font` par scène — sans elle, la réservation VRAM du
  texte retombe sur le maximum du projet (cf. `font_emit.scene_text_tiles`).
- Les dix méthodes `self:*` que la réconciliation d'`api_reference.json` regroupe dans une
  catégorie « Actor » fourre-tout, à ranger à la main dans Mouvement/Animation/Spawn.

Tranchés depuis : l'effet machine à écrire (`draw_upto`, puis les marqueurs), le retour à la
ligne automatique (dans une zone oui, dans `draw` non), la chasse proportionnelle (livrée),
et l'import de planche de glyphes sans éditeur de police (livré).

### v0.3.3 — UI en sprite

#### Décisions verrouillées

- Ajout d'un flag `screen_space: bool` sur `Actor` pour ancrer un actor à l'écran plutôt
  qu'au monde (ne scrolle pas avec la caméra). Réutilise tel quel le système
  `SpriteComponent` existant (animations, états, éditeur de sprite).

#### Ouvert

- Ordre d'affichage (z-order) entre UI en sprite (`screen_space`) et UI en background
  (v0.3.2) quand les deux se superposent — non défini.

---

## v0.4 — Éditeur de Background & animation de tuiles

Construit sur les fondations de la v0.3.1 (primitive de mutation de tilemap, scroll réel,
show/hide).

### v0.4.1 — Éditeur de Background

#### Déjà livré (par ricochet de la v0.2) — volet *peinture de palette* uniquement

L'écran Background Editor **existe** (`editor/ui/screens/background_editor_screen.py`), mais
uniquement dans sa dimension *couleur* — rien du volet « dessin » ci-dessous :

- Import / remplacement d'un PNG de fond, détection automatique du mode (tuilé 4bpp,
  tuilé 8bpp, bitmap Mode 4) et encodage, avec avertissement quand la détection force
  une perte.
- **Inpainting éditeur** : repeindre le `SE_PALBANK` d'une tuile 8×8 au pinceau sur le
  canvas, non-destructif (`BackgroundAsset.tile_palette_overrides` + `effective_tilemap()`),
  partagé par toutes les scènes qui utilisent le fond ; la gomme restaure l'original.
- Grille de sous-palettes (`PaletteSlotGridAsset`) alimentée par le catalogue, plafond 16.

Ce qui reste donc **entièrement** à faire en v0.4.1, c'est la *peinture de tuiles* : poser
des tuiles d'un tileset utilisateur sur une tilemap, et les UI layers réutilisables. Le
fond reste aujourd'hui une image importée qu'on recolore, pas une carte qu'on compose.

#### Décisions verrouillées

- Dessiner directement sur des Background Layers via des tilesets utilisateur importés
  ("tilesets utilisateur", jamais compilés tels quels). La classe résultante peut être
  ajoutée à une scène.
- Cet écran permet aussi de créer des **UI layers réutilisables** (across scenes, sans
  redéfinition).

#### Ouvert

- Aujourd'hui un seul charblock est câblé en dur par scène (voir v0.3.1). Décor + UI
  layer réutilisable en parallèle implique plusieurs charblocks/screenblocks simultanés
  — ampleur du changement de codegen VRAM pas encore évaluée.
- Une "UI layer réutilisable" est-elle un nouveau type de `Resource`, ou une variante de
  `BackgroundAsset` ?
- Indicateur de budget VRAM dans l'éditeur (évoqué en principe, pas conçu) — pertinent
  dès que plusieurs tilesets/charblocks coexistent.

### v0.4.2 — Animation de tuiles

#### Décisions verrouillées

- Trois techniques possibles selon le cas d'usage :
  1. *Swap d'index dans la tilemap* — peu coûteux, bien pour une torche/eau localisée.
  2. *Réécriture du charblock (DMA)* — anime instantanément toutes les cellules
     utilisant cette tuile, coût VRAM par frame, bien pour un effet plein écran.
  3. *Cycle de palette* — rotation des couleurs d'un bank (eau, lave qui scintille),
     quasi gratuit, se branche naturellement sur l'écran Palette de la v0.2.

---

## v0.5 — Sauvegarde (SRAM/Flash)

S'appuie sur le système `Globals` déjà existant pour décider quoi persister.

### Ouvert (quasiment tout)

- Portée : tous les `Globals` du projet, ou sélection explicite faite par l'utilisateur
  dans l'éditeur ?
- Un seul slot de sauvegarde, ou plusieurs ?

---

## v0.6 — Polish de la boucle de jeu

### v0.6.1 — Caméra

Gros sujet, à la fois fonctionnel et rendu — pas encore débattu en détail au-delà de
l'état des lieux ci-dessous.

#### État actuel (vérifié le 2026-07-06)

**Deux mécanismes de caméra coexistent aujourd'hui, indépendants et non coordonnés :**

1. **Déclaratif** (`Scene.cam_follow`, configuré par nom dans `camera_inspector.py`) —
   généré automatiquement dans le `scene_tick` : centre exactement sur l'acteur ciblé
   (`cam_x = actor.x - 120`, `cam_y = actor.y - 80` — 120/160 = moitié de la résolution
   écran 240×160), avec **clamp aux bords du monde**, mais seulement si `scroll_h`/
   `scroll_v` sont activés et qu'un fond existe (`main_gen.py:858-873`). Pas de zone
   morte : la caméra recentre exactement sur la cible à chaque frame.
2. **Scriptable** (`camera.follow(x, y, margin_x, margin_y)` en Lua → `camera_follow`
   en C, `runtime/include/actor_api_static.h:118-122`) — suivi par **zone morte**
   configurable (la caméra ne bouge que quand la cible sort de la marge), mais **sans
   aucun clamp aux bords du monde**.
3. Scroll manuel (aucun `cam_follow` configuré) : le D-pad déplace `cam_x`/`cam_y`
   directement (`main_gen.py:876-880`), **sans clamp non plus**.

Les trois écrivent les mêmes globales `cam_x`/`cam_y` sans coordination. **Risque
concret, pas juste théorique** : une scène avec `cam_follow` configuré dans l'inspector
ET un script qui appelle `camera.follow()` se disputent la position de la caméra.

Le parallax est câblé et fonctionne déjà pour n'importe lequel des trois mécanismes
ci-dessus, puisqu'il ne fait que lire `cam_x` (voir v0.3.1) — pas un sujet à reconstruire,
juste à exploiter.

**Zoom : impossible en Mode 0** (les layers BG regular ne supportent pas le
scaling) — bloqué tant que les layers affines de la v2.0 n'existent pas. À exclure
explicitement du scope v0.6.1, pas un oubli.

#### Décisions verrouillées (2026-07-06)

Contrainte de départ : la GBA n'a qu'un seul écran physique, et le multijoueur est hors
scope — "plusieurs caméras" ne peut donc pas vouloir dire plusieurs viewports simultanés
(pas de split-screen). Ça veut dire : **plusieurs configurations de caméra définissables,
une seule active à la fois par scène.**

- **`Camera` devient un nouveau type de `Resource`**, sur le même modèle que
  `Prefab`/`Sfx`/`Music`/`Font` (`to_dict`/`from_dict`). Ceci **remplace** les deux
  mécanismes en conflit décrits ci-dessus (`Scene.cam_follow` déclaratif +
  `camera.follow()` scriptable ad hoc) par une seule source de vérité : un objet
  `Camera` porte target/zone morte/bounds/shake en un seul endroit.
- **Stockage : `project/cameras/{name}.json`** — pas `assets/` (une config de caméra ne
  dépend d'aucune ressource externe, cohérent avec la distinction `assets/` vs
  `project/` déjà en place pour Prefab/variables).
- **Réutilisable entre scènes**, comme un Prefab — une caméra "boss_cam" définie une
  fois peut être référencée par plusieurs scènes.
- **Une seule caméra active à la fois par scène** (pas de rendu simultané, cohérent avec
  le hardware).
- **Changement de caméra active : appel API explicite uniquement**
  (`camera.activate("nom")` depuis un script) — **pas** de switch automatique par
  zone/trigger. Un comportement "zone" (ex: verrouiller la caméra dans une salle de
  boss) reste possible sans nouveau concept dédié : le script appelle simplement
  `camera.activate()` depuis le callback `onTriggerEnter` d'un `CollisionBoxComponent`
  trigger déjà existant. Pas besoin d'une Resource `CameraZone` séparée.
- **Caméra par défaut auto-créée à la création d'une scène** — l'utilisateur n'a jamais
  besoin de créer explicitement une `Camera` pour le cas simple à une seule caméra ;
  une Resource `Camera` par défaut est générée automatiquement en même temps que la
  `Scene`.
- **Nouveau champ sur `Scene`** (aux côtés de `render_mode`, voir v0.3.1) : référence par
  nom vers la `Camera` active **au démarrage** de la scène — remplace
  `Scene.cam_follow` comme point d'entrée déclaratif. Ce champ ne fixe que l'état
  initial ; `camera.activate()` peut en changer ensuite pendant l'exécution.
- **`scroll_h`/`scroll_v` restent sur `Scene`, ne migrent pas dans `Camera`.** Ce sont
  deux concepts différents : la `Camera` décide *comment* `cam_x`/`cam_y` sont calculés
  (suivi, zone morte, shake) ; `scroll_h`/`scroll_v` décrivent *si le niveau lui-même*
  est censé défiler dans cet axe (propriété du level design porté par la Scène et ses
  `BackgroundLayer`, pas de la caméra active). Changer de caméra active ne doit pas
  changer si le niveau défile. `scroll_h`/`scroll_v` agissent comme un filtre appliqué
  par-dessus la position calculée par la `Camera`, avant écriture dans `BGOFS`/OAM.
  - **Bug existant à corriger dans le même chantier** : aujourd'hui `scroll_h=False` ne
    bloque pas réellement le mouvement de la caméra en mode suivi, il ne bloque que le
    clamp aux bords (`main_gen.py:868` : `cam_x` est réassigné à `actor.x-120`
    indépendamment de `scroll_h`). Le flag ne fait pas ce que son nom promet — à
    corriger en posant le nouveau modèle, pas à documenter tel quel.
- **`Camera` peut recevoir un script Lua**, même pattern que `Scene.script`
  (`project.py:851`) et `ScriptComponent` : champ `script: str`, hooks `on_start()` /
  `on_update()` / `on_late_update()`. Les champs déclaratifs (target/zone morte/clamp/
  shake) sont **toujours calculés en premier** ; si un script est attaché, son
  `on_late_update()` s'exécute ensuite et peut lire/écraser `cam_x`/`cam_y` — comme un
  `ScriptComponent` d'Actor qui tourne après les autres systèmes. Permet un usage
  purement déclaratif (débutant), purement scripté (`target` laissé vide), ou hybride
  (déclaratif comme base + ajustement fin par script) sans flag de bascule dédié.

#### Ouvert

- Champs exacts de la Resource `Camera` (target actor par nom ? marges de zone morte ?
  bounds on/off ? paramètres de shake — amplitude/durée/décroissance ?) — pas encore
  spécifiés en détail.
- Nom exact du nouveau champ `Scene` et convention de nommage de la caméra par défaut
  auto-créée (ex : même nom que la scène ? toujours `"Default"` ?).
- Migration des scènes existantes : `Scene.cam_x`/`cam_y`/`cam_follow` actuels
  deviennent obsolètes au profit de ce nouveau champ — stratégie de migration à définir
  (pré-1.0, donc probablement pas critique).
- **Shake** — paramètres non conçus (amplitude, durée, décroissance).
- **Bounds clamping** — aujourd'hui présent seulement dans l'ancien mécanisme
  déclaratif ; à porter proprement dans le nouveau modèle `Camera`.

### v0.6.2 — Transitions de scène

- Fade in/out — aujourd'hui `scene.switch()` est un cut instantané (`api.py:264-268`),
  aucune trace de fade dans le codebase.

### v0.6.3 — Pentes / collision

- 22 types de tiles de pente sont définis côté éditeur (`project.py:792-816`,
  `TILE_SLOPE_L/R` 26°/45°/63° + miroirs plafond), à finaliser côté runtime.

#### Ouvert

- La résolution runtime réelle des pentes n'a **jamais été confirmée** par
  l'exploration — ce point pourrait être à *construire* plutôt qu'à *finaliser*.
  Vérifier l'état runtime avant de scoper ce chantier plus précisément.

---

## v0.7 — Son enrichi & écran de mixage

Les resources `Sfx` (`project.py:504-512`) et `Music` (`project.py:522-534`) sont
aujourd'hui des stubs marqués TODO explicitement dans le code.

### v0.7.1 — Clarification des resources Sfx/Music

- `Sfx` : format source (wav brut vs conversion Maxmod), pitch.
- `Music` : module tracker (.mod/.s3m/.xm/.it via Maxmod), loop point.

### v0.7.2 — Écran de mixage

- Existe déjà en partie (`ui/sound_mixer/sound_panel.py`), à enrichir : preview live du
  mix SFX+musique, volume par canal/catégorie, gestion des priorités (nombre de canaux
  hardware GBA limité).

#### Ouvert

- Politique de priorité/culling quand trop de SFX jouent simultanément — non décidée.

### v0.7.3 — API Lua

- `sfx.play`/`music.play` avec overrides pitch/volume à l'appel (pas seulement au
  niveau resource).

---

## v0.8 — Traduction des jeux créés avec l'éditeur (i18n runtime)

Sujet **séparé** de la traduction de l'éditeur (v0.10) — deux chantiers indépendants
que l'utilisateur a explicitement distingués.

### Scope

- Tables de strings multi-langues, basées sur les clés posées en v0.3 (les textes
  doivent être référencés par clé dès la v0.3, pas écrits en dur dans les scripts Lua,
  pour éviter un refactor complet ici).
- Sélection de langue en jeu, langue persistée via le save de la v0.5.

### Ouvert

- Format des tables de strings non défini.
- Workflow de traduction pour quelqu'un sans compétence dev : édition directe dans
  l'éditeur, ou export/import type tableur ?

---

## v0.9 — Distribution élargie

- Réactivation du job Linux/AppImage (actuellement `if: false` dans
  `.github/workflows/release.yml`, "en pause" en attendant un test sur une vraie distro).
- macOS : jamais mentionné dans le codebase actuel.

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût (compte développeur
  payant) — "Linux seul" est une option valable pour cette version si le coût ne se
  justifie pas.

---

## v0.10 — Traduction de l'interface de l'éditeur (i18n UI)

Complètement indépendant du runtime GBA — interface PyQt6 en plusieurs langues.
Déplaçable librement dans l'ordre (peut être fait en parallèle de n'importe quelle
autre version).

---

## v1.0 — Consolidation

- Un **deuxième jeu de démo** (au-delà de Pong) qui exerce réellement texte + save +
  caméra + transitions + traduction, pour valider tout le pipeline bout-en-bout comme
  Pong l'a fait pour la v0.1.
- Stabilisation, documentation.

### Ouvert

- Aucun genre choisi pour le deuxième jeu de démo. Un jeu de plateforme ou proto-RPG
  exercerait mieux les nouvelles features (dialogue, save, pentes, caméra, son) qu'un
  autre jeu type Pong.

---

## Au-delà de la v1.0

### v2.0 — Backgrounds affines ("Mode 7")

Modes vidéo GBA 1 et 2 : BG0/BG1 regular + BG2 affine (Mode 1), ou BG2/BG3 tous deux
affines (Mode 2). Un layer affine ajoute rotation + zoom (registres de matrice + point
de référence), au prix de perdre des layers regular ailleurs — et adresse sa tilemap
différemment d'un layer regular (8bpp uniquement, wraparound différent), donc un second
chemin de codegen, pas juste "un layer de plus".

- Support des layers BG affines, nouveau chemin de codegen dédié.
- API Lua pour piloter rotation/échelle/point de référence en jeu.
- Outil éditeur de configuration/prévisualisation.

Volontairement décrit à haut niveau — la portée exacte dépendra de ce qui aura été
appris en construisant les fondations de la v0.3.

#### Piste posée le 2026-07-21 — l'abstraction « caméra » sera remise en cause ici

La caméra n'est aujourd'hui pas une entité : `cam_x`/`cam_y` plus un `Scene.cam_follow`.
Elle est en train d'en devenir une, en absorbant les **windows** de la v0.3.2 — auquel cas
ce n'est plus « où on regarde » mais **une configuration d'écran nommée qu'on active** :
cadrage, suivi, et régions qui découpent l'affichage. Modèle retenu : des caméras
**mutuellement exclusives** (une seule active à la fois), donc 2 windows par caméra
n'implique jamais plus de 2 rectangles par frame — la contrainte matérielle tient.

Nom de travail : **`Caméra2D`** (convention Godot, immédiatement lisible). Réserve à
garder en tête : il promet une `Caméra3D` qui n'existera jamais sur GBA. Le Mode 7 n'est
pas de la 3D mais une transformation **affine** 2D. Le jour où une seconde caméra arrive,
le vrai axe est donc *régulière* (translation seule, `BGOFS`) vs *affine* (translation +
rotation + zoom, `BGxPA-PD` + point de référence) — pas 2D/3D.

Deux choses à traiter à ce moment-là, pas avant :
- **Unifier les deux mécanismes de caméra concurrents** (cf. v0.6.1) : c'est quand la
  caméra devient un objet nommé porteur d'un état qu'il devient absurde d'en avoir deux.
- **Le split-screen** rouvrira la question « une région appartient-elle à une caméra, ou
  l'inverse ? ». Tant que les caméras sont exclusives, la question ne se pose pas.

### v3.0 — Modes bitmap (framebuffer direct)

Modes vidéo GBA 3/4/5 — famille complètement différente des modes tile, seul BG2
existe, pas de tilemap/charblock/screenblock, framebuffer direct.

| Mode | Résolution | Couleur | Buffers |
|---|---|---|---|
| 3 | 240×160 | 16-bit direct | 1 seul (75 Ko / 96 Ko VRAM, pas de place pour un 2e) |
| 4 | 240×160 | 8-bit indexé (palette BG) | 2 (double buffer, 75 Ko total) |
| 5 | 160×128 | 16-bit direct | 2 (80 Ko total, résolution réduite) |

En mode bitmap, la VRAM des sprites démarre plus tard (0x06014000 au lieu de
0x06010000) : le budget tuiles OBJ est divisé par deux (16 Ko au lieu de 32 Ko).

- Pipeline de rendu indépendant du système de tuiles, **priorité au mode 4** (256
  couleurs, double buffer, pleine résolution — évite le tearing du mode 3 et la
  résolution réduite du mode 5).
- Outils d'import/dessin pixel direct, API de blit depuis Lua.
- Modes 3/5 en option selon les besoins réels identifiés.

**Exclu délibérément des fondations v0.3** : les modes bitmap cassent tout le pipeline
actuel (grit, tilesets réutilisables, palettes par bank) au profit d'un framebuffer
brut — un moteur de rendu différent, pas une extension. Rarement utilisés dans de vrais
jeux commerciaux pour cette raison (coût VRAM/bande passante, pas de réutilisation de
tuiles).

---

## Hors scope (pour l'instant)

- **Multijoueur (link cable)** — envisagé après la v1.0, pas avant. Feature GBA très
  spécifique et coûteuse à implémenter proprement.
