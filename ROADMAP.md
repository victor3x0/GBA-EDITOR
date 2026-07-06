# Roadmap détaillée

Ce document est la version détaillée de la section "Roadmap" du [README](README.md) — le
README reste volontairement condensé (une ligne par version, pour un lecteur public) ;
ce fichier explique le scope, les décisions verrouillées et les questions encore ouvertes
derrière chaque jalon. Construit en session le 2026-07-06, juste après la sortie de la v0.1
(démo Pong complète).

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

### Décisions verrouillées

- **Deux pools séparés**, fidèles au hardware GBA (mémoire palette OBJ et BG
  physiquement distinctes) : 16 palettes OBJ (sprites) × 16 couleurs, 16 palettes BG
  (fonds) × 16 couleurs.
- **Nouvel écran Palette** dédié pour construire ces palettes à la main.
- **Import** : depuis un PNG (bande de couleurs) ou un export standard Aseprite
  (PNG/`.gpl`) — pas de parsing du format `.aseprite` natif (trop de travail pour la
  valeur ajoutée, fragile aux évolutions du format).
- **Réservoir auto-import** : N banks par pool réservées à l'import automatique (grit
  récupère les couleurs des PNG non explicitement palettisés). Défaut N=3 (48 couleurs
  auto par pool).
  - Quand le réservoir est plein : **pas d'éviction** — la nouvelle couleur est mappée
    vers la couleur auto existante la plus proche. Aucun asset déjà construit ne change
    de rendu (contrairement à un override silencieux, qui aurait pu casser des assets
    sans rapport).
  - **Réglages projet** (pas éditeur) : le toggle marche/arrêt de l'auto-import ET le
    nombre de banks réservées sont tous les deux des réglages par projet.
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

### Ouvert

- `Scene` doit probablement recevoir un nouveau champ palette dédié pour porter les
  overrides par `BackgroundLayer` — à ajouter au même endroit que le champ `render_mode`
  (voir v0.3).
- Calcul de "couleur la plus proche" (distance colorimétrique — RGB15 GBA ?) non précisé.

---

## v0.3 — Fondations runtime "background vivant" + Texte & UI in-game

### État actuel (vérifié par exploration du runtime, 2026-07-06)

Le système de background est aujourd'hui **build-time only**, pensé pour du décor
pré-cuit et statique :

- Mode 0 confirmé (4 layers regular max), mais **un seul tileset partagé par scène**,
  chargé une fois dans un charblock fixe à l'init (`editor/codegen/runtime_codegen/main_gen.py:576`).
- **Le scroll parallax n'est pas câblé** : le champ `scroll_speed` existe sur
  `BackgroundLayer` mais rien n'écrit dans les registres `BGxHOFS/VOFS` au runtime —
  champ mort aujourd'hui.
- **Aucune mutation de tilemap au runtime** : pas de fonction pour écrire une tuile à
  `(x,y)`, ni côté C (`gba_engine.h`) ni exposée en Lua. `tile.get` (`api.py:378-383`)
  ne lit que la carte de collision, pas la VRAM.
- **Aucun show/hide de layer** : les bits `DISPCNT` sont posés une fois à l'init de
  scène et jamais retouchés.
- Tout l'agencement VRAM (charblock/screenblock) est figé au moment du build.

Le texte est un **cas particulier de la même primitive manquante** : afficher du texte
sur un BG, c'est écrire des index de tuiles (glyphes) dans une tilemap au runtime, frame
après frame. Donc la fondation "mutation de tilemap au runtime" sert à la fois le texte
et (en v0.4) l'éditeur de background/l'animation — pas de scope redondant entre les deux
chantiers.

### Décisions verrouillées

- Câblage réel du scroll matériel (écriture effective des registres `BGxHOFS/VOFS`).
- Primitive générique de **mutation de tilemap au runtime**, exposée en Lua.
- **Show/hide de layer** exposé en Lua.
- Police custom (`Font`, actuellement un stub vide dans `project.py:544`) et API texte
  enrichie (dialogues, HUD, menus) — construits sur la primitive de mutation ci-dessus.
- **UI en sprite** : ajout d'un flag `screen_space: bool` sur `Actor` pour ancrer un
  actor à l'écran plutôt qu'au monde (ne scrolle pas avec la caméra). Réutilise tel quel
  le système `SpriteComponent` existant (animations, états, éditeur de sprite).
- **Champ `render_mode` sur `Scene`** (`editor/core/project.py`, dataclass `Scene`
  autour de la ligne 842, à côté de `text_bg`/`collision_layer`) : ajouté dès maintenant,
  défaut = Mode 0, **caché dans `scene_inspector.py`** tant qu'aucun autre mode n'est
  supporté. Anticipe v2.0 (Mode 7) et v3.0 (bitmap) sans migration de fichiers de scène
  plus tard.

