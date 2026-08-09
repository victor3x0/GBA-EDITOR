
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
| v0.4 | Éditeur de background & animation de tuiles | Partiellement entamée par ricochet |
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
donc à la fois le texte (v0.3.2) et, plus tard, l'éditeur de background — les deux chantiers
ne se recouvrent pas.

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

## v0.4 — Éditeur de background & animation de tuiles

### v0.4.1 — Éditeur de background

#### Déjà là, par ricochet de la v0.2 et de la v0.3

L'écran existe, mais uniquement dans sa dimension **couleur** : importer une image, laisser
l'éditeur détecter son mode et l'encoder, repeindre la palette tuile par tuile.

S'y est ajoutée la notion de **sorte de fond** — décor, interface, animé — portée par un
champ sur l'asset plutôt que par trois types distincts : les trois partagent tout le pipeline
d'import, d'encodage et de palettes, et trois classes auraient triplé ça pour un champ de
différence. Le cadre nine-slice n'est donc plus un asset séparé, c'est un fond marqué
« interface ».

Pour les fonds animés, une règle à retenir : **le placement vit chez l'hôte, pas chez
l'animé**. Une cascade dessinée une fois se pose dans trois décors ; stocker les positions
dans l'animé obligerait à y citer les fonds qui l'emploient, c'est-à-dire à inverser le sens
de la référence. L'éditeur est livré ; **le support ROM des fonds animés reste à écrire**, et
c'est le voisin naturel de la v0.4.2.

Ce qui reste donc **entièrement** à faire, c'est la *peinture de tuiles* : composer une carte
en posant des tuiles, au lieu de recolorer une image importée.

#### Décisions verrouillées

- Dessiner directement sur les calques de fond avec des **tilesets importés par
  l'utilisateur**, jamais compilés tels quels. Le résultat s'ajoute à une scène.
- Le même écran sert à créer des **calques d'interface réutilisables** entre scènes, sans
  redéfinition.

#### Ouvert

- Décor et calque d'interface réutilisable en parallèle impliquent plusieurs zones de mémoire
  vidéo simultanées — l'ampleur du changement n'est pas évaluée.
- Un « calque d'interface réutilisable » est-il un nouveau type d'asset, ou une variante du
  fond existant ?
- Un indicateur de budget mémoire vidéo dans l'éditeur, évoqué en principe mais pas conçu —
  pertinent dès que plusieurs tilesets coexistent.

### v0.4.2 — Animation de tuiles

#### Décisions verrouillées

Trois techniques, selon le cas d'usage :

1. **Changer l'index dans la carte** — peu coûteux, bien pour une torche ou une flaque d'eau.
2. **Réécrire la tuile elle-même** — anime d'un coup toutes les cases qui l'utilisent, coût
   par image, bien pour un effet plein écran.
3. **Faire tourner les couleurs d'une palette** — eau, lave qui scintille : quasi gratuit, et
   se branche naturellement sur l'écran Palette de la v0.2.

---

## v0.5 — Sauvegarde (SRAM/Flash)

S'appuie sur les variables globales déjà existantes pour décider quoi persister.

### Ouvert (quasiment tout)

- Portée : toutes les variables globales, ou une sélection explicite dans l'éditeur ?
- Un seul emplacement de sauvegarde, ou plusieurs ?

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
