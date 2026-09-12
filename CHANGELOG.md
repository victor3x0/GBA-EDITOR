# Changelog

Une entrée courte par version **livrée**, dans l'ordre numérique des versions (une version
reste une identité, pas un rang — voir [ROADMAP.md](ROADMAP.md)). Pour le détail complet
d'une version (décisions verrouillées, pièges rencontrés, mesures), voir
[changelog-archive/](changelog-archive/). Pour ce qui reste à faire, voir [ROADMAP.md](ROADMAP.md).

## v0.2 — Gestion des palettes de couleurs

Catalogue de palettes nommées, illimité, partagé par tout le projet, avec un écran dédié
(roue chromatique, rampes, import PNG et `.gpl`). Import non destructif, encodage des fonds
(tuiles, dédup, jusqu'à 16 sous-palettes par image), palette par calque de fond, inpainting
(repeindre la palette d'une tuile 8×8 sans toucher l'image d'origine).

→ [détail](changelog-archive/v0.2.md)

## v0.3 — Background vivant, texte et interface in-game

Le décor devient pilotable depuis un script (calques, fenêtres, mélange de couleurs). Un
projet peut afficher du texte dans ses propres polices et dessiner son interface au canvas,
avec une table de textes balisée. Interface en sprite pour les cas qui ne tiennent pas sur
un fond.

→ [détail](changelog-archive/v0.3.md)

## v0.4 — Animation de décor

Fonds animés jusqu'en ROM (une tuile de décor qui bouge, un animé posé sur un hôte), et
couleurs d'une scène pilotables au script (palettes au runtime). Pas d'éditeur de carte ni
de peinture de tuiles — hors périmètre assumé, ce logiciel n'est pas un outil de dessin.

→ [détail](changelog-archive/v0.4.md)

## v0.5 — Sauvegarde (SRAM)

Une variable globale peut être marquée persistante ; un script écrit ou relit l'ensemble de
ces variables dans un emplacement de sauvegarde. Format tolérant à l'évolution du jeu (id
opaque par variable, pas de rang).

→ [détail](changelog-archive/v0.5.md)

## v0.6 — Polish de la boucle de jeu

Caméra devenue un asset réutilisable (suivi, bornes, secousse, script). Transitions de scène
en fondu, réglées au projet et surchargeables par scène. Pentes résolues au runtime (26°,
45°, 63°, sols et plafonds). Rotation et échelle des sprites (transform monde × local) avec
des raccourcis de game feel (squash, flash, shake…).

→ [détail](changelog-archive/v0.6.md)

## v0.7 — Structures de données

Tableaux typés dans les scripts et tables de données authorées, cuites en `const` dans la
ROM. `vec2`/`vec3` dans le langage. Les propriétés : l'état s'écrit comme un champ. L'état
d'un prefab poolé. Les séquences, pour écrire une attente en ligne droite. Et le sous-ensemble
Lua enfin dit et tenu ([SCRIPTING.md](SCRIPTING.md)) : ce qui n'est pas traduit est refusé sur
sa ligne, plus jamais ignoré en silence.

→ [détail](changelog-archive/v0.7.md)

## v0.8 — Son : la musique par scène, les transitions, le mixage

Musique portée par la scène, deux transitions fidèles au matériel (fondu traversant, coupe à
la position). Écran de mixage à boîtes d'état (musique/jingle/effets). Référence d'effet avec
réglages à l'appel. Import des quatre formats que maxmod sait jouer (`.mod`, `.xm`, `.s3m`,
`.it`) — et 96 % de musique morte retirée de la ROM par filtrage réel.

→ [détail](changelog-archive/v0.8.md)

## v0.9 — Traduction des jeux créés avec l'éditeur

L'écran Texte devient une table de travail plate (rangement en trois colonnes, statut
traduit/manquant, atelier en onglets par langue) puis gagne les langues elles-mêmes : side
par langue joint par id, remap de police, sous-ensemble de glyphes par (scène, langue), et
`lang.set`/`lang.get` pour changer de langue en jeu (rechargement de la scène active). Une
**police par défaut** du projet (« Default Font ») sert à la fois de police de scène par défaut
et de repli de couverture, surchargeable par scène : un caractère absent de la police active —
un mot resté dans la langue source sous une écriture qui n'a pas ses lettres — se rend depuis
elle plutôt que de disparaître. Garde-fous silencieux, même en projet monolingue : VRAM au pire
cas, littéraux non traduits, caractère qu'aucune police (ni l'active ni le repli) ne porte.

→ [détail](changelog-archive/v0.9.md)

## v0.14 — Diagnostic — ce que le jeu fait, et ce qu'il coûte

*Livrée le 2026-08-20.* `debug.log`, le toggle Debug/Release du projet, et le budget frame +
OAM par le journal mGBA. Réduite au périmètre réellement mesurable (canaux/DMA non
mesurables).

→ [détail](changelog-archive/v0.14.md)

## v0.15 — Visibilité des éléments d'interface

Texte, panneau et image peuvent se cacher/montrer, au script comme à l'authoring, et un
panneau caché cache tout son sous-arbre — livrée conforme sur le modèle et le runtime, sous
une autre forme côté Lua que celle prévue (`ui.get("nom"):show()` plutôt que `ui.show`).

