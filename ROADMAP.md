
# Roadmap détaillée

Ce document explique **le pourquoi** derrière chaque jalon : ce que la version résout, les
choix qui sont tranchés, et les questions volontairement laissées ouvertes.

Trois documents, trois rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| **ce fichier** | qui décide de la suite | scope, décisions, questions ouvertes |
| [ARCHITECTURE](ARCHITECTURE.md) | qui modifie le code | comment c'est construit |

Convention : **Décisions verrouillées** = tranché, à implémenter tel quel — on ne rouvre
pas sans raison neuve. **Ouvert** = identifié mais volontairement non tranché : à rouvrir
quand le chantier démarre réellement, le contexte du moment valant mieux que des
suppositions faites à l'avance.

---

## Où on en est

| Version | Sujet | État |
| --- | --- | --- |
| v0.2 | Palettes de couleurs | **Livrée**, quelques finitions |
| v0.3 | Background vivant, texte et interface | **Livrée**, un report assumé |
| v0.4 | Animation de décor | **Livrée** |
| v0.5 | Sauvegarde | Non commencée |
| v0.6 | Polish de la boucle de jeu | Non commencée |
| v0.7 | Son enrichi | Non commencée |
| v0.8 | Traduction des jeux | Non commencée |
| v0.9 | Distribution Linux | Non commencée |
| v0.10 | Traduction de l'éditeur | Non commencée |

---

## v0.2 — Gestion des palettes de couleurs

Au départ, un acteur portait un simple numéro de banque de palette, tapé à la main, sans
aucune vue sur ce que contenaient les autres banques ni détection de conflit. Chaque image
recevait par ailleurs une palette « optimale » calculée indépendamment, sans garantie que
deux sprites rangés dans la même banque soient compatibles.

### Ce que ça donne

Un **catalogue de palettes nommées**, illimité, partagé par tout le projet, avec un écran
dédié pour les construire (roue chromatique, rampes, import PNG et `.gpl`). Chaque scène y
pioche les palettes qu'elle veut activer. Partout où l'on choisissait un numéro, on choisit
maintenant une palette dans une liste avec ses couleurs affichées.

Sont venus dans la foulée : l'**import non destructif** (une image déposée est analysée et
encodée à côté, jamais réécrite), l'**encodage des fonds** (découpe en tuiles, déduplication,
jusqu'à 16 sous-palettes par image), une **palette par calque de fond**, et l'**inpainting** —
repeindre la palette d'une tuile 8×8 au pinceau, sans toucher à l'image d'origine.

### Décisions verrouillées

- **Deux pools séparés, fidèles au matériel** : la mémoire de palette des sprites et celle
  des fonds sont physiquement distinctes sur GBA — 16 banques de 16 couleurs chacune. Cette
  séparation vit dans la **sélection de la scène**, pas dans le catalogue.
- **Le catalogue, lui, est unifié** (révision du plan initial « 16 banques fixes par pool »,
  sur le modèle GB Studio) : une palette n'est que 16 couleurs, rien n'empêche la même
  définition de servir aux sprites et aux fonds. Chaque scène choisit jusqu'à 16 palettes
  actives par pool, et c'est **cette sélection** qui occupe réellement le matériel.
- **Import depuis un PNG ou un export Aseprite standard** — pas de lecture du format
  `.aseprite` natif : trop de travail pour la valeur ajoutée, et fragile aux évolutions du
  format.
- **Deux cascades de surcharge, sans influence croisée.** Côté décor, une scène peut
  surcharger la palette de chacun de ses calques ; côté sprites, un acteur peut surcharger
  d'un coup tous ses sprites. La scène n'a aucune prise sur les sprites, et l'acteur aucune
  sur le décor. Usage : l'une donne un thème de couleurs cohérent à tout un décor, l'autre
  recolore une instance précise sans toucher aux autres.
- **Aucune banque réservée** : les 16 sont toutes utilisables et éditables.
- **Coupe assumée** : les couleurs d'un sprite sont calculées une fois pour tout le projet.
  Si deux scènes le rangent dans des palettes différentes, l'une gagne et le validateur
  avertit. Générer une variante par scène est un chantier de pipeline à part.
- **Un prefab choisit sa palette comme un acteur**, relativement à la scène — bien qu'un
  prefab instancié à la volée n'ait pas de scène propriétaire unique. Le validateur signale
  les cas où deux scènes lui résolvent des couleurs différentes ; c'est un avertissement, pas
  un blocage, parce que le remplacement de palette par emplacement est un usage légitime.

### Écarté (2026-07-07) — le réservoir d'import automatique

Le plan initial réservait quelques banques par pool à un remplissage automatique, les
couleurs des images non palettisées y atterrissant toutes seules. Abandonné **avant
implémentation**, sur deux problèmes de conception :

- **Dégradation silencieuse** — le réservoir sature vite, et au-delà les couleurs dérivent
  vers l'approximation la plus proche sans un mot. « Pourquoi mon sprite a changé de couleur
  quand j'en ai ajouté un autre ? »
- **Non-déterminisme** — quelle couleur atterrit où dépend de l'ordre de traitement au build,
  qui n'est pas garanti stable. Même projet, même images, rendu potentiellement différent.

À rouvrir seulement avec un débordement **visible** au build et un ordre de traitement
déterministe.

### Reste à faire

- **Support ROM du mode bitmap** — les fonds bitmap sont éditables et encodés, mais ignorés
  au build. C'est la principale finition côté runtime.
- **Vrai 16 bits** — un import 16 bits retombe aujourd'hui sur un repli en mode 4.
- **Aperçu contextuel** dans l'écran Palette.
- Le calcul de « couleur la plus proche » est une distance euclidienne simple, sans
  justification perceptuelle.

---

## v0.3 — Background vivant, texte et interface in-game

### v0.3.1 — Rendre le décor pilotable

Le système de fond était pensé pour du décor pré-cuit : rien ne permettait de changer une
tuile, de masquer un calque ou de toucher à l'affichage pendant le jeu. Le scroll et le
parallaxe, eux, fonctionnaient déjà.