### Ouvert

- API texte concrète : effet machine à écrire ? retour à la ligne automatique ? une ou
  plusieurs polices actives simultanément par scène ?
- `Font` : glyphes à largeur fixe seulement, ou proportionnelle ? Import spritesheet de
  glyphes vs éditeur de police dédié ?
- Le layer BG unique réservé à l'UI (`Scene.text_bg` actuel) suffit-il une fois panneaux
  + texte + police custom ajoutés, ou faut-il en réserver plusieurs ?
- Ordre d'affichage (z-order) entre UI en sprite (`screen_space`) et UI en background
  quand les deux se superposent — non défini.

---

## v0.4 — Éditeur de Background & animation de tuiles

Construit sur les fondations de la v0.3 (primitive de mutation de tilemap, scroll réel,
show/hide).

### Décisions verrouillées

- **Éditeur de Background** : dessiner directement sur des Background Layers via des
  tilesets utilisateur importés ("tilesets utilisateur", jamais compilés tels quels).
  La classe résultante peut être ajoutée à une scène.
- Cet écran permet aussi de créer des **UI layers réutilisables** (across scenes, sans
  redéfinition).
- **Animation de tuiles**, trois techniques possibles selon le cas d'usage :
  1. *Swap d'index dans la tilemap* — peu coûteux, bien pour une torche/eau localisée.
  2. *Réécriture du charblock (DMA)* — anime instantanément toutes les cellules
     utilisant cette tuile, coût VRAM par frame, bien pour un effet plein écran.
  3. *Cycle de palette* — rotation des couleurs d'un bank (eau, lave qui scintille),
     quasi gratuit, se branche naturellement sur l'écran Palette de la v0.2.

### Ouvert

- Aujourd'hui un seul charblock est câblé en dur par scène (voir état v0.3 ci-dessus).
  Décor + UI layer réutilisable en parallèle implique plusieurs charblocks/screenblocks
  simultanés — ampleur du changement de codegen VRAM pas encore évaluée.
- Une "UI layer réutilisable" est-elle un nouveau type de `Resource`, ou une variante de
  `BackgroundAsset` ?
- Indicateur de budget VRAM dans l'éditeur (évoqué en principe, pas conçu) — pertinent
  dès que plusieurs tilesets/charblocks coexistent.

---

## v0.5 — Sauvegarde (SRAM/Flash)

S'appuie sur le système `Globals` déjà existant pour décider quoi persister.

### Ouvert (quasiment tout)

- Portée : tous les `Globals` du projet, ou sélection explicite faite par l'utilisateur
  dans l'éditeur ?
- Un seul slot de sauvegarde, ou plusieurs ?

---

## v0.6 — Polish de la boucle de jeu

### Scope

- **Caméra** : bounds (limites de scroll), shake, zones — aujourd'hui juste
  follow-target + pan manuel (`camera_inspector.py`), pas de bounds/shake/zones.
- **Transitions de scène** : fade in/out — aujourd'hui `scene.switch()` est un cut
  instantané (`api.py:264-268`), aucune trace de fade dans le codebase.
- **Pentes** : 22 types de tiles de pente sont définis côté éditeur
  (`project.py:792-816`, `TILE_SLOPE_L/R` 26°/45°/63° + miroirs plafond), à finaliser
  côté runtime.

### Ouvert

- La résolution runtime réelle des pentes n'a **jamais été confirmée** par
  l'exploration — ce point pourrait être à *construire* plutôt qu'à *finaliser*.
  Vérifier l'état runtime avant de scoper ce chantier plus précisément.

---

## v0.7 — Son enrichi & écran de mixage

Les resources `Sfx` (`project.py:504-512`) et `Music` (`project.py:522-534`) sont
aujourd'hui des stubs marqués TODO explicitement dans le code.

### Scope

- Clarifier `Sfx` : format source (wav brut vs conversion Maxmod), pitch.
- Clarifier `Music` : module tracker (.mod/.s3m/.xm/.it via Maxmod), loop point.
- **Écran de mixage** (existe déjà en partie, `ui/sound_mixer/sound_panel.py`) enrichi :
  preview live du mix SFX+musique, volume par canal/catégorie, gestion des priorités
  (nombre de canaux hardware GBA limité).
- API Lua `sfx.play`/`music.play` avec overrides pitch/volume à l'appel (pas seulement
  au niveau resource).

### Ouvert

- Politique de priorité/culling quand trop de SFX jouent simultanément — non décidée.

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
