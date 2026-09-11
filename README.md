# GBA Editor

Un éditeur visuel pour créer des jeux Game Boy Advance en Lua : scènes, sprites, collisions, son, depuis une seule interface.
Développé en Python/PyQt6, le projet s'appuie sur la toolchain devkitPro pour compiler de véritables ROMs .gba, jouables aussi bien sur émulateur que sur console.
Le choix de Lua s'est imposé pour sa simplicité et sa légèreté. Les scripts sont transpilés en C lors de la compilation, garantissant des ROMs optimisées, sans machine virtuelle ni coût d'exécution supplémentaire.

---

## Comment ça marche

Chaque projet est entièrement contenu dans son propre dossier. 
Vous y retrouvez vos ressources (sprites, backgrounds, scripts, sons...), ainsi que les scènes et les éléments qui composent votre jeu.
Importez vos backgrounds, ajoutez un acteur, construisez la logique de votre jeu.
Il suffit de cliquer sur Build & Run. 

L'éditeur s'occupe automatiquement de préparer les ressources & de générer le code C nécessaire afin de tester votre jeu.

---

## Installation

1. Télécharger depuis l'onglet [Releases](https://github.com/victor3x0/GBA-EDITOR/releases), au choix :
   - **`GBAEditor-<version>-windows-setup.exe`** — installateur. S'installe pour votre compte utilisateur uniquement, sans demander de droits administrateur.
   - **`GBAEditor-<version>-windows-portable.zip`** — version portable. Décompressez où vous voulez et lancez `GBA Editor.exe`.

