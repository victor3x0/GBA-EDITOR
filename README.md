# GBA Editor

Éditeur de jeux Game Boy Advance basé sur Python/PyQt6 + devkitPro.

---

## Architecture

```
gba-editor/
├── editor/                          ← application Python (PyQt6)
│   ├── main.py                      ← point d'entrée
│   ├── window.py                    ← MainWindow + onglets
│   ├── core/
│   │   ├── project.py               ← modèle de données (project.json)
│   │   ├── project_watcher.py       ← détection live des assets
│   │   ├── scene_editor.py          ← canvas GBA - Placer des acteurs, dessiner ses collisions.
│   │   └── ...
│   ├── codegen/
│   │   ├── pipeline.py              ← orchestration build
│   │   ├── asset_pipeline.py        ← grit (sprites + BG)
│   │   └── runtime_codegen/         ← génération main.c, scènes, acteurs
│   ├── scripting/                   ← compilation Lua → C
│   └── ui/
│       ├── sprite_editor.py         ← éditeur de sprites (tile-based)
│       ├── build_panel.py
│       ├── inspectors_module.py
│       └── ...
├── runtime/
│   └── Makefile                     ← copié dans build/ au moment du build
└── projects/                        ← projets utilisateur
    └── Pong/                        ← projet démo
        ├── project.json
        ├── assets/
        │   ├── sprites/             ← PNG + JSON sidecar (SpriteAsset)
        │   ├── backgrounds/         ← PNG bruts (BackgroundImage)
        │   └── scripts/             ← scripts Lua source (acteurs + scènes)
        ├── project/
        │   ├── scenes/              ← définition des scènes (.json)
        │   ├── backgrounds/         ← BackgroundAsset (.json) — assemblages de layers
        │   └── prefab/              ← préfabs d'acteurs (.json)
        └── build/                   ← 100% généré, gitignored
```

---

## Terminologie

### Correspondances éditeur ↔ GBA / grit

Ces concepts ont un équivalent direct dans le hardware ou la toolchain.

| Éditeur | GBA / grit | Description |
|---------|------------|-------------|
| `SpriteAsset` | tiles OBJ VRAM | PNG converti par grit en tiles 8×8 chargées dans OBJ VRAM |
| `TileCell` | tile index VRAM | Une tile 8×8 référencée par son index dans VRAM |
| `AnimFrame` | plage de tile indices | Un état visuel = N tiles dans VRAM |
| `Actor` | `OBJATTR` (OAM) | Instance affichée à l'écran via une entrée OAM |
| `BackgroundImage` | PNG source | Image brute dans `assets/backgrounds/`, source pour grit |
| `BackgroundLayer` | charblock + screenblock BG | `{image, bg_slot, scroll_speed}` — un plan BG physique |
| `BackgroundAsset` | `REG_BGxCNT` × N | Assemblage de layers dans `project/backgrounds/*.json`, assigné à une scène |
| `Scene.background_asset` | ensemble de `REG_BGxCNT` activés | Référence (par nom) au `BackgroundAsset` de la scène |
| `Scene` | `scene_init_X` / `scene_tick_X` | Paire de fonctions C dispatchées via vtable dans `main.c` |
| `ScriptComponent` (Lua) | fonction C compilée | Le Lua est transpilé vers C, pas interprété à l'exécution |

### Abstractions pures de l'éditeur

Ces concepts n'ont pas d'équivalent direct dans grit ou le hardware GBA.

| Concept | Rôle | Résolution au build |
|---------|------|---------------------|
| `Prefab` | Template d'acteur réutilisable | Chaque instance génère son propre code C |
| `AnimState` | État d'animation nommé (`Idle`, `Walk`…) | Converti en index entier, pas de concept GBA natif |


### Components

| Nom | Rôle | API Lua |
|-----|------|---------|
| `SpriteComponent` | Lien vers un `SpriteAsset`, état initial, vitesse d'animation... | `self:play_anim("state")` `self:set_frame(n)` `self:set_visible(bool)` `self:set_flip_h(bool)` `self:set_pal(n)` |
| `CollisionBoxComponent` | AABB de collision. `solid=true` → résolution physique ; `solid=false` → trigger | callbacks : `onCollisionEnter(id)` `onCollisionExit(id)` `onTriggerEnter(id)` `onTriggerExit(id)` |
| `SoundFxComponent` | Déclenche un effet sonore lié à l'acteur | `sfx.play("name")` |
| `ScriptComponent` | Attache un script Lua à l'acteur | `on_start()` `on_update()` `on_late_update()` |
| `PathComponent` | Chemin de déplacement (waypoints) | — (en cours) |