Le texte est un **cas particulier de la primitive manquante** : afficher du texte sur un
fond, c'est écrire des index de tuiles dans une carte, image par image. Cette fondation sert
donc à la fois le texte (v0.3.2) et, plus tard, les fonds animés de la v0.4 — les deux
chantiers ne se recouvrent pas.

#### Ce que ça donne

Le décor devient pilotable depuis un script : afficher ou masquer un calque, changer son
ordre de profondeur, le décaler indépendamment de la caméra, réécrire ses tuiles une à une.
Plus les **fenêtres** (découper l'écran en régions) et le **mélange de couleurs**
(transparence, fondu au blanc ou au noir), disponibles au script comme à l'authoring.

#### Décisions verrouillées

- **Les fenêtres sont exposées brutes.** On garde le mot « window » du GBA ; c'est à la
  documentation d'expliquer le concept. Les deux rectangles matériels sont exposés tels
  quels, **sans allocateur** : l'utilisateur gère la pénurie, un allocateur qui réattribue
  en douce rendrait les bugs incompréhensibles. La fenêtre-objet est incluse — c'est elle
  qui donne les formes libres.
- **Le mélange n'a qu'un mode pour tout l'écran**, mais deux listes de cibles. C'est le
  matériel ; proposer un mode par calque serait mentir. À ne pas reproposer.
- **Un champ « mode vidéo » sur la scène** dès maintenant, resté à sa valeur par défaut et
  caché tant qu'aucun autre mode n'existe : ça évite une migration des fichiers de scène le
  jour où le Mode 7 (v2.0) et les modes bitmap (v3.0) arrivent.

#### Hors périmètre

Mosaïque et effets par ligne de balayage (qui demanderaient une infrastructure d'interruption
horizontale). Aucun n'était bloquant pour la suite.

---

### v0.3.2 — Texte et interface

#### Ce que ça donne

Un projet peut afficher du texte dans ses propres polices, et dessiner son interface au
canvas plutôt qu'en la codant.

- **Polices importées** depuis une planche PNG ou un descripteur BMFont, avec un jeu de
  caractères corrigeable et des chasses déclarées.
- **Table de textes** au niveau projet : chaque texte a une clé, il est rangé dans un arbre,
  et il est traduisible — c'est ce qui rend la v0.8 possible sans tout refactorer.
- **Balisage** dans le contenu : pauses, vitesse de défilement, ondulation, couleur, et
  insertion de valeurs (`$score`). Tout est résolu à la compilation, le moteur n'embarque
  aucun analyseur.
- **Interface authorée** : des éléments de texte, des conteneurs (qui peuvent porter un fond)
  et des images, organisés en arbre dans l'éditeur de scène, positionnables à la souris.
- Le rendu du texte prend automatiquement le chemin le moins cher — index de tuiles pour une
  police à chasse fixe, composition pixel par pixel pour une police proportionnelle ou trop
  grosse pour tenir en mémoire vidéo. C'est ce qui rend une police CJK possible.

#### La neutralité de style — règle de conception à tenir

Objectif explicite : **couvrir tous les besoins sans induire un style graphique**. La fenêtre
matérielle est le bon socle précisément parce qu'elle ne dessine rien : elle dit *où*, jamais
*à quoi ça ressemble*. Trois garde-fous, valables dans la durée :

1. **Aucun habillage par défaut.** Si l'on livre des exemples, on en livre plusieurs
   visuellement opposés — cadre pixel-art épais, bandeau plein sans bordure, texte nu sur
   fond estompé — et dans le projet de démo, jamais dans le moteur. Un seul exemple *est* un
   défaut, quoi qu'en dise la documentation.
2. **Le nine-slice est un outil, pas un look.** Proposer un panneau étirable est légitime ;
   en faire le seul chemin ne l'est pas. Panneau en sprites, panneau plein écran ou pas de
   panneau du tout doivent rester aussi simples.
3. **Aucune position par défaut**, et **vocabulaire de moteur** dans l'API : région, calque,
   carte de tuiles — jamais « dialogue », « message » ou « boîte de texte ». Un nom de
   fonction est une suggestion de design.

Même principe côté polices : **pas de police par défaut, mais jamais de cul-de-sac** — une
étagère de départ de trois polices visuellement opposées, présentées comme des exemples à
modifier. Le pluriel est ce qui fait la différence entre un exemple et un défaut.

#### Décisions verrouillées — le stockage du texte

Le point de départ n'est pas l'affichage mais **où le texte est rangé**, parce que la v0.8
exige qu'il soit référencé par clé dès maintenant. Principe directeur : **séparer le stockage
de la saisie**. Les confondre donne soit des clés à taper partout, soit du texte enterré dans
les scripts.

- **Une table au niveau projet**, entrée du graphe de dépendances, compilée en table indexée.
- **L'utilisateur ne tape jamais une clé.** Trois portes, une seule table : le champ dans
  l'inspecteur, l'écran Textes, et l'appel de script avec autocomplétion.
- **La clé situe, elle ne résume pas** : dérivée du contexte de création, jamais du contenu —
  sinon elle ment dès que le garde devient un mendiant. Le sens arrive par renommage manuel
  quand un texte le mérite.
- **La table reste plate — pas d'éditeur de dialogue.** Ni arbre de conversation, ni
  portraits, ni choix branchés : un éditeur de dialogue *est* une décision de genre. Le
  séquencement reste du script, écrit une fois dans un comportement réutilisable — c'est ça
  qui tue la redondance, pas la table.
- **Un type de donnée « texte » distinct de « chaîne »** : le premier est destiné au joueur
  et traduisible, le second est technique et reste dans le script. Un mot posé maintenant
  évite un tri manuel en v0.8.

#### Décisions verrouillées — l'API d'écriture

Forme **définitive**, décidée avant d'ouvrir le chantier du balisage pour ne pas figer des
signatures deux fois.

- **Deux fonctions pour écrire, pas plus** : écrire à une position, ou écrire dans une zone.
  Grammaire *position ou conteneur → contenu*, tenue dans les deux. Tout le reste est du
  paramétrage, déclaré avant ou porté par les balises.
- **L'écriture à une position accepte un littéral** autant qu'une clé — c'est le seul accès
  rapide qui ne passe pas par l'interface, au prix assumé de la traduction. À la compilation,
  un littéral devient une entrée anonyme : le moteur ne connaît qu'un chemin.
- **Le tempo s'écrit dans le texte, par l'auteur.** Ça ne contredit pas le refus d'un réglage
  global de « vitesse du texte », qui imposerait un genre à tous les textes : une pause posée
  à un endroit précis est de l'écriture, au même titre qu'une virgule.
- **Syntaxe à la BBCode**, sur le modèle de Godot. Trois raisons : elle est **fermée** (sans
  borne de fin, `/S12` serait indécidable) ; les crochets n'apparaissent pas en prose là où
  `/` le fait (« et/ou », « 12/05 ») ; et elle a des **balises de portée**, ce dont un effet
  par caractère a besoin. Précédent connu de beaucoup de gens, donc rien à apprendre.
- **Un crochet en prose n'est pas une faute.** Une balise inconnue reste du texte, et n'est
  signalée que si sa forme trahit une tentative — nom voisin d'une balise connue, casse
  fautive, valeur portée. « Touche [A] » s'écrit sans rien échapper.
- **L'interpolation vit dans l'entrée, pas au site d'appel** : `"score : $score_player"`.
  Donc pas d'arguments variables, donc une signature qui ne peut plus grandir. **Porte fermée
  assumée** : pas de valeur calculée, une expression passe par un global intermédiaire. Un
  score *est* un global dans la quasi-totalité des cas ; l'échange se fait contre une
  signature définitive.
- **Résolution à la compilation, aucun analyseur au runtime.**
- **L'écriture à une position ne gagnera jamais largeur, alignement ni police en argument.**
  Chacun ramènerait de la géométrie dans le script, invisible à l'éditeur et incalculable
  avant le build. La réponse à ces trois besoins est « dessine une zone », et c'est la bonne
  pédagogie.
- **Pas de retour à la ligne automatique** hors d'une zone — comportement attendu d'un
  `print`. Le débordement est **coupé franc** au bord, pour être visible et inoffensif au
  lieu d'aller écrire ailleurs.

#### Décisions verrouillées — les polices

- **Un glyphe = une tuile.** Bénéfice caché du choix : le glyphe hérite gratuitement de tout
  ce qui s'applique à une tuile — recoloration, découpe par une fenêtre, ordre de
  profondeur — sans une ligne de code spécifique au texte.
- **Deux points d'entrée, pas plus** : planche PNG ou descripteur BMFont. TTF/OTF écarté
  (rastérisation imprécise, choix de taille pénible) alors que le corpus de polices pixel
  d'itch.io est déjà énorme et vient en PNG.
- **Jeu de caractères explicite et corrigeable**, jamais un « ASCII 32-126 » figé : c'est ce
  qui permet les accents, les icônes de boutons et n'importe quel symbole. La neutralité de
  style appliquée aux polices — on ne présuppose pas un alphabet.
- **Pas d'éditeur de glyphes** : on dessine dans son outil habituel, comme pour les sprites.
  Et pas d'assistant d'import en plusieurs étapes — le dépôt du fichier suffit.
- **La chasse est déclarée, jamais devinée.** Trois sources par ordre d'autorité : le
  descripteur, sinon un marqueur de couleur qui dit où finit le caractère, sinon la chasse
  fixe. Pas de repli sur une mesure de l'encre : sans flanc déclaré, une chasse
  proportionnelle colle les lettres et donne un texte à rattraper case par case, là où de la
  chasse fixe est toujours lisible.

#### Reste à faire

Le **type de donnée « texte » branché sur l'inspecteur**. C'est le dernier trou de la v0.3 et
il est reporté sciemment : les valeurs par instance d'un script ne sont lues par aucun
générateur aujourd'hui, donc un menu de clés dans l'inspecteur serait une fausse
fonctionnalité. Et le câblage touche exactement le lien entre variables globales et scripts
qu'un chantier à venir doit refaire — le faire maintenant obligerait à le refaire après.

#### Ouvert

- Le calque unique réservé à l'interface suffit-il, maintenant que panneaux, texte et polices
  cohabitent dessus, ou faut-il pouvoir en réserver plusieurs ?
- Une dizaine de méthodes d'acteur sont regroupées dans une catégorie fourre-tout de la
  documentation intégrée, à ranger à la main.

Tranchés depuis : l'effet machine à écrire (remplacé par les balises), le retour à la ligne
automatique (dans une zone oui, ailleurs non), la chasse proportionnelle, l'import de planche
sans éditeur de police, et l'indexation des polices par scène.

---

### v0.3.3 — Interface en sprite

#### Ce que ça donne

Un acteur peut être **ancré à l'écran** plutôt qu'au monde : il ne défile plus avec la
caméra, et ses coordonnées deviennent des pixels d'écran. C'est l'interface qui a besoin de
logique — un curseur de menu, une jauge qui réagit — avec tout le système de sprites habituel
(états, animations, éditeur de sprite).

Le périmètre a rétréci en cours de route : le widget **image** de la v0.3.2 couvre déjà
l'illustration d'interface. Ce qui restait, c'est l'**acteur de jeu** ancré à l'écran, celui
qui porte un script et des composants.

#### Décisions verrouillées

- **Résolu à la compilation**, pas au runtime : un acteur est de l'interface ou du monde pour
  toute sa vie. Le cas par défaut doit rester littéralement gratuit.
- **L'ordre d'affichage face à l'interface de fond, c'est le matériel qui répond** — aucun
  concept nouveau. La priorité de l'acteur se compare à celle du calque d'interface, et à
  égalité le sprite passe devant. Les deux ordres sont des choix légitimes ; inventer une
  règle implicite par-dessus rendrait le résultat imprévisible.

---

## v0.4 — Animation de décor

Le jalon s'appelait « Éditeur de background & animation de tuiles » et devait livrer un
éditeur de carte : composer un décor en posant des tuiles importées. **Ce périmètre est
retiré**, pas reporté — voir « Ce que la v0.4 ne fera pas » plus bas. Restait le décor qui
bouge : les fonds animés jusqu'en ROM, puis les couleurs d'une scène pilotables au script. Les
deux sont livrés.

### Ce qui est déjà là, par ricochet de la v0.2 et de la v0.3

L'écran Background Editor existe dans sa dimension **couleur** : importer une image, laisser
l'éditeur détecter son mode et l'encoder, repeindre la palette tuile par tuile.

S'y est ajoutée la notion de **sorte de fond** — décor, interface, animé — portée par un
champ sur l'asset plutôt que par trois types distincts : les trois partagent tout le pipeline
d'import, d'encodage et de palettes, et trois classes auraient triplé ça pour un champ de
différence. Le cadre nine-slice n'est donc plus un asset séparé, c'est un fond marqué
« interface ».

Côté animé, l'authoring était livré avant ce jalon — découpe de la planche en grille, vitesse
en ticks, dépôt d'un animé sur un fond hôte, joué sur place au canvas — mais rien n'en sortait
en ROM. C'est ce que la v0.4.1 est venue fermer.

### Ce que la v0.4 ne fera pas

**Pas de peinture de tuiles, pas d'éditeur de carte, pas de tileset importé.** Ce logiciel
n'est pas un outil de pixel art ni de dessin — d'excellents outils existent déjà pour ça, et
l'import non destructif est fait pour les accueillir. La seule part de « dessin » assumée est
le glisser-déposer d'assets animés sur un fond qui existe déjà.

Tombent avec ce périmètre : le tileset comme asset de premier rang, et l'indicateur de budget
mémoire vidéo dans l'éditeur (il n'avait de raison d'être que si plusieurs tilesets pouvaient
coexister par la volonté de l'utilisateur).

Le **calque d'interface réutilisable** entre scènes sort aussi de la v0.4 — mais par absence
d'usage démontré, pas par décision. Partager un calque d'interface reste un problème de
référencement et d'allocation, indépendant de l'authoring qui vient de disparaître ; la
question tiendra donc toujours le jour où un projet réel réclamera le même HUD dans douze
scènes. Elle n'est pas tranchée, elle attend son cas.

### v0.4.1 — Fonds animés en ROM — **LIVRÉE**

C'est aussi là que se joue l'« animation de tuiles » du titre d'origine : animer une tuile de
décor et jouer un fond animé posé sur un hôte, ce sont deux formulations du même mécanisme.

#### Décisions verrouillées

- **Le placement vit chez l'hôte, la nature de l'animation vit chez l'animé.** Une cascade
  dessinée une fois se pose dans trois décors ; stocker les positions dans l'animé obligerait
  à y citer les fonds qui l'emploient, c'est-à-dire à inverser le sens de la référence.
  Symétriquement, découpe, vitesse, boucle et mode d'animation appartiennent à l'asset : une
  cascade est une cascade partout où on la pose.
- **Deux modes d'animation exposés à l'auteur**, `shared` et `instance`, portés par
  `BackgroundAsset.animation_mode` :
  - `instance` — chaque copie posée a sa propre animation. Techniquement, on réécrit les
    index de la carte ; toutes les images restent résidentes en mémoire vidéo.
  - `shared` — toutes les copies bougent ensemble. Techniquement, on réécrit les pixels de la
    tuile ; une seule image est résidente, et toute case qui l'utilise change avec elle.
- **Nommés par leur effet observable, pas par leur cas d'usage.** « Cascade » et « objet
  unique » sont des exemples, et un libellé qui est un exemple laisse l'auteur chercher lequel
  des deux ressemble le plus à son tapis d'herbe. « Toutes les copies ensemble » contre
  « chacune la sienne » est une différence de comportement, dicible sans expliquer le
  matériel.
- **`instance` par défaut.** C'est l'attente naturelle quand on pose un objet à une position
  précise. `shared` demande en plus de *désactiver* la déduplication — une case dont on réécrit
  les pixels ne peut pas partager sa tuile avec une autre, ce serait faire changer sa voisine
  en même temps.
- **Le débordement mémoire bloque le build et nomme l'autre mode.** C'est `instance` qui peut
  déborder — un fond plein écran sur quatre images demanderait plus de tuiles que l'index de
  carte ne peut en adresser. Le garde-fou dit un choix *impossible* et son issue ; il
  n'explique pas le matériel. Effet de bord : aucun fond compressé n'avait jusque-là de
  contrôle de budget bloquant, seul le chemin grit en avait un. Le trou est fermé.

#### L'animé se pose SUR le décor, il ne le remplace pas

Première version livrée : un placement écrasait la tuile de son hôte. Une case de tilemap ne
portant qu'une tuile, la transparence de l'animé perçait alors jusqu'au fond d'écran — un
arbre posé devant un mur trouait le mur sur tout son rectangle englobant. Correct côté
matériel, absurde côté auteur.

Le build **fusionne** désormais : pixel de l'animé là où il peint, pixel du décor là où il est
transparent, transparence seulement là où les deux se taisent. Un arbre laisse voir le mur
derrière lui ; un arbre posé sur un trou du décor laisse toujours passer le calque du dessous.
La règle se dit sans parler du matériel, et c'est ce qu'on attend en regardant le canvas.

- **La sous-palette est SYNTHÉTISÉE.** L'hôte et l'animé ont chacun la leur, une tuile fusionnée
  pioche dans les deux : elle ne peut être ni l'une ni l'autre. Le build en fabrique une, allouée
  comme n'importe quelle banque et dédupliquée par contenu.
- **Au-delà de 15 couleurs, le build BLOQUE** en nommant le placement et sa position. Approximer
  les couleurs du décor vers la palette de l'animé marcherait toujours et les ferait dériver sans
  un mot : c'est exactement la dégradation silencieuse écartée en v0.2. Sur le cas de référence,
  la fusion demande 6 couleurs sur 15 — la marge est confortable.
- **Les tuiles dépendent de ce qu'il y a dessous.** Deux copies ne partagent leur bloc que si le
  décor sous elles est identique. La déduplication le rattrape sans qu'on ait à le dire, mais
  une forêt sur un décor varié coûte réellement plus cher qu'une forêt sur un fond uni. C'est le
  prix de la règle, pas un défaut à corriger.

Deux contraintes du mode `shared` **disparaissent** avec la fusion, et il ne faut pas les
réintroduire : toutes les cases d'un placement partageant une seule sous-palette synthétisée, une
case ne peut plus changer de banque d'une image à l'autre. Les miroirs, eux, sont résolus dans
les pixels des deux côtés — une tuile fusionnée est neuve, elle n'hérite pas des bits de miroir
de ses sources.

- **En `shared`, les entrées de carte sont cuites en ROM**, pas posées à l'initialisation :
  elles ne changeront jamais, et le placement étant une propriété du fond hôte, toute scène qui
  affiche ce fond affiche ses animés. Il ne reste au runtime que des pixels à recopier.
- **Le canvas de scène montre les animés posés, figés sur leur première image**, en passant par
  le MÊME calcul de fusion que le build. Figés parce qu'un canvas de scène sert à placer des
  acteurs et des collisions, et qu'un décor qui bouge sous la souris gêne ce travail — c'est
  l'inverse du Background Editor, où l'animation est l'objet qu'on pose. Un aperçu qui
  composerait autrement ferait mentir l'éditeur sur ce que la ROM produira.

#### L'ordre de grandeur, mesuré

Un arbre animé de 48×48 sur 4 images en 4bpp (36 tuiles par image), posé **deux fois** dans un
décor de 10 tuiles. Chiffres relevés au build, pas estimés :

| | `instance` | `shared` |
| --- | --- | --- |
| Tuiles chargées | 100 (10 + **90**) | 46 (10 + 36) |
| Taille de la ROM | 823 884 o | 826 188 o |
| Par changement d'image | 36 entrées de carte (72 o) | 36 tuiles (1152 o) |
| Deux arbres désynchronisés | gratuit | impossible par construction |

L'estimation faite avant d'écrire la moindre ligne annonçait « ≤ 144 tuiles, ~100 après
déduplication, le tronc ne bougeant pas » : 90 mesurées, fusion avec le décor comprise. La
fusion ne coûte donc que 2 tuiles ici — les cases entièrement transparentes au-dessus du même
décor retombent sur une seule tuile, ce qui rattrape l'essentiel.

Les deux modes tiennent largement, et ce n'est pas le coût qui tranche mais l'intention — six
arbres qui scintillent au même instant, c'est la forêt qui respire en rythme.

La règle de croisement, pour qui doit arbitrer : **`shared` ne gagne en mémoire que tant que le
nombre de copies désynchronisées reste inférieur au nombre d'images.** À quatre arbres et
quatre images, les deux modes coûtent la même chose et `shared` fait quatre fois plus de copies
par tick. Il se paie par ailleurs en ROM, puisque ce sont les pixels qui voyagent.

#### Ce qui se règle par COPIE

Une copie posée porte deux réglages, et deux seulement — le reste (découpe, boucle, mode)
appartient à l'animé, une cascade étant une cascade partout où on la pose.

- **`start_frame`** — l'image sur laquelle cette copie démarre.
- **`speed`** — une SURCHARGE de la cadence de l'animé, `0` valant « celle de l'animé ». Même
  convention que `UIPanel.fill_speed` vis-à-vis du sprite qu'il pave : rien de neuf à apprendre.

Le premier plan tenait un décalage en *ticks* plutôt qu'une image de départ, au motif qu'une
forêt dont les arbres sont sur des images différentes change encore de façon synchrone. C'était
vrai, mais la vitesse par copie règle le problème bien mieux : deux copies à des cadences
différentes se désynchronisent durablement, là où un décalage en ticks ne fait que déphaser un
rythme resté commun. L'image de départ suffit alors, et elle se règle sans traduire.

- **Résolu au build.** Tout y est constant, le descripteur émis porte directement l'image et le
  tick de départ ; le runtime ne divise jamais. L'initialisation de scène repart de ce départ
  authoré et non de zéro — revenir dans une scène doit la retrouver telle qu'elle a été réglée,
  pas là où la visite précédente l'avait laissée.
- **Absents en `shared`**, où toutes les copies partagent un unique compteur : l'inspecteur
  masque les champs au lieu de les griser. Un champ sans effet vaut moins qu'un champ absent.
- **L'aperçu du canvas lit la même cadence effective que le build.** Deux copies y jouent
  vraiment à des moments différents ; l'éditeur mentirait sur la ROM si les deux divergeaient.

Ni l'un ni l'autre n'entre dans la clé de partage des blocs : deux copies déphasées lisent
toujours les mêmes tuiles.

#### Ouvert

- Un animé posé **à cheval sur deux fonds hôtes** n'a pas de sens aujourd'hui (le placement
  appartient à un hôte) ; rien ne l'interdit non plus explicitement.
- La fusion suppose que le décor sous un animé ne change pas. Un script qui réécrit ces cases
  (`tilemap.set`) les remet à leur contenu de ROM, animé compris — cohérent, mais jamais
  éprouvé.

### v0.4.2 — Palettes au runtime — **LIVRÉE**

#### Le problème

Les couleurs d'une scène étaient figées à son entrée. `PAL_BG_RAM` n'était écrit qu'au
`scene_init` et par le système de police ; il n'existait **aucun domaine `palette.*`** dans
l'API de script. `tilemap.set_palette` ne faisait pas exception — elle choisit *quelle banque*
une tuile lit, elle ne change aucune couleur.

Changer l'ambiance d'un décor en cours de jeu — la nuit qui tombe, une saison qui vire, une
salle qui passe au rouge — était donc impossible. C'était une fonctionnalité absente, pas une
variante d'autre chose.

#### La frontière avec le mélange, mesurée

Le préalable que ce jalon s'était fixé. Sur le même décor, le mélange en mode 3 (assombrir vers
le noir, formule matérielle exacte) contre un échange de palette :