Pour compiler et lancer des ROMs, deux outils externes sont nécessaires (l'éditeur les détecte automatiquement leur installation) :

| Outil | Rôle | Lien |
|-------|------|----------------|
| **devkitPro** (devkitARM + grit + make) | Compile le C généré en ROM `.gba` | [devkitpro.org](https://devkitpro.org/wiki/Getting_Started) |
| **mGBA** | Émulateur pour tester la ROM (Build & Run) | [mgba.io](https://mgba.io/downloads.html) |

## Fonctionnalités

- **Construisez vos niveaux à la souris** : posez acteurs, collisions et caméra directement sur un canvas GBA, et voyez votre scène telle qu'elle sera sur la console.

![Scene Manager](docs/screenshots/SceneEditor.png) 

- **Animez vos personnages** : découpez une spritesheet et montez vos animations image par image, sans outil externe.

![Sprite Editor](docs/screenshots/SpriteEditor.png)

- **Écrivez votre gameplay en Lua** : un langage simple à apprendre, traduit en C optimisé à la compilation — vos ROMs tournent à pleine vitesse, sans machine virtuelle ni ralenti.

![Script Editor](docs/screenshots/ScriptEditor.png)

  Comme le script est *traduit* et non interprété, le langage accepté est un sous-ensemble de Lua : [**SCRIPTING.md**](SCRIPTING.md) dit ce qu'on peut écrire, ce qui ne marche pas, et quoi écrire à la place.

- **Habillez votre jeu de son** : effets sonores et musique (maxmod) gérés directement dans l'éditeur.

- **Réutilisez votre travail** : transformez un acteur en *prefab* et réemployez-le d'une scène à l'autre, avec ses composants et sa logique.

- **Assemblez par composants** : des briques empilables (sprite, collision, script, son) qui s'attachent à un acteur et se pilotent en Lua — vous composez un comportement au lieu de le recoder.

## Projet de démo

Un jeu Pong complet (scènes, sprites, scripts, son) est disponible dans [`Project Demo/Pong`](https://github.com/victor3x0/GBA-EDITOR/tree/main/Project%20Demo/Pong)
à télécharger directement depuis GitHub (clique sur le lien, ou clone/télécharge le repo en ZIP) puis à placer dans ton dossier `GBAProjects` local pour l'ouvrir depuis l'éditeur.

---

### Objectif de la Version 1.0

Première version stable de **GBA Editor** : le pipeline 2D complet, de bout en bout.

L'objectif est énoncé comme une cible, pas comme une liste de fonctionnalités — à la v1.0,
ces cinq genres doivent être réalisables avec l'éditeur :

| Genre | Ce qu'il exerce |
| --- | --- |
| Platformer | gravité, pentes, collision de tuiles, caméra en suivi |
| Metroidvania | état persistant entre scènes, déverrouillages |
| RPG | tables de données, menus, dialogues, sauvegarde longue |
| Tactique (Advance Wars) | grille, liste d'unités, recherche de chemin |
| Gestion (Zoo Tycoon) | beaucoup d'entités à état propre, économie |

Plus la stabilisation du runtime et de l'éditeur, la documentation utilisateur, et un
deuxième jeu de démo choisi parmi les genres les plus exigeants de cette liste.

Et quatre points qui ne sont pas des fonctionnalités, mais sans lesquels le mot « 1.0 » ne
tient pas : une licence (**faite** — cf. plus bas), des formats de fichiers qu'un outil de
version sait relire, des modèles de projet pour démarrer, et la vérification que l'éditeur
tient à l'échelle d'un vrai projet.

## Roadmap vers la v1.0

Où en est l'éditeur, et ce que chaque étape apporte à vos jeux. Les versions marquées ✅ sont
déjà là ; les autres arrivent. La [ROADMAP](ROADMAP.md) détaillée en donne l'ordre recommandé.

- **v0.2** ✅ : **Palettes de couleurs** — un catalogue de couleurs partagé par tout le jeu, avec import de vos palettes favorites.
- **v0.3** ✅ : **Décors et interface** — des fonds à plusieurs couches, du texte, des menus et une UI dessinés à l'écran, avec vos propres polices.
- **v0.4** ✅ : **Décors animés** — eau, flammes, couleurs qui pulsent : des fonds vivants posés au canvas et pilotables au script.
- **v0.5** ✅ : **Sauvegarde** — la progression du joueur persiste sur la cartouche, avec plusieurs emplacements.
- **v0.6** ✅ : **Le jeu prend vie** — caméra qui suit le joueur, transitions en fondu entre scènes, pentes, rotation et échelle des sprites, plus une palette d'effets de *game feel* (squash, flash, secousse…).
- **v0.7** ✅ : **Données de jeu** — tableaux et tables de données éditables dans l'éditeur, qui débloquent RPG, tactique et gestion.
- **v0.8** ✅ : **Son complet** — musique par scène, transitions fidèles au matériel, effets sonores réglables (volume, hauteur, panning), et import des formats de tracker courants (`.mod`, `.xm`, `.s3m`, `.it`).
- **v0.9** ✅ : **Jeux multilingues** — écrivez votre jeu en plusieurs langues, le joueur choisit la sienne en jeu, et rien ne disparaît à l'écran grâce à une police de repli.
- **v0.10** : **Windows et Linux** — l'éditeur disponible sur les deux systèmes.
- **v0.11** : **Éditeur traduit** — l'interface de l'éditeur elle-même en plusieurs langues.
- **v0.12** : **Vue d'ensemble** — un plan du jeu qui montre scènes et transitions d'un seul coup d'œil.
- **v0.13** : **Édition mixte code / blocs** — programmez au clic *ou* au clavier, sur un même script.
- **v0.14** ✅ : **Outils de débogage** — journal en direct, mesure des performances sur la cible, le tout retiré automatiquement de la version livrée.
- **v0.15** ✅ : **Interface qui se montre et se cache** — panneaux, textes et images affichables ou masquables à volonté, à l'authoring comme au script.
- **v0.16** : **Scripting simplifié** — une bibliothèque de scripting rangée par ce que vous voulez faire, plus par le matériel.
- **v0.17** : **Scènes plus légères** — chaque scène ne consomme que les ressources qu'elle utilise vraiment.
- **v0.18** : **Affichage dynamique** — montrez n'importe quelle valeur à l'écran (PV, score, timer) sans détour.
- **v0.19** ✅ : **Mouvement fluide** — accélération, sauts à hauteur variable et reculs réglés au sous-pixel près, pour un contrôle qui répond.
- **v0.20** ✅ : **Grandes sauvegardes** — des centaines d'états de jeu (coffres, quêtes, interrupteurs) tenus en quelques octets.
- **v0.21** ✅ : **Dialogues dynamiques** — parcourez une conversation entière au script, toujours traduisible.
- **v0.22** ✅ : **Menus et listes** — des menus navigables au curseur prêts à l'emploi, et des sauvegardes lisibles avant même de charger la partie.
- **v0.23** ✅ : **Combats et boss** — attentes scriptées, boss articulés en plusieurs parties, et collisions optimisées entre types d'entités.
- **v0.24** (en cours) : **Prêt pour le travail en équipe** — des fichiers de projet lisibles par git et des builds incrémentaux nettement plus rapides.
- **v0.25** ✅ : **Interface ancrée** — un HUD fixé à l'écran, une bulle qui suit un personnage : chaque élément d'interface choisit sa cible.
- **v0.27** ✅ : **Autocomplétion intelligente** — l'éditeur suggère en écrivant exactement ce que le langage accepte, jamais une fonction qui n'existe pas.

## Les versions suivantes exploreront des fonctionnalités plus avancées de la Game Boy Advance :

Fonctionnalités envisagées :

- Backgrounds affines ("Mode 7"), rotation et zoom des couches de fond.
- Physique et collision : gravité, milieux (air, viscosité), collision par normale, formes
  cercle et maillage, import d'une carte de collision depuis une image.
- Distorsion d'image par ligne (eau, chaleur, vitesse).
- Rendu isométrique : projection en losange et tri en profondeur des sprites.
- Un **second moteur de rendu**, en 3D logicielle sur framebuffer (modes bitmap), à côté du
  moteur 2D actuel — avec pour objectif qu'un jeu du niveau de V-Rally 3 soit constructible
  avec l'éditeur.
- Support du câble Link (multijoueur)
- Nouveaux outils d'édition
- Optimisations du runtime

---

## Licence

### Votre jeu vous appartient

**Sans réserve.** Vos images, vos sons, vos scripts, vos scènes et la ROM que
vous en tirez sont votre travail : les avoir produits avec cet éditeur ne donne
à personne le moindre droit dessus.

- **Vendez-le** où vous voulez, sans nous demander, sans rien reverser.
- **Ne publiez pas vos sources** si vous ne le souhaitez pas.
- **Ne joignez aucune notice** à votre ROM.

Le moteur recopié dans votre projet au moment du build est sous licence **zlib**
([runtime/LICENSE](runtime/LICENSE)), justement pour que rien de tout ça ne soit
à négocier.

> Une réserve qui ne vient pas de nous : votre ROM est liée à `libgba` et
> `maxmod` (devkitPro). Elles sont permissives et compatibles avec un jeu
> commercial, mais leurs termes sont à lire chez devkitPro.

### L'éditeur

GBA Editor est un **logiciel libre**, sous [GPL-3.0-only](LICENSE). Vous pouvez
l'utiliser, l'étudier, le modifier et le redistribuer. En contrepartie, toute
version modifiée que vous distribuez doit rester libre, sous la même licence, et
créditer les auteurs d'origine.

Le téléchargement depuis GitHub est et restera gratuit. Les versions vendues sur
d'autres plateformes sont les mêmes : ce qui s'y achète, c'est la commodité et
le soutien au développement, jamais un supplément de fonctionnalités.

Les composants tiers embarqués et leurs licences sont listés dans
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

---

## Crédits

Musiques du projet de démo par **Tiptoptom Cat** — [itch.io](https://tiptoptomcat.itch.io/).

### Palettes de couleurs

Merci à leurs créateurs :

| Palette | Auteur |
| --- | --- |
| Miyazaki 16 | skeddles |
| NA16 | Nauris |
| PICO-8 | Lexaloffle Games |
| Soft 16 | Endesga |
| Mystic 16 | polyphrog |
| Colorquest 16 | polyphrog |

Beaucoup de ces palettes sont partagées par leurs auteurs sur
[Lospec](https://lospec.com/palette-list); elles restent la propriété de
leurs créateurs.

Musiques du projet de démo par **Tiptoptom Cat** — [itch.io](https://tiptoptomcat.itch.io/).