### Règles clés

- `assets/` → la source de vérité des assets bruts ; le JSON sidecar est auto-géré par l'éditeur
- `assets/backgrounds/` → PNG bruts (`BackgroundImage`) ; `project/backgrounds/` → assemblages de layers (`BackgroundAsset`)
- `assets/scripts/` → scripts Lua édités par le dev ; copiés dans `build/src/` au build
- `build/grit_out/` et `build/src/` → effacés et regénérés à chaque build ; `build/obj/` est conservé pour la compilation incrémentale
- `project.json` → config racine uniquement (nom, scène de démarrage, auteur, globals) ; toutes les données vivent dans `project/**/*.json`
- Les assets sont référencés **par nom** (ex. `SpriteComponent.sprite_name`, `Scene.background_asset`) — jamais par chemin absolu
- Les scripts Lua sont **transpilés vers C** au build, pas interprétés à l'exécution
- Les `GlobalVar` sont des variables C partagées entre tous les scripts d'une scène (`globals.h` / `globals.c` générés)
- Chaque scène génère une paire C `scene_init_X` / `scene_tick_X` dispatchée via une vtable statique dans `main.c`

---

## Pipeline de build

```
① Validation du projet (scenes, sprites, scripts)

② grit BG — par scène (si un BackgroundAsset est assigné)
   assets/backgrounds/{image}.png  (via BackgroundAsset.layers)
       → grit              → build/grit_out/{scene}_tileset.c/.h

③ grit Sprites — union de toutes les scènes + prefabs (dédupliqués)
   assets/sprites/{name}.png
       → grit              → build/grit_out/sprite_{name}.c/.h

④ Audio (optionnel)
   assets/sounds/*.wav/.mod
       → mmutil + bin2s     → build/grit_out/soundbank.*

⑤ Génération des headers C
   project/ + sprites
       → codegen            → build/src/actor_types.h
                            → build/src/actor_api.h

⑥ Transpilation Lua → C — toutes les scènes en une passe
   assets/scripts/scenes/*.lua   → build/src/{scene}_scene.c
   assets/scripts/actors/*.lua   → build/src/actor_{name}.c
   (globals partagés)            → build/src/globals.c / globals.h

⑦ Génération de main.c
   all_scene_data + prefabs
       → codegen            → build/src/main.c

⑧ Compilation + link
   build/src/*.c + build/grit_out/*.c
       → arm-none-eabi-gcc  → build/obj/*.o
       → make (Makefile)    → build/rom.elf → build/rom.gba

⑨ Lancement
   build/rom.gba → mgba
```

---

## Dépendances externes

```mermaid
flowchart TD
    APP["GBA Editor<br/>(Python + PyQt6)"]

    subgraph PY["Runtime Python"]
        PYQT["PyQt6<br/>interface graphique"]
        PIL["Pillow<br/>traitement d'images (asset pipeline)"]
        QTA["qtawesome<br/>icônes (optionnel)"]
    end

    subgraph DKP["devkitPro — toolchain GBA"]
        ARM["devkitARM<br/>arm-none-eabi-gcc"]
        GRIT["grit<br/>PNG → tiles/palettes GBA"]
        LIBGBA["libgba<br/>bibliothèque hardware"]
        MMUTIL["mmutil<br/>conversion audio (maxmod)"]
        MAKE["make<br/>orchestration du build"]
    end

    MGBA["mGBA<br/>émulateur (Build &amp; Run)"]

    APP --> PY
    APP --> DKP
    APP --> MGBA
    PY --> PYQT
    PY --> PIL
    PY --> QTA
    DKP --> ARM
    DKP --> GRIT
    DKP --> LIBGBA
    DKP --> MMUTIL
    DKP --> MAKE
```

`PyQt6` et `Pillow` sont des paquets Python (voir `requirements.txt`, détectés par l'onglet *Insights → Dependency graph* de GitHub). `devkitPro` et `mGBA` sont des outils système installés séparément — ils n'apparaissent pas dans un gestionnaire de paquets Python.

---

## Prérequis

```bash
# Python
pip install -r requirements.txt

# devkitPro (installe devkitARM + grit + libgba + mmutil + make)
# https://devkitpro.org/wiki/Getting_Started
dkp-pacman -S gba-dev

# mgba
# https://mgba.io/downloads.html

# Lancement
python editor/main.py
```
