
# Roadmap détaillée

Ce document explique **le pourquoi** derrière chaque jalon : ce que la version résout, les
choix qui sont tranchés, et les questions volontairement laissées ouvertes.

Quatre documents, quatre rôles :

| Fichier | Pour qui | Contenu |
| --- | --- | --- |
| [README](README.md) | un visiteur | une ligne par version |
| **ce fichier** | qui décide de la suite | scope, décisions, questions ouvertes |
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
| v0.2 | Palettes de couleurs | **Livrée**, quelques finitions |
| v0.3 | Background vivant, texte et interface | **Livrée**, un report assumé |
| v0.4 | Animation de décor | **Livrée** |
| v0.5 | Sauvegarde | **Livrée** |
| v0.6 | Polish de la boucle de jeu | **Livrée**, rouverte pour le game feel |
| v0.7 | Structures de données, et le langage | **Livrée**, les deux chantiers rouverts avec |
| v0.8 | Son : la musique par scène, les transitions, le mixage | Non commencée |
| v0.9 | Traduction des jeux | Non commencée |
| v0.10 | Distribution Linux | Non commencée |
| v0.11 | Traduction de l'éditeur | Non commencée |
| v0.12 | Vue d'ensemble (graphe des scènes) | Non commencée |
| v0.13 | Édition mixte (appels d'API en blocs) | Non commencée |
| v0.14 | Diagnostic (trace de débogage, budget) | Non commencée |
| v0.15 | Visibilité des éléments d'interface | **Livrée**, sous une autre forme que prévu |

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
  et il est traduisible — c'est ce qui rend la v0.9 possible sans tout refactorer.
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

Le point de départ n'est pas l'affichage mais **où le texte est rangé**, parce que la v0.9
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
  évite un tri manuel en v0.9.

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
- ~~Une dizaine de méthodes d'acteur sont regroupées dans une catégorie fourre-tout de la
  documentation intégrée, à ranger à la main.~~ **Réglé en v0.7.4** : `api_reference.json` est
  purgé et la réconciliation garde sa place à une catégorie — 22 catégories nommées, aucune
  « Autres ».

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

### v0.6.1 — Caméra — **LIVRÉE**

#### Le problème d'origine

Il était que **trois mécanismes de caméra coexistaient**, indépendants et
non coordonnés : un déclaratif (la scène désigne un acteur à suivre, recentrage exact et
blocage aux bords du monde), un scriptable (zone morte, sans blocage), et le scroll manuel
au D-pad (sans blocage non plus). Les trois écrivaient la même position sans se coordonner.

L'unification a été faite en premier : un seul point d'écriture, des bornes explicites
appliquées par un clamp unique, et le scroll libre au D-pad retiré. **La v0.6.1 est LIVRÉE**
(2026-08-12) : la caméra est devenue un asset portant mode, cible, zone morte, bornes et
script, la secousse existe, et une scène désigne sa caméra de démarrage.

Le parallaxe fonctionne avec n'importe lequel des modes — il ne fait que lire la position de
la caméra. Rien à reconstruire de ce côté.

#### Ce que la v0.6.1 ne fera JAMAIS, et pourquoi

Ce sont les branches d'une caméra de moteur 3D (Unity, Godot) que le matériel ne peut pas
tenir. Les proposer dans l'inspecteur promettrait un rendu que la GBA ne produit pas — même
règle que les modes de mélange *multiply* et *overlay*, absents pour la même raison.

| Demandé | Verdict |
| --- | --- |
| rotation | **impossible en Mode 0.** Un calque régulier ne tourne pas ; seul un calque affine le sait (v2.0). Les sprites, eux, tournent déjà — mais tourner les sprites sans le décor n'est pas une rotation de caméra |
| projection (ortho / perspective, FOV) | **la GBA n'a pas de 3D.** Le « Mode 7 » n'est pas une projection perspective mais une transformation affine appliquée ligne par ligne. Le vrai axe est *régulier* contre *affine* |
| zoom (taille orthographique) | même raison que la rotation : c'est une matrice affine, donc la v2.0 |
| viewport (x, y, largeur, hauteur) | **faisable, mais c'est une window matérielle** — il n'y en a que deux, et la scène les authore déjà. Reporté en v2.0 avec l'écran partagé, qui rouvrira « une région appartient-elle à une caméra, ou l'inverse ? » |
| mode de rendu | **reste à la scène.** Le mode vidéo décide quels types de calques existent, et les fonds de la scène sont authorés contre lui : une caméra qui le changerait invaliderait les fonds de la scène qui l'active |

#### Décisions verrouillées

Contrainte de départ : la GBA n'a qu'un seul écran et le multijoueur est hors périmètre.
« Plusieurs caméras » ne peut donc pas vouloir dire plusieurs vues simultanées. Ça veut dire
**plusieurs configurations définissables, une seule active à la fois par scène**.

- **La caméra est un asset à part entière**, réutilisable entre scènes comme un prefab :
  mode, cible, zone morte, bornes et script au même endroit (`project/cameras/*.json`).
- **Rangée avec les données propres au projet**, pas avec les ressources externes — une
  configuration de caméra ne dépend d'aucun fichier importé.
- **Changement de caméra par appel explicite uniquement**, pas de bascule automatique par
  zone. Un comportement « zone » reste possible sans concept dédié : le script active la
  caméra depuis le déclencheur de collision qui existe déjà. Pas besoin d'un type « zone de
  caméra » séparé.
- **La caméra par défaut est IMPLICITE** : une scène qui n'en désigne aucune est fixe à
  l'origine, sans bornes ni suivi, et aucun fichier n'existe pour ça. L'auteur n'a donc rien
  à créer pour le cas simple, et la liste des caméras ne se remplit pas d'une entrée par
  scène jamais réglée. Elle se matérialise au PREMIER réglage — y compris le déplacement du
  cadre dans le canvas : « je veux autre chose que l'origine » est exactement le moment où
  une caméra a lieu d'exister. Au runtime, elle est l'entrée 0 de la table, ce qui évite un
  cas particulier à chaque activation.
- **La scène référence sa caméra de démarrage** ; le script peut en changer ensuite.
- **Le défilement horizontal/vertical reste une propriété de la scène**, il ne migre pas dans
  la caméra. Ce sont deux concepts : la caméra décide *comment* la position est calculée, le
  défilement décrit *si le niveau lui-même* est censé défiler dans cet axe. Changer de caméra
  ne doit pas changer ça. Il agit comme un filtre appliqué par-dessus.
  - ~~**Bug à corriger dans le même chantier** : désactiver le défilement ne bloque pas
    réellement le mouvement de la caméra en mode suivi.~~ **Corrigé** : un axe désactivé
    reçoit `cam_x`/`cam_y` lui-même comme cible, donc un écart nul, donc aucun mouvement.
- **La caméra peut recevoir un script**, avec les mêmes points d'entrée qu'une scène. Les
  réglages déclaratifs sont **toujours calculés en premier** ; le script s'exécute ensuite et
  peut ajuster. Ça permet un usage purement déclaratif, purement scripté, ou hybride, sans
  réglage de bascule dédié.

- **La secousse n'a AUCUN champ dans l'asset.** C'est un événement, pas un état : rien de
  déclaratif ne la déclenche, donc des champs seraient les valeurs par défaut d'un appel qui
  les porte déjà. `camera.shake(amplitude, frames)`, l'amplitude retombant linéairement à
  zéro sur la durée — c'est la décroissance, sans troisième réglage. Le décalage est appliqué
  APRÈS le clamp aux bornes (trembler au bord du monde doit se voir) et retiré au début de la
  frame suivante, si bien que le suivi ne raisonne jamais sur une position tremblée.
- **Les bornes s'appliquent à l'ACTIVATION, pas à chaque frame.** Les réécrire chaque frame
  ferait de `camera.set_bounds()` un mensonge : un script qui débloque une zone garde la main
  jusqu'à la prochaine activation.
- **Activer une caméra applique son cadrage.** C'est ce que « caméra fixe » veut dire ; une
  caméra en suivi se recale de toute façon dans la frame.
- **La cible est citée par NOM et résolue par scène.** Les noms d'acteurs sont locaux à une
  scène ; une caméra réutilisée là où cet acteur n'existe pas y reste immobile, et le
  validateur le dit. Le codegen n'émet le suivi que pour les caméras qui peuvent réellement
  suivre quelqu'un dans cette scène-là.
- **Migration : table rase.** Les anciens champs `cam_*` inline des scènes ne sont plus relus
  (la maison ne migre pas les formats) ; une scène antérieure repart de la caméra par défaut.
  Vérifié sans conséquence sur la démo Pong, dont les trois scènes étaient au défaut.

#### Ouvert

- Rien côté éditeur ne liste les caméras hors de l'inspecteur : on en choisit une, on la
  renomme et on la crée depuis là. Un vrai gestionnaire d'assets n'a d'intérêt qu'avec
  beaucoup de caméras — à rouvrir sur un cas réel.

### v0.6.2 — Transitions de scène

Un changement de scène est une coupure franche. Cette version lui donne un fondu à la
fermeture et à l'ouverture.

La brique basse existait déjà : `blend_set_mode(2|3)` + `blend_set_fade(evy)` posent un
fondu vers le blanc ou le noir sur tout l'écran (v0.3, mélange de couleurs). Ce qui manquait
est le **séquencement** autour de la bascule, qui vit dans la boucle principale — le seul
endroit qui connaisse les deux scènes. `scene_switch()` ne fait que poser une intention.

#### Décisions verrouillées

- **Réglage de projet, surchargeable par scène.** Un type (aucun / vers le noir / vers le
  blanc) et une durée en frames valent pour tout le jeu ; une scène peut déclarer les siens.
  Le défaut de projet évite d'avoir à répondre à la question sur chaque scène, la surcharge
  évite d'imposer un fondu à un menu qui doit apparaître net.
- **Une transition a deux moitiés, et chaque scène décrit la sienne.** La fermeture emploie
  le réglage de la scène **qu'on quitte**, l'ouverture celui de la scène **qu'on ouvre**. Il
  n'y a donc jamais de « qui gagne » entre deux scènes : une scène dit comment elle
  disparaît et comment elle apparaît, un point c'est tout. L'héritage projet→scène est
  résolu **au build**, en une table par scène : le runtime ne connaît pas la notion.
- **La scène sortante gèle.** Son tick est suspendu dès la première frame du fondu : l'image
  se fige et s'éteint. Laisser tourner le jeu sur un écran qu'on quitte, c'est laisser le
  joueur agir sans le voir, et laisser un script s'exécuter sur une scène condamnée. La
  musique et le compteur de frames, eux, continuent — la transition est un effet d'affichage,
  pas une pause du moteur.
- **La première scène fait son ouverture comme les autres.** Le jeu démarre en fondu si la
  scène de départ en déclare un. Pas de cas particulier au démarrage : un écran noir pendant
  l'init est de toute façon plus propre qu'une première frame à moitié construite.
- **L'effet de mélange authoré de la scène est suspendu pendant la transition.** `BLDCNT`
  n'a qu'un seul champ mode : il n'existe pas de « fondu par-dessus une translucidité » sur
  ce matériel. Le réglage de la scène est repris tel quel à la fin du fondu (l'instantané
  est pris après `scene_init`, donc c'est bien celui de la scène entrante). Conflit
  matériel assumé et dit, pas contourné par un second chemin.
- **Un `scene.switch` appelé pendant une transition est honoré à la fin de celle-ci**, pas
  au milieu. Interrompre un fondu en cours pour en démarrer un autre demanderait de décider
  ce que devient la moitié déjà jouée ; l'attente est prévisible et se comprend sans
  documentation.
- **Même vocabulaire que le mélange de couleurs** : `none`, `fade_black`, `fade_white`. Ce
  sont les chaînes déjà employées par les effets de scène — un fondu au noir doit s'appeler
  pareil partout.

#### Ouvert

- Aucune API Lua dédiée n'est ajoutée : `blend.set_fade` couvre déjà le fondu piloté à la
  main, et la transition de scène est déclarative. À rouvrir si un cas réel demande de
  déclencher une transition sans changer de scène.
- Autres types que le fondu (volet, cercle, pixelisation) : hors périmètre. Ils demandent
  soit une window animée, soit une manipulation de palette par frame, c'est-à-dire un autre
  chantier que celui-ci.

### v0.6.3 — Pentes / collision — **LIVRÉE**

22 types de tuiles de pente sont définis côté éditeur (26°, 45°, 63° et leurs miroirs
plafond), avec leur génération par glisser et leur rendu dans le canvas. Le doute posé en
« Ouvert » est **confirmé** : le runtime n'en savait rien — `tile_solid_at` répondait
`cmap[i] != 0`, donc toute pente était un bloc plein. C'était à **construire**.

Deux choses ont été trouvées en ouvrant le chantier, qui en ont élargi le périmètre :

- **la résolution ne tournait que si l'acteur définissait `on_tile_collide`**, alors qu'elle
  *déplace* l'acteur et que le callback n'est qu'une notification. Un acteur à box `solid`
  sans ce hook traversait la carte, quand le modèle promet « solid = résolution physique » ;
- **la géométrie des 22 tuiles n'existait que dans les polygones du canvas.** Écrire la table
  du runtime à la main en aurait fait une seconde source, qui aurait divergé au premier
  ajustement — le défaut des « deux listes de prototypes ».

#### Décisions verrouillées

- **Une seule source pour la géométrie.** Chacune des 22 tuiles se décrit par *une droite de
  surface traversant la tuile, plus le côté plein* — deux ordonnées et un drapeau. Le
  polygone exact du canvas et le profil de hauteurs que lit le runtime en **dérivent** tous
  les deux. Vérifié sur les 22, pentes raides comprises (leur droite sort de la tuile et se
  clampe).
- **Toute box `solid` collisionne** avec la carte de tuiles dès que la scène en a une.
  `on_tile_collide` redevient ce qu'il prétend être : une notification. Et la vitesse est
  remise à zéro sur l'axe bloqué **toujours** — auparavant le callback la remplaçait, si bien
  qu'écrire le hook désactivait la physique.
- **Une tuile de pente ne bloque jamais le déplacement horizontal.** Seul `TILE_SOLID`
  repousse en X ; sinon une pente serait un mur et personne ne la gravirait. La conséquence
  est assumée : l'acteur qui entre dans une pente est *soulevé* à sa surface, sans plafond de
  marche — c'est ce que l'auteur a dessiné en peignant une pente plutôt qu'un bloc.
- **Le sol se cherche en trois points** — les deux coins bas de la box et son centre, la
  surface la plus haute l'emportant. Un acteur large ne s'enfonce donc pas dans la pente et
  franchit une arête proprement.
  - Chaque sonde balaie **trois tuiles** : celle au-dessus des pieds, celle des pieds, celle
    du dessous. La tuile du dessus est indispensable — sur une pente, la matière de la
    colonne suivante vit dans la tuile d'au-dessus, et s'arrêter aux pieds fait décrocher
    l'acteur en pleine montée. Une surface plus haute que la box est écartée : elle ne le
    touche pas, et l'y hisser le téléporterait sur une plateforme qu'il passait dessous.
- **La vitesse est constante LE LONG du sol.** Un pas horizontal sur une pente parcourt
  `√(1+p²)` fois plus de distance qu'à plat — 114 % à 26°, 141 % à 45°, **224 % à 63°** —
  donc sans correction, plus la pente est raide plus le personnage paraît rapide. Le moteur
  ramène le pas au cosinus de la pente gravie, précalculé par type de tuile (aucune racine à
  l'exécution). C'est la seule chose que le moteur DÉFAIT de ce qu'un script a demandé, d'où
  deux garde-fous : il faut être au sol à la frame précédente (un saut n'est pas une marche),
  et le pas doit tenir dans une tuile — au-delà la résolution ne prétend déjà plus rien, et
  c'est là qu'un script téléporte au lieu de marcher. Le reste est reporté au 1/256 de pixel,
  sinon un pas de 2 px à 45° tomberait toujours sur 1 px.
  - Conséquence assumée des positions ENTIÈRES : à 1 px par frame, la marche devient « un
    pixel, une pause » (29 % des frames sur une pente à 45°). Impossible d'avancer de 0,7
    pixel ; à partir de 2 px par frame le mouvement redevient régulier.
- **Le monde reste une boîte close.** Hors carte vaut plein, dans les quatre directions —
  c'est ce que faisait l'ancien `tile_solid_at`, et le perdre laisse un acteur tomber sans
  fin, son sprite rebouclant en haut de l'écran tous les 256 px (l'OAM ne code Y que sur
  8 bits).
- **Le collage au sol appartient au moteur, sans réglage exposé.** Un bit « au sol » sur
  l'acteur, et en descente il est recollé tant que l'écart reste sous `|vx|×2 + 1` px — la
  chute maximale que la pente la plus raide (63°) peut produire à cette vitesse. Dérivé du
  mouvement : ni constante magique, ni champ à comprendre. Sans lui, toute descente
  tressaute.
- **L'ordre passe de Y-puis-X à X-puis-Y.** On avance à l'horizontale sans être gêné par les
  pentes, *puis* la surface est cherchée — l'inverse ferait chercher le sol à une abscisse
  qu'on n'occupe pas encore.

- **`solid` ne voulait déjà dire que ça.** En cherchant qui avait droit à la résolution, on a
  découvert que le drapeau n'est lu nulle part ailleurs : les collisions acteur-contre-acteur
  ne le consultent pas, malgré une docstring qui prétendait l'inverse depuis toujours. La
  décision ci-dessus ne fait donc qu'appliquer le sens que le code lui donnait déjà.
  Conséquence sur la démo : les box de Pong (raquettes, balle) sont passées à `solid=false`,
  car leurs scripts gèrent les murs eux-mêmes (`tile.get` + rebond maison). Sans ça la balle
  se collait au mur du bas, vitesse verticale annulée — vérifié en simulation avant de le
  dire.

#### Ouvert

- Pas de gravité, pas de plateforme traversable par le bas : le moteur n'a pas de physique à
  lui au-delà de ce qui précède. Un script décide du mouvement, la résolution le corrige.
- **Rien n'agit à distance** : la sonde ne regarde que la tuile courante et sa voisine, donc
  un acteur qui va plus vite que 8 px par frame peut traverser un sol. C'était déjà le cas
  avant, et le corriger demanderait un balayage du trajet — à rouvrir si un vrai jeu s'y
  heurte. **Toujours vrai, et daté** : la
  physique (gravité, milieux, collision par normale, types de corps) est le sujet de la
  v2.1 et n'arrivera pas avant elle — décidé le 2026-08-12. Cette ligne n'est donc pas une
  lacune à combler au prochain passage, c'est la règle en vigueur jusqu'à la v2.0.
- `actor_on_ground()` existait en C sans être exposée en Lua ; elle l'est désormais
  (`self.grounded`, propriété en lecture seule depuis la v0.7.4) et lit le bit posé par la
  résolution, donc l'état de la frame précédente — un script qui la consulte dans
  `on_update` lit le résultat du tour d'avant, ce qui est le contrat normal.

### v0.6.4 — Transform affine et game feel — **LIVRÉE**

Rangée ici par SUJET et non par date : elle est arrivée après la v0.7.7, et c'est bien du
polish de boucle de jeu — un impact qui écrase le sprite, un dégât qui le fait clignoter.

#### Le problème : ça existait, et ça ne marchait pas

La v0.6.1 écrivait « les sprites, eux, tournent déjà ». C'était vrai sur le papier et faux à
l'exécution : les tableaux `g_affine_*[]` étaient `static` dans un header **multi-inclus**,
donc recopiés une fois par unité de compilation. Un `self.rotation` écrit depuis
`actor_Ball.c` n'atteignait jamais le rendu, qui lisait la copie de `main.c`. Panne muette —
le C compile, le sprite ne tourne pas.

#### Décisions verrouillées

- **Deux niveaux de transform, séparés par qui les possède.** Le transform **monde** appartient
  à l'`Actor` (`self.rotation`, `self.scale`), le transform **local** au `SpriteComponent`
  (`self.sprite_rotation`, `self.sprite_scale`, `self.sprite_offset`). Le matériel n'a qu'UNE
  matrice par slot : le runtime les compose à la frame et n'écrit que le résultat — rotation
  sommée, scale multiplié en Q8, offset transformé par la matrice de l'ACTOR. Le local vit donc
  dans le repère de l'actor : quand l'actor tourne, l'offset du sprite tourne avec lui.
- **La décision vit sur l'ACTOR, pas sur le sprite** — `Actor.affine_transform`, case « Affine
  transform » de l'inspecteur. Un actor coché **réserve un des 32 jeux de paramètres du
  matériel, même à l'identité** : c'est ce qui donne à `self.rotation` un endroit où écrire.
  Décoché, aucun slot n'est pris et les champs de transform n'ont aucun effet.
- **Un prefab porte la même case, et elle vaut pour tout son pool** — chaque copie réserve son
  slot. Elle est montrée dans une carte « Affine » **séparée de « Transform »** : l'affine est
  une capacité de RENDU, décidable sur un template, là où x/y/priority/direction sont un
  PLACEMENT, qui n'existe que pour un actor posé dans une scène.
- **Le slot appartient à la SCÈNE**, distribué au seed par `_compute_affine_info` : le même
  prefab n'a pas le même numéro d'une scène à l'autre.
- **Le stockage runtime est PAR-ACTOR, jamais indexé par slot.** Un script de prefab poolé est
  une fonction C partagée par toutes ses instances ; chacune a sa struct `Actor` mais un
  `affine_slot` différent, donc les valeurs propres à l'instance ne peuvent venir que de son
  `g_actors[i]`. C'est aussi ce qui supprime par construction la panne muette ci-dessus : il
  n'existe plus de copie par unité de compilation à désynchroniser.
- **Sans slot, le getter rend l'identité et le setter ne fait rien** (`if (affine_slot >= 0)`),
  et le **checker refuse au build** un `self.rotation` sur un actor non coché en nommant la
  case. Le silence est fermé du côté où il se voit — sur la ligne Lua, pas sur le rendu.
- **Neuf helpers de game feel qui ne composent que l'API existante** — `squash`, `stretch`,
  `bounce`, `shake`, `flash`, `blink`, `pulse`, `pop`, `wobble`, tous en `self:<nom>(t,
  duration, amount)`. Ils sont **sans état** : `t` est fourni par l'appelant, et au-delà de
  `duration` l'effet retombe seul à son neutre. Aucun n'ajoute de capacité — chacun se
  réécrit à la main avec `sprite_scale`, `sprite_offset`, `sprite_rotation`, `pal` ou
  `visible`, et un test le vérifie. Ce sont donc des raccourcis nommés d'après l'effet
  observable, pas un système d'animation.
  - Les sept qui écrivent un transform exigent « Affine transform », **sans erreur** : même
    contrat que `self.sprite_scale`, ils sont simplement sans effet. `flash` et `blink`
    (palette, visibilité) n'ont pas cette contrainte.

#### Le piège du spawn

`spawn_X()` remet l'`Actor` à zéro (`(Actor){0}`). Il doit donc **préserver le slot et reposer
les échelles neutres** (256 = ×1) du template : sans ça une instance spawnée repart avec une
échelle nulle — matrice dégénérée, sprite invisible — et avec le slot 0, c'est-à-dire celui
d'un autre actor. Trouvé au même endroit : le seed de scène lisait `flip_h` sur le
`SpriteComponent`, un champ qui n'y existe pas, donc toujours faux ; il le lit sur l'`Actor`.

#### Ouvert

- **Les helpers demandent leur `t` parce qu'ils sont antérieurs aux séquences.** Depuis la
  v0.7.7, `wait(n)` existe, et un helper appelé dans une séquence pourrait tenir son propre
  compteur. Rien ne presse — la forme sans état reste la bonne hors séquence — mais les deux
  écritures cohabitent sans qu'aucune documentation ne dise laquelle choisir.

---

## v0.7 — Structures de données

**Placée en tête du reste des v0.x parce qu'elle est la porte de la v1.0**, et la seule qui
le soit : les versions qui suivent (son, traductions, distribution) enrichissent un pipeline
déjà utilisable, celle-ci débloque des genres entiers qui sont aujourd'hui hors d'atteinte.

### Le problème, mesuré

Le sous-ensemble Lua ne connaît que des scalaires. `parser.py` le dit en toutes lettres :
`field: str  # pour notation DOT ; pour [] ce sera une Expr → non géré v1`. Il n'y a ni
constructeur de table, ni parcours `for … in`, ni indexation. L'AST complet est nombres,
booléens, nil, chaînes, noms, accès pointé, appels, opérateurs.

Et il n'existe **aucun asset de table de données** : les registres du projet sont des scènes,
prefabs, sprites, fonds, sfx, musiques, polices, palettes, mises en page, caméras, textes et
variables — et les variables sont des scalaires. Un RPG a deux cents objets à décrire quelque
part ; il n'y a nulle part.

Deux manques jumeaux, un seul effet :

| Genre visé en v1.0 | Atteignable aujourd'hui | Ce qui manque |
| --- | --- | --- |
| Platformer | **oui** | rien — la gravité s'écrit au script, la résolution de pentes v0.6.3 fait le reste |
| Metroidvania | **oui** | rien — l'état persistant tient dans les globals + SRAM de la v0.5 |
| RPG | non | inventaire, objets, sorts, groupe : des listes |
| Tactique (Advance Wars, FFT) | non | unités, grille, recherche de chemin : des tableaux |
| Gestion (Zoo Tycoon) | non | N entités à état propre : un tableau |

#### Un troisième manque, découvert en ouvrant le chantier

**La boucle `for` numérique ne marche pas** — pas « n'existe pas » : elle se traduit, et le C
produit ne s'exécute jamais. `parser.py` lit les champs de `Fornum` décalés d'un cran par
rapport à luaparser, qui expose `(target, start, stop, step, body)` : le convertisseur prend
`start` pour la variable de boucle, `stop` pour la borne de départ, `step` pour la borne
d'arrivée, et jette le pas.

```
for i = 1, 10, 2   →   StmtForNum(var='i', start=10, stop=2, step=None)
                   →   for (int i = 10; i <= 2; i += 1)     /* corps jamais atteint */
```

Sans pas déclaré, la borne d'arrivée tombe à `None`, donc à `0`, donc `i <= 0` : même
silence. Et `var` retombe sur son défaut `"i"`, si bien que `for k = …` déclare quand même un
`i`. C'est le premier caillou de la v0.7 — un tableau sans boucle ne sert à rien — et c'est
une **correction**, pas une fonctionnalité : la panne n'a jamais rien dit, parce qu'un corps
de boucle non exécuté ne produit ni erreur de checker, ni avertissement gcc.

### v0.7.1 — Les tableaux dans le langage — **LIVRÉE**

Vérifiée par un build ROM complet sur une copie de la démo, `build/` effacé : un tableau
d'état dans un acteur de scène, un tableau de travail dans un handler de prefab poolé, et le
refus attendu quand ce dernier est déclaré en tête. Le C émis se relit avec les mots du Lua :

```c
static int couts[4] = {1, 2, 4, 8};
static int grille[4][3] = {{0}};
for (int i = 1; i <= 4; i += 1) { total = (total + couts[(i) - 1]); }
for (int y = 4; y >= 1; y += (-1)) { grille[(y) - 1][1] = total; }
```

#### Décisions verrouillées

- **Des tableaux typés de taille fixe, pas des tables Lua.** Une vraie table Lua suppose
  hachage, redimensionnement et ramasse-miettes — trois choses qui n'ont rien à faire dans un
  moteur entièrement entier, sans allocation, sur 32 Ko d'IWRAM. Un tableau de taille connue
  se traduit en C directement, et le coût reste visible dans le source généré.
- **La taille fait partie du type.** Elle est connue au build, donc vérifiable au build : un
  dépassement est une erreur du checker, pas un comportement au runtime. C'est la même règle
  que partout ailleurs — la faute se voit sur la cause, jamais sur une ligne générée. Un index
  **calculé** n'est en revanche vérifié par personne : le borner à chaque accès coûterait un
  test par lecture dans un moteur qui n'en fait aucun ailleurs.
- **Deux origines pour une table, un seul type à l'usage.** Une table AUTHORÉE (l'asset de la
  v0.7.2, émis en `const` dans la ROM) et une table de TRAVAIL déclarée dans un script (en
  RAM). Le script les lit de la même façon ; seule l'écriture distingue les deux, et la const
  refuse d'être écrite — au build.
- **Deux façons de déclarer, parce que ce sont deux besoins.** `local couts = {1, 2, 4, 8}`
  donne le CONTENU et en déduit la taille ; `local grille = array(20, 12)` donne la TAILLE et
  remplit de zéros. Écrire quatre cents zéros à la main n'est pas une option, et rien ne
  remplace un petit tableau posé en clair.
- **L'ordre des arguments d'`array` EST l'ordre des index.** `array(20, 12)` se lit
  `grille[1..20][1..12]` et devient `int grille[20][12]`. Aucun vocabulaire de largeur, de
  hauteur, de ligne ou de colonne n'entre dans la règle : les nommer obligerait l'auteur à se
  rappeler lequel des deux vient en premier, alors que la déclaration le lui montre déjà.
- **Les tableaux sont indexés à partir de 1**, comme partout en Lua. Le codegen émet
  `t[(i) - 1]`, replié à la compilation quand l'index est littéral. Le reste de l'API expose
  bien des index à partir de 0 (`save.write(0)`, les banques de palette) — mais ce sont des
  **numéros matériels**, pas des positions dans un conteneur du langage. Un script Lua dont le
  premier élément n'est pas `t[1]` serait un piège pour tout lecteur qui connaît Lua, et ce
  n'est pas un piège qu'on rattrape par de la documentation.
- **Un tableau ne contient que des entiers.** Le moteur n'a ni flottant ni chaîne manipulable ;
  un tableau de chaînes est refusé en nommant l'issue — une colonne `text` de l'asset table.
- **`#t` est une constante de compilation**, résolue en littéral. Pas de champ de longueur en
  RAM : la taille fait partie du type, donc elle est connue sans être rangée.
- **Pas de `for … in`, ni `ipairs`, ni `pairs`.** Le `for` numérique réparé plus `#t` couvrent
  le parcours entier. Un itérateur générique suppose des valeurs de première classe et un état
  d'itération, c'est-à-dire le début des tables Lua que la première décision écarte.
- **Le pas d'une boucle `for` s'écrit en clair.** C'est lui qui dit si la boucle monte ou
  descend, et la comparaison émise (`i <= stop` ou `i >= stop`) est décidée au build. Un pas
  calculé obligerait à tester son signe à chaque tour, dans un moteur qui ne teste rien
  ailleurs.
- ~~**Un tableau d'ÉTAT est refusé dans un prefab poolé**, en erreur qui nomme la variable.
  Les locals de tête d'un prefab poolé vivent dans `Actor.data[8]`, huit entiers par
  instance : un tableau n'y tient pas.~~ **Refus levé en v0.7.6** : `data[8]` a disparu au
  profit d'une structure dimensionnée par le pool, qui n'a plus de contrainte de type.

### v0.7.2 — L'asset table — **LIVRÉE**

Vérifiée par un build ROM complet, `build/` effacé, sur une copie de la démo qui porte une
table réelle : `data_tables.h/.c` émis, compilés et liés, la référence résolue en index.

```c
typedef struct { int prix; int nom; int rare; } DataRow_Objets;
const DataRow_Objets g_data_Objets[3] = {
    { 10, 4, 0 },   /* 1 : nom = potion_nom */
    { 50, 7, 1 },   /* 2 : nom = epee_nom */
    { 5, 0, 0 },    /* 3 : nom : aucune référence */
};
```

```c
for (int i = 1; i <= 3; i += 1) { total = (total + g_data_Objets[(i) - 1].prix); }
if (g_data_Objets[1].rare) { text_draw(8, 8, g_data_Objets[1].nom); }
```


Colonnes typées, lignes éditables, référençable depuis un script comme n'importe quel asset
nommé. Un fichier par table dans `project/data/`, avec les données propres au projet et non
dans `assets/` : une table ne dérive d'aucun fichier importé, comme une caméra ou une palette.

#### L'écran remplace le Tileset Manager

L'entrée « Tileset Manager » de la navigation était un **écriteau « coming soon »** —
`PlaceholderScreen`, zéro ligne de logique — et elle promettait un écran qui ne viendra pas :
le tileset comme asset de premier rang est sorti du périmètre en v0.4, « ce logiciel n'est pas
un outil de dessin ». Le Data Editor prend sa place, et l'écriteau disparaît avec sa classe.

Trois colonnes, comme Palette, Sprite et Texte : les tables du projet à gauche, la grille au
centre, la colonne et la cellule sélectionnées à droite.

- **Le schéma s'édite dans l'EN-TÊTE, les valeurs dans les cellules.** Deux objets d'édition
  dans un seul widget — les colonnes et les lignes — distingués par le geste et non par un
  mode à basculer. Double-clic sur l'en-tête pour renommer, menu contextuel pour le type.
- **Ce qui justifie l'écran contre le JSON, c'est la CELLULE TYPÉE.** Un entier a un champ
  numérique, un booléen une case à cocher, et une colonne de référence **une liste peuplée par
  le registre du projet**. Taper `potion_nom` à la main est une faute de frappe qui n'apparaît
  qu'au build ; le choisir dans une liste est impossible à rater. Le reste (aligner des
  colonnes, compter des virgules) n'est qu'un confort.
- **La grille montre la valeur, l'inspecteur montre ce qu'elle DÉSIGNE.** Afficher le contenu
  du texte à côté de sa clé, sur deux cents lignes, écraserait la grille et ferait dire à
  l'éditeur autre chose que ce que la donnée contient.
- **Le rang d'une ligne est la vérité, et il se voit.** L'en-tête vertical numérote à partir
  de 1 — l'index qu'un script écrit. Insérer au milieu décale ce qui suit : c'est le
  comportement voulu, pas un défaut à masquer par une identité de ligne qu'un script ne
  pourrait de toute façon pas nommer.
- **L'écriture passe par la grille, jamais par l'inspecteur**, qui se contente d'émettre. Un
  seul chemin d'écriture, donc un seul endroit qui pousse dans l'historique — même répartition
  que le Palette Editor. Ctrl+Z couvre la cellule, la ligne, la colonne et son type.
- **Ce n'est pas un tableur** : ni formule, ni tri, ni filtre. Un tri afficherait un ordre qui
  n'est pas celui des index.
- **Le JSON reste lisible et modifiable à la main.** Une ligne est un objet keyé par nom de
  colonne, jamais un tableau positionnel : réordonner les colonnes ne déplace aucune valeur,
  une clé absente reprend le défaut, et un diff git reste utile.

#### Décisions verrouillées

- **Le script y accède par indexation, pas par un appel** : `data.Objets[i].prix`. Le module
  `data` est l'espace de noms réservé des tables authorées. C'est ce qui fait qu'une table SE
  LIT comme un tableau — ce que la v0.7 promet — au lieu d'un `table.get("Objets", i, "prix")`
  qui n'aurait d'un tableau que le nom.
  - **Conséquence assumée, et c'est un vrai élargissement** : `scripting/refactor.py` ne savait
    repérer une référence que dans un ARGUMENT littéral d'appel, sa table de sites étant
    dérivée de `RUNTIME_API`. Un nom de table cité en `data.Objets` lui était invisible, et un
    renommage aurait laissé les scripts en arrière. Il a donc appris un **second type de site
    structurel** — la table ET la colonne — et le repérage reste ce qu'il a toujours été : de
    l'AST, jamais du texte. Un commentaire qui mentionne `data.Objets`, ou une chaîne qui le
    contient, ne bouge pas.
    - Un détail du matériel de luaparser a forcé une nuance : un noeud `Name` n'y porte
      **aucun offset** (`start_char` vaut `None`), seuls les noeuds `Index` en ont un, et leur
      tranche se termine par le nom cherché. L'arbre dit donc QUELLES occurrences sont des
      citations, et la réécriture relit la tranche source pour n'écrire que si elle finit bien
      par `.<nom>`. Repérage structurel, écriture vérifiée.
    - Trouvé au passage, et corrigé : `refactor.script_paths()` **oubliait les scripts de
      caméra** depuis leur apparition en v0.6.1. Un `scene.switch("Arène")` écrit dans une
      caméra n'était donc réécrit par aucun renommage de scène, et rien ne le disait — la
      faute ne remontait qu'au build suivant, sur un `SCENE_IDX_*` indéfini.
- **Le nom d'une table et de ses colonnes est un IDENTIFIANT**, pas un libellé libre : lettres,
  chiffres et `_`, sans commencer par un chiffre. C'est la contrepartie directe de la décision
  précédente — le script écrit ce nom comme du **code**, pas entre guillemets, donc « Objets
  rares » n'est pas renommable en un identifiant valide. Contrainte posée à la saisie, comme
  la clé d'une entrée de texte.
- **Une colonne de référence déclare un DOMAINE**, et hérite gratuitement des trois
  consommateurs qui en dépendent déjà : le checker (ce nom existe-t-il ?), le codegen (quelle
  constante C émettre ?) et le refactor (suivre le renommage). Aucune mécanique nouvelle —
  c'est la règle « un domaine a trois consommateurs » appliquée à une donnée au lieu d'un
  argument.
- **Sont admis les domaines que le runtime sait déjà INDEXER** : `text`, `sfx`, `music`,
  `scene`, `camera`, `font`, `palette`, `region`, `image`. Chacun est déjà un `#define NOM i`
  qui désigne une entrée d'une table en ROM ; une colonne de ce type EST cet entier, et ne
  coûte rien de plus.
- **Sont refusés `sprite` et `prefab`, et la raison n'est pas la même.**
  - `sprite` (et `anim`, `actor`) : il n'existe aucune table indexée de sprites en ROM, et
    aucune fonction de l'API ne prend un sprite par numéro. La colonne rendrait un entier que
    rien ne peut consommer — une référence qui ne référence pas.
  - `prefab` : `actor.spawn("X")` se résout en `spawn_X(x, y)`, une FONCTION, pas un index.
    Une colonne de prefabs suppose donc un `spawn_by_id(int, x, y)` et son aiguillage généré,
    c'est-à-dire une petite fonctionnalité de runtime à part entière. Elle est utile — « cette
    ligne d'ennemi fait apparaître ce prefab » — et elle est nommée en « Ouvert » avec son
    coût, plutôt que bâclée dans le même passage.
- **Le registre ENTIER part en ROM**, sans dérivation depuis les scripts. Même raisonnement
  qu'en v0.4.2 pour le catalogue de palettes : la donnée est en ROM, qui est large, alors que
  la dérivation ferait courir le risque de sous-réserver — un risque qui n'a de sens que pour
  la mémoire vidéo. Ce que ça coûte est visible et proportionnel : une ligne de six colonnes
  pèse ses six entiers.
- **Émise en tableau de structs**, un `typedef` par table, dans un `data_tables.h` / `.c`
  générés. `data.Objets[i].prix` devient `g_table_Objets[(i) - 1].prix` : le C se relit avec
  les mêmes mots que le Lua. Un tableau par colonne (structure de tableaux) serait plus rapide
  sur un parcours d'une seule colonne, et illisible partout ailleurs.
- **Une table authorée refuse l'écriture, au build**, en nommant la table et la colonne. Elle
  est `const` en ROM : l'écriture ne serait pas seulement inefficace, elle ne compilerait pas —
  autant le dire sur la ligne Lua fautive que sur la ligne générée.
- **Une table n'est PAS un domaine de script**, malgré l'apparence. La mécanique de domaine
  dérive de `RUNTIME_API.params`, et une table n'apparaît jamais comme argument littéral d'un
  appel : lui inventer un `DOMAIN_TABLE` obligerait à le déclarer « traité ailleurs » des deux
  côtés du contrôle de couverture, pour un `Param` qui n'existe pas. Le checker et le codegen
  reçoivent donc directement `{nom: (colonnes, lignes)}`. Ce sont les **colonnes de référence**
  qui portent un domaine, côté donnée et non côté argument — et c'est
  `validator._check_data_column_types` qui tient les trois listes d'accord.
- **Trois erreurs bloquantes plutôt qu'un 0 plausible** : table inconnue, colonne inconnue,
  rang hors bornes écrit en clair. Et côté données, une référence qui ne résout pas bloque
  aussi : elle serait émise en 0, c'est-à-dire la PREMIÈRE entrée de la table citée — une
  valeur crédible et fausse, exactement la dégradation silencieuse refusée depuis la v0.2.

### v0.7.3 — vec2/vec3 dans le langage — **LIVRÉE**

Vérifiée par un build ROM complet, `build/` effacé, sur la démo Pong migrée à la nouvelle API :
`checker.py`/`codegen.py` compilent, `arm-none-eabi-gcc -Wall` ne signale rien, `rom.gba` sort.

```lua
local pos = self.position
local vel = self.velocity + input.axis
self.velocity = vel
self.position = pos + vel
```

```c
Vec2 pos = actor_get_position(self);
Vec2 vel = vec2_add(actor_get_velocity(self), input_get_axis());
actor_set_velocity(self, vel);
actor_set_position(self, vec2_add(pos, vel));
```

*(Ce chapitre a d'abord été livré avec des appels `self:get_position()` /
`self:set_velocity(v)`. La v0.7.4 en a fait des PROPRIÉTÉS le lendemain : le C émis est
resté le même, seule la forme Lua a changé. L'exemple ci-dessus est la forme courante —
l'ancienne est refusée par le checker.)*

`vec2(x, y)` / `vec3(x, y, z)` sont la SEULE exception au « sous-ensemble Lua entièrement
scalaire » posé en tête de ce chapitre (`parser.py` n'en sait toujours rien : ce sont
`checker.py`/`codegen.py`, via le module partagé `scripting/vec_types.py`, qui reconnaissent
et valident ces deux constructeurs — pas un troisième type de nœud AST).

- **Position, vélocité, l'axe d'input et le déplacement ponctuel passent en vec2** —
  `self.position`, `self.velocity`, `self:add_velocity(dv)`, `input.axis`, puis
  `self:move(dir, speed)` et `self:move_to(target, speed)` (une direction et un point du
  monde sont des vecteurs). Les anciens `self:get_x/get_y/get_vx/get_vy` et
  `input.get_horizontal_axis/get_vertical_axis` sont retirés (message guidé dans
  `REMOVED_API`, pas juste un « méthode inconnue ») : deux scalaires toujours lus et écrits
  ensemble sont un seul concept, pas deux appels à garder synchrones à la main.
  `actor.spawn("prefab", position)` prend un nom scalaire et une position en vec2.
- **`+`, `-` et `*` (par un entier), rien de plus.** Pas de comparaison, pas de produit
  vectoriel, pas de mélange vec2/vec3 dans une même opération — `checker.py` bloque les quatre
  à la ligne fautive plutôt que de laisser gcc les découvrir sur le C généré. Le C n'a pas
  d'opérateur sur les structs : `vec2_add`/`vec2_sub`/`vec2_scale` (et leur vec3) vivent dans
  `actor_api_static.h`, `+`/`-`/`*` Lua s'y traduisent.
- **Deux entiers/trois entiers, jamais de virgule flottante** — `Vec2`/`Vec3` dans
  `actor_types_static.h` sont des structs `int`, comme tout le reste du moteur.
- ~~**Un vec2/vec3 d'ÉTAT est refusé dans un prefab poolé**, même raison et même erreur
  nommée que pour un tableau (v0.7.1).~~ **Refus levé en v0.7.6**, en même temps que celui
  du tableau et pour la même raison.
- **vec3 sert dès maintenant à la couleur** (RVB) et servira de socle aux transforms de la v3
  (3D) — aucune des deux n'a encore d'entrée `RUNTIME_API` qui RETOURNE un vec3 (`palette.*`
  reste un échange de banque, pas une composante RVB adressable). Le type est prêt, l'API
  couleur reste à ouvrir sur son premier vrai besoin.

### v0.7.4 — Les propriétés : l'état s'écrit comme un champ — **LIVRÉE**

Vérifiée par `pytest tests` (48 cas nouveaux, `tests/test_scripting_api.py`) et par une sonde
compilée sur les VRAIS en-têtes du runtime avec l'`actor_types.h` généré de Pong : une unité
d'acteur qui n'inclut que `actor_api.h` refusait `WINR_0`/`BLD_SIDE_TOP`/`BLD_MODE_*` avant,
compile `-Wall -Wextra` sans un mot après — de même que le C émis pour les nouvelles
propriétés — et main.c voyant les deux en-têtes ne signale aucune redéfinition. **Pas de build
ROM complet sur ce jalon-ci** — le C émis est identique à celui de la v0.7.3 sur toute la démo
Pong, qui n'écrit ni window, ni mélange, ni direction nommée.

La v0.7.3 a rendu `self:get_position()` symétrique de `self:set_position(p)` — et ce faisant,
a rendu visible que la paire elle-même était de trop. Une position n'est pas une opération :
c'est un ÉTAT, et un état se lit et s'écrit comme un champ.

```lua
self.position = self.position + self.velocity   -- au lieu de self:set_position(...)
self.flip_h   = self.direction.x < 0
if not self.active then return end
camera.bound  = rect(0, 0, 512, 256)
```

**La grammaire est réglée par la FORME, pas par le goût** — c'est elle qui dit au parseur quoi
produire (`Invoke` pour `:`, `Index` pour `.`), donc qui décide de la résolution. Le tableau
des trois formes et la règle de décision complète vivent dans
[ARCHITECTURE](ARCHITECTURE.md#la-grammaire-de-lapi--trois-formes-une-par-nature) ; en une
ligne : **état → propriété, requête pure sans argument → propriété en lecture seule, requête
indexée → fonction, action → méthode ou fonction de module.**

#### Décisions verrouillées

- **Une valeur composée est IMMUABLE.** `self.position.x` se lit, `self.position = vec2(x, y)`
  s'écrit, `self.position.x = 5` est refusé par le checker. Écrire un champ supposerait que le
  getter rende une référence ; il rend une copie, et l'écriture partirait dans le vide.
- **Une propriété d'actor s'accède sur N'IMPORTE QUEL acteur nommé** — `other.velocity`,
  `get_actor("PADDLE").position`. Le catalogue les range sous `self.<champ>` : c'est une clé,
  pas une restriction (`vec_types.resolve_prop`). Les MÉTHODES sont logées à la même enseigne,
  et le checker les valide désormais sur tous les récepteurs — cf. le piège ci-dessous.
- **Une propriété peut porter une énumération matérielle** (`ApiProp.domain`), donc s'écrire
  ET se comparer par un nom : `self.obj_mode = "window"`, `if blend.mode == "alpha"`. Sans ce
  champ, faire d'un réglage une propriété le faisait retomber sur l'entier nu que les
  énumérations nommées (v0.6) existent pour supprimer. Le C ne change pas : `OBJ_MODE_WINDOW`
  vaut toujours 2.
- **Le C émis est identique à celui des anciens get/set.** Une propriété n'est pas une couche :
  `c_getter`/`c_setter` nomment les mêmes fonctions `actor_*` qu'avant. Seule la forme Lua
  change — donc aucun coût sur la ROM, et rien à re-mesurer.
- **`scene.size` est la seule propriété sans fonction C** : sa lecture est synthétisée depuis
  `g_scene_w`/`g_scene_h` (`getter_expr`). Une fonction pour deux globaux constants dans la
  scène aurait été du bruit.

#### Trois pièges, et ce qui les tient

- **Retirer une API ne suffit pas à la retirer.** `codegen._invoke` traduit toute méthode
  inconnue en `actor_<méthode>(récepteur, ...)` — qui tombait pile sur la fonction C encore
  présente. `self:set_frame(0)` ne produisait donc qu'un avertissement NON bloquant et
  continuait de marcher, non documenté, à côté de `self.frame = 0` : deux grammaires vivantes
  pour le même état. Corrigé par les entrées `REMOVED_API` manquantes **et** par le passage de
  « méthode inconnue » en ERREUR — un `:` ne peut désigner qu'une méthode du catalogue,
  contrairement à `module.func()` qui peut être un helper de l'utilisateur.
- **Ne valider que `self` laissait tout passer.** `other:set_position(p)` traversait sans un
  mot, alors que le codegen en émettait du C qui compile. Le checker valide maintenant tous les
  récepteurs. Seule exception, bloquée explicitement : un argument dont le nom appartient au
  sprite du RÉCEPTEUR (`other:play_anim("walk")`) — le contexte de build décrit l'acteur qui
  *exécute*, et le codegen résolvait le nom contre lui, produisant une constante crédible et
  fausse.
- **Les CONSTANTES tombent dans le trou des « deux listes de prototypes »**, pas seulement les
  fonctions. `WINR_*`, `BLD_MODE_*` et `BLD_SIDE_*` n'étaient définies que dans `gba_engine.h`,
  que les unités de scène et d'acteur n'incluent pas : tout `window.set_layer` ou
  `blend.set_layer` écrit depuis un script échouait au `make` sur un identifiant inconnu.
  Elles sont déclarées des deux côtés, et `validator._check_api_prototypes` compare maintenant
  les constantes comme les prototypes, dérivées de `HARDWARE_ENUMS`.

#### Ce que la règle a fini par emporter

Appliquer la grammaire à tout le catalogue a fait tomber trois choses qui traînaient. Aucune
n'était un renommage.

- **La direction s'écrivait TROIS fois** pour un seul couple `dir_x`/`dir_y` : `self.direction`
  (vec2), `self:set_dir("north")`, et `self:get_dir()` rendant un 0-8 nu — on la posait par un
  nom et on la relisait en nombre. Il n'en reste qu'une, et elle accepte les deux écritures :
  `self.direction = "north_east"` comme `self.direction = vec2(1, -1)`, et la comparaison suit
  (`if self.direction == "west"`). C'est ce qui a demandé `ApiProp.c_getter_named` /
  `c_setter_named` : le C ne range qu'une donnée, mais les deux vues n'y accèdent pas par la
  même porte (`actor_set_dir` prend un index de boussole, `actor_set_direction` un `Vec2`) — et
  le getter ordinaire rend un `Vec2`, que le C ne sait pas comparer du tout. Restent
  `self.auto_dir` (setter d'état sans getter : la lecture n'existait pas, un script qui voulait
  basculer le calcul automatique devait tenir son propre drapeau) et `self.grounded`, requête
  pure sans argument — renommée au passage, `on_` étant le préfixe des ÉVÉNEMENTS.
- **`ui.image_set(image, state)` : `state` n'avait pas de domaine**, donc n'était ni vérifié ni
  suivi par `refactor`, contrairement à la règle posée en tête d'`api.py`. Le blocage était
  réel : un état n'existe que DANS un sprite, et c'est l'IMAGE qui dit lequel — la validité
  dépend d'un AUTRE argument. Résolu en donnant à la table de contrôle l'appel entier et non le
  seul littéral. `DOMAIN_IMAGE_STATE` est le premier domaine de cette nature ; un futur
  renommage d'état passera par `refactor.iter_call_sites(DOMAIN_IMAGE, DOMAIN_IMAGE_STATE)`,
  qui rend la PAIRE et permet de ne toucher que les images du bon sprite.
- **`self.tag` était inutilisable.** Sa doc disait « utile dans `on_collide` pour identifier
  `other` » sans dire comment : elle rendait un entier opaque qu'aucune écriture Lua ne
  permettait de nommer. `DOMAIN_TAG` existait pourtant — déclaré, résolu par le codegen, cité
  par aucun paramètre, et rangé parmi les domaines NON validés au motif que `TAG_*` serait un
  espace ouvert. C'était faux : `TAG_*` est émis une fois par acteur de scène et par prefab
  poolé (`headers.py`), donc parfaitement énumérable. La confusion venait de `BOXTAG_*`, lui
  bel et bien libre puisqu'il sort du champ texte `CollisionBoxComponent.tag`. `self.tag` porte
  donc le domaine, se compare par le nom (`if other.tag == "Ball"` → `actor_get_tag(other) ==
  TAG_BALL`), et un nom inconnu est refusé. Au passage, le domaine d'une propriété passe par
  les MÊMES tables que celui d'un paramètre (`_DOMAIN_CHECKS`, `_DOMAIN_CONSTANT`) au lieu de
  ne connaître que `HARDWARE_ENUMS` : c'est le domaine qui décide, pas ce qui le porte.
- **L'écran de référence avait perdu son ordre et ses catégories.** 24 des 91 entrées
  d'`api_reference.json` décrivaient une API retirée. La réconciliation les filtrait — mais une
  catégorie entièrement vidée disparaissait puis se recréait EN FIN de liste (« Transform »,
  première du fichier, s'affichait avant-dernière), et sept fonctions tombaient dans « Autres »
  faute de catégorie. Le JSON est purgé, « Interface » et « Palette » existent, « Communication »
  (qui ne contenait plus que `get_actor` depuis le retrait de `send`/`broadcast`) est repliée
  sur « Actor », et deux règles ont changé dans `api_reference.py` : le RANGEMENT s'apprend de
  toutes les entrées, mortes comprises — un `scene.frame()` périmé dit encore que le module
  `scene` habite « Scène », et c'est faute de l'écouter que `scene.switch` finissait en vrac —
  et une catégorie garde sa PLACE, n'étant retirée qu'à la toute fin si rien ne l'a remplie.

### v0.7.5 — Le sous-ensemble Lua, dit et tenu — **LIVRÉE**

Vérifiée par un build ROM complet sur une copie de la démo, `build\` effacé : les six scripts
passent le checker sans une erreur, `arm-none-eabi-gcc -Wall` ne signale rien, `rom.gba` sort.
Et par 41 tests qui figent chacun des silences ci-dessous.

Les quatre versions précédentes ont ÉTENDU le langage. Celle-ci ne lui ajoute rien : elle dit
ce qu'il est, et fait en sorte qu'il le tienne. Le déclencheur tient en un tableau — voici ce
que produisait du Lua parfaitement légal, écrit par quelqu'un qui connaît Lua :

| Écrit en Lua | Ce que le checker disait | Ce qui partait dans le C |
| --- | --- | --- |
| `for k, v in pairs(t) do … end` | rien | **rien — le bloc disparaît** |
| `repeat … until n == 0` | rien | **rien — le bloc disparaît** |
| `goto fin` / `::fin::` | rien | **rien** |
| `"a" .. "b"` | rien | `__unsupported_Concat` |
| `local f = function() … end` | rien | `__unsupported_AnonymousFunction` |
| `math.floor(3.7)` | rien | `math.floor(3)` |
| `print(n)` | rien | `print(n)` |
| `table.insert(t, 1)` | rien | `table.insert(t, 1)` |

Les cinq dernières lignes échouent au `make`, sur la ligne générée et jamais sur sa cause.
Les trois premières ne disent **rien du tout** : le corps de boucle est simplement absent du
jeu. C'est la même famille de panne que le `for` numérique inversé qui a ouvert la v0.7 — un
silence, pas une erreur — et elle vient de deux lignes de `parser.py` : `_stmt` rend `None`
pour tout nœud non géré (le commentaire dit « silencieux en v1 »), `_expr` rend
`ExprName("__unsupported_<Type>")`.

Un piège de plus, celui-là dû au succès de l'API : **`math` existe, mais ce n'est pas celui
de Lua**. Le catalogue offre `abs, atan2, clamp, cos, ease, lerp, max, min, rand, sign, sin,
sqrt` — donc pas de `floor` (le moteur est entier, il n'y a rien à arrondir), pas de `random`
(c'est `rand`), pas de `pi`, et `sin`/`cos` prennent des **degrés**. Un module de la
bibliothèque standard dont le nom est repris et le contenu différent est le pire cas
possible : celui où l'auteur a raison de ne pas vérifier.

#### Décisions verrouillées

- **Une seule table décrit le sous-ensemble** — `scripting/lua_subset.py`. Chaque type de
  nœud de luaparser y est soit ACCEPTÉ (en nommant ce qui le traduit), soit REFUSÉ avec la
  phrase qui dit quoi écrire à la place. La documentation en dérive et le checker s'en sert :
  les deux ne peuvent pas diverger, parce qu'il n'y a pas deux listes.
- **Le contrôle de couverture casse le build**, comme celui des domaines d'arguments
  (`validator._check_api_domains`) et pour la même raison exactement : un nœud que luaparser
  ajouterait à la faveur d'une mise à jour retomberait sinon dans le trou silencieux qu'on
  vient de boucher. Classer un nœud fait partie de l'ajout, ce n'est pas une formalité.
- **Un refus est une ERREUR bloquante, située sur sa ligne.** Pas un avertissement : un
  `repeat` ignoré ne se rattrape pas en jouant, et une expression traduite en
  `__unsupported_Concat` ne compile de toute façon pas.
- **Le parser décrit, le checker juge.** Le convertisseur porte le nœud non géré (son nom,
  sa ligne) au lieu de le perdre ; la phrase, elle, vit dans la table et se dit dans le
  checker. Même contrat que `ExprTable.has_keys`, écrit dans `parser.py` depuis la v0.7.1 :
  « le parser décrit ce qui est écrit, il ne juge pas ».
- **Un appel inconnu est refusé**, alors qu'il était toléré au motif que ce pouvait être un
  helper écrit par l'utilisateur. Ce motif ne tenait pas : le codegen émettait quand même
  l'appel tel quel, donc `math.floor(x)` partait en C avec son point. Les seuls appels
  légitimes sont ceux du catalogue, les constructeurs du langage (`vec2`, `vec3`, `rect`,
  `array`), `require`, et les méthodes d'un behavior importé — tout le reste est une faute de
  frappe ou une fonction de Lua qui n'existe pas ici. C'est le pendant, côté `.`, de ce que la
  v0.7.4 a fait pour le `:` (une méthode inconnue est une erreur, pas un avertissement).
- **La bibliothèque standard est nommée, pas seulement absente.** `print`, `pairs`, `ipairs`,
  `tostring`, `table.*`, `string.*`, `os.*`, `io.*`, `math.floor`… reçoivent chacun le message
  qui dit l'issue quand il y en a une (`math.floor` → il n'y a que des entiers ; `print` → le
  débogage est le sujet de la v0.14 ; `table.insert` → un tableau a une taille fixe, v0.7.1) et
  qui dit clairement « non » quand il n'y en a pas. Un « fonction inconnue » générique
  laisserait croire à une faute de frappe.
- **Le document est écrit à la main, ses listes sont vérifiées.** `SCRIPTING.md` rejoint les
  trois documents en tête de ce fichier ; il s'adresse à qui ÉCRIT un script, là où
  `ARCHITECTURE` s'adresse à qui modifie le compilateur. Un test échoue si un refus de la
  table n'y est pas documenté — la prose reste écrite, mais elle ne peut pas prendre du
  retard.
- **Rien de nouveau dans le langage.** Ni concaténation, ni closure, ni table Lua, ni
  coroutine, ni `goto` : cette version ne fait que dire pourquoi. Chaque « pourquoi » existe
  déjà et n'est pas rouvert ici — les tables (v0.7.1), les chaînes manipulables (v0.3.2 : le
  texte vit dans la table de textes, pas dans le script), les flottants (le moteur est
  entièrement entier).

#### Ce que la règle a fait tomber

Dire ce que le langage accepte a obligé à le REGARDER, et quatre choses sont tombées.

- **Le template de behavior que l'éditeur écrit lui-même ne passait pas son propre checker.**
  `local M = {}` était lu comme un tableau raté — « un tableau vide n'a pas de taille, écris
  `array(n)` » — et le codegen émettait un `static int M = 0;` que personne ne lit. La table
  de module est désormais une FORME, reconnue sur ses deux bouts (`local M = {}` ET
  `function M.f(…)`) : elle ne produit rien en C. Exiger les deux évite de prendre pour un
  module un `local t = {}` que l'auteur voulait tableau — celui-là reste refusé, avec la
  phrase qui dit `array(n)`. Au passage, les appels `M.f(…)` sont validés contre les
  fonctions du module : `M.aid` au lieu de `M.aide` est refusé.
- **La liste des opérateurs traduits était une RUSE, pas une liste** : « le nom du nœud
  luaparser finit par `Op` ». `^`, `//`, `&`, `|`, `<<`, `>>` la passaient, et leur nom de
  classe partait tel quel dans le C — `(a ExpoOp b)`. Deux tables explicites la remplacent
  (`_BINOP_MAP`, `_UNOP_MAP`), et ce sont elles que `lua_subset` complète. Elles portaient
  aussi `EqOp` et `NotEqOp`, qui n'ont jamais existé chez luaparser (c'est `EqToOp` /
  `NotEqToOp`) : deux entrées mortes depuis l'origine, à côté des vivantes.
- **Une fonction de premier niveau au nom inconnu n'était qu'un avertissement**, alors que le
  C émis (`static void <Acteur>_<nom>(Actor* self)`) n'est atteignable par aucun appel Lua —
  `nom()` s'émet `nom()`, sans le préfixe. Donc du code mort au mieux, un « implicit
  declaration » au `make` au pire. C'est une erreur, et le message nomme le behavior.
- **La reconnaissance de `require` était écrite trois fois** dans `codegen.py`, dont une dans
  un `_scan_requires` que plus rien n'appelait. Elle vit maintenant dans
  `parser.require_target`, à côté d'`array_dims` et pour la raison que ce fichier écrit
  déjà : la FORME se reconnaît là où on lit l'AST, et ses consommateurs l'appellent. Le
  checker en est un nouveau — sans lui, refuser les appels inconnus aurait refusé
  `IA.update(self)`.

#### Ouvert

- **Le code posé hors de tout handler reste ignoré en silence.** `convert_chunk` ne retient
  que les fonctions, les `local` et la table `exports` : un `sfx.play("Bip")` écrit en tête
  de fichier ne s'exécute jamais et ne dit rien. Le refuser demande de juger une POSITION et
  non un nœud — la fonction imbriquée est le seul cas déjà traité ainsi — et de continuer à
  laisser passer le `return M` d'un behavior. C'est le même silence que celui-ci, à un autre
  étage, et il mérite son propre passage.
- **Les opérateurs binaires sont refusés faute de demande, pas faute de moyen.** `&`, `|`,
  `~`, `<<`, `>>` se traduiraient terme à terme. Aucun cas ne les a réclamés, et les ajouter
  aurait fait de cette version une extension du langage, qu'elle n'est pas. À rouvrir sur un
  besoin réel.
- **Un refus qui vient d'un APPEL ne porte pas sa ligne** (`math.floor`, `print`), là où un
  refus de nœud la porte. `ExprCall` n'a pas d'offset dans notre AST : le lui donner
  situerait du même coup toutes les erreurs d'API, qui n'en ont jamais eu — un gain réel, et
  un chantier à lui.
- **La sidebar du Script Editor ne montre toujours que l'API, pas le LANGAGE.** Une section
  « Langage » qui proposerait `if`, `for`, `local`, `array(n)` au clic est possible et pas
  décidée : la sidebar sert à INSÉRER ce qu'on ne connaît pas par cœur, et `if … then` n'est
  pas de cette famille. À rouvrir si les refus mesurés portent surtout sur la syntaxe.
- **Les 67 `doc_anchor` d'`api_reference.json` ne mènent nulle part**, et le tooltip promet
  encore « doc (bientôt disponible) ». `SCRIPTING.md` documente le LANGAGE, pas chaque
  fonction du catalogue — la promesse reste donc à tenir ou à retirer, et ce n'est pas le même
  chantier.
- **Le checker ne tourne pas pendant qu'on écrit.** Un refus n'apparaît qu'au build, dans le
  `BuildPanel`. Le faire vivre dans la marge de l'éditeur est un vrai gain et une vraie
  mécanique (relance temporisée, position des erreurs) : à traiter avec le diagnostic de la
  v0.14, pas à côté.

### v0.7.6 — L'état d'un prefab poolé — **LIVRÉE**

Un prefab poolé rangeait les variables de tête de son script dans `Actor.data[8]`
: huit entiers par instance. Ce choix avait produit **trois refus et un piège**, et le
prochain chantier en ajouterait un quatrième — c'est ce qui l'a rouvert.

| Ce qui était refusé dans un prefab poolé | Depuis |
| --- | --- |
| un tableau d'état | v0.7.1 |
| un vec2/vec3 d'état | v0.7.3 |
| l'état d'une séquence | ce serait la v0.7.7 |

Le piège, lui, était silencieux : dans `codegen._emit_locals`, une string ou un composite d'un
prefab poolé **retombait sur une déclaration de fichier**, donc partagée par toutes les
instances. Le commentaire l'assumait — « sans danger : ce sont des constantes d'initialisation »
— et c'était vrai tant que personne n'y écrivait. Le jour où un script écrit dedans, les vingt
instances partagent une variable, sans un mot.

Et `data[8]` coûtait à **tout le monde** : le champ était dans chaque `Actor`, poolé ou pas. Un
acteur de scène range ses locals dans des statiques de fichier et n'y touchait jamais — il
payait 32 octets pour rien, multipliés par la taille de `g_actors[]`.

#### Le remplacement existe déjà, pour un autre usage

Les pools sont des **plages contiguës connues au build** — `for(int _pi=START; _pi<START+N;
_pi++)` — et `main_gen.py:2428` émet déjà, pour la mémoire de collision d'un prefab poolé,
un `static u8 _pcol_<sym>[N][boxes]` indexé par `_sl = _pi - START`. Un état par slot,
dimensionné par le pool, alloué au build : exactement ce qu'il faut pour les locals.

On fait donc pour l'état de script ce que le C généré fait déjà pour l'état de collision :

```c
static struct { int pv; Vec2 vitesse; int trajet[8]; } g_state_Ball[16];
```

#### Décisions verrouillées

- **Un champ par local, du type que le local demande.** Plus de plafond à huit entiers, plus
  de refus : un tableau, un vec2, une string d'état deviennent possibles parce qu'il n'y a
  plus de case de taille fixe où les faire entrer.
- **L'index est une soustraction de pointeurs** : `self - &g_actors[START_Ball]`, la plage
  étant une constante de build. Pas de champ à ranger dans l'`Actor`, pas de recherche.
- **`pool_init` garde son rôle** exact (remettre l'état à zéro au spawn) et son point
  d'appel ; seule la cible change.
- **`data[8]` disparaît de la struct `Actor`.** Il n'est ni sérialisé dans la sauvegarde, ni
  exposé en Lua, ni lu par le runtime : il n'appartient qu'au transpileur, ce qui rend le
  retrait contenu — `parser`/`checker`/`codegen`, plus l'appel de `pool_init`.
- **Seul ce que le script ÉCRIT est de l'état.** Un local de tête jamais assigné est une
  constante — `local FX_POP = 1` — et reste une déclaration de fichier, partagée par toutes
  les instances comme aujourd'hui. Sur `Ball.lua`, quatre des six locals sont de ce genre :
  les recopier par instance à chaque spawn ferait payer seize fois une valeur qui ne bouge
  jamais, et ferait surtout **mentir la mesure** ci-dessous, qui n'annoncerait plus l'état
  mais la longueur de l'en-tête du fichier. La règle se dit sans parler du C : *ce qui change
  appartient à l'instance, ce qui ne change pas appartient au prefab.*
- **La mesure, pas de garde-fou.** Le build dit, par prefab poolé, ce que son état coûte
  (`Ball : 8 octets × 16 = 128`) et le total. Rien ne bloque. Le garde-fou bloquant de la
  v0.2 protège la mémoire **vidéo**, qui est rare et dont le dépassement est *impossible* à
  satisfaire ; ici la ressource est l'EWRAM (256 Kio) et le dépassement est un arbitrage —
  bloquer demanderait un plafond arbitraire, c'est-à-dire exactement le `data[8]` qu'on
  retire. Un chiffre juste vaut mieux qu'une limite inventée. À rouvrir le jour où un projet
  réel s'en approche, avec son chiffre à lui.
- **Le refus des tableaux et des vec2 d'état DISPARAÎT** — les deux messages du checker,
  `BuildContext.is_pooled` qui n'existait que pour eux, et la mention dans `ARCHITECTURE.md`.
  Laisser une règle debout après avoir retiré sa raison d'être, c'est laisser mentir la
  documentation.

#### Ce que le C émis donne, mesuré

Les bornes du pool sont deux `#define` émis par `headers.py` là où l'offset est déjà
calculé (`POOL_<SYM>_START`, `POOL_<SYM>_SIZE`) : le script transpilé est compilé une fois
pour le PROJET et ne peut pas les connaître autrement. Le tableau d'état se dimensionne
**sur le `#define`**, jamais sur un littéral recalculé — un écart avec la boucle de pool de
`main.c` serait un débordement muet.

```c
/* Constantes du script — jamais assignées, donc partagées par toutes les instances */
static int FX_NONE = 0;
static int FX_POP = 1;

/* État par instance — un champ par variable de tête que le script
   écrit. 8 octets × 1 instance(s) = 8 octets. */
typedef struct { int fx; int fx_t; } BallState;
static BallState g_state_Ball[POOL_BALL_SIZE];
static inline int Ball_pool_slot(Actor* self) { return (int)(self - g_actors) - POOL_BALL_START; }

void Ball_pool_init(Actor* self) {
    BallState* _st = &g_state_Ball[Ball_pool_slot(self)];
    *_st = (BallState){ .fx = FX_POP, .fx_t = 0 };
}
```

**Le slot est résolu une fois par fonction**, dans un `_st` posé en tête, et non réécrit à
chaque accès — cf. « Le pointeur d'état » en fin de v0.7.7, où la mesure a été faite.

Deux chiffres relevés au build, pas estimés. Sur la démo Pong telle quelle : `Ball` déclare
six variables de tête, dont **deux seulement sont écrites** — son état pèse 8 octets là où
`data[8]` en réservait 32, et les quatre `FX_*` sont sorties de l'instance. Sur une copie
dont le pool est porté à 8 et dont le script gagne les trois types autrefois refusés
(`array(4)`, `vec2`, string d'état) : 36 octets × 8 = 288 octets, ROM construite sans un
warning. S'y ajoute la disparition de `data[8]` de la struct `Actor`, soit 32 octets rendus
par acteur du projet, poolé ou non.

- **`pool_init` pose un littéral composé, pas un `static const` de fichier.** Écrit
  d'abord en `static const BallState BallState_init = { .fx = FX_POP, … }`, le build a
  refusé : en C l'initialiseur d'un objet statique doit être une constante, et `FX_POP` est
  une variable. Le littéral composé est en portée bloc, il n'a pas cette contrainte — et il
  garde la propriété qui comptait, **une seule affectation**, la seule forme qui
  réinitialise aussi un tableau et un vec2. Défaut attrapé par le build de bout en bout, pas
  par les tests unitaires : la raison même pour laquelle il est fait.

#### Ouvert

- **La distinction écrit/constant ne descend pas dans les behaviors inlinés.** Un behavior
  dont une variable porte par hasard le nom d'un local de tête de son hôte verrait sa
  référence réécrite vers l'état de l'hôte. Le défaut est **antérieur** à ce chantier
  (`_expr` faisait déjà la substitution sur `self->data[N]`, avec en prime un `self` qui
  n'est pas forcément le nom du premier paramètre du behavior) et n'a pas été élargi. À
  traiter avec la portée des behaviors, pas ici.

---

### v0.7.7 — Les séquences — écrire une attente en ligne droite — **LIVRÉE**

Aujourd'hui, une scène scénarisée s'écrit en machine à états à la main : un `etape`, un
compteur, et une chaîne de `elseif`. Le moteur a pourtant déjà tout ce qu'il faut pour la
partie difficile — `self:move_to`, `camera.shake(amp, frames)`, `text.reading(zone)`,
`math.ease` — mais **rien ne les enchaîne**. Le séquencement est du script (décision v0.3.2,
« pas d'éditeur de dialogue »), et c'est l'écriture de ce séquencement qui est pénible.

```lua
function on_sequence()
    self:move_to(vec2(120, 80), 60)
    wait_until(self.position.x >= 120)
    wait(30)
    text.draw_in("bulle", "garde_01")
    wait_until(not text.reading("bulle"))
    scene.switch("Arena")
end
```

Le C émis fait la même chose, à la frame près, que les quatre `elseif` qu'on écrit
aujourd'hui. **Cette version n'ajoute aucune capacité** — elle ajoute de la lisibilité, comme
la v0.7.4 l'a fait pour les propriétés (« le C émis est identique, seule la forme Lua
change »). Décidé le 2026-08-16 de la faire quand même, sans attendre un cas réel : l'outil
est assez courant dans les moteurs pour qu'un utilisateur le cherche.

#### Décisions verrouillées

- **Une séquence est un HANDLER NOMMÉ, pas un mot-clé.** Le front-end est luaparser : la
  source doit rester du Lua syntaxiquement valide, donc `wait(30)` est un appel ordinaire et
  une séquence est une fonction de premier niveau. Cette contrainte n'est pas négociable, et
  c'est elle qui dessine la forme.
- **La transformation est faite au BUILD** : le handler est découpé à chaque attente et émis
  en `switch (état)`. Pas de pile, pas d'objet de première classe, pas d'allocation — juste un
  entier d'état et les locals qui traversent une attente. C'est ce que font les itérateurs C#
  et les coroutines d'Unity, et c'est possible ici précisément parce qu'`on_update` rend déjà
  la main à chaque frame.
- **L'ensemble des séquences est connu au build.** Rien n'en crée à l'exécution : c'est le
  seul refus vraiment structurel de la vraie coroutine de Lua, et il vient du modèle mémoire
  du projet — décidé au build, donc mesurable avant de graver.
- **Plusieurs séquences peuvent tourner en même temps**, tant qu'elles sont déclarées. Ce
  n'est pas un ordonnancement : ce sont N machines à états appelées dans l'ordre où elles sont
  écrites, exactement comme les acteurs le sont déjà dans la boucle de frame — laquelle est
  une liste d'appels directs déroulée au build (`main_gen.py:2386`), sans le moindre
  ordonnanceur.
- **Aucune priorité, aucune préemption.** C'est là que commencerait un vrai ordonnanceur, et
  le refus n'est pas une question de coût : aujourd'hui l'ordre d'une frame se lit en clair
  dans le `main.c` généré. Une politique de priorités serait le premier endroit du moteur où
  l'ordre d'exécution est décidé ailleurs que là où on l'écrit.
- **La sémantique diffère de Lua, et c'est assumé.** `wait_until(cond)` ré-évalue son
  argument à chaque frame là où Lua l'évaluerait une fois, à l'appel. Le principe posé le
  2026-08-16 : *le matériel impose ses conditions, le langage suit* — on offre l'outil adapté
  plutôt que de s'en priver, à charge pour `SCRIPTING.md` de porter l'écart en toutes lettres.
  C'est le même arbitrage que pour `math`, à une différence près qui doit rester visible :
  celui-là, on l'introduit sciemment.
- **Un nom de séquence est un DOMAINE** (`DOMAIN_SEQUENCE`), comme un nom d'animation. Ça
  donne d'un coup la validation (`sequence.start("intr")` refusé, avec la liste), la constante
  C, et le suivi des renommages — et `validator._check_api_domains` **oblige** le checker et le
  codegen à le traiter, sous peine de casser le build.
- **Le C émis garde l'ordre de la source** : un `case` par tranche, dans l'ordre d'écriture,
  chacun commenté avec sa ligne Lua. C'est la contrepartie exigée par la règle « le C se relit
  avec les mots du Lua » (v0.7.1, v0.7.2), que cette transformation met sous tension — à
  juger sur un vrai fichier émis, pas sur cette promesse.
- **L'état d'une séquence vit là où vit l'état du script**, donc dans la structure par slot
  posée par la v0.7.6 — un `int` d'étape de plus dans `g_state_<sym>[]`, sans cas
  particulier. C'est pour ça qu'elle passait avant : sans elle, cette version aurait ajouté
  un quatrième « sauf dans un prefab poolé » à une liste qui n'existe plus.

#### Décisions verrouillées — la forme écrite (2026-08-17)

- **Une séquence est `function on_sequence_<nom>()`.** Le préfixe `on_` est la marque du
  projet pour « le moteur appelle ça », et c'est exactement vrai : le moteur la fait avancer
  à chaque frame. Aucune catégorie nouvelle à retenir, et le refus existant tient tout seul —
  une fonction de premier niveau inconnue est DÉJÀ une erreur du checker
  (`checker.py`, « Fonction '<nom>' inconnue »), donc admettre cette forme-là n'ouvre rien
  d'autre.
- **Le namespace d'un nom de séquence est le SCRIPT, pas le projet.** C'est la première fois
  pour un domaine, et ça tombe bien : checker et codegen reçoivent déjà l'AST, ils collectent
  les noms eux-mêmes — aucun champ de contexte à porter depuis `build.py`. Conséquence à
  connaître : `refactor` dérive `DOMAIN_SEQUENCE` du catalogue comme les autres, mais aucun
  renommage d'asset ne le déclenchera, une séquence n'étant pas un asset de projet.
- **Trois portes, un seul entier** : `sequence.start(nom)`, `sequence.stop(nom)`,
  `sequence.running(nom)`. L'état d'une séquence est un entier où **0 = arrêtée** et
  **1..N = l'étape en cours** — `start` écrit 1, `stop` écrit 0, `running` teste ≠ 0. Les
  trois fonctions ne coûtent donc rien de plus que la première. `running` est ce qui permet
  d'enchaîner deux séquences ou de geler une commande pendant une cinématique, sans la
  variable globale tenue à la main que cette version veut justement supprimer.
- **Une TRANCHE PAR FRAME, et un `switch` sans boucle.** Chaque `case` s'exécute, avance
  l'étape, et rend la main. Une séquence à N attentes coûte donc N frames de plus qu'une
  exécution en ligne droite — invisible sur une cinématique, et c'est précisément « la même
  chose, à la frame près, que les `elseif` qu'on écrit aujourd'hui ». L'alternative (dérouler
  jusqu'à la prochaine VRAIE attente) demanderait un `for(;;)` autour du `switch`, donc un
  cycle sans attente pourrait figer la frame. Le `switch` nu ne peut structurellement pas
  tourner en rond.
- **Le pompage vit à la FIN de `on_update`**, dans l'ordre de déclaration des séquences. Un
  seul endroit, lisible dans le C émis, et rien à ajouter à la boucle de frame de `main.c` —
  laquelle appelle déjà `on_update` pour chaque propriétaire. Un script qui n'écrit aucun
  `on_update` en reçoit un : c'est le stub qui existe déjà, avec le pompage dedans.
- **Mêmes règles dans un script de SCÈNE et d'ACTEUR.** La transformation est identique ; seul
  diffère l'endroit où l'état atterrit, et la v0.7.6 a déjà répondu à ça (statique de fichier
  pour un propriétaire unique, champ de `g_state_<sym>[]` pour un prefab poolé). Donner autre
  chose à la scène serait un second chemin pour la même chose.

#### Décisions verrouillées — attendre (2026-08-17)

- **Deux primitives : `wait(frames)` et `wait_until(cond)`.** `wait_until` n'est pas un
  confort : sans lui, attendre la fin d'un `self:move_to(pos, 60)` oblige à réécrire `wait(60)`
  à côté — deux chiffres à tenir d'accord, dont le désaccord ne se voit qu'à l'œil. Et la durée
  d'un `text.reading(zone)` dépend du contenu, donc ne s'écrit pas en dur du tout.
- **`wait(n)` partage un compteur par séquence**, pas un par attente : une seule attente est
  active à la fois par construction. Une séquence qui ne contient que des `wait_until` n'a
  donc pas de compteur du tout.
- **Une variable locale d'une séquence SURVIT à l'attente.** Celle qui est relue après une
  attente devient un champ de l'état de la séquence. La règle se dit sans parler du C — *dans
  une séquence, une locale survit à l'attente* — et c'est ce qu'on attend en lisant du code
  écrit en ligne droite. L'analyse à écrire (« qui traverse une attente ? ») est la même que
  celle qu'aurait demandée un refus ; seule change la réponse, et hisser est la réponse
  aimable. Le coût apparaît dans la mesure `[ewram]` posée en v0.7.6.
- **Un `wait_until` dont la condition ne peut PAS changer bloque le build.** Le contrôle ne
  prétend pas tout attraper : il refuse le cas *décidable* — une condition sans appel d'API,
  sans global, sans propriété, dont les seuls noms sont des variables qu'**aucune ligne du
  script n'assigne**. `wait_until(false)` et `wait_until(SEUIL > 10)` sont donc refusés sur
  leur ligne ; une condition portant sur un global écrit par un autre script passe, et c'est
  assumé. Le prédicat réutilise `assigned_names()`, écrit pour la v0.7.6 — pas d'analyse
  neuve. Un contrôle qui ferme la faute bête sans inventer de surveillance au runtime : un
  watchdog aurait demandé un entier de plus par séquence et un seuil arbitraire, pour un
  comportement qui diverge entre « ça marche » et « ça a mis trop longtemps ».

#### Ce que le C émis donne, vérifié

Sur une séquence de SCÈNE de la démo (pas de `self`), les deux primitives, et une variable
qui traverse une attente :

```c
static void INTRO_scene_sequence_ouverture(void) {
    switch (INTRO_seq_ouverture_step) {
    case 1: {
        INTRO_seq_ouverture_depart = compteur;
        INTRO_seq_ouverture_step = 2;
    } break;
    case 2: {   /* wait(60) */
        if (++INTRO_seq_ouverture_timer < 60) break;
        INTRO_seq_ouverture_timer = 0;
        INTRO_seq_ouverture_step = 3;
    } break;
    case 3: {
        text_draw_in(REGION_INVITE, TEXT_INTRO_02);
        INTRO_seq_ouverture_step = 4;
    } break;
    case 4: {   /* wait_until */
        if (!((compteur >= (INTRO_seq_ouverture_depart + 90)))) break;
        INTRO_seq_ouverture_step = 0;
    } break;
    }
}
```

La contrepartie exigée par « le C se relit avec les mots du Lua » est tenue, et c'était la
seule promesse à juger sur pièce. Deux détails du rendu, décidés en écrivant :

- **Le commentaire d'une tranche nomme la construction, pas la ligne source.** Un numéro de
  ligne aurait demandé de porter la position dans tout l'AST (aujourd'hui seuls les nœuds
  refusés la portent), pour moins d'information que la condition C, qui est juste en dessous
  et se lit.
- **Chaque `case` est accolé** (`case 1: { … } break;`). Un `local` non hissé y est déclaré,
  et sauter par-dessus une déclaration dans un `switch` nu n'est pas correct en C.

Vérifié de bout en bout : ROM de la démo construite depuis zéro avec cette séquence, sans un
warning. Un prefab poolé porte le même mécanisme, son état passant dans `g_state_<sym>[]` —
mesuré par la jauge de la v0.7.6, une séquence coûte 4 octets par instance, plus 4 si elle
contient un `wait(n)`, plus 4 par variable qui traverse une attente.

#### Le pointeur d'état — dette de la v0.7.6, payée ici

Première version : chaque accès à l'état d'un prefab poolé réécrivait le chemin complet,
`g_state_Ball[Ball_pool_slot(self)].seq_entree_depart`. Trente-sept occurrences dans
`actor_Ball.c`, et le nom que l'auteur a écrit noyé dans 38 caractères de machinerie. Les
séquences n'ont pas créé le défaut — c'était la forme d'accès posée par la v0.7.6, que
`on_update` portait déjà — mais elles l'ont rendu voyant : un `switch` touche l'état trois
fois par tranche.

Le codegen pose désormais **un pointeur par fonction qui en a besoin** :

```c
static void Ball_sequence_entree(Actor* self) {
    BallState* _st = &g_state_Ball[Ball_pool_slot(self)];
    switch (_st->seq_entree_step) {
```

- **Posé seulement s'il sert.** `_state_ref()` lève un drapeau, `_close_state_scope()` insère
  la déclaration après coup — un pointeur déclaré et jamais lu, c'est un
  `-Wunused-variable` à chaque build. Corollaire : il n'y a pas de seuil à choisir, donc pas
  de chiffre arbitraire à défendre ; `pool_init`, qui n'y touche qu'une fois, le pose comme
  les autres.
- **Une seule forme d'accès**, chez les cinq émetteurs de corps (handlers, stubs,
  `pool_init`, séquences, behaviors inlinés). Corriger les seules séquences aurait laissé
  deux formes du même état dans un même fichier.
- **Le gain runtime est réel mais mineur, et ce n'était pas le motif.** Mesuré au
  désassemblage sur le prefab de la démo, pool de 4 avec une séquence :

| | instructions | divisions de slot |
| --- | --- | --- |
| forme d'origine | 853 | 6 |
| avec `_st` | **828** | **4** |

`sizeof(Actor)` vaut 144 octets — pas une puissance de deux — donc `self - g_actors` est une
division, que gcc développe en douze instructions Thumb. Il factorisait déjà presque tout
seul (37 accès → 6 calculs) ; le pointeur atteint le plancher de 4, soit un par fonction qui
touche l'état. La ROM de la démo perd 32 octets. **Le motif reste la lisibilité** : c'est la
règle « le code généré doit se comprendre par son auteur sans consulter Claude » qui était
en défaut, pas le budget.

#### Ouvert

- Rien côté ÉDITEUR : une séquence s'écrit et se lit dans le Script Editor, et la sidebar ne
  la propose pas (elle est dérivée de `RUNTIME_API`, où une séquence de l'utilisateur ne
  figure pas — même trou que pour les tables, cf. « Ouvert » de la v0.7).
- **Une séquence ne peut pas en attendre une autre** autrement qu'en testant
  `sequence.running`. Une primitive dédiée (`wait_sequence`) serait la même chose écrite plus
  court ; à rouvrir si le motif se répète.
- **L'état d'une séquence d'un propriétaire NON poolé est une statique de fichier**, donc il
  survit à un changement de scène — comme n'importe quelle variable de tête depuis toujours.
  Une scène quittée pendant sa cinématique la retrouve à son étape en y revenant. Cohérent
  avec le reste, jamais éprouvé sur un cas réel. Un prefab poolé, lui, repart propre : son
  `pool_init` remet l'état à zéro au spawn.
- **Une attente reste refusée dans un `if` ou une boucle.** C'est la limite du découpage en
  ligne droite, et elle est dite sur la ligne fautive avec ses deux issues. La lever
  demanderait une transformation en continuations, dont le C émis ne se relirait plus avec
  les mots du Lua — c'est-à-dire le prix que cette version refuse de payer. À rouvrir
  seulement si une cinématique réelle bute dessus.

---

### Ouvert

- **Rien dans la sidebar du Script Editor ne liste les tables.** Elle est dérivée de
  `RUNTIME_API`, et une table n'y figure pas — cf. la décision ci-dessus. Une section qui
  proposerait `data.Objets[1].prix` au clic serait utile ; elle demande une source de snippets
  qui ne vienne pas du catalogue.
- **La colonne `prefab`** et son `spawn_by_id`, ci-dessus. À rouvrir sur le premier vrai
  bestiaire — c'est là qu'on saura si l'aiguillage doit rendre l'acteur créé, et ce qu'il fait
  quand le pool est plein.
- L'import depuis un tableur (CSV). Rien ne l'exige, mais deux cents objets ne s'éditent pas
  ligne à ligne avec plaisir.
- La recherche de chemin : fournie par le moteur, ou laissée au script une fois les tableaux
  disponibles ? Un A\* écrit en Lua transpilé est faisable ; sa vitesse ne l'est peut-être pas.
  À trancher **mesuré**, pas supposé — les tableaux existants rendent l'expérience possible.
- Un tableau de travail à trois dimensions : rien ne l'interdit dans la règle « l'ordre des
  arguments est l'ordre des index », rien ne le réclame non plus.

---

## v0.8 — Son : la musique par scène, les transitions, le mixage

Les ressources son et musique sont aujourd'hui des ébauches, explicitement marquées comme
telles dans le code (`core/models/audio.py` porte un TODO en tête).

### L'état des lieux, relevé avant d'ouvrir le chantier (2026-08-17)

Le déséquilibre à connaître avant de découper : **le C est déjà largement en avance sur le
Lua.** Ce jalon expose plus qu'il ne construit.

| Couche | Ce qui existe |
| --- | --- |
| Modèle | `Sfx(asset, volume)`, `Music(asset, loop, volume)` — rien d'autre |
| Build | mmutil + bin2s → soundbank ; `mmInitDefault(…, 8)`, huit canaux **en dur** |
| Runtime C | `sfx_play(id, volume)`, `sfx_set_volume/panning/stop`, `sfx_set_effects_volume`, `music_play(id, loop, volume)`, `music_stop/pause/resume/is_playing/set_volume` |
| Lua | **quatre entrées** : `sfx.play(nom)`, `music.play(nom)`, `music.stop()`, `self:play_sfx()` |
| Écran | arbre d'assets, import, volume/loop par asset, aperçu — dont un rendu MOD en Python à `GBA_MIX_RATE` |

Volume et boucle voyagent déjà jusqu'à la ROM : le codegen les lit sur la RESSOURCE et les
pose dans l'appel émis (`sfx_play(SFX_GOAL, 255)`). Ce qui manque est donc la surcharge **à
l'appel**, pas la plomberie.

Et un trou qui n'apparaît dans aucune ligne du tableau : **la scène n'a pas de champ
musique.** Le codegen émet `mmStart(MOD_<première musique du projet>)` une fois, au boot
([main_gen.py:3256](editor/codegen/runtime_codegen/main_gen.py:3256)) ; tout le jeu joue donc
le premier morceau du catalogue, quel qu'il soit. Ce n'est pas une ébauche à enrichir, c'est
un emplacement réservé. Il passe devant le reste du jalon : **sans musique par scène, il n'y
a rien à faire transiter.**

### v0.8.1 — Clarifier les ressources

Format source des effets (wav brut ou conversion), hauteur ; format de musique (module
tracker) et point de bouclage.

- **Un trou concret, mesuré** : `SFX_FILE_EXTS` accepte `.ogg` et `.mp3`, `MUSIC_FILE_EXTS`
  accepte `.mp3`, et le dialogue d'import propose `*.ogg` — or les fichiers partent **bruts**
  à mmutil, qui ne connaît que le wav et les modules (mod/xm/s3m/it). Un `.ogg` déposé casse
  donc le build sur une sortie mmutil, jamais sur sa cause, et `validator.py` ne dit rien du
  son. Décider ce que l'éditeur accepte est exactement le sujet de ce chapitre : soit il
  convertit, soit il refuse en le disant à l'import.
- **La hauteur n'existe nulle part** : `ex.rate` est figé à `1024` dans le `sfx_play` émis.
  C'est le seul manque réel côté C.

#### Décisions verrouillées

- **Le point de bouclage vient du FICHIER, jamais d'un champ.** Un MOD porte sa position de
  restart dans son en-tête (octet 951, juste après la longueur du morceau), et
  `mod_file.py:78` la **jette** — le commentaire le dit lui-même : « position de restart —
  ignorée (v1) ». L'aperçu de l'éditeur reboucle donc toujours au début du morceau. La case
  « Loop » garde son sens — jouer une fois ou en boucle — mais *où* ça boucle appartient au
  fichier, et ne deviendra pas un réglage de l'éditeur.
  - **Premier travail du chantier : mesurer l'écart, pas le supposer.** Que mmutil transporte
    cette position jusqu'au format MAS et que Maxmod la relise en `MM_PLAY_LOOP` est plausible
    mais **non vérifié ici** ; tant que ça ne l'est pas, on ne sait pas si l'éditeur diverge de
    la ROM ou si les deux rebouclent pareil. Un module dont la position de restart n'est pas 0,
    écouté dans l'écran puis dans mGBA, répond en une manipulation. La réponse décide s'il y a
    un bug à corriger ou seulement un champ à afficher.
- **L'aperçu ne connaît que le ProTracker**, `mod_file.py` le dit en tête : ni XM, ni S3M, ni
  IT. Un `.xm` se construit donc en ROM mais reste muet dans l'écran. À **afficher** dans
  l'interface, pas à laisser découvrir en cliquant ▶ — même refus de la dégradation
  silencieuse qu'en v0.2.

### v0.8.2 — La musique par scène

Le socle du reste du jalon, et le seul morceau dont l'absence se voit déjà en jouant à la
démo. Une scène désigne sa musique comme elle désigne déjà sa caméra de démarrage (v0.6.1) et
ses réglages de transition (v0.6.2).

#### Décisions verrouillées

- **Trois valeurs, pas deux** : un morceau, `none` (silence explicite), et **`inherit` par
  défaut** — la scène ne touche pas à ce qui joue. Passer d'une salle à la suivante ne doit
  pas redémarrer le thème, et c'est aussi le cas le moins cher : aucun appel n'est émis.
  Le silence se **déclare** ; il ne s'obtient pas en laissant un champ vide.
- **Coût assumé** : dans une scène `inherit`, ce qui joue dépend d'où l'on vient. C'est voulu
  — une scène qui exige un morceau précis le déclare — mais ça se vérifie : le validateur peut
  nommer les scènes atteignables sans qu'aucune musique ait jamais été posée en amont.
- **Pas de réglage de projet ici**, contrairement aux transitions de scène. Un fondu par défaut
  vaut pour tout un jeu ; « le morceau par défaut du jeu » n'a pas de sens — c'est la scène de
  démarrage qui le pose, et `inherit` le propage tout seul. Ne pas recopier un mécanisme dont
  la raison d'être ne s'applique pas (même règle qu'en v0.4.2 pour la réservation de palettes).
- **Résolu au build**, une table par scène. Le runtime ne connaît pas la notion d'héritage.

### v0.8.3 — Les deux transitions, et ce que le matériel refuse

#### Le crossfade n'existe pas sur cette console

Le concept d'écran (2026-08-17) dessine un fondu enchaîné : deux enveloppes qui se recouvrent,
« Normal (Forest Theme) » qui s'éteint pendant que « Combat (Battle Theme) » monte. **Le
matériel ne le tient pas.** `maxmod.h` expose `mmPlayModule(address, mode, layer)` avec
exactement deux couches : le module principal, et le **jingle** — qui ne boucle pas par
construction. C'est une couche pour un cri de victoire, pas pour un second morceau. Deux
musiques ne jouent jamais ensemble durablement.

Le dessiner serait promettre un rendu que la console ne produit pas — même règle que la
rotation et le zoom écartés de la caméra en v0.6.1, même règle que « BLDCNT n'a qu'un seul
mode » en v0.3.1. **À ne pas reproposer.**

#### Les deux transitions honnêtes, nommées séparément

Séparément, parce qu'elles ne servent pas dans les mêmes cas et qu'un nom unique masquerait
laquelle on obtient.

| | Mécanisme | Ce que ça donne |
| --- | --- | --- |
| **Fondu traversant** | volume à 0, `mmStart`, volume remonte | marche entre deux morceaux quelconques ; laisse un creux, et le nouveau repart de son début |
| **Coupe à la position** | `mmGetPosition()`, `mmStart` la variante, `mmPosition()` au même motif | instantané, en mesure, sans creux, et le morceau ne repart pas de zéro |

La coupe à la position est **faite pour le catalogue de la démo** : 105 modules qui sont les
mêmes morceaux en variantes (`Admin Rights - Full DX` / `… DRUMLESS` / `… FAST` / `… SLOW`).
Deux variantes d'un même morceau partagent leur grille de motifs ; sauter de l'une à l'autre à
la même position, c'est littéralement « la batterie entre ». **C'est ça, l'intensité, sur ce
matériel** — pas un mixeur de couches, qui n'existe pas.

#### Décisions verrouillées

- **La compatibilité de deux variantes se vérifie au build, pas à l'oreille.**
  `mod_file.py` rend déjà `order` et `patterns` : deux modules dont la table d'ordre diffère en
  longueur ne peuvent pas se relayer à la position. Le validateur le dit en les nommant, sinon
  l'auteur entend un saut sans savoir d'où il vient.
- **La quantification vient de la MUSIQUE, jamais d'un champ en millisecondes.**
  `MMCB_SONGMESSAGE` remonte l'effet `EFx` que le compositeur a posé dans son module — c'est
  lui qui sait où une mesure se termine. À défaut de marqueur, `mmGetPositionRow()` donne la
  ligne courante. Un délai en ms saisi dans l'inspecteur serait faux dès que le tempo change,
  et faux en silence.
- **La bascule est différée, jamais instantanée-et-fausse.** Un changement demandé en cours de
  mesure attend le prochain point valide, comme un `scene.switch` appelé pendant une transition
  est honoré à la fin de celle-ci (v0.6.2). L'attente est prévisible et se comprend sans
  documentation.
- **`mmSetModuleTempo` et `mmSetModulePitch` ne sont pas des transitions.** Ce sont des molettes
  légitimes — les deux seules réellement continues de ce matériel — mais elles relèvent de
  l'API (v0.8.5), pas d'ici. Ni volet, ni filtre : ils demanderaient un mixeur.

### v0.8.4 — Écran de mixage

Existe déjà en partie, à enrichir : écoute du mélange en direct, volume par canal ou par
catégorie, gestion des priorités — le nombre de canaux matériels est limité.

L'écran d'aujourd'hui est un **navigateur d'assets avec aperçu** : ni mixage, ni volume par
catégorie, ni priorité. Mais `engine_emulation/mod_file.py` + `mod_render.py` rendent déjà un
module au taux de mixage de la GBA — la brique de l'écoute est là, et elle suit la règle de la
maison (l'éditeur refait en Python ce que la console fait en C, plutôt qu'une approximation).

#### Le budget affiché doit être celui du son

Le bandeau du bas montre OAM, cycles par ligne, VRAM et palettes. **Aucune de ces quatre
valeurs ne concerne le son.** La ressource rare ici, ce sont les **huit canaux logiciels**
partagés entre musique et effets, et le coût de `mmFrame` dans la frame. Un écran de son qui
affiche le budget des sprites ne ment pas sur les chiffres, il ment par déplacement — il
laisse croire qu'on voit ce qu'on dépense.

#### Ouvert

- Politique de priorité quand trop d'effets jouent en même temps : non décidée.
- Les huit canaux de `mmInitDefault` sont un littéral du codegen. Réglage de projet, ou
  chiffre dérivé de ce que le projet emploie ?

### v0.8.5 — API

Jouer un son ou une musique avec des surcharges de hauteur et de volume **à l'appel**, pas
seulement au niveau de la ressource.

C'est d'abord une **exposition** : `sfx_set_volume`, `sfx_set_panning`, `sfx_stop`,
`sfx_set_effects_volume`, `music_pause`, `music_resume`, `music_is_playing`,
`music_set_volume` existent en C et n'ont aucune porte Lua. La question de conception n'est
donc pas « comment faire », c'est **quelles portes ouvrir** — et `sfx_play` rend déjà un
`mm_sfxhand` que rien ne récupère, ce qui rouvre la question d'une référence d'effet en cours
dans un langage qui n'a que des entiers.

### v0.8.6 — La machine à états musicale

La surface d'authoring du concept : un graphe d'états, chacun portant un morceau, reliés par
des transitions nommées. Elle vient **après**, et par construction — elle ne fait que poser une
interface au-dessus de la musique par scène (v0.8.2) et des deux transitions (v0.8.3). Si elle
est repoussée, un jeu a quand même sa musique par scène et ses transitions, pilotables en Lua.
L'inverse n'est pas vrai.

#### Décisions verrouillées

- **Asset de premier rang, réutilisable entre scènes**, rangé avec les données propres au
  projet — même statut et même raison que la caméra en v0.6.1 : un graphe musical ne dépend
  d'aucun fichier importé, et il sert plusieurs scènes.
- **Le graphe ne possède pas le flux du jeu.** Un déclencheur est un **nom qu'un script émet**,
  jamais une condition que le moteur évalue. Le moteur qui déciderait *quand* la musique passe
  au combat déciderait de ce qu'est un combat — c'est une décision de genre, refusée pour la
  même raison que l'éditeur de dialogue (v0.3.2) et que la « scène de reprise » (v0.5).
- **Un état, c'est un morceau, son mode de bouclage, et par quelle transition on y entre.**
  Rien de plus. Le curseur « Intensity » du concept est un pourcentage **sans cible nommée** :
  sur ce matériel il ne peut désigner que le volume du module, son tempo, ou le choix d'une
  variante. Un curseur qui ne dit pas lequel promet un mixeur de couches qui n'existe pas.
- **Résolu au build**, comme le reste : le runtime lit une table, il ne parcourt pas un graphe.

#### Ouvert

- **Deux chemins pour changer la musique.** `music.play("X")` existe ; `music.trigger("…")`
  arriverait à côté. C'est exactement le grief porté contre le modèle GB Studio en v0.13 — deux
  chemins d'authoring pour la même logique. Trois issues : la machine à états absorbe
  `music.play`, elle coexiste comme couche facultative, ou elle reste hors du Lua. **À trancher
  quand le socle sera en main**, pas maintenant.
- **Ce que « Parameters » devient, s'il devient quelque chose.** Une courbe qui mappe
  « Player HP » vers une intensité suppose une molette continue ; il n'y en a que deux (volume,
  tempo). Si l'intensité choisit une variante, ce sont des **seuils**, et l'interface doit
  montrer des seuils — une courbe lissée dessinerait un fondu qui n'aura pas lieu.
- **La position des nœuds** : disposition automatique, ou déplaçable et mémorisée quelque part ?
  Même question qu'en v0.12, et elle mérite la même réponse — c'est une décision de modèle, pas
  d'affichage.

---

## v0.9 — Traduction des jeux créés avec l'éditeur

Sujet **séparé** de la traduction de l'éditeur (v0.11) : deux chantiers indépendants.

### Périmètre

- Tables de chaînes multilingues, basées sur les clés posées en v0.3 — c'est précisément pour
  éviter un refactor complet ici que les textes sont référencés par clé depuis le début.
- Sélection de la langue en jeu, persistée par la sauvegarde de la v0.5.

### Ouvert

- Format des tables multilingues non défini.
- Workflow de traduction pour quelqu'un sans compétence de développement : édition directe
  dans l'éditeur, ou export/import type tableur ?

---

## v0.10 — Distribution élargie

Réactivation de la construction Linux (en pause, en attendant un test sur une vraie
distribution).

### Ouvert

- macOS réellement souhaité ? La notarisation Apple a un coût récurrent — « Linux seul » est
  une option valable si le coût ne se justifie pas.

---

## v0.11 — Traduction de l'interface de l'éditeur

Complètement indépendant du runtime GBA. Déplaçable librement dans l'ordre : peut être fait
en parallèle de n'importe quelle autre version.

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

## v0.14 — Diagnostic — ce que le jeu fait, et ce qu'il coûte

Le pipeline sait construire un jeu ; il ne sait rien dire de ce que ce jeu fait une fois
lancé. Les deux manques sont vécus quotidiennement par qui développe, et aucun n'est couvert.

### Le problème

- **Rien ne permet de déboguer.** L'auteur écrit du Lua, qui devient du C, qui tourne sur du
  matériel. Quand un acteur ne bouge pas, il n'a ni trace, ni journal, ni point d'arrêt.
  `display.print` a été retiré en v0.3.2 et rien ne l'a remplacé **pour le développeur** —
  `text.draw` s'adresse au joueur, ce qui n'est pas la même chose : il consomme des tuiles de
  police, il passe par la table de textes, il est traduisible. Aucun de ces traits ne convient
  à une trace de mise au point.
- **Rien ne dit ce que la frame coûte.** Côté build, l'outillage est bon : VRAM et palettes
  sont alloués, vérifiés, et le budget est signalé en erreur bloquante. Côté exécution, il n'y
  a rien. « Le jeu tombe à 40 fps avec douze acteurs » n'a aucune réponse dans le logiciel, et
  c'est le mur qu'on prend au troisième mois de projet.

### Décisions verrouillées

- **La trace de débogage sort de la ROM, pas de l'écran.** mGBA expose un canal de journal
  qu'une ROM peut écrire ; c'est là que va `debug.log`, pas dans un coin de l'affichage. Le
  jeu n'a donc rien à sacrifier pour être débogué — ni tuiles, ni palette, ni calque — et la
  trace survit à un écran plein.
- **`debug.*` disparaît des builds de release.** Sinon la mise au point coûte de la ROM et des
  cycles dans le jeu livré. Un appel retiré à la compilation, pas une fonction qui teste un
  drapeau au runtime.
- **Le budget se mesure sur la CIBLE, jamais estimé par l'éditeur.** Un chiffre de coût qui
  viendrait d'un modèle Python serait faux dès la première divergence, et faux en silence.
  C'est la même règle que pour l'aperçu du rasteriseur en v3.0 : ce qui prétend décrire le
  matériel vient du matériel.

### Ouvert

- Ce que `debug.log` accepte : une chaîne formatée demande un `printf` en ROM, ce que le
  moteur évite partout ailleurs. Concaténer des valeurs déjà converties suffit peut-être.
- Où le budget s'affiche : superposé en jeu (donc il fausse ce qu'il mesure), renvoyé au
  journal, ou lu par l'éditeur pendant que la ROM tourne ?
- Ce que le budget couvre au-delà du temps de frame : compte d'OAM, occupation des canaux
  sonores, cycles DMA. À choisir sur ce qui sature réellement, mesuré, pas supposé.

---

## v0.15 — Visibilité des éléments d'interface — **LIVRÉE**

Livrée conforme sur le modèle et le runtime, **sous une autre forme côté Lua** : la décision
verrouillée annonçait `ui.show(nom, on)`, le code expose `ui.get("nom"):show()` / `:hide()`.
La raison est arrivée entre-temps — cf. « La forme écrite, et pourquoi elle a changé ».

#### Le problème

`UILayout` ([ui_region.py](editor/core/models/ui_region.py)) savait dessiner un `UIText`, un
`UIPanel` ou une `UIImage`, mais aucun des trois ne savait *disparaître* proprement. Le seul
équivalent existant était asymétrique et incomplet :

- `UIImage` avait un show/hide runtime — `ui.image_show(nom, on)` — qui posait `attr0 =
  0x0200` en cible OBJ et effaçait les tuiles déjà écrites en cible BG
  (`ui_image_clear_bg`).
- `UIText` n'avait rien d'équivalent : la seule façon de le « cacher » était `text.clear_in`,
  qui efface le *contenu*, pas l'existence de la zone.
- `UIPanel` n'avait aucune identité runtime en dehors de son fond sprite (`g_ui_images` si
  `fill_kind == sprite`) — un panel-groupe pur n'existait dans aucune table C.

### Le besoin

Une propriété `visible` sur les trois types, et qui **se transmet aux enfants** : cacher un
panel doit cacher tout son sous-arbre sans qu'il faille toucher un seul enfant.

### Décisions verrouillées

- **Authoré ET piloté au script**, pas l'un ou l'autre. Un champ `visible: bool = True` posé
  dans le JSON pour l'état initial (même logique que `text_key` vide = zone que le script
  remplit), plus un appel Lua générique pour basculer au runtime. Un élément qui ne doit
  jamais apparaître avant qu'un script en décide autrement ne doit pas passer par une
  case cochée puis un appel immédiat au chargement de la scène.
- **La propagation aux enfants se calcule à la lecture, elle ne s'écrit jamais.** L'arbre de
  `UILayout` est déjà dérivé des refs `parent` et jamais stocké (`children()`, `ancestors()`,
  `descendants()`). La visibilité suit la même règle : chaque élément ne porte que son
  propre bit ; la visibilité effective remonte la chaîne des parents à la lecture
  (`layout.ancestors(name)`), sans jamais pousser un état vers les descendants. Cacher un
  enfant individuellement puis remontrer son parent le laisse caché — comportement
  prévisible, sans propagation à écrire ni à désynchroniser.
- **Une seule API Lua pour les trois types**, plutôt qu'une par type. Un panel et une image
  partagent déjà une surface d'accès commune côté fond sprite ; étendre ce principe à la
  visibilité évite une troisième fonction (`ui.text_show` en plus de `ui.image_show`) pour le
  même concept. `ui.image_show` est remplacé, pas dupliqué. ~~`ui.show(nom, on)`~~ — la forme
  exacte a changé, cf. ci-dessous.
- **Le BG et l'OBJ restent deux chemins distincts, comme partout ailleurs dans `UILayout`** :
  cacher un élément en cible OBJ pose `attr0 = 0x0200` (déjà fait pour les images) ; en cible
  BG ça déclenche le `clear` déjà écrit (`text_clear_in`, `ui_image_clear_bg`) — pas de
  nouveau chemin de rendu, seulement une garde avant l'écriture existante.

### La forme écrite, et pourquoi elle a changé

`ui.show("alerte", false)` a été remplacé par `ui.get("alerte"):hide()` en écrivant le
chantier, pour une raison qui n'existait pas au moment de la décision : **la v0.7.4 avait
posé une grammaire**, et `ui.show(nom, on)` ne la respecte pas. La règle dit *requête indexée
→ fonction, action → méthode* — cacher un élément est une action, sur un élément qu'on
désigne d'abord.

- **Le même schéma que `get_actor`**, qui existait déjà : un nom résolu en une constante à la
  compilation, puis appelée en `:`. `ui.get("alerte")` s'émet `UIELEM_ALERTE` et rien d'autre —
  aucune fonction runtime, la même constante que celle émise en tête de fichier pour la table.
  Deux façons de désigner un élément de scène auraient été deux choses à apprendre.
- **Une référence, pas un identifiant nu.** Un nom d'élément écrit sans porte
  (`alerte:hide()`) collisionnerait avec les namespaces `ui` / `text` / `camera`.
- **`show()` et `hide()`, pas `show(on)`.** Le booléen au site d'appel ne se lit pas :
  `ui.show("alerte", false)` demande de savoir dans quel sens va le drapeau, `:hide()` non.
- **`DOMAIN_UI_ELEMENT` est un domaine à part entière**, distinct de `DOMAIN_REGION` (les
  zones de texte) : il couvre les trois types confondus. Il hérite donc gratuitement des trois
  consommateurs — le checker refuse un nom absent de la mise en page, le codegen émet
  `UIELEM_*`, et le refactor suit les renommages.

### Ce que ça donne côté runtime

Un panel-groupe pur n'avait aucune ligne dans aucune table C. La visibilité générique par NOM
a donc demandé une table plate indexée sur **tous** les éléments de `UILayout.elements`
(texte, panel, image confondus), pas seulement ceux qui dessinent — `g_ui_elements`, construite
par le codegen dans le même ordre que `slots`/`images` le font déjà pour leurs propres tables.
Chaque entrée porte son propre bit et l'index de son parent ; `ui_element_is_visible(idx)`
remonte la chaîne, et l'effectif n'est **jamais** stocké — exactement la règle du modèle Python
(`UILayout.is_visible`). Profondeur d'arbre d'UI toujours minuscule, donc coût négligeable.
`g_ui_regions` et `g_ui_images` portent chacun l'index de leur ligne dans cette table,
consultée avant chaque écriture.

### Les deux « Ouvert » sont tranchés

- **`ui.image_show` : suppression franche**, pas d'alias. Elle est entrée dans `REMOVED_API`
  avec la phrase qui dit quoi écrire à la place — la porte ouverte en v0.7.4, quand retirer une
  API sans le dire s'était révélé insuffisant à la retirer vraiment. Les scripts de Pong sont
  migrés.
- **La constante d'un panel-groupe est `UIELEM_*`**, un troisième espace à côté de `REGION_*`
  et `IMAGE_*` — et c'est lui que `ui.get` rend, quel que soit le type de l'élément. Le nommer
  d'après l'un des deux autres aurait fait croire à une table de dessin.

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

Les deux premiers sont **atteignables aujourd'hui**. Les trois suivants attendent la v0.7 —
c'est le seul verrou, et c'est pourquoi elle passe devant.

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
- **Des formats que git sait relire.** Aujourd'hui un fond fait 688 lignes et la carte de
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
- **La vérification que ça tient à l'échelle.** `Project.load()` charge tout, tout de suite —
  chaque sidecar de chaque collection. Pong et ses 118 fichiers vont très bien ; quarante
  scènes et deux cents sprites, personne n'en sait rien. L'affirmation « absorbe un projet de
  production » se vérifie ou s'écroule exactement là, et c'est le deuxième jeu de démo qui
  tranchera.

### Ouvert

- Lequel des trois genres bloqués sert de démo. À trancher quand la v0.7 est livrée, sur ce
  qu'elle rend réellement confortable.
- Les menus et listes (curseur, défilement, sélection) sont aujourd'hui du script pur
  par-dessus `UILayout`. Faisable — mais si les trois genres à menus le rendent pénible, c'est
  ici que ça se verra, et il faudra décider si le moteur en prend une part.

---

## Au-delà de la v1.0

### Chantier transverse — l'allocateur de ressources matérielles

Ne porte pas de numéro de version : il **se déclenche par un événement**, pas par une date —
le jour où une ressource matérielle a son deuxième consommateur. Le premier candidat est le
viewport de caméra / l'écran partagé de la v2.0, qui rouvre déjà « une région appartient-elle
à une caméra, ou l'inverse ? ». Le second est le clipping d'UI.

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
- **L'assignation matérielle reste visible, dans un panneau avancé.** Le principe « l'auteur
  peut descendre jusqu'au matériel » n'est pas suspendu : il ne nomme plus la ressource pour
  obtenir un masque, mais il peut voir laquelle lui a été donnée, et la forcer.

#### Ce qu'il faut faire AVANT, et qui ne coûte presque rien

L'allocateur complet attend son deuxième client — une abstraction à un seul consommateur se
dessinerait contre des besoins imaginés. Deux gestes se font en revanche dès maintenant, et
rendent le reste possible sans rien casser :

1. **Le principe est écrit** (fait — cf. ARCHITECTURE), pour que rien de neuf ne lie un
   concept de haut niveau à un slot matériel d'ici là.
2. **Cesser de faire de `WindowSlot.region` un index matériel côté auteur.** C'est une
   indirection et un renommage, pas un ordonnanceur.

#### Ouvert

- L'API Lua `window.set_layer(r, …)` expose les régions par numéro matériel, et des scripts
  les adressent déjà ainsi. C'est la partie la plus dure à déplacer, et la maison ne migre
  pas les formats — à traiter comme une rupture assumée, au bon moment.
- Jusqu'où va l'allocateur de frame. Un arbitrage OAM par frame est un vrai coût CPU ; il se
  décide sur un cas mesuré, pas à l'avance.

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

Deux choses à traiter à ce moment-là, pas avant : **unifier les mécanismes de caméra
concurrents** (c'est quand la caméra devient un objet nommé porteur d'un état qu'il devient
absurde d'en avoir deux), et l'**écran partagé**, qui rouvrira la question « une région
appartient-elle à une caméra, ou l'inverse ? ». Tant que les caméras sont exclusives, la
question ne se pose pas.

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