- **Le mélange éteint tout uniformément.** `BLDCNT` ne cible que BG0-3, OBJ et le backdrop : sa
  granularité est le **calque**, et ses deux seules directions sont le blanc et le noir.
- **Une banque ne concerne que les tuiles qui la citent.** On peut donc refroidir un décor en
  gardant ses lanternes allumées — ce que le mélange ne saura jamais faire.

Le périmètre de la v0.4.2 est exactement ce que le mélange ne couvre pas : un changement de
teinte sélectif. « Il fait nuit » restait du ressort de `blend.set_fade`, et le reste.

#### Décisions verrouillées

- **La rotation de palette est écartée.** Elle figurait comme troisième technique d'animation
  de tuiles (« faire tourner les couleurs d'une palette : eau, lave qui scintille »). Elle ne
  gagne quelque chose que si les images sont la même grille d'index avec une palette
  différente — or une lave dessinée puis exportée en planche a des *index* différents d'une
  image à l'autre, ses tuiles ne se dédupliquent pas, et elle emprunte le chemin ordinaire des
  fonds animés. La faire gagner supposerait que l'éditeur détecte une permutation d'index et
  la convertisse en cycle : de la magie invisible, qui imposerait en plus la lockstep à tout
  ce qui partage la banque. Le cas plein écran, seul rescapé plausible, est couvert par le
  mode `shared`. À ne pas reproposer.
- **Ce qui est visé, c'est l'échange**, pas le cycle : remplacer les seize couleurs d'une
  banque par celles d'une autre palette du catalogue. C'est le besoin réel — une ambiance —
  et il se pose au niveau de la scène, pas de l'asset.
- **Le catalogue ENTIER part en ROM**, et rien n'est dérivé des scripts. Le plan initial
  prévoyait que la scène déclare les palettes atteignables, sur le motif de la réservation des
  polices et de sa règle de sûreté (« réserver trop peu écrit dans le vide sans erreur avant
  l'exécution »). **Ce piège n'existe pas ici** : il venait de la mémoire vidéo, qui est rare.
  Une palette pèse 32 octets en ROM — sur le projet de démo, tout le catalogue coûte 160 octets.
  Émettre l'ensemble supprime d'un coup la dérivation depuis les scripts, la question du nom
  choisi au runtime, et tout risque de sous-réserver. Ne pas recopier un mécanisme dont la
  raison d'être ne s'applique pas.
- **Deux fonctions, pas un argument de cible** : `palette.set_bg(bank, nom)` et
  `palette.set_obj(bank, nom)`. Les deux pools sont physiquement distincts sur GBA
  (`PAL_BG_RAM` / `PAL_OBJ_RAM`), la scène les sélectionne déjà séparément, et une cible en
  paramètre laisserait croire qu'une même banque existe des deux côtés. Les sprites suivent
  donc, au même titre que les fonds — une nuit qui ne tomberait que sur le décor se verrait.
- **Le nom passe par un domaine**, `DOMAIN_PALETTE` → `PAL_{NOM}`, comme les polices et les
  textes. Le checker refuse une palette absente du catalogue en la nommant, plutôt que de
  laisser le `make` échouer sur un identifiant indéfini.
- **Bornés des deux côtés au runtime** : une banque hors 0-15 écrirait dans la palette voisine,
  un index hors table lirait des couleurs au hasard.

#### Ouvert

- La **transition** d'une palette vers une autre sur une durée, plutôt que l'échange sec.
  L'échange sec est tranché comme point de départ : il écrit seize couleurs et s'arrête, là où
  une transition demande un état par banque et une interpolation par image — d'une écriture
  ponctuelle on passerait à un système qui tourne. À rouvrir quand l'échange sec sera en main
  et qu'on verra où la coupure franche se voit.
- Un échange **ne survit pas à un changement de scène** : `scene_init` recharge les palettes
  authorées. C'est cohérent — la scène rétablit son état de départ, comme pour tout le reste —
  mais aucun cas réel ne l'a encore éprouvé.
- Rien côté ÉDITEUR : l'échange s'écrit en Lua, et aucun aperçu ne le montre. Cohérent avec le
  reste de l'API de script, à rouvrir seulement si l'usage réclame de voir l'ambiance sans
  lancer le jeu.

---

## v0.5 — Sauvegarde (SRAM)

S'appuie sur les variables globales déjà existantes pour décider quoi persister. Le socle
était déjà là sans avoir été construit pour ça : `globals.h` émet depuis la v0.3 un **index
par variable** et les accesseurs `global_read(i)` / `global_write(i, v)` — c'est-à-dire
exactement ce dont un sérialiseur a besoin. Il ne manquait que le support.

### Ce que ça donne

Une variable globale peut être marquée **persistante** ; un script écrit ou relit
l'ensemble de ces variables dans un **emplacement de sauvegarde**, et le jeu retrouve son
état au démarrage suivant.

### Décisions verrouillées

- **La persistance est un drapeau par variable**, coché dans la table GLOBALS. Tout
  persister aurait l'air plus simple, mais un compteur de frames ou un index de travail
  n'a rien à faire en mémoire de sauvegarde, et surtout : ce qui entre dans la sauvegarde
  décide de sa compatibilité. Une case à cocher est le prix à payer pour que l'auteur
  sache ce qu'il promet à ses joueurs.
- **SRAM 32 Kio, seule.** 32 Kio adressés octet par octet, sans pilote, sans effacement.
  Une centaine de globales pèse quelques centaines d'octets : la capacité n'est pas la
  contrainte, donc le pilote Flash (identification du fabricant, effacement par secteur,
  bascule de banque) n'achèterait rien. À rouvrir seulement si une donnée volumineuse —
  une carte explorée, un journal — devient persistable, ce qui n'est pas le cas ici.
- **Plusieurs emplacements, leur nombre réglé au projet** (1 par défaut). L'API prend
  toujours un numéro d'emplacement : un jeu à une seule partie écrit `save.write(0)` et ne
  rencontre jamais le concept, un jeu à trois fichiers ne demande pas de changer de
  signature. Le nombre est un réglage et non une valeur libre parce qu'il **borne la
  place** : la capacité se vérifie au build, pas à l'exécution.
- **La sauvegarde ne connaît que des variables.** Pas de « scène de reprise », pas d'état
  moteur caché : reprendre une partie est un aiguillage que l'auteur écrit, comme le
  séquencement d'un dialogue reste du script (v0.3.2). Le moteur qui déciderait *où* on
  reprend déciderait de la structure d'une partie — c'est une décision de genre.
  Conséquence assumée : `scene.switch` reste résolu au build, et un jeu qui veut reprendre
  sa scène écrit son propre test. Si ce test devient un motif récurrent dans un projet
  réel, c'est là qu'il faudra rouvrir, pas avant.
- **L'écriture est explicite, jamais automatique.** Aucune sauvegarde à la sortie de
  scène, aucun rythme imposé : le moment où l'on peut sauver est une règle de game design.
- **Le format est tolérant à l'évolution du jeu.** Chaque valeur est rangée avec l'**id
  opaque** de sa variable, pas à un rang. Ajouter, retirer, réordonner ou renommer une
  variable persistante laisse donc les sauvegardes existantes lisibles ; une variable
  absente du fichier reprend simplement sa valeur par défaut. C'est huit octets par
  variable (quatre d'identité, quatre de valeur) au lieu des deux ou quatre qu'un
  tableau positionnel aurait coûtés — sur 32 Kio, le rapport est sans discussion face à
  « l'auteur ajoute une variable et efface les parties de ses joueurs ». Mesuré sur la
  démo : deux variables persistantes et trois emplacements occupent 84 octets.
  - L'id vaut 12 chiffres, plus que 32 bits : c'est un **repli déterministe sur 32 bits**
    qui est écrit, et une collision entre deux variables persistantes **bloque le build**
    en les nommant. Elle est improbable et resterait sinon indétectable en jeu.
- **Une sauvegarde douteuse est traitée comme absente.** Somme de contrôle par
  emplacement, et empreinte de format en tête. Ni réparation, ni lecture partielle : la
  mémoire d'une cartouche à pile vide rend des octets plausibles, et une lecture « au
  mieux » restaurerait un état inventé sans un mot. Même refus de la dégradation
  silencieuse qu'en v0.2.
- **Le support n'est déclaré que s'il sert.** La chaîne de détection `SRAM_Vnnn` — que
  cherchent émulateurs et linkers pour savoir qu'il y a une sauvegarde — n'est émise que
  si le projet a au moins une variable persistante. Un jeu sans sauvegarde ne doit pas
  faire naître un fichier de sauvegarde vide chez le joueur.

### Ouvert

- **Effacer un emplacement, oui ; le lister, pas encore.** `save.exists` répond « il y a
  quelque chose ici », ce qui suffit à griser une entrée de menu. Un écran de sélection
  qui afficherait *quoi* — un nom, une durée de jeu, un chapitre — demanderait un
  en-tête descriptif par emplacement, donc une notion de métadonnée que le format
  n'a pas. À rouvrir sur un cas réel.
- Rien côté éditeur ne montre l'occupation de la sauvegarde en dehors du garde-fou de
  build. Un indicateur « X octets sur 32 Kio » n'a d'intérêt que si l'on peut approcher
  la limite, ce qui demande beaucoup de variables.

---

## v0.6 — Polish de la boucle de jeu

### v0.6.1 — Caméra

Gros sujet, à la fois fonctionnel et rendu.

#### Le problème

**Deux mécanismes de caméra coexistent aujourd'hui, indépendants et non coordonnés** : un
déclaratif (la scène désigne un acteur à suivre, avec recentrage exact et blocage aux bords
du monde) et un scriptable (suivi par zone morte, mais sans aucun blocage aux bords). Un
troisième chemin, le scroll manuel, n'a pas de blocage non plus. Les trois écrivent la même
position sans se coordonner : une scène configurée dans l'inspecteur **et** pilotée par un
script se disputent la caméra. Le risque est concret, pas théorique.

Le parallaxe, lui, fonctionne déjà avec n'importe lequel des trois — il ne fait que lire la
position de la caméra. Rien à reconstruire de ce côté.

**Le zoom est impossible en Mode 0** : les calques réguliers ne savent pas se mettre à
l'échelle. Bloqué jusqu'aux calques affines de la v2.0 — à exclure explicitement du périmètre,
ce n'est pas un oubli.

#### Décisions verrouillées

Contrainte de départ : la GBA n'a qu'un seul écran et le multijoueur est hors périmètre.
« Plusieurs caméras » ne peut donc pas vouloir dire plusieurs vues simultanées. Ça veut dire
**plusieurs configurations définissables, une seule active à la fois par scène**.

- **La caméra devient un asset à part entière**, réutilisable entre scènes comme un prefab,
  et **remplace** les deux mécanismes en conflit par une seule source de vérité : cible, zone
  morte, bornes et secousse au même endroit.
- **Rangée avec les données propres au projet**, pas avec les ressources externes — une
  configuration de caméra ne dépend d'aucun fichier importé.
- **Changement de caméra par appel explicite uniquement**, pas de bascule automatique par
  zone. Un comportement « zone » reste possible sans concept dédié : le script active la
  caméra depuis le déclencheur de collision qui existe déjà. Pas besoin d'un type « zone de
  caméra » séparé.
- **Une caméra par défaut est créée avec la scène** : l'utilisateur n'a jamais à en créer une
  pour le cas simple.
- **La scène référence sa caméra de démarrage** ; le script peut en changer ensuite.
- **Le défilement horizontal/vertical reste une propriété de la scène**, il ne migre pas dans
  la caméra. Ce sont deux concepts : la caméra décide *comment* la position est calculée, le
  défilement décrit *si le niveau lui-même* est censé défiler dans cet axe. Changer de caméra
  ne doit pas changer ça. Il agit comme un filtre appliqué par-dessus.
  - **Bug à corriger dans le même chantier** : aujourd'hui désactiver le défilement ne bloque
    pas réellement le mouvement de la caméra en mode suivi, seulement le blocage aux bords. Le
    réglage ne fait pas ce que son nom promet — à corriger en posant le nouveau modèle, pas à
    documenter tel quel.
- **La caméra peut recevoir un script**, avec les mêmes points d'entrée qu'une scène. Les
  réglages déclaratifs sont **toujours calculés en premier** ; le script s'exécute ensuite et
  peut ajuster. Ça permet un usage purement déclaratif, purement scripté, ou hybride, sans
  réglage de bascule dédié.

#### Ouvert

- Champs exacts de l'asset caméra (marges de zone morte ? bornes activables ? paramètres de
  secousse — amplitude, durée, décroissance ?).
- Convention de nommage de la caméra créée par défaut.
- Stratégie de migration des scènes existantes — pré-1.0, donc probablement pas critique.
- Le **blocage aux bords du monde** n'existe aujourd'hui que dans l'ancien mécanisme
  déclaratif : à porter proprement dans le nouveau modèle.

### v0.6.2 — Transitions de scène

Fondu à l'ouverture et à la fermeture : un changement de scène est aujourd'hui une coupure
franche.

### v0.6.3 — Pentes / collision

Une vingtaine de types de tuiles de pente sont définis côté éditeur (26°, 45°, 63° et leurs
miroirs), à finaliser côté runtime.

#### Ouvert

- La résolution réelle des pentes au runtime n'a **jamais été confirmée** : ce point est
  peut-être à *construire* plutôt qu'à *finaliser*. Vérifier avant de scoper.

---

## v0.7 — Son enrichi & écran de mixage

Les ressources son et musique sont aujourd'hui des ébauches, explicitement marquées comme
telles dans le code.

### v0.7.1 — Clarifier les ressources

Format source des effets (wav brut ou conversion), hauteur ; format de musique (module
tracker) et point de bouclage.

### v0.7.2 — Écran de mixage

Existe déjà en partie, à enrichir : écoute du mélange en direct, volume par canal ou par
catégorie, gestion des priorités — le nombre de canaux matériels est limité.

#### Ouvert

- Politique de priorité quand trop d'effets jouent en même temps : non décidée.

### v0.7.3 — API

Jouer un son ou une musique avec des surcharges de hauteur et de volume **à l'appel**, pas
seulement au niveau de la ressource.

---

## v0.8 — Traduction des jeux créés avec l'éditeur

Sujet **séparé** de la traduction de l'éditeur (v0.10) : deux chantiers indépendants.

### Périmètre

- Tables de chaînes multilingues, basées sur les clés posées en v0.3 — c'est précisément pour
  éviter un refactor complet ici que les textes sont référencés par clé depuis le début.
- Sélection de la langue en jeu, persistée par la sauvegarde de la v0.5.

### Ouvert

- Format des tables multilingues non défini.
- Workflow de traduction pour quelqu'un sans compétence de développement : édition directe
  dans l'éditeur, ou export/import type tableur ?

---

## v0.9 — Distribution élargie

Réactivation de la construction Linux (en pause, en attendant un test sur une vraie
distribution).

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût récurrent — « Linux seul » est
  une option valable si le coût ne se justifie pas.

---

## v0.10 — Traduction de l'interface de l'éditeur

Complètement indépendant du runtime GBA. Déplaçable librement dans l'ordre : peut être fait
en parallèle de n'importe quelle autre version.

---

## v1.0 — Consolidation

Un **deuxième jeu de démo** au-delà de Pong, qui exerce réellement texte, sauvegarde, caméra,
transitions et traduction — pour valider le pipeline de bout en bout comme Pong l'a fait pour
la v0.1. Plus stabilisation et documentation.

### Ouvert

- Aucun genre choisi. Une plateforme ou un proto-RPG exerceraient mieux les nouvelles
  fonctionnalités qu'un second jeu du type de Pong.

---

## Au-delà de la v1.0

### v2.0 — Backgrounds affines (« Mode 7 »)

Un calque affine ajoute rotation et zoom, au prix de perdre des calques réguliers ailleurs —
et il adresse sa carte différemment, donc c'est un **second chemin de génération de code**,
pas « un calque de plus ».

Volontairement décrit à haut niveau : la portée exacte dépendra de ce qui aura été appris en
construisant les fondations précédentes.

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

### v3.0 — Modes bitmap

Famille complètement différente des modes tuilés : un seul calque, pas de tuiles ni de cartes,
un framebuffer direct. Le budget des sprites y est par ailleurs divisé par deux.

| Mode | Résolution | Couleur | Tampons |
| --- | --- | --- | --- |
| 3 | 240×160 | 16 bits directs | 1 seul |
| 4 | 240×160 | 8 bits indexés | 2 (double tampon) |
| 5 | 160×128 | 16 bits directs | 2, résolution réduite |

**Priorité au mode 4** : 256 couleurs, double tampon, pleine résolution — il évite le
déchirement d'image du mode 3 et la résolution réduite du mode 5.

**Exclu délibérément des fondations v0.3** : les modes bitmap cassent tout le pipeline actuel
(tilesets réutilisables, palettes par banque) au profit d'un framebuffer brut. C'est un moteur
de rendu différent, pas une extension — et c'est aussi pourquoi de vrais jeux commerciaux les
emploient rarement.

---

## Hors périmètre (pour l'instant)

- **Multijoueur par câble Link** — envisagé après la v1.0, pas avant. Très spécifique et
  coûteux à implémenter proprement.
