
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

- **Un glyphe = une tuile** (rendu à chasse fixe, sur la primitive `tilemap.*` de la
  v0.3.1). Le rendu pixel-dans-la-tuile — chasse proportionnelle, placement au pixel — est
  reporté ; l'asset stocke déjà `advance` pour que **rien ne soit à réimporter** ce
  jour-là. Bénéfice caché du choix : un glyphe étant une tuile, `tilemap.set_palette` le
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
  `display.print` (TTE) reste disponible entre-temps, donc aucun projet n'est muet.

#### Livré (asset Font + import)

- `core/models/font.py` — `Glyph` (rect + `advance` + offsets) et `Font` (`asset`,
  `descriptor`, `cell_w/h`, `line_height`, `glyphs`), modèle **à rectangles** pour
  accueillir BMFont ; `charset` dérivé, `missing_chars()`, `tile_count()`.
- `core/font_import.py` — `detect_grid()` (découpage noté), `propose_charset()`,
  `import_font_png()` (mesure d'encre, bourrage de fin retiré), `parse_bmfont()`
  texte + XML, `import_font_fnt()`.
- `core/asset_sync.py::sync_font_file` + `project_migrations.reconcile_fonts`
  (dépôts hors ligne, `.fnt` prioritaire sur sa page).

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
- `main_gen` émet les tables et appelle `text_set_layer` + `text_set_font(0)` à l'init de
  chaque scène. Un projet sans police ni texte émet des tables vides et compile.

**Pas de réglage de vitesse dans le moteur** : `text.draw_upto(id, tx, ty, n)` révèle les
n premiers caractères, et le rythme appartient au script. Un champ « vitesse du texte »
dans l'inspecteur choisirait le genre à la place de l'utilisateur — même refus que pour
les boîtes de dialogue.

Reste à faire côté v0.3.2 : le type d'export `text` branché sur l'inspecteur existant,
l'écran Textes et l'écran Police. `rename_text_key` ne réécrit pas encore les références
Lua — à faire avec le type d'export, sur le modèle de `rename_export`.

#### Ouvert

- API texte concrète : effet machine à écrire ? retour à la ligne automatique ? une ou
  plusieurs polices actives simultanément par scène ?
- `Font` : glyphes à largeur fixe seulement, ou proportionnelle ? Import spritesheet de
  glyphes vs éditeur de police dédié ?
- Le layer BG unique réservé à l'UI (`Scene.text_bg` actuel) suffit-il une fois panneaux
  + texte + police custom ajoutés, ou faut-il en réserver plusieurs ?

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
