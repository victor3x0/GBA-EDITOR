# GBA Editor

Un éditeur visuel pour créer des jeux Game Boy Advance : scènes, sprites, collisions et un langage de scripts intégré (Lua, transpilé en C) depuis une seule interface. Basé sur Python/PyQt6, s'appuie sur la toolchain officielle **devkitPro** pour compiler de vraies ROMs `.gba` jouables sur émulateur ou hardware.

---

## Installation

1. Télécharger le dernier `.exe` depuis l'onglet [Releases](https://github.com/victor3x0/GBA-EDITOR/releases).

Pour compiler et lancer des ROMs, deux outils externes sont nécessaires (l'éditeur les détecte automatiquement s'ils sont installés, sinon il propose leur chemin de téléchargement) :

| Outil | Rôle | Lien |
|-------|------|----------------|
| **devkitPro** (devkitARM + grit + make) | Compile le C généré en ROM `.gba` | [devkitpro.org](https://devkitpro.org/wiki/Getting_Started) |
| **mGBA** | Émulateur pour tester la ROM (Build & Run) | [mgba.io](https://mgba.io/downloads.html) |

## Fonctionnalités

- **Éditeur de scènes** — placement d'acteurs, réglage des collisions, caméra, directement sur un canvas GBA (240×160).
- **Éditeur de sprites** — dessin tile par tile, animations par états (`Idle`, `Walk`, ...).
- **Scripting Lua** — logique de jeu et d'acteurs en Lua, transpilé en C au build (pas d'interpréteur embarqué, donc pas de perte de perf à l'exécution).
- **Son** — effets sonores et musique (maxmod), gérés depuis l'éditeur.
- **Prefabs** — acteurs réutilisables entre scènes.

## Projet de démo

Un jeu Pong complet (scènes, sprites, scripts, son) est disponible dans [`Project Demo/Pong`](https://github.com/victor3x0/GBA-EDITOR/tree/main/Project%20Demo/Pong) — pas embarqué dans l'exe, à télécharger directement depuis GitHub (clique sur le lien, ou clone/télécharge le repo en ZIP) puis à placer dans ton dossier `GBAProjects` local pour l'ouvrir depuis l'éditeur.

---

## Comment ça marche (pour aller plus loin)

Un projet vit dans son propre dossier (`assets/` pour les sources — sprites, backgrounds, scripts — et `project/` pour les scènes/prefabs/assemblages). Le bouton *Build & Run* orchestre  le pipeline : conversion des assets via `grit`, transpilation Lua → C, génération du `main.c`, compilation avec `arm-none-eabi-gcc`, puis lancement dans mGBA. Le code Python de l'éditeur vit dans `editor/`, le runtime C partagé par toutes les ROMs dans `runtime/`.

---

## Crédits

Musiques du projet de démo par **Tiptoptom Cat** — [itch.io](https://tiptoptomcat.itch.io/).