→ [détail](changelog-archive/v0.15.md)

## v0.19 — Le sous-pixel

*Livrée le 2026-08-20.* Position et vitesse en point fixe (Q8) : une accélération, un saut à
hauteur variable et un recul qui ne se règlent pas par pixel entier. `self.velocity` change
d'unité, `self:apply_velocity()` accumule sans perte de fraction à travers la collision.

→ [détail](changelog-archive/v0.19.md)

## v0.20 — L'état du monde : les collections persistantes

*Livrée le 2026-08-20.* Une variable globale peut avoir plusieurs cases
(`global.coffres[i]`), sauvegardables d'un bloc et empaquetées en SRAM (400 booléens tiennent
en 60 octets, pas 1 600).

→ [détail](changelog-archive/v0.20.md)

## v0.21 — Le texte adressable : le dialogue piloté par la donnée

*Livrée le 2026-08-21.* Un id de texte peut être une valeur (`text.draw(2, 16,
data.Dialogues[i].replique)`), pas seulement une clé écrite à la main : un script parcourt
une conversation au lieu d'être déroulé réplique par réplique, et le dialogue reste
traduisible.

→ [détail](changelog-archive/v0.21.md)

## v0.22 — Menus, listes et curseur

*Livrée le 2026-09-05.* Le moteur prend la navigation, la mise en page reste authorée. `UIList`
devient un quatrième type d'élément (à côté de texte, conteneur et image) : il porte son index,
ses bornes, une grille (`nav_columns`/`nav_major`) et son curseur, qui se POSE sur la rangée
choisie ou y GLISSE. Un `active` par liste permet un menu et son sous-menu à l'écran en même
temps. `ui.image_move` déplace une image d'interface au script (le curseur qu'on pilote
soi-même), `list.active`/`list.set_active` bascule la sélection. L'en-tête de sauvegarde s'étend
sans nouveau concept : `save.read(slot, "nom")` lit une variable d'un emplacement sans charger la
partie, et l'ancien `save.read(slot)` — qui remplace TOUTES les persistantes — devient
`save.load(slot)`. Au passage, `UIPanel` devient `UIContainer`, jusqu'à la valeur sérialisée.

→ [détail](changelog-archive/v0.22.md)

## v0.23 — Ce qu'un boss demande

*Livrée le 2026-08-21.* Boucle bornée dans une séquence (`for i = 1, 3 do tirer() ;
wait(20) end`), hiérarchie d'acteurs (un boss segmenté se déplace d'un bloc, chaque enfant
gardant son sprite et ses collisions), et une matrice de collision entre tags qui retire du
build les paires qui ne se rencontrent jamais.

→ [détail](changelog-archive/v0.23.md)

## v0.25 — L'interface possède son chemin matériel

*Livrée le 2026-09-03.* Un nœud « Interface » se pose dans l'arbre de scène (comme un
acteur) et porte, à un seul endroit, l'ancrage (écran / monde / acteur) et la cible matérielle
(BG ou sprite) de tout son contenu ; ses textes et images en héritent. Une scène peut en poser
plusieurs — un HUD fixe en fond, une bulle qui suit un acteur en sprite — chacun son chemin. Un
inspecteur dédié affiche le réglage et sa raison quand le matériel l'impose.

→ [détail](changelog-archive/v0.25.md)

## v0.26 — Les polices : sources, assets et aperçu

*Livrée le 2026-09-12.* Les sources PNG, BMFont, TTF et OTF sont séparées des Font Assets
logiques du projet. Une source découverte crée son asset immédiatement ; les familles
vectorielles réunissent automatiquement leurs faces natives. Le rasterizer FreeType produit le
même aperçu pour l'inspecteur et le canvas, avec politique pixel-fit éditable (strikes bitmap,
alignement sur grille ou rendu natif) et sélection de poids/italique natifs.

La police par défaut peut être remplacée par langue (Latin → Misaki pour le japonais) sans
perdre la banque d'encre choisie dans la scène. Le build, le canvas et le runtime suivent la
police effectivement rendue : une police composée reçoit sa surface VRAM propre par zone, ce qui
évite les glyphes tronqués ; le choix de palette est persisté dans la scène et réapparaît après
réouverture.

→ [détail](changelog-archive/v0.26.md)

## v0.27 — L'éditeur souffle le mot juste

*Livrée le 2026-09-07.* Autocomplétion du Script Editor : en tapant `self:`, `sfx.` ou
`camera.`, une liste des suites s'ouvre sous le curseur, avec la même infobulle que la sidebar.
Elle **dérive du catalogue** — membres et modules, handlers, enum matériels, `local`/paramètres
en portée, et noms du projet dans les arguments chaîne (`sfx.play("` → les effets) — donc elle
propose exactement ce que le checker accepte, jamais une fonction morte. `Tab` accepte, `Entrée`
insère une ligne, `Échap` ferme, `↑`/`↓` naviguent, `Ctrl+Espace` ouvre à la demande. En chemin,
un correctif du moteur : un `local a, b, c` en corps de handler déclare enfin ses trois noms.

→ [détail](changelog-archive/v0.27.md)
